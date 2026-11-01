"""Maths and physics board: typed and spoken explanations, solving, graphs, shapes, arrows, teacher-only control. Run from the project folder."""
import sys, uuid
sys.path.insert(0, '/home/claude/koja_tests')
import harness
from harness import A, run, select
A.app.config['TESTING'] = True
A.csrf_valid = lambda: True
res = []
def chk(name, cond, extra=''):
    res.append(bool(cond)); print(('PASS ' if cond else 'FAIL ') + name, extra)
def refused(text, items=None):
    try:
        A._board_say(items or [], text); return False
    except A.LabInputError:
        return True
def texts(items):
    return [i.get('text', '') for i in items if i.get('type') == 'equation']

# 1. Spoken words become symbols
chk('speech: "x squared minus 5x plus 6 equals 0"', A._board_speech('x squared minus 5x plus 6 equals 0') == 'x ^2 - 5x + 6 = 0', A._board_speech('x squared minus 5x plus 6 equals 0'))
chk('speech: "divided by" and "times"', A._board_speech('a divided by 2 times b') == 'a / 2 * b')

# 2. Solving linear and quadratic equations, worked on the board
items, msg = A._board_say([], 'solve 2x + 3 = 7')
chk('linear: 2x + 3 = 7 gives x = 2 on the board', 'x = 2' in texts(items), texts(items))
chk('linear: the equation is written first', texts(items)[0] == '2x + 3 = 7', texts(items)[0])
chk('linear: the graph of the difference is plotted too', any(i['type'] == 'graph' and i['expr'] == '2x+3-(7)' for i in items))
items, msg = A._board_say([], 'solve x squared minus 5x plus 6 equals 0')
chk('quadratic: roots 3 and 2 written', 'x = 3 or x = 2' in texts(items), texts(items))
chk('quadratic: a, b, c and D are shown', any(t.startswith('a = 1, b = -5, c = 6') for t in texts(items)) and 'D = b^2 - 4ac = 1' in texts(items))
items, msg = A._board_say([], 'solve x squared plus 1 equals 0')
chk('quadratic: no real roots is said', any('No real solutions' in t for t in texts(items)))
items, msg = A._board_say([], 'solve x squared minus 2x plus 1 equals 0')
chk('quadratic: double root x = 1', 'x = -b / 2a = 1' in texts(items), texts(items))
items, msg = A._board_say([], 'solve 3x equals 9')
chk('linear without a constant: x = 3', 'x = 3' in texts(items), texts(items))
items, msg = A._board_say([], 'solve x squared equals 4')
chk('equation with no linear term still solves (x = 2 or x = -2)', 'x = 2 or x = -2' in texts(items), texts(items))
chk('cubic is refused', refused('solve x cubed equals 8'))
chk('two equals signs are refused', refused('solve x = 2 = 3'))
chk('solving an empty equation is refused', refused('solve'))

# 3. Plotting
items, msg = A._board_say([], 'plot y equals 2x plus 1')
g = items[0]
chk('plot: "plot y equals 2x plus 1" stores 2x + 1', g['type'] == 'graph' and g['expr'] == '2x + 1', g)
items, _ = A._board_say([], 'graph sin(x)')
chk('plot: sin(x) accepted', items[0]['expr'] == 'sin(x)')
chk('plot: unknown word refused', refused('plot banana'))

# 4. Shapes
items, msg = A._board_say([], 'triangle 0,0 4,0 0,3 label right triangle')
t = items[0]
chk('triangle: three points and a label', t['kind'] == 'triangle' and len(t['points']) == 3 and t['label'] == 'right triangle', t)
chk('triangle with four points is refused', refused('triangle 0,0 4,0 0,3 4,4'))
items, _ = A._board_say([], 'circle centre 0,0 radius 2')
chk('circle: centre and radius 2', items[0]['kind'] == 'circle' and items[0]['radius'] == 2 and items[0]['points'] == [[0.0, 0.0]], items[0])
chk('circle without a radius is refused', refused('circle centre 0,0'))
items, _ = A._board_say([], 'angle 1,0 0,0 0,1')
chk('angle: three points', items[0]['kind'] == 'angle' and len(items[0]['points']) == 3)
items, _ = A._board_say([], 'segment 0,0 5,0')
chk('segment: two points', items[0]['kind'] == 'segment')

# 5. Physics arrows
items, msg = A._board_say([], 'force 10 newtons right')
a = items[0]
chk('force: arrow to the right, labelled 10 N', a['type'] == 'arrow' and a['to'] == [10.0, 0.0] and a['label'] == 'force 10 N', a)
items, _ = A._board_say([], 'velocity 3 m/s up')
chk('velocity: arrow up, length 3', items[0]['to'] == [0.0, 3.0] and items[0]['label'].startswith('velocity 3'), items[0])
items, _ = A._board_say([], 'force 25 newtons left')
chk('force above 10 squares is capped at 10 squares, label keeps 25 N', items[0]['to'] == [-10.0, 0.0] and items[0]['label'] == 'force 25 N', items[0])
chk('force without a direction is refused', refused('force 10 newtons'))
chk('force without a size is refused', refused('force right'))

# 6. Pythagoras worked out
items, msg = A._board_say([], 'pythagoras 3 4')
chk('pythagoras: c^2 = 3^2 + 4^2 written', 'c^2 = 3^2 + 4^2' in texts(items), texts(items))
chk('pythagoras: c = 5 written', 'c = 5' in texts(items))
chk('pythagoras: right triangle drawn', any(i['type'] == 'shape' and i['kind'] == 'triangle' for i in items))
chk('pythagoras with one side is refused', refused('pythagoras 3'))

# 7. Writing, clearing, errors
items, _ = A._board_say([], 'write x squared plus 3x equals 10')
chk('write: spoken equation becomes x ^2 + 3x = 10', texts(items) == ['x ^2 + 3x = 10'], texts(items))
chk('write: a brace is refused', refused('write x {2}'))
items, msg = A._board_say([{'type': 'equation', 'text': 'a = b'}], 'clear board')
chk('clear board empties the board', items == [] and msg == 'Board cleared.')
try:
    A._board_say([], 'hello there')
    chk('unknown request is refused', False)
except A.LabInputError as exc:
    chk('unknown request is refused and suggests phrases', 'Try:' in str(exc), str(exc)[:80])
chk('empty request is refused', refused('   '))
full = [{'type': 'equation', 'text': 'x'}] * A.BOARD_MAX_ITEMS
chk('a full board refuses more', refused('write x = 1', full))

# 8. Formula engine checks
tree = A._board_parse('2x + 3')
chk('formula: 2x + 3 at x = 2 is 7', A._board_eval(tree, 2) == 7)
chk('formula: sqrt(x) at -1 is undefined (nan)', A._board_eval(A._board_parse('sqrt(x)'), -1) != A._board_eval(A._board_parse('sqrt(x)'), -1))
chk('formula: 1/0 is undefined', A._board_eval(A._board_parse('1/x'), 0) != A._board_eval(A._board_parse('1/x'), 0))

# 9. Routes, access and persistence
TUID = str(uuid.uuid4()); TID = str(uuid.uuid4()); STUDENT = str(uuid.uuid4()); OUT = str(uuid.uuid4())
run(f"insert into public.koja_academic_teachers (id,user_id,full_name,subjects,grade_levels,hourly_rate,currency,status) values ('{TID}','{TUID}','Mwansa Banda','Maths','Grade 10',120,'ZMW','verified')")
SID = str(uuid.uuid4())
run(f"insert into public.koja_academic_sessions (id,teacher_id,teacher_user_id,student_id,learner_user_id,subject,scheduled_date,start_time,duration_minutes,price,currency,commission,teacher_earning,status,payment_status,room_name) "
    f"values ('{SID}','{TID}','{TUID}','{STUDENT}','{STUDENT}','Maths',current_date+1,'10:00',60,100,'ZMW',15,85,'accepted','paid','koja-ac-{SID[:12]}')")
def client(uid):
    cl = A.app.test_client()
    with cl.session_transaction() as s:
        s['user'] = {'id': uid, 'name': 'U', 'email': 'x@x.test', 'is_admin': False, 'role': 'buyer', 'full_name': 'U'}
        s['_csrf_token'] = 'tok'
    return cl
teacher = client(TUID); student = client(STUDENT); outsider = client(OUT)
hdr = {'X-CSRF-Token': 'tok'}
base = f'/academic/teach/session/{SID}/board'
r = teacher.post(base + '/say', json={'text': 'solve 2x + 3 = 7'}, headers=hdr)
chk('teacher explanation is accepted', r.status_code == 200 and 'x = 2' in [i.get('text') for i in r.get_json()['items']], r.status_code)
chk('the board is saved for the room', len(select('koja_academic_lab_state', {'room': 'board:session:' + SID})) == 1)
r = student.post(base + '/say', json={'text': 'pythagoras 3 4'}, headers=hdr)
chk('a student cannot put things on the board', r.status_code == 403)
r = teacher.post(base + '/say', json={'text': 'banana'}, headers=hdr)
chk('a bad explanation returns a readable error', r.status_code == 400 and 'Try:' in r.get_json()['error'])
r = student.get(base + '/data')
chk('a student sees the same board', r.status_code == 200 and any(i.get('text') == 'x = 2' for i in r.get_json()['items']))
chk('an outsider cannot read the board', outsider.get(base + '/data').status_code == 403)
pg = teacher.get(base).get_data(as_text=True)
chk('the teacher page has the explanation box and voice button', 'sayForm' in pg and 'sayMic' in pg and 'Teacher explanation' in pg)
pg = student.get(base).get_data(as_text=True)
chk('the student page has no controls', 'id="sayForm"' not in pg and 'Your teacher is working on the board' in pg)
chk('the room links to the board', 'Maths and physics board' in teacher.get(f'/academic/room/session/{SID}').get_data(as_text=True))
chk('the board needs login', A.app.test_client().get(base).status_code == 302)
r = teacher.post(base + '/say', json={'text': 'clear board'}, headers=hdr)
chk('the teacher can clear the board by voice', r.get_json()['items'] == [] and student.get(base + '/data').get_json()['items'] == [])

print(f'\n{sum(res)}/{len(res)} passed')
sys.exit(0 if all(res) else 1)
