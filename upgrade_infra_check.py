"""Shared rate limits, teacher list cache, index migration. Run from the project folder."""
import sys, uuid, time
sys.path.insert(0, '/home/claude/koja_tests')
from harness import A
A.app.config['TESTING'] = True
res = []
def chk(name, cond, extra=''):
    res.append(bool(cond)); print(('PASS ' if cond else 'FAIL ') + name, extra)

key = 'login:' + str(uuid.uuid4())
hits = [A._rate_limited(key, 3, 60) for _ in range(4)]
chk('the 4th sign-in attempt in the window is limited', hits == [False, False, False, True], hits)
A._rate_hits.clear()   # simulate a second server instance with an empty memory
chk('the limit still holds on another instance (shared record)', A._rate_limited(key, 3, 60) is True)
chk('limits on other keys are not affected', A._rate_limited('login:' + str(uuid.uuid4()), 3, 60) is False)
chk('non-login keys are never limited', all(A._rate_limited('other:x', 1, 60) is False for _ in range(3)))
A._TTL_CACHE.clear()
calls = []
def fn():
    calls.append(1)
    return [{'name': 'Cache Teacher', 'rating_avg': 4}]
a = A._ttl_cache('t', 60, fn)
a[0]['name'] = 'changed by caller'
b = A._ttl_cache('t', 60, fn)
chk('the cache returns the same data and calls the query once', len(calls) == 1 and b[0]['name'] == 'Cache Teacher')
chk('a caller changing its copy does not change the cache', b[0]['name'] == 'Cache Teacher')
A._TTL_CACHE['t'] = (time.time() - 120, [{'name': 'old'}])
chk('the cache refreshes after its time limit', A._ttl_cache('t', 60, fn)[0]['name'] == 'Cache Teacher' and len(calls) == 2)
print(f'\n{sum(res)}/{len(res)} passed')
sys.exit(0 if all(res) else 1)
