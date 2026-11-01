"""Help desk: overdue requests, assigned to me, CSV export. Run from the project folder."""
import sys, uuid, csv, io
sys.path.insert(0, '/home/claude/koja_tests')
from harness import A, run, select
A.app.config['TESTING'] = True
A.csrf_valid = lambda: True
res = []
def chk(name, cond, extra=''):
    res.append(bool(cond)); print(('PASS ' if cond else 'FAIL ') + name, extra)
A.notify_user = lambda *a, **k: None
A._bg = lambda fn, *a, **k: fn(*a, **k)
A.send_plain_email = lambda *a, **k: None
A.upload_storage = lambda f, folder=None, public=False, max_mb=None, allowed=None: (None, 'no')

# The test database is shared: start from an empty help desk so counts are exact.
run('delete from public.koja_service_messages')
run('delete from public.koja_service_requests')
ALICE = uuid.uuid4().hex; ADMIN = uuid.uuid4().hex
def client(uid=None, admin=False, name='Alice Banda'):
    cl = A.app.test_client()
    with cl.session_transaction() as s:
        if uid:
            s['user'] = {'id': uid, 'name': name, 'email': 'x@example.test', 'is_admin': admin, 'role': 'buyer', 'full_name': name}
        s['_csrf_token'] = 'tok'
    return cl
alice = client(ALICE); admin = client(ADMIN, admin=True, name='KOJA Admin'); anon = client()
base = {'full_name': 'Alice Banda', 'phone': '+260 97 111 2222', 'consent': 'yes', 'details': 'Please help with my CV for a job application.'}

def new_request(details, name='Alice Banda'):
    alice.post('/help-desk/request/job_application', data=dict(base, details=details, full_name=name))
    return select('koja_service_requests', {'user_id': ALICE}, order='created_at.desc')[0]['id']
def age(rid, hours, status=None):
    sets = "updated_at = now() - interval '%d hours'" % hours
    if status: sets += ", status = '%s'" % status
    run("update public.koja_service_requests set %s where id = '%s'" % (sets, rid))

OLD = new_request('An old request that nobody has answered yet.')
age(OLD, 72)
FRESH = new_request('A fresh request from today, not yet answered.')
WAIT = new_request('Waiting for the person to reply to us.')
age(WAIT, 96, status='waiting_user')
DONE = new_request('A finished request from long ago.')
age(DONE, 200, status='done')
MINE = new_request('Assigned to Mary for this week, in progress.')
admin.post('/admin/help-desk/%s/update' % MINE, data={'status': 'in_progress', 'assigned_to': 'KOJA Admin', 'currency': 'ZMW'})
age(MINE, 5)
OTHER = new_request('Assigned to someone else, in progress.')
admin.post('/admin/help-desk/%s/update' % OTHER, data={'status': 'in_progress', 'assigned_to': 'Mary Phiri', 'currency': 'ZMW'})
age(OTHER, 1)

# ---- overdue ----
ov = admin.get('/admin/help-desk?status=overdue').get_data(as_text=True)
chk('the overdue view lists the old unanswered request', ('/admin/help-desk/%s' % OLD) in ov)
chk('the overdue view leaves out a fresh request', ('/admin/help-desk/%s' % FRESH) not in ov)
chk('the overdue view leaves out a request waiting for the person', ('/admin/help-desk/%s' % WAIT) not in ov)
chk('the overdue view leaves out a finished request', ('/admin/help-desk/%s' % DONE) not in ov)
q = admin.get('/admin/help-desk').get_data(as_text=True)
chk('the queue shows the overdue count and an overdue flag', 'Overdue (1)' in q and 'overdue: no activity for 48+ hours' in q)

# ---- assigned to me ----
mine = admin.get('/admin/help-desk?status=mine').get_data(as_text=True)
chk('assigned to me lists my open request', ('/admin/help-desk/%s' % MINE) in mine)
chk('assigned to me leaves out another person\'s request', ('/admin/help-desk/%s' % OTHER) not in mine)
chk('assigned to me leaves out requests not mine', ('/admin/help-desk/%s' % OLD) not in mine)

# ---- CSV export ----
chk('the export needs staff', alice.get('/admin/help-desk/export.csv').status_code == 302)
chk('the export needs sign-in', anon.get('/admin/help-desk/export.csv').status_code == 302)
r = admin.get('/admin/help-desk/export.csv')
chk('the export is a CSV download, not cached', r.status_code == 200 and r.mimetype == 'text/csv' and 'attachment' in r.headers.get('Content-Disposition', '') and 'no-store' in r.headers.get('Cache-Control', ''))
rows = list(csv.reader(io.StringIO(r.get_data(as_text=True))))
chk('the export has a header row', rows[0][:4] == ['id', 'service_name', 'category', 'status'], rows[0][:4])
chk('the export has every request', len(rows) - 1 == len(select('koja_service_requests')), (len(rows) - 1))
chk('the export leaves out the request details', 'details' not in rows[0] and not any('CV for a job' in ' '.join(x) for x in rows))
chk('the export includes the assignee', any('KOJA Admin' in x for x in rows))
chk('the export keeps the payment columns', 'payment_status' in rows[0] and 'paid_at' in rows[0])

# formula cells are made safe
bad = new_request('Ask about my CV, it is short.', name='=HYPERLINK("http://x.example","click")')
rows = list(csv.reader(io.StringIO(admin.get('/admin/help-desk/export.csv').get_data(as_text=True))))
mine_row = [x for x in rows if x[0] == bad][0]
chk('a name that starts with = is not run as a formula', mine_row[rows[0].index('full_name')].startswith("'="), mine_row[rows[0].index('full_name')])

print(f'\n{sum(res)}/{len(res)} passed')
sys.exit(0 if all(res) else 1)
