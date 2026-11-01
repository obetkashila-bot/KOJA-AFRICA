"""Materials and equipment for lessons and classes: who can add, see, tick and download. Run from the project folder."""
import sys, uuid, subprocess, io
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
          '/home/claude/outputs/koja_app_final/koja_academic_payments.sql',
          '/home/claude/outputs/koja_app_final/koja_academic_teaching.sql']:
    subprocess.run(PSQL + ['-f', f], capture_output=True, text=True, check=True)
run("alter table public.koja_academic_sessions alter column learner_user_id set not null")
for t in ['koja_academic_equipment', 'koja_academic_materials', 'koja_academic_enrollments', 'koja_academic_payments', 'koja_academic_ledger', 'koja_academic_live', 'koja_academic_sessions', 'koja_academic_classes', 'koja_academic_teachers']:
    run(f"delete from public.{t}")
TUID = str(uuid.uuid4()); TID = str(uuid.uuid4()); STUDENT = str(uuid.uuid4()); OTHER = str(uuid.uuid4())
run(f"insert into public.koja_academic_teachers (id,user_id,full_name,subjects,grade_levels,hourly_rate,currency,status) values ('{TID}','{TUID}','Chanda Zulu','Science','Grade 10',120,'ZMW','verified')")
SID = str(uuid.uuid4()); CID = str(uuid.uuid4())
run(f"insert into public.koja_academic_sessions (id,teacher_id,teacher_user_id,student_id,learner_user_id,subject,scheduled_date,start_time,duration_minutes,price,currency,commission,teacher_earning,status,payment_status,room_name) "
    f"values ('{SID}','{TID}','{TUID}','{STUDENT}','{STUDENT}','Chemistry',current_date+1,'10:00',60,100,'ZMW',15,85,'accepted','paid','koja-ac-{SID[:12]}')")
run(f"insert into public.koja_academic_classes (id,teacher_id,teacher_user_id,title,subject,scheduled_date,start_time,duration_minutes,capacity,price_per_student,currency,status,room_name) "
    f"values ('{CID}','{TID}','{TUID}','Computer lab basics','ICT',current_date+2,'18:00',60,10,50,'ZMW','open','koja-ac-class-{CID[:10]}')")
run(f"insert into public.koja_academic_enrollments (class_id,student_id,payment_status) values ('{CID}','{STUDENT}','unpaid')")

A.FLW_SECRET_KEY = 'x'
A.upload_storage = lambda f, **k: ({'path': 'academic-materials/abc_' + f.filename, 'url': None, 'file_name': f.filename,
                                    'file_size': 3, 'mime_type': 'application/pdf'}, None)
class FakeGet:
    ok = True; content = b'%PDF-test'; headers = {'Content-Type': 'application/pdf'}
A._HTTP.get = lambda *a, **k: FakeGet()

def client(uid, name='User'):
    c = A.app.test_client()
    with c.session_transaction() as s:
        s['user'] = {'id': uid, 'name': name, 'email': 'x@x.test', 'is_admin': False, 'role': 'buyer', 'full_name': name}
        s['_csrf_token'] = 'tok'
    return c
teacher = client(TUID, 'Chanda'); student = client(STUDENT, 'Student'); other = client(OTHER, 'Other')
csrf = {'_csrf_token': 'tok'}

# 1. Teacher adds a link and an uploaded file to a lesson
r = teacher.post(f'/academic/teach/session/{SID}/material', data={**csrf, 'title': 'Lab sheet', 'url': 'https://example.org/lab'})
r = teacher.post(f'/academic/teach/session/{SID}/material', data={**csrf, 'title': 'Safety notes', 'file': (io.BytesIO(b'abc'), 'safety.pdf')}, content_type='multipart/form-data')
mats = select('koja_academic_materials', {'session_id': SID})
chk('a link is saved for the lesson', any(m['title'] == 'Lab sheet' and m['url'] == 'https://example.org/lab' for m in mats))
chk('an uploaded file is saved for the lesson', any(m['title'] == 'Safety notes' and m.get('file_path') for m in mats))
r = teacher.post(f'/academic/teach/session/{SID}/material', data={**csrf, 'title': 'Bad', 'url': 'javascript:alert(1)'})
chk('a non-web link is refused', not any(m['title'] == 'Bad' for m in select('koja_academic_materials', {'session_id': SID})))

# 2. Students can see; only the teacher can change
r = student.get(f'/academic/teach/session/{SID}')
chk('the booked student sees the lesson materials page', r.status_code == 200 and 'Lab sheet' in r.get_data(as_text=True))
r = student.post(f'/academic/teach/session/{SID}/material', data={**csrf, 'title': 'Mine', 'url': 'https://example.org/x'})
chk('a student cannot add material', r.status_code == 403 and not any(m['title'] == 'Mine' for m in select('koja_academic_materials', {'session_id': SID})))
r = other.get(f'/academic/teach/session/{SID}')
chk('someone not on the lesson cannot open its materials', r.status_code == 404, r.status_code)

# 3. Equipment: add, tick ready, remove
r = teacher.post(f'/academic/teach/session/{SID}/equipment', data={**csrf, 'category': 'lab', 'name': 'Bunsen burner', 'quantity': '5', 'provided_by': 'teacher', 'notes': 'Gas on bench 2'})
eq = select('koja_academic_equipment', {'session_id': SID})
chk('lab equipment is saved with quantity and who provides it', len(eq) == 1 and eq[0]['category'] == 'lab' and eq[0]['quantity'] == 5 and eq[0]['provided_by'] == 'teacher')
r = teacher.post(f'/academic/teach/session/{SID}/equipment', data={**csrf, 'category': 'nonsense', 'name': 'Laptop', 'quantity': '99999', 'provided_by': 'student'})
eq2 = [x for x in select('koja_academic_equipment', {'session_id': SID}) if x['name'] == 'Laptop']
chk('unknown categories fall back to other and quantity is capped', eq2 and eq2[0]['category'] == 'other' and eq2[0]['quantity'] == 1000 and eq2[0]['provided_by'] == 'student')
r = student.post(f"/academic/equipment/{eq[0]['id']}/ready", data=csrf)
chk('a student cannot tick equipment ready', r.status_code == 403)
teacher.post(f"/academic/equipment/{eq[0]['id']}/ready", data=csrf)
chk('the teacher can mark equipment ready', select('koja_academic_equipment', {'id': eq[0]['id']})[0]['ready'] is True)
body = student.get(f'/academic/teach/session/{SID}').get_data(as_text=True)
chk('the student sees the ready tick and the lab item', 'Bunsen burner' in body and '✔' in body)
teacher.post(f"/academic/equipment/{eq2[0]['id']}/delete", data=csrf)
chk('the teacher can remove equipment', not select('koja_academic_equipment', {'id': eq2[0]['id']}))

# 4. File download: students on the lesson only
mid_file = [m for m in select('koja_academic_materials', {'session_id': SID}) if m.get('file_path')][0]['id']
r = student.get(f'/academic/material/{mid_file}/file')
chk('the booked student can download the file', r.status_code == 200 and r.data == b'%PDF-test', r.status_code)
r = other.get(f'/academic/material/{mid_file}/file')
chk('someone not on the lesson cannot download it', r.status_code == 403, r.status_code)

# 5. Group class: enrolled students see materials and equipment; others do not
teacher.post(f'/academic/teach/class/{CID}/equipment', data={**csrf, 'category': 'computer', 'name': 'Laptop with Excel', 'quantity': '10', 'provided_by': 'teacher'})
body = student.get(f'/academic/teach/class/{CID}').get_data(as_text=True)
chk('enrolled students see the class equipment', 'Laptop with Excel' in body)
chk('someone not enrolled cannot see the class equipment', other.get(f'/academic/teach/class/{CID}').status_code == 404)

# 6. The live room shows the lists
room = teacher.get(f'/academic/room/session/{SID}').get_data(as_text=True)
chk('the live room lists the materials and equipment', 'Safety notes' in room and 'Bunsen burner' in room and 'Full materials and equipment page' in room)

# 7. Deleting a material removes it for the teacher only
mid_link = [m for m in select('koja_academic_materials', {'session_id': SID}) if m['title'] == 'Lab sheet'][0]['id']
student.post(f'/academic/material/{mid_link}/delete', data=csrf)
chk('a student cannot remove material', select('koja_academic_materials', {'id': mid_link}) != [])
teacher.post(f'/academic/material/{mid_link}/delete', data=csrf)
chk('the teacher can remove material', select('koja_academic_materials', {'id': mid_link}) == [])

run("delete from public.koja_academic_equipment"); run("delete from public.koja_academic_materials"); run("delete from public.koja_academic_enrollments")
run("delete from public.koja_academic_live"); run("delete from public.koja_academic_sessions"); run("delete from public.koja_academic_classes"); run("delete from public.koja_academic_teachers")
run("alter table public.koja_academic_sessions alter column learner_user_id drop not null")
print('RESULT: %d/%d passed' % (sum(res), len(res)))
