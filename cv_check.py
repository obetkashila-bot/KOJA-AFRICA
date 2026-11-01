"""KOJA CV: saved to the account, validated on the server, escaped, editable, printable, private to its owner.
Run from a directory that holds app.py."""
import sys, uuid, subprocess
sys.path.insert(0, '/home/claude/koja_tests')
from harness import A, run, select, PSQL
A.app.config['TESTING'] = True
res = []
def chk(name, cond, extra=''):
    res.append(bool(cond)); print(('PASS ' if cond else 'FAIL ') + name, extra)
subprocess.run(PSQL + ['-f', '/home/claude/outputs/koja_app_final/koja_cvs.sql'], capture_output=True, text=True, check=True)
run("delete from public.koja_cvs")
OWNER, OTHER = str(uuid.uuid4()), str(uuid.uuid4())
def client(uid, name):
    c = A.app.test_client()
    with c.session_transaction() as s:
        s['user'] = {'id': uid, 'name': name, 'email': name.lower().replace(' ', '') + '@x.test', 'is_admin': False}; s['_csrf_token'] = 'tok'
    return c
me, other = client(OWNER, 'Mary Banda'), client(OTHER, 'Other Person')
GOOD = {'_csrf_token': 'tok', 'full_name': 'Mary Banda', 'phone': '+260 971 234567', 'email': 'mary@example.com',
        'address': 'Lusaka', 'profile': 'Nurse with 6 years experience.\nRuns community clinics.',
        'education': 'BSc Nursing, UNZA, 2018', 'experience': 'Clinic Lead, Lusaka District', 'skills': 'First aid\nTraining',
        'references': 'Available on request'}

# 1. Form opens, prefilled from the account
r = me.get('/cv')
chk('CV form opens and is prefilled from the account', r.status_code == 200 and 'Mary Banda' in r.get_data(as_text=True))

# 2. A valid CV is saved and opens on its own page
r = me.post('/cv', data=GOOD)
rows = select('koja_cvs', {'user_id': OWNER})
chk('valid CV is saved to the account', r.status_code == 302 and len(rows) == 1, r.status_code)
cid = rows[0]['id']
view = me.get('/cv/%s' % cid).get_data(as_text=True)
chk('saved CV shows its contents', 'Mary Banda' in view and 'Clinic Lead' in view and 'UNZA' in view)
chk('printing: only the CV sheet is shown', '@media print' in view and 'visibility:visible' in view and 'cv-actions{display:none' in view.replace(' ', ''))
chk('line breaks are kept in every section', view.count('white-space:pre-wrap') >= 1 and 'Runs community clinics.' in view)

# 3. Server-side validation (the browser checks are not enough)
r = me.post('/cv', data=dict(GOOD, full_name='', email='not-an-email'))
h = r.get_data(as_text=True)
chk('empty name is refused on the server', 'Full name is required' in h)
chk('bad email is refused on the server', 'Email must look like' in h)
chk('refused form keeps what was typed', 'Clinic Lead' in h and 'Lusaka' in h)
chk('refused CV is not saved', len(select('koja_cvs', {'user_id': OWNER})) == 1)
r = me.post('/cv', data=dict(GOOD, profile='x' * 1501))
chk('text over the limit is refused, not cut', 'Professional profile is too long' in r.get_data(as_text=True) and len(select('koja_cvs', {'user_id': OWNER})) == 1)
r = me.post('/cv', data=dict(GOOD, phone='call me'))
chk('bad phone is refused', 'Phone must have' in r.get_data(as_text=True))

# 4. Text is escaped
r = me.post('/cv', data=dict(GOOD, profile='<script>alert(1)</script>Safe text'))
v = me.get('/cv/%s' % select('koja_cvs', {'user_id': OWNER}, order='updated_at.desc')[0]['id']).get_data(as_text=True)
chk('script tags in the CV are shown as text', '&lt;script&gt;' in v and '<script>alert(1)' not in v)

# 5. Editing keeps the CV in place
r = me.post('/cv/%s/edit' % cid, data=dict(GOOD, skills='Midwifery\nEmergency care'))
chk('edit saves', r.status_code == 302)
chk('edited skills show', 'Midwifery' in me.get('/cv/%s' % cid).get_data(as_text=True))
chk('edit does not create a second CV', len(select('koja_cvs', {'user_id': OWNER})) == 2)

# 6. Privacy: another user cannot see, edit or delete it
chk('another user gets 404 when opening it', other.get('/cv/%s' % cid).status_code == 404)
chk('another user gets 404 when editing it', other.post('/cv/%s/edit' % cid, data=GOOD).status_code == 404)
chk('another user gets 404 when deleting it', other.post('/cv/%s/delete' % cid, data={'_csrf_token': 'tok'}).status_code == 404)
chk('another user does not see it in their list', 'Mary Banda' not in other.get('/cv').get_data(as_text=True))
chk('invalid id gives 404', me.get('/cv/not-an-id').status_code == 404)

# 7. The owner's list and delete
chk('owner list shows the saved CV', 'Your saved CVs' in me.get('/cv').get_data(as_text=True))
r = me.post('/cv/%s/delete' % cid, data={'_csrf_token': 'tok'})
chk('owner can delete the CV', r.status_code == 302 and len(select('koja_cvs', {'user_id': OWNER})) == 1)

# 8. Profile photo and certifications
import io
import io as _fio
from PIL import Image as _FI
_jb = _fio.BytesIO(); _FI.new('RGB', (120, 160), (200, 80, 60)).save(_jb, 'JPEG'); JPEG = _jb.getvalue()
_pb = _fio.BytesIO(); _FI.new('RGB', (120, 160), (60, 80, 200)).save(_pb, 'PNG'); PNG = _pb.getvalue()
def up(name, blob):
    return (io.BytesIO(blob), name)
chk('CV form accepts a photo upload', b'enctype="multipart/form-data"' in me.get('/cv').data)
r = me.post('/cv', data=dict(GOOD, full_name='Photo Person', certifications='Registered Nurse, NMC 2019\nFirst aid instructor', photo=up('me.jpg', JPEG)), content_type='multipart/form-data')
rows = [x for x in select('koja_cvs', {'user_id': OWNER}) if x.get('title') == 'Photo Person']
chk('CV with a JPG photo is saved', r.status_code == 302 and len(rows) == 1, r.status_code)
pid = rows[0]['id'] if rows else None
v = me.get('/cv/%s' % pid).get_data(as_text=True) if pid else ''
chk('photo shows on the CV', 'class="cv-photo"' in v and 'data:image/jpeg;base64,' in v)
chk('certifications are saved and shown', 'Registered Nurse, NMC 2019' in v and 'Certifications and licences' in v)
r = me.post('/cv', data=dict(GOOD, full_name='Png Person', photo=up('me.png', PNG)), content_type='multipart/form-data')
chk('a PNG photo is accepted', r.status_code == 302)
r = me.post('/cv', data=dict(GOOD, full_name='Text Person', photo=up('me.txt', b'hello there' * 10)), content_type='multipart/form-data')
chk('a non-image file is refused', 'must be a JPG or PNG' in r.get_data(as_text=True) and not select('koja_cvs', {'user_id': OWNER, 'title': 'Text Person'}))
import os as _os
from PIL import Image as _PImg
import io as _pio
_bigbuf=_pio.BytesIO(); _PImg.frombytes('RGB',(2400,3000),_os.urandom(2400*3000*3)).save(_bigbuf,'JPEG',quality=95); BIG_JPG=_bigbuf.getvalue()
from werkzeug.datastructures import FileStorage as _FS
_bp_url, _bp_err = A._cv_read_photo(_FS(_fio.BytesIO(BIG_JPG), filename='big.jpg'))
chk('a large photo is accepted and made smaller', not _bp_err and _bp_url.startswith('data:image/jpeg') and len(_bp_url) <= 300 * 1024 * 4 // 3 + 64, (len(BIG_JPG), len(_bp_url)))
if pid:
    r = me.post('/cv/%s/edit' % pid, data=dict(GOOD, full_name='Photo Person', certifications='Registered Nurse, NMC 2019\nFirst aid instructor'), content_type='multipart/form-data')
    chk('editing without a new photo keeps the photo', 'class="cv-photo"' in me.get('/cv/%s' % pid).get_data(as_text=True))
    r = me.post('/cv/%s/edit' % pid, data=dict(GOOD, full_name='Photo Person', certifications='Registered Nurse, NMC 2019', remove_photo='1'), content_type='multipart/form-data')
    chk('remove photo deletes it', 'class="cv-photo"' not in me.get('/cv/%s' % pid).get_data(as_text=True))

run("delete from public.koja_cvs")
print('RESULT: %d/%d passed' % (sum(res), len(res)))
