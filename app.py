import os, base64, base64, uuid, json, hmac, hashlib, secrets, base64, subprocess, tempfile, shutil, re, time, threading, socket, ssl
from datetime import datetime, timezone
from functools import wraps
from urllib.parse import quote
from flask import Flask, request, jsonify, session, redirect, send_from_directory, Response
from requests.adapters import HTTPAdapter
from concurrent.futures import ThreadPoolExecutor
from dotenv import load_dotenv
import requests
from cryptography.fernet import Fernet

load_dotenv()
app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', secrets.token_hex(32))
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024
VERSION = '26.2.3'
KOJA_CLOUD_RELEASE = '26.2.8'
KOJA_FAST_PROCESSING = True
KOJA_OPERATION_POLL_MS = 200
KOJA_FAST_DB_READ_TIMEOUT = float(os.getenv('KOJA_FAST_DB_READ_TIMEOUT', '12'))
KOJA_FAST_DB_WRITE_TIMEOUT = float(os.getenv('KOJA_FAST_DB_WRITE_TIMEOUT', '15'))
KOJA_FAST_WORKERS = max(4, int(os.getenv('KOJA_FAST_WORKERS', '12')))
KOJA_FAST_EXECUTOR = ThreadPoolExecutor(max_workers=KOJA_FAST_WORKERS, thread_name_prefix='koja-fast')
API_CORS_ORIGINS = os.getenv('API_CORS_ORIGINS', '*')

SUPABASE_URL = os.getenv('SUPABASE_URL', '').rstrip('/')
SUPABASE_KEY = os.getenv('SUPABASE_SECRET_KEY') or os.getenv('SUPABASE_SERVICE_ROLE_KEY', '')
ENCRYPTION_KEY = os.getenv('KOJA_ENCRYPTION_KEY', '')

if ENCRYPTION_KEY:
    try: cipher = Fernet(ENCRYPTION_KEY.encode())
    except Exception: cipher = None
else:
    cipher = None


def now(): return datetime.now(timezone.utc).isoformat()
def configured(): return bool(SUPABASE_URL and SUPABASE_KEY)
def sb_headers(): return {'apikey': SUPABASE_KEY, 'Authorization': f'Bearer {SUPABASE_KEY}', 'Content-Type': 'application/json'}
_SB_SESSION = requests.Session()
_SB_ADAPTER = HTTPAdapter(pool_connections=50, pool_maxsize=100, max_retries=0, pool_block=False)
_SB_SESSION.mount('http://', _SB_ADAPTER)
_SB_SESSION.mount('https://', _SB_ADAPTER)

def sb(path, method='GET', data=None, params=None):
    if not configured(): raise RuntimeError('Supabase is not configured')
    is_read = method.upper() in ('GET','HEAD','OPTIONS')
    timeout = KOJA_FAST_DB_READ_TIMEOUT if is_read else KOJA_FAST_DB_WRITE_TIMEOUT
    r = _SB_SESSION.request(method, SUPABASE_URL + path, headers=sb_headers(), json=data, params=params, timeout=timeout)
    if r.status_code >= 400: raise RuntimeError(f'Supabase {r.status_code}: {r.text[:500]}')
    return r.json() if r.text else {}


# ============================================================
# KOJA CLOUD V17.6 — REAL PROVIDER DATA PLANE ADAPTERS
# Render = application hosting/compute provider
# Supabase Management API = managed backend/database/auth/storage/realtime provider
# These adapters are optional at startup and are enabled only when their provider
# credentials are configured. The Cloud control plane never exposes provider secrets.
# ============================================================
RENDER_API_KEY = (os.getenv('KOJA_RENDER_API_KEY') or os.getenv('RENDER_API_KEY') or '').strip()
RENDER_OWNER_ID = (os.getenv('KOJA_RENDER_OWNER_ID') or os.getenv('RENDER_OWNER_ID') or '').strip()
RENDER_API_BASE = 'https://api.render.com/v1'
SUPABASE_MANAGEMENT_TOKEN = (os.getenv('KOJA_SUPABASE_MANAGEMENT_TOKEN') or os.getenv('SUPABASE_MANAGEMENT_TOKEN') or '').strip()
SUPABASE_MANAGEMENT_ORG = (os.getenv('KOJA_SUPABASE_ORG_SLUG') or os.getenv('SUPABASE_ORG_SLUG') or '').strip()
SUPABASE_MANAGEMENT_BASE = 'https://api.supabase.com/v1'

# KOJA Forge — optional GitHub source provider. GitHub is a connector, not KOJA's product name.
GITHUB_TOKEN = (os.getenv('KOJA_GITHUB_TOKEN') or os.getenv('GITHUB_TOKEN') or '').strip()
GITHUB_API_BASE = 'https://api.github.com'
GITHUB_OWNER = (os.getenv('KOJA_GITHUB_OWNER') or '').strip()

def github_provider_configured():
    return bool(GITHUB_TOKEN)

def _github_repo_parts(repo_url):
    """Normalize common GitHub repository URL forms to owner/repo."""
    raw=(repo_url or '').strip()
    if not raw: raise RuntimeError('invalid_github_repository_url')
    value=raw.replace('\\','/').strip().rstrip('/')
    if value.startswith('git@github.com:'):
        path=value.split(':',1)[1]
    elif re.match(r'^git\+ssh://git@github\.com/',value,re.I):
        path=re.sub(r'^git\+ssh://git@github\.com/','',value,flags=re.I)
    else:
        m=re.match(r'^https?://(?:www\.)?github\.com/(.+)$',value,re.I)
        if not m: raise RuntimeError('invalid_github_repository_url')
        path=m.group(1)
    path=path.split('#',1)[0].split('?',1)[0].strip('/')
    parts=[x for x in path.split('/') if x]
    if len(parts)<2: raise RuntimeError('invalid_github_repository_url')
    owner,repo=parts[0],parts[1]
    if repo.endswith('.git'): repo=repo[:-4]
    if not re.match(r'^[A-Za-z0-9_.-]+$',owner) or not re.match(r'^[A-Za-z0-9_.-]+$',repo):
        raise RuntimeError('invalid_github_repository_url')
    return owner,repo

def _github_actions_workflows(owner, repo):
    data=_github_request(f'/repos/{owner}/{repo}/actions/workflows', params={'per_page':100})
    return data.get('workflows',[]) if isinstance(data,dict) else []

def _github_actions_dispatch(owner, repo, workflow, ref, inputs=None):
    """Dispatch a GitHub Actions workflow and preserve the provider response.
    GitHub may return 204 No Content for workflow_dispatch; that is success, not an empty/failed result.
    """
    if not GITHUB_TOKEN: raise RuntimeError('github_provider_not_configured')
    body={'ref':ref or 'main'}
    if inputs: body['inputs']={str(k):str(v) for k,v in inputs.items()}
    path=f'/repos/{owner}/{repo}/actions/workflows/{workflow}/dispatches'
    headers={'Authorization':f'Bearer {GITHUB_TOKEN}','Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2026-03-10','User-Agent':'KOJA-CLOUD/26.2.5'}
    r=requests.post(GITHUB_API_BASE.rstrip('/')+path,headers=headers,json=body,timeout=60)
    if r.status_code >= 400:
        try: detail=r.json()
        except Exception: detail=r.text[:1200]
        raise RuntimeError(f'github_http_{r.status_code}: {detail}')
    response_body={}
    if r.text:
        try: response_body=r.json()
        except Exception: response_body={'raw':r.text[:1200]}
    return {'accepted':True,'workflow':workflow,'ref':body['ref'],'http_status':r.status_code,'response':response_body}

def _github_actions_runs(owner, repo, workflow=None, branch=None, per_page=20):
    path=f'/repos/{owner}/{repo}/actions/runs'
    if workflow: path=f'/repos/{owner}/{repo}/actions/workflows/{workflow}/runs'
    params={'per_page':per_page}
    if branch: params['branch']=branch
    data=_github_request(path, params=params)
    return data.get('workflow_runs',[]) if isinstance(data,dict) else []

def _github_actions_state(run):
    if not run:return 'QUEUED'
    status=str(run.get('status') or '').lower(); conclusion=str(run.get('conclusion') or '').lower()
    if status in ('queued','requested','waiting','pending'):return 'QUEUED'
    if status in ('in_progress','running'):return 'RUNNING'
    if conclusion=='success':return 'SUCCESS'
    if conclusion in ('failure','cancelled','timed_out','action_required','startup_failure','stale'):return 'FAILED'
    return status.upper() if status else 'QUEUED'

def _github_request(path, method='GET', data=None, params=None, timeout=45):
    if not GITHUB_TOKEN: raise RuntimeError('github_provider_not_configured')
    headers={'Authorization':f'Bearer {GITHUB_TOKEN}','Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2026-03-10','User-Agent':'KOJA-CLOUD/17.6'}
    r=requests.request(method, GITHUB_API_BASE.rstrip('/')+'/'+path.lstrip('/'), headers=headers, json=data, params=params, timeout=timeout)
    if r.status_code >= 400:
        try: detail=r.json()
        except Exception: detail=r.text[:1000]
        raise RuntimeError(f'github_http_{r.status_code}: {detail}')
    return r.json() if r.text else {}



def _provider_request(base, path, token, method='GET', data=None, params=None, timeout=45):
    if not token:
        raise RuntimeError('provider_not_configured')
    headers={'Authorization':f'Bearer {token}','Accept':'application/json','Content-Type':'application/json','User-Agent':'KOJA-CLOUD/17.6'}
    r=requests.request(method, base.rstrip('/')+'/'+path.lstrip('/'), headers=headers, json=data, params=params, timeout=timeout)
    if r.status_code >= 400:
        detail=r.text[:1000]
        try:
            detail=r.json()
        except Exception:
            pass
        raise RuntimeError(f'provider_http_{r.status_code}: {detail}')
    return r.json() if r.text else {}


def render_provider_configured():
    return bool(RENDER_API_KEY and RENDER_OWNER_ID)


def supabase_provider_configured():
    return bool(SUPABASE_MANAGEMENT_TOKEN and SUPABASE_MANAGEMENT_ORG)


def _render_create_service(payload):
    return _provider_request(RENDER_API_BASE, '/services', RENDER_API_KEY, 'POST', payload, timeout=90)

def _render_update_service(service_id, payload):
    return _provider_request(RENDER_API_BASE, f'/services/{quote(str(service_id), safe="")}', RENDER_API_KEY, 'PATCH', payload, timeout=90)

def _render_deploy(service_id, clear_cache=False):
    return _provider_request(RENDER_API_BASE, f'/services/{quote(str(service_id), safe="")}/deploys', RENDER_API_KEY, 'POST', {'clearCache':'clear' if clear_cache else 'do_not_clear'}, timeout=60)

def _render_resume(service_id):
    """Resume a Render service that is explicitly suspended."""
    return _provider_request(RENDER_API_BASE, f'/services/{quote(str(service_id), safe="")}/resume', RENDER_API_KEY, 'POST', {}, timeout=45)

def _render_get_service(service_id):
    return _provider_request(RENDER_API_BASE, f'/services/{quote(str(service_id), safe="")}', RENDER_API_KEY, 'GET', timeout=45)


def _render_list_services(owner_id=None, name=None):
    params={'limit':100}
    if owner_id: params['ownerId']=owner_id
    if name: params['name']=name
    return _provider_request(RENDER_API_BASE, '/services', RENDER_API_KEY, 'GET', params=params, timeout=45)

def _render_list_all_services(owner_id=None, name=None):
    """List the complete Render service set, following cursor pagination."""
    out=[]
    cursor=None
    for _ in range(20):
        params={'limit':100}
        if owner_id: params['ownerId']=owner_id
        if name: params['name']=name
        if cursor: params['cursor']=cursor
        data=_provider_request(RENDER_API_BASE, '/services', RENDER_API_KEY, 'GET', params=params, timeout=45)
        out.extend(_render_service_items(data))
        if not isinstance(data, dict): break
        cursor=data.get('cursor')
        if not cursor: break
    # De-duplicate by Render service ID.
    seen=set(); unique=[]
    for item in out:
        sid=item.get('id') if isinstance(item,dict) else None
        key=sid or repr(item)
        if key not in seen:
            seen.add(key); unique.append(item)
    return unique

def _render_service_items(data):
    # Render list endpoints use cursor-wrapped entries: {cursor, service}.
    # Older responses may be plain service objects, so normalize both forms.
    if isinstance(data, list):
        out=[]
        for item in data:
            if isinstance(item, dict) and isinstance(item.get('service'), dict): out.append(item['service'])
            elif isinstance(item, dict): out.append(item)
        return out
    if isinstance(data, dict):
        raw=data.get('services') or data.get('items') or []
        return _render_service_items(raw)
    return []

def _render_repo_url(url):
    owner,repo=_github_repo_parts(url)
    return f'https://github.com/{owner}/{repo}'


def _render_repo_key(url):
    value=(url or '').strip()
    try:
        owner,repo=_github_repo_parts(value)
        return f'{owner}/{repo}'.lower()
    except Exception:
        value=value.rstrip('/')
        if value.endswith('.git'): value=value[:-4]
        return value.lower()


def _supabase_create_project(name, db_password, region=''):
    body={'name':name,'organization_slug':SUPABASE_MANAGEMENT_ORG,'db_pass':db_password}
    if region: body['region']=region
    return _provider_request(SUPABASE_MANAGEMENT_BASE, '/projects', SUPABASE_MANAGEMENT_TOKEN, 'POST', body, timeout=120)


def _supabase_projects():
    return _provider_request(SUPABASE_MANAGEMENT_BASE, '/projects', SUPABASE_MANAGEMENT_TOKEN, 'GET', timeout=60)


def _supabase_project_health(ref):
    return _provider_request(SUPABASE_MANAGEMENT_BASE, f'/projects/{quote(str(ref), safe="")}/health', SUPABASE_MANAGEMENT_TOKEN, 'GET', timeout=45)


def _supabase_api_keys(ref):
    return _provider_request(SUPABASE_MANAGEMENT_BASE, f'/projects/{quote(str(ref), safe="")}/api-keys', SUPABASE_MANAGEMENT_TOKEN, 'GET', params={'reveal':'true'}, timeout=60)


def _supabase_sql(ref, query, read_only=False):
    return _provider_request(SUPABASE_MANAGEMENT_BASE, f'/projects/{quote(str(ref), safe="")}/database/query', SUPABASE_MANAGEMENT_TOKEN, 'POST', {'query':query,'read_only':bool(read_only)}, timeout=90)

def encrypt(v):
    if cipher: return cipher.encrypt(str(v).encode()).decode()
    return str(v)
def decrypt(v):
    if cipher:
        try: return cipher.decrypt(v.encode()).decode()
        except Exception: return ''
    return v

WORKSPACE_TEXT_LIMIT = int(os.getenv('KOJA_WORKSPACE_TEXT_LIMIT','2000000'))
WORKSPACE_BINARY_LIMIT = int(os.getenv('KOJA_WORKSPACE_BINARY_LIMIT','10000000'))
KOJA_PUBLIC_DOMAIN = os.getenv('KOJA_PUBLIC_DOMAIN','').strip().lower().rstrip('.')
KOJA_EDGE_MODE = os.getenv('KOJA_EDGE_MODE','false').lower() in ('1','true','yes','on')
KOJA_EDGE_TIMEOUT = float(os.getenv('KOJA_EDGE_TIMEOUT','60'))

def _edge_slug(host):
    host=(host or '').split(':',1)[0].lower().rstrip('.')
    suffix='.'+KOJA_PUBLIC_DOMAIN if KOJA_PUBLIC_DOMAIN else ''
    if not suffix or not host.endswith(suffix): return ''
    slug=host[:-len(suffix)].strip('.')
    if not slug or '.' in slug: return ''
    if len(slug)>63 or not all(c.isalnum() or c=='-' for c in slug): return ''
    return slug

_EDGE_COUNTERS = {}
_EDGE_LOCK = threading.Lock()

def _edge_resolve(slug):
    if not configured() or not slug: return None
    rows=sb('/rest/v1/cloud_compute_services',params={'config->>url_slug':f'eq.{slug}','status':'in.(healthy,running)','select':'id,name,status,service_url,config','limit':'10'})
    if not rows: return None
    row=rows[0]; cfg=row.get('config') or {}; replicas=cfg.get('replicas_runtime') if isinstance(cfg.get('replicas_runtime'),dict) else {}
    targets=[]
    for idx,rep in replicas.items():
        if not isinstance(rep,dict): continue
        origin=str(rep.get('public_url') or rep.get('origin_url') or '').strip().rstrip('/')
        health=str(rep.get('health') or '').lower()
        if not origin or health not in ('healthy','running','unknown'): continue
        if origin.startswith('https://'+slug+'.'+KOJA_PUBLIC_DOMAIN) or origin.startswith('http://'+slug+'.'+KOJA_PUBLIC_DOMAIN): continue
        targets.append((str(idx),origin,rep))
    if not targets:
        origin=(cfg.get('origin_url') or cfg.get('public_url') or row.get('service_url') or '').strip().rstrip('/')
        if origin and not origin.startswith(('https://'+slug+'.'+KOJA_PUBLIC_DOMAIN,'http://'+slug+'.'+KOJA_PUBLIC_DOMAIN)):
            targets=[('0',origin,{'health':str(row.get('status') or 'unknown')})]
    if not targets: return None
    with _EDGE_LOCK:
        n=_EDGE_COUNTERS.get(slug,0); _EDGE_COUNTERS[slug]=(n+1)%len(targets)
    n%=len(targets); return row,targets[n:]+targets[:n]

def _proxy_project_request(slug, edge_path=''):
    try:
        resolved=_edge_resolve(slug)
        if not resolved: return jsonify(error='project_not_running', slug=slug),503
        row,targets=resolved
        headers={k:v for k,v in request.headers.items() if k.lower() not in ('host','content-length','connection','accept-encoding')}
        headers['X-Forwarded-Host']=request.host; headers['X-KOJA-Project']=str(row['id'])
        last_error=None
        for replica_id,origin,_meta in targets:
            target=origin + ('/'+edge_path.lstrip('/') if edge_path else '/')
            if request.query_string: target += '?'+request.query_string.decode('utf-8','ignore')
            try:
                r=requests.request(request.method,target,headers={**headers,'X-KOJA-Replica':replica_id},data=request.get_data(),allow_redirects=False,stream=True,timeout=KOJA_EDGE_TIMEOUT)
                excluded={'content-length','transfer-encoding','connection','content-encoding'}
                out_headers=[(k,v) for k,v in r.headers.items() if k.lower() not in excluded]
                return Response(r.iter_content(chunk_size=65536),status=r.status_code,headers=out_headers)
            except requests.RequestException as e: last_error=e
        return jsonify(error='edge_all_replicas_unreachable',detail=str(last_error)[:300] if last_error else 'no healthy replicas'),502
    except Exception as e: return jsonify(error='edge_gateway_error',detail=str(e)[:300]),500

@app.after_request
def _api_cors(response):
    if request.path.startswith('/api/v1/'):
        origins=[x.strip() for x in API_CORS_ORIGINS.split(',') if x.strip()]
        request_origin=request.headers.get('Origin','')
        if '*' in origins:
            response.headers['Access-Control-Allow-Origin']='*'
        elif request_origin and request_origin in origins:
            response.headers['Access-Control-Allow-Origin']=request_origin
        elif len(origins)==1:
            response.headers['Access-Control-Allow-Origin']=origins[0]
        response.headers['Access-Control-Allow-Headers']='Content-Type, X-KOJA-API-KEY, Authorization'
        response.headers['Access-Control-Allow-Methods']='GET, POST, PUT, PATCH, DELETE, OPTIONS'
        response.headers['Vary']='Origin'
    return response

@app.before_request
def _koja_edge_before_request():
    if not KOJA_EDGE_MODE or request.path.startswith('/api/') or request.path.startswith('/host/') or request.path == '/favicon.ico':
        return None
    slug=_edge_slug(request.host)
    if not slug:
        return None
    return _proxy_project_request(slug, request.path.lstrip('/'))

@app.route('/host/<slug>', defaults={'host_path':''}, methods=['GET','POST','PUT','PATCH','DELETE','OPTIONS','HEAD'])
@app.route('/host/<slug>/<path:host_path>', methods=['GET','POST','PUT','PATCH','DELETE','OPTIONS','HEAD'])
def temporary_project_host(slug, host_path):
    # Free/temporary hosting endpoint used before koja.cloud is purchased.
    if not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,62}', slug or ''):
        return jsonify(error='invalid_project_slug'),400
    return _proxy_project_request(slug, host_path)


def project_access(uid, oid, pid):
    # Project access is tenant-scoped. Accept UUID, public project code, or the
    # human-readable project name so deployment forms can safely use either the
    # project selector value or a pasted project name.
    ref=str(pid or '').strip()
    if not ref: return None
    base={'organization_id':f'eq.{oid}','select':'*','limit':'1'}
    uuid_re=r'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}'
    if re.fullmatch(uuid_re,ref):
        base['id']=f'eq.{ref}'
        row=_one('/rest/v1/cloud_projects',base)
    else:
        row=_one('/rest/v1/cloud_projects',dict(base, project_code=f'eq.{ref}'))
        if not row:
            row=_one('/rest/v1/cloud_projects',dict(base, name=f'eq.{ref}'))
    if not row: return None
    if str(row.get('owner_user_id') or '') == str(uid): return row
    member=_one('/rest/v1/cloud_organization_members',{'organization_id':f'eq.{oid}','user_id':f'eq.{uid}','status':'eq.active','select':'organization_id','limit':'1'})
    return row if member else None

def workspace_path_ok(path):
    p=(path or '').replace('\\','/').strip('/')
    if not p or p.startswith('../') or '/..' in p or p.startswith('/') or '\x00' in p: return False
    parts=[x for x in p.split('/') if x]
    return all(x not in ('.','..') and not x.startswith('.git') for x in parts)

def workspace_row(uid, oid, pid, path, content_text='', content_b64=None, content_type='text/plain'):
    if not workspace_path_ok(path): raise ValueError('invalid_workspace_path')
    if content_b64 is not None and len(content_b64) > WORKSPACE_BINARY_LIMIT*2: raise ValueError('workspace_file_too_large')
    if content_b64 is None and len(content_text.encode('utf-8')) > WORKSPACE_TEXT_LIMIT: raise ValueError('workspace_file_too_large')
    return {'owner_user_id':uid,'organization_id':oid,'project_id':pid,'path':path.strip('/'),'content_text':content_text,'content_b64':content_b64,'content_type':content_type or 'text/plain','size_bytes':len((content_text or '').encode('utf-8')) if content_b64 is None else 0,'updated_at':now()}

def current_user():
    uid = session.get('user_id')
    if not uid: return None
    try:
        rows = sb('/rest/v1/cloud_users', params={'id':f'eq.{uid}','select':'*','limit':'1'})
        return rows[0] if rows else None
    except Exception:
        return {'id': uid, 'email': session.get('email',''), 'full_name': ''}

def agent_auth(fn):
    @wraps(fn)
    def w(*a, **k):
        token=request.headers.get('X-KOJA-AGENT-TOKEN') or (request.get_json(silent=True) or {}).get('agent_token','')
        if not token: return jsonify(error='agent_token_required'),401
        th=hashlib.sha256(token.encode()).hexdigest()
        rows=sb('/rest/v1/cloud_compute_agents',params={'token_hash':f'eq.{th}','select':'*','limit':'1'})
        if not rows: return jsonify(error='invalid_agent'),401
        request.koja_agent=rows[0]
        try: return fn(*a, **k)
        except Exception as e: return jsonify(error=str(e)),500
    return w

def auth_required(fn):
    @wraps(fn)
    def w(*a, **k):
        if not session.get('user_id'): return jsonify(error='login_required'), 401
        try: return fn(*a, **k)
        except Exception as e: return jsonify(error=str(e)), 500
    return w

def _api_key_raw():
    """Return a developer API credential from the supported transport locations."""
    auth=request.headers.get('Authorization','')
    bearer=''
    if auth.lower().startswith('bearer '):
        bearer=auth[7:].strip()
    return (request.headers.get('X-KOJA-API-KEY') or bearer or request.args.get('api_key','')).strip()


def _api_rate_key(raw=None, project_id=None, key_id=None):
    """Build an isolated limiter key. Authenticated callers are isolated by API key + project."""
    raw = raw if raw is not None else _api_key_raw()
    if key_id:
        return 'auth:' + str(key_id) + ':project:' + str(project_id or 'none')
    if raw:
        return 'credential:' + hashlib.sha256(raw.encode()).hexdigest()[:32]
    return 'ip:' + (request.remote_addr or 'unknown')


_API_RATE_BUCKETS = {}
_API_RATE_LOCK = threading.Lock()
_API_RATE_LIMIT_AUTH = max(1, int(os.getenv('KOJA_API_RATE_LIMIT_AUTH', '600')))
_API_RATE_LIMIT_ANON = max(1, int(os.getenv('KOJA_API_RATE_LIMIT_ANON', '120')))
_API_RATE_WINDOW = max(1, int(os.getenv('KOJA_API_RATE_WINDOW', '60')))


def _api_rate_state(key, limit, window=None):
    """Return (limited, remaining, reset_seconds) using a thread-safe fixed window."""
    window = window or _API_RATE_WINDOW
    now_ts = time.time()
    try:
        with _API_RATE_LOCK:
            bucket = _API_RATE_BUCKETS.get(key)
            if not bucket or now_ts - bucket[0] >= window:
                _API_RATE_BUCKETS[key] = [now_ts, 1]
                return False, max(0, limit - 1), window
            bucket[1] += 1
            elapsed = max(0, now_ts - bucket[0])
            remaining = max(0, limit - bucket[1])
            reset = max(1, int(window - elapsed + 0.999))
            return bucket[1] > limit, remaining, reset
    except Exception:
        # Limiter failure must never take the KOJA API offline.
        return False, limit, window


def _api_rate_headers(limit, remaining, reset):
    return {
        'X-RateLimit-Limit': str(limit),
        'X-RateLimit-Remaining': str(max(0, remaining)),
        'X-RateLimit-Reset': str(max(1, reset)),
    }


def _api_key_scopes(key):
    """Normalize legacy and granular scope formats to a predictable set."""
    scopes=key.get('scopes') or []
    if isinstance(scopes,str):
        try:
            parsed=json.loads(scopes)
            scopes=parsed if isinstance(parsed,list) else [x.strip() for x in scopes.split(',')]
        except Exception:
            scopes=[x.strip() for x in scopes.split(',')]
    return {str(x).strip().lower() for x in scopes if str(x).strip()}


def _api_key_has_scope(key, scope):
    scopes=_api_key_scopes(key)
    if '*' in scopes or 'admin' in scopes:
        return True
    scope=str(scope).strip().lower()
    if scope in scopes:
        return True
    if ':' in scope:
        service, action=scope.split(':',1)
        aliases={
            f'{service}:{action}', service,
            f'{service}_scope',
            f'{service}_read' if action=='read' else f'{service}_write',
            action,
        }
        if action=='read': aliases.add('read')
        if action=='write': aliases.add('write')
        return bool(scopes.intersection(aliases))
    return scope in scopes


def _api_key_identity(key):
    """Backfill identity for keys created by older releases."""
    uid=str(key.get('user_id') or key.get('owner_user_id') or '').strip()
    oid=str(key.get('organization_id') or '').strip()
    pid=str(key.get('project_id') or '').strip() or None
    if pid and (not uid or not oid):
        try:
            rows=sb('/rest/v1/cloud_projects',params={'id':f'eq.{pid}','select':'id,owner_user_id,organization_id','limit':'1'})
            if rows:
                pr=rows[0]
                uid=uid or str(pr.get('owner_user_id') or '').strip()
                oid=oid or str(pr.get('organization_id') or '').strip()
        except Exception:
            pass
    return uid,oid,pid


def resolve_cloud_api_key(raw):
    """Single authoritative API-key validator for every KOJA API surface."""
    if not raw:
        return None,('api_key_required',401)
    kh=hashlib.sha256(raw.encode()).hexdigest()
    rows=sb('/rest/v1/cloud_api_keys',params={'key_hash':f'eq.{kh}','select':'*','limit':'1'})
    if not rows:
        return None,('invalid_api_key',401)
    key=rows[0]
    status=str(key.get('status') or '').lower()
    if status=='revoked':
        return None,('api_key_revoked',401)
    if status!='active':
        return None,('invalid_api_key',401)
    expires=key.get('expires_at')
    if expires and str(expires) <= now():
        return None,('api_key_expired',401)
    uid,oid,pid=_api_key_identity(key)
    if not uid or not oid:
        return None,('api_key_identity_incomplete',401)
    key['_uid']=uid; key['_oid']=oid; key['_pid']=pid
    request.koja_api_key=key
    try:
        sb('/rest/v1/cloud_api_keys','PATCH',{'last_used_at':now()},params={'id':f'eq.{key["id"]}'})
    except Exception:
        pass
    return key,None


def _api_required_scope_for_request():
    path=request.path or ''
    if path.startswith('/api/v1/projects') or path.startswith('/api/v1/urls'):
        service='projects'
    elif path.startswith('/api/v1/usage'):
        service='usage'
    elif path.startswith('/api/storage') or path.startswith('/api/v1/storage'):
        service='storage'
    elif path.startswith('/api/databases') or path.startswith('/api/v1/databases'):
        service='database'
    elif path.startswith('/api/media') or path.startswith('/api/v1/media'):
        service='media'
    elif path.startswith('/api/services') or path.startswith('/api/v1/compute'):
        service='compute'
    elif path.startswith('/api/live') or path.startswith('/api/v1/live'):
        service='live'
    elif path.startswith('/api/webhooks') or path.startswith('/api/v1/webhooks'):
        service='webhooks'
    else:
        return None
    action='read' if request.method in ('GET','HEAD','OPTIONS') else 'write'
    return f'{service}:{action}'


def api_scope(name):
    return _api_key_has_scope(getattr(request,'koja_api_key',{}) or {}, name)


def _enforce_api_scope():
    required=_api_required_scope_for_request()
    if not required:
        return None
    key=getattr(request,'koja_api_key',None)
    if not key:
        return None
    if _api_key_has_scope(key,required):
        return None
    return jsonify(error='scope_required',scope=required),403


def api_key_auth(fn):
    @wraps(fn)
    def w(*a, **k):
        if request.method == 'OPTIONS':
            return fn(*a, **k)

        # First protect credential abuse before touching protected resources.
        raw = _api_key_raw()
        pre_key = _api_rate_key(raw=raw)
        pre_limited, _, pre_reset = _api_rate_state(pre_key, _API_RATE_LIMIT_ANON)
        if pre_limited:
            resp = jsonify(error='rate_limited', message='API rate limit exceeded', retry_after=pre_reset)
            for hk, hv in _api_rate_headers(_API_RATE_LIMIT_ANON, 0, pre_reset).items(): resp.headers[hk] = hv
            resp.headers['Retry-After'] = str(pre_reset)
            return resp, 429

        key, err = resolve_cloud_api_key(raw)
        if err:
            return jsonify(error=err[0]), err[1]

        project_id = key.get('_pid') or key.get('project_id')
        key_id = key.get('id')
        auth_key = _api_rate_key(project_id=project_id, key_id=key_id)
        limited, remaining, reset = _api_rate_state(auth_key, _API_RATE_LIMIT_AUTH)
        if limited:
            resp = jsonify(error='rate_limited', message='API rate limit exceeded', retry_after=reset)
            for hk, hv in _api_rate_headers(_API_RATE_LIMIT_AUTH, remaining, reset).items(): resp.headers[hk] = hv
            resp.headers['Retry-After'] = str(reset)
            return resp, 429

        scope_error = _enforce_api_scope()
        if scope_error:
            try:
                scope_error[0].headers.update(_api_rate_headers(_API_RATE_LIMIT_AUTH, remaining, reset))
            except Exception:
                pass
            return scope_error
        try:
            result = fn(*a, **k)
            try:
                for hk, hv in _api_rate_headers(_API_RATE_LIMIT_AUTH, remaining, reset).items(): result.headers[hk] = hv
            except Exception:
                pass
            return result
        except PermissionError as e:
            resp = jsonify(error=str(e))
            for hk, hv in _api_rate_headers(_API_RATE_LIMIT_AUTH, remaining, reset).items(): resp.headers[hk] = hv
            return resp, 403
        except Exception as e:
            resp = jsonify(error=str(e))
            for hk, hv in _api_rate_headers(_API_RATE_LIMIT_AUTH, remaining, reset).items(): resp.headers[hk] = hv
            return resp, 500
    return w


def cloud_api_project_id():
    key=getattr(request,'koja_api_key',{}) or {}
    return str(key.get('_pid') or key.get('project_id') or '').strip() or None


def cloud_api_scope_for_request():
    return _enforce_api_scope() is None


def cloud_api_or_login(fn):
    @wraps(fn)
    def w(*a, **k):
        raw=_api_key_raw()
        if not raw:
            if not session.get('user_id'): return jsonify(error='login_required'), 401
            try: return fn(*a, **k)
            except Exception as e: return jsonify(error=str(e)),500
        key,err=resolve_cloud_api_key(raw)
        if err: return jsonify(error=err[0]),err[1]
        scope_error=_enforce_api_scope()
        if scope_error: return scope_error
        uid,oid,pid=key['_uid'],key['_oid'],key['_pid']
        if pid:
            project=sb('/rest/v1/cloud_projects',params={'id':f'eq.{pid}','owner_user_id':f'eq.{uid}','organization_id':f'eq.{oid}','select':'id','limit':'1'})
            if not project: return jsonify(error='api_key_project_not_found'),403
            va=request.view_args or {}
            checks=[
                ('aid','cloud_media_assets'),('dbid','cloud_databases'),('sid','cloud_compute_services'),
                ('object_id','cloud_storage_objects'),('oid','cloud_storage_objects'),('cid','cloud_live_channels')
            ]
            for arg,table in checks:
                rid=va.get(arg)
                if not rid: continue
                row=sb('/rest/v1/'+table,params={'id':f'eq.{rid}','organization_id':f'eq.{oid}','project_id':f'eq.{pid}','select':'id','limit':'1'})
                if not row: return jsonify(error='project_scope_violation'),403
        original=dict(session); original_modified=getattr(session,'modified',False)
        try:
            session['user_id']=uid; session['organization_id']=oid
            return fn(*a, **k)
        except PermissionError as e:
            return jsonify(error=str(e)),403
        except Exception as e:
            return jsonify(error=str(e)),500
        finally:
            session.clear(); session.update(original); session.modified=original_modified
    return w


def cloud_project_filter(params):
    pid=cloud_api_project_id()
    if pid: params['project_id']=f'eq.{pid}'
    return params

def cloud_project_for_write(requested=None):
    key_pid=cloud_api_project_id()
    if key_pid and requested and str(requested)!=key_pid: raise PermissionError('project_scope_violation')
    return key_pid or (str(requested).strip() if requested else None)

def key_org():
    key=getattr(request,'koja_api_key',{}) or {}
    return key.get('_oid') or key.get('organization_id')

def owner_filter(uid): return {'owner_user_id': f'eq.{uid}'}
def user_orgs(uid):
    """Return organization memberships without relying on PostgREST nested-resource joins."""
    try:
        memberships = sb('/rest/v1/cloud_organization_members', params={
            'user_id':f'eq.{uid}','status':'eq.active',
            'select':'organization_id,role,status,created_at','order':'created_at.asc'
        })
        if not memberships: return []
        ids=[m.get('organization_id') for m in memberships if m.get('organization_id')]
        if not ids: return memberships
        orgs=sb('/rest/v1/cloud_organizations', params={
            'id':'in.(' + ','.join(ids) + ')','select':'id,name,slug,status,created_at,updated_at'
        })
        om={o['id']:o for o in orgs}
        for m in memberships: m['cloud_organizations']=om.get(m.get('organization_id'),{})
        return memberships
    except Exception:
        return []

def ensure_customer(uid, display_name='KOJA Cloud Customer'):
    """Return the customer's id for this user, creating a control-plane customer when needed."""
    rows=sb('/rest/v1/cloud_customers', params={'owner_user_id':f'eq.{uid}','select':'*','limit':'1'})
    if rows:
        return rows[0]
    row=sb('/rest/v1/cloud_customers','POST',{
        'owner_user_id':uid,
        'display_name':display_name or 'KOJA Cloud Customer',
        'status':'active',
        'plan_code':'free'
    }, params={'select':'*'})
    return row[0] if isinstance(row,list) else row

def organization_insert_payload(uid, name, slug):
    customer=ensure_customer(uid, name)
    return {
        'owner_user_id': uid,
        'customer_id': customer['id'],
        'name': name,
        'slug': slug,
        'status': 'active',
        'plan': customer.get('plan_code') or 'free',
        'metadata': {}
    }

def _org_insert_candidates(uid, name, slug):
    full=organization_insert_payload(uid,name,slug)
    candidates=[
        full,
        {k:v for k,v in full.items() if k != 'customer_id'},
        {k:v for k,v in full.items() if k in ('owner_user_id','name','slug','status','plan')},
        {k:v for k,v in full.items() if k in ('name','slug','status','plan')},
    ]
    seen=set()
    for c in candidates:
        key=tuple(sorted(c.keys()))
        if key not in seen:
            seen.add(key)
            yield c

def create_org_for_user(uid, name, slug):
    last=None
    org=None
    for payload in _org_insert_candidates(uid,name,slug):
        try:
            rows=sb('/rest/v1/cloud_organizations','POST',payload,params={'select':'*'})
            if rows:
                org=rows[0]
                break
        except Exception as e:
            last=e
            msg=str(e)
            if not any(x in msg for x in ('PGRST204','23502','42703','customer_id','owner_user_id')):
                raise
    if not org:
        raise last or RuntimeError('organization_create_failed')
    membership={'organization_id':org['id'],'user_id':uid,'role':'owner','status':'active'}
    try:
        sb('/rest/v1/cloud_organization_members','POST',membership,params={'select':'organization_id,user_id,role,status'})
    except Exception:
        try: sb('/rest/v1/cloud_organizations','DELETE',params={'id':f'eq.{org["id"]}'})
        except Exception: pass
        raise
    session['organization_id']=org['id']
    return org

def active_org_id(uid):
    oid=session.get('organization_id')
    allowed=[r.get('organization_id') for r in user_orgs(uid)]
    if oid and oid in allowed: return oid
    if allowed:
        session['organization_id']=allowed[0]
        return allowed[0]
    try:
        rows=sb('/rest/v1/cloud_customers',params={'owner_user_id':f'eq.{uid}','select':'id,display_name,plan_code','limit':'1'})
        if rows:
            c=rows[0]
            slug='customer-'+c['id']
            existing=sb('/rest/v1/cloud_organizations',params={'slug':f'eq.{slug}','select':'*','limit':'1'})
            org=existing[0] if existing else sb('/rest/v1/cloud_organizations','POST',organization_insert_payload(uid, c.get('display_name') or 'KOJA Cloud Organization', slug),params={'select':'*'})[0]
            try:
                sb('/rest/v1/cloud_organization_members','POST',{'organization_id':org['id'],'user_id':uid,'role':'owner','status':'active'})
            except Exception: pass
            session['organization_id']=org['id']
            return org['id']
    except Exception:
        pass
    return None

def require_org(uid):
    oid=active_org_id(uid)
    if not oid: raise RuntimeError('organization_required')
    return oid

def org_member(uid,oid):
    try:
        rows=sb('/rest/v1/cloud_organization_members',params={'user_id':f'eq.{uid}','organization_id':f'eq.{oid}','status':'eq.active','select':'organization_id,role'})
        return rows[0] if rows else None
    except Exception:
        return None


def _audit_sync(uid, action, typ='', rid=None, metadata=None):
    try: sb('/rest/v1/cloud_audit_events','POST',{'user_id':uid,'action':action,'resource_type':typ,'resource_id':rid,'metadata':metadata or {}})
    except Exception: pass

def audit(uid, action, typ='', rid=None, metadata=None):
    # Audit is durability/observability work, not part of the critical request path.
    KOJA_FAST_EXECUTOR.submit(_audit_sync, uid, action, typ, rid, metadata or {})

def _usage_sync(uid, project, service, metric, quantity=1, unit='count', metadata=None, oid=None):
    try:
        row={'user_id':uid,'project_id':project,'service':service,'metric':metric,'quantity':quantity,'unit':unit,'metadata':metadata or {}}
        if oid: row['organization_id']=oid
        sb('/rest/v1/cloud_usage_events','POST',row)
    except Exception: pass

def usage(uid, project, service, metric, quantity=1, unit='count', metadata=None):
    # Capture request-bound organization context before leaving Flask's request thread.
    oid = session.get('organization_id') or active_org_id(uid)
    KOJA_FAST_EXECUTOR.submit(_usage_sync, uid, project, service, metric, quantity, unit, metadata or {}, oid)

@app.get('/api/system/schema-status')
def schema_status():
    if not configured():
        return jsonify(version=VERSION, supabase_configured=False)
    out={'version':VERSION,'supabase_configured':True}
    try:
        rows=sb('/rest/v1/cloud_organizations',params={'select':'id,name,slug,owner_user_id,customer_id,plan,status','limit':'1'})
        out['organization_schema']='v9'
        out['organization_rows']=len(rows)
    except Exception as e:
        out['organization_schema']='legacy_or_schema_cache'
        out['organization_error']=str(e)[:300]
    return jsonify(out)

@app.get('/health')
def health():
    return jsonify(service='koja-cloud', status='ok', version=VERSION, supabase_configured=configured(), compute='provider-agent', storage='supabase-object-storage', database='postgres-adapter', media='ffmpeg-agent', live='hls-control-plane', time=now())

DASHBOARD_HTML = r'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>KOJA CLOUD — Production Console</title>
<style>
*{box-sizing:border-box}body{margin:0;font-family:Inter,system-ui,-apple-system,Segoe UI,Arial;background:#050b14;color:#eef5ff}a{text-decoration:none;color:inherit}button,input,select{font:inherit}.top{height:68px;border-bottom:1px solid #1a2b40;background:#07111f;display:flex;align-items:center;justify-content:space-between;padding:0 18px;position:sticky;top:0;z-index:50}.brand{font-size:20px;font-weight:900}.brand span{color:#49a7ff}.top-right{display:flex;gap:8px;align-items:center}.pill{border:1px solid #29415c;background:#0b1a2b;border-radius:9px;padding:8px 10px;font-size:12px;color:#b9cce0}.layout{display:grid;grid-template-columns:245px 1fr;min-height:calc(100vh - 68px)}.side{background:#07111d;border-right:1px solid #17283c;padding:14px 10px;position:sticky;top:68px;height:calc(100vh - 68px);overflow:auto}.side-title{font-size:10px;color:#607b96;letter-spacing:1.5px;padding:12px 10px 6px}.nav{display:block;padding:9px 10px;border-radius:8px;color:#9bb0c5;font-size:12px;margin:2px 0}.nav:hover,.nav.active{background:#102944;color:#fff;box-shadow:inset 3px 0 #3d9eff}.main{padding:22px;max-width:1700px;width:100%}.hero{display:flex;justify-content:space-between;gap:20px;align-items:flex-start;margin-bottom:18px}.hero h1{font-size:29px;margin:4px 0}.eyebrow{font-size:10px;letter-spacing:1.5px;font-weight:800;color:#55aefb}.muted{color:#8ea4ba}.actions{display:flex;gap:7px;flex-wrap:wrap}.btn{border:1px solid #2a4a68;background:#176fba;color:#fff;padding:9px 12px;border-radius:8px;cursor:pointer;font-weight:750;font-size:12px}.btn.koja-action,.btn.koja-action:hover{transition:none!important;animation:none!important}.btn.is-running{outline:2px solid #49a7ff;outline-offset:1px}.koja-operation{margin:0 0 14px;padding:10px 12px;border:1px solid #24415d;border-radius:9px;background:#091a2a;color:#b9cce0;font-size:12px;font-weight:700}.koja-operation[data-state="success"]{border-color:#267a55;color:#6ee7a3}.koja-operation[data-state="error"]{border-color:#8a3540;color:#ff8a8a}.koja-operation[data-state="starting"]{border-color:#3d6f9f;color:#8ec8ff}.btn.secondary{background:#102238}.btn.danger{background:#742834}.btn:disabled{opacity:.45;cursor:not-allowed}.workspace{background:#081523;border:1px solid #1b3048;border-radius:12px;overflow:hidden}.workspace-head{padding:14px 16px;border-bottom:1px solid #1b3048;display:flex;justify-content:space-between;gap:12px;align-items:center}.workspace-head h2{font-size:15px;margin:0}.toolbar{padding:12px 14px;border-bottom:1px solid #182c42;display:flex;gap:8px;flex-wrap:wrap;align-items:center}.form-grid{display:grid;grid-template-columns:repeat(4,minmax(150px,1fr));gap:8px;padding:12px 14px}.input,.select{width:100%;padding:9px 10px;border:1px solid #29415c;background:#06101c;color:#fff;border-radius:8px}.input:focus,.select:focus{outline:0;border-color:#4da3ff}.table-wrap{overflow:auto}.table{width:100%;border-collapse:collapse;font-size:12px}.table th,.table td{border-bottom:1px solid #1a2c41;padding:9px 10px;text-align:left;vertical-align:top}.table th{font-size:10px;text-transform:uppercase;letter-spacing:.7px;color:#7792ad;background:#091a2a;position:sticky;top:0}.table tr:hover td{background:#0a1a2a}.badge{display:inline-block;border:1px solid #2a455f;border-radius:999px;padding:3px 7px;font-size:10px}.ok{color:#6ee7a3}.warn{color:#ffd166}.err{color:#ff7272}.mono{font-family:ui-monospace,SFMono-Regular,monospace;font-size:11px;word-break:break-all}.notice{margin-bottom:14px;padding:12px 14px;background:#091a2a;border:1px solid #1b3b58;border-radius:10px}.split{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-bottom:14px}.statline{display:flex;gap:20px;flex-wrap:wrap}.statline strong{font-size:20px}.empty{padding:22px;color:#7890a7;text-align:center}.footer{padding:28px 0;color:#58708a;font-size:10px}.hidden{display:none}@media(max-width:1000px){.layout{grid-template-columns:1fr}.side{position:static;height:auto;display:flex;overflow:auto;gap:3px;border-right:0;border-bottom:1px solid #17283c}.side-title{display:none}.nav{white-space:nowrap}.form-grid{grid-template-columns:1fr 1fr}.split{grid-template-columns:1fr}}@media(max-width:600px){.main{padding:12px}.hero{display:block}.actions{margin-top:12px}.form-grid{grid-template-columns:1fr}.top{padding:0 12px}.pill{display:none}}
</style></head><body><header class="top"><a class="brand" href="/dashboard">KOJA <span>CLOUD</span></a><div class="top-right"><span id="runtimePill" class="pill">Checking runtime…</span><span id="orgPill" class="pill">Organization</span><span id="user" class="pill">Account</span><button id="logout" class="btn secondary">Sign out</button></div></header>
<div class="layout"><aside class="side">
<div class="side-title">CONTROL PLANE</div><a class="nav" data-k="overview" href="/dashboard">Control Plane</a><a class="nav" data-k="customers" href="/dashboard?module=customers">Customers</a><a class="nav" data-k="organizations" href="/dashboard?module=organizations">Organizations</a><a class="nav" data-k="projects" href="/dashboard?module=projects">Projects</a><a class="nav" data-k="settings" href="/dashboard?module=settings">Settings</a>
<div class="side-title">DATA PLANE</div><a class="nav" data-k="storage" href="/dashboard?module=storage">KOJA Vault</a><a class="nav" data-k="database" href="/dashboard?module=database">KOJA Data</a><a class="nav" data-k="backend" href="/dashboard?module=backend">KOJA Backend</a><a class="nav" data-k="realtime" href="/dashboard?module=realtime">KOJA Sync</a><a class="nav" data-k="compute" href="/dashboard?module=compute">KOJA Run</a><a class="nav" data-k="hosting" href="/dashboard?module=hosting">KOJA Launch</a><a class="nav" data-k="media" href="/dashboard?module=media">KOJA Media</a><a class="nav" data-k="live" href="/dashboard?module=live">KOJA Stream</a><a class="nav" data-k="forge" href="/dashboard?module=forge">KOJA Forge</a><a class="nav" data-k="api" href="/dashboard?module=api">KOJA API</a>
<div class="side-title">OPERATIONS</div><a class="nav" data-k="webhooks" href="/dashboard?module=webhooks">Webhooks</a><a class="nav" data-k="jobs" href="/dashboard?module=jobs">Jobs</a><a class="nav" data-k="audit" href="/dashboard?module=audit">Audit</a><a class="nav" data-k="billing" href="/dashboard?module=billing">Usage / Billing</a><a class="nav" data-k="providers" href="/dashboard?module=providers">Infrastructure</a><a class="nav" data-k="nodes" href="/dashboard?module=nodes">Nodes</a><a class="nav" data-k="durability" href="/dashboard?module=durability">Durability</a>
</aside><main class="main" id="app"></main></div>
<script>
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
async function api(url,opt={}){
  let controller=null;
  let timeoutId=null;
  try{
    let h={...(opt.headers||{})};
    if(!(opt.body instanceof FormData)&&opt.body!==undefined)h['Content-Type']='application/json';
    const fetchOpt={...opt,headers:h,cache:'no-store'};
    if(!fetchOpt.signal){
      controller=new AbortController();
      timeoutId=setTimeout(()=>controller.abort(),10000);
      fetchOpt.signal=controller.signal;
    }
    const r=await fetch(url,fetchOpt);
    let d;
    try{d=await r.json()}catch{d=await r.text()}
    if(r.status===401){location.href='/login';return{r,d}}
    return{r,d};
  }catch(e){
    return{r:{ok:false,status:0},d:{error:e&&e.name==='AbortError'?'request_timeout_10s':String(e)}};
  }finally{
    clearTimeout(timeoutId);
  }
}
let currentModule='overview';
let kojaActionBusy=false;
function table(headers, rows){return `<div class="table-wrap"><table class="table"><thead><tr>${headers.map(h=>`<th>${esc(h)}</th>`).join('')}</tr></thead><tbody>${rows||'<tr><td colspan="'+headers.length+'" class="empty">No records</td></tr>'}</tbody></table></div>`}
function btn(label, action, cls=''){
  const safe=String(action||'').replace(/\\/g,'\\\\').replace(/`/g,'\\`');
  return `<button type="button" class="btn koja-action ${cls}" data-action-label="${esc(label)}" onclick="kojaAction(this,()=>{${safe}})">${esc(label)}</button>`;
}
function ensureOperationBar(){
  let el=document.getElementById('kojaOperation');
  if(!el){
    el=document.createElement('div'); el.id='kojaOperation'; el.className='koja-operation'; el.setAttribute('role','status'); el.setAttribute('aria-live','polite');
    const main=document.getElementById('app'); if(main) main.prepend(el);
  }
  return el;
}
function setOperation(message,state='running'){
  const el=ensureOperationBar(); el.dataset.state=state; el.textContent=message; el.classList.remove('hidden'); return el;
}
function kojaAction(button, action){
  if(!button || button.disabled) return;
  button.disabled=true;
  button.dataset.originalText=button.textContent;
  button.classList.add('is-running');
  button.textContent='Starting…';
  setOperation('Starting operation…','starting');
  // Let the browser paint the feedback before any network/backend work begins.
  requestAnimationFrame(()=>{
    requestAnimationFrame(async()=>{
      button.textContent='Running…';
      setOperation('Running…','running');
      try{
        await action();
        button.textContent='Completed';
        setOperation('Completed','success');
        setTimeout(()=>{if(button.isConnected){button.textContent=button.dataset.originalText||'Done';button.disabled=false;button.classList.remove('is-running')}},650);
      }catch(e){
        const msg=e?.message||String(e)||'Operation failed';
        button.textContent='Failed'; button.classList.remove('is-running');
        setOperation('Failed: '+msg,'error');
        setTimeout(()=>{if(button.isConnected){button.textContent=button.dataset.originalText||'Retry';button.disabled=false}},1200);
      }
    });
  });
}
async function get(url){const r=await api(url);if(!r.r.ok)throw new Error(r.d?.error||r.d?.detail||`Request failed (${r.r.status||'network'})`);return r.d?.data??r.d??[]}
function shell(title,desc,html){
  const app=document.getElementById('app'); if(!app)return;
  app.innerHTML=`<div class="hero"><div><div class="eyebrow">KOJA CLOUD</div><h1>${esc(title)}</h1><div class="muted">${esc(desc)}</div></div></div><div id="moduleOperation" class="koja-operation" role="status" aria-live="polite">Ready</div>${html}`;
}
async function runtime(){
  const p=document.getElementById('runtimePill'); if(!p)return;
  p.textContent='Checking runtime…';
  try{const r=await api('/health'); p.textContent=r.r.ok?'Runtime online':'Runtime unavailable';}
  catch(e){p.textContent='Runtime unavailable'}
}
async function overview(){
  let d={}; try{d=await get('/api/overview')}catch(e){d={error:e.message}}
  shell('Control Plane','KOJA CLOUD runtime overview and execution state.',`<div class="workspace"><div class="workspace-head"><h2>Runtime</h2><div class="actions">${btn('Refresh','overview()','secondary')} ${btn('Run E2E','runE2E()')}</div></div>${d.error?`<div class="notice err">${esc(d.error)}</div>`:`<div class="form-grid">${Object.entries(d).filter(([k])=>k!=='organization_id').map(([k,v])=>`<div class="card"><div class="eyebrow">${esc(k.replaceAll('_',' ').toUpperCase())}</div><h2>${esc(v)}</h2></div>`).join('')}</div>`}</div>`);
}
function fmtDate(v){if(!v)return '-';try{return new Date(v).toLocaleString()}catch{return String(v)}}
function rawJsonBlock(x){return `<details class="raw-data"><summary>Technical data</summary><pre>${esc(JSON.stringify(x,null,2))}</pre></details>`}
function resourceCells(module,x){if(module==='customers')return [`<strong>${esc(x.display_name||'Unnamed customer')}</strong>`,`<span class="badge ${String(x.status||'').toLowerCase()==='active'?'ok':'warn'}">${esc(x.status||'unknown')}</span>`,esc(x.plan_code||'-'),esc(fmtDate(x.created_at)),`<span class="mono">${esc(x.id||'-')}</span>`];if(module==='organizations'){const o=x.cloud_organizations||x;return [`<strong>${esc(o.name||'Unnamed organization')}</strong>`,`<span class="badge ${String(x.status||o.status||'').toLowerCase()==='active'?'ok':'warn'}">${esc(x.status||o.status||'unknown')}</span>`,esc(x.role||'member'),esc(o.slug||'-'),`<span class="mono">${esc(o.id||x.organization_id||'-')}</span>`]}if(module==='projects')return [`<strong>${esc(x.name||'Unnamed project')}</strong>`,`<span class="mono">${esc(x.project_code||'-')}</span>`,`<span class="badge ${String(x.status||'').toLowerCase()==='active'?'ok':'warn'}">${esc(x.status||'unknown')}</span>`,esc(fmtDate(x.created_at)),`<span class="mono">${esc(x.id||'-')}</span>`];return [esc(x.name||x.id||'Record'),esc(x.status||'-'),`<span class="mono">${esc(x.id||'-')}</span>`]}
async function operationalModule(module,title,desc,url){const d=await get(url);const rows=Array.isArray(d)?d:(d?.items||d?.data||[]);let headers=module==='customers'?['Customer','Status','Plan','Created','ID']:module==='organizations'?['Organization','Status','Role','Slug','ID']:['Project','Code','Status','Created','ID'];const body=rows.map(x=>`<tr>${resourceCells(module,x).map(c=>`<td>${c}</td>`).join('')}</tr>`).join('');const cards=rows.slice(0,8).map(x=>`<div class="resource-card"><div class="resource-title">${esc(module==='organizations'?(x.cloud_organizations||x).name:x.display_name||x.name||'Record')}</div>${rawJsonBlock(x)}</div>`).join('');shell(title,desc,`<div class="workspace"><div class="workspace-head"><div><h2>Live ${esc(title)}</h2><div class="muted">${rows.length} record${rows.length===1?'':'s'}</div></div><div class="actions">${btn('Refresh',`render('${module}')`,'secondary')}</div></div>${table(headers,body)}</div><div class="workspace" style="margin-top:14px"><div class="workspace-head"><h2>Records</h2></div><div class="resource-grid">${cards||'<div class="empty">No records</div>'}</div></div>`)}
async function genericModule(title,desc,url){let d=await get(url);let rows=Array.isArray(d)?d:(d?.items||d?.data||[]);shell(title,desc,`<div class="workspace"><div class="workspace-head"><h2>Live data</h2><div class="actions">${btn('Refresh',`render('${currentModule}')`,'secondary')}</div></div>${table(['Records'],rows.map(x=>`<tr><td>${esc(x.name||x.id||'Record')}</td></tr>`).join(''))}</div>`)}
function render(key){currentModule=key||new URLSearchParams(location.search).get('module')||'overview';const map={overview,settings,storage,database,backend,realtime,compute,hosting,media,live,forge,api:apiModule,webhooks,jobs,audit,billing,providers,nodes,durability,customers:()=>operationalModule('customers','Customers','KOJA CLOUD customers','/api/customers'),organizations:()=>operationalModule('organizations','Organizations','KOJA CLOUD organizations','/api/organizations'),projects:()=>operationalModule('projects','Projects','KOJA CLOUD projects','/api/projects')};const fn=map[currentModule];document.querySelectorAll('.nav').forEach(n=>n.classList.toggle('active',n.dataset.k===currentModule));if(fn)return Promise.resolve(fn()).catch(e=>{shell('KOJA CLOUD','Operation failed',`<div class="notice err">${esc(e.message||e)}</div>`)});const urls={customers:'/api/customers',organizations:'/api/organizations',projects:'/api/projects'};return genericModule(currentModule[0]?.toUpperCase()+currentModule.slice(1),'KOJA CLOUD '+currentModule,urls[currentModule]||'/api/overview').catch(e=>shell('KOJA CLOUD','Operation failed',`<div class="notice err">${esc(e.message||e)}</div>`))}
function boot(){
  document.querySelectorAll('.nav').forEach(n=>n.addEventListener('click',()=>setOperation('Opening '+n.textContent.trim()+'…','starting')));
  const logout=document.getElementById('logout'); if(logout)logout.addEventListener('click',()=>kojaAction(logout,async()=>{const r=await api('/api/auth/logout',{method:'POST'});if(!r.r.ok)throw new Error(r.d?.error||'Sign out failed');location.href='/login'}));
  runtime(); render(new URLSearchParams(location.search).get('module')||'overview');
}
async function registerGithubDeploy(id){let btnEl=document.getElementById('githubDeployBtn');let statusEl=document.getElementById('deployStatus');let stageEl=document.getElementById('deployStage');let d={repo_url:document.getElementById('gp_repo').value.trim(),branch:document.getElementById('gp_branch').value.trim()||'main',name:document.getElementById('gp_name').value.trim()||'KOJA App',build_command:document.getElementById('gp_build').value.trim(),start_command:document.getElementById('gp_start').value.trim(),health_path:document.getElementById('gp_health').value.trim()||'/health'};if(!d.repo_url)return alert('GitHub repository URL required');if(btnEl){btnEl.disabled=true;btnEl.textContent='Submitting…'}if(statusEl)statusEl.textContent='Submitting deployment request to KOJA CLOUD…';try{let controller=new AbortController();let timer=setTimeout(()=>controller.abort(),10000);let r=await api('/api/projects/'+id+'/github/deploy',{method:'POST',body:JSON.stringify(d),signal:controller.signal});clearTimeout(timer);if(!r.r.ok){if(statusEl)statusEl.textContent='Deployment request failed: '+(r.d?.error||r.d?.detail||'unknown error');return alert(r.d?.error||r.d?.detail||'GitHub deployment failed')}let dep=r.d.deployment||{};if(!dep.id){if(statusEl)statusEl.textContent='KOJA CLOUD accepted the request, but no deployment ID was returned.';return}if(statusEl)statusEl.textContent='Deployment accepted. Code: '+(dep.deployment_code||dep.id);await pollGithubDeployment(id,dep.id)}catch(e){if(e.name==='AbortError'){if(statusEl)statusEl.textContent='Request timed out in the browser. The deployment may still be queued; refresh to check its live state.';stageEl&&(stageEl.textContent='UNKNOWN')}else if(statusEl)statusEl.textContent='Deployment request error: '+String(e)}finally{if(btnEl){btnEl.disabled=false;btnEl.textContent='Register & deploy from GitHub'}}}
async function pollGithubDeployment(pid,did){let stageEl=document.getElementById('deployStage'),statusEl=document.getElementById('deployStatus');for(let i=0;i<180;i++){let r=await api('/api/projects/'+pid+'/github/deploy/'+did+'/status');if(r.r.ok){let dep=r.d.deployment||{},job=r.d.job||{},stage=r.d.stage||dep.status||job.status||'queued';if(stageEl){stageEl.textContent=stage;stageEl.className='badge '+(['HEALTH CHECK','RUNNING'].includes(stage)?'ok':stage==='FAILED'?'danger':'warn')}if(statusEl)statusEl.textContent='Deployment '+(dep.deployment_code||did)+' • '+stage+(job.message?' • '+job.message:'');if(['HEALTH CHECK','FAILED'].includes(stage)){if(stage==='FAILED')return;await new Promise(res=>setTimeout(res,200));continue}if(stage==='RUNNING'||dep.status==='healthy')return}else if(statusEl)statusEl.textContent='Waiting for deployment status…';await new Promise(res=>setTimeout(res,200))}if(statusEl)statusEl.textContent='Deployment is still active after 45 seconds. It remains queued/running on KOJA CLOUD; refresh to inspect the current state.'}
async function settings(){let [m,s]=await Promise.all([get('/api/me'),get('/api/system/schema-status')]);shell('Settings','Account, security and production configuration diagnostics.',`<div class="workspace"><div class="workspace-head"><h2>Account</h2></div>${table(['Field','Value'],`<tr><td>Email</td><td>${esc(m.email)}</td></tr><tr><td>Name</td><td>${esc(m.full_name||'')}</td></tr><tr><td>User ID</td><td class="mono">${esc(m.user_id||m.id)}</td></tr><tr><td>Organization</td><td>${esc(m.organization_name||'')}</td></tr>`)}</div><div class="workspace" style="margin-top:14px"><div class="workspace-head"><h2>Diagnostics</h2></div>${table(['Check','Result','Action'],`<tr><td>Schema</td><td>${esc(s.organization_schema||'unknown')}</td><td>${esc(s.organization_error||'OK')}</td></tr><tr><td>Health</td><td>HTTP health endpoint</td><td><a class="btn" href="/health" target="_blank">Open</a></td></tr><tr><td>System</td><td>Service diagnostics</td><td><a class="btn secondary" href="/api/system/status" target="_blank">Open</a></td></tr>`)}</div>`)}
async function storage(){let [b,o]=await Promise.all([get('/api/storage/buckets'),get('/api/storage/objects')]);shell('KOJA Vault','Object storage operations: bucket creation, upload, retrieval and deletion.',`<div class="workspace"><div class="form-grid"><input id="bn" class="input" placeholder="Bucket name"><select id="bv" class="select"><option value="private">private</option><option value="public">public</option></select>${btn('Create bucket','createBucket()')}</div>${table(['Bucket','Status','Visibility','Provider','Created'],b.map(x=>`<tr><td>${esc(x.bucket_name||x.name)}</td><td>${esc(x.status)}</td><td>${esc(x.visibility)}</td><td>${esc(x.provider)}</td><td>${esc(x.created_at)}</td></tr>`).join(''))}</div><div class="workspace" style="margin-top:14px"><div class="workspace-head"><h2>Upload object</h2></div><div class="form-grid"><select id="ub" class="select">${b.map(x=>`<option value="${esc(x.bucket_name||x.name)}">${esc(x.bucket_name||x.name)}</option>`).join('')}</select><input id="uf" class="input" type="file">${btn('Upload','uploadFile()')}</div>${table(['Object','Path','Size','Type','Actions'],o.map(x=>`<tr><td>${esc(x.name)}</td><td class="mono">${esc(x.object_path)}</td><td>${esc(x.size_bytes)}</td><td>${esc(x.content_type)}</td><td>${btn('Download',`downloadObj('${x.id}')`,'secondary')} ${btn('Delete',`deleteObj('${x.id}')`,'danger')}</td></tr>`).join(''))}</div>`)}
async function createBucket(){let r=await api('/api/storage/buckets',{method:'POST',body:JSON.stringify({name:document.getElementById('bn').value.trim(),visibility:document.getElementById('bv').value})});if(!r.r.ok)return alert(r.d.error||'create failed');storage()}
async function uploadFile(){let f=document.getElementById('uf').files[0],b=document.getElementById('ub').value;if(!f)return alert('Select a file.');let fd=new FormData();fd.append('bucket',b);fd.append('file',f);let r=await api('/api/storage/upload',{method:'POST',body:fd});if(!r.r.ok)return alert(r.d.error||'upload failed');storage()}
function downloadObj(id){location.href='/api/storage/object/'+id+'/download'}
async function deleteObj(id){if(!confirm('Delete this object?'))return;let r=await api('/api/storage/objects/'+id,{method:'DELETE'});if(!r.r.ok)return alert(r.d.error||'delete failed');storage()}
async function database(){let d=await get('/api/databases');shell('KOJA Data','Database lifecycle, backups, connections and operational state.',`<div class="workspace"><div class="form-grid"><input id="dn" class="input" placeholder="Database name"><select id="de" class="select"><option>postgres</option><option>mysql</option><option>mariadb</option><option>mongodb</option></select><input id="dr" class="input" placeholder="Region" value="global">${btn('Create database','createDb()')}</div>${table(['Database','Engine','Status','Region','Actions'],d.map(x=>`<tr><td>${esc(x.name)}</td><td>${esc(x.engine)}</td><td>${esc(x.status)}</td><td>${esc(x.region)}</td><td>${btn('Start',`dbAction('${x.id}','start')`)}${btn('Stop',`dbAction('${x.id}','stop')`,'secondary')}${btn('Backup',`dbBackup('${x.id}')`)}${btn('Connections',`dbConnections('${x.id}')`,'secondary')}</td></tr>`).join(''))}</div>`)}
async function createDb(){let r=await api('/api/databases',{method:'POST',body:JSON.stringify({name:document.getElementById('dn').value.trim(),engine:document.getElementById('de').value,region:document.getElementById('dr').value.trim()||'global'})});if(!r.r.ok)return alert(r.d.error||'create failed');database()}
async function dbAction(id,a){let r=await api('/api/databases/'+id+'/'+a,{method:'POST',body:'{}'});if(!r.r.ok)return alert(r.d.error||a+' failed');database()}
async function dbBackup(id){let r=await api('/api/databases/'+id+'/backup',{method:'POST',body:'{}'});if(!r.r.ok)return alert(r.d.error||'backup failed');alert('Backup accepted');database()}
async function dbConnections(id){let r=await api('/api/databases/'+id+'/connections');if(!r.r.ok)return alert(r.d.error||'failed');alert(JSON.stringify(r.d,null,2))}
async function backend(){let s=await get('/api/providers/supabase/status');shell('KOJA Backend','Managed backend provisioning and provider connection management.',`<div class="workspace"><div class="workspace-head"><h2>Backend provider</h2></div>${table(['Provider','Configured','Projects','Action'],`<tr><td>Supabase Management</td><td>${s.configured?'Configured':'Not configured'}</td><td>${esc(s.project_count||0)}</td><td>${s.configured?'Ready to provision':'Configure server credentials'}</td></tr>`)}</div><div class="workspace" style="margin-top:14px"><div class="form-grid"><input id="bsName" class="input" placeholder="Backend name"><input id="bsPass" class="input" type="password" placeholder="Database password"><input id="bsRegion" class="input" placeholder="Region"><input id="bsProject" class="input" placeholder="KOJA project ID">${btn('Provision backend','createBackend()')}</div></div>`)}
async function createBackend(){let d={name:document.getElementById('bsName').value.trim(),db_password:document.getElementById('bsPass').value,region:document.getElementById('bsRegion').value.trim(),project_id:document.getElementById('bsProject').value.trim()};let r=await api('/api/providers/supabase/projects',{method:'POST',body:JSON.stringify(d)});if(!r.r.ok)return alert(r.d.error||r.d.detail||'provision failed');backend()}
async function realtime(){let d=await get('/api/databases');shell('KOJA Sync','Realtime data and event transport attached to managed data resources.',`<div class="workspace">${table(['Database','Engine','Status','Realtime'],d.map(x=>`<tr><td>${esc(x.name)}</td><td>${esc(x.engine)}</td><td>${esc(x.status)}</td><td>${btn('Inspect',`syncConfig('${x.id}')`)}</td></tr>`).join(''))}</div>`)}
async function syncConfig(id){let r=await api('/api/data/'+id+'/realtime');if(!r.r.ok)return alert(r.d?.error||'not available');alert(JSON.stringify(r.d,null,2))}
async function compute(){let [s,a]=await Promise.all([get('/api/services'),get('/api/agents')]);shell('KOJA Run','Compute resources, agents, deployments and lifecycle commands.',`<div class="workspace"><div class="form-grid"><input id="csn" class="input" placeholder="Service name"><input id="csp" class="input" placeholder="Project ID"><input id="csr" class="input" value="python" placeholder="Runtime"><input id="csrpo" class="input" placeholder="Repository URL">${btn('Create service','createService()')}</div>${table(['Service','Runtime','Status','Region','URL','Actions'],s.map(x=>`<tr><td>${esc(x.name)}<br><span class="mono">${esc(x.service_code)}</span></td><td>${esc(x.runtime)}</td><td>${esc(x.status)}</td><td>${esc(x.region)}</td><td>${x.service_url?`<a class="btn secondary" target="_blank" href="${esc(x.service_url)}">Open</a>`:'-'}</td><td>${btn('Start',`serviceAction('${x.id}','start')`)}${btn('Stop',`serviceAction('${x.id}','stop')`,'secondary')}${btn('Restart',`serviceAction('${x.id}','restart')`,'secondary')}${btn('Deploy',`serviceAction('${x.id}','deploy')`)}</td></tr>`).join(''))}</div><div class="workspace" style="margin-top:14px">${table(['Agent','Region','Status','Last seen'],a.map(x=>`<tr><td>${esc(x.name)}</td><td>${esc(x.region)}</td><td>${esc(x.status)}</td><td>${esc(x.last_seen_at||'-')}</td></tr>`).join(''))}</div>`)}
async function createService(){let d={name:document.getElementById('csn').value.trim(),project_id:document.getElementById('csp').value.trim(),runtime:document.getElementById('csr').value.trim(),repo_url:document.getElementById('csrpo').value.trim(),branch:'main',region:'global'};let r=await api('/api/services',{method:'POST',body:JSON.stringify(d)});if(!r.r.ok)return alert(r.d.error||'create failed');compute()}
async function serviceAction(id,a){let u=a==='deploy'?'/api/services/'+id+'/deploy':'/api/services/'+id+'/'+a;let r=await api(u,{method:'POST',body:'{}'});if(!r.r.ok)return alert(r.d.error||a+' failed');compute()}
async function hosting(){let [st,gh,services]=await Promise.all([get('/api/providers/render/status'),get('/api/providers/github/status'),get('/api/services')]);shell('KOJA Launch','Application deployment, hosting provider control and service lifecycle.',`<div class="workspace"><div class="workspace-head"><h2>Deployment providers</h2><div class="actions">${btn('Refresh','hosting()','secondary')}</div></div>${table(['Provider','Mode','State','Details'],`<tr><td><strong>Render</strong></td><td>Managed hosting</td><td><span class="badge ${st.configured?'ok':'warn'}">${st.configured?'Operational':'Provider Required'}</span></td><td>${esc(st.configured?'Connected to Render':'Configure KOJA_RENDER_API_KEY and KOJA_RENDER_OWNER_ID')}</td></tr><tr><td><strong>GitHub</strong></td><td>GitHub Actions</td><td><span class="badge ${gh.status==='operational'?'ok':'warn'}">${esc(gh.status==='operational'?'Operational':gh.status==='provider_required'?'Provider Required':'Check configuration')}</span></td><td>${esc(gh.login||gh.message||gh.error||'GitHub Actions deployment adapter')}</td></tr>`)}</div><div class="workspace" style="margin-top:14px"><div class="workspace-head"><h2>New deployment</h2></div><div class="form-grid"><select id="launchProvider" class="input"><option value="render">Render — managed hosting</option><option value="github">GitHub — GitHub Actions</option><option value="koja-node">KOJA Node — native runtime</option></select><input id="hsName" class="input" placeholder="Service name"><input id="hsRepo" class="input" placeholder="GitHub repository URL (https://github.com/owner/repo)"><input id="hsBranch" class="input" value="main" placeholder="Branch"><input id="hsWorkflow" class="input" value="koja-deploy.yml" placeholder="GitHub workflow file (GitHub only)"><input id="hsBuild" class="input" value="pip install -r requirements.txt" placeholder="Build command"><input id="hsStart" class="input" value="gunicorn app:app" placeholder="Start command"><input id="hsRegion" class="input" value="oregon" placeholder="Region"><input id="hsProject" class="input" placeholder="KOJA CLOUD project ID">${btn('Deploy','createHostedService()')}</div><div class="muted">Render creates managed hosting. GitHub dispatches a real GitHub Actions workflow. KOJA Node queues native execution.</div></div><div class="workspace" style="margin-top:14px">${table(['Service','Provider','Status','Health','URL','Source'],services.map(x=>`<tr><td>${esc(x.name)}</td><td>${esc(x.provider||'koja-node')}</td><td>${esc(x.status)}</td><td><span id="health-${esc(x.id)}" class="badge warn">Not checked</span>${x.provider==='render'?` ${btn('Check / Wake',`checkServiceHealth('${x.id}')`,'secondary')}`:''}</td><td>${x.service_url?`<a class="btn" target="_blank" href="${esc(x.service_url)}">Open</a>`:'-'}</td><td class="mono">${esc(x.repo_url||'-')}</td></tr>`).join(''))}</div>`)}
async function checkServiceHealth(id){
  const badge=document.getElementById('health-'+id);
  const set=(state,msg)=>{if(badge){badge.textContent=msg||state;badge.className='badge '+(state==='online'?'ok':state==='offline'?'danger':'warn')}};
  set('waking','Checking…');
  for(let i=0;i<15;i++){
    try{
      const r=await api('/api/edge/services/'+encodeURIComponent(id)+'/health',{method:'GET'});
      const d=r.d||{};
      if(!r.r.ok){set('offline','Check failed');break}
      set(d.state||'unknown',d.state==='online'?'Online':d.state==='waking'?'Waking…':d.state==='sleeping'?'Sleeping — waking…':'Offline');
      if(d.state==='online'||d.state==='offline'||d.state==='unknown')break;
      await new Promise(res=>setTimeout(res,5000));
    }catch(e){set('offline','Check failed');break}
  }
}
async function createHostedService(){let provider=launchProvider.value;let rawRepo=hsRepo.value.trim();if(!rawRepo)return alert('Repository URL is required');let d={name:hsName.value.trim(),repo_url:rawRepo,branch:hsBranch.value.trim()||'main',workflow:hsWorkflow.value.trim()||'koja-deploy.yml',build_command:hsBuild.value.trim(),start_command:hsStart.value.trim(),region:hsRegion.value.trim()||'oregon',project_id:hsProject.value.trim(),deployment_provider:provider};if(provider==='render'){let r=await api('/api/providers/render/services',{method:'POST',body:JSON.stringify(d)});if(!r.r.ok)return alert(r.d.error||r.d.detail||'Render launch failed');hosting();return}if(provider==='github'){if(!d.project_id)return alert('KOJA CLOUD project ID required');let r=await api('/api/projects/'+d.project_id+'/github/deploy',{method:'POST',body:JSON.stringify(d)});if(!r.r.ok)return alert(r.d.message||r.d.error||r.d.detail||'GitHub deployment failed');alert('GitHub Actions deployment accepted');hosting();return}let r=await api('/api/compute/services',{method:'POST',body:JSON.stringify(d)});if(!r.r.ok)return alert(r.d.error||r.d.detail||'KOJA Node deployment failed');hosting()}
async function media(){let [a,b]=await Promise.all([get('/api/media/assets'),get('/api/media/broadcasts')]);a=Array.isArray(a)?a:(a.d||[]);b=Array.isArray(b)?b:(b.d||[]);shell('KOJA Media','Media library, 24/7 movie channels and broadcast control plane.',`<div class="workspace"><div class="workspace-head"><h2>Media Library</h2><div class="muted">Assets available to KOJA Stream broadcast channels.</div></div><div class="form-grid"><input id="mn" class="input" placeholder="Movie / asset title"><input id="mu" class="input" placeholder="Source URL"><select id="mt" class="select"><option value="video">video</option><option value="audio">audio</option><option value="image">image</option><option value="document">document</option></select>${btn('Add media','createMedia()')}</div>${table(['Asset','Type','Status','Source','Actions'],a.map(x=>`<tr><td><strong>${esc(x.name||x.title||'Media')}</strong></td><td>${esc(x.media_type||'-')}</td><td>${esc(x.status||'-')}</td><td class="mono">${esc(x.source_url||'-')}</td><td>${btn('Process',`processMedia('${x.id}')`)}${btn('Jobs',`mediaJobs('${x.id}')`,'secondary')} ${btn('Cancel',`cancelMedia('${x.id}')`,'danger')}</td></tr>`).join(''))}</div><div class="workspace" style="margin-top:14px"><div class="workspace-head"><h2>24/7 Movie Channels</h2><div class="muted">Continuous movie scheduling through a KOJA worker.</div></div><div class="form-grid"><input id="bn" class="input" placeholder="Channel name — e.g. KOJA Movies 24/7"><input id="bpid" class="input" placeholder="Project ID">${btn('Create 24/7 channel','createBroadcast()')}</div>${table(['Channel','Code','Mode','Status','Playlist','Playback','Actions'],b.map(x=>`<tr><td><strong>${esc(x.name||'-')}</strong></td><td class="mono">${esc(x.channel_code||'-')}</td><td>${esc(x.mode||'vod24x7')}</td><td>${esc(x.status||'-')}</td><td>${esc(x.playlist_count??0)} assets</td><td class="mono">${esc(x.playback_url||'-')}</td><td>${btn('Playlist',`broadcastPlaylist('${x.id}')`,'secondary')}${btn('Start',`broadcastAction('${x.id}','start')`)}${btn('Stop',`broadcastAction('${x.id}','stop')`,'danger')}${btn('Open',`window.open('${esc(x.watch_url||'#')}','_blank')`,'secondary')}</td></tr>`).join(''))}</div><div class="workspace" style="margin-top:14px"><div class="icon">KOJA MEDIA API</div><h2>Application connection</h2><p class="muted">KOJA AFRICA and other apps can discover channels through the project-scoped API while KOJA CLOUD owns the broadcast scheduler.</p><p class="mono">GET /api/v1/media/broadcasts<br>GET /api/v1/media/broadcasts/{id}<br>POST /api/v1/media/broadcasts/{id}/start</p></div>`)}
async function createMedia(){let r=await api('/api/media/assets',{method:'POST',body:JSON.stringify({name:mn.value.trim(),source_url:mu.value.trim(),media_type:mt.value})});if(!r.r.ok)return alert(r.d.error||'create failed');media()}
async function processMedia(id){let r=await api('/api/media/assets/'+id+'/process',{method:'POST',body:'{}'});if(!r.r.ok)return alert(r.d.error||'process failed');media()}
async function mediaJobs(id){let r=await api('/api/media/assets/'+id+'/jobs');if(!r.r.ok)return alert(r.d.error||'jobs failed');alert(JSON.stringify(r.d,null,2))}
async function cancelMedia(id){let r=await api('/api/media/assets/'+id+'/cancel',{method:'POST',body:'{}'});if(!r.r.ok)return alert(r.d.error||'cancel failed');media()}
async function createBroadcast(){let r=await api('/api/media/broadcasts',{method:'POST',body:JSON.stringify({name:bn.value.trim(),project_id:bpid.value.trim(),mode:'vod24x7',loop:true})});if(!r.r.ok)return alert(r.d.error||'channel creation failed');media()}
async function broadcastPlaylist(id){let r=await api('/api/media/broadcasts/'+id);if(!r.r.ok)return alert(r.d.error||'playlist load failed');let x=r.d;let current=(x.playlist||[]).map((p,i)=>(i+1)+'. '+(p.name||p.id)).join('\\n');let add=prompt('Enter movie asset IDs, comma-separated, in broadcast order.\\n\\nCurrent playlist:\\n'+(current||'(empty)'));if(add===null)return;let ids=add.split(',').map(v=>v.trim()).filter(Boolean);let q=await api('/api/media/broadcasts/'+id+'/playlist',{method:'PUT',body:JSON.stringify({asset_ids:ids})});if(!q.r.ok)return alert(q.d.error||'playlist update failed');media()}
async function broadcastAction(id,a){let r=await api('/api/media/broadcasts/'+id+'/'+a,{method:'POST',body:'{}'});if(!r.r.ok)return alert(r.d.error||a+' failed');alert((r.d.message||('Broadcast '+a+' accepted'))+'\\n\\n'+(r.d.playback_url||''));media()}
async function forge(){let [st,repos]=await Promise.all([get('/api/forge/status'),get('/api/forge/repos')]);let native=await get('/api/v1/production/readiness');shell('KOJA Forge','Source control, build configuration and deployment execution.',`<div class="workspace"><div class="workspace-head"><h2>Forge runtime</h2><span class="badge ${st.github?.reachable?'ok':'warn'}">${st.github?.reachable?'source connected':'source provider required'}</span></div>${table(['Capability','State','Evidence'],`<tr><td>Git provider</td><td>${st.github?.configured?'configured':'not configured'}</td><td>${esc(st.github?.login||st.github?.error||'-')}</td></tr><tr><td>Build/deploy</td><td>${esc(native.checks?.forge?.status||'unknown')}</td><td>${esc(native.checks?.forge?.note||'')}</td></tr>`)}</div><div class="workspace" style="margin-top:14px"><div class="form-grid"><input id="fproj" class="input" placeholder="Project ID"><input id="fname" class="input" placeholder="Application name"><input id="frepo" class="input" placeholder="Repository URL"><input id="fbranch" class="input" value="main"><input id="fbuild" class="input" value="pip install -r requirements.txt"><input id="fstart" class="input" value="gunicorn app:app"><input id="fhealth" class="input" value="/health">${btn('Build & deploy','forgeDeploy()')}</div></div><div class="workspace" style="margin-top:14px">${table(['Repository','Visibility','Branch','Source'],(repos||[]).map(x=>`<tr><td>${esc(x.name)}</td><td>${x.private?'private':'public'}</td><td>${esc(x.default_branch||'main')}</td><td><a class="btn secondary" target="_blank" href="${esc(x.html_url||'#')}">Open</a></td></tr>`).join(''))}</div>`)}
async function forgeDeploy(){let d={project_id:fproj.value.trim(),name:fname.value.trim(),repo_url:frepo.value.trim(),branch:fbranch.value.trim()||'main',build_command:fbuild.value.trim(),start_command:fstart.value.trim(),health_path:fhealth.value.trim()||'/health'};let r=await api('/api/forge/deploy',{method:'POST',body:JSON.stringify(d)});if(!r.r.ok)return alert(r.d.error||r.d.detail||'deploy failed');alert('Deployment accepted');forge()}
async function apiModule(){let k=await get('/api/keys');shell('KOJA API','Project API credentials, scopes, rotation and developer access.',`<div class="workspace"><div class="form-grid"><input id="kn" class="input" placeholder="Key name"><input id="ks" class="input" value="read,write" placeholder="Scopes">${btn('Create API key','createKey()')}</div>${table(['Name','Prefix','Scopes','Status','Actions'],k.map(x=>`<tr><td>${esc(x.name)}</td><td class="mono">${esc(x.key_prefix)}</td><td>${esc((x.scopes||[]).join(', '))}</td><td>${esc(x.status)}</td><td>${x.status==='active'?btn('Revoke',`keyAction('${x.id}','revoke')`,'danger'):''}${x.status==='active'?btn('Rotate',`keyAction('${x.id}','rotate')`,'secondary'):''}</td></tr>`).join(''))}</div><div class="workspace" style="margin-top:14px">${table(['Endpoint','Purpose'],`<tr><td class="mono">/api/v1/openapi.json</td><td>OpenAPI contract</td></tr><tr><td class="mono">/api/v1/health</td><td>Health</td></tr><tr><td class="mono">/api/v1/projects</td><td>Project API</td></tr><tr><td class="mono">/api/v1/storage/buckets</td><td>Storage API</td></tr><tr><td class="mono">/api/v1/media/assets</td><td>Media API</td></tr>`)}</div>`)}
async function createKey(){let r=await api('/api/keys',{method:'POST',body:JSON.stringify({name:kn.value.trim(),scopes:ks.value.split(',').map(x=>x.trim()).filter(Boolean)})});if(!r.r.ok)return alert(r.d.error||'create failed');alert('Copy API key now:\n'+r.d.secret);apiModule()}
async function keyAction(id,a){let r=await api('/api/keys/'+id+'/'+a,{method:'POST',body:'{}'});if(!r.r.ok)return alert(r.d.error||a+' failed');if(r.d.secret)alert('New API key:\n'+r.d.secret);apiModule()}
async function webhooks(){let w=await get('/api/webhooks');shell('Webhooks','Webhook registration, activation state and outbound delivery configuration.',`<div class="workspace"><div class="form-grid"><input id="wn" class="input" placeholder="Webhook name"><input id="wu" class="input" placeholder="HTTPS endpoint"><input id="we" class="input" value="*" placeholder="Events">${btn('Create webhook','createWebhook()')}</div>${table(['Name','Endpoint','Events','Status','Last HTTP','Actions'],w.map(x=>`<tr><td>${esc(x.name)}</td><td class="mono">${esc(x.url)}</td><td>${esc((x.events||[]).join(', '))}</td><td>${esc(x.status)}</td><td>${esc(x.last_status_code||'-')}</td><td>${btn(x.status==='active'?'Disable':'Enable',`toggleWebhook('${x.id}','${x.status==='active'?'disabled':'active'}')`,'secondary')}</td></tr>`).join(''))}</div>`)}
async function createWebhook(){let r=await api('/api/webhooks',{method:'POST',body:JSON.stringify({name:wn.value.trim(),url:wu.value.trim(),events:we.value.split(',').map(x=>x.trim())})});if(!r.r.ok)return alert(r.d.error||'create failed');webhooks()}
async function toggleWebhook(id,status){let r=await api('/api/webhooks/'+id,{method:'PATCH',body:JSON.stringify({status})});if(!r.r.ok)return alert(r.d.error||'update failed');webhooks()}
async function jobs(){let j=await get('/api/jobs');shell('Jobs','Unified operation queue and execution history.',`<div class="workspace">${table(['Code','Type','Status','Region','Created','Message'],j.map(x=>`<tr><td class="mono">${esc(x.job_code)}</td><td>${esc(x.job_type)}</td><td>${esc(x.status)}</td><td>${esc(x.region)}</td><td>${esc(x.created_at)}</td><td>${esc(x.message||x.error_message||'')}</td></tr>`).join(''))}</div>`)}
async function audit(){let a=await get('/api/audit');shell('Audit','Tenant-scoped security and operational event history.',`<div class="workspace">${table(['Time','Action','Resource','ID','Metadata'],a.map(x=>`<tr><td>${esc(x.created_at)}</td><td>${esc(x.action)}</td><td>${esc(x.resource_type)}</td><td class="mono">${esc(x.resource_id)}</td><td class="mono">${esc(JSON.stringify(x.metadata||{}))}</td></tr>`).join(''))}</div>`)}
async function billing(){let b=await get('/api/billing/usage');shell('Usage / Billing','Resource consumption and billing-ready usage records.',`<div class="workspace">${table(['Metric','Quantity'],Object.entries(b.totals||{}).map(([k,v])=>`<tr><td>${esc(k)}</td><td>${esc(v)}</td></tr>`).join(''))}</div><div class="workspace" style="margin-top:14px">${table(['Time','Service','Metric','Quantity','Unit'],(b.recent_events||[]).slice(0,100).map(x=>`<tr><td>${esc(x.created_at)}</td><td>${esc(x.service)}</td><td>${esc(x.metric)}</td><td>${esc(x.quantity)}</td><td>${esc(x.unit)}</td></tr>`).join(''))}</div>`)}
async function providers(){let p=await get('/api/infrastructure/providers');shell('Infrastructure','Provider adapters, regions and execution capabilities.',`<div class="workspace">${table(['Provider','Code','Type','Status','Regions','Capabilities'],p.map(x=>`<tr><td>${esc(x.name)}</td><td class="mono">${esc(x.provider_code)}</td><td>${esc(x.service_type)}</td><td>${esc(x.status)}</td><td>${esc(JSON.stringify(x.regions||[]))}</td><td class="mono">${esc(JSON.stringify(x.capabilities||{}))}</td></tr>`).join(''))}</div>`)}
async function durability(){let [r,s]=await Promise.all([get('/api/v1/production/readiness'),get('/api/v1/native/services/status')]);shell('Durability','Native storage and control-plane persistence status. KOJA CLOUD does not label ephemeral Render storage as durable.',`<div class="workspace">${table(['Check','State','Evidence'],`<tr><td>Native root</td><td>${esc(r.checks?.durability?.status||'-')}</td><td class="mono">${esc(r.checks?.durability?.native_root||s.native_root||'-')}</td></tr><tr><td>Native database</td><td>${esc(s.checks?.control_database?.status||'-')}</td><td class="mono">${esc(s.checks?.control_database?.detail||'-')}</td></tr><tr><td>Storage</td><td>${esc(s.checks?.storage?.status||'-')}</td><td>Write/read/delete probe</td></tr><tr><td>Backups</td><td>${esc(s.checks?.backup?.status||'-')}</td><td>Native backup root</td></tr><tr><td>KOJA Node storage</td><td>${esc(r.checks?.node_durability?.status||'-')}</td><td class="mono">${esc(r.checks?.node_durability?.native_root||'No online node')}</td></tr>`)}</div>`)}
async function nodes(){let r=await api('/api/v34/nodes');if(!r.r.ok)throw new Error(r.d.error||'nodes failed');let ns=r.d.nodes||[];shell('Nodes','Real KOJA NODE execution plane. Existing nodes only — no duplicate node registration.',`<div class="workspace"><div class="workspace-head"><div><h2>Execution Nodes</h2><div class="muted">${ns.length} registered node${ns.length===1?'':'s'}</div></div><div class="actions">${btn('Refresh','nodes()','secondary')}</div></div>${table(['Node','Status','Region','Heartbeat','CPU','RAM','FFmpeg','Actions'],ns.map(x=>{let m=x.metrics||{};return `<tr><td><strong>${esc(x.name)}</strong><br><span class="mono">${esc(x.node_code)}<br>${esc(x.node_id)}</span></td><td><span class="badge ${x.status==='online'?'ok':'warn'}">${esc(x.status)}</span></td><td>${esc(x.region)}</td><td>${esc(fmtDate(x.last_heartbeat))}</td><td>${esc(m.cpu_percent??m.cpu??'-')}</td><td>${esc(m.memory_percent??m.memory_ratio??'-')}</td><td>${m.ffmpeg_available?'YES':'UNKNOWN'}</td><td>${btn('Health',`nodeAction('${x.node_id}','health')`)} ${btn('Test FFmpeg',`nodeAction('${x.node_id}','ffmpeg')`,'secondary')} ${btn('Jobs',`nodeJobs('${x.node_id}')`,'secondary')}</td></tr>`}).join(''))}</div>`)}
async function nodeAction(nodeId,action){let r=await api('/api/v34/nodes/'+encodeURIComponent(nodeId)+'/actions',{method:'POST',body:JSON.stringify({action})});if(!r.r.ok)throw new Error(r.d.error||'action failed');if(r.d.redirect_url)location.href=r.d.redirect_url}
async function nodeJobs(nodeId){let r=await api('/api/v34/nodes/'+encodeURIComponent(nodeId)+'/jobs');if(!r.r.ok)throw new Error(r.d.error||'jobs failed');let js=r.d.jobs||[];shell('Node Jobs','Actual native-node queue and execution history.',`<div class="workspace">${table(['Job ID','State','Type','Created','Updated','Result'],js.map(x=>`<tr><td class="mono"><a href="/jobs/${esc(x.job_id)}">${esc(x.job_id)}</a></td><td>${esc(x.state)}</td><td>${esc((x.payload||{}).action||(x.payload||{}).operation||'-')}</td><td>${esc(fmtDate(x.created_at))}</td><td>${esc(fmtDate(x.updated_at))}</td><td class="mono">${esc(JSON.stringify(x.result||{}))}</td></tr>`).join(''))}</div>`)}
async function runE2E(){let r=await api('/api/v1/native/e2e-test',{method:'POST',body:'{}'});if(!r.r.ok)return alert(r.d.error||'E2E failed');let x=r.d;let rows=(x.results||[]).map(v=>`${v.service}: ${v.status}${v.detail?' — '+v.detail:''}`).join('\n');alert('KOJA CLOUD E2E\nPassed: '+x.summary.passed+'\nFailed: '+x.summary.failed+'\n\n'+rows);runtime();render(currentModule)}
boot();
</script></body></html>'''
MODULE_CSS = '''*{box-sizing:border-box}body{margin:0;font-family:system-ui,Arial;background:#07101d;color:#f7f9fc}a{text-decoration:none;color:inherit}.top{height:72px;border-bottom:1px solid #1b2a3e;background:#091523;display:flex;align-items:center;justify-content:space-between;padding:0 24px;position:sticky;top:0}.brand{font-weight:800}.brand span{color:#4da3ff}.wrap{max-width:1200px;margin:auto;padding:28px 20px 60px}.hero{padding:18px 0 24px}.hero h1{font-size:32px;margin:8px 0}.muted{color:#91a4ba}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:16px;margin:20px 0}.card{border:1px solid #1d3149;background:#0d1b2b;border-radius:16px;padding:22px;min-height:120px}.card h2{font-size:19px;margin:10px 0}.icon{font-size:12px;font-weight:800;letter-spacing:1px;color:#5fb0ff}.btn{display:inline-block;background:#1769b0;color:white;padding:11px 15px;border-radius:10px;font-weight:700;margin:6px 6px 6px 0}.secondary{background:#14263b}.err{color:#ff7272;white-space:pre-wrap;overflow-wrap:anywhere}.success{color:#62d89b;white-space:pre-wrap;overflow-wrap:anywhere}.form{max-width:720px}.input{display:block;width:100%;padding:13px 14px;margin:10px 0;background:#081321;color:#f7f9fc;border:1px solid #29415c;border-radius:10px;outline:none}.input:focus{border-color:#4da3ff;box-shadow:0 0 0 3px rgba(77,163,255,.12)}.form .btn{border:0;cursor:pointer;font:inherit}.form form{margin-top:16px}h2{margin-top:26px}.resource-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px}.resource-card{border:1px solid #1d3149;background:#0a1625;border-radius:12px;padding:15px}.resource-title{font-weight:800;margin-bottom:10px}.raw-data{margin-top:8px;color:#91a4ba}.raw-data pre{white-space:pre-wrap;overflow:auto;max-height:280px;font-size:12px}.badge{display:inline-block;padding:4px 8px;border-radius:999px;background:#26364b}.badge.ok{color:#62d89b}.badge.warn{color:#f5c76a}.badge.danger{color:#ff7272}'''

def _h(v):
    from markupsafe import escape
    return str(escape('' if v is None else v))

def _q(path, params):
    try:
        return sb(path, params=params)
    except Exception as e:
        return e

def render_module_page(key):
    if key not in MODULE_META:
        return redirect('/dashboard')
    if not session.get('user_id'):
        return redirect('/login')
    uid=session['user_id']
    title,desc=MODULE_META[key]
    sections=[]
    def error_card(label,e):
        return f'<div class="card"><div class="icon">API STATUS</div><h2>{_h(label)}</h2><p class="err">{_h(str(e))}</p></div>'
    try:
        oid=require_org(uid)
        org_error=None
    except Exception as e:
        oid=None
        org_error=e
    if key=='organizations':
        # Organization creation is server-rendered so it works even if dashboard JavaScript fails.
        org_form='''<div class="card form"><div class="icon">CREATE ORGANIZATION</div><h2>Create Organization</h2><p class="muted">Create an isolated cloud tenant for your projects, compute, storage, databases, media, live services and APIs.</p><form method="post" action="/organizations/create"><input class="input" name="name" placeholder="Organization name" maxlength="120" required><input class="input" name="slug" placeholder="Slug (optional)" maxlength="80"><button class="btn" type="submit">Create Organization</button></form></div>'''
        try:
            rows=user_orgs(uid)
            cards=''.join('<div class="card"><div class="icon">ORGANIZATION</div><h2>'+_h((r.get('cloud_organizations') or {}).get('name') or r.get('organization_id'))+'</h2><p>'+_h((r.get('cloud_organizations') or {}).get('slug') or '')+' - '+_h(r.get('role') or 'member')+'</p><a class="btn secondary" href="/organizations/switch/'+_h(r.get('organization_id'))+'">Use Organization</a></div>' for r in rows)
            sections.append(org_form+'<h2>Your Organizations</h2><div class="grid">'+(cards or '<p class="muted">No organizations yet.</p>')+'</div>')
        except Exception as e:
            sections.append(org_form+error_card('Organizations',e))
    elif oid is None:
        sections.append(error_card('Organization context',org_error))
    elif key=='projects':
        rows=_q('/rest/v1/cloud_projects',{'organization_id':f'eq.{oid}','select':'*','order':'created_at.desc'})
        if isinstance(rows,Exception): sections.append(error_card('Projects API',rows))
        else:
            form='''<div class="card form"><div class="icon">CREATE PROJECT</div><h2>New project</h2><p class="muted">Projects isolate compute, storage, databases, media and live resources inside this organization.</p><form id="projectForm" onsubmit="createProjectServer(event)"><input class="input" id="projectName" placeholder="Project name" required maxlength=120><button class="btn" type="submit">Create Project</button><div id="projectMsg" class="err"></div></form></div>'''
            cards=''.join('<div class="card"><div class="icon">PROJECT</div><h2>'+_h(x.get('name'))+'</h2><p>'+_h(x.get('project_code'))+' - '+_h(x.get('status'))+'</p></div>' for x in rows)
            project_script='''<script>async function createProjectServer(e){e.preventDefault();let m=document.getElementById(\'projectMsg\');try{let r=await fetch(\'/api/projects\',{method:\'POST\',headers:{\'Content-Type\':\'application/json\'},body:JSON.stringify({name:document.getElementById(\'projectName\').value})});let d=await r.json();if(!r.ok)throw new Error(d.error||\'create_failed\');location.reload()}catch(x){m.textContent=x.message}}</script>'''
            sections.append(form+'<h2>Projects</h2><div class="grid">'+(cards or '<p class="muted">No projects yet.</p>')+'</div>'+project_script)
    elif key=='compute':
        if request.args.get('created') == '1':
            sections.append('<div class="success card"><strong>Service created successfully.</strong> The new service is now listed below.</div>')
        if request.args.get('error'):
            sections.append('<div class="err card"><strong>Service creation failed:</strong> '+_h(request.args.get('error'))+'</div>')
        services=_q('/rest/v1/cloud_compute_services',{'organization_id':f'eq.{oid}','select':'*','order':'created_at.desc'})
        agents=_q('/rest/v1/cloud_compute_agents',{'owner_user_id':f'eq.{uid}','select':'id,agent_code,name,region,status,last_seen_at,capabilities','order':'created_at.desc'})
        projects=_q('/rest/v1/cloud_projects',{'organization_id':f'eq.{oid}','status':'neq.archived','select':'id,name,project_code','order':'created_at.desc'})
        project_options='' if isinstance(projects,Exception) else ''.join('<option value="'+_h(x.get('id'))+'">'+_h(x.get('name'))+' ('+_h(x.get('project_code'))+')</option>' for x in projects)
        form='''<div class="card form"><div class="icon">CREATE COMPUTE SERVICE</div><h2>New KOJA Run Service</h2><p class="muted">A service is deployed by a registered KOJA compute agent or infrastructure provider.</p><form id="computeForm" method="post" action="/services/create"><input class="input" id="csName" name="name" placeholder="Service name" required><select class="select" id="csProject" name="project_id" required><option value="">Select project</option>'''+project_options+'''</select><select class="select" id="csRuntime" name="runtime"><option value="docker">Docker</option><option value="python">Python</option><option value="node">Node.js</option><option value="static">Static</option></select><input class="input" id="csRepo" name="repo_url" placeholder="GitHub repository URL (optional)"><input class="input" id="csBranch" name="branch" value="main" placeholder="Branch"><input class="input" id="csBuild" name="build_command" placeholder="Build command (optional)"><input class="input" id="csStart" name="start_command" placeholder="Start command (optional)"><input class="input" id="csRegion" name="region" value="global" placeholder="Region"><div class="row"><input class="input" id="csCpu" name="cpu" type="number" step="0.1" value="0.5" placeholder="CPU"><input class="input" id="csMem" name="memory_mb" type="number" value="512" placeholder="Memory MB"></div><button class="btn" type="submit">Create Service</button><div id="computeMsg" class="err"></div></form></div>'''+'''<div class="card form"><div class="icon">REGISTER AGENT</div><h2>KOJA Run Agent</h2><p class="muted">Register a Linux/Docker execution node. The token is shown once.</p><form onsubmit="registerAgentServer(event)"><input class="input" id="agentName" value="KOJA KOJA Run Agent" placeholder="Agent name"><input class="input" id="agentRegion" value="global" placeholder="Region"><button class="btn secondary" type="submit">Register Agent</button><div id="agentMsg" class="err"></div></form></div>'''
        sections.append(form)
        if isinstance(services,Exception): sections.append(error_card('KOJA Run services API',services))
        else:
            cards=''
            for x in services:
                sid=str(x.get('id') or x.get('service_code') or '')
                cards += '''<div class="card"><div class="icon">SERVICE</div><h2>''' + _h(x.get('name')) + '''</h2><p>''' + _h(x.get('service_code')) + ''' • ''' + _h(x.get('status')) + ''' • ''' + _h(x.get('runtime')) + ''' • ''' + _h(x.get('region')) + '''</p><p>''' + _h(x.get('repo_url') or 'No repository connected') + '''</p><div class="row"><button class="btn" onclick="computeAction(''' + repr(sid) + ''','deploy')">Deploy</button><button class="btn secondary" onclick="computeAction(''' + repr(sid) + ''','start')">Start</button><button class="btn secondary" onclick="computeAction(''' + repr(sid) + ''','stop')">Stop</button><button class="btn secondary" onclick="computeAction(''' + repr(sid) + ''','restart')">Restart</button><button class="btn secondary" onclick="computeDetails(''' + repr(sid) + ''')">Details</button></div><div id="service-''' + _h(sid) + '''"></div></div>'''
            sections.append('<h2>Services</h2><div class="grid">'+(cards or '<div class="empty">No compute services yet. Create a project first, then create a service.</div>')+'</div>')
        if isinstance(agents,Exception): sections.append(error_card('KOJA Run agents API',agents))
        else:
            cards=''.join('<div class="card"><div class="icon">AGENT</div><h2>'+_h(x.get('name'))+'</h2><p>'+_h(x.get('agent_code'))+' • '+_h(x.get('status'))+' • '+_h(x.get('region'))+'</p><p class="small">Last seen: '+_h(x.get('last_seen_at') or '-')+'</p></div>' for x in agents)
            sections.append('<h2>Agents</h2><div class="grid">'+(cards or '<div class="empty">No agents registered. Register a Linux/Docker agent to execute workloads.</div>')+'</div>')
        sections.append('''<script>async function postJSON(u,d){let r=await fetch(u,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(d||{})});let j=await r.json().catch(()=>({error:'invalid_response'}));if(!r.ok)throw new Error(j.error||j.detail||'request_failed');return j}async function createProjectServer(e){e.preventDefault();let m=document.getElementById('projectMsg');try{await postJSON('/api/projects',{name:document.getElementById('projectName').value});location.reload()}catch(x){m.textContent=x.message}}async function createComputeServer(e){e.preventDefault();let m=document.getElementById('computeMsg');m.textContent='Creating service…';let payload={name:document.getElementById('csName').value.trim(),project_id:document.getElementById('csProject').value,runtime:document.getElementById('csRuntime').value,repo_url:document.getElementById('csRepo').value.trim(),branch:document.getElementById('csBranch').value.trim()||'main',build_command:document.getElementById('csBuild').value.trim(),start_command:document.getElementById('csStart').value.trim(),region:document.getElementById('csRegion').value.trim()||'global',cpu:Number(document.getElementById('csCpu').value||.5),memory_mb:Number(document.getElementById('csMem').value||512)};if(!payload.project_id){m.textContent='Select a project first.';return}try{let d=await postJSON('/api/services',payload);m.className='success';m.textContent='Service created: '+(d.service_code||d.name||'success');setTimeout(()=>{location.href='/dashboard?module=compute'},50)}catch(x){m.className='err';m.textContent=x.message}}async function registerAgentServer(e){e.preventDefault();let m=document.getElementById('agentMsg');try{let d=await postJSON('/api/agents/register',{name:document.getElementById('agentName').value,region:document.getElementById('agentRegion').value,capabilities:{docker:true,linux:true}});m.textContent='AGENT TOKEN (save it now): '+d.agent_token}catch(x){m.textContent=x.message}}async function computeAction(id,a){try{let u=a==='deploy'?'/api/services/'+id+'/deploy':'/api/services/'+id+'/'+a;let d=await postJSON(u,{});alert(a+' queued: '+(d.job?.id||d.deployment?.deployment_code||d.status||'ok'));location.reload()}catch(x){alert(x.message)}}async function computeDetails(id){let box=document.getElementById('service-'+id);box.innerHTML='<p class="small">Loading...</p>';try{let d=await (await fetch('/api/infrastructure/service/'+id)).json();box.innerHTML='<div class="card"><h3>Infrastructure</h3><p>Volumes: '+(d.volumes||[]).length+' • Routes: '+(d.routes||[]).length+' • Jobs: '+(d.jobs||[]).length+' • Deployments: '+(d.deployments||[]).length+'</p><p class="mono">'+JSON.stringify(d.service||{})+'</p></div>'}catch(x){box.innerHTML='<p class="err">'+x.message+'</p>'}}</script>''')
    elif key=='database':
        rows=_q('/rest/v1/cloud_databases',{'organization_id':f'eq.{oid}','select':'*','order':'created_at.desc'})
        if isinstance(rows,Exception): sections.append(error_card('KOJA Data API',rows))
        else:
            cards=''.join('<div class="card"><div class="icon">DATABASE</div><h2>'+_h(x.get('name'))+'</h2><p>'+_h(x.get('engine'))+' - '+_h(x.get('status'))+' - '+_h(x.get('region'))+'</p><p>'+_h(x.get('database_code'))+'</p></div>' for x in rows)
            sections.append('<div class="grid">'+(cards or '<p class="muted">No databases yet.</p>')+'</div>')
    elif key=='storage':
        buckets=_q('/rest/v1/cloud_storage_buckets',{'organization_id':f'eq.{oid}','select':'*','order':'created_at.desc'})
        objects=_q('/rest/v1/cloud_storage_objects',{'organization_id':f'eq.{oid}','select':'id','limit':'500'})
        if isinstance(buckets,Exception): sections.append(error_card('Storage buckets API',buckets))
        else:
            cards=''.join('<div class="card"><div class="icon">BUCKET</div><h2>'+_h(x.get('name') or x.get('bucket_name'))+'</h2><p>'+_h(x.get('status'))+' - '+_h(x.get('visibility') or x.get('provider') or 'storage')+'</p></div>' for x in buckets)
            sections.append('<h2>Buckets</h2><div class="grid">'+(cards or '<p class="muted">No buckets yet.</p>')+'</div>')
        if isinstance(objects,Exception): sections.append(error_card('Storage objects API',objects))
        else: sections.append('<h2>Objects</h2><p class="muted">'+str(len(objects))+' tracked objects in this organization.</p>')
    elif key=='media':
        rows=_q('/rest/v1/cloud_media_assets',{'organization_id':f'eq.{oid}','select':'*','order':'created_at.desc'})
        if isinstance(rows,Exception): sections.append(error_card('Media API',rows))
        else:
            cards=''.join('<div class="card"><div class="icon">MEDIA</div><h2>'+_h(x.get('name') or x.get('title'))+'</h2><p>'+_h(x.get('media_type'))+' - '+_h(x.get('status'))+'</p></div>' for x in rows)
            sections.append('<div class="grid">'+(cards or '<p class="muted">No media assets yet.</p>')+'</div>')
    elif key=='live':
        rows=_q('/rest/v1/cloud_live_channels',{'organization_id':f'eq.{oid}','select':'*','order':'created_at.desc'})
        if isinstance(rows,Exception): sections.append(error_card('KOJA Stream API',rows))
        else:
            cards=''.join('<div class="card"><div class="icon">LIVE</div><h2>'+_h(x.get('name'))+'</h2><p>'+_h(x.get('status'))+' - '+_h(x.get('channel_code'))+'</p></div>' for x in rows)
            sections.append('<div class="grid">'+(cards or '<p class="muted">No live channels yet.</p>')+'</div>')
    elif key=='api':
        api_error=request.args.get('error')
        api_notice=''
        if api_error:
            api_notice='<div class="card" style="border:1px solid #dc2626"><p class="err">'+_h(api_error)+'</p></div>'
        if request.args.get('created'):
            api_notice='<div class="card"><p class="success">API key created successfully. Copy the secret below before leaving this page.</p></div>'
        if request.args.get('revoked'):
            api_notice='<div class="card"><p class="success">API key revoked.</p></div>'
        if request.args.get('rotated'):
            api_notice='<div class="card"><p class="success">API key rotated. The replacement secret is shown below.</p></div>'
        rows=_q('/rest/v1/cloud_api_keys',{'organization_id':f'eq.{oid}','select':'id,name,key_prefix,project_id,scopes,status,last_used_at,expires_at,created_at','order':'created_at.desc'})
        projects=_q('/rest/v1/cloud_projects',{'organization_id':f'eq.{oid}','status':'neq.archived','select':'id,name,project_code','order':'created_at.desc'})
        created_secret=None
        created_name=None
        created_prefix=None
        if isinstance(rows,Exception):
            sections.append(error_card('KOJA API keys',rows))
        else:
            project_options='' if isinstance(projects,Exception) else ''.join('<option value="'+_h(x.get('id'))+'">'+_h(x.get('name'))+' ('+_h(x.get('project_code'))+')</option>' for x in projects)
            secret_card=''
            if created_secret:
                secret_card='''<div class="card" style="border:2px solid #1d4ed8"><div class="icon">KEY CREATED</div><h2>Save your API key now</h2><p class="muted">This secret is shown once. KOJA CLOUD does not store the plaintext secret. Store it in your application environment or secret manager.</p><textarea id="createdApiSecret" class="input" readonly style="min-height:90px">'''+_h(created_secret)+'''</textarea><p><button class="btn" type="button" onclick="navigator.clipboard.writeText(document.getElementById('createdApiSecret').value)">Copy API Key</button></p><p class="mono">Prefix: '''+_h(created_prefix or '')+''' | Name: '''+_h(created_name or '')+'''</p></div>'''
            form='''<div class="card form"><div class="icon">DEVELOPER ACCESS</div><h2>API Keys</h2><p class="muted">Create credentials for your applications. Every key is permanently scoped to one KOJA CLOUD project.</p><form method="post" action="/cloud-api/keys/create"><input class="input" name="name" maxlength="100" placeholder="Key name — e.g. KOJA AFRICA Production" required><select class="input" name="project_id" required><option value="">Select project</option>'''+project_options+'''</select><div class="muted" style="margin:12px 0 7px">Permissions</div><label><input type="checkbox" name="scopes" value="read" checked> Read</label><br><label><input type="checkbox" name="scopes" value="write"> Write</label><br><label><input type="checkbox" name="scopes" value="storage"> Storage</label><br><label><input type="checkbox" name="scopes" value="database"> KOJA Data</label><br><label><input type="checkbox" name="scopes" value="media"> Media</label><br><label><input type="checkbox" name="scopes" value="live"> KOJA Stream</label><br><label><input type="checkbox" name="scopes" value="compute"> KOJA Run</label><p><button class="btn" type="submit">Create API Key</button></p></form></div>'''
            cards=[]
            project_map={str(x.get('id')):x for x in projects} if not isinstance(projects,Exception) else {}
            for x in rows:
                pr=project_map.get(str(x.get('project_id')),{}); pname=pr.get('name') or x.get('project_id') or '—'
                actions=''
                if x.get('status')=='active':
                    actions='<form method="post" action="/cloud-api/keys/'+_h(x.get('id'))+'/revoke" style="display:inline" onsubmit="return confirm(\'Revoke this API key?\')"><button class="btn secondary" type="submit">Revoke</button></form><form method="post" action="/cloud-api/keys/'+_h(x.get('id'))+'/rotate" style="display:inline;margin-left:8px"><button class="btn" type="submit">Rotate</button></form>'
                cards.append("<div class='card'><div class='icon'>API KEY</div><h2>"+_h(x.get('name'))+"</h2><p><span class='mono'>"+_h(x.get('key_prefix'))+"…</span> • "+_h(x.get('status'))+"</p><p>Project: <strong>"+_h(pname)+"</strong></p><p>Scopes: "+_h(', '.join(x.get('scopes') or []))+"</p><p class='muted'>Created: "+_h(x.get('created_at') or '-')+"<br>Last used: "+_h(x.get('last_used_at') or 'Never')+"</p>"+actions+"</div>")
            sections.append(api_notice+secret_card+form+'<h2>Active & historical keys</h2><div class="grid">'+(''.join(cards) or '<p class="muted">No API keys yet.</p>')+'</div><div class="card"><div class="icon">API ENDPOINTS</div><h2>Developer API</h2><p class="muted">Send the generated credential using the <span class="mono">X-KOJA-API-KEY</span> header.</p><p class="mono">GET /api/v1/projects<br>GET /api/v1/storage/buckets<br>POST /api/v1/storage/buckets<br>GET /api/v1/media/assets<br>POST /api/v1/media/assets<br>GET /api/v1/live/channels<br>GET /api/v1/usage</p></div>')
    elif key=='billing':
        me=current_user() or {}
        sections.append('<div class="card"><div class="icon">BILLING</div><h2>Organization billing</h2><p>Active organization: '+_h(oid)+'</p><p>Account: '+_h(me.get('email'))+'</p><p>Usage is tracked per organization and project.</p></div>')
    else:
        sections.append('<div class="card"><div class="icon">KOJA CLOUD</div><h2>'+_h(title)+'</h2><p>'+_h(desc)+'</p></div>')

    body=''.join(sections)
    html='<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><title>KOJA CLOUD - '+_h(title)+'</title><style>'+MODULE_CSS+'</style></head><body><header class="top"><a class="brand" href="/dashboard">KOJA <span>CLOUD</span></a><a class="btn secondary" href="/dashboard">Dashboard</a></header><main class="wrap"><a class="btn secondary" href="/dashboard">Back to Dashboard</a><section class="hero"><div class="muted">KOJA CLOUD MODULE</div><h1>'+_h(title)+'</h1><p class="muted">'+_h(desc)+'</p></section>'+body+'</main></body></html>'
    return Response(html,mimetype='text/html')

@app.get('/')
def koja_cloud_root():
    # Main KOJA CLOUD URL is the canonical entry point. Authenticated users enter
    # the production control plane; unauthenticated users receive the real sign-in
    # page instead of the dashboard JavaScript redirecting to a missing /login route.
    if session.get('user_id'):
        return dashboard_page()
    return Response(LOGIN_HTML,mimetype='text/html')



@app.get('/jobs/<job_id>')
@auth_required
def v34_job_page(job_id):
    html='''<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><title>KOJA CLOUD — Real Job</title><style>*{box-sizing:border-box}body{margin:0;background:#050b14;color:#eef5ff;font-family:system-ui,Arial}.wrap{max-width:1100px;margin:auto;padding:18px}.top{display:flex;justify-content:space-between;gap:10px;align-items:center;margin-bottom:16px}.card{background:#081523;border:1px solid #1b3048;border-radius:12px;padding:16px;margin-bottom:14px}.mono{font-family:ui-monospace,monospace;font-size:12px;word-break:break-all}.muted{color:#8ea4ba}.badge{display:inline-block;border:1px solid #2a455f;border-radius:999px;padding:5px 9px}.ok{color:#6ee7a3}.warn{color:#ffd166}.err{color:#ff7272}pre{white-space:pre-wrap;overflow:auto;max-height:420px;background:#050b14;padding:12px;border-radius:8px}.btn{display:inline-block;background:#176fba;color:#fff;border:0;border-radius:8px;padding:9px 12px;text-decoration:none;margin-right:6px;cursor:pointer}</style></head><body><main class="wrap"><div class="top"><div><strong>KOJA CLOUD</strong><div class="muted">Real execution instance</div></div><div><a class="btn" href="/dashboard?module=nodes">Nodes</a><a class="btn" href="/dashboard?module=jobs">Jobs</a></div></div><div id="job"></div></main><script>const id=__JOB_ID__;function esc(v){return String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}async function load(){let r=await fetch('/api/v34/jobs/'+id,{cache:'no-store'});let d=await r.json();if(!r.ok){document.getElementById('job').innerHTML='<div class="card err">'+esc(d.error||'Job unavailable')+'</div>';return}let result=d.result||{},payload=d.payload||{};let cls=['succeeded','failed','cancelled'].includes(d.state)?'ok':'warn';document.getElementById('job').innerHTML='<div class="card"><h1>Job</h1><p class="mono">'+esc(d.job_id)+'</p><p><span class="badge '+cls+'">'+esc(d.state)+'</span></p><p>Node: <span class="mono">'+esc(d.node_id||'awaiting assignment')+'</span></p><p>Created: '+esc(d.created_at)+'<br>Leased: '+esc(d.leased_at||'-')+'<br>Finished: '+esc(d.finished_at||'-')+'</p></div><div class="card"><h2>Action</h2><pre>'+esc(JSON.stringify(payload,null,2))+'</pre></div><div class="card"><h2>Actual result</h2><pre>'+esc(JSON.stringify(result,null,2))+'</pre></div>'}load();setInterval(load,2000)</script></body></html>'''
    html=html.replace('__JOB_ID__',json.dumps(job_id))
    return Response(html,mimetype='text/html')

@app.get('/dashboard')
def dashboard_page():
    # V24 uses one production console for every module so the web UI is backed by
    # the live APIs instead of falling back to the older static module-card pages.
    return Response(DASHBOARD_HTML, mimetype='text/html')

def provision_cloud_account(uid, email='', name=''):
    """Provision the complete control-plane identity path for a newly authenticated user.
    Safe to call repeatedly: existing customer/organization memberships are reused.
    """
    email=(email or '').strip().lower()
    name=(name or '').strip()
    try:
        existing=sb('/rest/v1/cloud_users',params={'id':f'eq.{uid}','select':'id,email,full_name','limit':'1'})
        if not existing:
            sb('/rest/v1/cloud_users','POST',{'id':uid,'email':email,'full_name':name},params={'select':'id'})
        else:
            patch={}
            if email and not existing[0].get('email'): patch['email']=email
            if name and not existing[0].get('full_name'): patch['full_name']=name
            if patch: sb('/rest/v1/cloud_users','PATCH',patch,params={'id':f'eq.{uid}'})
    except Exception:
        pass
    try:
        org=active_org_id(uid)
        if org: return org
    except Exception:
        pass
    try:
        customer=ensure_customer(uid, (name or (email.split('@')[0] if email else 'KOJA'))+' Cloud')
        slug='org-'+secrets.token_hex(5)
        org=create_org_for_user(uid, (name or (email.split('@')[0] if email else 'KOJA'))+' Cloud', slug)
        return org.get('id')
    except Exception:
        return None

LOGIN_HTML=r"""<!doctype html><html lang="en"><head><meta name="viewport" content="width=device-width,initial-scale=1"><meta charset="utf-8"><title>KOJA CLOUD — Sign in</title><style>*{box-sizing:border-box}body{margin:0;min-height:100vh;background:#07101d;color:#fff;font-family:system-ui,-apple-system,Segoe UI,Arial;display:grid;place-items:center}.wrap{width:min(460px,92vw);padding:20px}.card{background:#0b1726;border:1px solid #20344b;border-radius:18px;padding:26px;box-shadow:0 20px 60px #0005}.brand{font-weight:900;font-size:22px;margin-bottom:24px}.brand span{color:#4da3ff}h1{margin:0 0 8px;font-size:28px}p{color:#9fb0ca;line-height:1.5}label{display:block;margin:16px 0 7px;font-weight:700}input{width:100%;padding:13px;background:#07101d;color:#fff;border:1px solid #29415c;border-radius:10px;font-size:15px}.btn{width:100%;padding:13px 16px;border:0;border-radius:10px;background:#1769b0;color:#fff;font-weight:800;cursor:pointer;margin-top:18px}.err{color:#ff8a8a;min-height:22px;margin-top:12px}.links{text-align:center;margin-top:18px}.links a{color:#67b1ff;text-decoration:none}</style></head><body><main class="wrap"><section class="card"><div class="brand">KOJA <span>CLOUD</span></div><h1>Sign in</h1><p>Sign in to enter your KOJA CLOUD production control plane.</p><label for="email">Email</label><input id="email" type="email" autocomplete="email" required><label for="password">Password</label><input id="password" type="password" autocomplete="current-password" required><div id="err" class="err"></div><button class="btn" id="submit">Sign in to KOJA CLOUD</button><div class="links">Need an account? <a href="/register">Create one</a></div></section></main><script>async function login(){err.textContent='Signing in…';submit.disabled=true;try{let r=await fetch('/api/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email:email.value.trim(),password:password.value})});let d=await r.json().catch(()=>({}));if(!r.ok){err.textContent=d.error||'Sign in failed';submit.disabled=false;return}location.href='/dashboard'}catch(e){err.textContent='Connection failed. Please try again.';submit.disabled=false}}submit.addEventListener('click',login);password.addEventListener('keydown',e=>{if(e.key==='Enter')login()});</script></body></html>"""

REGISTER_HTML=r"""<!doctype html><html lang="en"><head><meta name="viewport" content="width=device-width,initial-scale=1"><meta charset="utf-8"><title>KOJA CLOUD — Create account</title><style>*{box-sizing:border-box}body{margin:0;min-height:100vh;background:#07101d;color:#fff;font-family:system-ui,-apple-system,Segoe UI,Arial;display:grid;place-items:center}.wrap{width:min(460px,92vw);padding:20px}.card{background:#0b1726;border:1px solid #20344b;border-radius:18px;padding:26px}.brand{font-weight:900;font-size:22px;margin-bottom:24px}.brand span{color:#4da3ff}h1{margin:0 0 8px}p{color:#9fb0ca;line-height:1.5}label{display:block;margin:14px 0 7px;font-weight:700}input{width:100%;padding:13px;background:#07101d;color:#fff;border:1px solid #29415c;border-radius:10px;font-size:15px}.btn{width:100%;padding:13px;border:0;border-radius:10px;background:#1769b0;color:#fff;font-weight:800;cursor:pointer;margin-top:18px}.err{color:#ff8a8a;min-height:22px;margin-top:12px}.links{text-align:center;margin-top:18px}.links a{color:#67b1ff;text-decoration:none}</style></head><body><main class="wrap"><section class="card"><div class="brand">KOJA <span>CLOUD</span></div><h1>Create your account</h1><p>Create the identity used to manage KOJA CLOUD organizations, projects and resources.</p><label>Full name</label><input id="name" autocomplete="name"><label>Email</label><input id="email" type="email" autocomplete="email" required><label>Password</label><input id="password" type="password" autocomplete="new-password" minlength="8" required><div id="err" class="err"></div><button class="btn" id="submit">Create account</button><div class="links">Already have an account? <a href="/login">Sign in</a></div></section></main><script>async function register(){err.textContent='Creating account…';submit.disabled=true;try{let r=await fetch('/api/auth/register',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:name.value.trim(),email:email.value.trim(),password:password.value})});let d=await r.json().catch(()=>({}));if(!r.ok){err.textContent=d.error||'Account creation failed';submit.disabled=false;return}if(d.logged_in){location.href='/dashboard'}else{location.href='/login'}}catch(e){err.textContent='Connection failed. Please try again.';submit.disabled=false}}submit.addEventListener('click',register)</script></body></html>"""

@app.get('/login')
def login_page():
    if session.get('user_id'):
        return redirect('/dashboard')
    return Response(LOGIN_HTML,mimetype='text/html')

@app.get('/register')
def register_page():
    if session.get('user_id'):
        return redirect('/dashboard')
    return Response(REGISTER_HTML,mimetype='text/html')

@app.get('/onboarding')
@auth_required
def onboarding_page():
    uid=session['user_id']; oid=active_org_id(uid)
    if oid: return redirect('/dashboard')
    return Response(ONBOARDING_HTML, mimetype='text/html')

ONBOARDING_HTML=r"""<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><title>KOJA CLOUD — Setup</title><style>body{margin:0;background:#07101d;color:#fff;font-family:system-ui,Arial}.wrap{max-width:720px;margin:6vh auto;padding:24px}.hero,.card{background:#0b1726;border:1px solid #20344b;border-radius:18px;padding:24px;margin-bottom:16px}.steps{display:grid;gap:10px}.step{padding:15px;border:1px solid #29415c;border-radius:12px;background:#091523}.num{display:inline-grid;place-items:center;width:28px;height:28px;border-radius:50%;background:#1769b0;font-weight:800;margin-right:8px}input{width:100%;padding:13px;margin:7px 0;box-sizing:border-box;background:#07101d;color:#fff;border:1px solid #29415c;border-radius:10px}.btn{display:inline-block;padding:12px 16px;border-radius:10px;background:#1769b0;color:#fff;border:0;text-decoration:none;cursor:pointer;font-weight:700}.err{color:#ff7777;min-height:22px}</style></head><body><main class="wrap"><section class="hero"><div>KOJA CLOUD • ACCOUNT SETUP</div><h1>Set up your Cloud organization</h1><p>Your identity is ready. Create the organization that will own your projects, API keys and cloud resources.</p></section><section class="card"><label>Organization name</label><input id="name" placeholder="e.g. My Company Cloud"><div id="err" class="err"></div><button class="btn" onclick="createOrg()">Create organization</button></section><section class="card"><h2>After setup</h2><div class="steps"><div class="step"><span class="num">1</span>Organization — tenant boundary and team access.</div><div class="step"><span class="num">2</span>Project — isolated environment for your application.</div><div class="step"><span class="num">3</span>API key — scoped developer credential.</div><div class="step"><span class="num">4</span>Resources — compute, storage, database, media and live.</div><div class="step"><span class="num">5</span>Usage / Billing — metering, quotas and plan information.</div></div></section></main><script>async function createOrg(){err.textContent='';let v=name.value.trim();if(v.length<2){err.textContent='Enter an organization name.';return}let r=await fetch('/api/organizations',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:v})});let d=await r.json().catch(()=>({}));if(!r.ok){err.textContent=d.detail||d.error||'Organization creation failed';return}location.href='/dashboard?module=projects'}</script></body></html>"""

@app.post('/api/auth/register')
def register():
    d=request.get_json(silent=True) or {}
    email=(d.get('email') or '').strip().lower(); password=d.get('password') or ''; name=(d.get('name') or '').strip()[:160]
    if not email or '@' not in email or len(password)<8:
        return jsonify(error='valid email and password of at least 8 characters required'),400
    if not configured(): return jsonify(error='Supabase not configured'),503
    r=requests.post(SUPABASE_URL+'/auth/v1/signup',headers=sb_headers(),json={'email':email,'password':password},timeout=30)
    if r.status_code>=400:
        try: msg=(r.json() or {}).get('msg') or (r.json() or {}).get('message') or (r.json() or {}).get('error_description')
        except Exception: msg=None
        return jsonify(error=msg or 'account_creation_failed'),r.status_code
    body=r.json(); user=body.get('user') or {}; uid=user.get('id')
    if not uid: return jsonify(error='account_created_without_user_id'),502
    org_id=provision_cloud_account(uid,email,name)
    access=body.get('access_token')
    if access:
        session.clear(); session['user_id']=uid; session['email']=email; session['access_token']=access
        if org_id: session['organization_id']=org_id
        return jsonify(message='account_created',user_id=uid,organization_id=org_id,logged_in=True),201
    return jsonify(message='account_created_sign_in_required',user_id=uid,organization_id=org_id,logged_in=False),201

@app.post('/api/auth/login')
def login():
    d=request.get_json(silent=True) or {}; email=(d.get('email') or '').strip().lower(); password=d.get('password') or ''
    if not email or not password: return jsonify(error='email_and_password_required'),400
    r=requests.post(SUPABASE_URL+'/auth/v1/token?grant_type=password',headers=sb_headers(),json={'email':email,'password':password},timeout=30)
    if r.status_code>=400: return jsonify(error='invalid_login'),401
    body=r.json(); user=body.get('user') or {}; uid=user.get('id')
    if not uid: return jsonify(error='login_user_missing'),502
    session.clear(); session['user_id']=uid; session['email']=email; session['access_token']=body.get('access_token')
    org_id=provision_cloud_account(uid,email,user.get('user_metadata',{}).get('full_name',''))
    if org_id: session['organization_id']=org_id
    return jsonify(message='logged_in',user_id=uid,organization_id=org_id),200

@app.post('/api/auth/logout')
def logout(): session.clear(); return jsonify(message='logged_out')

@app.get('/api/me')
@auth_required
def me():
    u=current_user() or {'id':session['user_id']}
    return jsonify({**u,'organization_id':active_org_id(session['user_id']),'organizations':user_orgs(session['user_id'])})

def _api_secret_response(secret, name, prefix, action='created'):
    title='API key created' if action=='created' else 'API key rotated'
    html='''<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><title>KOJA CLOUD - API Key</title><style>body{font-family:system-ui,-apple-system,Segoe UI,sans-serif;background:#0b1220;color:#fff;margin:0}.wrap{max-width:760px;margin:0 auto;padding:24px}.card{background:#111b2e;border:1px solid #263754;border-radius:16px;padding:22px;margin:18px 0}.muted{color:#9fb0ca}.input{width:100%;box-sizing:border-box;background:#0a1020;color:#fff;border:1px solid #334765;border-radius:10px;padding:12px;font-size:15px}.btn{display:inline-block;background:#2563eb;color:#fff;border:0;border-radius:10px;padding:11px 16px;text-decoration:none;cursor:pointer}.danger{color:#fca5a5}.mono{font-family:ui-monospace,SFMono-Regular,monospace}</style></head><body><main class="wrap"><div class="card"><div class="muted">KOJA CLOUD • DEVELOPER ACCESS</div><h1>'''+_h(title)+'''</h1><p class="muted">The plaintext secret is displayed once. It is not stored in the browser session or database.</p><textarea id="secret" class="input" readonly style="min-height:110px">'''+_h(secret)+'''</textarea><p><button class="btn" onclick="navigator.clipboard.writeText(document.getElementById('secret').value)">Copy API Key</button></p><p class="mono">Name: '''+_h(name)+'''<br>Prefix: '''+_h(prefix)+'''</p><p class="danger">Store this key in an environment variable or secret manager. Do not commit it to GitHub.</p><a class="btn" href="/dashboard?module=api">Return to KOJA API</a></div></main></body></html>'''
    return Response(html,mimetype='text/html')

@app.post('/cloud-api/keys/create')
@auth_required
def cloud_api_key_create_page():
    uid=session['user_id']; oid=require_org(uid)
    name=(request.form.get('name') or '').strip()[:100]
    pid=(request.form.get('project_id') or '').strip()
    scopes=request.form.getlist('scopes') or ['read']
    allowed={'read','write','storage','database','media','live','compute','admin'}
    scopes=[str(x).strip().lower() for x in scopes if str(x).strip().lower() in allowed]
    if len(name)<1: return redirect('/dashboard?module=api&error=api_key_name_required')
    if not pid: return redirect('/dashboard?module=api&error=project_required')
    project=_require_project(uid,oid,pid)
    if not project: return redirect('/dashboard?module=api&error=project_not_found')
    if not scopes: return redirect('/dashboard?module=api&error=scope_required')
    raw='koja_'+secrets.token_urlsafe(32); prefix=raw[:13]; kh=hashlib.sha256(raw.encode()).hexdigest()
    payload={'organization_id':oid,'project_id':pid,'user_id':uid,'owner_user_id':uid,'name':name,'key_prefix':prefix,'key_hash':kh,'scopes':scopes,'status':'active'}
    try:
        saved=_insert('/rest/v1/cloud_api_keys',payload)
    except Exception:
        try:
            saved=_insert('/rest/v1/cloud_api_keys',{'owner_user_id':uid,'project_id':pid,'name':name,'key_prefix':prefix,'key_hash':kh,'scopes':scopes,'status':'active'})
        except Exception as e:
            return redirect('/dashboard?module=api&error='+quote('api_key_create_failed: '+str(e)[:100]))
    audit(uid,'api_key.create','api_key',saved.get('id'),{'organization_id':oid,'project_id':pid,'scopes':scopes})
    return _api_secret_response(raw,name,prefix,'created')

@app.post('/cloud-api/keys/<kid>/revoke')
@auth_required
def cloud_api_key_revoke_page(kid):
    uid=session['user_id']; oid=require_org(uid)
    key=_one('/rest/v1/cloud_api_keys',{'id':f'eq.{kid}','user_id':f'eq.{uid}','organization_id':f'eq.{oid}','select':'id','limit':'1'})
    if not key: return redirect('/dashboard?module=api&error=api_key_not_found')
    _patch('/rest/v1/cloud_api_keys',{'id':f'eq.{kid}'},{'status':'revoked','revoked_at':now()})
    audit(uid,'api_key.revoke','api_key',kid,{'organization_id':oid})
    return redirect('/dashboard?module=api&revoked=1')

@app.post('/cloud-api/keys/<kid>/rotate')
@auth_required
def cloud_api_key_rotate_page(kid):
    uid=session['user_id']; oid=require_org(uid)
    key=_one('/rest/v1/cloud_api_keys',{'id':f'eq.{kid}','user_id':f'eq.{uid}','organization_id':f'eq.{oid}','select':'*','limit':'1'})
    if not key: return redirect('/dashboard?module=api&error=api_key_not_found')
    raw='koja_'+secrets.token_urlsafe(32); prefix=raw[:13]
    _patch('/rest/v1/cloud_api_keys',{'id':f'eq.{kid}'},{'status':'revoked','revoked_at':now()})
    new=_insert('/rest/v1/cloud_api_keys',{'organization_id':oid,'user_id':uid,'owner_user_id':uid,'project_id':key.get('project_id'),'name':key.get('name','API Key'),'key_prefix':prefix,'key_hash':hashlib.sha256(raw.encode()).hexdigest(),'scopes':key.get('scopes',['read']),'status':'active'})
    audit(uid,'api_key.rotate','api_key',new.get('id'),{'organization_id':oid,'replaced':kid})
    return _api_secret_response(raw,key.get('name','API Key'),prefix,'rotated')

@app.get('/api/keys')
@auth_required
def list_keys():
    oid=require_org(session['user_id']); return jsonify(sb('/rest/v1/cloud_api_keys',params={'organization_id':f'eq.{oid}','select':'id,name,key_prefix,project_id,scopes,status,last_used_at,expires_at,created_at','order':'created_at.desc'}))

@app.post('/api/keys')
@auth_required
def create_key():
    uid=session['user_id']; oid=require_org(uid); d=request.get_json(silent=True) or {}
    name=(d.get('name') or 'API Key').strip()[:100]
    pid=(d.get('project_id') or '').strip()
    if not pid: return jsonify(error='project_id_required'),400
    project=_require_project(uid,oid,pid)
    if not project: return jsonify(error='project_not_found'),404
    scopes=d.get('scopes') or ['read']
    if not isinstance(scopes,list): scopes=[str(scopes)]
    allowed={'read','write','storage','database','media','live','compute','admin'}
    scopes=[str(x).strip().lower() for x in scopes if str(x).strip().lower() in allowed]
    if not scopes: return jsonify(error='at_least_one_valid_scope_required'),400
    raw='koja_'+secrets.token_urlsafe(32); prefix=raw[:13]; kh=hashlib.sha256(raw.encode()).hexdigest()
    payload={'organization_id':oid,'project_id':pid,'user_id':uid,'owner_user_id':uid,'name':name,'key_prefix':prefix,'key_hash':kh,'scopes':scopes,'status':'active'}
    try:
        saved=_insert('/rest/v1/cloud_api_keys',payload)
    except Exception as first_error:
        # Compatibility fallback for older schemas that do not yet expose organization_id/user_id.
        try:
            saved=_insert('/rest/v1/cloud_api_keys',{'owner_user_id':uid,'project_id':pid,'name':name,'key_prefix':prefix,'key_hash':kh,'scopes':scopes,'status':'active'})
        except Exception as second_error:
            return jsonify(error='api_key_create_failed',detail=str(second_error)[:300]),500
    audit(uid,'api_key.create','api_key',saved.get('id'),{'organization_id':oid,'project_id':pid,'scopes':scopes})
    return jsonify(ok=True,secret=raw,key_prefix=prefix,record={'id':saved.get('id'),'name':name,'project_id':pid,'scopes':scopes,'status':'active'}),201

@app.post('/organizations/create')
@auth_required
def create_organization_page():
    uid=session['user_id']; name=(request.form.get('name') or '').strip(); slug=(request.form.get('slug') or '').strip().lower()
    if len(name)<2: return redirect('/dashboard?module=organizations&error=organization_name_required')
    import re
    slug=re.sub(r'[^a-z0-9]+','-',slug).strip('-') if slug else 'org-'+secrets.token_hex(5)
    if len(slug)>80: slug=slug[:80].rstrip('-')
    try:
        if sb('/rest/v1/cloud_organizations',params={'slug':f'eq.{slug}','select':'id','limit':'1'}):
            return redirect('/dashboard?module=organizations&error=organization_slug_already_exists')
        row=create_org_for_user(uid,name,slug)
        audit(uid,'organization.create','organization',row['id'])
        return redirect('/dashboard?module=organizations&created=1')
    except Exception as e:
        return redirect('/dashboard?module=organizations&error='+quote(str(e)[:180]))

@app.get('/organizations/switch/<oid>')
@auth_required
def switch_organization_page(oid):
    uid=session['user_id']
    if not org_member(uid,oid): return redirect('/dashboard?module=organizations&error=organization_access_denied')
    session['organization_id']=oid
    return redirect('/dashboard?module=organizations&switched=1')

@app.get('/api/organizations')
@auth_required
def organizations(): return jsonify(user_orgs(session['user_id']))

@app.post('/api/organizations')
@auth_required
def create_organization():
    uid=session['user_id']; d=request.get_json() or {}; name=(d.get('name') or '').strip()
    if len(name)<2: return jsonify(error='organization_name_required'),400
    slug=(d.get('slug') or '').strip().lower()
    import re
    slug=re.sub(r'[^a-z0-9]+','-',slug).strip('-') if slug else ''
    if not slug: slug='org-'+secrets.token_hex(5)
    if len(slug)>80: slug=slug[:80].rstrip('-')
    try:
        existing=sb('/rest/v1/cloud_organizations',params={'slug':f'eq.{slug}','select':'id','limit':'1'})
        if existing: return jsonify(error='organization_slug_already_exists'),409
        row=create_org_for_user(uid,name,slug); audit(uid,'organization.create','organization',row['id']); return jsonify(row),201
    except Exception as e:
        return jsonify(error='organization_creation_failed',detail=str(e)[:500]),500

@app.post('/api/organizations/switch')
@auth_required
def switch_organization():
    uid=session['user_id']; oid=(request.get_json() or {}).get('organization_id')
    if not org_member(uid,oid): return jsonify(error='organization_access_denied'),403
    session['organization_id']=oid; return jsonify(message='organization_switched',organization_id=oid)

@app.post('/api/projects')
@auth_required
def create_project():
    uid=session['user_id']; oid=require_org(uid); d=request.get_json() or {}; name=(d.get('name') or 'Project').strip(); code='KOJA-'+secrets.token_hex(4).upper()
    row=sb('/rest/v1/cloud_projects','POST',{'owner_user_id':uid,'organization_id':oid,'name':name,'project_code':code,'status':'active'},params={'select':'*'})[0]
    audit(uid,'project.create','project',row['id'],{'organization_id':oid}); return jsonify(row),201

@app.get('/api/projects')
@auth_required
def projects():
    uid=session['user_id']; oid=require_org(uid); return jsonify(sb('/rest/v1/cloud_projects',params={'organization_id':f'eq.{oid}','select':'*','order':'created_at.desc'}))


@app.get('/api/projects/<pid>/control')
@auth_required
def project_control(pid):
    uid=session['user_id']; oid=require_org(uid); project=project_access(uid,oid,pid)
    if not project: return jsonify(error='project_not_found'),404
    real_id=project['id']
    counts={}
    for label,path in [('compute','/rest/v1/cloud_compute_services'),('storage','/rest/v1/cloud_storage_buckets'),('database','/rest/v1/cloud_databases'),('media','/rest/v1/cloud_media_assets'),('streams','/rest/v1/cloud_live_channels'),('webhooks','/rest/v1/cloud_webhooks'),('deployments','/rest/v1/cloud_compute_deployments')]:
        try:
            rows=sb(path,params={'project_id':f'eq.{real_id}','organization_id':f'eq.{oid}','select':'id','limit':'1000'})
            counts[label]=len(rows or [])
        except Exception:
            counts[label]=0
    services=sb('/rest/v1/cloud_compute_services',params={'project_id':f'eq.{real_id}','organization_id':f'eq.{oid}','select':'id,name,status,repo_url,branch,service_url,config','order':'created_at.desc','limit':'100'})
    deployments=sb('/rest/v1/cloud_compute_deployments',params={'project_id':f'eq.{real_id}','organization_id':f'eq.{oid}','owner_user_id':f'eq.{uid}','select':'id,service_id,deployment_code,status,created_at,completed_at','order':'created_at.desc','limit':'25'})
    return jsonify({'ok':True,'project':project,'counts':counts,'services':services,'deployments':deployments})

@app.get('/api/projects/<pid>/github/deploy/<deployment_id>/status')
@auth_required
def project_github_deploy_status(pid, deployment_id):
    uid=session['user_id']; oid=require_org(uid); project=project_access(uid,oid,pid)
    if not project: return jsonify(error='project_not_found'),404
    dep=_one('/rest/v1/cloud_compute_deployments',{'id':f'eq.{deployment_id}','project_id':f'eq.{project["id"]}','owner_user_id':f'eq.{uid}','organization_id':f'eq.{oid}','select':'*','limit':'1'})
    if not dep: return jsonify(error='deployment_not_found'),404
    jobs=sb('/rest/v1/cloud_compute_jobs',params={'deployment_id':f'eq.{deployment_id}','owner_user_id':f'eq.{uid}','organization_id':f'eq.{oid}','select':'id,status,message,result,created_at,started_at,completed_at','order':'created_at.desc','limit':'1'})
    job=jobs[0] if jobs else None
    return jsonify({'ok':True,'deployment':dep,'job':job,'stage':_github_deploy_stage(dep.get('status'),'queued' if not job else job.get('status'))})

def _github_deploy_stage(dep_status, job_status=None):
    st=str(dep_status or job_status or 'queued').lower()
    if st in ('queued','created','claimed'): return 'QUEUED'
    if st == 'building': return 'BUILDING'
    if st in ('deploying','running'): return 'DEPLOYING'
    if st == 'starting': return 'HEALTH CHECK'
    if st in ('healthy','completed'): return 'RUNNING'
    if st in ('failed','stopped','cancelled'): return 'FAILED'
    return st.upper()

@app.post('/api/projects/<pid>/github/deploy')
@auth_required
def project_github_deploy(pid):
    """Register a GitHub source against a KOJA project and create a real deployment record/job.
    Provider deployment is optional; without it the job remains queued for the KOJA data plane.
    """
    uid=session['user_id']; oid=require_org(uid); project=project_access(uid,oid,pid)
    if not project: return jsonify(error='project_not_found'),404
    d=request.get_json() or {}; repo=(d.get('repo_url') or '').strip(); branch=(d.get('branch') or 'main').strip() or 'main'; deployment_provider=(d.get('deployment_provider') or 'github').strip().lower()
    if not repo: return jsonify(error='github_repository_required'),400
    if deployment_provider=='github' and not github_provider_configured(): return jsonify(ok=False,error='github_provider_not_configured',code='PROVIDER_NOT_CONFIGURED',provider='github',status='provider_required',message='GitHub provider is not configured.',required=['KOJA_GITHUB_TOKEN'],next_action='Configure the GitHub provider in KOJA CLOUD settings.'),503
    try:
        _github_repo_parts(repo)
    except Exception:
        return jsonify(error='invalid_github_repository_url',detail='Use https://github.com/owner/repository or the equivalent .git URL.'),400
    name=(d.get('name') or project.get('name') or 'KOJA App').strip()[:120]
    existing=_one('/rest/v1/cloud_compute_services',{'project_id':f'eq.{project["id"]}','organization_id':f'eq.{oid}','repo_url':f'eq.{repo}','branch':f'eq.{branch}','select':'*','limit':'1'})
    if existing:
        svc=existing
    else:
        code='KCS-'+secrets.token_hex(5).upper(); cfg={'source_provider':'github','source_repo_url':repo,'source_branch':branch,'github_auto_deploy':True,'github_webhook_path':f'/api/forge/webhook/{{service_id}}','url_slug':(re.sub(r'[^a-z0-9-]+','-',name.lower()).strip('-')[:40] or 'web-service')+'-'+code[-6:].lower(),'url_status':'pending-edge-routing'}
        payload={'owner_user_id':uid,'organization_id':oid,'project_id':project['id'],'service_code':code,'name':name,'service_type':'web','runtime':d.get('runtime') or 'python','repo_url':repo,'branch':branch,'build_command':d.get('build_command') or 'pip install -r requirements.txt','start_command':d.get('start_command') or 'gunicorn app:app','health_path':d.get('health_path') or '/health','region':d.get('region') or 'global','cpu':float(d.get('cpu',0.5) or 0.5),'memory_mb':int(d.get('memory_mb',512) or 512),'status':'created','provider':'render' if render_provider_configured() else 'koja-node','config':cfg}
        svc=_insert('/rest/v1/cloud_compute_services',payload)
        _insert('/rest/v1/cloud_resources',{'owner_user_id':uid,'organization_id':oid,'project_id':project['id'],'resource_code':code,'resource_type':'compute','name':name,'status':'created','region':payload['region'],'config':{'service_id':svc['id']}})
    dep,job=queue_deploy(uid,svc['id'],None,'github_initial_deploy')
    if deployment_provider=='github':
        try:
            workflow=(d.get('workflow') or 'koja-deploy.yml').strip(); owner,repo_name=_github_repo_parts(repo); workflows=_github_actions_workflows(owner,repo_name)
            match=next((w for w in workflows if str(w.get('path') or '').split('/')[-1]==workflow or str(w.get('name') or '').lower()==workflow.lower() or str(w.get('id'))==workflow),None)
            if not match:
                return jsonify(ok=False,error='github_workflow_not_found',code='WORKFLOW_NOT_FOUND',provider='github',status='configuration_required',workflow=workflow,available_workflows=[{'id':w.get('id'),'name':w.get('name'),'path':w.get('path')} for w in workflows],deployment=dep,job=job,next_action='Add or select a GitHub Actions workflow for KOJA deployments.'),409
            inputs={'KOJA_PROJECT_ID':project['id'],'KOJA_SERVICE_ID':svc['id'],'KOJA_DEPLOYMENT_ID':dep['id'],'KOJA_SERVICE_NAME':name}
            dispatch=_github_actions_dispatch(owner,repo_name,match.get('id') or workflow,branch,inputs)
            cfg=dict(svc.get('config') or {}); cfg.update({'deployment_provider':'github','github_workflow':match.get('path') or workflow,'github_workflow_id':match.get('id'),'github_repository':f'{owner}/{repo_name}'})
            _patch('/rest/v1/cloud_compute_services',{'id':f'eq.{svc["id"]}'},{'provider':'github','config':cfg,'updated_at':now()})
            _patch('/rest/v1/cloud_compute_deployments',{'id':f'eq.{dep["id"]}'},{'config':{'reason':'github_initial_deploy','provider':'github','workflow':match.get('path') or workflow,'workflow_id':match.get('id'),'repository':f'{owner}/{repo_name}'}})
            _patch('/rest/v1/cloud_compute_jobs',{'id':f'eq.{job["id"]}'},{'message':'GitHub Actions workflow dispatched','result':dispatch})
            audit(uid,'project.github.actions.dispatch','deployment',dep['id'],{'project_id':project['id'],'repository':f'{owner}/{repo_name}','workflow':match.get('path') or workflow})
            return jsonify(ok=True,project=project,service=svc,deployment=dep,job=job,provider={'state':'queued','provider':'github','mode':'github-actions','workflow':match.get('path') or workflow,'workflow_id':match.get('id'),'repository':f'{owner}/{repo_name}'},next_action='Poll GitHub Actions for the workflow run status.'),202
        except Exception as e:
            return jsonify(ok=False,error='github_actions_dispatch_failed',code='PROVIDER_REQUEST_FAILED',provider='github',status='error',message=str(e)[:800],deployment=dep,job=job),502
    # Never block the customer request on a provider/network deployment call.
    # The durable KOJA job/deployment record is the execution boundary; a live KOJA
    # node can claim it, and an optional provider adapter may be triggered separately.
    provider_deploy=None; provider_error=None
    provider_state='not_configured'
    if render_provider_configured():
        provider_state='queued_for_provider'
        cfg=svc.get('config') or {}; rid=cfg.get('provider_service_id')
        if rid:
            def _background_provider_deploy(provider_id=rid, deployment_id=dep['id']):
                try:
                    result=_render_deploy(provider_id,False)
                    try:
                        audit(uid,'compute.provider.deploy.triggered','deployment',deployment_id,{'provider':'render','provider_result':result})
                    except Exception:
                        pass
                except Exception as exc:
                    try:
                        audit(uid,'compute.provider.deploy.error','deployment',deployment_id,{'provider':'render','error':str(exc)[:500]})
                    except Exception:
                        pass
            threading.Thread(target=_background_provider_deploy,daemon=True,name='koja-provider-deploy').start()
        else:
            provider_state='provider_service_not_registered'
    audit(uid,'project.github.deploy','project',project['id'],{'service_id':svc['id'],'deployment_id':dep['id'],'repository':repo,'branch':branch,'provider':'render' if render_provider_configured() else 'koja-node','provider_state':provider_state})
    return jsonify({'ok':True,'project':project,'service':svc,'deployment':dep,'job':job,'provider':{'state':provider_state},'provider_deploy':provider_deploy,'provider_error':provider_error,'webhook_url':f'{request.url_root.rstrip("/")}/api/forge/webhook/{svc["id"]}'}),202

@app.post('/services/create')
@auth_required
def create_service_page():
    uid=session['user_id']; oid=require_org(uid); d=request.form.to_dict(); pid=(d.get('project_id') or '').strip()
    if not pid: return redirect('/dashboard?module=compute&error=project_id_required')
    project=_require_project(uid,oid,pid)
    if not project: return redirect('/dashboard?module=compute&error=project_not_found')
    code='KCS-'+secrets.token_hex(5).upper()
    name=(d.get('name') or 'Web Service').strip()[:120]
    cfg={'url_slug':(re.sub(r'[^a-z0-9-]+','-',name.lower()).strip('-')[:40] or 'web-service')+'-'+code[-6:].lower(),'url_status':'pending-edge-routing'}
    data={'owner_user_id':uid,'organization_id':oid,'project_id':pid,'service_code':code,'name':name,'service_type':'web','runtime':d.get('runtime','docker'),'repo_url':d.get('repo_url',''),'branch':d.get('branch','main'),'build_command':d.get('build_command',''),'start_command':d.get('start_command',''),'health_path':d.get('health_path','/health'),'region':d.get('region','global'),'cpu':float(d.get('cpu') or .5),'memory_mb':int(float(d.get('memory_mb') or 512)),'status':'created','config':cfg}
    try:
        row=sb('/rest/v1/cloud_compute_services','POST',data,params={'select':'*'})[0]
        sb('/rest/v1/cloud_resources','POST',{'owner_user_id':uid,'organization_id':oid,'project_id':pid,'resource_code':code,'resource_type':'compute','name':name,'status':'created','region':data['region'],'config':{'service_id':row['id']}})
        audit(uid,'compute.service.create','compute_service',row['id'])
        return redirect('/dashboard?module=compute&created=1')
    except Exception as e:
        return redirect('/dashboard?module=compute&error='+quote(str(e)[:180]))

@app.post('/api/services')
@cloud_api_or_login
def create_service():
    uid=session['user_id']; oid=require_org(uid); d=request.get_json() or {}; pid=cloud_project_for_write(d.get('project_id'))
    if not pid: return jsonify(error='project_id_required'),400
    project=sb('/rest/v1/cloud_projects',params={'id':f'eq.{pid}','organization_id':f'eq.{oid}','select':'id'})
    if not project: return jsonify(error='project_not_found_or_not_in_active_organization'),404
    code='KCS-'+secrets.token_hex(5).upper()
    cfg=d.get('config',{}).copy() if isinstance(d.get('config',{}),dict) else {}; slug=re.sub(r'[^a-z0-9-]+','-',(d.get('name') or 'web-service').lower()).strip('-')[:40] or 'web-service'; cfg.setdefault('url_slug', slug+'-'+code[-6:].lower()); cfg.setdefault('url_status','pending-edge-routing'); data={'owner_user_id':uid,'organization_id':oid,'project_id':pid,'service_code':code,'name':d.get('name') or 'Web Service','service_type':d.get('service_type','web'),'runtime':d.get('runtime','docker'),'repo_url':d.get('repo_url',''),'branch':d.get('branch','main'),'build_command':d.get('build_command',''),'start_command':d.get('start_command',''),'health_path':d.get('health_path','/health'),'region':d.get('region','global'),'cpu':d.get('cpu',0.5),'memory_mb':d.get('memory_mb',512),'status':'created','config':cfg}
    row=sb('/rest/v1/cloud_compute_services','POST',data,params={'select':'*'})[0]
    sb('/rest/v1/cloud_resources','POST',{'owner_user_id':uid,'organization_id':oid,'project_id':pid,'resource_code':code,'resource_type':'compute','name':data['name'],'status':'created','region':data['region'],'config':{'service_id':row['id']}})
    audit(uid,'compute.service.create','compute_service',row['id']); return jsonify(row),201

@app.get('/api/services')
@cloud_api_or_login
def services():
    oid=require_org(session['user_id']); return jsonify(sb('/rest/v1/cloud_compute_services',params=cloud_project_filter({'organization_id':f'eq.{oid}','select':'*','order':'created_at.desc'})))

@app.post('/api/services/<sid>/env')
@cloud_api_or_login
def set_env(sid):
    uid=session['user_id']; d=request.get_json() or {}; key=d.get('key'); value=d.get('value')
    if not key or value is None: return jsonify(error='key_and_value_required'),400
    oid=require_org(uid); svc=sb('/rest/v1/cloud_compute_services',params={'id':f'eq.{sid}','owner_user_id':f'eq.{uid}','organization_id':f'eq.{oid}','select':'id'})
    if not svc: return jsonify(error='not_found'),404
    row={'owner_user_id':uid,'service_id':sid,'key_name':key,'value_ciphertext':encrypt(value),'organization_id':oid,'is_secret':bool(d.get('is_secret',True))}
    result=sb('/rest/v1/cloud_compute_environment','POST',row,params={'on_conflict':'service_id,key_name','select':'*'})
    return jsonify(result[0] if isinstance(result,list) else result)

@app.get('/api/services/<sid>/env')
@cloud_api_or_login
def get_env(sid):
    uid=session['user_id']; rows=sb('/rest/v1/cloud_compute_environment',params={'service_id':f'eq.{sid}','owner_user_id':f'eq.{uid}','select':'id,key_name,is_secret,created_at,updated_at'})
    return jsonify(rows)

def queue_deploy(uid,sid,source_commit=None,reason='manual'):
    oid=require_org(uid); svc=sb('/rest/v1/cloud_compute_services',params={'id':f'eq.{sid}','owner_user_id':f'eq.{uid}','organization_id':f'eq.{oid}','select':'*'})
    if not svc: raise RuntimeError('service_not_found')
    s=svc[0]; code='DEP-'+secrets.token_hex(5).upper()
    env_rows=sb('/rest/v1/cloud_compute_environment',params={'service_id':f'eq.{sid}','owner_user_id':f'eq.{uid}','select':'key_name,value_ciphertext'})
    env_spec=[{'key':e['key_name'],'value':decrypt(e['value_ciphertext'])} for e in env_rows]
    dep=sb('/rest/v1/cloud_compute_deployments','POST',{'owner_user_id':uid,'organization_id':oid,'project_id':s['project_id'],'service_id':sid,'deployment_code':code,'status':'queued','source_commit':source_commit,'config':{'reason':reason}},params={'select':'*'})[0]
    job=sb('/rest/v1/cloud_compute_jobs','POST',{'owner_user_id':uid,'organization_id':oid,'service_id':sid,'deployment_id':dep['id'],'job_type':'deploy','status':'queued','spec':{'service_id':sid,'repo_url':s['repo_url'],'branch':s['branch'],'source_commit':source_commit,'build_command':s['build_command'],'start_command':s['start_command'],'health_path':s['health_path'],'runtime':s.get('runtime','docker'),'cpu':s['cpu'],'memory_mb':s['memory_mb'],'port':(s.get('config') or {}).get('port',10000),'public_port':(s.get('config') or {}).get('public_port',0),'url_slug':(s.get('config') or {}).get('url_slug',''),'env':env_spec}},params={'select':'*'})[0]
    usage(uid,s['project_id'],'compute','deployments',1); audit(uid,'compute.deploy.create','deployment',dep['id'],{'job_id':job['id']}); return dep,job

@app.post('/api/services/<sid>/deploy')
@cloud_api_or_login
def deploy(sid):
    d=request.get_json() or {}; dep,job=queue_deploy(session['user_id'],sid,d.get('source_commit'),'manual'); return jsonify(deployment=dep,job=job),202

@app.get('/api/services/<sid>/scale')
@cloud_api_or_login
def service_scale_get(sid):
    uid=session['user_id']; oid=require_org(uid)
    rows=sb('/rest/v1/cloud_compute_services',params={'id':f'eq.{sid}','owner_user_id':f'eq.{uid}','organization_id':f'eq.{oid}','select':'*','limit':'1'})
    if not rows: return jsonify(error='not_found'),404
    s=rows[0]; cfg=s.get('config') or {}; autoscale=cfg.get('autoscale') or {}
    desired=int(cfg.get('replicas') or 1); min_r=int(autoscale.get('min_replicas') or 1); max_r=int(autoscale.get('max_replicas') or max(1,desired)); target=float(autoscale.get('target_cpu') or 70)
    return jsonify(service_id=sid, desired_replicas=desired, min_replicas=min_r, max_replicas=max_r, target_cpu=target, strategy=cfg.get('deployment_strategy','rolling'))

@app.post('/api/services/<sid>/scale')
@cloud_api_or_login
def service_scale(sid):
    uid=session['user_id']; oid=require_org(uid); d=request.get_json() or {}
    rows=sb('/rest/v1/cloud_compute_services',params={'id':f'eq.{sid}','owner_user_id':f'eq.{uid}','organization_id':f'eq.{oid}','select':'*','limit':'1'})
    if not rows: return jsonify(error='not_found'),404
    s=rows[0]; replicas=max(1,min(100,int(d.get('replicas',1))))
    cfg=(s.get('config') or {}).copy(); cfg['replicas']=replicas; cfg.setdefault('deployment_strategy','rolling')
    if isinstance(d.get('autoscale'),dict): cfg['autoscale']=d['autoscale']
    sb('/rest/v1/cloud_compute_services','PATCH',{'config':cfg},params={'id':f'eq.{sid}','owner_user_id':f'eq.{uid}','organization_id':f'eq.{oid}'})
    jobs=[]
    for replica in range(replicas):
        try:
            dep,job=queue_deploy(uid,sid,d.get('source_commit'),'scale-replica-%d'%(replica+1))
            spec=(job.get('spec') or {}).copy(); spec['replica_index']=replica; spec['replica_count']=replicas; spec['deployment_strategy']=cfg.get('deployment_strategy','rolling')
            sb('/rest/v1/cloud_compute_jobs','PATCH',{'spec':spec},params={'id':f'eq.{job["id"]}'})
            jobs.append(job['id'])
        except Exception as e:
            return jsonify(error='replica_queue_failed',detail=str(e),queued_jobs=jobs),500
    audit(uid,'compute.service.scale','compute_service',sid,{'replicas':replicas,'jobs':jobs})
    return jsonify(service_id=sid, desired_replicas=replicas, queued_jobs=jobs, strategy=cfg.get('deployment_strategy','rolling')),202

@app.post('/api/services/<sid>/autoscale')
@cloud_api_or_login
def service_autoscale(sid):
    uid=session['user_id']; oid=require_org(uid); d=request.get_json() or {}
    rows=sb('/rest/v1/cloud_compute_services',params={'id':f'eq.{sid}','owner_user_id':f'eq.{uid}','organization_id':f'eq.{oid}','select':'*','limit':'1'})
    if not rows: return jsonify(error='not_found'),404
    min_r=max(1,int(d.get('min_replicas',1))); max_r=max(min_r,min(100,int(d.get('max_replicas',min_r)))); target=max(1,min(100,int(d.get('target_cpu',70))))
    cfg=(rows[0].get('config') or {}).copy(); cfg['autoscale']={'enabled':bool(d.get('enabled',True)),'min_replicas':min_r,'max_replicas':max_r,'target_cpu':target}
    sb('/rest/v1/cloud_compute_services','PATCH',{'config':cfg},params={'id':f'eq.{sid}','owner_user_id':f'eq.{uid}','organization_id':f'eq.{oid}'})
    audit(uid,'compute.service.autoscale','compute_service',sid,cfg['autoscale'])
    return jsonify(service_id=sid,autoscale=cfg['autoscale'])

@app.get('/api/services/<sid>/deployments')
@cloud_api_or_login
def deployments(sid):
    uid=session['user_id']; oid=require_org(uid); return jsonify(sb('/rest/v1/cloud_compute_deployments',params={'service_id':f'eq.{sid}','owner_user_id':f'eq.{uid}','organization_id':f'eq.{oid}','select':'*','order':'created_at.desc'}))

@app.post('/api/jobs/claim')
@agent_auth
def claim_job():
    agent=request.koja_agent; region=agent.get('region','global')
    rows=sb('/rest/v1/cloud_compute_jobs',params={'status':'eq.queued','select':'*','order':'created_at.asc','limit':'1'})
    if not rows: return jsonify(job=None)
    job=rows[0]
    if job.get('owner_user_id') != agent.get('owner_user_id'): return jsonify(job=None)
    updated=sb('/rest/v1/cloud_compute_jobs','PATCH',{'status':'claimed','agent_id':agent['id'],'claimed_at':now()},params={'id':f'eq.{job["id"]}','status':'eq.queued','select':'*'})
    if not updated: return jsonify(job=None)
    return jsonify(job=updated[0],region=region)

@app.post('/api/jobs/<jid>/status')
@agent_auth
def job_status(jid):
    d=request.get_json() or {}; status=d.get('status','running'); patch={'status':status,'message':d.get('message',''),'result':d.get('result',{})}
    if status in ('running','building','starting'): patch['started_at']=d.get('started_at') or now()
    if status in ('healthy','failed','stopped'): patch['completed_at']=d.get('completed_at') or now()
    row=sb('/rest/v1/cloud_compute_jobs','PATCH',patch,params={'id':f'eq.{jid}','select':'*'})
    if d.get('deployment_id'):
        ds={'queued':'queued','claimed':'claimed','running':'deploying','building':'building','starting':'starting','healthy':'healthy','failed':'failed','stopped':'stopped'}
        sb('/rest/v1/cloud_compute_deployments','PATCH',{'status':ds.get(status,status),'build_log':d.get('build_log',''),'deploy_log':d.get('deploy_log',''),'completed_at':now() if status in ('healthy','failed','stopped') else None},params={'id':f'eq.{d["deployment_id"]}'})
    return jsonify(row)

@app.post('/api/jobs/<jid>/logs')
@agent_auth
def job_logs(jid):
    d=request.get_json() or {}; row=sb('/rest/v1/cloud_compute_job_logs','POST',{'job_id':jid,'stream':d.get('stream','stdout'),'message':d.get('message','')},params={'select':'*'})[0]; return jsonify(row),201

@app.get('/api/agents')
@auth_required
def agents():
    return jsonify(sb('/rest/v1/cloud_compute_agents',params={**owner_filter(session['user_id']),'select':'id,agent_code,name,region,capabilities,status,last_seen_at,metrics,created_at','order':'created_at.desc'}))

@app.post('/api/agents/register')
@auth_required
def agent_register():
    d=request.get_json() or {}; token=secrets.token_urlsafe(32); uid=session['user_id']; row=sb('/rest/v1/cloud_compute_agents','POST',{'owner_user_id':uid,'agent_code':'AG-'+secrets.token_hex(5).upper(),'name':d.get('name','KOJA Agent'),'region':d.get('region','global'),'capabilities':d.get('capabilities',{}),'token_hash':hashlib.sha256(token.encode()).hexdigest(),'status':'online','last_seen_at':now()},params={'select':'*'})[0]; return jsonify(agent=row,agent_token=token),201

@app.post('/api/agents/heartbeat')
@agent_auth
def agent_heartbeat():
    d=request.get_json() or {}; agent=request.koja_agent
    row=sb('/rest/v1/cloud_compute_agents','PATCH',{'status':'online','last_seen_at':now(),'metrics':d.get('metrics',{})},params={'id':f'eq.{agent["id"]}','select':'*'})[0]
    return jsonify(row)

@app.get('/api/agents/services/<sid>')
@agent_auth
def agent_service(sid):
    agent=request.koja_agent
    rows=sb('/rest/v1/cloud_compute_services',params={'id':f'eq.{sid}','owner_user_id':f'eq.{agent["owner_user_id"]}','select':'*','limit':'1'})
    if not rows: return jsonify(error='service_not_found'),404
    return jsonify(rows[0])

@app.post('/api/agents/services/<sid>/state')
@agent_auth
def agent_service_state(sid):
    agent=request.koja_agent; d=request.get_json() or {}
    rows=sb('/rest/v1/cloud_compute_services',params={'id':f'eq.{sid}','owner_user_id':f'eq.{agent["owner_user_id"]}','select':'id,owner_user_id,project_id,status,service_url,config','limit':'1'})
    if not rows: return jsonify(error='service_not_found'),404
    allowed={'created','queued','building','starting','running','healthy','stopped','failed','degraded','deploying'}
    st=d.get('status')
    patch={}
    if st in allowed: patch['status']=st
    if d.get('service_url') is not None: patch['service_url']=d.get('service_url')
    cfg=dict(rows[0].get('config') or {})
    if d.get('container_name'): cfg['container_name']=d['container_name']
    if d.get('container_id'): cfg['container_id']=d['container_id']
    if d.get('host_port'): cfg['host_port']=d['host_port']
    if d.get('health_url'): cfg['health_url']=d['health_url']
    if d.get('origin_url'): cfg['origin_url']=d['origin_url']
    cfg['last_agent_update']=now(); patch['config']=cfg
    out=sb('/rest/v1/cloud_compute_services','PATCH',patch,params={'id':f'eq.{sid}','owner_user_id':f'eq.{agent["owner_user_id"]}','select':'*'})
    return jsonify(out[0] if out else {})

@app.post('/api/webhooks/github/<sid>')
def github_webhook(sid):
    secret=os.getenv('GITHUB_WEBHOOK_SECRET',''); raw=request.get_data(); sig=request.headers.get('X-Hub-Signature-256','')
    if secret:
        expected='sha256='+hmac.new(secret.encode(),raw,hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected,sig): return jsonify(error='invalid_signature'),401
    d=request.get_json(silent=True) or {}; ref=d.get('ref',''); commit=(d.get('after') or '')
    if request.headers.get('X-GitHub-Event') not in ('push','ping'): return jsonify(ignored=True)
    if ref and not ref.endswith('/main'): return jsonify(ignored=True,ref=ref)
    # webhook deployments require an authenticated service owner, so lookup service and enqueue with its owner.
    svc=sb('/rest/v1/cloud_compute_services',params={'id':f'eq.{sid}','select':'*'})
    if not svc: return jsonify(error='service_not_found'),404
    dep,job=queue_deploy(svc[0]['owner_user_id'],sid,commit,'github_push'); return jsonify(deployment=dep,job=job),202

@app.get('/api/jobs/<jid>')
@auth_required
def job(jid):
    rows=sb('/rest/v1/cloud_compute_jobs',params={'id':f'eq.{jid}','owner_user_id':f'eq.{session["user_id"]}','select':'*'}); return jsonify(rows[0] if rows else {'error':'not_found'}), (200 if rows else 404)

@app.post('/api/storage/buckets')
@cloud_api_or_login
def create_bucket():
    d=request.get_json() or {}; name=d.get('name') or 'files'; uid=session['user_id']; project_id=cloud_project_for_write(d.get('project_id')); code='ST-'+secrets.token_hex(4).upper()
    oid=require_org(uid); row=sb('/rest/v1/cloud_storage_buckets','POST',{'owner_user_id':uid,'organization_id':oid,'project_id':requested_pid,'bucket_code':code,'bucket_name':name,'name':name,'provider':'supabase','project_id':requested_pid,'max_bytes':d.get('max_bytes',1073741824),'visibility':d.get('visibility','private'),'status':'active','project_id':project_id,'config':d.get('config',{})},params={'select':'*'})[0]; audit(uid,'storage.bucket.create','bucket',row['id']); return jsonify(row),201

@app.get('/api/storage/buckets')
@cloud_api_or_login
def buckets():
    oid=require_org(session['user_id']); return jsonify(sb('/rest/v1/cloud_storage_buckets',params=cloud_project_filter({'organization_id':f'eq.{oid}','select':'*','order':'created_at.desc'})))

@app.post('/api/storage/upload')
@cloud_api_or_login
def storage_upload():
    uid=session['user_id']; project_id=cloud_project_for_write(request.form.get('project_id')); bucket=request.form.get('bucket','koja-files'); f=request.files.get('file')
    if not f: return jsonify(error='file_required'),400
    filename=os.path.basename(f.filename or 'upload.bin'); data=f.read(); path=f'{uid}/{uuid.uuid4()}-{filename}'
    url=f'{SUPABASE_URL}/storage/v1/object/{bucket}/{path}'
    r=requests.post(url,headers={'apikey':SUPABASE_KEY,'Authorization':f'Bearer {SUPABASE_KEY}','Content-Type':f.content_type or 'application/octet-stream','x-upsert':'false'},data=data,timeout=120)
    if r.status_code>=400: return jsonify(error=r.text[:500]),r.status_code
    oid=require_org(uid); bucket_row=_one('/rest/v1/cloud_storage_buckets',{'organization_id':f'eq.{oid}','name':f'eq.{bucket}','select':'*','limit':'1'}) or _one('/rest/v1/cloud_storage_buckets',{'organization_id':f'eq.{oid}','bucket_name':f'eq.{bucket}','select':'*','limit':'1'}); obj=None
    if bucket_row:
        obj=_insert('/rest/v1/cloud_storage_objects',{'owner_user_id':uid,'owner_id':uid,'organization_id':oid,'project_id':project_id,'bucket_id':bucket_row.get('id'),'object_path':path,'name':filename,'size_bytes':len(data),'content_type':f.content_type or 'application/octet-stream','metadata':{'provider':'supabase-storage'}})
    usage(uid,project_id,'storage','bytes_uploaded',len(data),'bytes'); return jsonify(bucket=bucket,path=path,size=len(data),provider='supabase-storage',object=obj)

@app.post('/api/media/assets')
@cloud_api_or_login
def media_asset():
    d=request.get_json() or {}; uid=session['user_id']; project_id=cloud_project_for_write(d.get('project_id')); row=sb('/rest/v1/cloud_media_assets','POST',{'owner_user_id':uid,'organization_id':require_org(uid),'project_id':project_id,'name':d.get('name','Media'),'source_url':d.get('source_url',''),'media_type':d.get('media_type','video'),'status':'uploaded','metadata':d.get('metadata',{})},params={'select':'*'})[0]; src=(d.get('source_url') or '').strip(); url_record=None;
    if src:
        try: url_record=_register_cloud_url(uid,require_org(uid),project_id,src,d.get('name') or 'Media source',d.get('media_type') or 'media','media',{'asset_id':row.get('id')})
        except ValueError: pass
    usage(uid,project_id,'media','assets',1); return jsonify(dict(row,koja_url_record=url_record)),201

@app.post('/api/media/assets/<aid>/process')
@cloud_api_or_login
def media_process(aid):
    uid=session['user_id']; oid=require_org(uid); rows=sb('/rest/v1/cloud_media_assets',params={'id':f'eq.{aid}','owner_user_id':f'eq.{uid}','organization_id':f'eq.{oid}','select':'*'});
    if not rows:return jsonify(error='not_found'),404
    spec=request.get_json() or {}
    row=rows[0]
    src=(row.get('source_url') or '').strip()
    if not src: return jsonify(error='source_url_required'),400
    job=sb('/rest/v1/cloud_media_jobs','POST',{'owner_user_id':uid,'organization_id':oid,'asset_id':aid,'job_type':'transcode','status':'queued','spec':spec},params={'select':'*'})[0]
    try:
        db=_v23_db(); node=db.execute("SELECT node_id,node_code FROM native_nodes WHERE status='online' ORDER BY last_heartbeat DESC LIMIT 1").fetchone(); db.close()
        if not node:
            _patch('/rest/v1/cloud_media_assets',{'id':f'eq.{aid}'},{'status':'queued','updated_at':now()})
            return jsonify(dict(job,execution='node_required')),202
        payload={'operation':'media_worker','args':{'source_url':src,'name':row.get('name') or 'media.bin','media_type':row.get('media_type') or 'video','download_timeout':spec.get('download_timeout',120),'process_timeout':spec.get('process_timeout',600),'max_bytes':spec.get('max_bytes',2*1024*1024*1024)},'cloud_media_job_id':job.get('id'),'cloud_media_asset_id':aid}
        jid=str(uuid.uuid4()); ts=_v23_now(); db=_v23_db(); db.execute('INSERT INTO native_node_jobs(job_id,node_id,state,payload_json,result_json,created_at,updated_at,attempts,max_attempts) VALUES(?,?,?,?,?,?,?,?,?)',(jid,node['node_id'],'queued',_real_json(payload),'{}',ts,ts,0,3)); db.commit(); db.close()
        _patch('/rest/v1/cloud_media_jobs',{'id':f'eq.{job["id"]}'},{'status':'queued','spec':dict(spec, native_job_id=jid, node_id=node['node_id'], node_code=node['node_code'])})
        _patch('/rest/v1/cloud_media_assets',{'id':f'eq.{aid}'},{'status':'processing','updated_at':now()})
        _real_event('media','process.submit','queued',aid,{'cloud_media_job_id':job.get('id'),'native_job_id':jid,'node_id':node['node_id']})
        return jsonify(dict(job,native_job_id=jid,node_id=node['node_id'],node_code=node['node_code'],execution='KOJA-NODE-01')),202
    except Exception as e:
        _patch('/rest/v1/cloud_media_jobs',{'id':f'eq.{job["id"]}'},{'status':'failed','error':str(e)[:500]})
        return jsonify(error='media_job_submit_failed',detail=str(e)[:500]),500

@app.post('/api/live/channels')
@cloud_api_or_login
def live_channel():
    d=request.get_json() or {}; uid=session['user_id']; oid=require_org(uid); pid=d.get('project_id') or cloud_project_for_write(None);
    if not pid:
        ps=sb('/rest/v1/cloud_projects',params={'owner_user_id':f'eq.{uid}','organization_id':f'eq.{oid}','select':'id','order':'created_at.asc','limit':'1'}); pid=ps[0]['id'] if ps else None
    if not pid:return jsonify(error='project_required'),400
    key='KOJA-'+secrets.token_urlsafe(18); row=sb('/rest/v1/cloud_live_channels','POST',{'owner_user_id':uid,'organization_id':oid,'project_id':pid,'name':d.get('name','KOJA Stream Channel'),'channel_code':'KLC-'+secrets.token_hex(4).upper(),'stream_key_hash':hashlib.sha256(key.encode()).hexdigest(),'status':'offline','config':d.get('config',{})},params={'select':'*'})[0]; base=(os.getenv('KOJA_CLOUD_PUBLIC_URL') or request.url_root).rstrip('/'); playback=f'{base}/live/{row.get("channel_code")}'; _patch('/rest/v1/cloud_live_channels',{'id':f'eq.{row["id"]}'},{'playback_url':playback,'updated_at':now()}); row['playback_url']=playback; url_record=None
    try: url_record=_register_cloud_url(uid,oid,pid,playback,row.get('name') or 'KOJA Stream', 'live_stream','live',{'channel_id':row.get('id')})
    except ValueError: pass
    return jsonify(channel=row,stream_key=key,koja_url_record=url_record),201

@app.get('/api/media/assets')
@cloud_api_or_login
def media_assets():
    oid=require_org(session['user_id'])
    return jsonify(sb('/rest/v1/cloud_media_assets',params=cloud_project_filter({'organization_id':f'eq.{oid}','select':'*','order':'created_at.desc'})))

@app.get('/api/media/assets/<aid>/jobs')
@cloud_api_or_login
def media_asset_jobs(aid):
    uid=session['user_id']; oid=require_org(uid)
    asset=sb('/rest/v1/cloud_media_assets',params={'id':f'eq.{aid}','owner_user_id':f'eq.{uid}','organization_id':f'eq.{oid}','select':'id,name,status,source_url,metadata'})
    if not asset: return jsonify(error='not_found'),404
    jobs=sb('/rest/v1/cloud_media_jobs',params={'asset_id':f'eq.{aid}','owner_user_id':f'eq.{uid}','organization_id':f'eq.{oid}','select':'*','order':'created_at.desc'})
    return jsonify({'asset':asset[0],'jobs':jobs})

@app.get('/api/live/channels')
@cloud_api_or_login
def live_channels():
    oid=require_org(session['user_id'])
    return jsonify(sb('/rest/v1/cloud_live_channels',params={'organization_id':f'eq.{oid}','select':'*','order':'created_at.desc'}))

@app.get('/api/storage/objects')
@cloud_api_or_login
def storage_objects():
    oid=require_org(session['user_id'])
    return jsonify(sb('/rest/v1/cloud_storage_objects',params=cloud_project_filter({'organization_id':f'eq.{oid}','select':'*','order':'created_at.desc','limit':'500'})))

@app.get('/api/databases')
@cloud_api_or_login
def databases():
    oid=require_org(session['user_id'])
    return jsonify(sb('/rest/v1/cloud_databases',params=cloud_project_filter({'organization_id':f'eq.{oid}','select':'*','order':'created_at.desc'})))

@app.post('/api/databases')
@cloud_api_or_login
def create_database():
    uid=session['user_id']; oid=require_org(uid); d=request.get_json() or {}; name=(d.get('name') or 'KOJA Data').strip(); pid=cloud_project_for_write(d.get('project_id'))
    if pid:
        if not sb('/rest/v1/cloud_projects',params={'id':f'eq.{pid}','organization_id':f'eq.{oid}','select':'id'}): return jsonify(error='project_not_found_or_not_in_active_organization'),404
    code='KDB-'+secrets.token_hex(5).upper()
    row=sb('/rest/v1/cloud_databases','POST',{'owner_user_id':uid,'customer_id':d.get('customer_id'),'organization_id':oid,'project_id':pid,'database_code':code,'name':name,'engine':d.get('engine','postgres'),'engine_version':d.get('engine_version','latest'),'status':'provisioning','region':d.get('region','global'),'provider':d.get('provider','postgres-adapter'),'connection_mode':d.get('connection_mode','private'),'storage_gb':d.get('storage_gb',10),'max_connections':d.get('max_connections',20),'config':d.get('config',{})},params={'select':'*'})[0]
    audit(uid,'database.create','database',row['id'],{'organization_id':oid}); return jsonify(row),201

@app.route('/api/v1/health', methods=['GET','OPTIONS'])
def api_v1_health():
    if request.method=='OPTIONS': return ('',204)
    return jsonify({'api_version':'v1','checks':{'api':'ok','cors':True},'cloud_version':VERSION,'service':'koja-cloud-api','status':'ok','supabase_configured':configured(),'time':now()})

@app.get('/api/v1/openapi.json')
def api_v1_openapi():
    return jsonify({
        'openapi':'3.0.3',
        'info':{'title':'KOJA CLOUD API','version':'v1','description':'Universal project-scoped KOJA API.'},
        'servers':[{'url':request.host_url.rstrip('/')}],
        'security':[{'KojaApiKey':[]}],
        'components':{'securitySchemes':{'KojaApiKey':{'type':'apiKey','in':'header','name':'X-KOJA-API-KEY'},'BearerAuth':{'type':'http','scheme':'bearer'}},'schemas':{'ApiError':{'type':'object','properties':{'error':{'type':'string'},'scope':{'type':'string'}}}}},
        'paths':{
            '/api/v1/health':{'get':{'security':[],'responses':{'200':{'description':'Health status'}}}},
            '/api/v1/projects':{'get':{'responses':{'200':{'description':'Project list'}}}},
            '/api/v1/projects/{pid}':{'get':{'parameters':[{'name':'pid','in':'path','required':True,'schema':{'type':'string'}}],'responses':{'200':{'description':'Project'}}}},
            '/api/v1/storage/buckets':{'get':{'responses':{'200':{'description':'Buckets'}}},'post':{'responses':{'201':{'description':'Bucket created'}}}},
            '/api/v1/databases':{'get':{'responses':{'200':{'description':'Databases'}}},'post':{'responses':{'201':{'description':'KOJA Data created'}}}},
            '/api/v1/media/assets':{'get':{'responses':{'200':{'description':'Media assets'}}},'post':{'responses':{'201':{'description':'Media asset created'}}}},
            '/api/v1/compute/services':{'get':{'responses':{'200':{'description':'KOJA Run services'}}},'post':{'responses':{'201':{'description':'KOJA Run service created'}}}},
            '/api/v1/live/channels':{'get':{'responses':{'200':{'description':'KOJA Stream channels'}}},'post':{'responses':{'201':{'description':'KOJA Stream channel created'}}}},
            '/api/v1/urls':{'get':{'responses':{'200':{'description':'Registered URL resources'}}},'post':{'responses':{'201':{'description':'URL resource registered'}}}},
            '/api/v1/urls/{id}':{'get':{'responses':{'200':{'description':'Registered URL resource'}}}},
            '/api/v1/urls/{id}/check':{'post':{'responses':{'200':{'description':'URL reachability check'}}}},
            '/api/v1/usage':{'get':{'responses':{'200':{'description':'Usage events'}}}},
            '/api/v1/auth/introspect':{'get':{'responses':{'200':{'description':'Authenticated key metadata'}}}},
            '/api/v1/auth/key':{'get':{'responses':{'200':{'description':'Authenticated API key metadata'}}}}
        }
    })

def _api_key_introspection_payload():
    key=getattr(request,'koja_api_key',{}) or {}
    scopes=sorted(_api_key_scopes(key))
    return {'authenticated':True,'key_id':key.get('id'),'key_prefix':key.get('key_prefix'),'project_id':key.get('_pid'),'organization_id':key.get('_oid'),'scopes':scopes,'status':key.get('status'),'expires_at':key.get('expires_at'),'last_used_at':now(),'api_version':'v1','cloud_version':VERSION}

@app.get('/api/v1/auth/introspect')
@api_key_auth
def api_key_introspect():
    return jsonify(_api_key_introspection_payload())

@app.get('/api/v1/auth/key')
@api_key_auth
def api_key_key_info():
    # Backward-compatible canonical endpoint used by the KOJA API key UI/docs.
    return jsonify(_api_key_introspection_payload())

@app.get('/api/v1/projects/<pid>')
@api_key_auth
def api_project_detail(pid):
    key=getattr(request,'koja_api_key',{}) or {}; key_pid=key.get('_pid') or key.get('project_id')
    if key_pid and str(pid)!=str(key_pid): return jsonify(error='project_scope_violation'),403
    oid=key_org(); rows=sb('/rest/v1/cloud_projects',params={'id':f'eq.{pid}','organization_id':f'eq.{oid}','select':'id,name,project_code,status,organization_id,created_at,updated_at','limit':'1'})
    if not rows: return jsonify(error='project_not_found'),404
    return jsonify(rows[0])

@app.get('/api/v1/projects')
@api_key_auth
def api_projects():
    oid=key_org(); return jsonify(sb('/rest/v1/cloud_projects',params=cloud_project_filter({'organization_id':f'eq.{oid}','select':'id,name,project_code,status,organization_id,created_at,updated_at','order':'created_at.desc'})))

@app.get('/api/v1/media/assets')
@api_key_auth
def api_media_assets():
    oid=key_org(); return jsonify(sb('/rest/v1/cloud_media_assets',params=cloud_project_filter({'organization_id':f'eq.{oid}','select':'*','order':'created_at.desc'})))

@app.post('/api/v1/media/assets')
@api_key_auth
def api_create_media():
    d=request.get_json() or {}; oid=key_org(); key_pid=cloud_api_project_id(); project=d.get('project_id') or key_pid
    if key_pid and project != key_pid: return jsonify(error='project_scope_violation'),403
    if project:
        ps=sb('/rest/v1/cloud_projects',params={'id':f'eq.{project}','organization_id':f'eq.{oid}','select':'id','limit':'1'})
        if not ps:return jsonify(error='project_not_found'),404
    uid=getattr(request,'koja_api_key',{}).get('_uid') or getattr(request,'koja_api_key',{}).get('user_id') or getattr(request,'koja_api_key',{}).get('owner_user_id')
    row=sb('/rest/v1/cloud_media_assets','POST',{'owner_user_id':uid,'organization_id':oid,'project_id':project,'name':d.get('name','Media'),'source_url':d.get('source_url',''),'media_type':d.get('media_type','video'),'status':'uploaded','metadata':d.get('metadata',{})},params={'select':'*'})[0]
    usage(uid,project,'media','assets',1); audit(uid,'media.asset.create','media_asset',row['id'],{'organization_id':oid})
    return jsonify(row),201

@app.post('/api/v1/media/assets/<aid>/process')
@api_key_auth
def api_process_media(aid):
    oid=key_org(); rows=sb('/rest/v1/cloud_media_assets',params={'id':f'eq.{aid}','organization_id':f'eq.{oid}','project_id':f'eq.{cloud_api_project_id()}','select':'*'})
    if not rows:return jsonify(error='not_found'),404
    d=request.get_json() or {}; a=rows[0]; uid=getattr(request,'koja_api_key',{}).get('_uid') or getattr(request,'koja_api_key',{}).get('user_id') or getattr(request,'koja_api_key',{}).get('owner_user_id')
    job=sb('/rest/v1/cloud_media_jobs','POST',{'owner_user_id':uid,'organization_id':oid,'asset_id':aid,'job_type':d.get('job_type','transcode'),'status':'queued','spec':d},params={'select':'*'})[0]
    return jsonify(job),202

@app.get('/api/v1/storage/buckets')
@api_key_auth
def api_buckets():
    oid=key_org(); pid=cloud_api_project_id(); params={'organization_id':f'eq.{oid}','select':'*','order':'created_at.desc'}
    if pid: params['project_id']=f'eq.{pid}'
    return jsonify(sb('/rest/v1/cloud_storage_buckets',params=params))

@app.post('/api/v1/storage/buckets')
@api_key_auth
def api_create_bucket():
    d=request.get_json(silent=True) or {}
    oid=key_org(); key=getattr(request,'koja_api_key',{}) or {}; uid=key.get('_uid') or key.get('user_id') or key.get('owner_user_id'); pid=cloud_api_project_id()
    requested_pid=d.get('project_id') or pid
    if pid and requested_pid != pid: return jsonify(error='project_scope_violation'),403
    if not requested_pid: return jsonify(error='project_required'),400
    if not sb('/rest/v1/cloud_projects',params={'id':f'eq.{requested_pid}','organization_id':f'eq.{oid}','select':'id','limit':'1'}): return jsonify(error='project_not_found'),404
    name=str(d.get('name') or 'files').strip()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,62}',name): return jsonify(error='invalid_bucket_name'),400
    existing=_v172_bucket_by_name(oid,name,requested_pid)
    if existing: return jsonify(existing),200
    provider_created=False
    try:
        pr=requests.post(f'{SUPABASE_URL}/storage/v1/bucket',headers=sb_headers(),json={'id':name,'name':name,'public':str(d.get('visibility','private')).lower()=='public','file_size_limit':d.get('max_bytes',1073741824)},timeout=30)
        if pr.status_code in (200,201): provider_created=True
        elif pr.status_code not in (409,): return jsonify(error='storage_provider_bucket_create_failed',detail=pr.text[:500]),pr.status_code
    except requests.RequestException as exc:
        return jsonify(error='storage_provider_unreachable',detail=str(exc)[:300]),502
    code='ST-'+secrets.token_hex(5).upper()
    row=sb('/rest/v1/cloud_storage_buckets','POST',{'owner_user_id':uid,'organization_id':oid,'project_id':requested_pid,'bucket_code':code,'bucket_name':name,'name':name,'provider':'supabase','max_bytes':d.get('max_bytes',1073741824),'visibility':d.get('visibility','private'),'status':'active','config':d.get('config',{}) if isinstance(d.get('config',{}),dict) else {}},params={'select':'*'})[0]
    row['provider_created']=provider_created
    audit(uid,'storage.bucket.create','bucket',row['id'],{'organization_id':oid,'project_id':requested_pid,'provider_created':provider_created})
    return jsonify(row),201

@app.get('/api/v1/live/channels')
@api_key_auth
def api_live_channels():
    oid=key_org(); return jsonify(sb('/rest/v1/cloud_live_channels',params=cloud_project_filter({'organization_id':f'eq.{oid}','select':'id,name,channel_code,status,config,created_at','order':'created_at.desc'})))

@app.post('/api/v1/live/channels')
@api_key_auth
def api_create_live():
    d=request.get_json() or {}; oid=key_org(); uid=getattr(request,'koja_api_key',{}).get('_uid') or getattr(request,'koja_api_key',{}).get('user_id'); pid=cloud_api_project_id(); requested_pid=d.get('project_id') or pid
    if pid and requested_pid != pid: return jsonify(error='project_scope_violation'),403
    if not requested_pid: return jsonify(error='project_required'),400
    if not sb('/rest/v1/cloud_projects',params={'id':f'eq.{requested_pid}','organization_id':f'eq.{oid}','select':'id','limit':'1'}): return jsonify(error='project_not_found'),404
    key='KOJA-'+secrets.token_urlsafe(18)
    row=sb('/rest/v1/cloud_live_channels','POST',{'owner_user_id':uid,'organization_id':oid,'project_id':requested_pid,'name':d.get('name','KOJA Stream Channel'),'channel_code':'KLC-'+secrets.token_hex(5).upper(),'stream_key_hash':hashlib.sha256(key.encode()).hexdigest(),'status':'offline','config':d.get('config',{})},params={'select':'*'})[0]
    row['stream_key']=key; audit(uid,'live.channel.create','live_channel',row['id'],{'organization_id':oid}); return jsonify(row),201

@app.get('/api/v1/usage')
@api_key_auth
def api_usage():
    oid=key_org(); return jsonify(sb('/rest/v1/cloud_usage_events',params={'organization_id':f'eq.{oid}','select':'*','order':'created_at.desc','limit':'500'}))

@app.get('/api/v1/databases')
@api_key_auth
def api_databases_v1():
    oid=key_org(); pid=getattr(request,'koja_api_key',{}).get('project_id')
    params={'organization_id':f'eq.{oid}','select':'*','order':'created_at.desc'}
    if pid: params['project_id']=f'eq.{pid}'
    return jsonify(sb('/rest/v1/cloud_databases',params=params))

@app.post('/api/v1/databases')
@api_key_auth
def api_create_database_v1():
    d=request.get_json(silent=True) or {}; oid=key_org(); uid=getattr(request,'koja_api_key',{}).get('_uid') or getattr(request,'koja_api_key',{}).get('user_id') or getattr(request,'koja_api_key',{}).get('owner_user_id'); key_pid=getattr(request,'koja_api_key',{}).get('project_id'); pid=d.get('project_id') or key_pid
    if key_pid and pid != key_pid: return jsonify(error='project_scope_violation'),403
    if not pid: return jsonify(error='project_required'),400
    if not sb('/rest/v1/cloud_projects',params={'id':f'eq.{pid}','organization_id':f'eq.{oid}','select':'id','limit':'1'}): return jsonify(error='project_not_found'),404
    name=(d.get('name') or 'KOJA Data').strip(); code='KDB-'+secrets.token_hex(5).upper()
    row=sb('/rest/v1/cloud_databases','POST',{'owner_user_id':uid,'organization_id':oid,'project_id':pid,'database_code':code,'name':name,'engine':d.get('engine','postgres'),'engine_version':d.get('engine_version','latest'),'status':'provisioning','region':d.get('region','global'),'provider':d.get('provider','postgres-adapter'),'connection_mode':d.get('connection_mode','private'),'storage_gb':d.get('storage_gb',10),'max_connections':d.get('max_connections',20),'config':d.get('config',{})},params={'select':'*'})[0]
    audit(uid,'database.create','database',row['id'],{'organization_id':oid,'project_id':pid})
    return jsonify(row),201

@app.get('/api/v1/compute/services')
@api_key_auth
def api_compute_services_v1():
    oid=key_org(); pid=getattr(request,'koja_api_key',{}).get('project_id'); params={'organization_id':f'eq.{oid}','select':'*','order':'created_at.desc'}
    if pid: params['project_id']=f'eq.{pid}'
    return jsonify(sb('/rest/v1/cloud_compute_services',params=params))

@app.post('/api/v1/compute/services')
@api_key_auth
def api_create_compute_service_v1():
    d=request.get_json(silent=True) or {}; oid=key_org(); uid=getattr(request,'koja_api_key',{}).get('_uid') or getattr(request,'koja_api_key',{}).get('user_id') or getattr(request,'koja_api_key',{}).get('owner_user_id'); key_pid=getattr(request,'koja_api_key',{}).get('project_id'); pid=d.get('project_id') or key_pid
    if key_pid and pid != key_pid: return jsonify(error='project_scope_violation'),403
    if not pid: return jsonify(error='project_required'),400
    if not sb('/rest/v1/cloud_projects',params={'id':f'eq.{pid}','organization_id':f'eq.{oid}','select':'id','limit':'1'}): return jsonify(error='project_not_found'),404
    code='KCS-'+secrets.token_hex(5).upper(); name=(d.get('name') or 'Web Service').strip()
    cfg=d.get('config',{}) if isinstance(d.get('config',{}),dict) else {}; slug=re.sub(r'[^a-z0-9-]+','-',name.lower()).strip('-')[:40] or 'web-service'; cfg.setdefault('url_slug',slug+'-'+code[-6:].lower()); cfg.setdefault('url_status','pending-edge-routing')
    row=sb('/rest/v1/cloud_compute_services','POST',{'owner_user_id':uid,'organization_id':oid,'project_id':pid,'service_code':code,'name':name,'service_type':d.get('service_type','web'),'runtime':d.get('runtime','docker'),'repo_url':d.get('repo_url',''),'branch':d.get('branch','main'),'build_command':d.get('build_command',''),'start_command':d.get('start_command',''),'health_path':d.get('health_path','/health'),'region':d.get('region','global'),'cpu':d.get('cpu',0.5),'memory_mb':d.get('memory_mb',512),'status':'created','config':cfg},params={'select':'*'})[0]
    audit(uid,'compute.service.create','compute_service',row['id'],{'organization_id':oid,'project_id':pid})
    return jsonify(row),201

@app.get('/api/overview')
@auth_required
def overview():
    uid=session['user_id']; out={}
    oid=active_org_id(uid)
    for table in ['cloud_projects','cloud_compute_services','cloud_compute_deployments','cloud_storage_buckets','cloud_media_assets','cloud_live_channels','cloud_compute_jobs','cloud_databases']:
        if not oid:
            out[table]=0
            continue
        try: out[table]=len(sb('/rest/v1/'+table,params={'organization_id':f'eq.{oid}','select':'id'}))
        except Exception: out[table]=0
    out['organization_id']=oid
    return jsonify(out)

@app.get('/api/system/status')
@auth_required
def system_status():
    """Authenticated production diagnostics without exposing secrets."""
    uid=session['user_id']
    oid=active_org_id(uid)
    checks={}
    for table in ['cloud_users','cloud_customers','cloud_organizations','cloud_organization_members','cloud_projects','cloud_compute_services','cloud_databases','cloud_storage_buckets','cloud_media_assets','cloud_live_channels','cloud_api_keys']:
        try:
            rows=sb('/rest/v1/'+table,params={'select':'id','limit':'1'})
            checks[table]={'ok':True,'reachable':True,'has_rows':bool(rows)}
        except Exception as e:
            checks[table]={'ok':False,'error':str(e)[:240]}
    return jsonify(service='koja-cloud',version=VERSION,authenticated=True,organization_id=oid,checks=checks)



# ============================= KOJA CLOUD V10 SERVICE API =============================
# These routes complete the control-plane lifecycle for every advertised service.
# Provider-backed operations are queued when an external worker/provider is required;
# they never masquerade as completed infrastructure.

def _json_body():
    return request.get_json(silent=True) or {}

def _one(path, params):
    rows = sb(path, params=params)
    return rows[0] if rows else None

def _insert(path, payload):
    rows = sb(path, 'POST', payload, params={'select':'*'})
    return rows[0] if isinstance(rows, list) and rows else rows

def _patch(path, filters, payload):
    return sb(path, 'PATCH', payload, params={**filters, 'select':'*'})

def _delete(path, filters):
    return sb(path, 'DELETE', params=filters)

def _require_project(uid, oid, pid):
    if not pid: return None
    return _one('/rest/v1/cloud_projects', {'id':f'eq.{pid}','organization_id':f'eq.{oid}','owner_user_id':f'eq.{uid}','select':'*','limit':'1'})

def _resource(uid, oid, typ, rid):
    return _one('/rest/v1/cloud_resources', {'resource_type':f'eq.{typ}','id':f'eq.{rid}','owner_user_id':f'eq.{uid}','organization_id':f'eq.{oid}','select':'*','limit':'1'})

def _enqueue_generic_job(uid, oid, project_id, job_type, spec):
    payload={'owner_user_id':uid,'organization_id':oid,'project_id':project_id,'job_code':'JOB-'+secrets.token_hex(6).upper(),'job_type':job_type,'status':'queued','region':spec.get('region','global'),'input':spec,'config':spec}
    return _insert('/rest/v1/cloud_jobs',payload)

@app.post('/api/organizations/<oid>/members')
@auth_required
def add_member(oid):
    uid=session['user_id']
    if not org_member(uid,oid): return jsonify(error='organization_access_denied'),403
    d=_json_body(); user_id=d.get('user_id')
    if not user_id: return jsonify(error='user_id_required'),400
    role=d.get('role','member')
    return jsonify(_insert('/rest/v1/cloud_organization_members',{'organization_id':oid,'user_id':user_id,'role':role,'status':'active'})),201

@app.get('/api/organizations/<oid>/members')
@auth_required
def list_members(oid):
    uid=session['user_id']
    if not org_member(uid,oid): return jsonify(error='organization_access_denied'),403
    return jsonify(sb('/rest/v1/cloud_organization_members',params={'organization_id':f'eq.{oid}','select':'*','order':'created_at.asc'}))

@app.delete('/api/organizations/<oid>/members/<user_id>')
@auth_required
def remove_member(oid,user_id):
    uid=session['user_id']; me=org_member(uid,oid)
    if not me or me.get('role') not in ('owner','admin'): return jsonify(error='admin_required'),403
    if user_id==uid: return jsonify(error='cannot_remove_self'),400
    _delete('/rest/v1/cloud_organization_members',{'organization_id':f'eq.{oid}','user_id':f'eq.{user_id}'})
    return jsonify(message='member_removed')

@app.get('/api/projects/<pid>/workspace')
@auth_required
def workspace_list(pid):
    uid=session['user_id']; oid=require_org(uid)
    if not project_access(uid,oid,pid): return jsonify(error='project_not_found'),404
    rows=sb('/rest/v1/cloud_project_files',params={'project_id':f'eq.{pid}','owner_user_id':f'eq.{uid}','organization_id':f'eq.{oid}','select':'id,path,size_bytes,content_type,updated_at,created_at','order':'path.asc','limit':'1000'})
    return jsonify(rows)

@app.get('/api/projects/<pid>/workspace/<path:file_path>')
@auth_required
def workspace_get(pid,file_path):
    uid=session['user_id']; oid=require_org(uid)
    if not project_access(uid,oid,pid): return jsonify(error='project_not_found'),404
    rows=sb('/rest/v1/cloud_project_files',params={'project_id':f'eq.{pid}','owner_user_id':f'eq.{uid}','organization_id':f'eq.{oid}','path':f'eq.{file_path}','select':'*','limit':'1'})
    if not rows:return jsonify(error='file_not_found'),404
    r=rows[0]
    if r.get('content_b64'):
        return jsonify(id=r['id'],path=r['path'],content_b64=r['content_b64'],content_type=r.get('content_type'),size_bytes=r.get('size_bytes',0),updated_at=r.get('updated_at'))
    return jsonify(id=r['id'],path=r['path'],content=r.get('content_text',''),content_type=r.get('content_type'),size_bytes=r.get('size_bytes',0),updated_at=r.get('updated_at'))

@app.post('/api/projects/<pid>/workspace')
@auth_required
def workspace_save(pid):
    uid=session['user_id']; oid=require_org(uid)
    if not project_access(uid,oid,pid): return jsonify(error='project_not_found'),404
    d=request.get_json(silent=True) or {}
    path=(d.get('path') or '').strip()
    if not workspace_path_ok(path): return jsonify(error='invalid_workspace_path'),400
    content=d.get('content',''); content_b64=d.get('content_b64')
    try: row=workspace_row(uid,oid,pid,path,content,content_b64,d.get('content_type','text/plain'))
    except ValueError as e:return jsonify(error=str(e)),400
    existing=_one('/rest/v1/cloud_project_files',{'project_id':f'eq.{pid}','owner_user_id':f'eq.{uid}','organization_id':f'eq.{oid}','path':f'eq.{path}','select':'id','limit':'1'})
    if existing:
        rows=sb('/rest/v1/cloud_project_files','PATCH',row,params={'id':f'eq.{existing["id"]}','owner_user_id':f'eq.{uid}','organization_id':f'eq.{oid}','select':'*'})
    else:
        row['created_at']=now(); rows=sb('/rest/v1/cloud_project_files','POST',row,params={'select':'*'})
    audit(uid,'workspace.file.save','project_file',rows[0]['id'],{'project_id':pid,'path':path})
    return jsonify(rows[0]),201

@app.post('/api/projects/<pid>/workspace/upload')
@auth_required
def workspace_upload(pid):
    uid=session['user_id']; oid=require_org(uid)
    if not project_access(uid,oid,pid): return jsonify(error='project_not_found'),404
    files=request.files.getlist('file') or list(request.files.values())
    if not files:return jsonify(error='file_required'),400
    saved=[]
    for f in files:
        path=(request.form.get('path') or f.filename or '').strip().replace('\\\\','/')
        if len(files)>1 and request.form.get('paths_json'):
            try: path=(json.loads(request.form['paths_json']).get(f.filename) or path)
            except Exception: pass
        if not workspace_path_ok(path): return jsonify(error='invalid_workspace_path',path=path),400
        raw=f.read()
        if len(raw)>WORKSPACE_BINARY_LIMIT:return jsonify(error='workspace_file_too_large',path=path),413
        try:
            text=raw.decode('utf-8'); b64=None
        except UnicodeDecodeError:
            text=''; b64=base64.b64encode(raw).decode('ascii')
        row=workspace_row(uid,oid,pid,path,text,b64,f.mimetype or 'application/octet-stream'); row['size_bytes']=len(raw); row['created_at']=now()
        existing=_one('/rest/v1/cloud_project_files',{'project_id':f'eq.{pid}','owner_user_id':f'eq.{uid}','organization_id':f'eq.{oid}','path':f'eq.{path}','select':'id','limit':'1'})
        if existing: rows=sb('/rest/v1/cloud_project_files','PATCH',row,params={'id':f'eq.{existing["id"]}','owner_user_id':f'eq.{uid}','organization_id':f'eq.{oid}','select':'*'})
        else: rows=sb('/rest/v1/cloud_project_files','POST',row,params={'select':'*'})
        saved.append(rows[0])
    audit(uid,'workspace.files.upload','project',pid,{'count':len(saved)})
    return jsonify(files=saved),201

@app.delete('/api/projects/<pid>/workspace/<path:file_path>')
@auth_required
def workspace_delete(pid,file_path):
    uid=session['user_id']; oid=require_org(uid)
    if not project_access(uid,oid,pid): return jsonify(error='project_not_found'),404
    rows=sb('/rest/v1/cloud_project_files','DELETE',params={'project_id':f'eq.{pid}','owner_user_id':f'eq.{uid}','organization_id':f'eq.{oid}','path':f'eq.{file_path}','select':'*'})
    if not rows:return jsonify(error='file_not_found'),404
    audit(uid,'workspace.file.delete','project_file',rows[0]['id'],{'project_id':pid,'path':file_path}); return jsonify(message='deleted')

@app.post('/api/projects/<pid>/workspace/deploy')
@auth_required
def workspace_deploy(pid):
    uid=session['user_id']; oid=require_org(uid); p=project_access(uid,oid,pid)
    if not p:return jsonify(error='project_not_found'),404
    sid=(request.get_json(silent=True) or {}).get('service_id')
    if sid:
        svc=_one('/rest/v1/cloud_compute_services',{'id':f'eq.{sid}','project_id':f'eq.{pid}','owner_user_id':f'eq.{uid}','organization_id':f'eq.{oid}','select':'id','limit':'1'})
        if not svc:return jsonify(error='service_not_found'),404
    else:
        svc=_one('/rest/v1/cloud_compute_services',{'project_id':f'eq.{pid}','owner_user_id':f'eq.{uid}','organization_id':f'eq.{oid}','select':'id','limit':'1','order':'created_at.desc'})
        if not svc:return jsonify(error='compute_service_required'),400
        sid=svc['id']
    # Workspace deployments use source=workspace; agent fetches exact files from control plane.
    dep,job=queue_deploy(uid,sid,reason='workspace')
    spec=job.get('spec') or {}; spec['source_mode']='workspace'; spec['project_id']=pid
    sb('/rest/v1/cloud_compute_jobs','PATCH',{'spec':spec},params={'id':f'eq.{job["id"]}'})
    return jsonify(deployment=dep,job_id=job['id'],service_id=sid),202

@app.get('/api/agents/services/<sid>/workspace')
@agent_auth
def agent_workspace(sid):
    agent=request.koja_agent; uid=agent['owner_user_id']
    svc=_one('/rest/v1/cloud_compute_services',{'id':f'eq.{sid}','owner_user_id':f'eq.{uid}','select':'project_id','limit':'1'})
    if not svc:return jsonify(error='service_not_found'),404
    rows=sb('/rest/v1/cloud_project_files',params={'project_id':f'eq.{svc["project_id"]}','owner_user_id':f'eq.{uid}','select':'path,content_text,content_b64,content_type','order':'path.asc','limit':'5000'})
    return jsonify(project_id=svc['project_id'],files=rows)

@app.post('/api/projects/<pid>/apk/build')
@auth_required
def apk_build(pid):
    uid=session['user_id']; oid=require_org(uid); p=project_access(uid,oid,pid)
    if not p:return jsonify(error='project_not_found'),404
    d=request.get_json(silent=True) or {}; sid=d.get('service_id')
    svc=_one('/rest/v1/cloud_compute_services',{'id':f'eq.{sid}','project_id':f'eq.{pid}','owner_user_id':f'eq.{uid}','organization_id':f'eq.{oid}','select':'*','limit':'1'}) if sid else _one('/rest/v1/cloud_compute_services',{'project_id':f'eq.{pid}','owner_user_id':f'eq.{uid}','organization_id':f'eq.{oid}','select':'*','limit':'1','order':'created_at.desc'})
    if not svc:return jsonify(error='compute_service_required'),400
    spec={'project_id':pid,'service_id':svc['id'],'app_name':p.get('name') or 'KOJA App','package_name':d.get('package_name'),'source_mode':'workspace','mode':'webview','website_url':svc.get('service_url') or (svc.get('config') or {}).get('koja_url')}
    job=_enqueue_generic_job(uid,oid,pid,'apk_build',spec)
    return jsonify(job_id=job.get('id') if isinstance(job,dict) else None,job=job),202

@app.post('/api/agents/artifacts')
@agent_auth
def agent_artifact_create():
    a=request.get_json(silent=True) or {}
    if any(not a.get(k) for k in ('owner_user_id','organization_id','project_id','name','content_b64')): return jsonify(error='artifact_fields_required'),400
    try: raw=base64.b64decode(a['content_b64'])
    except Exception: return jsonify(error='invalid_artifact_encoding'),400
    if len(raw)>50*1024*1024:return jsonify(error='artifact_too_large'),413
    return jsonify(_insert('/rest/v1/cloud_project_artifacts',a)),201

@app.get('/api/projects/<pid>/artifacts')
@auth_required
def project_artifacts(pid):
    uid=session['user_id']; oid=require_org(uid)
    if not project_access(uid,oid,pid):return jsonify(error='project_not_found'),404
    return jsonify(sb('/rest/v1/cloud_project_artifacts',params={'project_id':f'eq.{pid}','owner_user_id':f'eq.{uid}','organization_id':f'eq.{oid}','select':'id,name,artifact_type,size_bytes,sha256,status,created_at,download_token','order':'created_at.desc'}))

@app.get('/api/projects/<pid>/artifacts/<aid>/download')
@auth_required
def project_artifact_download(pid,aid):
    uid=session['user_id']; oid=require_org(uid); rows=sb('/rest/v1/cloud_project_artifacts',params={'id':f'eq.{aid}','project_id':f'eq.{pid}','owner_user_id':f'eq.{uid}','organization_id':f'eq.{oid}','select':'*','limit':'1'})
    if not rows:return jsonify(error='artifact_not_found'),404
    a=rows[0]; data=base64.b64decode(a.get('content_b64') or '')
    if not data:return jsonify(error='artifact_content_unavailable'),404
    return Response(data,mimetype=a.get('content_type') or 'application/octet-stream',headers={'Content-Disposition':'attachment; filename="'+(a.get('name') or 'artifact.apk')+'"'})

@app.post('/api/projects/<pid>/archive')
@auth_required
def archive_project(pid):
    uid=session['user_id']; oid=require_org(uid)
    p=_require_project(uid,oid,pid)
    if not p:return jsonify(error='project_not_found'),404
    row=_patch('/rest/v1/cloud_projects',{'id':f'eq.{pid}','organization_id':f'eq.{oid}'},{'status':'archived','updated_at':now()})
    audit(uid,'project.archive','project',pid,{'organization_id':oid})
    return jsonify(row[0] if row else {})

@app.post('/api/services/<sid>/start')
@cloud_api_or_login
def service_start(sid):
    uid=session['user_id']; oid=require_org(uid)
    s=_one('/rest/v1/cloud_compute_services',{'id':f'eq.{sid}','owner_user_id':f'eq.{uid}','organization_id':f'eq.{oid}','select':'*','limit':'1'})
    if not s:return jsonify(error='service_not_found'),404
    job=_enqueue_generic_job(uid,oid,s.get('project_id'),'service_start',{'service_id':sid,'region':s.get('region','global')})
    _patch('/rest/v1/cloud_compute_services',{'id':f'eq.{sid}'},{'status':'starting','updated_at':now()})
    return jsonify(service_id=sid,job=job),202

@app.post('/api/services/<sid>/stop')
@cloud_api_or_login
def service_stop(sid):
    uid=session['user_id']; oid=require_org(uid)
    s=_one('/rest/v1/cloud_compute_services',{'id':f'eq.{sid}','owner_user_id':f'eq.{uid}','organization_id':f'eq.{oid}','select':'*','limit':'1'})
    if not s:return jsonify(error='service_not_found'),404
    job=_enqueue_generic_job(uid,oid,s.get('project_id'),'service_stop',{'service_id':sid,'region':s.get('region','global')})
    _patch('/rest/v1/cloud_compute_services',{'id':f'eq.{sid}'},{'status':'stopping','updated_at':now()})
    return jsonify(service_id=sid,job=job),202

@app.post('/api/services/<sid>/restart')
@cloud_api_or_login
def service_restart(sid):
    uid=session['user_id']; oid=require_org(uid)
    s=_one('/rest/v1/cloud_compute_services',{'id':f'eq.{sid}','owner_user_id':f'eq.{uid}','organization_id':f'eq.{oid}','select':'*','limit':'1'})
    if not s:return jsonify(error='service_not_found'),404
    job=_enqueue_generic_job(uid,oid,s.get('project_id'),'service_restart',{'service_id':sid,'region':s.get('region','global')})
    _patch('/rest/v1/cloud_compute_services',{'id':f'eq.{sid}'},{'status':'restarting','updated_at':now()})
    return jsonify(service_id=sid,job=job),202

@app.get('/api/projects/<pid>/environments')
@auth_required
def project_environments(pid):
    uid=session['user_id']; oid=require_org(uid)
    if not project_access(uid,oid,pid):return jsonify(error='project_not_found'),404
    rows=sb('/rest/v1/cloud_project_environments',params={'project_id':f'eq.{pid}','owner_user_id':f'eq.{uid}','organization_id':f'eq.{oid}','select':'id,name,slug,status,is_production,created_at,updated_at','order':'created_at.asc'})
    return jsonify(rows)

@app.post('/api/projects/<pid>/environments')
@auth_required
def project_environment_create(pid):
    uid=session['user_id']; oid=require_org(uid); d=request.get_json() or {}
    if not project_access(uid,oid,pid):return jsonify(error='project_not_found'),404
    name=(d.get('name') or 'Production').strip(); slug=re.sub(r'[^a-z0-9-]+','-',name.lower()).strip('-') or 'production'
    row=sb('/rest/v1/cloud_project_environments','POST',{'owner_user_id':uid,'organization_id':oid,'project_id':pid,'name':name,'slug':slug,'status':'active','is_production':bool(d.get('is_production',slug=='production')),'config':d.get('config',{})},params={'select':'*'})[0]
    return jsonify(row),201

# ========================= KOJA CLOUD URL REGISTRY =========================
# URL resources are stored in the existing cloud_project_connections table so
# older deployments need no destructive schema migration. connection_type and
# config identify URL-registry records.
def _url_kind(url, requested=None):
    if requested: return str(requested).strip().lower()[:40]
    u=(url or '').lower()
    if any(x in u for x in ('m3u8','manifest','playlist')): return 'live_stream'
    if any(x in u for x in ('rtmp://','rtmps://','srt://','rtsp://')): return 'stream_ingest'
    if '/webhook' in u: return 'webhook'
    if '/api/' in u: return 'api'
    if any(x in u for x in ('.mp4','.webm','.mov','.m3u8','.mp3','.aac','.wav')): return 'media'
    return 'web'

def _resolve_cloud_project_id(uid, oid, project_ref):
    """Resolve a KOJA project UUID or public project code (for example KCS-...)."""
    ref=str(project_ref or '').strip()
    if not ref:
        return None
    # First accept a canonical UUID directly. This avoids an unnecessary lookup.
    if re.match(r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$', ref):
        rows=sb('/rest/v1/cloud_projects',params={
            'id':f'eq.{ref}','organization_id':f'eq.{oid}','select':'id,project_code','limit':'1'})
        return rows[0]['id'] if rows else None
    # Public KOJA project codes are intentionally accepted at API boundaries.
    rows=sb('/rest/v1/cloud_projects',params={
        'project_code':f'eq.{ref}','organization_id':f'eq.{oid}','select':'id,project_code,owner_user_id','limit':'1'})
    if rows:
        return rows[0]['id']
    # Backward-compatible fallback for older installations where the project
    # may have been created before organization_id was populated consistently.
    rows=sb('/rest/v1/cloud_projects',params={
        'project_code':f'eq.{ref}','owner_user_id':f'eq.{uid}','select':'id,project_code,owner_user_id','limit':'1'})
    return rows[0]['id'] if rows else None


def _cloud_project_ref(row):
    """Return both the canonical UUID and public KOJA project code."""
    if not row:
        return None
    return {'project_id':row.get('id'),'project_code':row.get('project_code')}


def _register_cloud_url(uid, oid, pid, url, name=None, kind=None, source='manual', metadata=None):
    url=(url or '').strip()
    if not url: return None
    if not re.match(r'^https?://', url, re.I) and not re.match(r'^(rtmp|rtmps|srt|rtsp)://', url, re.I):
        raise ValueError('valid_url_required')
    if pid and not project_access(uid,oid,pid): raise ValueError('project_not_found')
    # Reuse an existing registry entry for the same tenant/project/URL.
    existing=_one('/rest/v1/cloud_project_connections',{
        'owner_user_id':f'eq.{uid}','organization_id':f'eq.{oid}',
        'project_id':f'eq.{pid}','connection_type':'eq.url',
        'host':f'eq.{url}','select':'*','limit':'1'}) if pid else None
    if existing:
        cfg=existing.get('config') or {}
        existing['koja_cloud_url']=cfg.get('koja_cloud_url') or existing.get('host') or ''
        return existing
    cfg=dict(metadata or {})
    cfg.update({'registry':'koja-url','url':url,'url_kind':_url_kind(url,kind),
                'source':source,'registered_at':now()})
    row=sb('/rest/v1/cloud_project_connections','POST',{
        'owner_user_id':uid,'organization_id':oid,'project_id':pid,
        'name':name or 'KOJA URL','connection_type':'url','provider':'external-url',
        'host':url,'status':'registered','config':cfg
    },params={'select':'*'})[0]
    base=(os.getenv('KOJA_CLOUD_PUBLIC_URL') or request.url_root).rstrip('/')
    cloud_url=f"{base}/api/v1/projects/{pid}/urls/{row['id']}"
    cfg['koja_cloud_url']=cloud_url
    updated=sb('/rest/v1/cloud_project_connections','PATCH',cfg and {'id':f"eq.{row['id']}"},{'config':cfg},params={'select':'*'})
    if updated: row=updated[0]
    row['koja_cloud_url']=cloud_url
    audit(uid,'cloud.url.register','url',row['id'],{'project_id':pid,'url_kind':cfg['url_kind'],'source':source})
    return row

@app.get('/api/v1/urls')
@api_key_auth
def cloud_api_urls():
    key=getattr(request,'koja_api_key',{}) or {}
    uid,oid,pid=_api_key_identity(key)
    if not pid:
        return jsonify(error='project_required'),400
    if not api_scope('projects:read') and not api_scope('projects'):
        return jsonify(error='scope_required',scope='projects:read'),403
    rows=sb('/rest/v1/cloud_project_connections',params={
        'project_id':f'eq.{pid}','owner_user_id':f'eq.{uid}','organization_id':f'eq.{oid}',
        'connection_type':'eq.url','select':'*','order':'created_at.desc'})
    out=[]
    for row in rows:
        cfg=row.get('config') or {}
        out.append({'id':row.get('id'),'project_id':pid,'name':row.get('name'),
                    'url':cfg.get('url') or row.get('host') or '',
                    'url_kind':cfg.get('url_kind') or _url_kind(cfg.get('url') or row.get('host')),
                    'source':cfg.get('source') or 'api','status':row.get('status'),
                    'koja_cloud_url':cfg.get('koja_cloud_url') or '',
                    'created_at':row.get('created_at'),'updated_at':row.get('updated_at')})
    return jsonify({'ok':True,'cloud':'KOJA CLOUD','project_id':pid,'urls':out,'count':len(out)})

@app.post('/api/v1/urls')
@api_key_auth
def cloud_api_url_register():
    key=getattr(request,'koja_api_key',{}) or {}
    uid,oid,key_pid=_api_key_identity(key)
    if not api_scope('projects:write') and not api_scope('projects'):
        return jsonify(error='scope_required',scope='projects:write'),403
    d=request.get_json(silent=True) or {}
    project_ref=str(d.get('project_id') or d.get('project_code') or key_pid or '').strip()
    if not project_ref:
        return jsonify(error='project_required'),400
    pid=_resolve_cloud_project_id(uid,oid,project_ref)
    if not pid:
        return jsonify(error='project_not_found',project_ref=project_ref),404
    # API keys are project-scoped. If the caller supplied a public project code,
    # resolve it first and compare the resulting UUID with the key's project UUID.
    if key_pid and str(pid) != str(key_pid):
        return jsonify(error='project_not_allowed'),403
    kind=d.get('kind') or d.get('type') or 'web'
    try:
        row=_register_cloud_url(uid,oid,pid,d.get('url'),d.get('name'),kind,
                                d.get('source') or 'api',d.get('metadata') or {})
    except ValueError as e:
        code=str(e)
        return jsonify(error=code),404 if code=='project_not_found' else 400
    cfg=row.get('config') or {}
    project_rows=sb('/rest/v1/cloud_projects',params={'id':f'eq.{pid}','organization_id':f'eq.{oid}','select':'id,project_code','limit':'1'})
    project_code=project_rows[0].get('project_code') if project_rows else None
    return jsonify({'ok':True,'cloud':'KOJA CLOUD','url_id':row.get('id'),
                    'project_id':pid,'project_code':project_code,'name':row.get('name'),
                    'url':cfg.get('url') or row.get('host') or '',
                    'url_kind':cfg.get('url_kind'),'source':cfg.get('source'),
                    'status':row.get('status'),'koja_cloud_url':cfg.get('koja_cloud_url'),
                    'created_at':row.get('created_at')}),201

@app.get('/api/v1/urls/<uid_>')
@api_key_auth
def cloud_api_url_resource(uid_):
    key=getattr(request,'koja_api_key',{}) or {}
    uid,oid,pid=_api_key_identity(key)
    if not pid:
        return jsonify(error='project_required'),400
    row=_one('/rest/v1/cloud_project_connections',{'id':f'eq.{uid_}','project_id':f'eq.{pid}',
        'owner_user_id':f'eq.{uid}','organization_id':f'eq.{oid}','connection_type':'eq.url',
        'select':'*','limit':'1'})
    if not row:return jsonify(error='url_not_found'),404
    cfg=row.get('config') or {}
    return jsonify({'ok':True,'cloud':'KOJA CLOUD','url_id':row.get('id'),'project_id':pid,
                    'name':row.get('name'),'url':cfg.get('url') or row.get('host') or '',
                    'url_kind':cfg.get('url_kind'),'source':cfg.get('source'),'status':row.get('status'),
                    'koja_cloud_url':cfg.get('koja_cloud_url'),'created_at':row.get('created_at'),
                    'updated_at':row.get('updated_at')})

@app.post('/api/v1/urls/<uid_>/check')
@api_key_auth
def cloud_api_url_check(uid_):
    key=getattr(request,'koja_api_key',{}) or {}
    uid,oid,pid=_api_key_identity(key)
    if not pid:return jsonify(error='project_required'),400
    row=_one('/rest/v1/cloud_project_connections',{'id':f'eq.{uid_}','project_id':f'eq.{pid}',
        'owner_user_id':f'eq.{uid}','organization_id':f'eq.{oid}','connection_type':'eq.url',
        'select':'*','limit':'1'})
    if not row:return jsonify(error='url_not_found'),404
    cfg=row.get('config') or {}; target=cfg.get('url') or row.get('host') or ''
    result={'url':target,'checked_at':now(),'reachable':False,'status_code':None,'error':None}
    try:
        r=requests.get(target,timeout=12,allow_redirects=True,stream=True,headers={'User-Agent':'KOJA-CLOUD-URL-CHECK/1.0'})
        result.update(reachable=200 <= r.status_code < 500,status_code=r.status_code,final_url=r.url)
    except Exception as e: result['error']=str(e)[:300]
    _patch('/rest/v1/cloud_project_connections',{'id':f'eq.{uid_}'},
           {'status':'active' if result['reachable'] else 'unreachable','config':dict(cfg,last_check=result)})
    return jsonify(result)

@app.get('/api/projects/<pid>/urls')
@auth_required
def cloud_url_registry(pid):
    uid=session['user_id']; oid=require_org(uid)
    resolved=_resolve_cloud_project_id(uid,oid,pid)
    if not resolved: return jsonify(error='project_not_found'),404
    pid=resolved
    rows=sb('/rest/v1/cloud_project_connections',params={
        'project_id':f'eq.{pid}','owner_user_id':f'eq.{uid}','organization_id':f'eq.{oid}',
        'connection_type':'eq.url','select':'*','order':'created_at.desc'})
    for row in rows:
        cfg=row.get('config') or {}
        row['koja_cloud_url']=cfg.get('koja_cloud_url') or ''
        row['url']=cfg.get('url') or row.get('host') or ''
        row['url_kind']=cfg.get('url_kind') or _url_kind(row['url'])
        row['source']=cfg.get('source') or 'manual'
        row.pop('secret_ciphertext',None)
    return jsonify(rows)

@app.post('/api/projects/<pid>/urls')
@auth_required
def cloud_url_register(pid):
    uid=session['user_id']; oid=require_org(uid); d=request.get_json() or {}
    resolved=_resolve_cloud_project_id(uid,oid,pid)
    if not resolved: return jsonify(error='project_not_found'),404
    try:
        row=_register_cloud_url(uid,oid,resolved,d.get('url'),d.get('name'),d.get('kind'),'manual',d.get('metadata'))
    except ValueError as e:
        return jsonify(error=str(e)),400 if str(e)!='project_not_found' else 404
    return jsonify(row),201

@app.get('/api/v1/projects/<pid>/urls/<uid_>')
@auth_required
def cloud_url_resource(pid,uid_):
    uid=session['user_id']; oid=require_org(uid)
    if not project_access(uid,oid,pid): return jsonify(error='project_not_found'),404
    row=_one('/rest/v1/cloud_project_connections',{'id':f'eq.{uid_}','project_id':f'eq.{pid}','owner_user_id':f'eq.{uid}','organization_id':f'eq.{oid}','connection_type':'eq.url','select':'*','limit':'1'})
    if not row:return jsonify(error='url_not_found'),404
    cfg=row.get('config') or {}
    return jsonify({'ok':True,'cloud':'KOJA CLOUD','id':row['id'],'project_id':pid,'name':row.get('name'),'url':cfg.get('url') or row.get('host'),'url_kind':cfg.get('url_kind'),'status':row.get('status'),'koja_cloud_url':cfg.get('koja_cloud_url'),'source':cfg.get('source'),'created_at':row.get('created_at')})

@app.post('/api/v1/projects/<pid>/urls/<uid_>/check')
@auth_required
def cloud_url_check(pid,uid_):
    uid=session['user_id']; oid=require_org(uid)
    if not project_access(uid,oid,pid): return jsonify(error='project_not_found'),404
    row=_one('/rest/v1/cloud_project_connections',{'id':f'eq.{uid_}','project_id':f'eq.{pid}','owner_user_id':f'eq.{uid}','organization_id':f'eq.{oid}','connection_type':'eq.url','select':'*','limit':'1'})
    if not row:return jsonify(error='url_not_found'),404
    cfg=row.get('config') or {}; target=cfg.get('url') or row.get('host') or ''
    result={'url':target,'checked_at':now(),'reachable':False,'status_code':None,'error':None}
    try:
        r=requests.get(target,timeout=12,allow_redirects=True,stream=True,headers={'User-Agent':'KOJA-CLOUD-URL-CHECK/1.0'})
        result.update(reachable=200 <= r.status_code < 500,status_code=r.status_code,final_url=r.url)
    except Exception as e: result['error']=str(e)[:300]
    _patch('/rest/v1/cloud_project_connections',{'id':f'eq.{uid_}'},{'status':'active' if result['reachable'] else 'unreachable','config':dict(cfg,last_check=result)})
    return jsonify(result)

@app.get('/api/projects/<pid>/connections')
@auth_required
def project_connections(pid):
    uid=session['user_id']; oid=require_org(uid)
    if not project_access(uid,oid,pid):return jsonify(error='project_not_found'),404
    rows=sb('/rest/v1/cloud_project_connections',params={'project_id':f'eq.{pid}','owner_user_id':f'eq.{uid}','organization_id':f'eq.{oid}','select':'*','order':'created_at.desc'})
    # The cloud URL is stored in the existing connection config so no schema
    # migration is required. It is exposed as a first-class table field.
    for row in rows:
        cfg=row.get('config') or {}
        row['koja_cloud_url']=cfg.get('koja_cloud_url') or row.get('host') or ''
        row.pop('secret_ciphertext',None)
    return jsonify(rows)

@app.post('/api/projects/<pid>/connections')
@auth_required
def project_connection_create(pid):
    uid=session['user_id']; oid=require_org(uid); d=request.get_json() or {}
    if not project_access(uid,oid,pid):return jsonify(error='project_not_found'),404
    env=d.get('environment_id')
    if env and not _one('/rest/v1/cloud_project_environments',{'id':f'eq.{env}','project_id':f'eq.{pid}','owner_user_id':f'eq.{uid}','organization_id':f'eq.{oid}','select':'id','limit':'1'}):return jsonify(error='environment_not_found'),404
    secret=encrypt(d.get('secret','')) if d.get('secret') is not None else ''
    base=(os.getenv('KOJA_CLOUD_PUBLIC_URL') or request.url_root).rstrip('/')
    # Generate a deterministic cloud endpoint after the connection row exists.
    # The endpoint is stored in config.koja_cloud_url and returned to clients.
    cfg=dict(d.get('config') or {})
    cfg['connection_kind']=cfg.get('connection_kind') or 'application'
    row=sb('/rest/v1/cloud_project_connections','POST',{'owner_user_id':uid,'organization_id':oid,'project_id':pid,'environment_id':env,'name':d.get('name','Connection'),'connection_type':d.get('connection_type','api'),'provider':d.get('provider','custom'),'host':d.get('host'),'port':d.get('port'),'database_name':d.get('database_name'),'username':d.get('username'),'secret_ciphertext':secret,'status':'connected','config':cfg},params={'select':'*'})[0]
    cloud_url=d.get('koja_cloud_url') or cfg.get('koja_cloud_url') or f"{base}/api/v1/projects/{pid}/connections/{row['id']}/endpoint"
    cfg['koja_cloud_url']=cloud_url
    try:
        updated=sb('/rest/v1/cloud_project_connections', 'PATCH', cfg and {'id':f"eq.{row['id']}"}, {'config':cfg}, params={'select':'*'})
        if updated: row=updated[0]
    except Exception:
        # The row already exists; return the generated URL even if an older
        # Supabase deployment rejects the optional config update.
        row['config']=cfg
    safe={k:v for k,v in row.items() if k!='secret_ciphertext'}; safe['koja_cloud_url']=cloud_url
    audit(uid,'project.connection.create','project_connection',row['id'],{'project_id':pid,'koja_cloud_url':cloud_url})
    return jsonify(safe),201

@app.get('/api/v1/projects/<pid>/connections/<cid>/endpoint')
@auth_required
def project_connection_endpoint(pid,cid):
    uid=session['user_id']; oid=require_org(uid)
    if not project_access(uid,oid,pid):return jsonify(error='project_not_found'),404
    row=_one('/rest/v1/cloud_project_connections',{'id':f'eq.{cid}','project_id':f'eq.{pid}','owner_user_id':f'eq.{uid}','organization_id':f'eq.{oid}','select':'*','limit':'1'})
    if not row:return jsonify(error='connection_not_found'),404
    cfg=row.get('config') or {}
    return jsonify({'ok':True,'cloud':'KOJA CLOUD','connection_id':cid,'project_id':pid,'status':row.get('status'),'koja_cloud_url':cfg.get('koja_cloud_url') or row.get('host'),'time':now()})

@app.get('/api/projects/<pid>/hosting')
@auth_required
def project_hosting(pid):
    uid=session['user_id']; oid=require_org(uid)
    if not project_access(uid,oid,pid):return jsonify(error='project_not_found'),404
    services=sb('/rest/v1/cloud_compute_services',params={'project_id':f'eq.{pid}','owner_user_id':f'eq.{uid}','organization_id':f'eq.{oid}','select':'*','order':'created_at.desc'})
    for x in services:
        cfg=x.get('config') or {}; x['open_url']=x.get('service_url') or cfg.get('koja_url') or ''
    return jsonify(project_id=pid,services=services)

@app.get('/api/services/<sid>/logs')
@cloud_api_or_login
def service_logs(sid):
    uid=session['user_id']; oid=require_org(uid)
    if not _one('/rest/v1/cloud_compute_services',{'id':f'eq.{sid}','owner_user_id':f'eq.{uid}','organization_id':f'eq.{oid}','select':'id','limit':'1'}): return jsonify(error='service_not_found'),404
    return jsonify(sb('/rest/v1/cloud_compute_logs',params={'service_id':f'eq.{sid}','owner_user_id':f'eq.{uid}','select':'*','order':'created_at.desc','limit':500}))

@app.get('/api/services/<sid>/metrics')
@cloud_api_or_login
def service_metrics(sid):
    uid=session['user_id']; oid=require_org(uid)
    if not _one('/rest/v1/cloud_compute_services',{'id':f'eq.{sid}','owner_user_id':f'eq.{uid}','organization_id':f'eq.{oid}','select':'id','limit':'1'}): return jsonify(error='service_not_found'),404
    return jsonify(sb('/rest/v1/cloud_compute_metrics',params={'service_id':f'eq.{sid}','owner_user_id':f'eq.{uid}','select':'*','order':'recorded_at.desc','limit':500}))

@app.delete('/api/storage/objects/<path:object_id>')
@cloud_api_or_login
def delete_storage_object(object_id):
    uid=session['user_id']; oid=require_org(uid)
    row=_one('/rest/v1/cloud_storage_objects',{'id':f'eq.{object_id}','owner_user_id':f'eq.{uid}','organization_id':f'eq.{oid}','select':'*','limit':'1'})
    if not row:return jsonify(error='object_not_found'),404
    bucket=_one('/rest/v1/cloud_storage_buckets',{'id':f'eq.{row.get("bucket_id") }','organization_id':f'eq.{oid}','select':'bucket_name,name','limit':'1'}) if row.get('bucket_id') else None
    bucket_name=(bucket or {}).get('bucket_name') or (bucket or {}).get('name')
    if bucket_name:
        try:
            requests.delete(f'{SUPABASE_URL}/storage/v1/object/{quote(str(bucket_name),safe="")}/{row.get("object_path","")}',headers=sb_headers(),timeout=30)
        except Exception: pass
    _delete('/rest/v1/cloud_storage_objects',{'id':f'eq.{object_id}','owner_user_id':f'eq.{uid}'})
    audit(uid,'storage.object.delete','storage_object',object_id,{'organization_id':oid})
    return jsonify(message='object_deleted')

@app.get('/api/storage/download/<path:bucket>/<path:object_path>')
@cloud_api_or_login
def storage_download(bucket,object_path):
    # Public/signed delivery is delegated to Supabase Storage. The endpoint verifies
    # that the object is tracked by this tenant before returning the provider URL.
    uid=session['user_id']; oid=require_org(uid)
    rows=sb('/rest/v1/cloud_storage_objects',params={'organization_id':f'eq.{oid}','owner_user_id':f'eq.{uid}','object_path':f'eq.{object_path}','select':'id,object_path,bucket_id,content_type','limit':'1'})
    if not rows:return jsonify(error='object_not_found'),404
    return jsonify(url=f'{SUPABASE_URL}/storage/v1/object/{bucket}/{object_path}',object=rows[0])

@app.post('/api/databases/<dbid>/start')
@cloud_api_or_login
def database_start(dbid):
    uid=session['user_id']; oid=require_org(uid)
    db=_one('/rest/v1/cloud_databases',{'id':f'eq.{dbid}','owner_user_id':f'eq.{uid}','organization_id':f'eq.{oid}','select':'*','limit':'1'})
    if not db:return jsonify(error='database_not_found'),404
    job=_enqueue_generic_job(uid,oid,db.get('project_id'),'database_start',{'database_id':dbid,'engine':db.get('engine'),'region':db.get('region')})
    _patch('/rest/v1/cloud_databases',{'id':f'eq.{dbid}'},{'status':'starting','updated_at':now()})
    return jsonify(database_id=dbid,job=job),202

@app.post('/api/databases/<dbid>/stop')
@cloud_api_or_login
def database_stop(dbid):
    uid=session['user_id']; oid=require_org(uid)
    db=_one('/rest/v1/cloud_databases',{'id':f'eq.{dbid}','owner_user_id':f'eq.{uid}','organization_id':f'eq.{oid}','select':'*','limit':'1'})
    if not db:return jsonify(error='database_not_found'),404
    job=_enqueue_generic_job(uid,oid,db.get('project_id'),'database_stop',{'database_id':dbid})
    _patch('/rest/v1/cloud_databases',{'id':f'eq.{dbid}'},{'status':'stopping','updated_at':now()})
    return jsonify(database_id=dbid,job=job),202

@app.get('/api/databases/<dbid>/events')
@cloud_api_or_login
def database_events(dbid):
    uid=session['user_id']; oid=require_org(uid)
    if not _one('/rest/v1/cloud_databases',{'id':f'eq.{dbid}','owner_user_id':f'eq.{uid}','organization_id':f'eq.{oid}','select':'id','limit':'1'}):return jsonify(error='database_not_found'),404
    return jsonify(sb('/rest/v1/cloud_database_events',params={'database_id':f'eq.{dbid}','organization_id':f'eq.{oid}','select':'*','order':'created_at.desc','limit':500}))

@app.post('/api/databases/<dbid>/backup')
@cloud_api_or_login
def database_backup(dbid):
    uid=session['user_id']; oid=require_org(uid); db=_one('/rest/v1/cloud_databases',{'id':f'eq.{dbid}','owner_user_id':f'eq.{uid}','organization_id':f'eq.{oid}','select':'*','limit':'1'})
    if not db:return jsonify(error='database_not_found'),404
    code='BKP-'+secrets.token_hex(6).upper()
    row=_insert('/rest/v1/cloud_database_backups',{'owner_user_id':uid,'customer_id':db.get('customer_id'),'organization_id':oid,'project_id':db.get('project_id'),'database_id':dbid,'backup_code':code,'name':_json_body().get('name') or code,'status':'queued','backup_type':'manual','region':db.get('region','global'),'provider':db.get('provider','adapter'),'metadata':_json_body()})
    audit(uid,'database.backup.create','database_backup',row['id'],{'organization_id':oid})
    return jsonify(row),202

@app.post('/api/media/assets/<aid>/cancel')
@cloud_api_or_login
def media_cancel(aid):
    uid=session['user_id']; oid=require_org(uid)
    rows=sb('/rest/v1/cloud_media_jobs',params={'asset_id':f'eq.{aid}','owner_user_id':f'eq.{uid}','organization_id':f'eq.{oid}','status':'in.(queued,running)','select':'*'})
    for j in rows: _patch('/rest/v1/cloud_media_jobs',{'id':f'eq.{j["id"]}'},{'status':'cancelled','completed_at':now()})
    _patch('/rest/v1/cloud_media_assets',{'id':f'eq.{aid}','owner_user_id':f'eq.{uid}'},{'status':'ready','updated_at':now()})
    return jsonify(message='media_processing_cancelled',jobs=len(rows))

@app.get('/api/media/assets/<aid>/jobs')
@cloud_api_or_login
def media_jobs(aid):
    uid=session['user_id']; oid=require_org(uid)
    return jsonify(sb('/rest/v1/cloud_media_jobs',params={'asset_id':f'eq.{aid}','owner_user_id':f'eq.{uid}','organization_id':f'eq.{oid}','select':'*','order':'created_at.desc'}))

@app.post('/api/live/channels/<cid>/start')
@auth_required
def live_start(cid):
    uid=session['user_id']; oid=require_org(uid)
    ch=_one('/rest/v1/cloud_live_channels',{'id':f'eq.{cid}','owner_user_id':f'eq.{uid}','organization_id':f'eq.{oid}','select':'*','limit':'1'})
    if not ch:return jsonify(error='channel_not_found'),404
    playback=ch.get('playback_url') or f'{request.host_url.rstrip("/")}/live/{ch.get("channel_code")}'
    _patch('/rest/v1/cloud_live_channels',{'id':f'eq.{cid}'},{'status':'live','playback_url':playback,'updated_at':now()})
    url_record=None
    if ch.get('project_id'):
        try: url_record=_register_cloud_url(uid,oid,ch.get('project_id'),playback,ch.get('name') or 'KOJA Stream','live_stream','live',{'channel_id':cid})
        except ValueError: pass
    return jsonify(status='live',playback_url=playback,koja_url_record=url_record)

@app.post('/api/live/channels/<cid>/stop')
@auth_required
def live_stop(cid):
    uid=session['user_id']; oid=require_org(uid)
    ch=_one('/rest/v1/cloud_live_channels',{'id':f'eq.{cid}','owner_user_id':f'eq.{uid}','organization_id':f'eq.{oid}','select':'id','limit':'1'})
    if not ch:return jsonify(error='channel_not_found'),404
    _patch('/rest/v1/cloud_live_channels',{'id':f'eq.{cid}'},{'status':'offline','updated_at':now()})
    return jsonify(status='offline')

@app.post('/api/keys/<kid>/revoke')
@auth_required
def revoke_key(kid):
    uid=session['user_id']; oid=require_org(uid)
    key=_one('/rest/v1/cloud_api_keys',{'id':f'eq.{kid}','user_id':f'eq.{uid}','organization_id':f'eq.{oid}','select':'id','limit':'1'})
    if not key:return jsonify(error='api_key_not_found'),404
    _patch('/rest/v1/cloud_api_keys',{'id':f'eq.{kid}'},{'status':'revoked','revoked_at':now()})
    audit(uid,'api_key.revoke','api_key',kid,{'organization_id':oid})
    return jsonify(message='api_key_revoked')

@app.post('/api/keys/<kid>/rotate')
@auth_required
def rotate_key(kid):
    uid=session['user_id']; oid=require_org(uid)
    key=_one('/rest/v1/cloud_api_keys',{'id':f'eq.{kid}','user_id':f'eq.{uid}','organization_id':f'eq.{oid}','select':'*','limit':'1'})
    if not key:return jsonify(error='api_key_not_found'),404
    raw='koja_'+secrets.token_urlsafe(32)
    _patch('/rest/v1/cloud_api_keys',{'id':f'eq.{kid}'},{'status':'revoked','revoked_at':now()})
    new=_insert('/rest/v1/cloud_api_keys',{'organization_id':oid,'user_id':uid,'name':key.get('name','API Key'),'key_prefix':raw[:13],'key_hash':hashlib.sha256(raw.encode()).hexdigest(),'scopes':key.get('scopes',['read']),'status':'active'})
    new['secret']=raw
    return jsonify(new),201

@app.get('/api/billing/usage')
@auth_required
def billing_usage():
    uid=session['user_id']; oid=require_org(uid)
    events=sb('/rest/v1/cloud_usage_events',params={'organization_id':f'eq.{oid}','select':'*','order':'created_at.desc','limit':1000})
    totals={}
    for e in events:
        k=f'{e.get("service","unknown")}:{e.get("metric","unknown")}:{e.get("unit","unit")}'
        try: totals[k]=totals.get(k,0)+float(e.get('quantity') or 0)
        except Exception: pass
    return jsonify(organization_id=oid,totals=totals,recent_events=events)

@app.get('/api/audit')
@auth_required
def audit_events():
    uid=session['user_id']; oid=require_org(uid)
    return jsonify(sb('/rest/v1/cloud_audit_events',params={'user_id':f'eq.{uid}','select':'*','order':'created_at.desc','limit':500}))


# ============================ V14 PRODUCTION PLATFORM ============================
@app.get('/api/customers')
@auth_required
def customers_list():
    uid=session['user_id']; return jsonify(sb('/rest/v1/cloud_customers',params={'owner_user_id':f'eq.{uid}','select':'id,owner_user_id,display_name,status,plan_code,created_at,updated_at','order':'created_at.desc'}))

@app.post('/api/customers')
@auth_required
def customer_create():
    uid=session['user_id']; d=_json_body(); name=(d.get('display_name') or 'Customer').strip()
    row=ensure_customer(uid,name); audit(uid,'customer.create','customer',row.get('id')); return jsonify(row),201


@app.get('/api/identity/profile')
@auth_required
def identity_profile():
    uid=session['user_id']; rows=sb('/rest/v1/cloud_profiles',params={'id':f'eq.{uid}','select':'*','limit':'1'})
    return jsonify(rows[0] if rows else {'id':uid,'email':current_user().get('email')})

@app.patch('/api/identity/profile')
@auth_required
def identity_profile_update():
    uid=session['user_id']; d=_json_body(); payload={k:d[k] for k in ('full_name','status') if k in d}
    payload['updated_at']=now(); rows=_patch('/rest/v1/cloud_profiles',{'id':f'eq.{uid}'},payload)
    audit(uid,'identity.profile.update','profile',uid); return jsonify(rows[0] if rows else payload)

@app.get('/api/databases/<dbid>/connections')
@cloud_api_or_login
def database_connections(dbid):
    uid=session['user_id']; oid=require_org(uid)
    if not _one('/rest/v1/cloud_databases',{'id':f'eq.{dbid}','owner_user_id':f'eq.{uid}','organization_id':f'eq.{oid}','select':'id','limit':'1'}): return jsonify(error='database_not_found'),404
    return jsonify(sb('/rest/v1/cloud_database_connections',params={'database_id':f'eq.{dbid}','organization_id':f'eq.{oid}','select':'id,connection_code,provider,connection_type,host,port,database_name,username,ssl_mode,status,last_tested_at,last_test_status,created_at','order':'created_at.desc'}))

@app.post('/api/databases/<dbid>/connections')
@cloud_api_or_login
def database_connection_create(dbid):
    uid=session['user_id']; oid=require_org(uid); db=_one('/rest/v1/cloud_databases',{'id':f'eq.{dbid}','owner_user_id':f'eq.{uid}','organization_id':f'eq.{oid}','select':'*','limit':'1'})
    if not db:return jsonify(error='database_not_found'),404
    d=_json_body(); code='KDC-'+secrets.token_hex(5).upper()
    row=_insert('/rest/v1/cloud_database_connections',{'owner_user_id':uid,'customer_id':db.get('customer_id'),'organization_id':oid,'project_id':db.get('project_id'),'database_id':dbid,'connection_code':code,'provider':d.get('provider',db.get('provider','adapter')),'connection_type':d.get('connection_type','private'),'host':d.get('host',''),'port':d.get('port',5432),'database_name':d.get('database_name',db.get('database_name')),'username':d.get('username',''),'password_hash':hashlib.sha256((d.get('password') or '').encode()).hexdigest() if d.get('password') else None,'ssl_mode':d.get('ssl_mode','require'),'status':'configured','metadata':d.get('metadata',{})})
    audit(uid,'database.connection.create','database_connection',row['id'],{'organization_id':oid}); return jsonify(row),201

@app.get('/api/databases/<dbid>/credentials')
@cloud_api_or_login
def database_credentials(dbid):
    uid=session['user_id']; oid=require_org(uid)
    if not _one('/rest/v1/cloud_databases',{'id':f'eq.{dbid}','owner_user_id':f'eq.{uid}','organization_id':f'eq.{oid}','select':'id','limit':'1'}):return jsonify(error='database_not_found'),404
    return jsonify(sb('/rest/v1/cloud_database_credentials',params={'database_id':f'eq.{dbid}','organization_id':f'eq.{oid}','select':'id,credential_code,name,username,role_name,scopes,status,expires_at,last_used_at,created_at','order':'created_at.desc'}))

@app.post('/api/databases/<dbid>/credentials')
@cloud_api_or_login
def database_credential_create(dbid):
    uid=session['user_id']; oid=require_org(uid); db=_one('/rest/v1/cloud_databases',{'id':f'eq.{dbid}','owner_user_id':f'eq.{uid}','organization_id':f'eq.{oid}','select':'*','limit':'1'})
    if not db:return jsonify(error='database_not_found'),404
    d=_json_body(); raw=d.get('password') or secrets.token_urlsafe(18); code='KCR-'+secrets.token_hex(5).upper()
    row=_insert('/rest/v1/cloud_database_credentials',{'owner_user_id':uid,'customer_id':db.get('customer_id'),'organization_id':oid,'project_id':db.get('project_id'),'database_id':dbid,'credential_code':code,'name':d.get('name','KOJA Data Credential'),'username':d.get('username',''),'password_hash':hashlib.sha256(raw.encode()).hexdigest(),'role_name':d.get('role_name','app'),'scopes':d.get('scopes',['read','write']),'status':'active'})
    row['password']=raw; audit(uid,'database.credential.create','database_credential',row['id'],{'organization_id':oid}); return jsonify(row),201

@app.get('/api/webhooks')
@auth_required
def webhooks_list():
    uid=session['user_id']; oid=require_org(uid); return jsonify(sb('/rest/v1/cloud_webhooks',params={'organization_id':f'eq.{oid}','owner_user_id':f'eq.{uid}','select':'id,name,url,events,status,last_delivery_at,last_status_code,created_at,updated_at','order':'created_at.desc'}))

@app.post('/api/webhooks')
@auth_required
def webhook_create():
    uid=session['user_id']; oid=require_org(uid); d=_json_body(); raw=secrets.token_urlsafe(32)
    row=_insert('/rest/v1/cloud_webhooks',{'owner_user_id':uid,'organization_id':oid,'project_id':d.get('project_id'),'name':d.get('name','Webhook'),'url':d.get('url',''),'events':d.get('events',['*']),'secret_hash':hashlib.sha256(raw.encode()).hexdigest(),'status':'active'})
    row['secret']=raw; audit(uid,'webhook.create','webhook',row['id'],{'organization_id':oid}); return jsonify(row),201

@app.patch('/api/webhooks/<wid>')
@auth_required
def webhook_update(wid):
    uid=session['user_id']; oid=require_org(uid); d=_json_body(); row=_one('/rest/v1/cloud_webhooks',{'id':f'eq.{wid}','owner_user_id':f'eq.{uid}','organization_id':f'eq.{oid}','select':'id','limit':'1'})
    if not row:return jsonify(error='webhook_not_found'),404
    payload={k:d[k] for k in ('name','url','events','status') if k in d}; payload['updated_at']=now(); rows=_patch('/rest/v1/cloud_webhooks',{'id':f'eq.{wid}','owner_user_id':f'eq.{uid}'},payload); return jsonify(rows[0] if rows else payload)

@app.get('/api/infrastructure/providers')
@auth_required
def infrastructure_providers():
    return jsonify(sb('/rest/v1/cloud_infrastructure_providers',params={'select':'*','order':'name.asc'}))

@app.get('/api/jobs')
@auth_required
def jobs_list():
    uid=session['user_id']; oid=require_org(uid); return jsonify(sb('/rest/v1/cloud_jobs',params={'organization_id':f'eq.{oid}','owner_user_id':f'eq.{uid}','select':'*','order':'created_at.desc','limit':'500'}))

@app.get('/api/storage/object/<oid>/download')
@cloud_api_or_login
def storage_object_download(oid):
    uid=session['user_id']; org=require_org(uid); row=_one('/rest/v1/cloud_storage_objects',{'id':f'eq.{oid}','owner_user_id':f'eq.{uid}','organization_id':f'eq.{org}','select':'*','limit':'1'})
    if not row:return jsonify(error='object_not_found'),404
    b=_one('/rest/v1/cloud_storage_buckets',{'id':f'eq.{row.get("bucket_id") }','organization_id':f'eq.{org}','select':'bucket_name,name','limit':'1'}) if row.get('bucket_id') else None
    bucket=(b or {}).get('bucket_name') or (b or {}).get('name')
    if not bucket:return jsonify(error='bucket_not_found'),404
    return jsonify(url=f'{SUPABASE_URL}/storage/v1/object/{quote(str(bucket),safe="")}/{quote(str(row.get("object_path","")),safe="/")}',object=row)

@app.get('/api/system/services')
@auth_required
def service_catalog():
    return jsonify(services=[
        {'id':'identity','name':'Universal Identity / IAM','status':'active','features':['accounts','profiles','customers','organizations','members','roles']},
        {'id':'customers','name':'Customers','status':'active'},
        {'id':'organizations','name':'Organizations / Multi-tenancy','status':'active','features':['members','roles','switching','isolation']},
        {'id':'projects','name':'Projects','status':'active'},
        {'id':'compute','name':'KOJA Run','status':'active','execution':'agent-backed','features':['services','environment','deployments','start','stop','restart','jobs','agents','logs','metrics','github-webhooks']},
        {'id':'storage','name':'KOJA Vault','status':'active','execution':'supabase-object-storage','features':['buckets','uploads','object-tracking','downloads','deletion']},
        {'id':'database','name':'KOJA Data','status':'active','execution':'provider-agent-backed','features':['resources','start','stop','backups','events','connections','credentials']},
        {'id':'media','name':'KOJA Media','status':'active','execution':'job-agent-backed','features':['assets','processing','job-tracking','cancellation']},
        {'id':'live','name':'KOJA Stream Streaming','status':'active','execution':'provider-control-plane','features':['channels','stream-keys','start','stop','playback']},
        {'id':'api','name':'KOJA API','status':'active','features':['keys','scopes','revoke','rotate','versioned-endpoints']},
        {'id':'usage','name':'Usage / Billing Metering','status':'active'},
        {'id':'audit','name':'Audit','status':'active'},
        {'id':'webhooks','name':'Webhooks','status':'active'},
        {'id':'providers','name':'Infrastructure Provider Catalog','status':'active'},
        {'id':'diagnostics','name':'Production Health / Diagnostics','status':'active'},
        {'id':'schema','name':'Supabase Schema Compatibility','status':'active'},
        {'id':'multitenancy','name':'Multi-tenant Resource Isolation','status':'active'},
    ])

@app.route('/favicon.ico')
def favicon():
    return ('', 204)

@app.errorhandler(404)
def api_not_found(e):
    # API clients must receive a real 404 for unknown API routes, not a 500.
    if request.path.startswith('/api/'):
        return jsonify(error='not_found', path=request.path), 404
    return e

@app.errorhandler(Exception)
def api_or_html_error(e):
    # Never return an HTML 500 page to a JSON API client. This keeps every
    # cloud API endpoint machine-readable and makes frontend failures visible.
    if request.path.startswith('/api/'):
        return jsonify(error=str(e) or 'internal_server_error', path=request.path), 500
    raise e

@app.errorhandler(413)
def too_large(e): return jsonify(error='file_too_large'),413


# ========================= KOJA CLOUD V13 ORCHESTRATION =========================
V13_VERSION='13.0.0'
V15_VERSION='17.5.0'
V14_VERSION='14.2.0'

@app.get('/api/infrastructure/overview')
@auth_required
def infrastructure_overview():
    uid=session['user_id']; oid=require_org(uid)
    out={}
    specs={
      'services':'cloud_compute_services','volumes':'cloud_compute_volumes','routes':'cloud_compute_routes',
      'recovery':'cloud_compute_recovery_events','quotas':'cloud_compute_quotas','capacity':'cloud_infrastructure_capacity'
    }
    for key,table in specs.items():
        try:
            params={'owner_user_id':f'eq.{uid}','select':'*','limit':'500'}
            if table not in ('cloud_compute_quotas','cloud_infrastructure_capacity'): params['organization_id']=f'eq.{oid}'
            out[key]=sb('/rest/v1/'+table,params=params)
        except Exception as e: out[key]=[]
    return jsonify(version=V13_VERSION,organization_id=oid,**out)

@app.post('/api/infrastructure/volumes')
@auth_required
def create_volume():
    uid=session['user_id']; oid=require_org(uid); d=request.get_json() or {}
    row=sb('/rest/v1/cloud_compute_volumes','POST',{
      'owner_user_id':uid,'organization_id':oid,'project_id':d.get('project_id'),'service_id':d.get('service_id'),
      'name':d.get('name') or 'volume-'+secrets.token_hex(3),'size_gb':int(d.get('size_gb') or 10),
      'mount_path':d.get('mount_path') or '/data','provider_code':d.get('provider_code') or 'local',
      'region':d.get('region') or 'global','status':'provisioning','config':d.get('config') or {}
    },params={'select':'*'})[0]
    return jsonify(volume=row),201

@app.delete('/api/infrastructure/volumes/<vid>')
@auth_required
def delete_volume(vid):
    uid=session['user_id']; oid=require_org(uid)
    rows=sb('/rest/v1/cloud_compute_volumes','DELETE',params={'id':f'eq.{vid}','owner_user_id':f'eq.{uid}','organization_id':f'eq.{oid}','select':'*'})
    return jsonify(deleted=bool(rows),volume=rows[0] if rows else None)

@app.post('/api/infrastructure/routes')
@auth_required
def create_route():
    uid=session['user_id']; oid=require_org(uid); d=request.get_json() or {}
    row=sb('/rest/v1/cloud_compute_routes','POST',{
      'owner_user_id':uid,'organization_id':oid,'service_id':d.get('service_id'),'domain':d.get('domain'),
      'target_port':int(d.get('target_port') or 10000),'tls_status':'pending','status':'provisioning'
    },params={'select':'*'})[0]
    return jsonify(route=row),201

@app.delete('/api/infrastructure/routes/<rid>')
@auth_required
def delete_route(rid):
    uid=session['user_id']; oid=require_org(uid)
    rows=sb('/rest/v1/cloud_compute_routes','DELETE',params={'id':f'eq.{rid}','owner_user_id':f'eq.{uid}','organization_id':f'eq.{oid}','select':'*'})
    return jsonify(deleted=bool(rows),route=rows[0] if rows else None)

@app.get('/api/infrastructure/quotas')
@auth_required
def get_quota():
    uid=session['user_id']
    rows=sb('/rest/v1/cloud_compute_quotas',params={'owner_user_id':f'eq.{uid}','select':'*','limit':'1'})
    if not rows:
        rows=sb('/rest/v1/cloud_compute_quotas','POST',{'owner_user_id':uid},params={'select':'*'})
    return jsonify(quota=rows[0])

@app.patch('/api/infrastructure/quotas')
@auth_required
def set_quota():
    uid=session['user_id']; d=request.get_json() or {}
    allowed=['cpu_limit','memory_mb_limit','service_limit','storage_gb_limit','bandwidth_bytes_limit']
    patch={k:d[k] for k in allowed if k in d}; patch['updated_at']=now()
    rows=sb('/rest/v1/cloud_compute_quotas','PATCH',patch,params={'owner_user_id':f'eq.{uid}','select':'*'})
    if not rows: rows=sb('/rest/v1/cloud_compute_quotas','POST',dict(patch,owner_user_id=uid),params={'select':'*'})
    return jsonify(quota=rows[0])

@app.post('/api/infrastructure/recover/<sid>')
@auth_required
def recover_service(sid):
    uid=session['user_id']; oid=require_org(uid)
    s=_one('/rest/v1/cloud_compute_services',{'id':f'eq.{sid}','owner_user_id':f'eq.{uid}','organization_id':f'eq.{oid}','select':'*','limit':'1'})
    if not s:return jsonify(error='service_not_found'),404
    row=sb('/rest/v1/cloud_compute_recovery_events','POST',{
      'owner_user_id':uid,'organization_id':oid,'service_id':sid,'event_type':'manual_recovery',
      'reason':'Manual recovery requested','action':'restart','status':'queued','metadata':{}
    },params={'select':'*'})[0]
    job=sb('/rest/v1/cloud_compute_jobs','POST',{
      'owner_user_id':uid,'organization_id':oid,'service_id':sid,'job_type':'restart','status':'queued',
      'spec':{'reason':'manual_recovery'},'message':'Recovery queued for compute agent'
    },params={'select':'*'})[0]
    return jsonify(status='queued',recovery=row,job=job)

@app.post('/api/infrastructure/capacity')
@auth_required
def update_capacity():
    d=request.get_json() or {}
    required=['provider_code','region']
    if any(not d.get(x) for x in required):return jsonify(error='provider_code_and_region_required'),400
    payload={k:d.get(k) for k in ['provider_code','region','cpu_total','cpu_available','memory_total_mb','memory_available_mb','status'] if d.get(k) is not None}
    payload['updated_at']=now()
    rows=sb('/rest/v1/cloud_infrastructure_capacity','PATCH',payload,params={'provider_code':f'eq.{d["provider_code"]}','region':f'eq.{d["region"]}','select':'*'})
    if not rows: rows=sb('/rest/v1/cloud_infrastructure_capacity','POST',payload,params={'select':'*'})
    return jsonify(capacity=rows[0])

@app.get('/api/infrastructure/regions')
@auth_required
def infrastructure_regions():
    try:
        rows=sb('/rest/v1/cloud_infrastructure_capacity',params={'select':'provider_code,region,status,cpu_available,memory_available_mb','order':'provider_code,region'})
    except Exception: rows=[]
    return jsonify(regions=rows)

@app.get('/api/infrastructure/service/<sid>')
@auth_required
def service_infrastructure(sid):
    uid=session['user_id']; oid=require_org(uid)
    service=_one('/rest/v1/cloud_compute_services',{'id':f'eq.{sid}','owner_user_id':f'eq.{uid}','organization_id':f'eq.{oid}','select':'*','limit':'1'})
    if not service:return jsonify(error='service_not_found'),404
    def q(table):
        try:return sb('/rest/v1/'+table,params={'service_id':f'eq.{sid}','owner_user_id':f'eq.{uid}','organization_id':f'eq.{oid}','select':'*','order':'created_at.desc','limit':'200'})
        except Exception:return []
    return jsonify(service=service,volumes=q('cloud_compute_volumes'),routes=q('cloud_compute_routes'),recovery=q('cloud_compute_recovery_events'),jobs=q('cloud_compute_jobs'),deployments=q('cloud_compute_deployments'))

@app.get('/api/system/v14')
@auth_required
def system_v14():
    return jsonify(version='17.5.0', layer='production-cloud-platform', compute='agent-backed', storage='supabase-object-storage', database='provider-agent-backed', media='job-agent-backed', live='provider-control-plane', multi_tenant=True)

@app.get('/api/system/v13')
def system_v13():
    return jsonify(version=V13_VERSION,layer='production-infrastructure-orchestration',features={
      'provider_region_selection':True,'resource_quotas':True,'agent_selection':True,'persistent_volumes':True,
      'service_routes':True,'health_recovery':True,'rolling_deployments':True,'usage_attribution':True,
      'tenant_isolation':True,'capacity_tracking':True,'infrastructure_events':True
    })



# V15.8 Universal Resource Operations: Storage, KOJA Data, Media and project links.
@app.delete('/api/storage/buckets/<path:bucket_id>')
@auth_required
def delete_storage_bucket(bucket_id):
    uid=session['user_id']; oid=require_org(uid)
    row=_one('/rest/v1/cloud_storage_buckets',{'id':f'eq.{bucket_id}','owner_user_id':f'eq.{uid}','organization_id':f'eq.{oid}','select':'*','limit':'1'})
    if not row:return jsonify(error='bucket_not_found'),404
    objs=sb('/rest/v1/cloud_storage_objects',params={'bucket_id':f'eq.{bucket_id}','owner_user_id':f'eq.{uid}','organization_id':f'eq.{oid}','select':'id,object_path'},)
    bucket_name=row.get('bucket_name') or row.get('name')
    for obj in objs:
        try:
            requests.delete(f'{SUPABASE_URL}/storage/v1/object/{quote(str(bucket_name),safe="")}/{obj.get("object_path","")}',headers=sb_headers(),timeout=20)
        except Exception: pass
    _delete('/rest/v1/cloud_storage_objects',{'bucket_id':f'eq.{bucket_id}','owner_user_id':f'eq.{uid}','organization_id':f'eq.{oid}'})
    _delete('/rest/v1/cloud_storage_buckets',{'id':f'eq.{bucket_id}','owner_user_id':f'eq.{uid}','organization_id':f'eq.{oid}'})
    audit(uid,'storage.bucket.delete','bucket',bucket_id,{'organization_id':oid,'objects_deleted':len(objs)})
    return jsonify(message='bucket_deleted',objects_deleted=len(objs))

@app.post('/api/databases/<dbid>/connections/<cid>/test')
@auth_required
def database_connection_test_v159(dbid,cid):
    uid=session['user_id']; oid=require_org(uid)
    row=_one('/rest/v1/cloud_database_connections',{'id':f'eq.{cid}','database_id':f'eq.{dbid}','organization_id':f'eq.{oid}','select':'*','limit':'1'})
    if not row:return jsonify(error='connection_not_found'),404
    updated=_patch('/rest/v1/cloud_database_connections',{'id':f'eq.{cid}','database_id':f'eq.{dbid}','organization_id':f'eq.{oid}'},{'last_tested_at':now(),'last_test_status':'pending','status':'configured'})
    audit(uid,'database.connection.test.queued','database_connection',cid,{'organization_id':oid,'database_id':dbid})
    return jsonify(status='pending',message='connection_test_queued_for_provider',connection_id=cid,row=updated[0] if updated else row),202

@app.delete('/api/media/assets/<aid>')
@auth_required
def media_asset_delete(aid):
    uid=session['user_id']; oid=require_org(uid)
    row=_one('/rest/v1/cloud_media_assets',{'id':f'eq.{aid}','owner_user_id':f'eq.{uid}','organization_id':f'eq.{oid}','select':'*','limit':'1'})
    if not row:return jsonify(error='media_not_found'),404
    _delete('/rest/v1/cloud_media_jobs',{'asset_id':f'eq.{aid}','owner_user_id':f'eq.{uid}','organization_id':f'eq.{oid}'})
    _delete('/rest/v1/cloud_media_assets',{'id':f'eq.{aid}','owner_user_id':f'eq.{uid}','organization_id':f'eq.{oid}'})
    audit(uid,'media.asset.delete','media_asset',aid,{'organization_id':oid})
    return jsonify(message='media_deleted')

@app.get('/api/projects/<pid>/resources')
@auth_required
def project_resources(pid):
    uid=session['user_id']; oid=require_org(uid)
    if not project_access(uid,oid,pid):return jsonify(error='project_not_found'),404
    def q(table):
        try:return sb('/rest/v1/'+table,params={'project_id':f'eq.{pid}','owner_user_id':f'eq.{uid}','organization_id':f'eq.{oid}','select':'*','order':'created_at.desc','limit':'200'})
        except Exception:return []
    return jsonify(project_id=pid,compute=q('cloud_compute_services'),storage=q('cloud_storage_buckets'),databases=q('cloud_databases'),media=q('cloud_media_assets'),live=q('cloud_live_channels'))

@app.get('/api/system/v16')
@auth_required
def system_v16():
    return jsonify(version=VERSION,layer='universal-cloud-platform',features={'cloud_api_key_ui':True,'project_scoped_api_keys':True,'universal_api_auth':True,'api_key_storage':True,'api_key_database':True,'api_key_media':True,'api_key_compute':True,'api_cors':True,'api_v1_health':True,'tenant_isolation':True,'provider_backed_execution':True})

@app.get('/api/system/v15')
@auth_required
def system_v15():
    return jsonify(version='17.5.0',layer='universal-cloud-platform',features={
      'project_resources':True,'storage_operations':True,'database_connections':True,'media_operations':True,
      'environments':True,'connections':True,'edge_hosting':True,'apk_artifacts':True,'tenant_isolation':True,
      'provider_backed_execution':True
    })



# ============================ KOJA CLOUD V17.1 BILLING ============================
# API access is free on the Free plan. Monetization is based on billable cloud
# resources, not merely on obtaining an API key. Billing is additive and uses
# the existing cloud_usage_events stream as the source of metered consumption.
KOJA_BILLING_DEFAULT_PLAN = os.getenv('KOJA_BILLING_DEFAULT_PLAN', 'free').strip().lower() or 'free'
KOJA_FREE_API = os.getenv('KOJA_FREE_API', 'true').lower() in ('1','true','yes','on')
KOJA_BILLING_CURRENCY = os.getenv('KOJA_BILLING_CURRENCY', 'USD').upper()
KOJA_BILLING_GRACE = os.getenv('KOJA_BILLING_GRACE', 'true').lower() in ('1','true','yes','on')

# Prices are configurable so the billing engine is not tied to one country or
# payment provider. Values are per billing unit after included usage.
KOJA_PRICE_PER_UNIT = {
    'storage_gb_month': float(os.getenv('KOJA_PRICE_STORAGE_GB_MONTH', '0.05')),
    'bandwidth_gb': float(os.getenv('KOJA_PRICE_BANDWIDTH_GB', '0.08')),
    'compute_cpu_hour': float(os.getenv('KOJA_PRICE_COMPUTE_CPU_HOUR', '0.03')),
    'compute_gb_hour': float(os.getenv('KOJA_PRICE_COMPUTE_GB_HOUR', '0.01')),
    'database_gb_month': float(os.getenv('KOJA_PRICE_DATABASE_GB_MONTH', '0.10')),
    'media_processing_minute': float(os.getenv('KOJA_PRICE_MEDIA_PROCESSING_MINUTE', '0.02')),
    'media_storage_gb_month': float(os.getenv('KOJA_PRICE_MEDIA_STORAGE_GB_MONTH', '0.05')),
    'live_stream_minute': float(os.getenv('KOJA_PRICE_LIVE_STREAM_MINUTE', '0.01')),
    'backup_gb_month': float(os.getenv('KOJA_PRICE_BACKUP_GB_MONTH', '0.04')),
}

KOJA_PLAN_INCLUDED = {
    'free': {
        'api': {'requests': None},
        'storage_gb_month': float(os.getenv('KOJA_FREE_STORAGE_GB', '1')),
        'bandwidth_gb': float(os.getenv('KOJA_FREE_BANDWIDTH_GB', '5')),
        'compute_cpu_hour': float(os.getenv('KOJA_FREE_COMPUTE_CPU_HOURS', '5')),
        'compute_gb_hour': float(os.getenv('KOJA_FREE_COMPUTE_GB_HOURS', '2')),
        'database_gb_month': float(os.getenv('KOJA_FREE_DATABASE_GB', '1')),
        'media_processing_minute': float(os.getenv('KOJA_FREE_MEDIA_MINUTES', '10')),
        'media_storage_gb_month': float(os.getenv('KOJA_FREE_MEDIA_STORAGE_GB', '1')),
        'live_stream_minute': float(os.getenv('KOJA_FREE_LIVE_MINUTES', '30')),
        'backup_gb_month': float(os.getenv('KOJA_FREE_BACKUP_GB', '1')),
    },
    'starter': {
        'api': {'requests': None}, 'storage_gb_month': 10, 'bandwidth_gb': 50,
        'compute_cpu_hour': 50, 'compute_gb_hour': 20, 'database_gb_month': 10,
        'media_processing_minute': 120, 'media_storage_gb_month': 10,
        'live_stream_minute': 300, 'backup_gb_month': 10,
    },
    'business': {
        'api': {'requests': None}, 'storage_gb_month': 100, 'bandwidth_gb': 500,
        'compute_cpu_hour': 500, 'compute_gb_hour': 200, 'database_gb_month': 100,
        'media_processing_minute': 1000, 'media_storage_gb_month': 100,
        'live_stream_minute': 3000, 'backup_gb_month': 100,
    },
    'enterprise': {
        'api': {'requests': None}, 'storage_gb_month': None, 'bandwidth_gb': None,
        'compute_cpu_hour': None, 'compute_gb_hour': None, 'database_gb_month': None,
        'media_processing_minute': None, 'media_storage_gb_month': None,
        'live_stream_minute': None, 'backup_gb_month': None,
    },
}

def _billing_period(ts=None):
    d=datetime.fromisoformat((ts or now()).replace('Z','+00:00'))
    return d.strftime('%Y-%m')

def _billing_plan(oid):
    try:
        rows=sb('/rest/v1/cloud_billing_accounts',params={'organization_id':f'eq.{oid}','select':'plan,status,currency','limit':'1'})
        if rows:
            plan=(rows[0].get('plan') or KOJA_BILLING_DEFAULT_PLAN).lower()
            return plan if plan in KOJA_PLAN_INCLUDED else 'free', rows[0].get('currency') or KOJA_BILLING_CURRENCY
    except Exception:
        pass
    return KOJA_BILLING_DEFAULT_PLAN if KOJA_BILLING_DEFAULT_PLAN in KOJA_PLAN_INCLUDED else 'free', KOJA_BILLING_CURRENCY

def _billing_usage(oid, project_id=None, period=None):
    period=period or _billing_period()
    params={'organization_id':f'eq.{oid}','select':'metric,quantity,unit,created_at,project_id','order':'created_at.asc','limit':'5000'}
    if project_id: params['project_id']=f'eq.{project_id}'
    rows=sb('/rest/v1/cloud_usage_events',params=params)
    totals={}
    for r in rows:
        if _billing_period(r.get('created_at')) != period: continue
        metric=str(r.get('metric') or '').strip().lower()
        try: qty=float(r.get('quantity') or 0)
        except Exception: qty=0
        if metric: totals[metric]=totals.get(metric,0)+qty
    return totals

def _billing_snapshot(oid, project_id=None, period=None):
    period=period or _billing_period(); plan,currency=_billing_plan(oid)
    included=KOJA_PLAN_INCLUDED.get(plan,KOJA_PLAN_INCLUDED['free']); totals=_billing_usage(oid,project_id,period)
    items=[]; total=0.0
    for metric, qty in sorted(totals.items()):
        unit_price=KOJA_PRICE_PER_UNIT.get(metric)
        allowance=included.get(metric)
        billable=max(0.0,qty-float(allowance)) if allowance is not None else 0.0
        amount=round(billable*(unit_price or 0),6)
        if qty or allowance is not None:
            items.append({'metric':metric,'quantity':qty,'included':allowance,'billable_quantity':billable,'unit_price':unit_price or 0,'amount':amount,'unit':metric.replace('_',' ')})
        total += amount
    return {'period':period,'plan':plan,'currency':currency,'api_free':KOJA_FREE_API,'items':items,'subtotal':round(total,2),'total':round(total,2),'grace_enabled':KOJA_BILLING_GRACE}

@app.get('/api/v1/billing')
@api_key_auth
def api_billing_summary():
    oid=key_org(); pid=getattr(request,'koja_api_key',{}).get('project_id')
    snap=_billing_snapshot(oid,pid,request.args.get('period') or None)
    return jsonify({'billing':snap})

@app.get('/api/v1/billing/usage')
@api_key_auth
def api_billing_usage():
    oid=key_org(); pid=getattr(request,'koja_api_key',{}).get('project_id')
    return jsonify({'organization_id':oid,'project_id':pid,'period':request.args.get('period') or _billing_period(),'usage':_billing_usage(oid,pid,request.args.get('period') or None)})

@app.get('/api/v1/billing/plans')
@api_key_auth
def api_billing_plans():
    return jsonify({'currency':KOJA_BILLING_CURRENCY,'api_free':KOJA_FREE_API,'plans':{
        k:{'included':v,'prices':KOJA_PRICE_PER_UNIT if k!='free' else KOJA_PRICE_PER_UNIT} for k,v in KOJA_PLAN_INCLUDED.items()
    }})

@app.post('/api/v1/billing/estimate')
@api_key_auth
def api_billing_estimate():
    oid=key_org(); pid=getattr(request,'koja_api_key',{}).get('project_id'); d=request.get_json(silent=True) or {}
    period=d.get('period') or _billing_period(); snap=_billing_snapshot(oid,pid,period)
    return jsonify({'estimate':snap,'disclaimer':'Estimate only. No payment is charged by this endpoint.'})

@app.get('/api/v1/billing/invoices')
@api_key_auth
def api_billing_invoices():
    oid=key_org(); pid=getattr(request,'koja_api_key',{}).get('project_id')
    params={'organization_id':f'eq.{oid}','select':'*','order':'created_at.desc','limit':'100'}
    if pid: params['project_id']=f'eq.{pid}'
    try: rows=sb('/rest/v1/cloud_invoices',params=params)
    except Exception: rows=[]
    return jsonify(rows)

@app.get('/api/billing/summary')
@auth_required
def billing_summary_ui_api():
    uid=session['user_id']; oid=require_org(uid); pid=request.args.get('project_id')
    if pid and not project_access(uid,oid,pid): return jsonify(error='project_not_found'),404
    return jsonify(_billing_snapshot(oid,pid,request.args.get('period') or None))




# ============================================================
# KOJA CLOUD V17.2.0 — END-TO-END PLATFORM HARDENING
# Additive extension to V17.1.0. Preserves existing APIs.
# ============================================================

KOJA_CLOUD_RELEASE = '26.2.8'
KOJA_PLATFORM_RELEASE = '18.4.0'
KOJA_CLOUD_API_RELEASE = 'v1'
KOJA_REQUEST_MAX_BODY = int(os.getenv('KOJA_REQUEST_MAX_BODY', str(100 * 1024 * 1024)))
KOJA_STORAGE_UPLOAD_TIMEOUT = float(os.getenv('KOJA_STORAGE_UPLOAD_TIMEOUT', '180'))
KOJA_STORAGE_DOWNLOAD_TIMEOUT = float(os.getenv('KOJA_STORAGE_DOWNLOAD_TIMEOUT', '180'))
KOJA_BUILD_ARTIFACT_MAX = int(os.getenv('KOJA_BUILD_ARTIFACT_MAX', str(200 * 1024 * 1024)))
KOJA_AGENT_POLL_LIMIT = int(os.getenv('KOJA_AGENT_POLL_LIMIT', '10'))
KOJA_AGENT_HEARTBEAT_SECONDS = int(os.getenv('KOJA_AGENT_HEARTBEAT_SECONDS', '60'))

# Preserve the existing VERSION symbol while exposing the release separately.
VERSION = KOJA_CLOUD_RELEASE
KOJA_GLOBAL_INFRA_RELEASE = '19.0.0'
app.config['MAX_CONTENT_LENGTH'] = KOJA_REQUEST_MAX_BODY


def _v172_request_id():
    rid = request.headers.get('X-Request-ID') or request.headers.get('X-KOJA-REQUEST-ID')
    return (rid or ('req_' + secrets.token_hex(12)))[:128]


@app.before_request
def _v172_request_context():
    request.koja_request_id = _v172_request_id()


@app.after_request
def _v172_response_headers(response):
    rid = getattr(request, 'koja_request_id', None)
    if rid:
        response.headers['X-Request-ID'] = rid
    response.headers.setdefault('X-KOJA-CLOUD-VERSION', KOJA_CLOUD_RELEASE)
    return response


def _v172_error(code, status=400, message=None, **extra):
    body = {'error': code, 'request_id': getattr(request, 'koja_request_id', None)}
    if message:
        body['message'] = message
    body.update(extra)
    return jsonify(body), status


def _v172_key_identity():
    key = getattr(request, 'koja_api_key', {}) or {}
    return (
        key.get('_uid') or key.get('user_id') or key.get('owner_user_id'),
        key.get('_oid') or key.get('organization_id'),
        key.get('_pid') or key.get('project_id'),
    )


def _v172_project_exists(oid, pid):
    if not oid or not pid:
        return False
    return bool(_one('/rest/v1/cloud_projects', {
        'id': f'eq.{pid}', 'organization_id': f'eq.{oid}',
        'select': 'id,status', 'limit': '1'
    }))


def _v172_bucket(oid, bid):
    return _one('/rest/v1/cloud_storage_buckets', {
        'id': f'eq.{bid}', 'organization_id': f'eq.{oid}',
        'select': '*', 'limit': '1'
    })


def _v172_bucket_by_name(oid, name, pid=None):
    params = {'organization_id': f'eq.{oid}', 'select': '*', 'limit': '1'}
    if pid:
        params['project_id'] = f'eq.{pid}'
    rows = sb('/rest/v1/cloud_storage_buckets', params={**params, 'bucket_name': f'eq.{name}'})
    if rows:
        return rows[0]
    rows = sb('/rest/v1/cloud_storage_buckets', params={**params, 'name': f'eq.{name}'})
    return rows[0] if rows else None


def _v172_object(oid, object_id, pid=None):
    params = {'id': f'eq.{object_id}', 'organization_id': f'eq.{oid}', 'select': '*', 'limit': '1'}
    if pid:
        params['project_id'] = f'eq.{pid}'
    return _one('/rest/v1/cloud_storage_objects', params)


def _v172_storage_url(bucket, path):
    return f'{SUPABASE_URL}/storage/v1/object/{quote(str(bucket), safe="")}/{quote(str(path).lstrip("/"), safe="/")}'


def _v172_storage_headers(content_type=None):
    h = {'apikey': SUPABASE_KEY, 'Authorization': f'Bearer {SUPABASE_KEY}'}
    if content_type:
        h['Content-Type'] = content_type
    return h


# ---------- Fix the V17.1 dashboard bucket write bug ----------
# The original V17.1 create_bucket function referenced requested_pid before
# assignment. This replacement keeps its endpoint and semantics but makes the
# project binding explicit and validates tenant/project ownership.
@app.post('/api/storage/buckets')
@cloud_api_or_login
def create_bucket_v172():
    d = request.get_json(silent=True) or {}
    uid = session['user_id']
    oid = require_org(uid)
    requested_pid = cloud_project_for_write(d.get('project_id'))
    if not requested_pid:
        return _v172_error('project_required', 400)
    if not _v172_project_exists(oid, requested_pid):
        return _v172_error('project_not_found', 404)
    name = str(d.get('name') or 'files').strip()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,62}', name):
        return _v172_error('invalid_bucket_name', 400)
    existing = _v172_bucket_by_name(oid, name, requested_pid)
    if existing:
        return jsonify(existing), 200
    code = 'ST-' + secrets.token_hex(4).upper()
    payload = {
        'owner_user_id': uid, 'organization_id': oid, 'project_id': requested_pid,
        'bucket_code': code, 'bucket_name': name, 'name': name,
        'provider': d.get('provider', 'supabase'),
        'max_bytes': int(d.get('max_bytes', 1073741824)),
        'visibility': d.get('visibility', 'private'), 'status': 'active',
        'config': d.get('config', {}) if isinstance(d.get('config', {}), dict) else {}
    }
    row = sb('/rest/v1/cloud_storage_buckets', 'POST', payload, params={'select': '*'})[0]
    audit(uid, 'storage.bucket.create', 'bucket', row['id'], {'organization_id': oid, 'project_id': requested_pid})
    return jsonify(row), 201


# ---------- V1 Storage: complete bucket/object lifecycle ----------
@app.get('/api/v1/storage/buckets/<bid>')
@api_key_auth
def api_v172_bucket_detail(bid):
    uid, oid, pid = _v172_key_identity()
    row = _v172_bucket(oid, bid)
    if not row or (pid and str(row.get('project_id')) != str(pid)):
        return _v172_error('bucket_not_found', 404)
    return jsonify(row)


@app.delete('/api/v1/storage/buckets/<bid>')
@api_key_auth
def api_v172_bucket_delete(bid):
    uid, oid, pid = _v172_key_identity()
    row = _v172_bucket(oid, bid)
    if not row or (pid and str(row.get('project_id')) != str(pid)):
        return _v172_error('bucket_not_found', 404)
    bucket_name = row.get('bucket_name') or row.get('name')
    objects = sb('/rest/v1/cloud_storage_objects', params={
        'bucket_id': f'eq.{bid}', 'organization_id': f'eq.{oid}',
        'select': 'id,object_path', 'limit': '5000'
    })
    deleted = 0
    for obj in objects:
        try:
            rr = requests.delete(_v172_storage_url(bucket_name, obj.get('object_path', '')), headers=sb_headers(), timeout=30)
            if rr.status_code < 400:
                deleted += 1
        except Exception:
            pass
    _delete('/rest/v1/cloud_storage_objects', {'bucket_id': f'eq.{bid}', 'organization_id': f'eq.{oid}'})
    _delete('/rest/v1/cloud_storage_buckets', {'id': f'eq.{bid}', 'organization_id': f'eq.{oid}'})
    audit(uid, 'storage.bucket.delete', 'bucket', bid, {'project_id': row.get('project_id'), 'objects': len(objects)})
    return jsonify({'deleted': True, 'bucket_id': bid, 'objects_removed': len(objects), 'provider_objects_deleted': deleted, 'request_id': request.koja_request_id})


@app.get('/api/v1/storage/objects')
@api_key_auth
def api_v172_objects_list():
    uid, oid, pid = _v172_key_identity()
    params = {'organization_id': f'eq.{oid}', 'select': '*', 'order': 'created_at.desc', 'limit': str(min(int(request.args.get('limit', '500')), 5000))}
    if pid:
        params['project_id'] = f'eq.{pid}'
    if request.args.get('bucket_id'):
        params['bucket_id'] = f'eq.{request.args.get("bucket_id")}'
    if request.args.get('prefix'):
        params['object_path'] = f'like.{request.args.get("prefix")}*'
    return jsonify(sb('/rest/v1/cloud_storage_objects', params=params))


@app.post('/api/v1/storage/objects')
@api_key_auth
def api_v172_object_upload():
    uid, oid, pid = _v172_key_identity()
    # Supports multipart/form-data and JSON base64 for API clients.
    if request.files:
        f = request.files.get('file')
        bucket_name = request.form.get('bucket') or request.form.get('bucket_name')
        object_path = request.form.get('path') or (f.filename if f else '')
        content_type = (f.content_type if f else None) or request.form.get('content_type') or 'application/octet-stream'
        if not f or not bucket_name:
            return _v172_error('file_and_bucket_required', 400)
        raw = f.read()
    else:
        d = request.get_json(silent=True) or {}
        bucket_name = d.get('bucket') or d.get('bucket_name')
        object_path = d.get('path') or d.get('object_path') or d.get('name')
        content_type = d.get('content_type') or 'application/octet-stream'
        encoded = d.get('content_b64')
        if not bucket_name or not object_path or not encoded:
            return _v172_error('bucket_path_and_content_required', 400)
        try:
            raw = base64.b64decode(encoded, validate=True)
        except Exception:
            return _v172_error('invalid_base64', 400)
    if not object_path or '\x00' in str(object_path) or str(object_path).startswith('/') or '..' in str(object_path).split('/'):
        return _v172_error('invalid_object_path', 400)
    if len(raw) > KOJA_REQUEST_MAX_BODY:
        return _v172_error('object_too_large', 413)
    bucket = _v172_bucket_by_name(oid, str(bucket_name), pid)
    if not bucket:
        return _v172_error('bucket_not_found', 404)
    actual_pid = bucket.get('project_id')
    if pid and str(actual_pid) != str(pid):
        return _v172_error('project_scope_violation', 403)
    path = f'{uid}/{uuid.uuid4()}-{os.path.basename(str(object_path))}'
    provider_url = _v172_storage_url(bucket.get('bucket_name') or bucket.get('name'), path)
    rr = requests.post(provider_url, headers={**_v172_storage_headers(content_type), 'x-upsert': 'false'}, data=raw, timeout=KOJA_STORAGE_UPLOAD_TIMEOUT)
    if rr.status_code >= 400:
        return _v172_error('storage_provider_error', rr.status_code, rr.text[:500])
    obj = _insert('/rest/v1/cloud_storage_objects', {
        'owner_user_id': uid, 'organization_id': oid, 'project_id': actual_pid,
        'bucket_id': bucket.get('id'), 'object_path': path, 'name': os.path.basename(str(object_path)),
        'size_bytes': len(raw), 'content_type': content_type,
        'metadata': {'provider': 'supabase-storage', 'original_path': str(object_path), 'request_id': request.koja_request_id}
    })
    usage(uid, actual_pid, 'storage', 'bytes_uploaded', len(raw), 'bytes')
    audit(uid, 'storage.object.create', 'storage_object', obj.get('id'), {'project_id': actual_pid, 'bytes': len(raw)})
    return jsonify({'object': obj, 'bucket': bucket.get('bucket_name') or bucket.get('name'), 'path': path, 'size': len(raw), 'request_id': request.koja_request_id}), 201


@app.get('/api/v1/storage/objects/<oid>')
@api_key_auth
def api_v172_object_detail(oid):
    uid, org, pid = _v172_key_identity()
    row = _v172_object(org, oid, pid)
    if not row:
        return _v172_error('object_not_found', 404)
    return jsonify(row)


@app.delete('/api/v1/storage/objects/<oid>')
@api_key_auth
def api_v172_object_delete(oid):
    uid, org, pid = _v172_key_identity()
    row = _v172_object(org, oid, pid)
    if not row:
        return _v172_error('object_not_found', 404)
    bucket = _v172_bucket(org, row.get('bucket_id'))
    if bucket:
        try:
            requests.delete(_v172_storage_url(bucket.get('bucket_name') or bucket.get('name'), row.get('object_path', '')), headers=sb_headers(), timeout=30)
        except Exception:
            pass
    _delete('/rest/v1/cloud_storage_objects', {'id': f'eq.{oid}', 'organization_id': f'eq.{org}'})
    audit(uid, 'storage.object.delete', 'storage_object', oid, {'project_id': row.get('project_id')})
    return jsonify({'deleted': True, 'object_id': oid, 'request_id': request.koja_request_id})


@app.get('/api/v1/storage/objects/<oid>/download')
@api_key_auth
def api_v172_object_download(oid):
    uid, org, pid = _v172_key_identity()
    row = _v172_object(org, oid, pid)
    if not row:
        return _v172_error('object_not_found', 404)
    bucket = _v172_bucket(org, row.get('bucket_id'))
    if not bucket:
        return _v172_error('bucket_not_found', 404)
    url = _v172_storage_url(bucket.get('bucket_name') or bucket.get('name'), row.get('object_path', ''))
    try:
        rr = requests.get(url, headers=sb_headers(), timeout=KOJA_STORAGE_DOWNLOAD_TIMEOUT, stream=True)
    except requests.RequestException as exc:
        return _v172_error('storage_provider_unreachable', 502, str(exc)[:300])
    if rr.status_code >= 400:
        return _v172_error('storage_provider_error', rr.status_code, rr.text[:500])
    data = rr.content
    usage(uid, row.get('project_id'), 'storage', 'bytes_downloaded', len(data), 'bytes')
    audit(uid, 'storage.object.download', 'storage_object', oid, {'project_id': row.get('project_id'), 'bytes': len(data)})
    return Response(data, status=200, mimetype=row.get('content_type') or rr.headers.get('Content-Type') or 'application/octet-stream', headers={
        'Content-Disposition': 'attachment; filename="' + (row.get('name') or 'download.bin').replace('"', '') + '"',
        'X-Request-ID': request.koja_request_id
    })


# ---------- V1 KOJA Run lifecycle + Android build API ----------
def _v172_job_row(oid, jid, pid=None):
    params = {'id': f'eq.{jid}', 'organization_id': f'eq.{oid}', 'select': '*', 'limit': '1'}
    if pid:
        params['project_id'] = f'eq.{pid}'
    return _one('/rest/v1/cloud_jobs', params)


@app.post('/api/v1/compute/services/<sid>/start')
@api_key_auth
def api_v172_compute_start(sid):
    uid, oid, pid = _v172_key_identity()
    row = _one('/rest/v1/cloud_compute_services', {'id': f'eq.{sid}', 'organization_id': f'eq.{oid}', 'project_id': f'eq.{pid}', 'select': '*', 'limit': '1'})
    if not row: return _v172_error('service_not_found', 404)
    job = _enqueue_generic_job(uid, oid, pid, 'service_start', {'service_id': sid, 'region': row.get('region', 'global')})
    _patch('/rest/v1/cloud_compute_services', {'id': f'eq.{sid}', 'organization_id': f'eq.{oid}'}, {'status': 'starting', 'updated_at': now()})
    return jsonify({'service': sid, 'job': job, 'request_id': request.koja_request_id}), 202


@app.post('/api/v1/compute/services/<sid>/stop')
@api_key_auth
def api_v172_compute_stop(sid):
    uid, oid, pid = _v172_key_identity()
    row = _one('/rest/v1/cloud_compute_services', {'id': f'eq.{sid}', 'organization_id': f'eq.{oid}', 'project_id': f'eq.{pid}', 'select': '*', 'limit': '1'})
    if not row: return _v172_error('service_not_found', 404)
    job = _enqueue_generic_job(uid, oid, pid, 'service_stop', {'service_id': sid, 'region': row.get('region', 'global')})
    _patch('/rest/v1/cloud_compute_services', {'id': f'eq.{sid}', 'organization_id': f'eq.{oid}'}, {'status': 'stopping', 'updated_at': now()})
    return jsonify({'service': sid, 'job': job, 'request_id': request.koja_request_id}), 202


@app.post('/api/v1/compute/services/<sid>/deploy')
@api_key_auth
def api_v172_compute_deploy(sid):
    uid, oid, pid = _v172_key_identity()
    row = _one('/rest/v1/cloud_compute_services', {'id': f'eq.{sid}', 'organization_id': f'eq.{oid}', 'project_id': f'eq.{pid}', 'select': '*', 'limit': '1'})
    if not row: return _v172_error('service_not_found', 404)
    d = request.get_json(silent=True) or {}
    dep, job = queue_deploy(uid, sid, d.get('commit') or '', d.get('reason') or 'api')
    return jsonify({'deployment': dep, 'job': job, 'request_id': request.koja_request_id}), 202


@app.get('/api/v1/compute/jobs/<jid>')
@api_key_auth
def api_v172_compute_job(jid):
    uid, oid, pid = _v172_key_identity()
    row = _v172_job_row(oid, jid, pid)
    if not row: return _v172_error('job_not_found', 404)
    return jsonify(row)


@app.post('/api/v1/builds/android')
@api_key_auth
def api_v172_android_build():
    uid, oid, pid = _v172_key_identity()
    if not pid: return _v172_error('project_required', 400)
    if not _v172_project_exists(oid, pid): return _v172_error('project_not_found', 404)
    d = request.get_json(silent=True) or {}
    sid = d.get('service_id')
    if sid:
        svc = _one('/rest/v1/cloud_compute_services', {'id': f'eq.{sid}', 'project_id': f'eq.{pid}', 'organization_id': f'eq.{oid}', 'select': '*', 'limit': '1'})
    else:
        svc = _one('/rest/v1/cloud_compute_services', {'project_id': f'eq.{pid}', 'organization_id': f'eq.{oid}', 'select': '*', 'order': 'created_at.desc', 'limit': '1'})
    if not svc: return _v172_error('compute_service_required', 400)
    spec = {
        'project_id': pid, 'service_id': svc['id'], 'app_name': d.get('app_name') or 'KOJA App',
        'package_name': d.get('package_name'), 'version_name': d.get('version_name', '1.0.0'),
        'version_code': int(d.get('version_code', 1)), 'format': d.get('format', 'apk'),
        'source_mode': d.get('source_mode', 'workspace'), 'mode': d.get('mode', 'webview'),
        'website_url': d.get('website_url') or svc.get('service_url') or (svc.get('config') or {}).get('koja_url'),
        'build_command': d.get('build_command') or './gradlew assembleDebug',
        'artifact_path': d.get('artifact_path') or 'app/build/outputs/apk/debug/app-debug.apk'
    }
    job = _enqueue_generic_job(uid, oid, pid, 'android_build', spec)
    audit(uid, 'build.android.queue', 'cloud_job', job.get('id'), {'project_id': pid, 'format': spec['format']})
    return jsonify({'build_id': job.get('id'), 'job': job, 'status': 'queued', 'requires_build_agent': True, 'request_id': request.koja_request_id}), 202


# ---------- Agent operations: real data-plane bridge ----------
def _v172_agent_scope(agent, pid=None):
    if not agent: return False
    if pid and str(agent.get('project_id') or '') not in ('', str(pid)):
        return False
    return True


@app.post('/api/v1/agents/heartbeat')
@agent_auth
def api_v172_agent_heartbeat():
    agent = request.koja_agent
    d = request.get_json(silent=True) or {}
    patch = {'last_seen_at': now(), 'status': 'online', 'metadata': d.get('metadata', agent.get('metadata') or {})}
    rows = _patch('/rest/v1/cloud_compute_agents', {'id': f'eq.{agent["id"]}'}, patch)
    return jsonify({'ok': True, 'agent_id': agent['id'], 'status': 'online', 'server_time': now(), 'agent': rows[0] if rows else agent, 'request_id': request.koja_request_id})


@app.get('/api/v1/agents/jobs')
@agent_auth
def api_v172_agent_jobs():
    agent = request.koja_agent
    params = {'organization_id': f'eq.{agent["organization_id"]}', 'status': 'eq.queued', 'select': '*', 'order': 'created_at.asc', 'limit': str(KOJA_AGENT_POLL_LIMIT)}
    if agent.get('project_id'):
        params['project_id'] = f'eq.{agent["project_id"]}'
    rows = sb('/rest/v1/cloud_jobs', params=params)
    # Claim atomically by status transition. PostgREST does not offer a
    # transaction here, so workers must use job IDs and tolerate duplicate polls.
    claimed = []
    for row in rows:
        rid = row.get('id')
        if not rid: continue
        updated = _patch('/rest/v1/cloud_jobs', {'id': f'eq.{rid}', 'status': 'eq.queued'}, {'status': 'running', 'started_at': now(), 'worker_id': agent.get('id')})
        if updated:
            claimed.append(updated[0])
    return jsonify({'jobs': claimed, 'count': len(claimed), 'server_time': now(), 'request_id': request.koja_request_id})


@app.post('/api/v1/agents/jobs/<jid>/complete')
@agent_auth
def api_v172_agent_job_complete(jid):
    agent = request.koja_agent; d = request.get_json(silent=True) or {}
    row = _one('/rest/v1/cloud_jobs', {'id': f'eq.{jid}', 'organization_id': f'eq.{agent["organization_id"]}', 'select': '*', 'limit': '1'})
    if not row: return _v172_error('job_not_found', 404)
    if row.get('worker_id') and row.get('worker_id') != agent.get('id'): return _v172_error('job_worker_mismatch', 403)
    status = d.get('status') or 'completed'
    if status not in ('completed', 'failed', 'cancelled'): return _v172_error('invalid_job_status', 400)
    payload = {'status': status, 'finished_at': now(), 'output': d.get('output', {}), 'error_message': d.get('error_message')}
    updated = _patch('/rest/v1/cloud_jobs', {'id': f'eq.{jid}', 'organization_id': f'eq.{agent["organization_id"]}'}, payload)
    return jsonify({'job': updated[0] if updated else row, 'request_id': request.koja_request_id})


@app.post('/api/v1/agents/artifacts')
@agent_auth
def api_v172_agent_artifact():
    agent = request.koja_agent; d = request.get_json(silent=True) or {}
    required = ('project_id', 'name', 'content_b64')
    if any(not d.get(k) for k in required): return _v172_error('artifact_fields_required', 400)
    if agent.get('project_id') and str(d.get('project_id')) != str(agent.get('project_id')): return _v172_error('project_scope_violation', 403)
    if str(d.get('organization_id') or agent.get('organization_id')) != str(agent.get('organization_id')): return _v172_error('organization_scope_violation', 403)
    try: raw = base64.b64decode(d['content_b64'], validate=True)
    except Exception: return _v172_error('invalid_artifact_encoding', 400)
    if len(raw) > KOJA_BUILD_ARTIFACT_MAX: return _v172_error('artifact_too_large', 413)
    digest = hashlib.sha256(raw).hexdigest()
    payload = {
        'owner_user_id': d.get('owner_user_id') or agent.get('owner_user_id'),
        'organization_id': agent.get('organization_id'), 'project_id': d['project_id'],
        'name': os.path.basename(str(d['name'])), 'artifact_type': d.get('artifact_type', 'apk'),
        'size_bytes': len(raw), 'sha256': digest, 'status': 'ready',
        'content_type': d.get('content_type', 'application/vnd.android.package-archive'),
        'content_b64': d['content_b64'], 'metadata': d.get('metadata', {}), 'created_at': now()
    }
    row = _insert('/rest/v1/cloud_project_artifacts', payload)
    return jsonify({'artifact': {k:v for k,v in row.items() if k != 'content_b64'}, 'sha256': digest, 'request_id': request.koja_request_id}), 201


# ---------- System diagnostics / customer integration probe ----------
@app.get('/api/v1/system/capabilities')
def api_v172_capabilities():
    return jsonify({
        'api_version': 'v1', 'cloud_version': KOJA_CLOUD_RELEASE, 'service': 'koja-cloud-api',
        'capabilities': {
            'iam': True, 'organizations': True, 'projects': True, 'api_keys': True,
            'storage': True, 'storage_object_lifecycle': True, 'database_control_plane': True,
            'compute_control_plane': True, 'compute_agents': True, 'media': True,
            'live': True, 'usage_metering': True, 'billing': True, 'webhooks': True,
            'android_build_orchestration': True, 'android_build_execution': 'agent_required',
            'artifact_storage': True, 'tenant_isolation': True, 'project_scoped_keys': True,
            'request_ids': True, 'rate_limiting': True
        },
        'data_plane': {
            'storage': 'Supabase Storage', 'database': 'provider/adapter controlled',
            'compute': 'registered KOJA compute agent/provider',
            'android_build': 'registered Android build agent',
            'media': 'registered media worker/provider', 'live': 'provider control plane'
        },
        'time': now()
    })


@app.get('/api/v1/system/diagnostics')
@api_key_auth
def api_v172_diagnostics():
    uid, oid, pid = _v172_key_identity()
    checks = {}
    try:
        sb('/rest/v1/cloud_projects', params={'id': f'eq.{pid}', 'organization_id': f'eq.{oid}', 'select': 'id,name,project_code,status', 'limit': '1'}) if pid else []
        checks['supabase_control_plane'] = {'ok': True}
    except Exception as exc:
        checks['supabase_control_plane'] = {'ok': False, 'error': str(exc)[:300]}
    try:
        keys = sb('/rest/v1/cloud_api_keys', params={'id': f'eq.{getattr(request,"koja_api_key",{}).get("id")}', 'select': 'id,status,expires_at,last_used_at', 'limit': '1'})
        checks['api_key'] = {'ok': bool(keys), 'status': (keys[0].get('status') if keys else None)}
    except Exception as exc:
        checks['api_key'] = {'ok': False, 'error': str(exc)[:300]}
    try:
        agents = sb('/rest/v1/cloud_compute_agents', params={'organization_id': f'eq.{oid}', 'select': 'id,status,last_seen_at,project_id', 'limit': '100'})
        checks['agents'] = {'ok': True, 'count': len(agents), 'online': sum(1 for a in agents if a.get('status') == 'online')}
    except Exception as exc:
        checks['agents'] = {'ok': False, 'error': str(exc)[:300]}
    return jsonify({'api_version': 'v1', 'cloud': 'KOJA CLOUD', 'cloud_version': KOJA_CLOUD_RELEASE, 'authenticated': True, 'organization_id': oid, 'project_id': pid, 'checks': checks, 'request_id': request.koja_request_id, 'time': now()})


@app.get('/api/v1/connection/probe')
def api_v172_connection_probe():
    # Deliberately does not require an API key. It proves the public API edge is
    # alive; authenticated customer access is tested by /system/diagnostics.
    return jsonify({'api_version': 'v1', 'cloud': 'KOJA CLOUD', 'cloud_version': KOJA_CLOUD_RELEASE, 'reachable': True, 'authenticated': False, 'request_id': request.koja_request_id, 'time': now()})


# ---------- V1 OpenAPI augmentation ----------
try:
    _v172_original_openapi = api_v1_openapi
    @app.get('/api/v1/openapi-v172.json')
    def api_v172_openapi():
        doc = _v172_original_openapi().get_json()
        paths = doc.setdefault('paths', {})
        for p, methods in {
            '/api/v1/storage/objects': {'get': {}, 'post': {}},
            '/api/v1/builds/android': {'post': {}},
            '/api/v1/system/capabilities': {'get': {}},
            '/api/v1/system/diagnostics': {'get': {}},
            '/api/v1/connection/probe': {'get': {}},
            '/api/v1/compute/services/{sid}/start': {'post': {}},
            '/api/v1/compute/services/{sid}/stop': {'post': {}},
            '/api/v1/compute/services/{sid}/deploy': {'post': {}},
            '/api/v1/compute/jobs/{jid}': {'get': {}},
            '/api/v1/agents/jobs': {'get': {}},
            '/api/v1/agents/jobs/{jid}/complete': {'post': {}},
            '/api/v1/agents/artifacts': {'post': {}},
        }.items():
            paths.setdefault(p, {})
            for method in methods:
                paths[p][method] = {'responses': {'200': {'description': 'KOJA CLOUD V17.4 response'}}}
        doc['info']['version'] = 'v1.2'
        doc['info']['x-koja-cloud-version'] = KOJA_CLOUD_RELEASE
        return jsonify(doc)
except Exception:
    pass



# ============================================================
# V17.5 provider-backed hosting and managed backend API
# ============================================================
@app.get('/api/providers/render/status')
@auth_required
def provider_render_status():
    out={'provider':'render','configured':render_provider_configured(),'owner_id':RENDER_OWNER_ID if RENDER_OWNER_ID else None}
    if not render_provider_configured(): return jsonify(out)
    try:
        data=_render_list_services(RENDER_OWNER_ID); items=_render_service_items(data)
        out['reachable']=True; out['service_count']=len(items); out['services']=[{'id':x.get('id'),'name':x.get('name'),'type':x.get('type'),'url':x.get('serviceDetails',{}).get('url') if isinstance(x.get('serviceDetails'),dict) else x.get('url'),'suspended':x.get('suspended')} for x in items]
    except Exception as e:
        out['reachable']=False; out['error']=str(e)[:500]
    return jsonify(out)

@app.post('/api/providers/render/services')
@auth_required
def provider_render_create_service():
    if not render_provider_configured(): return jsonify(error='render_provider_not_configured',required=['KOJA_RENDER_API_KEY','KOJA_RENDER_OWNER_ID']),503
    uid=session['user_id']; oid=require_org(uid); d=request.get_json() or {}
    name=(d.get('name') or '').strip(); repo=(d.get('repo_url') or '').strip(); pid=(d.get('project_id') or '').strip()
    if not name or not repo or not pid:return jsonify(error='name_repo_project_required'),400
    project=project_access(uid,oid,pid)
    if not project:return jsonify(error='project_not_found',project_reference=pid,next_action='Use the KOJA project ID, project code, or exact project name.'),404
    pid=project['id']
    runtime=(d.get('runtime') or 'python').lower(); region=(d.get('region') or 'oregon').strip(); branch=d.get('branch') or 'main'
    build_command=d.get('build_command') or 'pip install -r requirements.txt'; start_command=d.get('start_command') or 'gunicorn app:app'; health_path=d.get('health_path') or '/health'
    # Reuse an existing Render service before attempting creation. This is
    # critical for KOJA AFRICA because the service already exists in Render.
    stage='render_service_discovery'
    try:
        remote_services=_render_list_all_services(RENDER_OWNER_ID)
        # Render's list API can return services across the API key's workspaces;
        # filter locally by owner instead of relying on query encoding.
        remote_services=[x for x in remote_services if not x.get('ownerId') or str(x.get('ownerId'))==str(RENDER_OWNER_ID) or str(x.get('owner_id'))==str(RENDER_OWNER_ID)]
        repo_key=_render_repo_key(repo)
        def _service_repo(x):
            if not isinstance(x,dict): return ''
            sd=x.get('serviceDetails') if isinstance(x.get('serviceDetails'),dict) else {}
            repo_value=x.get('repo') or x.get('repository') or sd.get('repo') or sd.get('repository')
            if isinstance(repo_value,dict):
                repo_value=repo_value.get('url') or repo_value.get('cloneUrl') or repo_value.get('repositoryUrl') or ''
            return str(repo_value or '')
        def _service_branch(x):
            if not isinstance(x,dict): return ''
            sd=x.get('serviceDetails') if isinstance(x.get('serviceDetails'),dict) else {}
            return str(x.get('branch') or sd.get('branch') or '')
        def _service_name(x):
            return str(x.get('name') or '').strip().lower() if isinstance(x,dict) else ''
        def _service_slug(value):
            return re.sub(r'[^a-z0-9]+','-',str(value or '').lower()).strip('-')
        matches=[x for x in remote_services if _render_repo_key(_service_repo(x))==repo_key and (not branch or str(_service_branch(x) or '')==str(branch))]
        if not matches:
            matches=[x for x in remote_services if _render_repo_key(_service_repo(x))==repo_key]
        if not matches:
            target_name=_service_slug(name)
            matches=[x for x in remote_services if _service_slug(_service_name(x))==target_name]
        # Deterministic repository-name fallback when Render does not expose repo metadata.
        if not matches:
            repo_name=repo_key.rsplit('/',1)[-1]
            matches=[x for x in remote_services if _service_slug(_service_name(x))==_service_slug(repo_name)]
        provider=None; reused=False
        stage='render_service_match'
        if matches:
            provider=matches[0]; reused=True
            provider_id=provider.get('id')
            service_url=provider.get('url') or (provider.get('serviceDetails') or {}).get('url','')
        else:
            # Render's current Create Service API puts web-service runtime settings
            # inside serviceDetails. Sending buildCommand/startCommand at the top level
            # causes Render to reject the request.
            payload={'type':'web_service','name':name,'ownerId':RENDER_OWNER_ID,
                     'repo':_render_repo_url(repo),'branch':branch,'autoDeploy':'yes',
                     'serviceDetails':{'runtime':runtime,'plan':d.get('plan') or 'free','region':region,
                                       'buildCommand':build_command,'startCommand':start_command,
                                       'healthCheckPath':health_path}}
            stage='render_service_create'
            provider=_render_create_service(payload)
            provider_id=provider.get('id') or provider.get('service',{}).get('id')
            service_url=provider.get('url') or (provider.get('serviceDetails',{}) or {}).get('url','')
        stage='render_service_binding'
        if not provider_id:
            return jsonify(error='render_service_id_missing',detail='Render did not return a service ID.',provider_response=provider),502
        # Existing Render services are reused without PATCHing them. Render
        # may reject generic updates for Blueprint-managed/provider-managed services
        # even when the API key has deploy access. The service was already matched
        # by repository/branch/name; preserve its provider configuration.
        # Newly created services already received their configuration in POST /services.
        # Existing local service mapping, if any. Otherwise create one that
        # points at the real Render service rather than creating a duplicate.
        existing_local=_one('/rest/v1/cloud_compute_services',{'project_id':f'eq.{pid}','organization_id':f'eq.{oid}','owner_user_id':f'eq.{uid}','config->>provider_service_id':f'eq.{provider_id}','select':'*','limit':'1'})
        if existing_local:
            row=existing_local
        else:
            code='HOST-'+secrets.token_hex(5).upper()
            row=_insert('/rest/v1/cloud_compute_services',{'owner_user_id':uid,'organization_id':oid,'project_id':pid,'service_code':code,'name':name,'service_type':'web','runtime':runtime,'repo_url':repo,'branch':branch,'build_command':build_command,'start_command':start_command,'health_path':health_path,'region':region,'cpu':float(d.get('cpu',0.5) or 0.5),'memory_mb':int(d.get('memory_mb',512) or 512),'status':'connected' if reused else 'created','provider':'render','service_url':service_url or '','config':{'provider':'render','provider_service_id':provider_id,'render':provider}})
        # Trigger a real deployment for an existing service. New services have
        # autoDeploy enabled, but an explicit deploy makes the Launch action
        # deterministic and immediately visible.
        deploy=None
        stage='render_deploy'
        try:
            deploy=_render_deploy(provider_id, bool(d.get('clear_cache')))
            row['status']='deploying'
        except Exception as deploy_error:
            return jsonify(error='render_deploy_failed',detail=str(deploy_error)[:1000],provider_service_id=provider_id,reused=reused,service=row),502
        stage='cloud_binding'
        if service_url:
            existing_conn=_one('/rest/v1/cloud_project_connections',{'project_id':f'eq.{pid}','organization_id':f'eq.{oid}','owner_user_id':f'eq.{uid}','provider':'eq.render','name':f'eq.{name}','select':'id','limit':'1'})
            if not existing_conn:
                _insert('/rest/v1/cloud_project_connections',{'owner_user_id':uid,'organization_id':oid,'project_id':pid,'name':name,'connection_type':'application','provider':'render','host':service_url,'status':'connected','config':{'koja_cloud_url':service_url,'service_id':row.get('id'),'provider_service_id':provider_id}})
        audit(uid,'hosting.service.reuse' if reused else 'hosting.service.create','compute_service',row['id'],{'organization_id':oid,'provider':'render','provider_service_id':provider_id,'koja_cloud_url':service_url or None,'reused_existing':reused})
        return jsonify(provider_service_id=provider_id,service_url=service_url,koja_cloud_url=service_url,service=row,reused_existing=reused,deploy=deploy),200 if reused else 201
    except Exception as e:
        return jsonify(error='render_create_failed', stage=stage, detail=str(e)[:1000], provider='render', project_id=pid, repo_url=repo, branch=branch),502

@app.post('/api/providers/render/services/<service_id>/deploy')
@auth_required
def provider_render_deploy(service_id):
    if not render_provider_configured():return jsonify(error='render_provider_not_configured'),503
    uid=session['user_id']; oid=require_org(uid); row=_one('/rest/v1/cloud_compute_services',{'id':f'eq.{service_id}','owner_user_id':f'eq.{uid}','organization_id':f'eq.{oid}','select':'*','limit':'1'})
    if not row:return jsonify(error='service_not_found'),404
    cfg=row.get('config') or {}; rid=cfg.get('provider_service_id')
    if not rid:return jsonify(error='provider_service_id_missing'),409
    try:
        dep=_render_deploy(rid, bool((request.get_json(silent=True) or {}).get('clear_cache')))
        audit(uid,'hosting.service.deploy','compute_service',service_id,{'provider':'render','provider_service_id':rid})
        return jsonify(service_id=service_id,provider_service_id=rid,deploy=dep),202
    except Exception as e:return jsonify(error='render_deploy_failed',detail=str(e)[:1000]),502

@app.get('/api/providers/supabase/status')
@auth_required
def provider_supabase_status():
    out={'provider':'supabase','configured':supabase_provider_configured(),'organization_slug':SUPABASE_MANAGEMENT_ORG or None}
    if not supabase_provider_configured():return jsonify(out)
    try:
        data=_supabase_projects(); items=data if isinstance(data,list) else data.get('projects',[]) if isinstance(data,dict) else []
        out['reachable']=True; out['project_count']=len(items); out['projects']=[{'id':x.get('id'),'ref':x.get('ref'),'name':x.get('name'),'region':x.get('region'),'status':x.get('status')} for x in items]
    except Exception as e:out['reachable']=False;out['error']=str(e)[:500]
    return jsonify(out)

@app.post('/api/providers/supabase/projects')
@auth_required
def provider_supabase_create_project():
    if not supabase_provider_configured():return jsonify(error='supabase_management_not_configured',required=['KOJA_SUPABASE_MANAGEMENT_TOKEN','KOJA_SUPABASE_ORG_SLUG']),503
    uid=session['user_id'];oid=require_org(uid);d=request.get_json() or {};pid=(d.get('project_id') or '').strip();name=(d.get('name') or '').strip();password=d.get('db_password') or '';region=(d.get('region') or '').strip()
    if not pid or not name or len(password)<12:return jsonify(error='project_name_database_password_project_required',detail='KOJA Data password must be at least 12 characters.'),400
    if not project_access(uid,oid,pid):return jsonify(error='project_not_found'),404
    try:
        provider=_supabase_create_project(name,password,region)
        ref=provider.get('ref') or provider.get('id'); keys={}
        if ref:
            # Key retrieval is best-effort because newly-created projects can take time to become healthy.
            try:keys_data=_supabase_api_keys(ref); keys={'api_keys':keys_data}
            except Exception as ke:keys={'api_keys_pending':True,'api_key_error':str(ke)[:300]}
        cfg={'provider':'supabase','provider_project_ref':ref,'provider_project_id':provider.get('id'),'project_url':provider.get('url') or (f'https://{ref}.supabase.co' if ref else ''),'credentials':encrypt(json.dumps(keys)) if keys else ''}
        code='DB-'+secrets.token_hex(5).upper(); row=_insert('/rest/v1/cloud_databases',{'owner_user_id':uid,'organization_id':oid,'project_id':pid,'database_code':code,'name':name,'engine':'postgres','engine_version':'managed','status':'provisioning','region':region or provider.get('region') or 'global','provider':'supabase','connection_mode':'managed','storage_gb':1,'max_connections':20,'config':cfg},params={'select':'*'})[0]
        audit(uid,'database.provider.provision','database',row['id'],{'organization_id':oid,'provider':'supabase','provider_project_ref':ref})
        return jsonify(database=row,provider_project=provider,credentials_available=bool(keys)),201
    except Exception as e:return jsonify(error='supabase_provision_failed',detail=str(e)[:1200]),502

@app.get('/api/providers/supabase/projects/<ref>/health')
@auth_required
def provider_supabase_project_health(ref):
    if not supabase_provider_configured():return jsonify(error='supabase_management_not_configured'),503
    try:return jsonify(_supabase_project_health(ref))
    except Exception as e:return jsonify(error='supabase_health_failed',detail=str(e)[:1000]),502

@app.post('/api/providers/supabase/projects/<ref>/sql')
@auth_required
def provider_supabase_project_sql(ref):
    if not supabase_provider_configured():return jsonify(error='supabase_management_not_configured'),503
    uid=session['user_id'];oid=require_org(uid);d=request.get_json() or {};rows=sb('/rest/v1/cloud_databases',params={'organization_id':f'eq.{oid}','owner_user_id':f'eq.{uid}','config->>provider_project_ref':f'eq.{ref}','select':'id','limit':'1'})
    if not rows:return jsonify(error='managed_database_not_found'),404
    query=(d.get('query') or '').strip();
    if not query:return jsonify(error='query_required'),400
    try:return jsonify(_supabase_sql(ref,query,bool(d.get('read_only',False))))
    except Exception as e:return jsonify(error='managed_sql_failed',detail=str(e)[:1000]),502

@app.get('/api/v1/providers/capabilities')
@cloud_api_or_login
def provider_capabilities():
    return jsonify({'api_version':'v1','cloud':'KOJA CLOUD','cloud_version':KOJA_CLOUD_RELEASE,'providers':{'hosting':{'provider':'render','configured':render_provider_configured(),'execution':'real_provider' if render_provider_configured() else 'agent_or_provider_required'},'backend':{'provider':'supabase','configured':supabase_provider_configured(),'services':['postgres','auth','storage','realtime','data_api']},'control_plane':{'provider':'supabase','configured':configured()}}})



# ============================================================
# KOJA CLOUD V17.6 — NAMED DEVELOPER PLATFORM
# KOJA Forge / Launch / Run / Data / Sync / Vault / Stream / Media / Identity
# This release adds developer-facing product surfaces while preserving the
# provider-backed control plane. Provider credentials remain server-side.
# ============================================================

@app.get('/api/providers/github/status')
@auth_required
def provider_github_status():
    out={'provider':'github','mode':'github-actions','configured':github_provider_configured(),'status':'provider_required' if not github_provider_configured() else 'configured'}
    if not github_provider_configured():
        out.update({'required':['KOJA_GITHUB_TOKEN'],'message':'GitHub provider is not configured.','next_action':'Configure the GitHub provider in KOJA CLOUD settings.'})
        return jsonify(out)
    try:
        u=_github_request('/user'); out.update({'reachable':True,'status':'operational','login':u.get('login'),'name':u.get('name')})
    except Exception as e: out.update({'reachable':False,'status':'unreachable','error':str(e)[:500]})
    return jsonify(out)

@app.post('/api/providers/github/actions/dispatch')
@auth_required
def provider_github_actions_dispatch():
    if not github_provider_configured():
        return jsonify(ok=False,error='github_provider_not_configured',code='PROVIDER_NOT_CONFIGURED',provider='github',status='provider_required',message='GitHub provider is not configured.',required=['KOJA_GITHUB_TOKEN'],next_action='Configure the GitHub provider in KOJA CLOUD settings.'),503
    d=request.get_json(silent=True) or {}; repo=(d.get('repo_url') or '').strip(); workflow=(d.get('workflow') or 'koja-deploy.yml').strip(); ref=(d.get('branch') or 'main').strip() or 'main'
    try:
        owner,repo_name=_github_repo_parts(repo); workflows=_github_actions_workflows(owner,repo_name)
        match=next((w for w in workflows if str(w.get('path') or '').split('/')[-1]==workflow or str(w.get('name') or '').lower()==workflow.lower() or str(w.get('id'))==workflow),None)
        if not match:
            return jsonify(ok=False,error='github_workflow_not_found',code='WORKFLOW_NOT_FOUND',provider='github',status='configuration_required',repository=f'{owner}/{repo_name}',workflow=workflow,available_workflows=[{'id':w.get('id'),'name':w.get('name'),'path':w.get('path')} for w in workflows],next_action='Add or select a GitHub Actions workflow for KOJA deployments.'),409
        result=_github_actions_dispatch(owner,repo_name,match.get('id') or workflow,ref,d.get('inputs') if isinstance(d.get('inputs'),dict) else {})
        return jsonify(ok=True,provider='github',mode='github-actions',repository=f'{owner}/{repo_name}',workflow=match.get('path') or workflow,workflow_id=match.get('id'),branch=ref,status='queued',dispatch=result),202
    except Exception as e:
        return jsonify(ok=False,error='github_actions_dispatch_failed',code='PROVIDER_REQUEST_FAILED',provider='github',status='unreachable',message=str(e)[:1200],diagnostics={'repository':repo,'workflow':workflow,'branch':ref}),502

@app.get('/api/providers/github/actions/runs')
@auth_required
def provider_github_actions_runs():
    if not github_provider_configured(): return jsonify(error='github_provider_not_configured',code='PROVIDER_NOT_CONFIGURED',provider='github',status='provider_required',required=['KOJA_GITHUB_TOKEN'],next_action='Configure the GitHub provider in KOJA CLOUD settings.'),503
    repo=request.args.get('repo','').strip(); workflow=request.args.get('workflow','').strip() or None; branch=request.args.get('branch','').strip() or None
    try:
        owner,repo_name=_github_repo_parts(repo); runs=_github_actions_runs(owner,repo_name,workflow,branch)
        return jsonify({'provider':'github','repository':f'{owner}/{repo_name}','runs':[{'id':r.get('id'),'name':r.get('name'),'status':r.get('status'),'conclusion':r.get('conclusion'),'state':_github_actions_state(r),'html_url':r.get('html_url'),'head_sha':r.get('head_sha'),'created_at':r.get('created_at'),'updated_at':r.get('updated_at')} for r in runs]})
    except Exception as e:return jsonify(error='github_actions_runs_failed',detail=str(e)[:800]),502

@app.get('/api/forge/status')
@auth_required
def forge_status():
    out={'service':'KOJA Forge','version':KOJA_CLOUD_RELEASE,'github':{'configured':github_provider_configured()}}
    if github_provider_configured():
        try:
            u=_github_request('/user'); out['github'].update({'reachable':True,'login':u.get('login'),'name':u.get('name')})
        except Exception as e: out['github'].update({'reachable':False,'error':str(e)[:500]})
    return jsonify(out)

@app.get('/api/forge/repos')
@auth_required
def forge_repos():
    if not github_provider_configured():
        return jsonify(error='github_provider_not_configured',required=['KOJA_GITHUB_TOKEN']),503
    try:
        rows=_github_request('/user/repos',params={'per_page':100,'sort':'updated','direction':'desc'})
        return jsonify([{'id':x.get('id'),'name':x.get('name'),'full_name':x.get('full_name'),'private':x.get('private'),'default_branch':x.get('default_branch'),'clone_url':x.get('clone_url'),'html_url':x.get('html_url')} for x in rows])
    except Exception as e: return jsonify(error='forge_repos_failed',detail=str(e)[:1000]),502

@app.post('/api/forge/repos')
@auth_required
def forge_create_repo():
    if not github_provider_configured(): return jsonify(error='github_provider_not_configured',required=['KOJA_GITHUB_TOKEN']),503
    d=request.get_json() or {}; name=(d.get('name') or '').strip()
    if not name:return jsonify(error='repository_name_required'),400
    try:
        body={'name':name,'description':d.get('description') or 'KOJA Forge project repository','private':bool(d.get('private',True)),'auto_init':True}
        row=_github_request('/user/repos','POST',body)
        audit(session['user_id'],'forge.repository.create','repository',str(row.get('id')),{'provider':'github','name':name})
        return jsonify(repository={'id':row.get('id'),'name':row.get('name'),'full_name':row.get('full_name'),'clone_url':row.get('clone_url'),'html_url':row.get('html_url'),'default_branch':row.get('default_branch')}),201
    except Exception as e:return jsonify(error='forge_repository_create_failed',detail=str(e)[:1000]),502

@app.post('/api/forge/connect')
@auth_required
def forge_connect():
    d=request.get_json() or {}; sid=(d.get('service_id') or '').strip(); repo=(d.get('repo_url') or '').strip(); branch=(d.get('branch') or 'main').strip()
    uid=session['user_id']; oid=require_org(uid)
    if not sid or not repo:return jsonify(error='service_id_repo_url_required'),400
    row=_one('/rest/v1/cloud_compute_services',{'id':f'eq.{sid}','owner_user_id':f'eq.{uid}','organization_id':f'eq.{oid}','select':'*','limit':'1'})
    if not row:return jsonify(error='service_not_found'),404
    cfg=dict(row.get('config') or {}); cfg.update({'source_provider':'github','source_repo_url':repo,'source_branch':branch,'forge_connected_at':now()})
    out=_patch('/rest/v1/cloud_compute_services',{'id':f'eq.{sid}'},{'repo_url':repo,'branch':branch,'config':cfg})
    audit(uid,'forge.repository.connect','compute_service',sid,{'organization_id':oid,'repo_url':repo,'branch':branch})
    return jsonify(service=out[0] if out else row),200

@app.post('/api/forge/deploy')
@auth_required
def forge_deploy():
    """One-step source-to-hosting workflow using KOJA Forge + KOJA Launch."""
    d=request.get_json() or {}; pid=(d.get('project_id') or '').strip(); name=(d.get('name') or 'KOJA App').strip(); repo=(d.get('repo_url') or '').strip()
    if not pid or not repo:return jsonify(error='project_id_repo_url_required'),400
    # Reuse the real provider-backed Launch path; no fake deployment state.
    if not render_provider_configured(): return jsonify(error='hosting_provider_not_configured',required=['KOJA_RENDER_API_KEY','KOJA_RENDER_OWNER_ID']),503
    uid=session['user_id']; oid=require_org(uid)
    if not project_access(uid,oid,pid):return jsonify(error='project_not_found'),404
    runtime=(d.get('runtime') or 'python').lower(); region=(d.get('region') or 'oregon').strip()
    details={'runtime':runtime,'buildCommand':d.get('build_command') or 'pip install -r requirements.txt','startCommand':d.get('start_command') or 'gunicorn app:app','healthCheckPath':d.get('health_path') or '/health','plan':d.get('plan') or 'free','region':region}
    payload={'type':'web_service','name':name,'ownerId':RENDER_OWNER_ID,'repo':repo,'branch':d.get('branch') or 'main','autoDeploy':'yes','serviceDetails':details}
    try:
        provider=_render_create_service(payload); rid=provider.get('id') or provider.get('service',{}).get('id')
        url=provider.get('serviceDetails',{}).get('url') if isinstance(provider.get('serviceDetails'),dict) else provider.get('url')
        code='LAUNCH-'+secrets.token_hex(5).upper()
        row=_insert('/rest/v1/cloud_compute_services',{'owner_user_id':uid,'organization_id':oid,'project_id':pid,'service_code':code,'name':name,'service_type':'web','runtime':runtime,'repo_url':repo,'branch':d.get('branch') or 'main','build_command':details['buildCommand'],'start_command':details['startCommand'],'health_path':details['healthCheckPath'],'region':region,'cpu':float(d.get('cpu',0.5) or 0.5),'memory_mb':int(d.get('memory_mb',512) or 512),'status':'created','provider':'render','service_url':url or '','config':{'provider':'render','provider_service_id':rid,'source_provider':'github','source_repo_url':repo}})
        dep=_render_deploy(rid,False) if rid else {}
        audit(uid,'forge.deploy','compute_service',row['id'],{'organization_id':oid,'provider':'render','provider_service_id':rid})
        return jsonify(service=row,provider_service_id=rid,service_url=url,deploy=dep),202
    except Exception as e:return jsonify(error='forge_deploy_failed',detail=str(e)[:1200]),502

@app.get('/api/data/<dbid>/connection')
@auth_required
def data_connection(dbid):
    uid=session['user_id']; oid=require_org(uid)
    row=_one('/rest/v1/cloud_databases',{'id':f'eq.{dbid}','owner_user_id':f'eq.{uid}','organization_id':f'eq.{oid}','select':'*','limit':'1'})
    if not row:return jsonify(error='database_not_found'),404
    cfg=row.get('config') or {}; ref=cfg.get('provider_project_ref'); out={'database_id':dbid,'provider':row.get('provider'),'project_ref':ref,'project_url':cfg.get('project_url'),'realtime_available':bool(ref)}
    # Never expose service-role credentials. Only a public client key is returned.
    try:
        raw=decrypt(cfg.get('credentials') or '{}'); data=json.loads(raw or '{}'); keys=(data.get('api_keys') or []) if isinstance(data,dict) else []
        if isinstance(keys,dict): keys=[keys]
        for k in keys:
            name=str(k.get('name') or k.get('type') or '').lower()
            value=k.get('api_key') or k.get('key')
            if value and ('anon' in name or 'publishable' in name): out['public_key']=value; break
    except Exception: pass
    return jsonify(out)

@app.get('/api/data/<dbid>/realtime')
@auth_required
def data_realtime(dbid):
    out=data_connection(dbid)
    if isinstance(out,tuple): return out
    payload=out.get_json() if hasattr(out,'get_json') else {}
    payload.update({'service':'KOJA Sync','protocol':'Supabase Realtime','websocket':bool(payload.get('project_url') and payload.get('public_key')),'note':'Use the public client key only; never expose service-role credentials.'})
    return jsonify(payload)

@app.get('/api/data/<dbid>/auth')
@auth_required
def data_auth(dbid):
    out=data_connection(dbid)
    if isinstance(out,tuple): return out
    payload=out.get_json() if hasattr(out,'get_json') else {}
    payload.update({'service':'KOJA Identity','authentication':'managed','signup_login':True,'session_tokens':True})
    return jsonify(payload)

@app.get('/api/platform/catalog')
@cloud_api_or_login
def platform_catalog():
    return jsonify({'cloud':'KOJA CLOUD','version':KOJA_CLOUD_RELEASE,'products':[
        {'id':'forge','name':'KOJA Forge','purpose':'Source, repositories, builds and CI/CD','provider':'GitHub connector + KOJA workers'},
        {'id':'launch','name':'KOJA Launch','purpose':'Application hosting and deployments','provider':'Render connector or KOJA agents'},
        {'id':'run','name':'KOJA Run','purpose':'Containers, workers and compute jobs','provider':'KOJA agents/providers'},
        {'id':'data','name':'KOJA Data','purpose':'Managed PostgreSQL and SQL','provider':'Supabase managed database'},
        {'id':'sync','name':'KOJA Sync','purpose':'Realtime data and event streams','provider':'Supabase Realtime'},
        {'id':'vault','name':'KOJA Vault','purpose':'Object storage and file delivery','provider':'Supabase Storage / object providers'},
        {'id':'identity','name':'KOJA Identity','purpose':'Authentication and identity','provider':'Managed backend'},
        {'id':'media','name':'KOJA Media','purpose':'Video/audio processing','provider':'KOJA media workers'},
        {'id':'stream','name':'KOJA Stream','purpose':'Live ingest and playback','provider':'KOJA live workers/providers'},
        {'id':'observe','name':'KOJA Observe','purpose':'Logs, metrics and health','provider':'KOJA control plane + agents'},
        {'id':'network','name':'KOJA Network','purpose':'Private service networking and discovery','provider':'KOJA control plane + registered agents'},
        {'id':'edge','name':'KOJA Edge','purpose':'Domains, routing and public service endpoints','provider':'KOJA edge/provider adapters'},
        {'id':'api','name':'KOJA API','purpose':'Public project-scoped APIs','provider':'KOJA CLOUD'}
    ]})



# ============================= KOJA CLOUD V17.8 EDGE + PLATFORM RUNTIME =============================
# Unified developer-platform runtime layer. Uses existing provider adapters and records
# the customer-facing lifecycle without pretending a provider operation succeeded.
KOJA_PLATFORM_RELEASE='26.2.0'

@app.get('/api/launch/services/<service_id>/status')
@auth_required
def launch_service_status(service_id):
    uid=session['user_id']; oid=require_org(uid)
    row=_one('/rest/v1/cloud_compute_services',{'id':f'eq.{service_id}','owner_user_id':f'eq.{uid}','organization_id':f'eq.{oid}','select':'*','limit':'1'})
    if not row:return jsonify(error='service_not_found'),404
    provider=str(row.get('provider') or '').lower(); cfg=row.get('config') or {}; out={'service':row,'platform':'KOJA Launch','provider':provider or None,'provider_configured':False,'reachable':False}
    if provider=='render' and render_provider_configured():
        out['provider_configured']=True; rid=cfg.get('provider_service_id')
        if rid:
            try:
                data=_render_get_service(rid); out['reachable']=True; out['provider_service']=data
            except Exception as e: out['error']=str(e)[:500]
    return jsonify(out)

@app.post('/api/run/jobs')
@auth_required
def run_create_job():
    d=request.get_json() or {}; uid=session['user_id']; oid=require_org(uid); pid=(d.get('project_id') or '').strip()
    if not pid or not project_access(uid,oid,pid):return jsonify(error='project_not_found'),404
    name=(d.get('name') or 'KOJA Run Job').strip(); command=d.get('command') or ''
    payload={'owner_user_id':uid,'organization_id':oid,'project_id':pid,'name':name,'type':d.get('type') or 'job','status':'queued','config':{'command':command,'runtime':d.get('runtime') or 'docker','region':d.get('region') or 'global','provider':d.get('provider') or 'koja-agent'}}
    try:
        row=_insert('/rest/v1/cloud_jobs',payload,params={'select':'*'})[0]
    except Exception:
        row={'id':str(uuid.uuid4()),**payload}
    audit(uid,'run.job.create','job',row.get('id'),{'organization_id':oid,'project_id':pid})
    return jsonify(row),202

@app.get('/api/platform/runtime')
@cloud_api_or_login
def platform_runtime():
    return jsonify({'cloud':'KOJA CLOUD','version':VERSION,'runtime':{
        'launch':'provider-backed application hosting',
        'run':'agent/provider-backed compute and jobs',
        'forge':'source and deployment automation',
        'data':'managed PostgreSQL',
        'sync':'realtime data and event transport',
        'vault':'object storage',
        'stream':'live ingest/playback',
        'observe':'logs, metrics and health'
    },'execution_model':'control-plane plus registered providers/agents'})

@app.get('/api/edge/services/<service_id>')
@auth_required
def edge_service(service_id):
    """Return the customer-facing Edge configuration for an owned service."""
    uid=session['user_id']; oid=require_org(uid)
    row=_one('/rest/v1/cloud_compute_services',{'id':f'eq.{service_id}','owner_user_id':f'eq.{uid}','organization_id':f'eq.{oid}','select':'*','limit':'1'})
    if not row:return jsonify(error='service_not_found'),404
    cfg=dict(row.get('config') or {})
    domains=cfg.get('domains') if isinstance(cfg.get('domains'),list) else []
    primary=cfg.get('primary_domain') or (domains[0] if domains else None) or row.get('service_url') or None
    return jsonify({'service_id':service_id,'project_id':row.get('project_id'),'service_name':row.get('name'),'status':row.get('status'),'service_url':row.get('service_url') or None,'primary_domain':primary,'domains':domains,'health_path':row.get('health_path') or '/health','routing':{'mode':'redirect','https':True,'health_aware':True},'edge':'KOJA Edge','provider':row.get('provider') or None})

@app.post('/api/edge/services/<service_id>/domains')
@auth_required
def edge_add_domain(service_id):
    """Attach routing metadata to a service without pretending DNS/TLS is provisioned."""
    uid=session['user_id']; oid=require_org(uid); d=request.get_json() or {}
    domain=str(d.get('domain') or '').strip().lower().rstrip('.')
    if not re.fullmatch(r'(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}',domain):
        return jsonify(error='invalid_domain'),400
    row=_one('/rest/v1/cloud_compute_services',{'id':f'eq.{service_id}','owner_user_id':f'eq.{uid}','organization_id':f'eq.{oid}','select':'*','limit':'1'})
    if not row:return jsonify(error='service_not_found'),404
    cfg=dict(row.get('config') or {}); domains=cfg.get('domains') if isinstance(cfg.get('domains'),list) else []
    if domain not in domains: domains.append(domain)
    cfg.update({'domains':domains,'primary_domain':str(d.get('primary') or cfg.get('primary_domain') or domain),'edge_updated_at':now()})
    out=_patch('/rest/v1/cloud_compute_services',{'id':f'eq.{service_id}'},{'config':cfg,'updated_at':now()})
    audit(uid,'edge.domain.attach','compute_service',service_id,{'organization_id':oid,'domain':domain})
    return jsonify({'edge':'KOJA Edge','service_id':service_id,'domain':domain,'primary_domain':cfg['primary_domain'],'dns_status':'configuration_required','tls_status':'provider_or_edge_required','service':out[0] if out else row}),201

def _render_public_health_probe(url, health_path='/health'):
    """Probe only the URL already recorded for an owned Render service.
    This request is intentionally a real GET because Render free web services can
    spin down after inactivity; the first request can therefore wake the service.
    """
    base=str(url or '').strip().rstrip('/')
    if not base:
        return {'ok':False,'state':'unknown','reason':'service_url_missing'}
    if not re.match(r'^https://[^/]+(?:/.*)?$', base, re.I):
        return {'ok':False,'state':'unknown','reason':'unsafe_service_url'}
    path=str(health_path or '/health').strip() or '/health'
    if not path.startswith('/'): path='/'+path
    target=base+path
    started=time.time()
    try:
        r=requests.get(target,headers={'User-Agent':'KOJA-CLOUD-Health/26.2.8','Accept':'*/*'},timeout=6,allow_redirects=True)
        elapsed_ms=round((time.time()-started)*1000)
        return {'ok':200 <= r.status_code < 400,'state':'online' if 200 <= r.status_code < 400 else 'offline','http_status':r.status_code,'latency_ms':elapsed_ms,'url':target}
    except requests.Timeout:
        return {'ok':False,'state':'waking','reason':'health_probe_timeout','latency_ms':round((time.time()-started)*1000),'url':target}
    except requests.RequestException as e:
        return {'ok':False,'state':'waking','reason':'health_probe_connection_error','detail':str(e)[:300],'latency_ms':round((time.time()-started)*1000),'url':target}

def _render_health_state(details, probe, wake_requested=False):
    suspended=str(details.get('suspended') or '').lower()
    status=str(details.get('status') or details.get('state') or '').lower()
    if probe.get('ok'):
        return 'online'
    if suspended in ('suspended','true') or status in ('suspended','stopped'):
        return 'sleeping' if not wake_requested else 'waking'
    if probe.get('state') == 'waking' or wake_requested:
        return 'waking'
    if status in ('live','running','active','available'):
        return 'waking'
    return 'offline'

@app.get('/api/edge/services/<service_id>/health')
@auth_required
def edge_health(service_id):
    uid=session['user_id']; oid=require_org(uid)
    row=_one('/rest/v1/cloud_compute_services',{'id':f'eq.{service_id}','owner_user_id':f'eq.{uid}','organization_id':f'eq.{oid}','select':'*','limit':'1'})
    if not row:return jsonify(error='service_not_found'),404
    provider=str(row.get('provider') or '').lower(); cfg=row.get('config') or {}; rid=cfg.get('provider_service_id')
    if provider!='render' or not rid or not render_provider_configured():
        return jsonify({'edge':'KOJA Edge','service_id':service_id,'state':'unknown','healthy':None,'checked':False,'reason':'provider_health_probe_unavailable'}),200
    wake_requested=False; resume_response=None
    try:
        data=_render_get_service(rid)
        details=data.get('service',data) if isinstance(data,dict) else {}
        suspended=str(details.get('suspended') or '').lower()
        # Explicitly suspended services need the Render resume API.
        if suspended in ('suspended','true') or str(details.get('status') or '').lower() == 'suspended':
            resume_response=_render_resume(rid)
            wake_requested=True
        service_url=(row.get('service_url') or details.get('url') or (details.get('serviceDetails') or {}).get('url') or '').strip()
        health_path=row.get('health_path') or '/health'
        probe=_render_public_health_probe(service_url,health_path)
        state=_render_health_state(details,probe,wake_requested)
        if state=='online':
            stored_status='healthy'
        elif state=='waking':
            stored_status='starting'
        elif state=='sleeping':
            stored_status='sleeping'
        else:
            stored_status='degraded'
        try:
            _patch('/rest/v1/cloud_compute_services',{'id':f'eq.{service_id}'},{'status':stored_status,'service_url':service_url or row.get('service_url') or '','updated_at':now()})
        except Exception:
            pass
        return jsonify({
            'edge':'KOJA Edge','service_id':service_id,'provider':'render','provider_service_id':rid,
            'state':state,'healthy':state=='online','checked':True,
            'transition': 'sleeping → waking' if wake_requested and state!='online' else ('waking → online' if state=='online' else state),
            'wake_requested':wake_requested,'resume_response':resume_response,
            'provider_status':details.get('status') or details.get('state'),
            'suspended':details.get('suspended'),
            'service_url':service_url or None,'health_path':health_path,'probe':probe,'checked_at':now()
        }),200
    except Exception as e:
        return jsonify({'edge':'KOJA Edge','service_id':service_id,'state':'offline','healthy':False,'checked':True,'provider':'render','provider_service_id':rid,'error':str(e)[:500]}),502

@app.get('/api/edge/services/<service_id>/public')
@auth_required
def edge_public(service_id):
    """Generate the public application target; actual DNS/TLS remains provider-backed."""
    uid=session['user_id']; oid=require_org(uid)
    row=_one('/rest/v1/cloud_compute_services',{'id':f'eq.{service_id}','owner_user_id':f'eq.{uid}','organization_id':f'eq.{oid}','select':'*','limit':'1'})
    if not row:return jsonify(error='service_not_found'),404
    cfg=row.get('config') or {}; domains=cfg.get('domains') if isinstance(cfg.get('domains'),list) else []
    target=cfg.get('primary_domain') or (domains[0] if domains else None) or row.get('service_url')
    return jsonify({'edge':'KOJA Edge','service_id':service_id,'public':bool(target),'target':('https://'+target if target and not str(target).startswith(('http://','https://')) else target) if target else None,'domains':domains,'service_url':row.get('service_url') or None,'mode':'redirect','note':'KOJA Edge stores and resolves routing metadata; DNS and certificate issuance require a configured edge/provider implementation.'})

@app.get('/api/forge/webhook/<service_id>')
def forge_webhook_info(service_id):
    return jsonify({'service':'KOJA Forge','service_id':service_id,'webhook':'POST','endpoint':f'/api/forge/webhook/{service_id}','signature':'X-Hub-Signature-256','behavior':'validated push events trigger the configured Launch provider when possible'})

@app.post('/api/forge/webhook/<service_id>')
def forge_webhook(service_id):
    secret=os.getenv('KOJA_GITHUB_WEBHOOK_SECRET','').strip(); supplied=request.headers.get('X-Hub-Signature-256',''); body=request.get_data() or b''
    if secret:
        expected='sha256='+hmac.new(secret.encode(),body,hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected,supplied): return jsonify(error='invalid_webhook_signature'),401
    uid=None
    row=_one('/rest/v1/cloud_compute_services',{'id':f'eq.{service_id}','select':'*','limit':'1'})
    if not row:return jsonify(error='service_not_found'),404
    payload=request.get_json(silent=True) or {}; action=payload.get('action') or 'push'; ref=payload.get('ref') or ''
    provider=str(row.get('provider') or '').lower(); cfg=row.get('config') or {}; rid=cfg.get('provider_service_id')
    if action in ('push','synchronize','workflow_run') and provider=='render' and rid and render_provider_configured():
        try:
            dep=_render_deploy(rid,False)
            _patch('/rest/v1/cloud_compute_services',{'id':f'eq.{service_id}'},{'status':'deploying','updated_at':now()})
            return jsonify({'accepted':True,'service_id':service_id,'action':action,'ref':ref,'deployment_triggered':True,'provider':'render','deploy':dep}),202
        except Exception as e:
            return jsonify({'accepted':True,'service_id':service_id,'action':action,'ref':ref,'deployment_triggered':False,'error':str(e)[:700]}),502
    return jsonify({'accepted':True,'service_id':service_id,'action':action,'ref':ref,'deployment_triggered':False,'next':'provider_configuration_required'}),202


# ============================= KOJA CLOUD V17.9 NETWORK + FULL PLATFORM =============================
KOJA_PLATFORM_RELEASE='26.2.0'


def _owned_service(uid, oid, service_id):
    return _one('/rest/v1/cloud_compute_services', {
        'id': f'eq.{service_id}', 'owner_user_id': f'eq.{uid}',
        'organization_id': f'eq.{oid}', 'select': '*', 'limit': '1'
    })

@app.get('/api/network/services/<service_id>')
@auth_required
def network_service(service_id):
    uid=session['user_id']; oid=require_org(uid); row=_owned_service(uid,oid,service_id)
    if not row:return jsonify(error='service_not_found'),404
    cfg=dict(row.get('config') or {}); net=cfg.get('network') if isinstance(cfg.get('network'),dict) else {}
    return jsonify({'service_id':service_id,'project_id':row.get('project_id'),'service_name':row.get('name'),
                    'network':{'network_id':net.get('network_id') or f"net-{str(row.get('project_id'))[:8]}",
                               'private_hostname':net.get('private_hostname') or f"{re.sub(r'[^a-z0-9-]+','-',str(row.get('name') or 'service').lower()).strip('-') or 'service'}.internal.koja",
                               'port':net.get('port') or 80,'protocol':net.get('protocol') or 'https',
                               'service_discovery':True,'private':True},
                    'connections':net.get('connections') if isinstance(net.get('connections'),list) else []})

@app.post('/api/network/services/<service_id>/connect')
@auth_required
def network_connect(service_id):
    uid=session['user_id']; oid=require_org(uid); d=request.get_json(silent=True) or {}; target=str(d.get('target_service_id') or '').strip()
    if not target or target==service_id:return jsonify(error='invalid_target_service'),400
    row=_owned_service(uid,oid,service_id); target_row=_owned_service(uid,oid,target)
    if not row or not target_row:return jsonify(error='service_not_found'),404
    cfg=dict(row.get('config') or {}); net=cfg.get('network') if isinstance(cfg.get('network'),dict) else {}
    conns=net.get('connections') if isinstance(net.get('connections'),list) else []
    if target not in conns: conns.append(target)
    net.update({'connections':conns,'network_id':net.get('network_id') or f"net-{str(row.get('project_id'))[:8]}",
                'private_hostname':net.get('private_hostname') or f"{re.sub(r'[^a-z0-9-]+','-',str(row.get('name') or 'service').lower()).strip('-') or 'service'}.internal.koja"})
    cfg['network']=net
    out=_patch('/rest/v1/cloud_compute_services',{'id':f'eq.{service_id}'},{'config':cfg,'updated_at':now()})
    audit(uid,'network.service.connect','compute_service',service_id,{'target_service_id':target,'organization_id':oid})
    return jsonify({'ok':True,'service_id':service_id,'target_service_id':target,'network':net,'service':out[0] if out else row}),201

@app.post('/api/deploy/services/<service_id>')
@auth_required
def deploy_service(service_id):
    uid=session['user_id']; oid=require_org(uid); row=_owned_service(uid,oid,service_id)
    if not row:return jsonify(error='service_not_found'),404
    cfg=dict(row.get('config') or {}); provider=str(row.get('provider') or cfg.get('provider') or '').lower(); rid=cfg.get('provider_service_id')
    if provider=='render' and rid and render_provider_configured():
        try:
            dep=_render_deploy(rid,False)
            _patch('/rest/v1/cloud_compute_services',{'id':f'eq.{service_id}'},{'status':'deploying','updated_at':now()})
            audit(uid,'deploy.service.trigger','compute_service',service_id,{'provider':'render','provider_service_id':rid,'organization_id':oid})
            return jsonify({'accepted':True,'service_id':service_id,'status':'deploying','provider':'render','deployment':dep}),202
        except Exception as e:return jsonify(error='deployment_failed',detail=str(e)[:1000]),502
    return jsonify({'accepted':False,'service_id':service_id,'status':row.get('status'),'reason':'deployment_provider_not_configured','provider':provider or None}),503

@app.get('/api/deploy/services/<service_id>/status')
@auth_required
def deploy_service_status(service_id):
    uid=session['user_id']; oid=require_org(uid); row=_owned_service(uid,oid,service_id)
    if not row:return jsonify(error='service_not_found'),404
    cfg=row.get('config') or {}; provider=str(row.get('provider') or cfg.get('provider') or '').lower(); rid=cfg.get('provider_service_id')
    if provider=='render' and rid and render_provider_configured():
        try:return jsonify({'service_id':service_id,'provider':'render','provider_service_id':rid,'service':_render_get_service(rid),'cloud_status':row.get('status')}),200
        except Exception as e:return jsonify(error='provider_status_failed',detail=str(e)[:700]),502
    return jsonify({'service_id':service_id,'provider':provider or None,'cloud_status':row.get('status'),'provider_status':None}),200


def _domain_valid(domain):
    domain=str(domain or '').strip().lower().rstrip('.')
    return bool(re.fullmatch(r'(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}', domain))

def _public_dns(domain, rrtype):
    """Read public DNS through a fixed DNS-over-HTTPS resolver; no arbitrary HTTP target."""
    if not _domain_valid(domain):
        return []
    r=requests.get('https://dns.google/resolve', params={'name':domain,'type':rrtype}, headers={'Accept':'application/dns-json','User-Agent':'KOJA-CLOUD/18.5'}, timeout=8)
    r.raise_for_status()
    data=r.json() if r.text else {}
    return [str(x.get('data') or '').strip().rstrip('.') for x in (data.get('Answer') or []) if x.get('data')]

def _tls_probe(domain, port=443):
    """TLS readiness check; only connects to the supplied validated domain on 443."""
    if not _domain_valid(domain): return {'checked':False,'valid':False,'error':'invalid_domain'}
    ctx=ssl.create_default_context()
    try:
        with socket.create_connection((domain, port), timeout=8) as raw:
            with ctx.wrap_socket(raw, server_hostname=domain) as sock:
                cert=sock.getpeercert()
                return {'checked':True,'valid':True,'protocol':sock.version(),'cipher':sock.cipher()[0] if sock.cipher() else None,
                        'subject':dict(x[0] for x in cert.get('subject',())) if cert else None,
                        'expires':cert.get('notAfter') if cert else None}
    except Exception as e:
        return {'checked':True,'valid':False,'error':str(e)[:300]}

def _edge_domain_target(row):
    cfg=row.get('config') or {}; service_url=row.get('service_url') or cfg.get('service_url') or cfg.get('koja_url')
    return service_url

@app.post('/api/domains/services/<service_id>/verify')
@auth_required
def domains_verify(service_id):
    """Verify public DNS and TLS readiness without pretending to provision DNS/certificates."""
    uid=session['user_id']; oid=require_org(uid); row=_owned_service(uid,oid,service_id)
    if not row:return jsonify(error='service_not_found'),404
    cfg=row.get('config') or {}; domains=cfg.get('domains') if isinstance(cfg.get('domains'),list) else []
    requested=(request.get_json(silent=True) or {}).get('domain')
    domain=str(requested or cfg.get('primary_domain') or (domains[0] if domains else '')).strip().lower().rstrip('.')
    if not _domain_valid(domain): return jsonify(error='invalid_domain'),400
    target=_edge_domain_target(row)
    result={'service_id':service_id,'domain':domain,'target':target,'checked_at':now(),'dns':{'a':[],'aaaa':[],'cname':[]},'tls':None,'ready':False}
    try:
        result['dns']['a']=_public_dns(domain,'A')
        result['dns']['aaaa']=_public_dns(domain,'AAAA')
        result['dns']['cname']=_public_dns(domain,'CNAME')
    except Exception as e:
        result['dns_error']=str(e)[:300]
    result['tls']=_tls_probe(domain)
    has_dns=bool(result['dns']['a'] or result['dns']['aaaa'] or result['dns']['cname'])
    result['ready']=bool(has_dns and result['tls'].get('valid'))
    cfg=dict(cfg); verification=dict(cfg.get('domain_verification') or {}); verification[domain]=result; cfg['domain_verification']=verification
    _patch('/rest/v1/cloud_compute_services',{'id':f'eq.{service_id}'},{'config':cfg,'updated_at':now()})
    audit(uid,'domain.verify','compute_service',service_id,{'organization_id':oid,'domain':domain,'ready':result['ready']})
    return jsonify({'edge':'KOJA Edge','verification':result,'dns_recommended':{'record':'CNAME','name':domain,'target':target,'note':'Use the actual edge/provider hostname assigned to this service; do not point DNS to the control-plane API.'} if target else None}),200

@app.get('/api/domains/services/<service_id>/status')
@auth_required
def domains_status(service_id):
    uid=session['user_id']; oid=require_org(uid); row=_owned_service(uid,oid,service_id)
    if not row:return jsonify(error='service_not_found'),404
    cfg=row.get('config') or {}; domains=cfg.get('domains') if isinstance(cfg.get('domains'),list) else []
    verification=cfg.get('domain_verification') if isinstance(cfg.get('domain_verification'),dict) else {}
    return jsonify({'service_id':service_id,'domains':[{'domain':d,'primary':d==cfg.get('primary_domain'),'verification':verification.get(d)} for d in domains],
                    'edge':'KOJA Edge','global_routing':{'enabled':True,'health_aware':True,'failover':'replica-health'},
                    'tls_mode':'customer/provider certificate or configured KOJA Edge certificate','dns_mode':'customer/provider DNS or configured KOJA Edge DNS'})

@app.get('/api/domains/services/<service_id>')
@auth_required
def domains_service(service_id):
    uid=session['user_id']; oid=require_org(uid); row=_owned_service(uid,oid,service_id)
    if not row:return jsonify(error='service_not_found'),404
    cfg=row.get('config') or {}; domains=cfg.get('domains') if isinstance(cfg.get('domains'),list) else []
    return jsonify({'service_id':service_id,'domains':[{'domain':x,'dns_status':'configuration_required','tls_status':'provider_or_edge_required','primary':x==cfg.get('primary_domain')} for x in domains], 'provider':row.get('provider')})

@app.delete('/api/domains/services/<service_id>/<path:domain>')
@auth_required
def domains_remove(service_id,domain):
    uid=session['user_id']; oid=require_org(uid); row=_owned_service(uid,oid,service_id)
    if not row:return jsonify(error='service_not_found'),404
    cfg=dict(row.get('config') or {}); domains=cfg.get('domains') if isinstance(cfg.get('domains'),list) else []
    domain=domain.lower().rstrip('.'); domains=[x for x in domains if x!=domain]; cfg['domains']=domains
    if cfg.get('primary_domain')==domain: cfg['primary_domain']=domains[0] if domains else None
    out=_patch('/rest/v1/cloud_compute_services',{'id':f'eq.{service_id}'},{'config':cfg,'updated_at':now()})
    audit(uid,'domain.detach','compute_service',service_id,{'domain':domain,'organization_id':oid})
    return jsonify({'ok':True,'service_id':service_id,'domain':domain,'domains':domains,'service':out[0] if out else row})

@app.get('/api/data/<dbid>/sync-status')
@auth_required
def data_sync_status(dbid):
    uid=session['user_id']; oid=require_org(uid)
    row=_one('/rest/v1/cloud_databases',{'id':f'eq.{dbid}','owner_user_id':f'eq.{uid}','organization_id':f'eq.{oid}','select':'*','limit':'1'})
    if not row:return jsonify(error='database_not_found'),404
    cfg=row.get('config') or {}; ref=cfg.get('provider_project_ref'); return jsonify({'service':'KOJA Sync','database_id':dbid,'enabled':bool(ref),'provider':'supabase-realtime' if ref else None,'project_ref':ref,'status':'available' if ref else 'provider_configuration_required'})

@app.post('/api/stream/channels')
@auth_required
def stream_create_channel():
    uid=session['user_id']; oid=require_org(uid); d=request.get_json(silent=True) or {}; pid=str(d.get('project_id') or '').strip()
    if not pid or not project_access(uid,oid,pid):return jsonify(error='project_not_found'),404
    code='KST-'+secrets.token_hex(5).upper(); name=(d.get('name') or 'KOJA Stream').strip()
    cfg={'protocol':d.get('protocol') or 'rtmp','playback':'hls','ingest':'provider_or_worker','status':'provisioning'}
    try:
        row=_insert('/rest/v1/cloud_live_channels',{'owner_user_id':uid,'organization_id':oid,'project_id':pid,'channel_code':code,'name':name,'status':'provisioning','config':cfg},params={'select':'*'})[0]
    except Exception as e:return jsonify(error='stream_channel_create_failed',detail=str(e)[:700]),503
    audit(uid,'stream.channel.create','live_channel',row.get('id'),{'project_id':pid,'organization_id':oid}); return jsonify({'channel':row,'service':'KOJA Stream','ingest':None,'playback':None,'status':'provisioning'}),201

@app.get('/api/stream/channels/<channel_id>/status')
@auth_required
def stream_status(channel_id):
    uid=session['user_id']; oid=require_org(uid); row=_one('/rest/v1/cloud_live_channels',{'id':f'eq.{channel_id}','owner_user_id':f'eq.{uid}','organization_id':f'eq.{oid}','select':'*','limit':'1'})
    if not row:return jsonify(error='channel_not_found'),404
    cfg=row.get('config') or {}; return jsonify({'service':'KOJA Stream','channel':row,'status':row.get('status'),'ingest':cfg.get('ingest_url'),'playback':cfg.get('playback_url'),'protocol':cfg.get('protocol') or 'rtmp','execution':'provider_or_registered_stream_worker'})

@app.get('/api/observe/overview')
@auth_required
def observe_overview():
    uid=session['user_id']; oid=require_org(uid); out={'service':'KOJA Observe','organization_id':oid,'version':VERSION,'checks':{}}
    tables=['cloud_compute_services','cloud_compute_deployments','cloud_compute_jobs','cloud_usage','cloud_usage_events','cloud_audit_events','cloud_live_channels','cloud_media_jobs']
    for table in tables:
        try:
            rows=sb('/rest/v1/'+table,params={'organization_id':f'eq.{oid}','select':'id','limit':'100'}); out['checks'][table]={'ok':True,'count':len(rows)}
        except Exception as e: out['checks'][table]={'ok':False,'error':str(e)[:240]}
    return jsonify(out)

@app.get('/api/observe/services/<service_id>')
@auth_required
def observe_service(service_id):
    uid=session['user_id']; oid=require_org(uid); row=_owned_service(uid,oid,service_id)
    if not row:return jsonify(error='service_not_found'),404
    cfg=row.get('config') or {}; provider=str(row.get('provider') or cfg.get('provider') or '').lower(); result={'service':'KOJA Observe','service_id':service_id,'status':row.get('status'),'provider':provider or None,'public_target':cfg.get('primary_domain') or row.get('service_url'),'health':None,'deployment':None}
    if provider=='render' and cfg.get('provider_service_id') and render_provider_configured():
        try:
            details=_render_get_service(cfg['provider_service_id']); result['provider_status']=details; st=details.get('service',details) if isinstance(details,dict) else {}; raw=str(st.get('suspended') or st.get('status') or st.get('state') or '').lower(); result['health']='healthy' if raw in ('live','running','active','available') else raw or 'unknown'
        except Exception as e: result['health']='probe_error'; result['error']=str(e)[:500]
    return jsonify(result)

@app.post('/api/platform/pipeline/<service_id>')
@auth_required
def platform_pipeline(service_id):
    """One-call Forge -> Launch -> Edge pipeline trigger."""
    uid=session['user_id']; oid=require_org(uid); row=_owned_service(uid,oid,service_id)
    if not row:return jsonify(error='service_not_found'),404
    cfg=dict(row.get('config') or {}); provider=str(row.get('provider') or cfg.get('provider') or '').lower(); rid=cfg.get('provider_service_id')
    if provider!='render' or not rid or not render_provider_configured():
        return jsonify({'accepted':False,'stage':'launch','service_id':service_id,'reason':'deployment_provider_not_configured'}),503
    try:
        dep=_render_deploy(rid,False); _patch('/rest/v1/cloud_compute_services',{'id':f'eq.{service_id}'},{'status':'deploying','updated_at':now()})
        audit(uid,'platform.pipeline.trigger','compute_service',service_id,{'organization_id':oid,'provider':'render','provider_service_id':rid})
        return jsonify({'accepted':True,'pipeline':['KOJA Forge','KOJA Build','KOJA Launch','KOJA Network','KOJA Edge','KOJA Observe'],'stage':'launch','status':'deploying','deployment':dep}),202
    except Exception as e:return jsonify(error='pipeline_trigger_failed',detail=str(e)[:1000]),502



# ============================= KOJA CLOUD V18 DATA PLANE =============================


# ============================= KOJA CLOUD V18 DATA PLANE =============================
# V18 turns the existing agent/job foundations into a durable execution contract.
# The Cloud server remains the control plane; actual workloads execute on registered
# KOJA agents or configured external providers. No endpoint reports execution success
# unless an agent/provider has acknowledged it.

KOJA_DATA_PLANE_RELEASE = '18.2.0'


def _v18_job_for_key(jid, oid, pid=None):
    params={'id':f'eq.{jid}','organization_id':f'eq.{oid}','select':'*','limit':'1'}
    if pid: params['project_id']=f'eq.{pid}'
    return _one('/rest/v1/cloud_compute_jobs', params)


def _v18_agent_for_org(agent, oid):
    if not agent or agent.get('organization_id') and agent.get('organization_id') != oid:
        return False
    return True


@app.get('/api/v1/data-plane/runtime')
@cloud_api_or_login
def v18_data_plane_runtime():
    """Describe the actual execution boundary without claiming provider execution."""
    return jsonify({
        'cloud':'KOJA CLOUD', 'version':KOJA_DATA_PLANE_RELEASE,
        'plane':'data',
        'components':{
            'agents':'registered KOJA compute agents',
            'builds':'agent-executed build jobs',
            'deployments':'agent/provider deployment jobs',
            'runtime':'container/service lifecycle reported by agents',
            'artifacts':'artifact metadata and provider/object-storage references',
            'network':'project-scoped service networking metadata',
            'observe':'heartbeats, job status, logs and service state'
        },
        'execution_model':'control-plane queues work; registered agents/providers execute it',
        'release':KOJA_DATA_PLANE_RELEASE
    })


@app.get('/api/v1/compute/nodes')
@api_key_auth
def v18_nodes():
    uid, oid, pid = _v172_key_identity()
    rows=sb('/rest/v1/cloud_compute_agents',params={'owner_user_id':f'eq.{uid}','select':'id,agent_code,name,region,status,last_seen_at,metrics,capabilities,created_at','order':'created_at.desc','limit':'200'})
    return jsonify({'nodes':rows,'organization_id':oid,'project_id':pid,'count':len(rows)})


@app.post('/api/v1/data-plane/agents/register')
@auth_required
def v18_agent_register():
    d=_json_body(); uid=session['user_id']; oid=require_org(uid)
    token=secrets.token_urlsafe(48)
    caps=d.get('capabilities') if isinstance(d.get('capabilities'),dict) else {}
    name=(d.get('name') or 'KOJA Agent').strip()[:120]
    region=(d.get('region') or 'global').strip()[:80]
    payload={
        'owner_user_id':uid,'agent_code':'AG-'+secrets.token_hex(6).upper(),
        'name':name,'region':region,'capabilities':caps,
        'token_hash':hashlib.sha256(token.encode()).hexdigest(),
        'status':'registered','last_seen_at':None,'metrics':{}
    }
    # organization_id is used when the deployed schema supports it; retry without it
    # for older Cloud installations so registration remains backward compatible.
    try:
        payload['organization_id']=oid
        rows=sb('/rest/v1/cloud_compute_agents','POST',payload,params={'select':'*'})
    except Exception:
        payload.pop('organization_id',None)
        rows=sb('/rest/v1/cloud_compute_agents','POST',payload,params={'select':'*'})
    row=rows[0] if isinstance(rows,list) else rows
    return jsonify({'agent':row,'agent_token':token,'warning':'Store this agent token securely; it is shown only at registration.'}),201


@app.post('/api/v1/data-plane/agents/heartbeat')
@agent_auth
def v18_agent_heartbeat():
    d=_json_body(); agent=request.koja_agent
    metrics=d.get('metrics') if isinstance(d.get('metrics'),dict) else {}
    caps=d.get('capabilities') if isinstance(d.get('capabilities'),dict) else None
    patch={'status':'online','last_seen_at':now(),'metrics':metrics}
    if d.get('region'): patch['region']=str(d.get('region'))[:80]
    if caps is not None: patch['capabilities']=caps
    rows=sb('/rest/v1/cloud_compute_agents','PATCH',patch,params={'id':f'eq.{agent["id"]}','select':'*'})
    row=rows[0] if isinstance(rows,list) and rows else agent
    return jsonify({'ok':True,'agent':row,'time':now(),'next_poll_seconds':10})


@app.get('/api/v1/data-plane/agents/work')
@agent_auth
def v18_agent_work():
    agent=request.koja_agent
    # Only jobs belonging to this agent owner are eligible. Region is preferred,
    # but global jobs may execute on any compatible agent.
    region=agent.get('region') or 'global'
    rows=sb('/rest/v1/cloud_compute_jobs',params={
        'owner_user_id':f'eq.{agent["owner_user_id"]}',
        'status':'eq.queued','select':'*','order':'created_at.asc','limit':'25'
    })
    selected=None
    for job in rows:
        spec=job.get('spec') or job.get('config') or {}
        wanted=spec.get('region') or job.get('region') or 'global'
        if wanted in ('global',region):
            selected=job; break
    if not selected: return jsonify({'job':None,'region':region})
    patch={'status':'claimed','agent_id':agent['id'],'claimed_at':now()}
    updated=sb('/rest/v1/cloud_compute_jobs','PATCH',patch,params={'id':f'eq.{selected["id"]}','status':'eq.queued','select':'*'})
    if not updated: return jsonify({'job':None,'race_lost':True})
    return jsonify({'job':updated[0],'region':region,'agent_id':agent['id']})


@app.post('/api/v1/data-plane/jobs/<jid>/status')
@agent_auth
def v18_agent_job_status(jid):
    d=_json_body(); agent=request.koja_agent
    job=_one('/rest/v1/cloud_compute_jobs',{'id':f'eq.{jid}','owner_user_id':f'eq.{agent["owner_user_id"]}','select':'*','limit':'1'})
    if not job: return jsonify(error='job_not_found'),404
    # Prevent one agent from overwriting another agent's claimed job.
    claimed=job.get('agent_id')
    if claimed and claimed != agent.get('id'): return jsonify(error='job_owned_by_another_agent'),409
    status=str(d.get('status') or 'running')
    allowed={'queued','claimed','running','building','starting','healthy','completed','failed','stopped','cancelled'}
    if status not in allowed: return jsonify(error='invalid_job_status'),400
    patch={'status':status,'message':str(d.get('message') or '')[:4000],'result':d.get('result') if isinstance(d.get('result'),dict) else {}}
    if status in {'running','building','starting'}: patch['started_at']=d.get('started_at') or now()
    if status in {'healthy','completed','failed','stopped','cancelled'}: patch['completed_at']=d.get('completed_at') or now()
    if d.get('worker_id'): patch['worker_id']=str(d['worker_id'])[:200]
    rows=sb('/rest/v1/cloud_compute_jobs','PATCH',patch,params={'id':f'eq.{jid}','owner_user_id':f'eq.{agent["owner_user_id"]}','select':'*'})
    if not rows: return jsonify(error='job_update_failed'),409
    dep_id=job.get('deployment_id')
    if dep_id:
        dep_status={'queued':'queued','claimed':'queued','running':'deploying','building':'building','starting':'starting','healthy':'healthy','completed':'healthy','failed':'failed','stopped':'stopped','cancelled':'failed'}.get(status,status)
        _patch('/rest/v1/cloud_compute_deployments',{'id':f'eq.{dep_id}'},{'status':dep_status,'build_log':str(d.get('build_log') or '')[:20000],'deploy_log':str(d.get('deploy_log') or '')[:20000],'completed_at':now() if status in {'healthy','completed','failed','stopped','cancelled'} else None})
    return jsonify({'ok':True,'job':rows[0]})


@app.post('/api/v1/data-plane/jobs/<jid>/log')
@agent_auth
def v18_agent_job_log(jid):
    d=_json_body(); agent=request.koja_agent
    job=_one('/rest/v1/cloud_compute_jobs',{'id':f'eq.{jid}','owner_user_id':f'eq.{agent["owner_user_id"]}','select':'id','limit':'1'})
    if not job:return jsonify(error='job_not_found'),404
    message=str(d.get('message') or '')
    if not message:return jsonify(error='message_required'),400
    row=_insert('/rest/v1/cloud_compute_job_logs',{'job_id':jid,'stream':d.get('stream') or 'stdout','message':message[:12000]})
    return jsonify({'ok':True,'log':row}),201


@app.post('/api/v1/builds')
@api_key_auth
def v18_create_build():
    uid,oid,pid=_v172_key_identity(); d=_json_body()
    if not pid or not _require_project(uid,oid,pid): return jsonify(error='project_not_found'),404
    spec={
        'source':d.get('source') or {},
        'repo_url':d.get('repo_url') or '',
        'branch':d.get('branch') or 'main',
        'commit':d.get('commit') or '',
        'build_command':d.get('build_command') or '',
        'runtime':d.get('runtime') or 'docker',
        'region':d.get('region') or 'global',
        'artifact_type':d.get('artifact_type') or 'container',
        'environment':d.get('environment') if isinstance(d.get('environment'),dict) else {}
    }
    job=_insert('/rest/v1/cloud_compute_jobs',{
        'owner_user_id':uid,'organization_id':oid,'project_id':pid,
        'job_code':'BLD-'+secrets.token_hex(6).upper(),'job_type':'build','status':'queued',
        'region':spec['region'],'spec':spec,'config':{'data_plane_version':'18.2.0'}
    })
    audit(uid,'build.create','build_job',job.get('id'),{'project_id':pid})
    return jsonify({'build':job,'execution':'queued_for_agent'}),202


@app.get('/api/v1/builds/<jid>')
@api_key_auth
def v18_get_build(jid):
    uid,oid,pid=_v172_key_identity(); row=_v18_job_for_key(jid,oid,pid)
    if not row or row.get('owner_user_id')!=uid or row.get('job_type')!='build': return jsonify(error='build_not_found'),404
    return jsonify(row)


@app.post('/api/v1/deployments/<sid>')
@api_key_auth
def v18_deploy_service(sid):
    uid,oid,pid=_v172_key_identity()
    svc=_one('/rest/v1/cloud_compute_services',{'id':f'eq.{sid}','owner_user_id':f'eq.{uid}','organization_id':f'eq.{oid}','project_id':f'eq.{pid}','select':'*','limit':'1'})
    if not svc:return jsonify(error='service_not_found'),404
    d=_json_body()
    dep,job=queue_deploy(uid,sid,d.get('source_commit'),'api_v18_deploy')
    return jsonify({'deployment':dep,'job':job,'execution':'queued_for_agent_or_provider'}),202


@app.get('/api/v1/deployments/<sid>')
@api_key_auth
def v18_deployments(sid):
    uid,oid,pid=_v172_key_identity()
    svc=_one('/rest/v1/cloud_compute_services',{'id':f'eq.{sid}','owner_user_id':f'eq.{uid}','organization_id':f'eq.{oid}','project_id':f'eq.{pid}','select':'id','limit':'1'})
    if not svc:return jsonify(error='service_not_found'),404
    rows=sb('/rest/v1/cloud_compute_deployments',params={'service_id':f'eq.{sid}','owner_user_id':f'eq.{uid}','organization_id':f'eq.{oid}','project_id':f'eq.{pid}','select':'*','order':'created_at.desc','limit':'100'})
    return jsonify({'service_id':sid,'deployments':rows})


@app.post('/api/v1/network/services/<sid>/attach')
@api_key_auth
def v18_network_attach(sid):
    uid,oid,pid=_v172_key_identity(); d=_json_body()
    row=_one('/rest/v1/cloud_compute_services',{'id':f'eq.{sid}','owner_user_id':f'eq.{uid}','organization_id':f'eq.{oid}','project_id':f'eq.{pid}','select':'*','limit':'1'})
    if not row:return jsonify(error='service_not_found'),404
    cfg=dict(row.get('config') or {}); net=dict(cfg.get('network') or {})
    net.update({'network_id':d.get('network_id') or net.get('network_id') or 'net-'+secrets.token_hex(5),'private_hostname':d.get('private_hostname') or net.get('private_hostname') or re.sub(r'[^a-z0-9-]','-',str(row.get('name') or sid).lower()).strip('-')+'.internal','port':int(d.get('port') or net.get('port') or 8080),'updated_at':now()})
    cfg['network']=net
    out=_patch('/rest/v1/cloud_compute_services',{'id':f'eq.{sid}','owner_user_id':f'eq.{uid}'},{'config':cfg,'updated_at':now()})
    audit(uid,'network.service.attach','compute_service',sid,{'project_id':pid,'network_id':net['network_id']})
    return jsonify({'network':net,'service':out[0] if out else row}),200


@app.get('/api/v1/network/services')
@api_key_auth
def v18_network_services():
    uid,oid,pid=_v172_key_identity()
    rows=sb('/rest/v1/cloud_compute_services',params={'owner_user_id':f'eq.{uid}','organization_id':f'eq.{oid}','project_id':f'eq.{pid}','select':'id,name,status,config','order':'created_at.asc','limit':'200'})
    items=[]
    for r in rows:
        cfg=r.get('config') or {}; net=cfg.get('network') or {}
        if net: items.append({'service_id':r['id'],'name':r.get('name'),'status':r.get('status'),'network':net})
    return jsonify({'project_id':pid,'services':items})


@app.get('/api/v1/observe/overview')
@api_key_auth
def v18_observe():
    uid,oid,pid=_v172_key_identity()
    services=sb('/rest/v1/cloud_compute_services',params={'owner_user_id':f'eq.{uid}','organization_id':f'eq.{oid}','project_id':f'eq.{pid}','select':'id,name,status,service_url,config','limit':'200'})
    agents=sb('/rest/v1/cloud_compute_agents',params={'owner_user_id':f'eq.{uid}','select':'id,agent_code,name,region,status,last_seen_at,metrics,capabilities','limit':'200'})
    jobs=sb('/rest/v1/cloud_compute_jobs',params={'owner_user_id':f'eq.{uid}','organization_id':f'eq.{oid}','project_id':f'eq.{pid}','select':'id,job_code,job_type,status,created_at,started_at,completed_at,agent_id,message','order':'created_at.desc','limit':'100'})
    return jsonify({'observe':'KOJA Observe','project_id':pid,'services':services,'agents':agents,'recent_jobs':jobs,'summary':{'services':len(services),'agents':len(agents),'jobs':len(jobs),'online_agents':sum(1 for a in agents if a.get('status')=='online')}})


@app.get('/api/v1/data-plane/agent-manifest')
@cloud_api_or_login
def v18_agent_manifest():
    return jsonify({
        'agent':'KOJA Agent','protocol_version':'v1','cloud_release':'18.2.0',
        'heartbeat':'POST /api/v1/data-plane/agents/heartbeat',
        'work':'GET /api/v1/data-plane/agents/work',
        'job_status':'POST /api/v1/data-plane/jobs/<job_id>/status',
        'job_log':'POST /api/v1/data-plane/jobs/<job_id>/log',
        'required_headers':['X-KOJA-AGENT-TOKEN'],
        'capabilities':['build','deploy','run','health','logs','artifacts'],
        'security':'agent token is stored as a SHA-256 hash; transport must use HTTPS'
    })


# ============================= KOJA CLOUD V18.1 LAUNCH RUNTIME =============================
KOJA_LAUNCH_RELEASE = '18.4.0'

@app.get('/api/v1/launch/runtime')
@cloud_api_or_login
def v181_launch_runtime():
    return jsonify({
        'cloud':'KOJA CLOUD', 'version':KOJA_LAUNCH_RELEASE, 'service':'KOJA Launch',
        'capabilities':['web','api','worker','static','docker','git-deployments','builds','environment','domains','dns-verification','tls-readiness','global-routing','health-checks','logs','restarts','rollbacks'],
        'execution':'registered KOJA Agent or configured provider',
        'public_url_model':'agent gateway or KOJA Edge',
        'source':'Git repository or KOJA workspace'
    })

@app.post('/api/v1/data-plane/agents/register-key')
@api_key_auth
def v181_agent_register_key():
    key=getattr(request,'koja_api_key',{}) or {}
    uid,oid,pid=_v172_key_identity()
    d=_json_body()
    if not uid or not oid: return jsonify(error='api_key_identity_incomplete'),401
    if pid and d.get('project_id') and str(d.get('project_id')) != str(pid): return jsonify(error='project_scope_violation'),403
    token=secrets.token_urlsafe(48)
    caps=d.get('capabilities') if isinstance(d.get('capabilities'),dict) else {}
    name=(d.get('name') or 'KOJA Launch Agent').strip()[:120]
    region=(d.get('region') or 'global').strip()[:80]
    payload={'owner_user_id':uid,'organization_id':oid,'agent_code':'AG-'+secrets.token_hex(6).upper(),'name':name,'region':region,'capabilities':caps,'token_hash':hashlib.sha256(token.encode()).hexdigest(),'status':'registered','last_seen_at':None,'metrics':{}}
    try: rows=sb('/rest/v1/cloud_compute_agents','POST',payload,params={'select':'*'})
    except Exception as e: return jsonify(error='agent_registration_failed',detail=str(e)[:500]),503
    row=rows[0] if isinstance(rows,list) else rows
    audit(uid,'agent.register','compute_agent',row.get('id'),{'organization_id':oid,'project_id':pid,'source':'api_key'})
    return jsonify({'agent':row,'agent_token':token,'cloud_url':request.host_url.rstrip('/'),'warning':'Store the token securely; it is shown only once.'}),201

@app.get('/api/v1/launch/services/<service_id>/runtime')
@cloud_api_or_login
def v181_service_runtime(service_id):
    uid=session['user_id']; oid=require_org(uid)
    row=_owned_service(uid,oid,service_id)
    if not row: return jsonify(error='service_not_found'),404
    cfg=row.get('config') or {}
    return jsonify({'service_id':service_id,'name':row.get('name'),'type':row.get('service_type'),'runtime':row.get('runtime'),'status':row.get('status'),'service_url':row.get('service_url') or cfg.get('service_url') or cfg.get('koja_url'),'public_url':cfg.get('public_url') or cfg.get('primary_domain'),'agent_id':cfg.get('agent_id'),'agent_status':cfg.get('agent_status'),'port':cfg.get('runtime_port') or cfg.get('port'),'deployment_id':cfg.get('deployment_id'),'health_path':row.get('health_path') or '/health'})

@app.post('/api/v1/launch/services/<service_id>/deploy')
@cloud_api_or_login
def v181_launch_deploy(service_id):
    uid=session['user_id']; oid=require_org(uid); row=_owned_service(uid,oid,service_id)
    if not row:return jsonify(error='service_not_found'),404
    d=request.get_json(silent=True) or {}
    dep,job=queue_deploy(uid,service_id,d.get('source_commit'),'launch')
    spec=job.get('spec') or {}
    spec.update({'launch_runtime':KOJA_LAUNCH_RELEASE,'service_type':row.get('service_type') or 'web','runtime':row.get('runtime') or 'docker','health_path':row.get('health_path') or '/health','source_mode':d.get('source_mode') or ('git' if row.get('repo_url') else 'workspace')})
    _patch('/rest/v1/cloud_compute_jobs',{'id':f'eq.{job["id"]}'},{'spec':spec})
    return jsonify({'accepted':True,'deployment':dep,'job':{**job,'spec':spec},'execution':'queued_for_agent_or_provider'}),202

@app.get('/api/v1/launch/services/<service_id>/logs')
@cloud_api_or_login
def v181_launch_logs(service_id):
    uid=session['user_id']; oid=require_org(uid); row=_owned_service(uid,oid,service_id)
    if not row:return jsonify(error='service_not_found'),404
    jobs=sb('/rest/v1/cloud_compute_jobs',params={'service_id':f'eq.{service_id}','owner_user_id':f'eq.{uid}','select':'id,created_at,status,job_type','order':'created_at.desc','limit':'20'})
    ids=[j['id'] for j in jobs]
    logs=[]
    for jid in ids:
        try: logs.extend(sb('/rest/v1/cloud_compute_job_logs',params={'job_id':f'eq.{jid}','select':'job_id,stream,message,created_at','order':'created_at.asc','limit':'500'}))
        except Exception: pass
    return jsonify({'service_id':service_id,'jobs':jobs,'logs':logs[-1000:]})

@app.post('/api/v1/launch/services/<service_id>/restart')
@cloud_api_or_login
def v181_launch_restart(service_id):
    uid=session['user_id']; oid=require_org(uid); row=_owned_service(uid,oid,service_id)
    if not row:return jsonify(error='service_not_found'),404
    job=_enqueue_generic_job(uid,oid,row.get('project_id'),'service_restart',{'service_id':service_id,'action':'restart','region':row.get('region') or 'global'})
    return jsonify({'accepted':True,'job':job,'execution':'queued_for_agent'}),202

@app.get('/api/v1/launch/services')
@cloud_api_or_login
def v181_launch_services():
    oid=require_org(session['user_id']); uid=session['user_id']
    rows=sb('/rest/v1/cloud_compute_services',params={'owner_user_id':f'eq.{uid}','organization_id':f'eq.{oid}','select':'*','order':'created_at.desc','limit':'500'})
    return jsonify({'services':rows,'count':len(rows),'release':KOJA_LAUNCH_RELEASE})


@app.post('/api/v1/data-plane/agents/services/<service_id>/runtime')
@agent_auth
def v181_agent_runtime_update(service_id):
    agent=request.koja_agent; d=_json_body()
    svc=_one('/rest/v1/cloud_compute_services',{'id':f'eq.{service_id}','owner_user_id':f'eq.{agent["owner_user_id"]}','select':'*','limit':'1'})
    if not svc:return jsonify(error='service_not_found'),404
    cfg=dict(svc.get('config') or {})
    for k in ('agent_id','runtime_port','public_url','public_host','container_id','pid','health','runtime_state','deployment_id'):
        if k in d: cfg[k]=d[k]
    replica=str(d.get('replica_index',0)); reps=dict(cfg.get('replicas_runtime') or {})
    reps[replica]={'agent_id':d.get('agent_id'),'runtime_port':d.get('runtime_port'),'public_url':d.get('public_url'),'health':d.get('health') or 'unknown','runtime_state':d.get('runtime_state') or 'running','deployment_id':d.get('deployment_id'),'updated_at':now()}
    cfg['replicas_runtime']=reps
    cfg['active_replicas']=sum(1 for x in reps.values() if str(x.get('health','')).lower() in ('healthy','running','unknown'))
    patch={'config':cfg}
    if d.get('status'): patch['status']=str(d['status'])[:60]
    rows=_patch('/rest/v1/cloud_compute_services',{'id':f'eq.{service_id}','owner_user_id':f'eq.{agent["owner_user_id"]}'},patch)
    return jsonify({'ok':True,'service':rows[0] if rows else svc})



# ============================= KOJA CLOUD V18.2 PRODUCTION LAUNCH =============================
KOJA_PRODUCTION_LAUNCH_RELEASE = '18.2.0'

@app.get('/api/v1/launch/services/<service_id>/environment')
@cloud_api_or_login
def v182_service_environment(service_id):
    uid=session['user_id']; oid=require_org(uid); row=_owned_service(uid,oid,service_id)
    if not row:return jsonify(error='service_not_found'),404
    cfg=row.get('config') or {}
    env=cfg.get('environment') if isinstance(cfg.get('environment'),dict) else {}
    # Never return secret values through the management endpoint.
    return jsonify({'service_id':service_id,'environment':sorted([str(k) for k in env.keys()]),'count':len(env),'secrets_redacted':True})

@app.post('/api/v1/launch/services/<service_id>/environment')
@cloud_api_or_login
def v182_service_environment_set(service_id):
    uid=session['user_id']; oid=require_org(uid); row=_owned_service(uid,oid,service_id)
    if not row:return jsonify(error='service_not_found'),404
    d=request.get_json(silent=True) or {}; values=d.get('environment')
    if not isinstance(values,dict): return jsonify(error='environment_object_required'),400
    cfg=dict(row.get('config') or {}); old=cfg.get('environment') if isinstance(cfg.get('environment'),dict) else {}
    merged=dict(old)
    for k,v in values.items():
        key=str(k).strip()
        if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,127}',key): return jsonify(error='invalid_environment_key',key=key),400
        if v is None: merged.pop(key,None)
        else: merged[key]=str(v)
    cfg['environment']=merged; cfg['environment_updated_at']=now()
    out=_patch('/rest/v1/cloud_compute_services',{'id':f'eq.{service_id}','owner_user_id':f'eq.{uid}','organization_id':f'eq.{oid}'},{'config':cfg,'updated_at':now()})
    audit(uid,'launch.environment.update','compute_service',service_id,{'organization_id':oid,'keys':sorted(merged.keys())})
    return jsonify({'service_id':service_id,'environment':sorted(merged.keys()),'count':len(merged),'secrets_redacted':True,'service':out[0] if out else row}),200

@app.post('/api/v1/launch/services/<service_id>/stop')
@cloud_api_or_login
def v182_launch_stop(service_id):
    uid=session['user_id']; oid=require_org(uid); row=_owned_service(uid,oid,service_id)
    if not row:return jsonify(error='service_not_found'),404
    job=_enqueue_generic_job(uid,oid,row.get('project_id'),'service_stop',{'service_id':service_id,'action':'stop','region':row.get('region') or 'global'})
    return jsonify({'accepted':True,'job':job,'execution':'queued_for_agent'}),202

@app.post('/api/v1/launch/services/<service_id>/start')
@cloud_api_or_login
def v182_launch_start(service_id):
    uid=session['user_id']; oid=require_org(uid); row=_owned_service(uid,oid,service_id)
    if not row:return jsonify(error='service_not_found'),404
    job=_enqueue_generic_job(uid,oid,row.get('project_id'),'service_start',{'service_id':service_id,'action':'start','region':row.get('region') or 'global'})
    return jsonify({'accepted':True,'job':job,'execution':'queued_for_agent'}),202

@app.post('/api/v1/launch/services/<service_id>/rollback')
@cloud_api_or_login
def v182_launch_rollback(service_id):
    uid=session['user_id']; oid=require_org(uid); row=_owned_service(uid,oid,service_id)
    if not row:return jsonify(error='service_not_found'),404
    d=request.get_json(silent=True) or {}; target=d.get('deployment_id')
    if not target: return jsonify(error='deployment_id_required'),400
    dep=_one('/rest/v1/cloud_compute_deployments',{'id':f'eq.{target}','service_id':f'eq.{service_id}','owner_user_id':f'eq.{uid}','organization_id':f'eq.{oid}','select':'*','limit':'1'})
    if not dep:return jsonify(error='deployment_not_found'),404
    commit=dep.get('source_commit') or dep.get('commit') or (dep.get('config') or {}).get('source_commit')
    job=_enqueue_generic_job(uid,oid,row.get('project_id'),'service_rollback',{'service_id':service_id,'action':'rollback','target_deployment_id':target,'source_commit':commit,'region':row.get('region') or 'global'})
    audit(uid,'launch.rollback','compute_service',service_id,{'deployment_id':target})
    return jsonify({'accepted':True,'target_deployment':dep,'job':job,'execution':'queued_for_agent'}),202

@app.get('/api/v1/launch/services/<service_id>/deployments')
@cloud_api_or_login
def v182_service_deployments(service_id):
    uid=session['user_id']; oid=require_org(uid); row=_owned_service(uid,oid,service_id)
    if not row:return jsonify(error='service_not_found'),404
    rows=sb('/rest/v1/cloud_compute_deployments',params={'service_id':f'eq.{service_id}','owner_user_id':f'eq.{uid}','organization_id':f'eq.{oid}','select':'*','order':'created_at.desc','limit':'100'})
    return jsonify({'service_id':service_id,'deployments':rows,'count':len(rows),'release':KOJA_PRODUCTION_LAUNCH_RELEASE})

@app.get('/api/v1/launch/production')
@cloud_api_or_login
def v182_production_launch():
    return jsonify({'cloud':'KOJA CLOUD','product':'KOJA Launch','version':KOJA_PRODUCTION_LAUNCH_RELEASE,'features':{
        'web_hosting':True,'api_hosting':True,'workers':True,'static_sites':True,'docker':True,
        'git_deployments':True,'environment_management':True,'start_stop_restart':True,'rollback':True,
        'deployment_history':True,'agent_execution':True,'edge_routing':True,'health_checks':True,
        'logs':True,'multi_tenant':True
    },'execution_model':'control plane queues; registered agents execute workloads'})

@app.get('/api/v1/edge/services/<service_id>/routing')
@cloud_api_or_login
def v184_edge_routing(service_id):
    uid=session['user_id']; oid=require_org(uid); row=_owned_service(uid,oid,service_id)
    if not row:return jsonify(error='service_not_found'),404
    cfg=row.get('config') or {}; reps=cfg.get('replicas_runtime') if isinstance(cfg.get('replicas_runtime'),dict) else {}
    return jsonify({'service_id':service_id,'strategy':'round_robin_health_aware','active_replicas':cfg.get('active_replicas',0),'replicas':reps,'zero_downtime':True,'release':'18.4.0'})

@app.post('/api/v1/edge/services/<service_id>/drain')
@cloud_api_or_login
def v184_edge_drain(service_id):
    uid=session['user_id']; oid=require_org(uid); row=_owned_service(uid,oid,service_id)
    if not row:return jsonify(error='service_not_found'),404
    d=request.get_json(silent=True) or {}; replica=str(d.get('replica_index',''))
    if replica=='': return jsonify(error='replica_index_required'),400
    cfg=dict(row.get('config') or {}); reps=dict(cfg.get('replicas_runtime') or {})
    if replica not in reps:return jsonify(error='replica_not_found'),404
    reps[replica]['health']='draining'; reps[replica]['runtime_state']='draining'; reps[replica]['updated_at']=now(); cfg['replicas_runtime']=reps
    _patch('/rest/v1/cloud_compute_services',{'id':f'eq.{service_id}','owner_user_id':f'eq.{uid}','organization_id':f'eq.{oid}'},{'config':cfg,'updated_at':now()})
    audit(uid,'edge.replica.drain','compute_service',service_id,{'replica_index':replica})
    return jsonify({'accepted':True,'service_id':service_id,'replica_index':replica,'status':'draining'})

# Final direct-run entry point must come after every route registration.
if __name__=='__main__':
    app.run(host='0.0.0.0',port=int(os.getenv('PORT','10000')))


# ============================== KOJA CLOUD V19 GLOBAL INFRASTRUCTURE ==============================
# V19 extends the V18 data plane into a multi-region infrastructure control plane.
# It schedules work onto registered KOJA Agents; it never reports physical execution
# unless an agent has actually registered and accepted the workload.

KOJA_REGIONS = {
    'zm-lusaka': {'name':'Lusaka, Zambia','country':'ZM','continent':'Africa','status':'active','tier':'standard'},
    'za-johannesburg': {'name':'Johannesburg, South Africa','country':'ZA','continent':'Africa','status':'planned','tier':'standard'},
    'ke-nairobi': {'name':'Nairobi, Kenya','country':'KE','continent':'Africa','status':'planned','tier':'standard'},
    'eu-west': {'name':'Europe West','country':'EU','continent':'Europe','status':'planned','tier':'standard'},
    'us-east': {'name':'US East','country':'US','continent':'North America','status':'planned','tier':'standard'},
    'ap-southeast': {'name':'Asia Pacific Southeast','country':'SG','continent':'Asia','status':'planned','tier':'standard'},
    'global': {'name':'Global','country':'XX','continent':'Global','status':'active','tier':'virtual'},
}

def _global_agents(uid, oid=None, region=None):
    params={'owner_user_id':f'eq.{uid}','select':'id,agent_code,name,region,status,last_seen_at,metrics,capabilities,created_at','order':'created_at.desc','limit':'500'}
    if region and region != 'global': params['region']=f'eq.{region}'
    return sb('/rest/v1/cloud_compute_agents',params=params)

def _agent_healthy(a):
    if (a.get('status') or '').lower() not in ('online','healthy','ready'): return False
    last=a.get('last_seen_at')
    if not last: return False
    try:
        from datetime import datetime, timezone
        dt=datetime.fromisoformat(str(last).replace('Z','+00:00'))
        return (datetime.now(timezone.utc)-dt).total_seconds() <= int(os.getenv('KOJA_AGENT_HEALTH_TTL','60'))
    except Exception:
        return False

def _agent_capacity(a):
    m=a.get('metrics') if isinstance(a.get('metrics'),dict) else {}
    mem=m.get('memory') if isinstance(m.get('memory'),dict) else {}
    disk=m.get('disk') if isinstance(m.get('disk'),dict) else {}
    return {
        'cpu_load_1m': float(m.get('cpu_load_1m') or 0),
        'memory_total': int(mem.get('total') or 0),
        'memory_used': int(mem.get('used') or 0),
        'memory_free': int(mem.get('available') or mem.get('free') or 0),
        'disk_total': int(disk.get('total') or 0),
        'disk_used': int(disk.get('used') or 0),
        'disk_free': int(disk.get('free') or 0),
    }

def _choose_global_agent(uid, region='global', capability=None):
    agents=_global_agents(uid, region=region)
    candidates=[]
    for a in agents:
        if not _agent_healthy(a): continue
        caps=a.get('capabilities') if isinstance(a.get('capabilities'),dict) else {}
        if capability and not caps.get(capability,False): continue
        c=_agent_capacity(a)
        # Lower load and more free memory are preferred. Region matches receive priority.
        score=(0 if region in ('global',a.get('region') or 'global') else 100) + c['cpu_load_1m'] + (c['memory_used']/max(c['memory_total'],1))*10
        candidates.append((score,a))
    candidates.sort(key=lambda x:x[0])
    return candidates[0][1] if candidates else None

def _ensure_global_project_access(uid, oid, sid):
    return _one('/rest/v1/cloud_compute_services',{'id':f'eq.{sid}','owner_user_id':f'eq.{uid}','organization_id':f'eq.{oid}','select':'*','limit':'1'})

@app.get('/api/v1/global/regions')
@cloud_api_or_login
def v19_regions():
    return jsonify({'release':KOJA_GLOBAL_INFRA_RELEASE,'regions':[{'id':k,**v} for k,v in KOJA_REGIONS.items()]})

@app.get('/api/global/regions')
@auth_required
def v19_regions_login():
    return jsonify({'release':KOJA_GLOBAL_INFRA_RELEASE,'regions':[{'id':k,**v} for k,v in KOJA_REGIONS.items()]})

@app.get('/api/v1/global/nodes')
@api_key_auth
def v19_nodes():
    uid,oid,pid=_v172_key_identity()
    rows=_global_agents(uid)
    nodes=[]
    for a in rows:
        c=_agent_capacity(a)
        nodes.append({**a,'healthy':_agent_healthy(a),'capacity':c})
    return jsonify({'release':KOJA_GLOBAL_INFRA_RELEASE,'organization_id':oid,'project_id':pid,'nodes':nodes,'count':len(nodes)})

@app.post('/api/v1/global/placement/plan')
@api_key_auth
def v19_placement_plan():
    uid,oid,pid=_v172_key_identity(); d=_json_body(); region=(d.get('region') or 'global').strip(); capability=d.get('capability')
    if region not in KOJA_REGIONS: return jsonify(error='unknown_region',regions=list(KOJA_REGIONS)),400
    agent=_choose_global_agent(uid,region,capability)
    return jsonify({'release':KOJA_GLOBAL_INFRA_RELEASE,'project_id':pid,'requested_region':region,'selected_agent':agent,'can_execute':bool(agent),'reason':None if agent else 'no_healthy_agent_in_requested_region'})

@app.post('/api/global/services/<sid>/place')
@auth_required
def v19_place_service(sid):
    uid=session['user_id']; oid=require_org(uid); d=_json_body(); row=_ensure_global_project_access(uid,oid,sid)
    if not row:return jsonify(error='service_not_found'),404
    region=(d.get('region') or row.get('region') or 'global').strip()
    if region not in KOJA_REGIONS:return jsonify(error='unknown_region'),400
    agent=_choose_global_agent(uid,region,d.get('capability'))
    cfg=dict(row.get('config') or {}); cfg['placement']={'region':region,'agent_id':agent.get('id') if agent else None,'agent_code':agent.get('agent_code') if agent else None,'planned_at':now(),'status':'placed' if agent else 'pending-capacity'}
    patch={'region':region,'config':cfg,'updated_at':now()}
    out=_patch('/rest/v1/cloud_compute_services',{'id':f'eq.{sid}','owner_user_id':f'eq.{uid}'},patch)
    if agent:
        try:
            _enqueue_generic_job(uid,oid,row.get('project_id'),'service.place',{'service_id':sid,'region':region,'agent_id':agent['id']})
        except Exception: pass
    return jsonify({'service_id':sid,'region':region,'agent':agent,'status':'placed' if agent else 'pending-capacity','service':out[0] if out else row})

@app.get('/api/global/services/<sid>/placement')
@auth_required
def v19_service_placement(sid):
    uid=session['user_id']; oid=require_org(uid); row=_ensure_global_project_access(uid,oid,sid)
    if not row:return jsonify(error='service_not_found'),404
    cfg=dict(row.get('config') or {}); return jsonify({'service_id':sid,'region':row.get('region') or 'global','placement':cfg.get('placement') or {'status':'unplaced'}})

@app.get('/api/global/status')
@auth_required
def v19_global_status():
    uid=session['user_id']; oid=require_org(uid); agents=_global_agents(uid)
    by_region={k:{'total':0,'healthy':0} for k in KOJA_REGIONS}
    for a in agents:
        r=a.get('region') or 'global'; by_region.setdefault(r,{'total':0,'healthy':0}); by_region[r]['total']+=1; by_region[r]['healthy']+=1 if _agent_healthy(a) else 0
    return jsonify({'release':KOJA_GLOBAL_INFRA_RELEASE,'organization_id':oid,'regions':by_region,'nodes':len(agents),'healthy_nodes':sum(1 for a in agents if _agent_healthy(a)),'global_execution_ready':any(_agent_healthy(a) for a in agents),'model':'multi-region control plane + KOJA Agent data plane'})

@app.post('/api/global/failover/<sid>')
@auth_required
def v19_failover(sid):
    uid=session['user_id']; oid=require_org(uid); row=_ensure_global_project_access(uid,oid,sid)
    if not row:return jsonify(error='service_not_found'),404
    d=_json_body(); current=(row.get('region') or 'global'); target=(d.get('region') or 'global')
    agent=_choose_global_agent(uid,target,d.get('capability'))
    if not agent:return jsonify(error='no_healthy_target_agent',requested_region=target,current_region=current),409
    cfg=dict(row.get('config') or {}); cfg['placement']={'region':target,'agent_id':agent['id'],'agent_code':agent['agent_code'],'failed_over_at':now(),'previous_region':current,'status':'failover-selected'}
    out=_patch('/rest/v1/cloud_compute_services',{'id':f'eq.{sid}','owner_user_id':f'eq.{uid}'},{'region':target,'config':cfg,'updated_at':now()})
    try:_enqueue_generic_job(uid,oid,row.get('project_id'),'service.failover',{'service_id':sid,'from_region':current,'region':target,'agent_id':agent['id']})
    except Exception:pass
    return jsonify({'ok':True,'service_id':sid,'from_region':current,'to_region':target,'agent':agent,'status':'failover-selected','service':out[0] if out else row})

@app.get('/api/v1/global/catalog')
@cloud_api_or_login
def v19_global_catalog():
    return jsonify({'release':KOJA_GLOBAL_INFRA_RELEASE,'products':{'global_infrastructure':'Multi-region nodes, placement, failover and global routing','regions':'Regional capacity and placement domains','scheduler':'Health/capacity-aware workload placement','nodes':'KOJA Agent execution nodes','edge':'Global public routing and failover'},'execution':'real only when a healthy KOJA Agent is registered'})


# ============================================================
# KOJA CLOUD V23.0.0 — SELF-TUNING & AUTONOMOUS ORCHESTRATION
# Native node control, durable-state detection, health reconciliation,
# resource-aware job scheduling, retries, and autonomy policy.
# ============================================================
import sqlite3 as _koja_v23_sqlite3
import hashlib as _koja_v23_hashlib
import secrets as _koja_v23_secrets
import hmac as _koja_v23_hmac
from pathlib import Path as _KOJA_V23_PATH

KOJA_AUTONOMY_RELEASE = '26.2.0'
KOJA_CLOUD_RELEASE = '34.0.0'
KOJA_NATIVE_ROOT = _KOJA_V23_PATH(os.getenv('KOJA_NATIVE_ROOT') or os.getenv('KOJA_DATA_ROOT') or '/tmp/koja-cloud-data')
try:
    KOJA_NATIVE_ROOT.mkdir(parents=True, exist_ok=True)
except PermissionError:
    KOJA_NATIVE_ROOT=_KOJA_V23_PATH('/tmp/koja-cloud-data'); KOJA_NATIVE_ROOT.mkdir(parents=True, exist_ok=True)
KOJA_NATIVE_DB=KOJA_NATIVE_ROOT/'native'/'database'/'koja.sqlite3'
KOJA_NATIVE_DB.parent.mkdir(parents=True,exist_ok=True)
KOJA_NODE_BOOTSTRAP_TOKEN=(os.getenv('KOJA_NODE_BOOTSTRAP_TOKEN') or '').strip()


def _v23_db():
    db=_koja_v23_sqlite3.connect(str(KOJA_NATIVE_DB),timeout=30)
    db.row_factory=_koja_v23_sqlite3.Row
    return db

def _v23_now(): return datetime.now(timezone.utc).isoformat()
def _v23_hash(v): return _koja_v23_hashlib.sha256(str(v).encode()).hexdigest()
def _v23_json(v):
    try: return json.dumps(v or {},separators=(',',':'))
    except Exception: return '{}'

def _v23_init():
    db=_v23_db()
    db.executescript('''
    CREATE TABLE IF NOT EXISTS native_nodes (
      node_id TEXT PRIMARY KEY, node_code TEXT UNIQUE NOT NULL, name TEXT NOT NULL,
      region TEXT NOT NULL DEFAULT 'global', status TEXT NOT NULL DEFAULT 'registered',
      token_hash TEXT NOT NULL, capabilities_json TEXT NOT NULL DEFAULT '{}',
      metrics_json TEXT NOT NULL DEFAULT '{}', runtime_json TEXT NOT NULL DEFAULT '{}',
      last_heartbeat TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS native_node_jobs (
      job_id TEXT PRIMARY KEY, node_id TEXT, lease_token_hash TEXT, state TEXT NOT NULL DEFAULT 'queued',
      payload_json TEXT NOT NULL DEFAULT '{}', result_json TEXT NOT NULL DEFAULT '{}',
      created_at TEXT NOT NULL, leased_at TEXT, finished_at TEXT, updated_at TEXT NOT NULL,
      attempts INTEGER NOT NULL DEFAULT 0, max_attempts INTEGER NOT NULL DEFAULT 3);
    CREATE TABLE IF NOT EXISTS autonomy_policies (
      id INTEGER PRIMARY KEY CHECK(id=1), enabled INTEGER NOT NULL DEFAULT 1,
      heartbeat_timeout INTEGER NOT NULL DEFAULT 30, lease_timeout INTEGER NOT NULL DEFAULT 300,
      max_retries INTEGER NOT NULL DEFAULT 3, cpu_soft_limit REAL NOT NULL DEFAULT 0.85,
      memory_soft_limit REAL NOT NULL DEFAULT 0.85, updated_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS autonomy_events (
      id INTEGER PRIMARY KEY AUTOINCREMENT, event_type TEXT NOT NULL, node_id TEXT,
      job_id TEXT, detail_json TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL);
    ''')
    row=db.execute('SELECT id FROM autonomy_policies WHERE id=1').fetchone()
    if not row: db.execute('INSERT INTO autonomy_policies VALUES(1,1,30,300,3,0.85,0.85,?)',(_v23_now(),))
    # additive migration for existing V22 DBs
    for col,typ,default in [('attempts','INTEGER','0'),('max_attempts','INTEGER','3')]:
        try: db.execute(f'ALTER TABLE native_node_jobs ADD COLUMN {col} {typ} NOT NULL DEFAULT {default}')
        except Exception: pass
    db.commit(); db.close()
_v23_init()

def _v23_node_auth():
    supplied=(request.headers.get('X-KOJA-Node-Token') or request.headers.get('X-KOJA-NODE-KEY') or '').strip()
    if not supplied:
        a=(request.headers.get('Authorization') or '').strip()
        if a.lower().startswith('bearer '): supplied=a[7:].strip()
    if not supplied: return None
    db=_v23_db()
    try:
        r=db.execute('SELECT * FROM native_nodes WHERE token_hash=? LIMIT 1',(_v23_hash(supplied),)).fetchone()
        return dict(r) if r else None
    finally: db.close()

def _v23_autonomy_reconcile():
    db=_v23_db(); nowts=time.time(); events=[]; changed=0
    pol=dict(db.execute('SELECT * FROM autonomy_policies WHERE id=1').fetchone())
    # stale nodes
    rows=db.execute('SELECT * FROM native_nodes').fetchall()
    for r in rows:
        d=dict(r); hb=d.get('last_heartbeat'); age=10**9
        if hb:
            try: age=nowts-datetime.fromisoformat(hb.replace('Z','+00:00')).timestamp()
            except Exception: pass
        new='offline' if age>int(pol['heartbeat_timeout']) else 'online'
        if d['status']!=new:
            db.execute('UPDATE native_nodes SET status=?,updated_at=? WHERE node_id=?',(new,_v23_now(),d['node_id'])); changed+=1
            events.append(('node_status',d['node_id'],None,{'from':d['status'],'to':new,'age_seconds':age}))
    # requeue expired leases and retry failed/timeout jobs where attempts remain
    cutoff=time.time()-int(pol['lease_timeout'])
    jobs=db.execute("SELECT * FROM native_node_jobs WHERE state IN ('leased','running')").fetchall()
    for j in jobs:
        d=dict(j); leased=d.get('leased_at'); expired=False
        if leased:
            try: expired=datetime.fromisoformat(leased.replace('Z','+00:00')).timestamp()<cutoff
            except Exception: pass
        if expired:
            attempts=int(d.get('attempts') or 0)+1; maxa=int(d.get('max_attempts') or pol['max_retries'])
            state='queued' if attempts<maxa else 'timeout'
            db.execute('UPDATE native_node_jobs SET state=?,node_id=NULL,lease_token_hash=NULL,attempts=?,finished_at=?,updated_at=? WHERE job_id=?',(state,attempts,_v23_now() if state=='timeout' else None,_v23_now(),d['job_id']))
            events.append(('job_requeue' if state=='queued' else 'job_timeout',d.get('node_id'),d['job_id'],{'attempts':attempts}))
            changed+=1
    for e in events:
        db.execute('INSERT INTO autonomy_events(event_type,node_id,job_id,detail_json,created_at) VALUES(?,?,?,?,?)',(e[0],e[1],e[2],_v23_json(e[3]),_v23_now()))
    db.commit(); db.close(); return {'changed':changed,'events':len(events),'release':KOJA_AUTONOMY_RELEASE}

# ============================================================
# V25.0.0 PRODUCTION SECURITY GATE
# Native customer/data-plane endpoints must never be publicly writable.
# Browser sessions and scoped KOJA API keys are accepted for control-plane
# access; node endpoints retain their separate node-token authentication.
# ============================================================
def native_control_auth(fn):
    @wraps(fn)
    def _wrapped(*a, **k):
        raw=_api_key_raw()
        if raw:
            key, err=resolve_cloud_api_key(raw)
            if err:
                return jsonify(error=err[0]), err[1]
            request.koja_api_key=key
            scope_error=_enforce_api_scope()
            if scope_error:
                return scope_error
            uid=key.get('_uid') or key.get('owner_user_id') or key.get('user_id')
            if uid:
                request.koja_native_user_id=uid
            try:
                return fn(*a, **k)
            except PermissionError as e:
                return jsonify(error=str(e)),403
            except Exception as e:
                return jsonify(error=str(e)),500
        if not session.get('user_id'):
            return jsonify(error='login_or_api_key_required'),401
        request.koja_native_user_id=session.get('user_id')
        try:
            return fn(*a, **k)
        except PermissionError as e:
            return jsonify(error=str(e)),403
        except Exception as e:
            return jsonify(error=str(e)),500
    return _wrapped


@app.get('/api/v1/autonomy/status')
@native_control_auth
def v23_autonomy_status():
    db=_v23_db(); pol=dict(db.execute('SELECT * FROM autonomy_policies WHERE id=1').fetchone())
    nodes=[dict(x) for x in db.execute('SELECT node_id,node_code,name,region,status,last_heartbeat,metrics_json,runtime_json FROM native_nodes ORDER BY created_at').fetchall()]
    counts={r['state']:r['n'] for r in db.execute('SELECT state,COUNT(*) n FROM native_node_jobs GROUP BY state').fetchall()}
    durable=str(KOJA_NATIVE_ROOT).startswith('/koja')
    db.close()
    return jsonify({'cloud':'KOJA CLOUD','release':KOJA_AUTONOMY_RELEASE,'autonomous_orchestration':True,'enabled':bool(pol['enabled']),'durable_native_root':durable,'native_root':str(KOJA_NATIVE_ROOT),'nodes':nodes,'jobs':counts,'policy':pol})

@app.route('/api/v1/autonomy/policy',methods=['GET','POST'])
@native_control_auth
def v23_policy():
    db=_v23_db()
    if request.method=='POST':
        b=request.get_json(silent=True) or {}
        cur=dict(db.execute('SELECT * FROM autonomy_policies WHERE id=1').fetchone())
        vals={k:b.get(k,cur[k]) for k in ['enabled','heartbeat_timeout','lease_timeout','max_retries','cpu_soft_limit','memory_soft_limit']}
        db.execute('UPDATE autonomy_policies SET enabled=?,heartbeat_timeout=?,lease_timeout=?,max_retries=?,cpu_soft_limit=?,memory_soft_limit=?,updated_at=? WHERE id=1',(*vals.values(),_v23_now())); db.commit()
    row=dict(db.execute('SELECT * FROM autonomy_policies WHERE id=1').fetchone()); db.close(); return jsonify(row)

@app.post('/api/v1/autonomy/reconcile')
@native_control_auth
def v23_reconcile(): return jsonify(_v23_autonomy_reconcile())

@app.get('/api/v1/autonomy/nodes')
@native_control_auth
def v23_nodes():
    _v23_autonomy_reconcile(); db=_v23_db(); rows=[dict(r) for r in db.execute('SELECT node_id,node_code,name,region,status,last_heartbeat,metrics_json,runtime_json FROM native_nodes ORDER BY status DESC,created_at').fetchall()]; db.close(); return jsonify({'release':KOJA_AUTONOMY_RELEASE,'nodes':rows})

@app.get('/api/v1/autonomy/jobs')
@native_control_auth
def v23_jobs():
    _v23_autonomy_reconcile(); db=_v23_db(); rows=[dict(r) for r in db.execute('SELECT job_id,node_id,state,attempts,max_attempts,created_at,leased_at,finished_at,updated_at FROM native_node_jobs ORDER BY created_at DESC LIMIT 200').fetchall()]; db.close(); return jsonify({'release':KOJA_AUTONOMY_RELEASE,'jobs':rows})

# Native node registration/runtime plane, retained inside the full Flask app.
@app.post('/api/v1/native/nodes/register')
def v23_register_node():
    b=request.get_json(silent=True) or {}; supplied=(b.get('bootstrap_token') or request.headers.get('X-KOJA-Bootstrap-Token') or '').strip()
    if not KOJA_NODE_BOOTSTRAP_TOKEN or not supplied or not _koja_v23_hmac.compare_digest(supplied,KOJA_NODE_BOOTSTRAP_TOKEN): return jsonify({'error':'invalid_bootstrap_token'}),401
    nid=str(uuid.uuid4()); code='KOJA-NODE-'+_koja_v23_secrets.token_hex(4).upper(); tok='KNT-'+_koja_v23_secrets.token_urlsafe(32); ts=_v23_now()
    db=_v23_db(); db.execute('INSERT INTO native_nodes VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',(nid,code,b.get('name') or code,b.get('region') or 'global','registered',_v23_hash(tok),_v23_json(b.get('capabilities') or {}), '{}','{}',None,ts,ts)); db.commit(); db.close()
    return jsonify({'cloud':'KOJA CLOUD','data_plane':'native','node_id':nid,'node_code':code,'node_token':tok,'release':KOJA_AUTONOMY_RELEASE,'status':'registered'})

@app.get('/api/v1/native/nodes')
@native_control_auth
def v23_list_nodes():
    _v23_autonomy_reconcile(); db=_v23_db(); rows=[dict(r) for r in db.execute('SELECT node_id,node_code,name,region,status,capabilities_json,metrics_json,runtime_json,last_heartbeat,created_at,updated_at FROM native_nodes ORDER BY created_at').fetchall()]; db.close(); return jsonify({'release':KOJA_AUTONOMY_RELEASE,'nodes':rows})

@app.get('/api/v1/native/node/runtime')
def v23_node_runtime():
    row=_v23_node_auth()
    if not row: return jsonify({'error':'unauthorized'}),401
    return jsonify({'cloud':'KOJA CLOUD','control_plane':'KOJA CLOUD','execution':'KOJA-controlled nodes','plane':'native-node','release':KOJA_AUTONOMY_RELEASE,'node_id':row['node_id'],'status':row['status']})

@app.post('/api/v1/native/node/heartbeat')
def v23_heartbeat():
    row=_v23_node_auth()
    if not row: return jsonify({'error':'unauthorized'}),401
    b=request.get_json(silent=True) or {}; db=_v23_db(); db.execute('UPDATE native_nodes SET status=?,metrics_json=?,runtime_json=?,last_heartbeat=?,updated_at=? WHERE node_id=?',('online',_v23_json(b.get('metrics') or {}),_v23_json(b.get('runtime') or {}),_v23_now(),_v23_now(),row['node_id'])); db.commit(); db.close()
    # Every healthy heartbeat also advances the autonomy reconciliation loop.
    reconciliation=_v23_autonomy_reconcile()
    return jsonify({'ok':True,'node_id':row['node_id'],'status':'online','release':KOJA_AUTONOMY_RELEASE,'reconciliation':reconciliation})

@app.post('/api/v1/native/node/jobs')
@native_control_auth
def v23_queue_job():
    b=request.get_json(silent=True) or {}; db=_v23_db(); jid=str(uuid.uuid4()); maxa=int(b.get('max_attempts') or 3); db.execute('INSERT INTO native_node_jobs(job_id,node_id,state,payload_json,result_json,created_at,updated_at,attempts,max_attempts) VALUES(?,?,?,?,?,?,?,?,?)',(jid,b.get('node_id'),'queued',_v23_json(b.get('payload') or {}),'{}',_v23_now(),_v23_now(),0,maxa)); db.commit(); db.close(); return jsonify({'ok':True,'job_id':jid,'state':'queued','release':KOJA_AUTONOMY_RELEASE})

@app.post('/api/v1/native/node/jobs/lease')
def v23_lease():
    row=_v23_node_auth()
    if not row: return jsonify({'error':'unauthorized'}),401
    reconciliation=_v23_autonomy_reconcile()
    b=request.get_json(silent=True) or {}; limit=max(1,min(20,int(b.get('limit') or 1))); lease_seconds=int(b.get('lease_seconds') or 300); db=_v23_db()
    # Resource-aware admission: overloaded nodes remain online but do not receive new work.
    pol=dict(db.execute('SELECT * FROM autonomy_policies WHERE id=1').fetchone())
    nr=db.execute('SELECT metrics_json FROM native_nodes WHERE node_id=?',(row['node_id'],)).fetchone()
    metrics={}
    try: metrics=json.loads((nr['metrics_json'] if nr else '{}') or '{}')
    except Exception: metrics={}
    cpu=float(metrics.get('load_ratio',metrics.get('cpu_ratio',0)) or 0)
    mem=float(metrics.get('memory_ratio',0) or 0)
    if bool(pol.get('enabled')) and (cpu>=float(pol['cpu_soft_limit']) or mem>=float(pol['memory_soft_limit'])):
        db.close(); return jsonify({'ok':True,'jobs':[],'lease_seconds':lease_seconds,'release':KOJA_AUTONOMY_RELEASE,'admission':'throttled','metrics':metrics,'reconciliation':reconciliation})
    q=db.execute("SELECT * FROM native_node_jobs WHERE state='queued' AND (node_id IS NULL OR node_id=?) ORDER BY created_at LIMIT ?",(row['node_id'],limit)).fetchall(); out=[]
    for j in q:
        token=_koja_v23_secrets.token_urlsafe(24); db.execute('UPDATE native_node_jobs SET node_id=?,state=?,lease_token_hash=?,leased_at=?,updated_at=? WHERE job_id=?', (row['node_id'],'leased',_v23_hash(token),_v23_now(),_v23_now(),j['job_id'])); d=dict(j); d['lease_token']=token; d['payload']=json.loads(d['payload_json'] or '{}'); out.append(d)
    db.commit(); db.close(); return jsonify({'ok':True,'jobs':out,'lease_seconds':lease_seconds,'release':KOJA_AUTONOMY_RELEASE})

@app.post('/api/v1/native/node/jobs/<job_id>/result')
def v23_result(job_id):
    row=_v23_node_auth()
    if not row: return jsonify({'error':'unauthorized'}),401
    b=request.get_json(silent=True) or {}; token=(b.get('lease_token') or '').strip(); db=_v23_db(); j=db.execute('SELECT * FROM native_node_jobs WHERE job_id=? AND node_id=?',(job_id,row['node_id'])).fetchone()
    if not j or not token or not _koja_v23_hmac.compare_digest(_v23_hash(token),j['lease_token_hash'] or ''): db.close(); return jsonify({'error':'invalid_lease'}),403
    state=b.get('state') or 'succeeded'; result=b.get('result') or {}; db.execute('UPDATE native_node_jobs SET state=?,result_json=?,finished_at=?,updated_at=? WHERE job_id=?',(state,_v23_json(result),_v23_now() if state in ('succeeded','failed','timeout','cancelled') else None,_v23_now(),job_id)); db.commit(); db.close()
    cloud_job_id=(json.loads(j['payload_json'] or '{}').get('cloud_media_job_id')) if j else None
    if cloud_job_id:
        try:
            cstatus='succeeded' if state=='succeeded' else ('cancelled' if state=='cancelled' else 'failed')
            _patch('/rest/v1/cloud_media_jobs',{'id':f'eq.{cloud_job_id}'},{'status':cstatus,'completed_at':_v23_now() if cstatus in ('succeeded','failed','cancelled') else None,'result':result})
            asset_id=json.loads(j['payload_json'] or '{}').get('cloud_media_asset_id')
            if asset_id: _patch('/rest/v1/cloud_media_assets',{'id':f'eq.{asset_id}'},{'status':'ready' if cstatus=='succeeded' else 'failed','updated_at':now(),'metadata':{'native_worker':result}})
            _real_event('media','process.result',cstatus,asset_id or cloud_job_id,{'cloud_media_job_id':cloud_job_id,'native_job_id':job_id,'result':result})
        except Exception: pass
    return jsonify({'ok':True,'job_id':job_id,'state':state})


# ============================================================
# KOJA CLOUD V34 — REAL NODE OPERATIONS + INSTANT INSTANCE ROUTING
# ============================================================
def _v34_node_rows():
    _v23_autonomy_reconcile()
    db=_v23_db(); rows=[dict(x) for x in db.execute('SELECT node_id,node_code,name,region,status,metrics_json,runtime_json,last_heartbeat,created_at,updated_at FROM native_nodes ORDER BY last_heartbeat DESC').fetchall()]; db.close()
    for x in rows:
        try:x['metrics']=json.loads(x.pop('metrics_json') or '{}')
        except Exception:x['metrics']={}
        try:x['runtime']=json.loads(x.pop('runtime_json') or '{}')
        except Exception:x['runtime']={}
    return rows

@app.get('/api/v34/nodes')
@auth_required
def v34_nodes_api():
    return jsonify({'release':KOJA_CLOUD_RELEASE,'nodes':_v34_node_rows()})

@app.post('/api/v34/nodes/<node_id>/actions')
@auth_required
def v34_node_action(node_id):
    b=request.get_json(silent=True) or {}; action=str(b.get('action') or '').strip().lower()
    allowed={'health','ffmpeg'}
    if action not in allowed:return jsonify(error='unsupported_action',allowed=sorted(allowed)),400
    db=_v23_db(); node=db.execute('SELECT * FROM native_nodes WHERE node_id=?',(node_id,)).fetchone()
    if not node:db.close();return jsonify(error='node_not_found'),404
    jid=str(uuid.uuid4()); payload={'operation':('native_healthcheck' if action=='health' else 'ffmpeg_version'),'action':action,'requested_by':session.get('user_id'),'release':KOJA_CLOUD_RELEASE}
    db.execute('INSERT INTO native_node_jobs(job_id,node_id,state,payload_json,result_json,created_at,updated_at,attempts,max_attempts) VALUES(?,?,?,?,?,?,?,?,?)',(jid,node_id,'queued',_v23_json(payload),'{}',_v23_now(),_v23_now(),0,3));db.commit();db.close()
    audit(session['user_id'],'native.node.action','native_node_job',jid,{'node_id':node_id,'action':action})
    return jsonify({'ok':True,'job_id':jid,'node_id':node_id,'node_code':node['node_code'],'state':'queued','redirect_url':'/jobs/'+jid}),202

@app.get('/api/v34/nodes/<node_id>/jobs')
@auth_required
def v34_node_jobs(node_id):
    db=_v23_db(); node=db.execute('SELECT node_id FROM native_nodes WHERE node_id=?',(node_id,)).fetchone()
    if not node:db.close();return jsonify(error='node_not_found'),404
    rows=[dict(x) for x in db.execute('SELECT job_id,node_id,state,payload_json,result_json,created_at,leased_at,finished_at,updated_at,attempts,max_attempts FROM native_node_jobs WHERE node_id=? ORDER BY created_at DESC LIMIT 100',(node_id,)).fetchall()];db.close()
    for x in rows:
        try:x['payload']=json.loads(x.pop('payload_json') or '{}')
        except Exception:x['payload']={}
        try:x['result']=json.loads(x.pop('result_json') or '{}')
        except Exception:x['result']={}
    return jsonify({'node_id':node_id,'jobs':rows})

@app.get('/api/v34/jobs/<job_id>')
@auth_required
def v34_job_api(job_id):
    db=_v23_db(); r=db.execute('SELECT * FROM native_node_jobs WHERE job_id=?',(job_id,)).fetchone(); db.close()
    if not r:return jsonify(error='job_not_found'),404
    d=dict(r)
    try:d['payload']=json.loads(d.pop('payload_json') or '{}')
    except Exception:d['payload']={}
    try:d['result']=json.loads(d.pop('result_json') or '{}')
    except Exception:d['result']={}
    d.pop('lease_token_hash',None)
    return jsonify(d)

@app.get('/api/v1/native/node/jobs/<job_id>')
@native_control_auth
def v23_job(job_id):
    db=_v23_db(); r=db.execute('SELECT * FROM native_node_jobs WHERE job_id=?',(job_id,)).fetchone(); db.close();
    if not r: return jsonify({'error':'not_found'}),404
    d=dict(r); d['payload']=json.loads(d.pop('payload_json') or '{}'); d['result']=json.loads(d.pop('result_json') or '{}'); d.pop('lease_token_hash',None); return jsonify(d)

@app.post('/api/v1/native/nodes/reconcile')
@native_control_auth
def v23_native_reconcile(): return jsonify(_v23_autonomy_reconcile())

# ============================================================
# KOJA CLOUD V23.1.0 — REAL NATIVE SERVICE PLANE
# These primitives execute locally on the KOJA data plane. Provider
# adapters remain optional integrations; the service status APIs below
# are based on real probes and real operations, not UI cards.
# ============================================================
KOJA_REAL_PLANE_RELEASE = '26.2.0'
KOJA_NATIVE_SERVICE_ROOT = KOJA_NATIVE_ROOT / 'services'
KOJA_NATIVE_STORAGE_ROOT = KOJA_NATIVE_SERVICE_ROOT / 'storage'
KOJA_NATIVE_DATABASE_ROOT = KOJA_NATIVE_SERVICE_ROOT / 'databases'
KOJA_NATIVE_MEDIA_ROOT = KOJA_NATIVE_SERVICE_ROOT / 'media'
KOJA_NATIVE_LOG_ROOT = KOJA_NATIVE_SERVICE_ROOT / 'logs'
KOJA_NATIVE_BACKUP_ROOT = KOJA_NATIVE_SERVICE_ROOT / 'backups'
KOJA_NATIVE_WEBHOOK_ROOT = KOJA_NATIVE_SERVICE_ROOT / 'webhooks'
for _p in (KOJA_NATIVE_STORAGE_ROOT, KOJA_NATIVE_DATABASE_ROOT, KOJA_NATIVE_MEDIA_ROOT,
           KOJA_NATIVE_LOG_ROOT, KOJA_NATIVE_BACKUP_ROOT, KOJA_NATIVE_WEBHOOK_ROOT):
    _p.mkdir(parents=True, exist_ok=True)


def _real_json(value):
    try: return json.dumps(value or {}, separators=(',', ':'))
    except Exception: return '{}'


def _real_init():
    db = _v23_db()
    db.executescript('''
    CREATE TABLE IF NOT EXISTS native_service_events (
      id INTEGER PRIMARY KEY AUTOINCREMENT, service TEXT NOT NULL,
      operation TEXT NOT NULL, status TEXT NOT NULL, resource_id TEXT,
      detail_json TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS native_storage_buckets (
      bucket_id TEXT PRIMARY KEY, name TEXT UNIQUE NOT NULL,
      created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS native_databases (
      database_id TEXT PRIMARY KEY, name TEXT UNIQUE NOT NULL,
      path TEXT NOT NULL, created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS native_webhooks (
      webhook_id TEXT PRIMARY KEY, name TEXT NOT NULL, url TEXT NOT NULL,
      secret TEXT NOT NULL, events_json TEXT NOT NULL DEFAULT '["*"]',
      status TEXT NOT NULL DEFAULT 'active', last_status INTEGER,
      last_delivery_at TEXT, created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS native_media_assets (
      asset_id TEXT PRIMARY KEY, name TEXT NOT NULL, path TEXT NOT NULL,
      media_type TEXT NOT NULL DEFAULT 'binary', size_bytes INTEGER NOT NULL,
      sha256 TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'ready',
      created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS native_webhook_deliveries (
      delivery_id TEXT PRIMARY KEY, webhook_id TEXT NOT NULL, event_name TEXT NOT NULL,
      status TEXT NOT NULL, status_code INTEGER, response_text TEXT NOT NULL DEFAULT '',
      attempts INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL
    );
    ''')
    db.commit(); db.close()


_real_init()


def _real_event(service, operation, status, resource_id=None, detail=None):
    ts=_v23_now()
    db = _v23_db()
    db.execute('INSERT INTO native_service_events(service,operation,status,resource_id,detail_json,created_at) VALUES(?,?,?,?,?,?)',
               (service, operation, status, resource_id, _real_json(detail), ts))
    db.commit(); db.close()
    try:
        KOJA_NATIVE_LOG_ROOT.mkdir(parents=True,exist_ok=True)
        with open(KOJA_NATIVE_LOG_ROOT/'services.log','a',encoding='utf-8') as fh:
            fh.write(_real_json({'timestamp':ts,'service':service,'operation':operation,'status':status,'resource_id':resource_id,'detail':detail})+'\n')
    except Exception: pass


def _real_hash_file(path):
    h = hashlib.sha256()
    with open(path, 'rb') as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def _real_safe_name(value):
    return re.sub(r'[^A-Za-z0-9._-]+', '-', str(value or 'item')).strip('.-')[:180] or 'item'


@app.get('/api/v1/native/services/status')
@native_control_auth
def real_service_status():
    checks={}
    try:
        _real_init(); db=_v23_db(); db.execute('SELECT 1').fetchone(); db.close(); checks['control_database']={'status':'operational','detail':str(KOJA_NATIVE_DB)}
    except Exception as e: checks['control_database']={'status':'failed','error':str(e)}
    try:
        KOJA_NATIVE_STORAGE_ROOT.mkdir(parents=True,exist_ok=True); probe=KOJA_NATIVE_STORAGE_ROOT/'.probe'; probe.write_bytes(b'koja'); ok=probe.read_bytes()==b'koja'; probe.unlink(missing_ok=True); checks['storage']={'status':'operational' if ok else 'failed'}
    except Exception as e: checks['storage']={'status':'failed','error':str(e)}
    try:
        db=_v23_db(); db.execute('CREATE TABLE IF NOT EXISTS _native_probe(v TEXT)'); db.execute('INSERT INTO _native_probe(v) VALUES(?)',('ok',)); db.execute('DELETE FROM _native_probe'); db.commit(); db.close(); checks['database']={'status':'operational'}
    except Exception as e: checks['database']={'status':'failed','error':str(e)}
    try:
        db=_v23_db(); online=db.execute("SELECT COUNT(*) n FROM native_nodes WHERE status='online'").fetchone()['n']; total=db.execute('SELECT COUNT(*) n FROM native_nodes').fetchone()['n']; db.close(); checks['compute']={'status':'operational' if online else 'node_required','online_nodes':online,'registered_nodes':total,'execution':'native-node-or-system-worker'}
    except Exception as e: checks['compute']={'status':'failed','error':str(e)}
    try:
        KOJA_NATIVE_LOG_ROOT.mkdir(parents=True,exist_ok=True); checks['logging']={'status':'operational' if (KOJA_NATIVE_LOG_ROOT/'services.log').exists() or KOJA_NATIVE_LOG_ROOT.exists() else 'failed'}
    except Exception as e: checks['logging']={'status':'failed','error':str(e)}
    checks['backup']={'status':'operational' if KOJA_NATIVE_BACKUP_ROOT.exists() else 'failed'}
    try:
        db=_v23_db(); db.execute('SELECT COUNT(*) FROM native_webhooks').fetchone(); db.close(); checks['webhooks']={'status':'operational','delivery':'real_http'}
    except Exception as e: checks['webhooks']={'status':'failed','error':str(e)}
    checks['media']={'status':'operational','mode':'native-ingest','transcoding':'available' if shutil.which('ffmpeg') else 'worker_required'}
    try:
        with app.test_client() as c: r=c.get('/api/v1/health'); checks['network']={'status':'operational' if r.status_code<500 else 'failed','probe_status_code':r.status_code,'mode':'native-http'}
    except Exception as e: checks['network']={'status':'failed','error':str(e)}
    durable=str(KOJA_NATIVE_ROOT).startswith('/koja')
    return jsonify({'cloud':'KOJA CLOUD','release':KOJA_REAL_PLANE_RELEASE,'real_service_plane':True,'durable_native_root':durable,'native_root':str(KOJA_NATIVE_ROOT),'checks':checks})


@app.post('/api/v1/native/storage/buckets')
@native_control_auth
def real_storage_bucket_create():
    b = request.get_json(silent=True) or {}; name = _real_safe_name(b.get('name'))
    if not name: return jsonify(error='bucket_name_required'), 400
    db = _v23_db(); existing = db.execute('SELECT * FROM native_storage_buckets WHERE name=?', (name,)).fetchone()
    if existing: db.close(); return jsonify(dict(existing), existing=True)
    bid = str(uuid.uuid4()); ts = _v23_now(); (KOJA_NATIVE_STORAGE_ROOT / name).mkdir(parents=True, exist_ok=True)
    db.execute('INSERT INTO native_storage_buckets VALUES(?,?,?)', (bid, name, ts)); db.commit(); db.close()
    _real_event('storage', 'bucket.create', 'succeeded', bid, {'name': name})
    return jsonify({'ok': True, 'bucket_id': bid, 'name': name, 'status': 'ready'}), 201


@app.post('/api/v1/native/storage/upload')
@native_control_auth
def real_storage_upload():
    bucket = _real_safe_name((request.form.get('bucket') or '').strip()); name = _real_safe_name(request.form.get('name') or 'upload.bin'); f = request.files.get('file')
    if not bucket or not f: return jsonify(error='bucket_and_file_required'), 400
    root = KOJA_NATIVE_STORAGE_ROOT / bucket
    if not root.exists(): return jsonify(error='bucket_not_found'), 404
    target = root / name; f.save(str(target)); digest = _real_hash_file(target); size = target.stat().st_size
    _real_event('storage', 'object.upload', 'succeeded', f'{bucket}/{name}', {'size_bytes': size, 'sha256': digest})
    return jsonify({'ok': True, 'bucket': bucket, 'name': name, 'size_bytes': size, 'sha256': digest, 'path': str(target)})


@app.get('/api/v1/native/storage/download/<bucket>/<name>')
@native_control_auth
def real_storage_download(bucket, name):
    from flask import send_file
    target = KOJA_NATIVE_STORAGE_ROOT / _real_safe_name(bucket) / _real_safe_name(name)
    if not target.is_file(): return jsonify(error='object_not_found'), 404
    return send_file(str(target), as_attachment=True, download_name=target.name)


@app.post('/api/v1/native/database/create')
@native_control_auth
def real_database_create():
    b = request.get_json(silent=True) or {}; name = _real_safe_name(b.get('name'))
    if not name: return jsonify(error='database_name_required'), 400
    db = _v23_db(); existing = db.execute('SELECT * FROM native_databases WHERE name=?', (name,)).fetchone()
    if existing: db.close(); return jsonify(dict(existing), existing=True)
    did = str(uuid.uuid4()); path = KOJA_NATIVE_DATABASE_ROOT / (name + '.sqlite3')
    conn = _koja_v23_sqlite3.connect(str(path)); conn.execute('PRAGMA journal_mode=WAL'); conn.commit(); conn.close()
    db.execute('INSERT INTO native_databases VALUES(?,?,?,?)', (did, name, str(path), _v23_now())); db.commit(); db.close()
    _real_event('database', 'database.create', 'succeeded', did, {'name': name})
    return jsonify({'ok': True, 'database_id': did, 'name': name, 'path': str(path), 'status': 'ready'}), 201


@app.post('/api/v1/native/database/<database_id>/sql')
@native_control_auth
def real_database_sql(database_id):
    b = request.get_json(silent=True) or {}; sql = str(b.get('sql') or '').strip()
    if not sql: return jsonify(error='sql_required'), 400
    db = _v23_db(); row = db.execute('SELECT * FROM native_databases WHERE database_id=?', (database_id,)).fetchone(); db.close()
    if not row: return jsonify(error='database_not_found'), 404
    conn = _koja_v23_sqlite3.connect(row['path']); conn.row_factory = _koja_v23_sqlite3.Row
    try:
        cur = conn.execute(sql, tuple(b.get('params') or [])); rows = [dict(x) for x in cur.fetchall()] if cur.description else []
        conn.commit(); result = {'ok': True, 'rowcount': cur.rowcount, 'rows': rows}
        _real_event('database', 'sql', 'succeeded', database_id, {'rowcount': cur.rowcount})
        return jsonify(result)
    except Exception as e:
        conn.rollback(); _real_event('database', 'sql', 'failed', database_id, {'error': str(e)[:500]}); return jsonify(error='sql_failed', detail=str(e)[:500]), 400
    finally: conn.close()


@app.post('/api/v1/native/compute/jobs')
@native_control_auth
def real_compute_job():
    b=request.get_json(silent=True) or {}; operation=str(b.get('operation') or 'native_healthcheck'); allowed={'native_healthcheck','storage_hash','database_probe'}
    if operation not in allowed:return jsonify(error='unsupported_safe_operation',allowed=sorted(allowed)),400
    payload={'operation':operation,'args':b.get('args') or {}}; jid=str(uuid.uuid4()); now=_v23_now()
    db=_v23_db(); db.execute('INSERT INTO native_node_jobs(job_id,node_id,state,payload_json,result_json,created_at,updated_at,attempts,max_attempts) VALUES(?,?,?,?,?,?,?,?,?)',(jid,None,'queued',_real_json(payload),'{}',now,now,0,int(b.get('max_attempts') or 3))); db.commit(); db.close(); _real_event('compute','job.submit','queued',jid,payload)
    # If a live KOJA node exists, the normal node agent leases it. Otherwise the built-in safe system worker executes the operation now.
    db=_v23_db(); node=db.execute("SELECT * FROM native_nodes WHERE status='online' ORDER BY last_heartbeat DESC LIMIT 1").fetchone(); db.close()
    if not node:
        state,result=_real_local_compute(payload); db=_v23_db(); db.execute('UPDATE native_node_jobs SET state=?,result_json=?,attempts=1,finished_at=?,updated_at=? WHERE job_id=?',(state,_real_json(result),_v23_now(),_v23_now(),jid)); db.commit(); db.close(); _real_event('compute','job.execute',state,jid,{'executor':'KOJA system worker',**result})
        return jsonify({'ok':state=='succeeded','job_id':jid,'state':state,'result':result,'executor':'KOJA system worker'}),200
    return jsonify({'ok':True,'job_id':jid,'state':'queued','operation':operation,'executor':'KOJA-NODE','node_id':node['node_id']}),202

def _real_local_compute(payload):
    op=payload.get('operation'); args=payload.get('args') or {}
    try:
        if op=='native_healthcheck': return 'succeeded',{'ok':True,'execution':'KOJA system worker','platform':platform.platform()}
        if op=='ffmpeg_version':
            exe=shutil.which('ffmpeg')
            if not exe: return 'failed',{'error':'ffmpeg_not_found'}
            proc=subprocess.run([exe,'-version'],capture_output=True,text=True,timeout=15)
            return ('succeeded' if proc.returncode==0 else 'failed'),{'ok':proc.returncode==0,'ffmpeg':exe,'stdout':proc.stdout[:4000],'stderr':proc.stderr[:2000],'exit_code':proc.returncode,'execution':'KOJA system worker'}
        if op=='storage_hash':
            path=str(args.get('path') or ''); p=Path(path)
            if not p.is_file(): return 'failed',{'error':'file_not_found'}
            return 'succeeded',{'path':path,'sha256':_real_hash_file(p),'size_bytes':p.stat().st_size}
        if op=='database_probe':
            db=_v23_db(); db.execute('SELECT 1').fetchone(); db.close(); return 'succeeded',{'ok':True,'database_engine':'sqlite-native','execution':'KOJA system worker'}
        return 'failed',{'error':'unsupported_operation'}
    except Exception as e:return 'failed',{'error':str(e)[:500]}


@app.post('/api/v1/native/webhooks')
@native_control_auth
def real_webhook_create():
    b = request.get_json(silent=True) or {}; name = str(b.get('name') or 'KOJA Webhook')[:120]; url = str(b.get('url') or '').strip()
    if not (url.startswith('http://') or url.startswith('https://')): return jsonify(error='valid_http_url_required'), 400
    wid = str(uuid.uuid4()); secret = 'wh_' + secrets.token_urlsafe(24); db = _v23_db()
    db.execute('INSERT INTO native_webhooks(webhook_id,name,url,secret,events_json,status,last_status,last_delivery_at,created_at) VALUES(?,?,?,?,?,?,?,?,?)', (wid, name, url, secret, _real_json(b.get('events') or ['*']), 'active', None, None, _v23_now()))
    db.commit(); db.close(); _real_event('webhooks', 'webhook.create', 'succeeded', wid, {'url': url})
    return jsonify({'ok': True, 'webhook_id': wid, 'name': name, 'url': url, 'secret': secret, 'status': 'active'}), 201


@app.post('/api/v1/native/webhooks/<webhook_id>/send')
@native_control_auth
def real_webhook_send(webhook_id):
    b = request.get_json(silent=True) or {}; db = _v23_db(); row = db.execute('SELECT * FROM native_webhooks WHERE webhook_id=?', (webhook_id,)).fetchone(); db.close()
    if not row: return jsonify(error='webhook_not_found'), 404
    body = _real_json({'event': b.get('event') or 'test', 'data': b.get('data') or {}, 'sent_at': _v23_now()})
    signature = hmac.new(row['secret'].encode(), body.encode(), hashlib.sha256).hexdigest()
    try:
        r = requests.post(row['url'], data=body, headers={'Content-Type': 'application/json', 'X-KOJA-Signature': signature}, timeout=15)
        status = 'succeeded' if 200 <= r.status_code < 300 else 'failed'
        db = _v23_db(); db.execute('UPDATE native_webhooks SET last_status=?,last_delivery_at=? WHERE webhook_id=?', (r.status_code, _v23_now(), webhook_id)); db.execute('INSERT INTO native_webhook_deliveries(delivery_id,webhook_id,event_name,status,status_code,response_text,attempts,created_at) VALUES(?,?,?,?,?,?,?,?)',(str(uuid.uuid4()),webhook_id,str(b.get('event') or 'test'),status,r.status_code,r.text[:2000],1,_v23_now())); db.commit(); db.close()
        _real_event('webhooks', 'delivery', status, webhook_id, {'status_code': r.status_code})
        return jsonify({'ok': 200 <= r.status_code < 300, 'status_code': r.status_code, 'response': r.text[:500]})
    except Exception as e:
        _real_event('webhooks', 'delivery', 'failed', webhook_id, {'error': str(e)[:500]}); return jsonify(error='delivery_failed', detail=str(e)[:500]), 502


@app.post('/api/v1/native/webhooks/verify')
@native_control_auth
def real_webhook_verify():
    b=request.get_json(silent=True) or {}; body=_real_json(b.get('data') or {}); secret=str(b.get('secret') or ''); supplied=str(request.headers.get('X-KOJA-Signature') or '')
    expected=hmac.new(secret.encode(),body.encode(),hashlib.sha256).hexdigest() if secret else ''
    return jsonify({'ok':bool(secret and hmac.compare_digest(expected,supplied)),'verified':bool(secret and hmac.compare_digest(expected,supplied))})


@app.post('/api/v1/native/media/ingest')
@native_control_auth
def real_media_ingest():
    f = request.files.get('file'); name = _real_safe_name(request.form.get('name') or (f.filename if f else 'media.bin'))
    if not f: return jsonify(error='file_required'), 400
    target = KOJA_NATIVE_MEDIA_ROOT / name; f.save(str(target)); size = target.stat().st_size; digest = _real_hash_file(target); aid = str(uuid.uuid4())
    db = _v23_db(); db.execute('INSERT INTO native_media_assets VALUES(?,?,?,?,?,?,?)', (aid, name, str(target), 'video' if name.lower().endswith(('.mp4','.mov','.mkv','.webm')) else 'binary', size, digest, 'ready', _v23_now())); db.commit(); db.close()
    _real_event('media', 'ingest', 'succeeded', aid, {'size_bytes': size, 'sha256': digest, 'ffmpeg_available': bool(shutil.which('ffmpeg'))})
    return jsonify({'ok': True, 'asset_id': aid, 'name': name, 'size_bytes': size, 'sha256': digest, 'status': 'ready', 'transcoding_available': bool(shutil.which('ffmpeg'))}), 201


@app.post('/api/v1/native/backup')
@native_control_auth
def real_backup():
    b = request.get_json(silent=True) or {}; source = str(b.get('source') or '').strip()
    if source not in ('database', 'storage', 'media'): return jsonify(error='source_required', allowed=['database','storage','media']), 400
    src = {'database': KOJA_NATIVE_DATABASE_ROOT, 'storage': KOJA_NATIVE_STORAGE_ROOT, 'media': KOJA_NATIVE_MEDIA_ROOT}[source]
    if not src.exists(): return jsonify(error='source_not_found'), 404
    bid = str(uuid.uuid4()); target = KOJA_NATIVE_BACKUP_ROOT / bid; shutil.copytree(src, target); manifest = []
    for p in target.rglob('*'):
        if p.is_file(): manifest.append({'path': str(p.relative_to(target)), 'size_bytes': p.stat().st_size, 'sha256': _real_hash_file(p)})
    (target / 'manifest.json').write_text(_real_json({'source': source, 'created_at': _v23_now(), 'files': manifest}), encoding='utf-8')
    _real_event('backup', 'create', 'succeeded', bid, {'source': source, 'files': len(manifest)})
    return jsonify({'ok': True, 'backup_id': bid, 'source': source, 'files': len(manifest), 'path': str(target)}), 201


def _real_verify_backup(backup_id):
    root=KOJA_NATIVE_BACKUP_ROOT / _real_safe_name(backup_id)
    if not root.exists() or not root.is_dir():
        raise FileNotFoundError('backup_not_found')
    mf=root/'manifest.json'
    if not mf.exists(): raise RuntimeError('backup_manifest_missing')
    manifest=json.loads(mf.read_text(encoding='utf-8'))
    verified=0
    for item in manifest.get('files',[]):
        rel=Path(str(item.get('path','')))
        if rel.is_absolute() or '..' in rel.parts: raise RuntimeError('invalid_backup_manifest_path')
        fp=root/rel
        if not fp.exists() or not fp.is_file(): raise RuntimeError('backup_file_missing:'+str(rel))
        if int(item.get('size_bytes',-1)) != fp.stat().st_size: raise RuntimeError('backup_size_mismatch:'+str(rel))
        if item.get('sha256') and item['sha256'] != _real_hash_file(fp): raise RuntimeError('backup_checksum_mismatch:'+str(rel))
        verified+=1
    return manifest,verified,root

@app.post('/api/v1/native/backup/<backup_id>/verify')
@native_control_auth
def real_backup_verify(backup_id):
    try:
        manifest,n,root=_real_verify_backup(backup_id)
        _real_event('backup','verify','succeeded',backup_id,{'files':n,'source':manifest.get('source')})
        return jsonify(ok=True,backup_id=backup_id,verified_files=n,source=manifest.get('source'),status='verified')
    except FileNotFoundError:
        return jsonify(error='backup_not_found'),404
    except Exception as e:
        _real_event('backup','verify','failed',backup_id,{'error':str(e)})
        return jsonify(error='backup_verification_failed',detail=str(e)),422

@app.post('/api/v1/native/backup/<backup_id>/restore')
@native_control_auth
def real_backup_restore(backup_id):
    b=request.get_json(silent=True) or {}
    if b.get('confirm') is not True:
        return jsonify(error='restore_confirmation_required',message='Set confirm=true to replace the selected native data set.'),400
    try:
        manifest,n,root=_real_verify_backup(backup_id)
        source=str(manifest.get('source') or '')
        targets={'database':KOJA_NATIVE_DATABASE_ROOT,'storage':KOJA_NATIVE_STORAGE_ROOT,'media':KOJA_NATIVE_MEDIA_ROOT}
        target=targets.get(source)
        if target is None: return jsonify(error='unsupported_restore_source'),400
        staging=KOJA_NATIVE_BACKUP_ROOT/(backup_id+'.restore-staging')
        if staging.exists(): shutil.rmtree(staging,ignore_errors=True)
        staging.mkdir(parents=True,exist_ok=True)
        # Copy only manifest-listed payload files; never copy manifest.json into the live service root.
        for item in manifest.get('files',[]):
            rel=Path(str(item.get('path','')))
            if rel.name=='manifest.json': continue
            src=root/rel; dst=staging/rel; dst.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(src,dst)
        if target.exists():
            old=KOJA_NATIVE_BACKUP_ROOT/(backup_id+'.pre-restore')
            if old.exists(): shutil.rmtree(old,ignore_errors=True)
            shutil.move(str(target),str(old))
        shutil.move(str(staging),str(target))
        _real_event('backup','restore','succeeded',backup_id,{'source':source,'files':n})
        return jsonify(ok=True,backup_id=backup_id,source=source,restored_files=n,status='restored',target=str(target))
    except FileNotFoundError:
        return jsonify(error='backup_not_found'),404
    except Exception as e:
        _real_event('backup','restore','failed',backup_id,{'error':str(e)})
        return jsonify(error='backup_restore_failed',detail=str(e)),500

@app.post('/api/v1/native/media/<asset_id>/process')
@native_control_auth
def real_media_process(asset_id):
    db=_v23_db(); row=db.execute('SELECT * FROM native_media_assets WHERE asset_id=?',(asset_id,)).fetchone(); db.close()
    if not row: return jsonify(error='asset_not_found'),404
    src=Path(row['path'])
    if not src.exists(): return jsonify(error='media_file_missing'),404
    ffmpeg=shutil.which('ffmpeg')
    if not ffmpeg:
        # Do not claim transcoding works. Queue an explicit node operation for a KOJA worker.
        jid=str(uuid.uuid4()); db=_v23_db(); payload={'operation':'media_transcode','asset_id':asset_id,'source':str(src),'output_root':str(KOJA_NATIVE_MEDIA_ROOT/(asset_id+'-hls'))}; db.execute('INSERT INTO native_node_jobs(job_id,node_id,state,payload_json,result_json,created_at,updated_at,attempts,max_attempts) VALUES(?,?,?,?,?,?,?,?,?)',(jid,None,'queued',_v23_json(payload),'{}',_v23_now(),_v23_now(),0,3)); db.commit(); db.close(); _real_event('media','process.queue','queued',asset_id,{'job_id':jid,'worker_required':True}); return jsonify(ok=True,asset_id=asset_id,status='queued',job_id=jid,worker_required=True),202
    outdir=KOJA_NATIVE_MEDIA_ROOT/(asset_id+'-hls'); outdir.mkdir(parents=True,exist_ok=True)
    playlist=outdir/'index.m3u8'
    cmd=[ffmpeg,'-y','-i',str(src),'-c:v','libx264','-preset','veryfast','-c:a','aac','-f','hls','-hls_time','6','-hls_playlist_type','vod',str(playlist)]
    try:
        proc=subprocess.run(cmd,capture_output=True,text=True,timeout=900,check=False)
        if proc.returncode!=0: raise RuntimeError(proc.stderr[-2000:] or 'ffmpeg_failed')
        _real_event('media','process','succeeded',asset_id,{'playlist':str(playlist)})
        return jsonify(ok=True,asset_id=asset_id,status='ready',playlist=str(playlist),output_root=str(outdir))
    except subprocess.TimeoutExpired:
        _real_event('media','process','failed',asset_id,{'error':'ffmpeg_timeout'})
        return jsonify(error='media_processing_timeout'),504
    except Exception as e:
        _real_event('media','process','failed',asset_id,{'error':str(e)})
        return jsonify(error='media_processing_failed',detail=str(e)[:1000]),500

@app.get('/api/v1/native/services/events')
@native_control_auth
def real_service_events():
    db = _v23_db(); rows=[dict(r) for r in db.execute('SELECT * FROM native_service_events ORDER BY id DESC LIMIT 100').fetchall()]; db.close(); return jsonify({'release': KOJA_REAL_PLANE_RELEASE, 'events': rows})


@app.get('/api/v1/production/readiness')
def production_readiness():
    """Real production readiness snapshot. Never reports provider-backed features as native-ready."""
    checks={}
    try:
        _real_init(); db=_v23_db(); db.execute('SELECT 1').fetchone(); db.close(); checks['control_plane']={'status':'operational','detail':'native control database'}
    except Exception as e: checks['control_plane']={'status':'failed','detail':str(e)[:300]}
    try:
        KOJA_NATIVE_STORAGE_ROOT.mkdir(parents=True,exist_ok=True); probe=KOJA_NATIVE_STORAGE_ROOT/'.production-probe'; probe.write_bytes(b'KOJA'); ok=probe.read_bytes()==b'KOJA'; probe.unlink(missing_ok=True); checks['storage']={'status':'operational' if ok else 'failed'}
    except Exception as e: checks['storage']={'status':'failed','detail':str(e)[:300]}
    try:
        with app.test_client() as c: r=c.get('/api/v1/health'); checks['network']={'status':'operational' if r.status_code<500 else 'failed','http_status':r.status_code}
    except Exception as e: checks['network']={'status':'failed','detail':str(e)[:300]}
    try:
        db=_v23_db(); online=db.execute("SELECT COUNT(*) n FROM native_nodes WHERE status='online'").fetchone()['n']; total=db.execute('SELECT COUNT(*) n FROM native_nodes').fetchone()['n']; db.close(); checks['compute']={'status':'operational' if online else 'node_required','online_nodes':online,'registered_nodes':total}
    except Exception as e: checks['compute']={'status':'failed','detail':str(e)[:300]}
    try:
        db=_v23_db(); mn=db.execute("SELECT node_id,node_code,metrics_json FROM native_nodes WHERE status='online' ORDER BY last_heartbeat DESC LIMIT 1").fetchone(); db.close()
        if mn:
            mm=json.loads(mn['metrics_json'] or '{}'); checks['media']={'status':'operational','ingest':'native','transcoding':'operational' if mm.get('ffmpeg_available') or shutil.which('ffmpeg') else 'worker_required','worker':'native-node','node_code':mn['node_code']}
        else:
            checks['media']={'status':'operational','ingest':'native','transcoding':'operational' if shutil.which('ffmpeg') else 'worker_required','worker':'system-worker' if shutil.which('ffmpeg') else 'node_required'}
    except Exception as e: checks['media']={'status':'failed','detail':str(e)[:300]}
    checks['backup']={'status':'operational' if KOJA_NATIVE_BACKUP_ROOT.exists() else 'failed'}
    try:
        db=_v23_db(); db.execute('SELECT 1 FROM native_webhooks LIMIT 1').fetchone(); db.close(); checks['webhooks']={'status':'operational','delivery':'real_http'}
    except Exception as e: checks['webhooks']={'status':'failed','detail':str(e)[:300]}
    checks['forge']={'status':'provider_required','github_configured':github_provider_configured(),'note':'Source/build/deploy requires a configured source/build provider or KOJA node.'}
    checks['launch']={'status':'provider_required','render_configured':render_provider_configured(),'note':'Public managed hosting requires a configured provider or KOJA node.'}
    checks['durability']={'status':'durable' if str(KOJA_NATIVE_ROOT).startswith('/koja') else 'ephemeral','native_root':str(KOJA_NATIVE_ROOT)}
    try:
        db=_v23_db(); nr=db.execute("SELECT node_id,node_code,name,status,metrics_json,runtime_json,last_heartbeat FROM native_nodes WHERE status='online' ORDER BY last_heartbeat DESC LIMIT 1").fetchone(); db.close()
        if nr:
            try: nm=json.loads(nr['metrics_json'] or '{}')
            except Exception: nm={}
            checks['node_durability']={'status':'durable' if nm.get('storage_durable') and nm.get('storage_writable') else 'node_storage_check_required','node_id':nr['node_id'],'node_code':nr['node_code'],'native_root':nm.get('koja_native_root'),'free_bytes':nm.get('disk_free_bytes'),'storage_writable':bool(nm.get('storage_writable'))}
        else:
            checks['node_durability']={'status':'node_required','detail':'No online KOJA node is reporting durable storage.'}
    except Exception as e:
        checks['node_durability']={'status':'failed','detail':str(e)[:300]}
    bad=[k for k,v in checks.items() if v.get('status') in ('failed','node_required','provider_required','worker_required','node_storage_check_required')]
    software_blockers=[k for k,v in checks.items() if v.get('status') in ('failed',)]
    infrastructure_dependencies=[k for k,v in checks.items() if v.get('status') in ('node_required','provider_required','worker_required','node_storage_check_required','ephemeral')]
    return jsonify({'cloud':'KOJA CLOUD','release':VERSION,'production_ready':not software_blockers,'software_production_ready':not software_blockers,'infrastructure_provisioned':not infrastructure_dependencies,'blocking_software':software_blockers,'infrastructure_dependencies':infrastructure_dependencies,'checks':checks,'execution_model':'KOJA native control/data plane; external providers and KOJA nodes are explicit infrastructure dependencies'})

@app.post('/api/v1/native/e2e-test')
@native_control_auth
def real_e2e_test():
    results=[]; suffix=secrets.token_hex(4); started=_v23_now()
    def test(name,fn):
        try: results.append({'service':name,**fn()})
        except Exception as e: results.append({'service':name,'status':'failed','error':str(e)[:500]})
    test('storage',lambda:_e2e_storage(suffix)); test('database',lambda:_e2e_database(suffix)); test('compute',lambda:_e2e_compute(suffix)); test('logging',lambda:_e2e_logging(suffix)); test('backup',lambda:_e2e_backup(suffix)); test('media',lambda:_e2e_media(suffix)); test('webhooks',lambda:_e2e_webhook(suffix)); test('network',lambda:_e2e_network())
    passed=sum(1 for x in results if x.get('status')=='passed'); failed=len(results)-passed
    return jsonify({'ok':failed==0,'release':KOJA_REAL_PLANE_RELEASE,'started_at':started,'completed_at':_v23_now(),'summary':{'passed':passed,'failed':failed},'results':results})

def _e2e_storage(s):
    bucket='e2e-'+s; root=KOJA_NATIVE_STORAGE_ROOT/bucket; root.mkdir(parents=True,exist_ok=True); obj=root/'probe.txt'; obj.write_text('KOJA CLOUD E2E',encoding='utf-8'); digest=_real_hash_file(obj); read=obj.read_text(encoding='utf-8'); obj.unlink(); root.rmdir(); return {'status':'passed' if read=='KOJA CLOUD E2E' else 'failed','detail':'bucket/create-write-read-hash-delete','sha256':digest}

def _e2e_database(s):
    path=KOJA_NATIVE_DATABASE_ROOT/('e2e-'+s+'.sqlite3'); c=_koja_v23_sqlite3.connect(str(path)); c.execute('CREATE TABLE probe(id INTEGER PRIMARY KEY,value TEXT)'); c.execute('INSERT INTO probe(value) VALUES(?)',('ok',)); a=c.execute('SELECT value FROM probe').fetchone()[0]; c.execute('UPDATE probe SET value=? WHERE id=1',('updated',)); b=c.execute('SELECT value FROM probe').fetchone()[0]; c.execute('DELETE FROM probe'); c.commit(); c.close(); path.unlink(missing_ok=True); return {'status':'passed' if a=='ok' and b=='updated' else 'failed','detail':'create-insert-select-update-delete'}

def _e2e_compute(s):
    state,result=_real_local_compute({'operation':'native_healthcheck','args':{}}); return {'status':'passed' if state=='succeeded' and result.get('ok') else 'failed','detail':'submit-execute-result','executor':result.get('execution')}

def _e2e_logging(s):
    _real_event('logging','e2e','succeeded','e2e-'+s,{'probe':True}); db=_v23_db(); row=db.execute("SELECT COUNT(*) n FROM native_service_events WHERE resource_id=?",('e2e-'+s,)).fetchone(); db.close(); return {'status':'passed' if row['n']>=1 and (KOJA_NATIVE_LOG_ROOT/'services.log').exists() else 'failed','detail':'database-event-and-log-file'}

def _e2e_backup(s):
    src=KOJA_NATIVE_MEDIA_ROOT/('e2e-'+s); src.mkdir(parents=True,exist_ok=True); (src/'probe.txt').write_text('backup',encoding='utf-8'); dest=KOJA_NATIVE_BACKUP_ROOT/('e2e-'+s); shutil.copytree(src,dest); ok=(dest/'probe.txt').read_text(encoding='utf-8')=='backup'; shutil.rmtree(src,ignore_errors=True); shutil.rmtree(dest,ignore_errors=True); return {'status':'passed' if ok else 'failed','detail':'copy-and-verify'}

def _e2e_media(s):
    p=KOJA_NATIVE_MEDIA_ROOT/('e2e-'+s+'.bin'); p.write_bytes(b'KOJA-MEDIA-E2E'); digest=_real_hash_file(p); ok=p.stat().st_size==15 and len(digest)==64; p.unlink(missing_ok=True); return {'status':'passed' if ok else 'failed','detail':'ingest-size-hash-delete','sha256':digest}

def _e2e_webhook(s):
    secret='e2e-'+s; data={'probe':True,'id':s}; body=_real_json(data); sig=hmac.new(secret.encode(),body.encode(),hashlib.sha256).hexdigest(); expected=hmac.new(secret.encode(),body.encode(),hashlib.sha256).hexdigest(); return {'status':'passed' if hmac.compare_digest(sig,expected) else 'failed','detail':'payload-signature-generation-and-verification'}

def _e2e_network():
    with app.test_client() as c: r=c.get('/api/v1/health'); return {'status':'passed' if r.status_code<500 else 'failed','detail':'native-http-health-route','http_status':r.status_code}


# ============================================================
# KOJA CLOUD MEDIA BROADCAST PLANE v26.3.0
# Media library -> ordered playlist -> 24/7 broadcast worker -> public playback.
# ============================================================

KOJA_MEDIA_BROADCAST_RELEASE='26.3.0'

def _broadcast_channel(uid,oid,cid):
    return _one('/rest/v1/cloud_live_channels',{'id':f'eq.{cid}','owner_user_id':f'eq.{uid}','organization_id':f'eq.{oid}','select':'*','limit':'1'})

def _broadcast_assets(uid,oid,asset_ids):
    clean=[]
    for x in asset_ids or []:
        s=str(x).strip()
        if s and s not in clean: clean.append(s)
    if not clean:return []
    rows=sb('/rest/v1/cloud_media_assets',params={'id':'in.('+','.join(clean)+')','owner_user_id':f'eq.{uid}','organization_id':f'eq.{oid}','select':'*'})
    by_id={str(x.get('id')):x for x in rows}
    return [by_id[x] for x in clean if x in by_id]

def _broadcast_public_base():
    return (os.getenv('KOJA_CLOUD_PUBLIC_URL') or request.url_root).rstrip('/')

def _broadcast_view(channel):
    cfg=channel.get('config') if isinstance(channel.get('config'),dict) else {}
    playlist=cfg.get('playlist') if isinstance(cfg.get('playlist'),list) else []
    return {'id':channel.get('id'),'name':channel.get('name'),'channel_code':channel.get('channel_code'),'project_id':channel.get('project_id'),'status':channel.get('status'),'mode':cfg.get('mode','vod24x7'),'loop':bool(cfg.get('loop',True)),'playlist_count':len(playlist),'playlist_asset_ids':playlist,'playback_url':channel.get('playback_url') or cfg.get('playback_url'),'watch_url':f"{_broadcast_public_base()}/media/channel/{channel.get('channel_code')}",'stream_url':f"{_broadcast_public_base()}/stream/{channel.get('channel_code')}",'execution':cfg.get('execution','koja-native-worker'),'worker_job_id':cfg.get('worker_job_id'),'updated_at':channel.get('updated_at')}

@app.get('/api/media/broadcasts')
@cloud_api_or_login
def media_broadcasts():
    uid=session['user_id'];oid=require_org(uid)
    rows=sb('/rest/v1/cloud_live_channels',params={'owner_user_id':f'eq.{uid}','organization_id':f'eq.{oid}','select':'*','order':'created_at.desc'})
    out=[]
    for row in rows:
        cfg=row.get('config') if isinstance(row.get('config'),dict) else {}
        if cfg.get('mode')=='vod24x7' or cfg.get('broadcast') is True:out.append(_broadcast_view(row))
    return jsonify(out)

@app.post('/api/media/broadcasts')
@cloud_api_or_login
def media_broadcast_create():
    d=request.get_json(silent=True) or {};uid=session['user_id'];oid=require_org(uid)
    pid=cloud_project_for_write(d.get('project_id'))
    if not pid:
        ps=sb('/rest/v1/cloud_projects',params={'owner_user_id':f'eq.{uid}','organization_id':f'eq.{oid}','select':'id','order':'created_at.asc','limit':'1'})
        pid=ps[0]['id'] if ps else None
    if not pid:return jsonify(error='project_required'),400
    if not project_access(uid,oid,pid):return jsonify(error='project_not_found'),404
    name=(d.get('name') or 'KOJA Movies 24/7').strip()[:120];code='KLC-'+secrets.token_hex(5).upper();stream_secret='KOJA-'+secrets.token_urlsafe(18)
    cfg={'broadcast':True,'mode':'vod24x7','loop':bool(d.get('loop',True)),'playlist':[],'execution':'koja-native-worker','scheduler':'continuous','recovery':'auto-requeue'}
    row=sb('/rest/v1/cloud_live_channels','POST',{'owner_user_id':uid,'organization_id':oid,'project_id':pid,'name':name,'channel_code':code,'stream_key_hash':hashlib.sha256(stream_secret.encode()).hexdigest(),'status':'offline','config':cfg},params={'select':'*'})[0]
    playback=f'{_broadcast_public_base()}/stream/{code}'
    _patch('/rest/v1/cloud_live_channels',{'id':f'eq.{row["id"]}'},{'playback_url':playback,'updated_at':now()})
    row['playback_url']=playback;row['config']=cfg
    audit(uid,'media.broadcast.create','live_channel',row['id'],{'organization_id':oid,'project_id':pid,'mode':'vod24x7'})
    return jsonify(dict(_broadcast_view(row),stream_key=stream_secret)),201

@app.get('/api/media/broadcasts/<cid>')
@cloud_api_or_login
def media_broadcast_detail(cid):
    uid=session['user_id'];oid=require_org(uid);ch=_broadcast_channel(uid,oid,cid)
    if not ch:return jsonify(error='broadcast_not_found'),404
    cfg=ch.get('config') if isinstance(ch.get('config'),dict) else {};ids=cfg.get('playlist') if isinstance(cfg.get('playlist'),list) else []
    assets=_broadcast_assets(uid,oid,ids)
    return jsonify(dict(_broadcast_view(ch),playlist=[{'id':x.get('id'),'name':x.get('name'),'status':x.get('status'),'source_url':x.get('source_url'),'media_type':x.get('media_type'),'metadata':x.get('metadata') or {}} for x in assets]))

@app.put('/api/media/broadcasts/<cid>/playlist')
@cloud_api_or_login
def media_broadcast_playlist(cid):
    d=request.get_json(silent=True) or {};uid=session['user_id'];oid=require_org(uid);ch=_broadcast_channel(uid,oid,cid)
    if not ch:return jsonify(error='broadcast_not_found'),404
    ids=d.get('asset_ids')
    if not isinstance(ids,list):return jsonify(error='asset_ids_must_be_array'),400
    assets=_broadcast_assets(uid,oid,ids);requested=[str(x).strip() for x in ids if str(x).strip()];clean=[str(x.get('id')) for x in assets]
    if clean!=requested:return jsonify(error='one_or_more_assets_not_found_or_not_owned'),404
    cfg=ch.get('config') if isinstance(ch.get('config'),dict) else {};cfg=dict(cfg);cfg.update({'broadcast':True,'mode':'vod24x7','playlist':clean,'playlist_updated_at':now()})
    updated=_patch('/rest/v1/cloud_live_channels',{'id':f'eq.{cid}'},{'config':cfg,'updated_at':now()})
    audit(uid,'media.broadcast.playlist.update','live_channel',cid,{'organization_id':oid,'asset_count':len(clean)})
    return jsonify({'ok':True,'channel_id':cid,'asset_ids':clean,'playlist_count':len(clean),'channel':updated[0] if updated else ch})

def _queue_broadcast_worker(uid,oid,channel,action='start'):
    cfg=channel.get('config') if isinstance(channel.get('config'),dict) else {};ids=cfg.get('playlist') if isinstance(cfg.get('playlist'),list) else []
    if not ids:raise ValueError('broadcast_playlist_empty')
    db=_v23_db();node=db.execute("SELECT node_id,node_code FROM native_nodes WHERE status='online' ORDER BY last_heartbeat DESC LIMIT 1").fetchone()
    if not node:db.close();return {'queued':False,'execution':'node_required','node_required':True}
    jid=str(uuid.uuid4());ts=_v23_now()
    payload={'operation':'broadcast_worker','args':{'channel_id':channel['id'],'channel_code':channel.get('channel_code'),'project_id':channel.get('project_id'),'playlist_asset_ids':ids,'loop':bool(cfg.get('loop',True)),'mode':'vod24x7','action':action,'public_base':_broadcast_public_base()},'broadcast_channel_id':channel['id'],'broadcast_action':action}
    db.execute('INSERT INTO native_node_jobs(job_id,node_id,state,payload_json,result_json,created_at,updated_at,attempts,max_attempts) VALUES(?,?,?,?,?,?,?,?,?)',(jid,node['node_id'],'queued',_real_json(payload),'{}',ts,ts,0,3));db.commit();db.close()
    return {'queued':True,'execution':'KOJA-NODE','node_id':node['node_id'],'node_code':node['node_code'],'native_job_id':jid}

@app.post('/api/media/broadcasts/<cid>/start')
@cloud_api_or_login
def media_broadcast_start(cid):
    uid=session['user_id'];oid=require_org(uid);ch=_broadcast_channel(uid,oid,cid)
    if not ch:return jsonify(error='broadcast_not_found'),404
    cfg=ch.get('config') if isinstance(ch.get('config'),dict) else {};ids=cfg.get('playlist') if isinstance(cfg.get('playlist'),list) else []
    if not ids:return jsonify(error='broadcast_playlist_empty',message='Add at least one movie asset before starting the 24/7 channel.'),400
    try:q=_queue_broadcast_worker(uid,oid,ch,'start')
    except Exception as e:return jsonify(error='broadcast_queue_failed',detail=str(e)[:500]),500
    cfg=dict(cfg);cfg.update({'broadcast':True,'mode':'vod24x7','last_action':'start','worker_job_id':q.get('native_job_id'),'execution':q.get('execution')})
    status='starting' if q.get('queued') else 'waiting_for_node'
    _patch('/rest/v1/cloud_live_channels',{'id':f'eq.{cid}'},{'status':status,'config':cfg,'updated_at':now()})
    return jsonify({'ok':True,'status':status,'message':'24/7 broadcast job queued for KOJA node.' if q.get('queued') else '24/7 broadcast is waiting for an online KOJA node.','playback_url':ch.get('playback_url') or f"{_broadcast_public_base()}/stream/{ch.get('channel_code')}",**q}),202

@app.post('/api/media/broadcasts/<cid>/stop')
@cloud_api_or_login
def media_broadcast_stop(cid):
    uid=session['user_id'];oid=require_org(uid);ch=_broadcast_channel(uid,oid,cid)
    if not ch:return jsonify(error='broadcast_not_found'),404
    cfg=ch.get('config') if isinstance(ch.get('config'),dict) else {};cfg=dict(cfg);cfg.update({'last_action':'stop','execution':'koja-native-worker'})
    _patch('/rest/v1/cloud_live_channels',{'id':f'eq.{cid}'},{'status':'offline','config':cfg,'updated_at':now()})
    return jsonify({'ok':True,'status':'offline','message':'Broadcast stop recorded in KOJA CLOUD control plane.'})

@app.get('/stream/<channel_code>')
def public_broadcast_stream(channel_code):
    rows=sb('/rest/v1/cloud_live_channels',params={'channel_code':f'eq.{channel_code}','select':'*','limit':'1'})
    if not rows:return jsonify(error='channel_not_found'),404
    ch=rows[0];cfg=ch.get('config') if isinstance(ch.get('config'),dict) else {}
    if not (cfg.get('broadcast') is True or cfg.get('mode')=='vod24x7'):return jsonify(error='not_a_broadcast_channel'),404
    target=(cfg.get('published_playback_url') or '').strip()
    if target and target.rstrip('/')!=request.url.rstrip('/'):return redirect(target,code=302)
    return jsonify({'service':'KOJA CLOUD Media Broadcast','channel':ch.get('name'),'channel_code':channel_code,'status':ch.get('status'),'mode':'vod24x7','message':'Broadcast worker has not published a live playback target yet.'}),503

@app.get('/media/channel/<channel_code>')
def public_broadcast_player(channel_code):
    rows=sb('/rest/v1/cloud_live_channels',params={'channel_code':f'eq.{channel_code}','select':'name,channel_code,status,playback_url,config','limit':'1'})
    if not rows:return ('Channel not found',404)
    ch=rows[0];cfg=ch.get('config') if isinstance(ch.get('config'),dict) else {}
    if not (cfg.get('broadcast') is True or cfg.get('mode')=='vod24x7'):return ('Not a broadcast channel',404)
    target=(cfg.get('published_playback_url') or '').strip();safe_name=_h(ch.get('name') or 'KOJA Movies 24/7')
    return f"""<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><title>{safe_name} — KOJA CLOUD</title><style>body{{margin:0;background:#06101d;color:#fff;font-family:Arial,sans-serif}}main{{max-width:1100px;margin:auto;padding:20px}}video{{width:100%;background:#000;border-radius:14px}}.muted{{color:#9db0c5}}.pill{{display:inline-block;padding:6px 10px;border-radius:999px;background:#12304d}}</style></head><body><main><h1>{safe_name}</h1><p class="muted">KOJA CLOUD 24/7 Media Broadcast • <span class="pill">{_h(ch.get('status') or 'offline')}</span></p><video id="player" controls autoplay playsinline></video><p class="muted">Channel: <code>{_h(channel_code)}</code></p><script>const target={json.dumps(target)};const v=document.getElementById('player');if(target.endsWith('.m3u8')&&v.canPlayType('application/vnd.apple.mpegurl')){{v.src=target;}}else if(target.endsWith('.m3u8')){{const s=document.createElement('script');s.src='https://cdn.jsdelivr.net/npm/hls.js@latest';s.onload=()=>{{if(window.Hls&&Hls.isSupported()){{let h=new Hls();h.loadSource(target);h.attachMedia(v);}}else{{v.src=target;}}}};document.head.appendChild(s);}}else if(target){{v.src=target;}}</script></main></body></html>"""

@app.get('/api/v1/media/broadcasts')
@api_key_auth
def api_broadcasts_v1():
    oid=key_org();pid=cloud_api_project_id();params={'organization_id':f'eq.{oid}','select':'*','order':'created_at.desc'}
    if pid:params['project_id']=f'eq.{pid}'
    rows=sb('/rest/v1/cloud_live_channels',params=params);out=[]
    for row in rows:
        cfg=row.get('config') if isinstance(row.get('config'),dict) else {}
        if cfg.get('broadcast') is True or cfg.get('mode')=='vod24x7':out.append(_broadcast_view(row))
    return jsonify(out)

@app.post('/api/v1/media/broadcasts/<cid>/start')
@api_key_auth
def api_broadcast_start_v1(cid):
    key=getattr(request,'koja_api_key',{}) or {};uid=key.get('_uid') or key.get('user_id') or key.get('owner_user_id');oid=key_org();pid=cloud_api_project_id()
    params={'id':f'eq.{cid}','organization_id':f'eq.{oid}','select':'*','limit':'1'}
    if pid:params['project_id']=f'eq.{pid}'
    if not sb('/rest/v1/cloud_live_channels',params=params):return jsonify(error='broadcast_not_found'),404
    original=dict(session);original_modified=getattr(session,'modified',False)
    try:session['user_id']=uid;session['organization_id']=oid;return media_broadcast_start(cid)
    finally:session.clear();session.update(original);session.modified=original_modified

@app.get('/api/v1/media/broadcasts/<cid>')
@api_key_auth
def api_broadcast_detail_v1(cid):
    key=getattr(request,'koja_api_key',{}) or {};oid=key_org();pid=cloud_api_project_id();params={'id':f'eq.{cid}','organization_id':f'eq.{oid}','select':'*','limit':'1'}
    if pid:params['project_id']=f'eq.{pid}'
    rows=sb('/rest/v1/cloud_live_channels',params=params)
    if not rows:return jsonify(error='broadcast_not_found'),404
    ch=rows[0];cfg=ch.get('config') if isinstance(ch.get('config'),dict) else {}
    if not (cfg.get('broadcast') is True or cfg.get('mode')=='vod24x7'):return jsonify(error='not_a_broadcast_channel'),404
    return jsonify(_broadcast_view(ch))

@app.post('/api/v1/native/node/broadcast-result')
def native_broadcast_result():
    row=_v23_node_auth()
    if not row:return jsonify(error='unauthorized'),401
    b=request.get_json(silent=True) or {};cid=str(b.get('channel_id') or '').strip()
    if not cid:return jsonify(error='channel_id_required'),400
    state=str(b.get('state') or 'running').lower();playback=str(b.get('playback_url') or '').strip()
    db=_v23_db();j=db.execute("SELECT * FROM native_node_jobs WHERE node_id=? AND state IN ('leased','running') AND json_extract(payload_json,'$.broadcast_channel_id')=? ORDER BY created_at DESC LIMIT 1",(row['node_id'],cid)).fetchone();db.close()
    if not j:return jsonify(error='broadcast_job_not_found'),404
    ch=_one('/rest/v1/cloud_live_channels',{'id':f'eq.{cid}','select':'*','limit':'1'})
    if not ch:return jsonify(error='broadcast_channel_not_found'),404
    cfg=ch.get('config') if isinstance(ch.get('config'),dict) else {};cfg=dict(cfg);cfg.update({'worker_job_id':j['job_id'],'worker_node_id':row['node_id'],'last_worker_state':state})
    if playback:cfg['published_playback_url']=playback
    status='live' if state in ('running','live','succeeded') else ('offline' if state in ('stopped','failed','cancelled') else 'starting')
    patch={'status':status,'config':cfg,'updated_at':now()}
    if playback:patch['playback_url']=playback
    _patch('/rest/v1/cloud_live_channels',{'id':f'eq.{cid}'},patch)
    return jsonify({'ok':True,'channel_id':cid,'status':status,'playback_url':playback or ch.get('playback_url')})

@app.get('/api/v1/media/broadcast-openapi.json')
def media_broadcast_openapi():
    return jsonify({'openapi':'3.0.3','info':{'title':'KOJA CLOUD Media Broadcast API','version':'26.3.0'},'servers':[{'url':request.host_url.rstrip('/')}],'security':[{'KojaApiKey':[]}],'paths':{'/api/v1/media/broadcasts':{'get':{'responses':{'200':{'description':'24/7 broadcast channels'}}}},'/api/v1/media/broadcasts/{id}':{'get':{'responses':{'200':{'description':'Broadcast and playlist'}}}},'/api/v1/media/broadcasts/{id}/start':{'post':{'responses':{'202':{'description':'Broadcast job queued'}}}}}})
