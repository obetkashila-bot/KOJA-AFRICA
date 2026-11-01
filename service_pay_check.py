"""Help desk payments and staff alerts: quote payment, callback, webhook, alerts. Run from the project folder."""
import sys, uuid, io, json, hmac, hashlib, base64
sys.path.insert(0, '/home/claude/koja_tests')
from harness import A, run, select
A.app.config['TESTING'] = True
A.csrf_valid = lambda: True
res = []
def chk(name, cond, extra=''):
    res.append(bool(cond)); print(('PASS ' if cond else 'FAIL ') + name, extra)

notes = []; mails = []; sms = []
A.notify_user = lambda uid, title, body, *a, **k: notes.append((str(uid), title))
A._bg = lambda fn, *a, **k: fn(*a, **k)
A.send_plain_email = lambda to, subject, body: mails.append((to, subject, body))
A.send_sms_message = lambda phone, msg: sms.append((phone, msg))
A.HELP_DESK_ALERT_EMAILS = ['staff@example.test']
A.HELP_DESK_ALERT_PHONE = '+260971000000'
A.upload_storage = lambda f, folder=None, public=False, max_mb=None, allowed=None: ({'path': 'help-desk/p.pdf', 'url': None, 'file_name': 'p.pdf', 'file_size': 1, 'mime_type': 'application/pdf'}, None)
A.delete_storage = lambda p: None
A.FLW_SECRET_KEY = ''
A.FLW_SECRET_HASH = 'whsec-test'

VERIFY = {'tx': None}
def fake_verify(transaction_id=None, tx_ref=None):
    return VERIFY['tx']
A._flutterwave_verify = fake_verify

CHARGES = []
class FakeResp:
    def __init__(self, ok, body): self.ok = ok; self.status_code = 200 if ok else 500; self._b = body; self.text = json.dumps(body)
    def json(self): return self._b
def fake_post(url, headers=None, json=None, timeout=None, **kw):
    CHARGES.append(json)
    return FakeResp(True, {'status': 'success', 'meta': {'authorization': {'redirect': 'https://checkout.example.test/pay/abc'}}})
A._HTTP.post = fake_post

ALICE = uuid.uuid4().hex; BOB = uuid.uuid4().hex; ADMIN = uuid.uuid4().hex
def client(uid=None, admin=False, email='alice@example.test'):
    cl = A.app.test_client()
    with cl.session_transaction() as s:
        if uid:
            s['user'] = {'id': uid, 'name': 'Alice Banda', 'email': email, 'is_admin': admin, 'role': 'buyer', 'full_name': 'Alice Banda'}
        s['_csrf_token'] = 'tok'
    return cl
alice = client(ALICE); bob = client(BOB, email='bob@example.test'); admin = client(ADMIN, admin=True)
base = {'full_name': 'Alice Banda', 'phone': '+260 97 111 2222', 'consent': 'yes', 'details': 'Help me apply for the bursary for 2027, please.'}

# ---- staff alerts on a new request ----
mails.clear(); sms.clear()
alice.post('/help-desk/request/bursary_application', data=base)
chk('staff get an email about a new request', any(m[0] == 'staff@example.test' and 'new request' in m[1].lower() for m in mails), mails[-1:])
chk('the staff email does not carry the person\'s details', all('bursary for 2027' not in m[2] and '+260 97 111' not in m[2] for m in mails))
chk('staff get an SMS too when a phone is set', any(p == '+260971000000' and 'Bursary' in m for p, m in sms), sms[-1:])
rows = select('koja_service_requests', {'user_id': ALICE}, order='created_at.desc')
RID = rows[0]['id']

# ---- no quote yet: no payment ----
alice.post('/help-desk/requests/%s/pay' % RID, data={'network': 'MTN', 'phone': '+260 97 111 2222'})
chk('no payment without a quote', select('koja_service_requests', {'id': RID})[0].get('payment_status') in (None, ''))
admin.post('/admin/help-desk/%s/update' % RID, data={'status': 'in_progress', 'quote_amount': '80', 'currency': 'ZMW'})
pg = alice.get('/help-desk/requests/%s' % RID).get_data(as_text=True)
chk('the page shows the quote', '80 ZMW' in pg)
chk('online payment not set up is shown plainly', 'Online payment is not set up yet' in pg)

# ---- payment set up ----
A.FLW_SECRET_KEY = 'flw-test-key'
pg = alice.get('/help-desk/requests/%s' % RID).get_data(as_text=True)
chk('the pay form shows once payment is set up', '/help-desk/requests/%s/pay' % RID in pg and 'Pay 80 ZMW' in pg)
alice.post('/help-desk/requests/%s/pay' % RID, data={'network': 'NOPE', 'phone': '+260 97 111 2222'})
chk('an unknown network is refused', len(CHARGES) == 0)
alice.post('/help-desk/requests/%s/pay' % RID, data={'network': 'MTN', 'phone': 'abc'})
chk('a bad phone number is refused', len(CHARGES) == 0)
r = alice.post('/help-desk/requests/%s/pay' % RID, data={'network': 'MTN', 'phone': '+260 97 111 2222'})
row = select('koja_service_requests', {'id': RID})[0]
chk('the payment starts and goes to the checkout', r.status_code == 302 and r.headers.get('Location') == 'https://checkout.example.test/pay/abc', r.headers.get('Location'))
chk('the charge is 80 ZMW for the mobile-money network', CHARGES and CHARGES[-1]['amount'] == 80 and CHARGES[-1]['currency'] == 'ZMW' and CHARGES[-1]['network'] == 'MTN')
chk('the payment is marked pending with a KOJA reference', row.get('payment_status') == 'pending' and str(row.get('payment_reference')).startswith('KOJA-HLP-'))
TX_REF = row['payment_reference']

# ---- callback: wrong person, bad reference ----
chk('another person cannot confirm this payment', bob.get('/help-desk/payment/callback?tx_ref=%s' % TX_REF).status_code == 404)
chk('an unknown reference is not found', alice.get('/help-desk/payment/callback?tx_ref=KOJA-HLP-nothing').status_code == 404)

# ---- callback: not yet confirmed ----
VERIFY['tx'] = {'id': 901, 'tx_ref': TX_REF, 'status': 'pending', 'amount': 80, 'currency': 'ZMW'}
alice.get('/help-desk/payment/callback?tx_ref=%s&transaction_id=901' % TX_REF)
chk('an unconfirmed payment is not marked paid', select('koja_service_requests', {'id': RID})[0].get('payment_status') == 'pending')

# ---- callback: short payment ----
VERIFY['tx'] = {'id': 902, 'tx_ref': TX_REF, 'status': 'successful', 'amount': 50, 'currency': 'ZMW'}
alice.get('/help-desk/payment/callback?tx_ref=%s&transaction_id=902' % TX_REF)
chk('a payment for less than the quote is not accepted', select('koja_service_requests', {'id': RID})[0].get('payment_status') == 'pending')

# ---- callback: correct payment ----
notes.clear(); mails.clear()
VERIFY['tx'] = {'id': 903, 'tx_ref': TX_REF, 'status': 'successful', 'amount': 80, 'currency': 'ZMW'}
alice.get('/help-desk/payment/callback?tx_ref=%s&transaction_id=903' % TX_REF)
row = select('koja_service_requests', {'id': RID})[0]
chk('a verified payment marks the quote paid', row.get('payment_status') == 'paid' and row.get('payment_transaction_id') == '903' and row.get('paid_at'), row.get('payment_status'))
chk('the person is told the payment was received', (ALICE, 'Payment received') in notes)
chk('staff are told a payment was received', any('payment received' in m[1].lower() for m in mails))
pg = alice.get('/help-desk/requests/%s' % RID).get_data(as_text=True)
chk('the page says it is paid and hides the pay form', 'Paid on' in pg and '/help-desk/requests/%s/pay' % RID not in pg)
n_before = len(CHARGES)
alice.post('/help-desk/requests/%s/pay' % RID, data={'network': 'MTN', 'phone': '+260 97 111 2222'})
chk('paying again is refused', len(CHARGES) == n_before)

# ---- webhook: verified payment ----
alice.post('/help-desk/request/bursary_application', data=dict(base, details='Second request for the bursary form.'))
RID2 = select('koja_service_requests', {'user_id': ALICE}, order='created_at.desc')[0]['id']
admin.post('/admin/help-desk/%s/update' % RID2, data={'status': 'in_progress', 'quote_amount': '120', 'currency': 'ZMW'})
alice.post('/help-desk/requests/%s/pay' % RID2, data={'network': 'AIRTEL', 'phone': '+260 97 111 2222'})
ref2 = select('koja_service_requests', {'id': RID2})[0]['payment_reference']
body = json.dumps({'data': {'tx_ref': ref2, 'id': 904}}).encode()
sig = base64.b64encode(hmac.new(b'whsec-test', body, hashlib.sha256).digest()).decode()
VERIFY['tx'] = {'id': 904, 'tx_ref': ref2, 'status': 'successful', 'amount': 120, 'currency': 'ZMW'}
wr = A.app.test_client().post('/webhook/flutterwave', data=body, headers={'flutterwave-signature': sig, 'Content-Type': 'application/json'})
chk('a webhook with a bad signature is refused', A.app.test_client().post('/webhook/flutterwave', data=body, headers={'flutterwave-signature': 'bad', 'Content-Type': 'application/json'}).status_code == 401)
chk('a verified webhook marks the quote paid', wr.status_code == 200 and select('koja_service_requests', {'id': RID2})[0].get('payment_status') == 'paid', wr.status_code)

# ---- webhook: wrong amount is not accepted ----
alice.post('/help-desk/request/bursary_application', data=dict(base, details='Third request for the bursary form.'))
RID3 = select('koja_service_requests', {'user_id': ALICE}, order='created_at.desc')[0]['id']
admin.post('/admin/help-desk/%s/update' % RID3, data={'status': 'in_progress', 'quote_amount': '200', 'currency': 'ZMW'})
alice.post('/help-desk/requests/%s/pay' % RID3, data={'network': 'MTN', 'phone': '+260 97 111 2222'})
ref3 = select('koja_service_requests', {'id': RID3})[0]['payment_reference']
body3 = json.dumps({'data': {'tx_ref': ref3, 'id': 905}}).encode()
sig3 = base64.b64encode(hmac.new(b'whsec-test', body3, hashlib.sha256).digest()).decode()
VERIFY['tx'] = {'id': 905, 'tx_ref': ref3, 'status': 'successful', 'amount': 10, 'currency': 'ZMW'}
A.app.test_client().post('/webhook/flutterwave', data=body3, headers={'flutterwave-signature': sig3, 'Content-Type': 'application/json'})
chk('a webhook for the wrong amount does not mark it paid', select('koja_service_requests', {'id': RID3})[0].get('payment_status') == 'pending')

# ---- staff see the payment state ----
chk('the staff page shows the payment state', 'payment: <strong>paid</strong>' in admin.get('/admin/help-desk/%s' % RID).get_data(as_text=True))

# ---- cancelled requests take no payment ----
alice.post('/help-desk/request/bursary_application', data=dict(base, details='Fourth request to be cancelled.'))
RID4 = select('koja_service_requests', {'user_id': ALICE}, order='created_at.desc')[0]['id']
admin.post('/admin/help-desk/%s/update' % RID4, data={'status': 'in_progress', 'quote_amount': '60', 'currency': 'ZMW'})
alice.post('/help-desk/requests/%s/cancel' % RID4)
n_before = len(CHARGES)
alice.post('/help-desk/requests/%s/pay' % RID4, data={'network': 'MTN', 'phone': '+260 97 111 2222'})
chk('a cancelled request cannot start a payment', len(CHARGES) == n_before)

print(f'\n{sum(res)}/{len(res)} passed')
sys.exit(0 if all(res) else 1)
