"""KOJA CV downloads: PDF and Word files open, contain the CV text and photo, escape special characters, and are private.
Run from a directory that holds app.py."""
import sys, uuid, io, subprocess
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
        s['user'] = {'id': uid, 'name': name, 'email': 'x@x.test', 'is_admin': False}; s['_csrf_token'] = 'tok'
    return c
me, other = client(OWNER, 'Mary Banda'), client(OTHER, 'Other Person')
import base64
PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==')
PHOTO = 'data:image/png;base64,' + base64.b64encode(PNG).decode()
r = me.post('/cv', data={'_csrf_token': 'tok', 'full_name': 'Mary Banda', 'email': 'mary@example.com', 'phone': '+260 971 234567',
    'address': 'Lusaka', 'profile': 'Nurse & midwife, <strong>experienced</strong>.',
    'experience': 'Clinic Lead, Lusaka District\nTrained 40 staff', 'education': 'BSc Nursing, UNZA, 2018',
    'skills': 'First aid', 'certifications': 'NMC Registered 2019', 'references': 'Available on request'},
    content_type='multipart/form-data')
cid = select('koja_cvs', {'user_id': OWNER})[0]['id']
# attach the photo through the stored data
row = select('koja_cvs', {'id': cid})[0]
data = dict(row['data'], photo=PHOTO)
A.db_update('koja_cvs', {'id': cid}, {'data': data})

view = me.get('/cv/%s' % cid).get_data(as_text=True)
chk('the saved CV page shows Download PDF and Download Word', 'Download PDF' in view and 'Download Word' in view)

# PDF
r = me.get('/cv/%s/download/pdf' % cid)
pdf = r.get_data()
chk('PDF downloads as an attachment', r.status_code == 200 and r.mimetype == 'application/pdf' and 'attachment' in r.headers.get('Content-Disposition', ''), r.status_code)
chk('PDF file is a real PDF', pdf.startswith(b'%PDF'))
chk('PDF name is taken from the CV', 'Mary-Banda-CV.pdf' in r.headers.get('Content-Disposition', ''))
from pypdf import PdfReader
txt = '\n'.join(p.extract_text() or '' for p in PdfReader(io.BytesIO(pdf)).pages)
chk('PDF contains the name, contact, sections and certifications', all(x in txt for x in ['Mary Banda', 'mary@example.com', 'Clinic Lead', 'NMC Registered 2019', 'Certifications']))
chk('PDF keeps special characters as text', 'Nurse & midwife' in txt and '<strong>experienced</strong>' in txt)
chk('PDF includes the photo', len(PdfReader(io.BytesIO(pdf)).pages[0].images) >= 1)

# Word
r = me.get('/cv/%s/download/docx' % cid)
docx_bytes = r.get_data()
chk('Word file downloads as an attachment', r.status_code == 200 and 'wordprocessingml' in r.mimetype and 'Mary-Banda-CV.docx' in r.headers.get('Content-Disposition', ''), r.mimetype)
chk('Word file is a real .docx (zip package)', docx_bytes[:2] == b'PK')
from docx import Document
d = Document(io.BytesIO(docx_bytes))
text = '\n'.join(p.text for p in d.paragraphs)
chk('Word file contains the name, contact, sections and certifications', all(x in text for x in ['Mary Banda', 'mary@example.com', 'Clinic Lead', 'NMC Registered 2019', 'Certifications and licences']))
chk('Word file includes the photo', len(d.inline_shapes) == 1)

# Without a photo the files still work
A.db_update('koja_cvs', {'id': cid}, {'data': dict(row['data'], photo='')})
chk('PDF still downloads without a photo', me.get('/cv/%s/download/pdf' % cid).get_data().startswith(b'%PDF'))
chk('Word file still downloads without a photo', me.get('/cv/%s/download/docx' % cid).get_data()[:2] == b'PK')

# Every line survives, including long CVs that run onto a second page, and PDF-unsafe characters are visible
from pypdf import PdfReader as _PR
long_exp = '\n'.join('Achievement line %02d: supported district clinics' % i for i in range(1, 41))
A.db_update('koja_cvs', {'id': cid}, {'data': dict(row['data'], photo='', experience=long_exp,
            profile='\u2713 Trained staff\n\u2192 Led the team\n\u2022 Bullet point\nZambian: \u00e9 \u00f6 \u00f1 \u0142\n\U0001F4DA emoji')})
ptxt = '\n'.join(p.extract_text() or '' for p in _PR(io.BytesIO(me.get('/cv/%s/download/pdf' % cid).get_data())).pages)
chk('all 40 long-CV lines are in the PDF', all('Achievement line %02d' % i in ptxt for i in range(1, 41)))
chk('bullets, accents and Polish letters are kept in the PDF', '\u2022 Bullet point' in ptxt and '\u0142' in ptxt and '\u00e9' in ptxt)
chk('tick and arrow become readable marks in the PDF', 'Trained staff' in ptxt and 'Led the team' in ptxt)
chk('emoji is shown as ? in the PDF, not dropped', '? emoji' in ptxt)
wtext = '\n'.join(p.text for p in Document(io.BytesIO(me.get('/cv/%s/download/docx' % cid).get_data())).paragraphs)
chk('Word keeps the emoji and the tick mark', '\U0001F4DA emoji' in wtext and '\u2713 Trained staff' in wtext)

# Privacy and bad input
chk('another user cannot download the PDF', other.get('/cv/%s/download/pdf' % cid).status_code == 404)
chk('another user cannot download the Word file', other.get('/cv/%s/download/docx' % cid).status_code == 404)
chk('an unknown format is 404', me.get('/cv/%s/download/exe' % cid).status_code == 404)
chk('an invalid id is 404', me.get('/cv/not-an-id/download/pdf').status_code == 404)
chk('anonymous download is refused', A.app.test_client().get('/cv/%s/download/pdf' % cid).status_code in (302, 401, 403))

run("delete from public.koja_cvs")
print('RESULT: %d/%d passed' % (sum(res), len(res)))
