"""KOJA can be installed to a phone's home screen: the web app manifest is served and linked from every page."""
import sys, json
sys.path.insert(0, '/home/claude/koja_tests')
from harness import A
A.app.config['TESTING'] = True
res = []
def chk(name, cond, extra=''):
    res.append(bool(cond)); print(('PASS ' if cond else 'FAIL ') + name, extra)
c = A.app.test_client()
r = c.get('/manifest.webmanifest')
chk('manifest is served', r.status_code == 200, r.status_code)
chk('manifest has the manifest mime type', r.mimetype == 'application/manifest+json', r.mimetype)
m = json.loads(r.get_data(as_text=True))
chk('manifest opens full screen (standalone) from the home page', m.get('display') == 'standalone' and m.get('start_url') == '/' and m.get('scope') == '/')
chk('manifest has a name and short name', m.get('name') == 'KOJA AFRICA' and m.get('short_name') == 'KOJA')
chk('manifest has a PNG icon of at least 192px for install', any(i.get('type') == 'image/png' and i.get('sizes') == '192x192' for i in m.get('icons', [])))
chk('every page links the manifest', 'rel="manifest" href="/manifest.webmanifest"' in c.get('/').get_data(as_text=True))
print('RESULT: %d/%d passed' % (sum(res), len(res)))
