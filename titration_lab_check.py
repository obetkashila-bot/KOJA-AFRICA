"""Virtual titration lab: chemistry, endpoints, validation and page access. Run from the project folder."""
import sys, math
sys.path.insert(0, '/home/claude/koja_tests')
from harness import A
A.app.config['TESTING'] = True
res = []
def chk(name, cond, extra=''):
    res.append(bool(cond)); print(('PASS ' if cond else 'FAIL ') + name, extra)
def near(a, b, tol): return abs(a - b) <= tol

# 1. Strong acid with strong base (0.1 M, 25 mL, 0.1 M NaOH)
chk('strong acid starts at pH 1.00', near(A._titration_ph(0.1, 25, 0.1, 0, None), 1.00, 0.01))
chk('strong acid at 12.5 mL is pH 1.48', near(A._titration_ph(0.1, 25, 0.1, 12.5, None), 1.48, 0.01))
chk('strong acid at equivalence is pH 7.00', A._titration_ph(0.1, 25, 0.1, 25, None) == 7.0)
chk('strong acid at 50 mL is pH 12.52', near(A._titration_ph(0.1, 25, 0.1, 50, None), 12.52, 0.01))

# 2. Weak acid (acetic acid, Ka 1.8e-5)
ka = 1.8e-5
chk('acetic acid starts at pH 2.87', near(A._titration_ph(0.1, 25, 0.1, 0, ka), 2.87, 0.02))
chk('half-equivalence gives pH = pKa (4.74)', near(A._titration_ph(0.1, 25, 0.1, 12.5, ka), 4.74, 0.02))
chk('acetate at equivalence is basic (pH 8.72)', near(A._titration_ph(0.1, 25, 0.1, 25, ka), 8.72, 0.03))

# 3. Curve and endpoints
c = A._titration_curve(0.1, 25, 0.1, 'hcl', 'phenolphthalein')
chk('equivalence volume is 25.0 mL', near(c['equivalence_ml'], 25.0, 0.001))
chk('curve runs to twice the equivalence volume', near(c['end_ml'], 50.0, 0.001) and len(c['points']) == 1001)
chk('phenolphthalein changes within 0.1 mL of equivalence', c['indicator']['change_ml'] is not None and abs(c['indicator']['error_ml']) <= 0.1, c['indicator'])
cm = A._titration_curve(0.1, 25, 0.1, 'hcl', 'methyl_orange')
chk('methyl orange changes early, near 24.9 mL', 24.8 <= cm['indicator']['change_ml'] <= 25.0, cm['indicator']['change_ml'])
chk('the pH curve is never decreasing for strong base', all(c['points'][i][1] <= c['points'][i + 1][1] + 1e-9 for i in range(len(c['points']) - 1)))

# 4. Route: validation and success
A_HASH = None
def client(uid):
    cl = A.app.test_client()
    with cl.session_transaction() as s:
        s['user'] = {'id': uid, 'name': 'S', 'email': 'x@x.test', 'is_admin': False, 'role': 'buyer', 'full_name': 'S'}
        s['_csrf_token'] = 'tok'
    return cl
st = client('11111111-1111-1111-1111-111111111111')
base = {'analyte': 'hcl', 'indicator': 'phenolphthalein', 'ca': '0.1', 'va': '25', 'cb': '0.1'}
def q(**kw):
    d = dict(base); d.update(kw); return st.get('/academic/lab/titration/curve', query_string=d)
r = q(ca='0')
chk('zero concentration is refused', r.status_code == 400, r.status_code)
r = q(va='500')
chk('analyte volume above 100 mL is refused', r.status_code == 400)
r = q(cb='nan')
chk('a non-number is refused', r.status_code == 400)
r = q(analyte='bogus')
chk('an unknown analyte is refused', r.status_code == 400)
r = q(indicator='bogus')
chk('an unknown indicator is refused', r.status_code == 400)
r = q()
body = r.get_json() or {}
chk('a valid setup returns the curve', r.status_code == 200 and body.get('ok') is True and near(body.get('equivalence_ml', 0), 25.0, 0.001), r.status_code)
chk('the response lists the assumptions', len(body.get('assumptions', [])) >= 3)

# 5. Page access and link
r = st.get('/academic/lab/titration')
chk('the lab page opens for a logged-in user', r.status_code == 200 and 'Virtual lab: acid-base titration' in r.get_data(as_text=True))
anon = A.app.test_client()
chk('the lab page needs login', anon.get('/academic/lab/titration').status_code == 302)
chk('the curve needs login', anon.get('/academic/lab/titration/curve').status_code == 302)

print('RESULT: %d/%d passed' % (sum(res), len(res)))
