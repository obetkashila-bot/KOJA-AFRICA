"""Lesson booking works on the live table shape, where learner_user_id is required. Run from the project folder."""
import sys, uuid, subprocess
from datetime import date, timedelta
sys.path.insert(0, '/home/claude/koja_tests')
from harness import A, run, select, PSQL
A.app.config['TESTING'] = True
A.csrf_valid = lambda: True
res = []
def chk(name, cond, extra=''):
    res.append(bool(cond)); print(('PASS ' if cond else 'FAIL ') + name, extra)
subprocess.run(PSQL + ['-f', '/mnt/user-data/attachments/19d8f52e-d460-5865-871e-9298dbb6579d/a46a35ce-koja_academic_migration.sql'], capture_output=True, text=True, check=True)
subprocess.run(PSQL + ['-f', '/home/claude/outputs/koja_app_final/koja_academic_learner_fix.sql'], capture_output=True, text=True, check=True)
# Mirror the live database: learner_user_id is required.
run("alter table public.koja_academic_sessions alter column learner_user_id set not null")
run("delete from public.koja_academic_sessions")
run("delete from public.koja_academic_teachers")
TUID = str(uuid.uuid4()); TID = str(uuid.uuid4())
run(f"insert into public.koja_academic_teachers (id,user_id,full_name,subjects,grade_levels,hourly_rate,status) values ('{TID}','{TUID}','Chanda Zulu','Chemistry','Grade 10',120,'verified')")
STUDENT = str(uuid.uuid4())
c = A.app.test_client()
with c.session_transaction() as s:
    s['user'] = {'id': STUDENT, 'name': 'Student', 'email': 's@x.test', 'is_admin': False, 'role': 'buyer', 'full_name': 'Student'}; s['_csrf_token'] = 'tok'
day = (date.today() + timedelta(days=3)).isoformat()
r = c.post(f'/academic/teacher/{TID}/book', data={'_csrf_token': 'tok', 'scheduled_date': day, 'start_time': '10:00', 'duration_minutes': '60', 'subject': 'Chemistry', 'notes': 'please'})
rows = select('koja_academic_sessions', {'teacher_id': TID})
chk('booking is saved', len(rows) == 1, r.status_code)
chk('the learner is recorded in learner_user_id', bool(rows) and str(rows[0].get('learner_user_id')) == STUDENT)
chk('the learner is also recorded in student_id', bool(rows) and str(rows[0].get('student_id')) == STUDENT)
chk('the lesson is booked instantly and unpaid', bool(rows) and rows[0].get('status') == 'accepted' and rows[0].get('payment_status') == 'unpaid')
run("delete from public.koja_academic_sessions"); run("delete from public.koja_academic_teachers")
run("alter table public.koja_academic_sessions alter column learner_user_id drop not null")  # restore the shared test database
print('RESULT: %d/%d passed' % (sum(res), len(res)))
