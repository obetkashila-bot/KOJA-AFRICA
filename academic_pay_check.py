"""Lessons paid at booking: checkout, return page, webhook, idempotent unlock, tampered amounts, access, Go live. Run from the project folder."""
import sys, uuid, subprocess, base64, hmac, hashlib, json
from datetime import date, timedelta
sys.path.insert(0, '/home/claude/koja_tests')
import harness
from harness import A, run, select, PSQL
H = harness
def _where(filters):
    if not filters:
        return ''
    parts = []
    for k, v in filters.items():
        if isinstance(v, str) and v.startswith('gte.'):
            parts.append(f'"{k}" >= {harness.lit(v[4:])}::timestamptz')
        elif isinstance(v, str) and v.startswith('in.(') and v.endswith(')'):
            items = [x for x in v[4:-1].split(',') if x]
            parts.append(f'"{k}" in (' + ', '.join(harness.lit(x) for x in items) + ')' if items else 'false')
        elif isinstance(v, str) and v.startswith('eq.'):
            parts.append(f'"{k}" = {harness.lit(v[3:])}')
        else:
            parts.append(f'"{k}" = {harness.lit(v)}')
    return ' where ' + ' and '.join(parts)
harness.where = _where
A.app.config['TESTING'] = True
A.csrf_valid = lambda: True
res = []
def chk(name, cond, extra=''):
    res.append(bool(cond)); print(('PASS ' if cond else 'FAIL ') + name, extra)

for f in ['/mnt/user-data/attachments/19d8f52e-d460-5865-871e-9298dbb6579d/a46a35ce-koja_academic_migration.sql',
          '/home/claude/outputs/koja_app_final/koja_academic_learner_fix.sql',
          '/home/claude/outputs/koja_app_final/koja_academic_live.sql',
          '/home/claude/outputs/koja_app_final/koja_academic_payments.sql']:
    subprocess.run(PSQL + ['-f', f], capture_output=True, text=True, check=True)
run("alter table public.koja_academic_sessions alter column learner_user_id set not null")
for t in ['koja_academic_payments', 'koja_academic_ledger', 'koja_academic_live', 'koja_academic_sessions', 'koja_academic_classes', 'koja_academic_teachers']:
    run(f"delete from public.{t}")
TUID = str(uuid.uuid4()); TID = str(uuid.uuid4()); STUDENT = str(uuid.uuid4()); OTHER = str(uuid.uuid4())
run(f"insert into public.koja_academic_teachers (id,user_id,full_name,subjects,grade_levels,hourly_rate,currency,status) values ('{TID}','{TUID}','Chanda Zulu','Chemistry','Grade 10',120,'ZMW','verified')")

# Stubs: the Flutterwave charge and the server-side verification
A.FLW_SECRET_KEY = 'test-secret'
A.FLW_SECRET_HASH = 'whsec'
CALLS = []
TAMPER = {'extra': 0}
class FakeResp:
    def __init__(self, body, ok=True, code=200): self._b, self.ok, self.status_code, self.text, self.headers = body, ok, code, json.dumps(body), {'Content-Type': 'application/json'}
    def json(self): return self._b
def fake_post(url, headers=None, json=None, timeout=None, **k):
    CALLS.append((url, json))
    return FakeResp({'status': 'success', 'meta': {'authorization': {'redirect': 'https://checkout.flutterwave.test/pay/' + json['tx_ref']}}})
A._HTTP.post = fake_post
def fake_verify(*a, **k):
    ref = k['tx_ref'] if 'tx_ref' in k else (a[1] if len(a) > 1 else None)
    p = H.first('koja_academic_payments', {'tx_ref': ref}) if ref else None
    if not p:
        return None
    return {'id': 9000 + len(CALLS), 'status': 'successful', 'tx_ref': ref, 'amount': float(p['amount']) + TAMPER['extra'],
            'currency': p['currency'], 'meta': {'koja_session_id': p['session_id']}}
A._flutterwave_verify = fake_verify

def client(uid, name='User'):
    c = A.app.test_client()
    with c.session_transaction() as s:
        s['user'] = {'id': uid, 'name': name, 'email': 'x@x.test', 'is_admin': False, 'role': 'buyer', 'full_name': name}
        s['_csrf_token'] = 'tok'
    return c
teacher = client(TUID, 'Chanda Zulu'); student = client(STUDENT, 'Student'); other = client(OTHER, 'Other')
csrf = {'_csrf_token': 'tok'}
def sess_on(day):
    rows = select('koja_academic_sessions', {'teacher_id': TID, 'scheduled_date': str(day)})
    return rows[0] if rows else None
def pays_for(sid):
    return select('koja_academic_payments', {'session_id': sid})
def ledger_for(sid):
    return select('koja_academic_ledger', {'ref_id': sid, 'kind': 'earning'})
d1, d2, d3 = [date.today() + timedelta(days=n) for n in (1, 2, 3)]
book = {'subject': 'Chemistry', 'start_time': '10:00', 'duration_minutes': '60', 'notes': ''}

# 1. Book and pay in one step
r = student.post(f'/academic/teacher/{TID}/book', data={**csrf, **book, 'scheduled_date': str(d1), 'network': 'ZM:MTN', 'phone': '0971234567'})
s1 = sess_on(d1); SID1 = s1['id']
chk('booking with pay now sends the student to checkout', r.status_code == 302 and 'checkout.flutterwave.test' in r.headers.get('Location', ''), r.headers.get('Location'))
chk('the charge uses the Zambia mobile-money type with the chosen network', CALLS and CALLS[-1][0].endswith('/charges?type=mobile_money_zambia') and CALLS[-1][1].get('network') == 'MTN')
chk('the charge is for the lesson price in kwacha', CALLS and float(CALLS[-1][1]['amount']) == 120.0, CALLS[-1][1]['amount'] if CALLS else None)
p1 = pays_for(SID1)
chk('a pending payment is recorded for the lesson', len(p1) == 1 and p1[0]['status'] == 'pending' and p1[0]['tx_ref'].startswith('KOJA-LES-'))
chk('the lesson is accepted and unpaid until payment', s1 and s1['status'] == 'accepted' and s1['payment_status'] == 'unpaid')

# 2. Return page verifies and opens the room
r = student.get(f"/academic/payment/callback?tx_ref={p1[0]['tx_ref']}&transaction_id=5001", follow_redirects=False)
s1 = sess_on(d1)
chk('return page marks the payment paid and the lesson paid', pays_for(SID1)[0]['status'] == 'paid' and s1['payment_status'] == 'paid')
chk('the live room opens for the student', student.get(f'/academic/room/session/{SID1}').status_code == 200)

# 3. Teacher completes: teacher is credited once
teacher.post(f'/academic/session/{SID1}/complete', data=csrf)
chk('completing a paid lesson credits the teacher once', len(ledger_for(SID1)) == 1, len(ledger_for(SID1)))

# 4. Repeat return and any repeat webhook do not pay twice
student.get(f"/academic/payment/callback?tx_ref={p1[0]['tx_ref']}&transaction_id=5001")
chk('a repeated return page does not credit the teacher again', len(ledger_for(SID1)) == 1, len(ledger_for(SID1)))

# 5. Pay later, then pay from My lessons; the webhook opens the room
r = student.post(f'/academic/teacher/{TID}/book', data={**csrf, **book, 'scheduled_date': str(d2)})
s2 = sess_on(d2); SID2 = s2['id']
chk('booking without pay now records the lesson and no payment', s2 and s2['payment_status'] == 'unpaid' and pays_for(SID2) == [])
r = student.post(f'/academic/session/{SID2}/pay', data={**csrf, 'network': 'ZM:AIRTEL', 'phone': '0977654321'})
p2 = pays_for(SID2)
chk('paying from My lessons starts checkout', r.status_code == 302 and 'checkout.flutterwave.test' in r.headers.get('Location', '') and len(p2) == 1)
raw = json.dumps({'event': 'charge.completed', 'data': {'id': 7777, 'tx_ref': p2[0]['tx_ref'], 'status': 'successful'}}).encode()
sig = base64.b64encode(hmac.new(b'whsec', raw, hashlib.sha256).digest()).decode()
r = A.app.test_client().post('/webhook/flutterwave', data=raw, headers={'flutterwave-signature': sig, 'Content-Type': 'application/json'})
s2 = sess_on(d2)
chk('the webhook accepts the signed event and opens the lesson', r.status_code == 200 and 'academic:finalized' in r.get_data(as_text=True), r.get_data(as_text=True)[:200])
chk('the webhook marks the lesson paid', s2['payment_status'] == 'paid' and pays_for(SID2)[0]['status'] == 'paid')
bad = A.app.test_client().post('/webhook/flutterwave', data=raw, headers={'flutterwave-signature': 'wrong', 'Content-Type': 'application/json'})
chk('a webhook with a bad signature is refused', bad.status_code == 401, bad.status_code)

# 6. Only the student can pay; a tampered amount does not unlock
r = student.post(f'/academic/teacher/{TID}/book', data={**csrf, **book, 'scheduled_date': str(d3), 'network': 'ZM:MTN', 'phone': '0971111111'})
s3 = sess_on(d3); SID3 = s3['id']; p3 = pays_for(SID3)
r = other.post(f'/academic/session/{SID3}/pay', data={**csrf, 'network': 'ZM:MTN', 'phone': '0971111111'})
chk('another user cannot pay for the lesson', r.status_code == 404, r.status_code)
TAMPER['extra'] = 5
student.get(f"/academic/payment/callback?tx_ref={p3[0]['tx_ref']}&transaction_id=6001")
TAMPER['extra'] = 0
s3 = sess_on(d3)
chk('a payment with the wrong amount does not unlock the lesson', s3['payment_status'] == 'unpaid' and pays_for(SID3)[0]['status'] == 'pending')
chk('a tampered payment is not marked paid, room stays closed', student.get(f'/academic/room/session/{SID3}', follow_redirects=False).status_code == 302)
body = student.get('/academic/my-lessons').get_data(as_text=True)
chk('My lessons still offers payment for the unpaid lesson', 'Pay with mobile money' in body)

# 7. Paying an already-paid lesson creates nothing new
before = len(select('koja_academic_payments', {'session_id': SID1}))
r = student.post(f'/academic/session/{SID1}/pay', data={**csrf, 'network': 'ZM:MTN', 'phone': '0971234567'})
chk('paying a paid lesson again creates no payment', len(select('koja_academic_payments', {'session_id': SID1})) == before and r.status_code == 302)

# 8. Teacher Go live and the profile's pay-now option
body = teacher.get('/academic/teacher/dashboard').get_data(as_text=True)
chk('the teacher home page shows Go live for the next paid lesson', 'Go live' in body and f'/academic/room/session/{SID2}' in body)
body = student.get(f'/academic/teacher/{TID}').get_data(as_text=True)
chk('the booking form offers pay now or pay later', 'Pay later from My lessons' in body and 'Book lesson' in body)

run("delete from public.koja_academic_payments"); run("delete from public.koja_academic_ledger"); run("delete from public.koja_academic_live")
run("delete from public.koja_academic_sessions"); run("delete from public.koja_academic_classes"); run("delete from public.koja_academic_teachers")
run("alter table public.koja_academic_sessions alter column learner_user_id drop not null")
print('RESULT: %d/%d passed' % (sum(res), len(res)))
