"""KOJA Media V6 HLS worker.

Run as a separate Render Background Worker or equivalent process.
Requires ffmpeg + ffprobe on PATH and Supabase environment variables.
It scans published video posts that do not yet have a master playlist, downloads
one source video, creates adaptive HLS renditions, uploads them to a public HLS
bucket, then records the master playlist URL in koja_public_posts.
"""
import os, re, json, time, shutil, tempfile, subprocess
from pathlib import Path
from urllib.parse import quote, unquote
import requests

SUPABASE_URL=os.getenv('SUPABASE_URL','').rstrip('/')
SUPABASE_SERVICE_KEY=os.getenv('SUPABASE_SERVICE_KEY','') or os.getenv('SUPABASE_KEY','')
STORAGE_BUCKET=os.getenv('SUPABASE_STORAGE_BUCKET','koja-files')
HLS_BUCKET=os.getenv('KOJA_HLS_BUCKET','koja-media-hls')
HLS_PUBLIC_BASE=os.getenv('KOJA_HLS_PUBLIC_BASE','').rstrip('/')
POLL_SECONDS=int(os.getenv('KOJA_MEDIA_WORKER_POLL_SECONDS','20'))
SEGMENT_SECONDS=int(os.getenv('KOJA_HLS_SEGMENT_SECONDS','4'))
MAX_JOBS=int(os.getenv('KOJA_MEDIA_WORKER_MAX_JOBS','1'))


def headers(extra=None):
    h={'apikey':SUPABASE_SERVICE_KEY,'Content-Type':'application/json'}
    if SUPABASE_SERVICE_KEY and not SUPABASE_SERVICE_KEY.startswith('sb_secret_'):
        h['Authorization']='Bearer '+SUPABASE_SERVICE_KEY
    if extra:h.update(extra)
    return h

def rest(table):return f'{SUPABASE_URL}/rest/v1/{quote(table,safe="")}'
def storage(path,bucket=None):return f'{SUPABASE_URL}/storage/v1/object/{quote(bucket or STORAGE_BUCKET,safe="")}/{quote(path,safe="/")}'
def public_storage(path,bucket=None):return f'{SUPABASE_URL}/storage/v1/object/public/{quote(bucket or HLS_BUCKET,safe="")}/{quote(path,safe="/")}'

def select(params):
    r=requests.get(rest('koja_public_posts'),headers=headers(),params=params,timeout=30);r.raise_for_status();return r.json()
def patch(pid,data):
    r=requests.patch(rest('koja_public_posts'),headers=headers({'Prefer':'return=minimal'}),params={'id':f'eq.{pid}'},json=data,timeout=30);r.raise_for_status()

def ensure_bucket():
    r=requests.post(f'{SUPABASE_URL}/storage/v1/bucket',headers=headers(),json={'id':HLS_BUCKET,'name':HLS_BUCKET,'public':True,'file_size_limit':0},timeout=30)
    if r.status_code not in (200,201,409): print('bucket:',r.status_code,r.text[:300])

def source_path(value):
    value=str(value or '')
    prefix=f'{SUPABASE_URL}/storage/v1/object/public/{quote(STORAGE_BUCKET,safe="")}/'
    if value.startswith(prefix):return unquote(value[len(prefix):])
    if value.startswith(('http://','https://')):
        m=re.search(r'/storage/v1/object/(?:public/)?'+re.escape(STORAGE_BUCKET)+r'/(.+)$',value)
        if m:return unquote(m.group(1))
        raise ValueError('Media URL is not a KOJA storage object')
    return value.lstrip('/')

def download_source(path,out):
    with requests.get(storage(path),headers=headers(),stream=True,timeout=60) as r:
        r.raise_for_status()
        with open(out,'wb') as f:
            for chunk in r.iter_content(1024*1024):
                if chunk:f.write(chunk)

def ffprobe(src):
    cmd=['ffprobe','-v','error','-show_entries','stream=width,height,duration','-of','json','-select_streams','v:0',src]
    p=subprocess.run(cmd,capture_output=True,text=True,check=True)
    st=(json.loads(p.stdout).get('streams') or [{}])[0]
    return int(st.get('width') or 0),int(st.get('height') or 0),float(st.get('duration') or 0)

def renditions(height):
    return [(360,700000,80000),(480,1200000,96000),(720,2500000,128000),(1080,5000000,160000) if height>=1080 else None]

def build_hls(src,out,height):
    rs=[x for x in renditions(height) if x and height>=x[0]]
    # At least one rendition; 360p is used for sources below 360p.
    if not rs: rs=[(height,500000,64000)]
    filters=[];maps=[]
    for i,(h,vb,ab) in enumerate(rs):
        filters.append(f'[0:v]scale=w=-2:h={h}:force_original_aspect_ratio=decrease[v{i}]')
        maps += ['-map',f'[v{i}]','-map','0:a:0?']
    cmd=['ffmpeg','-y','-i',src,'-filter_complex',';'.join(filters)]
    cmd += maps
    # Encode each mapped video/audio pair with per-stream settings.
    for i,(h,vb,ab) in enumerate(rs):
        cmd += [f'-c:v:{i}','libx264',f'-b:v:{i}',str(vb),f'-maxrate:v:{i}',str(int(vb*1.12)),f'-bufsize:v:{i}',str(vb*2),f'-preset:v:{i}','veryfast',f'-g:v:{i}','48',f'-keyint_min:v:{i}','48']
        cmd += [f'-c:a:{i}','aac',f'-b:a:{i}',str(ab)]
    varmap=' '.join(f'v:{i},a:{i}' for i in range(len(rs)))
    cmd += ['-f','hls','-hls_time',str(SEGMENT_SECONDS),'-hls_playlist_type','vod','-hls_flags','independent_segments','-master_pl_name','master.m3u8','-var_stream_map',varmap,'-hls_segment_filename',str(out/'v%v'/'seg_%05d.ts'),str(out/'v%v'/'index.m3u8')]
    for i in range(len(rs)):(out/f'v{i}').mkdir(parents=True,exist_ok=True)
    subprocess.run(cmd,check=True)
    # Rewrite master labels to stable quality names and preserve relative playlists.
    master=(out/'master.m3u8').read_text()
    for i,(h,_,_) in enumerate(rs): master=master.replace(f'NAME="v{i}"',f'NAME="{h}p"')
    (out/'master.m3u8').write_text(master)
    return rs

def upload_tree(root,base):
    for f in root.rglob('*'):
        if not f.is_file():continue
        rel=f.relative_to(root).as_posix(); path=f'{base}/{rel}'
        mime='application/vnd.apple.mpegurl' if f.suffix=='.m3u8' else 'video/mp2t'
        if f.suffix=='.vtt':mime='text/vtt'
        with open(f,'rb') as fh:
            r=requests.post(storage(path,HLS_BUCKET),headers=headers({'Content-Type':mime,'x-upsert':'true','Cache-Control':'public,max-age=31536000,immutable'}),data=fh,timeout=60)
        r.raise_for_status()

def process(post):
    pid=str(post['id']); work=Path(tempfile.mkdtemp(prefix='koja-hls-'))
    try:
        patch(pid,{'media_processing_status':'processing','media_processing_error':None})
        src=work/'source'; download_source(source_path(post['media_url']),src)
        w,h,d=ffprobe(str(src)); out=work/'hls';out.mkdir()
        rs=build_hls(str(src),out,h)
        base=f'posts/{pid}'; upload_tree(out,base)
        master=(HLS_PUBLIC_BASE.rstrip('/')+'/'+base+'/master.m3u8') if HLS_PUBLIC_BASE else public_storage(f'{base}/master.m3u8')
        patch(pid,{'media_processing_status':'ready','media_master_url':master,'media_duration_seconds':d,'media_source_width':w,'media_source_height':h,'media_processed_at':time.strftime('%Y-%m-%dT%H:%M:%SZ'),'media_processing_error':None})
        print('READY',pid,w,h,d,rs)
    except Exception as e:
        print('ERROR',pid,e); 
        try:patch(pid,{'media_processing_status':'error','media_processing_error':str(e)[:1000]})
        except Exception:pass
    finally:shutil.rmtree(work,ignore_errors=True)

def main():
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY: raise SystemExit('SUPABASE_URL and SUPABASE_SERVICE_KEY are required')
    subprocess.run(['ffmpeg','-version'],stdout=subprocess.DEVNULL,check=True);subprocess.run(['ffprobe','-version'],stdout=subprocess.DEVNULL,check=True);ensure_bucket()
    while True:
        try:
            rows=select({'select':'id,media_url,media_type,media_master_url,is_published','is_published':'eq.true','media_type':'eq.video','media_master_url':'is.null','order':'created_at.asc','limit':MAX_JOBS})
            for post in rows:process(post)
        except Exception as e: print('worker loop:',e)
        time.sleep(POLL_SECONDS)
if __name__=='__main__':main()
