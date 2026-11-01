"""Admin adds a resource source: only built-in connectors, checked automatically, added paused, admin only.
Network calls are replaced by fakes. Run from a directory that holds app.py (copy app.py there first)."""
import sys, uuid
sys.path.insert(0, '/home/claude/koja_tests')
from harness import A, run, select
A.app.config['TESTING'] = True
res = []
def chk(name, cond, extra=''):
    res.append(bool(cond)); print(('PASS ' if cond else 'FAIL ') + name, extra)
run("delete from public.koja_discovered_resources")
run("delete from public.koja_resource_sources where id in ('openalex','gutendex')")
run("delete from public.koja_resource_audit_logs")
def client(uid, name, admin=False):
    c = A.app.test_client()
    with c.session_transaction() as s:
        s['user'] = {'id': uid, 'name': name, 'email': 'x@x.test', 'is_admin': admin}; s['_csrf_token'] = 'tok'
    return c
admin = client(str(uuid.uuid4()), 'Admin', admin=True)
user = client(str(uuid.uuid4()), 'Member')
anon = A.app.test_client()
FAKE_WORK = {'results': [{'id': 'https://openalex.org/W1', 'display_name': 'Climate adaptation in towns', 'authorships': [],
                          'publication_date': '2024-01-01', 'primary_topic': {'display_name': 'Climate'},
                          'primary_location': {'landing_page_url': 'https://example.org/paper-1', 'license': 'cc-by'}},
                         {'id': 'https://openalex.org/W2', 'display_name': 'Closed paper', 'authorships': [],
                          'primary_location': {'landing_page_url': 'https://example.org/paper-2', 'license': None}}]}
STATE = {'fail': False}
def fake_get(url, params=None, timeout=20, headers=None):
    if STATE['fail']:
        raise RuntimeError('unreachable')
    return FAKE_WORK
A._res_get_json = fake_get

chk('a member cannot add a source', user.post('/admin/resources/sources/add', data={'_csrf_token': 'tok', 'connector': 'openalex'}).status_code in (302, 401, 403)
    and not select('koja_resource_sources', {'id': 'openalex'}))
chk('anonymous visitors cannot add a source', anon.post('/admin/resources/sources/add', data={'connector': 'openalex'}).status_code in (302, 401, 403))
admin.post('/admin/resources/sources/add', data={'_csrf_token': 'tok', 'connector': 'https://evil.example/feed.xml'})
chk('a web address is refused as a source', not select('koja_resource_sources', {'id': 'https://evil.example/feed.xml'}))
r = admin.post('/admin/resources/sources/add', data={'_csrf_token': 'tok', 'connector': 'openalex'}, follow_redirects=True).get_data(as_text=True)
rows = select('koja_resource_sources', {'id': 'openalex'})
chk('a built-in connector is added', len(rows) == 1)
chk('it is added paused', rows and str(rows[0].get('enabled')).lower() in ('false', 'f', '0'))
chk('the automatic check is recorded in its note', rows and 'Checked automatically' in (rows[0].get('licence_note') or '') and '1 with an open licence' in rows[0]['licence_note'])
chk('the page says it was added and paused', 'added and paused' in r)
page_now = admin.get('/admin/resources').get_data(as_text=True)
chk('the added source is no longer offered to add, the other one still is', 'value="openalex"' not in page_now and 'value="gutendex"' in page_now)
chk('the add is audited', select('koja_resource_audit_logs', {'action': 'source_added'}) != [])
admin.post('/admin/resources/sources/add', data={'_csrf_token': 'tok', 'connector': 'openalex'})
chk('a source already listed is not added twice', len(select('koja_resource_sources', {'id': 'openalex'})) == 1)
STATE['fail'] = True
run("delete from public.koja_resource_sources where id = 'gutendex'")
admin.post('/admin/resources/sources/add', data={'_csrf_token': 'tok', 'connector': 'gutendex'})
chk('a source that cannot be reached is not added', not select('koja_resource_sources', {'id': 'gutendex'}))
STATE['fail'] = False
run("delete from public.koja_discovered_resources"); run("delete from public.koja_resource_sources where id in ('openalex','gutendex')"); run("delete from public.koja_resource_audit_logs")
print('RESULT: %d/%d passed' % (sum(res), len(res)))
