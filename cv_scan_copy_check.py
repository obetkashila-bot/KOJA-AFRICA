"""SmartCV scan copies: saved to the existing KOJA Documents as pending, visible to the owner, public only when approved.
Storage is an in-memory fake. Run from a directory that holds app.py (copy app.py there first)."""
import sys, uuid, io
sys.path.insert(0, '/home/claude/koja_tests')
from harness import A, run, select
A.app.config['TESTING'] = True
res = []
def chk(name, cond, extra=''):
    res.append(bool(cond)); print(('PASS ' if cond else 'FAIL ') + name, extra)
run("create table if not exists public.documents (id uuid primary key, title text, description text, category text, subject text, author text, tags text, user_id text, file_name text, file_path text, file_url text, approval_status text, is_public boolean, is_active boolean, created_at timestamptz, updated_at timestamptz)")
run("create table if not exists public.koja_cv_settings (user_id text primary key, auto_save_documents boolean not null default false, updated_at timestamptz not null default now())")
run("delete from public.koja_cv_settings"); run("delete from public.documents"); run("delete from public.koja_cvs")
STORE = {}
def fake_upload(fs, folder='uploads', public=False, max_mb=None, allowed=None):
    data = fs.read(); path = '%s/%s_%s' % (folder, uuid.uuid4().hex, fs.filename)
    STORE[path] = data
    return {'path': path, 'url': None, 'file_name': fs.filename, 'file_size': len(data)}, None
A.upload_storage = fake_upload
A.delete_storage_path = lambda path: STORE.pop(path, None)
A._ai_call = lambda *a, **k: ('{"full_name": "Grace Mwansa", "experience": "Taught Grade 7"}', None)
OWNER, OTHER = str(uuid.uuid4()), str(uuid.uuid4())
def client(uid, name, admin=False):
    c = A.app.test_client()
    with c.session_transaction() as s:
        s['user'] = {'id': uid, 'name': name, 'email': 'x@x.test', 'is_admin': admin}; s['_csrf_token'] = 'tok'
    return c
me, other, anon = client(OWNER, 'Grace'), client(OTHER, 'Other'), A.app.test_client()
CERT = b'Certificate: Diploma in Early Childhood Education, 2019.'
def scan(c, save):
    form = {'_csrf_token': 'tok', 'consent': '1', 'document': (io.BytesIO(CERT), 'certificate.txt')}
    if save: form['save_copy'] = '1'
    return c.post('/cv/start/scan', data=form, content_type='multipart/form-data', follow_redirects=True).get_data(as_text=True)

page = me.get('/cv/start').get_data(as_text=True)
chk('the Documents save option is offered but unticked by default', 'KOJA Documents' in page and 'name="save_copy" value="1">' in page)
r = scan(me, save=True)
docs = select('documents', {'user_id': OWNER})
chk('a scan with the save option adds one document', len(docs) == 1)
d = docs[0] if docs else {}
chk('the copy is pending, not public', d.get('approval_status') == 'pending' and str(d.get('is_public')).lower() in ('false', 'f', '0'))
chk('the stored file is the original bytes', STORE.get(d.get('file_path')) == CERT)
chk('the scan result says the copy is pending approval', 'pending until it is approved' in r)
chk('the draft CV is still made', len(select('koja_cvs', {'user_id': OWNER})) == 1)
scan(me, save=False)
chk('a scan without the save option adds nothing', len(select('documents', {'user_id': OWNER})) == 1)

# visibility follows the existing rule: owner and admins see pending; others see it only once approved
chk('the owner sees the pending copy in KOJA Documents', d.get('title', 'x') in me.get('/documents').get_data(as_text=True))
chk('another user does not see it while pending', d.get('title', 'x') not in other.get('/documents').get_data(as_text=True))
admin = client(str(uuid.uuid4()), 'Admin', admin=True)
chk('an admin sees it for review', d.get('title', 'x') in admin.get('/documents').get_data(as_text=True))
run("update public.documents set approval_status='approved' where id='%s'" % d.get('id'))
chk('once approved, other users see it', d.get('title', 'x') in other.get('/documents').get_data(as_text=True))
# opt-in automatic saving: only after an explicit agreement, visible, and reversible
r = me.post('/cv/start/auto-save', data={'_csrf_token': 'tok', 'on': '1'}, follow_redirects=True).get_data(as_text=True)
chk('turning it on without agreeing is refused', 'Tick the box to say you agree' in r and len(select('koja_cv_settings', {'user_id': OWNER})) == 0)
me.post('/cv/start/auto-save', data={'_csrf_token': 'tok', 'on': '1', 'agree': '1'})
chk('after agreeing, the setting is on', 'Automatic saving is on' in me.get('/cv/start').get_data(as_text=True))
before_auto = len(select('documents', {'user_id': OWNER}))
me.post('/cv/start/scan', data={'_csrf_token': 'tok', 'document': (io.BytesIO(CERT), 'auto.txt')}, content_type='multipart/form-data')
chk('with the standing permission on, a scan needs no consent tick and is saved', len(select('documents', {'user_id': OWNER})) == before_auto + 1)
chk('the standing-permission scan still makes the CV draft', len(select('koja_cvs', {'user_id': OWNER})) >= 1)
chk('other people are not affected by the setting', len(select('documents', {'user_id': OTHER})) == 0)
other.post('/cv/start/scan', data={'_csrf_token': 'tok', 'consent': '1', 'document': (io.BytesIO(CERT), 'other.txt')}, content_type='multipart/form-data')
chk('another person scanning without the setting saves nothing', len(select('documents', {'user_id': OTHER})) == 0)
me.post('/cv/start/auto-save', data={'_csrf_token': 'tok', 'on': '0'})
before_off = len(select('documents', {'user_id': OWNER}))
me.post('/cv/start/scan', data={'_csrf_token': 'tok', 'document': (io.BytesIO(CERT), 'no-tick.txt')}, content_type='multipart/form-data')
chk('with the permission off, a scan without the tick is refused', len(select('documents', {'user_id': OWNER})) == before_off)
me.post('/cv/start/scan', data={'_csrf_token': 'tok', 'consent': '1', 'document': (io.BytesIO(CERT), 'after-off.txt')}, content_type='multipart/form-data')
chk('after turning it off, scans are not saved', len(select('documents', {'user_id': OWNER})) == before_auto + 1)
chk('anonymous users cannot change the setting', anon.post('/cv/start/auto-save', data={'on': '1', 'agree': '1'}).status_code in (302, 401, 403))
run("delete from public.documents"); run("delete from public.koja_cvs")
print('RESULT: %d/%d passed' % (sum(res), len(res)))
