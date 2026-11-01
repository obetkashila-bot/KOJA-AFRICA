"""Virtual circuit lab: Ohm's law in series and parallel, validation and access. Run from the project folder."""
import sys, re
sys.path.insert(0, '/home/claude/koja_tests')
from harness import A
A.app.config['TESTING'] = True
res = []
def chk(name, cond, extra=''):
    res.append(bool(cond)); print(('PASS ' if cond else 'FAIL ') + name, extra)
def near(a, b, tol=1e-6): return abs(a - b) <= tol

# 1. Series: 12 V across 100 and 200 ohms
s = A._circuit_solve(12, [100, 200], 'series')
chk('series total resistance is 300 ohms', near(s['total_ohms'], 300))
chk('series current is 0.04 A', near(s['total_amps'], 0.04))
chk('series voltages split 4 V and 8 V', near(s['resistors'][0]['volts'], 4) and near(s['resistors'][1]['volts'], 8))
chk('series total power is 0.48 W', near(s['total_watts'], 0.48))

# 2. Parallel: 12 V across 100 and 200 ohms
p = A._circuit_solve(12, [100, 200], 'parallel')
chk('parallel total resistance is 66.67 ohms', near(p['total_ohms'], 200 / 3, 1e-6))
chk('parallel branch currents are 0.12 A and 0.06 A', near(p['resistors'][0]['amps'], 0.12) and near(p['resistors'][1]['amps'], 0.06))
chk('parallel total current is 0.18 A', near(p['total_amps'], 0.18))
chk('parallel total power is 2.16 W', near(p['total_watts'], 2.16))

# 3. Energy check: the parts add up to the total in both modes
chk('series power of parts equals total', near(s['power_check_watts'], s['total_watts'], 1e-9))
chk('parallel power of parts equals total', near(p['power_check_watts'], p['total_watts'], 1e-9))

# 4. Route: validation and success
def client(uid):
    cl = A.app.test_client()
    with cl.session_transaction() as st:
        st['user'] = {'id': uid, 'name': 'S', 'email': 'x@x.test', 'is_admin': False, 'role': 'buyer', 'full_name': 'S'}
        st['_csrf_token'] = 'tok'
    return cl
st = client('11111111-1111-1111-1111-111111111111')
def calc(**kw):
    d = {'mode': 'series', 'volts': '12', 'resistors': '100, 200'}
    d.update(kw)
    return st.get('/academic/lab/circuit/calc', query_string=d)
chk('an unknown mode is refused', calc(mode='loop').status_code == 400)
chk('no resistors is refused', calc(resistors='').status_code == 400)
chk('seven resistors is refused', calc(resistors='1,2,3,4,5,6,7').status_code == 400)
chk('a negative resistance is refused', calc(resistors='100,-5').status_code == 400)
chk('a resistor above 1 megaohm is refused', calc(resistors='2000000').status_code == 400)
chk('a non-number is refused', calc(volts='nan').status_code == 400 and calc(resistors='abc').status_code == 400)
chk('voltage above 240 V is refused', calc(volts='300').status_code == 400)
r = calc(mode='parallel')
body = r.get_json() or {}
chk('a valid parallel calculation returns totals', r.status_code == 200 and body.get('ok') is True and near(body.get('total_amps', 0), 0.18, 1e-5), r.status_code)
chk('the response lists the assumptions', len(body.get('assumptions', [])) == 3)
chk('semicolons also separate resistors', calc(resistors='100;200').status_code == 200)

# 5. Page access and links
r = st.get('/academic/lab/circuit')
chk('the circuit lab page opens for a logged-in user', r.status_code == 200 and 'series and parallel circuits' in r.get_data(as_text=True))
anon = A.app.test_client()
chk('the circuit lab page needs login', anon.get('/academic/lab/circuit').status_code == 302)
chk('the circuit calculation needs login', anon.get('/academic/lab/circuit/calc').status_code == 302)

print('RESULT: %d/%d passed' % (sum(res), len(res)))
