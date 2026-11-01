"""Upgrades: lab voice control, enrolment counts, favicon, polling, library photo override. Run from the project folder."""
import sys, os
sys.path.insert(0, '/home/claude/koja_tests')
from harness import A
A.app.config['TESTING'] = True
res = []
def chk(name, cond, extra=''):
    res.append(bool(cond)); print(('PASS ' if cond else 'FAIL ') + name, extra)
import uuid
UID = str(uuid.uuid4())
cl = A.app.test_client()
with cl.session_transaction() as s:
    s['user'] = {'id': UID, 'name': 'U', 'email': 'x@x.test', 'is_admin': False, 'role': 'buyer', 'full_name': 'U'}
    s['_csrf_token'] = 'tok'
src = open('app.py', encoding='utf-8').read()
chk('enrolment counts read up to 10000 rows', '{"class_id": cid}, limit=500)' not in src and src.count('{"class_id": cid}, limit=10000)') >= 3)
chk('favicon file exists and is served', os.path.isfile('static/favicon.svg') and os.path.isfile('static/favicon-192.png'))
chk('/favicon.ico redirects to the icon', cl.get('/favicon.ico').status_code == 302 and 'favicon.svg' in cl.get('/favicon.ico').headers.get('Location', ''))
chk('the static icon is served', cl.get('/static/favicon.svg').status_code == 200)
chk('board and demonstration poll every 5 seconds only while visible', 'if(!document.hidden)load();},5000)' in src and 'if(!document.hidden)loadState();},5000)' in src)
pg = cl.get('/academic/lab/spectrophotometer').get_data(as_text=True)
chk('the spectrophotometer lab has the voice and typed control', 'id="vMic"' in pg and 'id="vForm"' in pg and 'Say or type a value' in pg)
chk('the kinetics lab has the same control', 'id="vMic"' in cl.get('/academic/lab/kinetics').get_data(as_text=True))
chk('the enzyme lab has the same control', 'id="vMic"' in cl.get('/academic/lab/enzyme').get_data(as_text=True))
chk('the RC lab has the same control', 'id="vMic"' in cl.get('/academic/lab/rc-circuit').get_data(as_text=True))
with A.app.test_request_context():
    chk('no photo yet: the library shows the drawing', A._lib_photo('ammeter') is None)
os.makedirs('static/library', exist_ok=True)
open('static/library/ammeter.png', 'wb').write(b'\x89PNG')
try:
    with A.app.test_request_context():
        chk('a photo placed in static/library is used', A._lib_photo('ammeter') == '/static/library/ammeter.png', A._lib_photo('ammeter'))
    chk('the library page shows the photo', '/static/library/ammeter.png' in cl.get('/academic/library').get_data(as_text=True))
finally:
    os.remove('static/library/ammeter.png')
print(f'\n{sum(res)}/{len(res)} passed')
sys.exit(0 if all(res) else 1)
