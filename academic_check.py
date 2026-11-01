import os, sys, uuid, json
sys.path.insert(0, os.path.dirname(__file__))
import harness as H
from harness import A, run
def _where(filters):
    if not filters: return ''
    parts=[]
    for k,v in filters.items():
        if isinstance(v,str) and v.startswith('in.('):
            items=[H.lit(x.strip()) for x in v[4:-1].split(',') if x.strip()]
            parts.append(f'"{k}" in ({",".join(items)})')
        elif v is None: parts.append(f'"{k}" is null')
        else: parts.append(f'"{k}" = {H.lit(v)}')
    return ' where ' + ' and '.join(parts)
H.where=_where

RESULTS=[]
def check(name, ok, detail=''):
    RESULTS.append((name, ok)); print(('PASS ' if ok else 'FAIL ')+name+(' :: '+str(detail)[:160] if detail else ''))

# ---- schema: the real additive migration, run on the test DB ----
MIG=os.path.join(os.path.dirname(__file__),'..','koja_academic_migration.sql')
run(open(MIG).read())
run("truncate public.koja_academic_ledger, public.koja_academic_attendance, public.koja_academic_enrollments, public.koja_academic_materials, public.koja_academic_reviews, public.koja_academic_sessions, public.koja_academic_classes, public.koja_academic_teachers")
check('S1 migration creates all 9 academic tables', int(run("select count(*) from information_schema.tables where table_schema='public' and table_name like 'koja_academic_%' and table_name not in ('koja_academic_quiz','koja_academic_quiz_answers','koja_academic_refunds','koja_academic_live','koja_academic_payments','koja_academic_equipment','koja_academic_lab_state')"))==9)
run(open(MIG).read()); check('S2 migration runs again without error', True)

# ---- fixtures ----
ADMIN=str(uuid.uuid4()); TEACHER=str(uuid.uuid4()); STUDENT=str(uuid.uuid4()); OTHER=str(uuid.uuid4())
TID=str(uuid.uuid4())
run(f"insert into public.koja_academic_teachers (id,user_id,full_name,subjects,hourly_rate,currency,status) values ('{TID}','{TEACHER}','Tutor T','Maths',100,'ZMW','verified')")

def client(uid=None, admin=False):
    c=A.app.test_client()
    if uid:
        with c.session_transaction() as s:
            s['user']={'id':uid,'is_admin':admin,'role':'admin' if admin else 'customer','full_name':'U'}
            s['_csrf_token']='tok'
    return c
def csrf_form(d): d=dict(d); d['_csrf_token']='tok'; return d

def new_session(status, payment, price=100.0, fee=15.0, earn=85.0):
    sid=str(uuid.uuid4())
    run(f"insert into public.koja_academic_sessions (id,teacher_id,teacher_user_id,student_id,subject,scheduled_date,start_time,duration_minutes,price,currency,commission,teacher_earning,status,payment_status,room_name) "
        f"values ('{sid}','{TID}','{TEACHER}','{STUDENT}','Maths',current_date+7,'10:00',60,{price},'ZMW',{fee},{earn},'{status}','{payment}','koja-ac-{sid[:12]}')")
    return sid
def ledger_earnings(uid, ref):
    return int(run(f"select count(*) from public.koja_academic_ledger where user_id='{uid}' and ref_id='{ref}' and kind='earning'"))

# ---- 1. completed lesson paid later credits the teacher exactly once ----
sid=new_session('completed','unpaid')
check('L1 completed unpaid lesson: no credit yet', ledger_earnings(TEACHER,sid)==0)
r=client(ADMIN,True).post(f'/academic/session/{sid}/mark-paid', data=csrf_form({}))
check('L1 admin mark-paid responds with redirect', r.status_code in (302,303), r.status_code)
check('L1 completed lesson credited on payment', ledger_earnings(TEACHER,sid)==1)
client(ADMIN,True).post(f'/academic/session/{sid}/mark-paid', data=csrf_form({}))
check('L1 second mark-paid does not double credit', ledger_earnings(TEACHER,sid)==1)

# ---- 2. accepted lesson: paid first, then completed credits once ----
sid2=new_session('accepted','unpaid')
client(ADMIN,True).post(f'/academic/session/{sid2}/mark-paid', data=csrf_form({}))
check('L2 accepted + paid: no credit before completion', ledger_earnings(TEACHER,sid2)==0)
client(TEACHER,False).post(f'/academic/session/{sid2}/complete', data=csrf_form({}))
check('L2 completion after payment credits once', ledger_earnings(TEACHER,sid2)==1)

# ---- 3. room gate: unpaid lesson cannot get a token; paid lesson can ----
sid3=new_session('accepted','unpaid')
r=client(STUDENT).get(f'/academic/room/session/{sid3}/token')
check('R1 unpaid accepted lesson: token refused (403)', r.status_code==403, r.status_code)
r=client(TEACHER).get(f'/academic/room/session/{sid3}/token')
check('R1 teacher also refused until paid (403)', r.status_code==403, r.status_code)
client(ADMIN,True).post(f'/academic/session/{sid3}/mark-paid', data=csrf_form({}))
r=client(STUDENT).get(f'/academic/room/session/{sid3}/token')
check('R2 paid accepted lesson: token allowed (not 403)', r.status_code!=403, r.status_code)
r=client(OTHER).get(f'/academic/room/session/{sid3}/token')
check('R3 outsider refused (403)', r.status_code==403, r.status_code)

# ---- 4. student lesson page only shows join once paid ----
sid4=new_session('accepted','unpaid')
b=client(STUDENT).get('/academic/my-lessons').get_data(as_text=True)
check('P1 payment form shown for accepted unpaid lesson', 'Pay with mobile money' in b)

# ---- 5. group class seats: pay before or after attendance credits once ----
CID=str(uuid.uuid4())
run(f"insert into public.koja_academic_classes (id,teacher_id,teacher_user_id,title,subject,scheduled_date,start_time,duration_minutes,capacity,price_per_student,currency,status,room_name) "
    f"values ('{CID}','{TID}','{TEACHER}','Algebra live','Maths',current_date+3,'18:00',60,10,50,'ZMW','open','koja-ac-class-{CID[:10]}')")
r=client(STUDENT).post(f'/academic/class/{CID}/enrol', data=csrf_form({}))
enr=H.first('koja_academic_enrollments', {'class_id':CID,'student_id':STUDENT})
check('C1 paid class enrol creates unpaid seat', enr and enr['payment_status']=='unpaid', enr and enr.get('payment_status'))
EID=enr['id']
# attendance marked before payment: no credit yet
client(TEACHER).post(f'/academic/class/{CID}/attendance', data=csrf_form({'present':[STUDENT]}))
check('C2 attendance before payment: no credit', ledger_earnings(TEACHER,EID)==0)
r=client(ADMIN,True).post(f'/admin/academic/enrolment/{EID}/mark-paid', data=csrf_form({}))
check('C3 admin marks seat paid, redirect', r.status_code in (302,303), r.status_code)
check('C3 seat credited once after payment (attended)', ledger_earnings(TEACHER,EID)==1)
client(ADMIN,True).post(f'/admin/academic/enrolment/{EID}/mark-paid', data=csrf_form({}))
client(TEACHER,False).post(f'/academic/class/{CID}/attendance', data=csrf_form({'present':[STUDENT]}))
check('C3 repeat payment/attendance does not double credit', ledger_earnings(TEACHER,EID)==1)

# seat paid first, then attended: credits at attendance
CID2=str(uuid.uuid4())
run(f"insert into public.koja_academic_classes (id,teacher_id,teacher_user_id,title,subject,scheduled_date,start_time,duration_minutes,capacity,price_per_student,currency,status,room_name) "
    f"values ('{CID2}','{TID}','{TEACHER}','Physics live','Science',current_date+4,'18:00',60,10,50,'ZMW','open','koja-ac-class-{CID2[:10]}')")
client(STUDENT).post(f'/academic/class/{CID2}/enrol', data=csrf_form({}))
EID2=H.first('koja_academic_enrollments', {'class_id':CID2,'student_id':STUDENT})['id']
client(ADMIN,True).post(f'/admin/academic/enrolment/{EID2}/mark-paid', data=csrf_form({}))
check('C4 paid seat before attendance: no credit yet', ledger_earnings(TEACHER,EID2)==0)
client(TEACHER,False).post(f'/academic/class/{CID2}/attendance', data=csrf_form({'present':[STUDENT]}))
check('C4 attendance after payment credits once', ledger_earnings(TEACHER,EID2)==1)

# ---- 6. permissions: only admins can mark seats or lessons paid ----
CID3=str(uuid.uuid4())
run(f"insert into public.koja_academic_classes (id,teacher_id,teacher_user_id,title,subject,scheduled_date,start_time,duration_minutes,capacity,price_per_student,currency,status,room_name) "
    f"values ('{CID3}','{TID}','{TEACHER}','Chem live','Science',current_date+5,'18:00',60,10,50,'ZMW','open','koja-ac-class-{CID3[:10]}')")
client(OTHER).post(f'/academic/class/{CID3}/enrol', data=csrf_form({}))
EID3=H.first('koja_academic_enrollments', {'class_id':CID3,'student_id':OTHER})['id']
r=client(STUDENT).post(f'/admin/academic/enrolment/{EID3}/mark-paid', data=csrf_form({}))
check('X1 non-admin cannot mark seat paid', r.status_code in (302,303,403) and H.first('koja_academic_enrollments',{'id':EID3})['payment_status']=='unpaid', r.status_code)
r=client(STUDENT).post(f'/academic/session/{sid4}/mark-paid', data=csrf_form({}))
check('X2 non-admin cannot mark lesson paid', H.first('koja_academic_sessions',{'id':sid4})['payment_status']=='unpaid', r.status_code)

# ---- 7. whiteboard history and live room page ----
bs=new_session('accepted','paid')
BU=f'/academic/room/session/{bs}/board'
st_c=client(STUDENT); te_c=client(TEACHER,False); out_c=client(OTHER)
r=st_c.post(BU, headers={'X-CSRF-Token':'tok'}, json={'kind':'stroke','points':[[10,10],[50,60],[90,20]]})
check('B1 student stroke saved (200)', r.status_code==200, r.status_code)
r=te_c.get(BU); strokes=r.get_json().get('strokes',[])
check('B2 late joiner (teacher) sees saved stroke', len(strokes)==1 and strokes[0]['points'][1]==[50,60], strokes)
r=st_c.post(BU, headers={'X-CSRF-Token':'tok'}, json={'kind':'clear'})
check('B3 student cannot clear the board (403)', r.status_code==403, r.status_code)
r=te_c.post(BU, headers={'X-CSRF-Token':'tok'}, json={'kind':'stroke','points':[[1,1],[2,2]]})
check('B4 stroke after a clear is kept', r.status_code==200, r.status_code)
te_c.post(BU, headers={'X-CSRF-Token':'tok'}, json={'kind':'clear'})
check('B5 teacher clear empties history', te_c.get(BU).get_json()['strokes']==[])
te_c.post(BU, headers={'X-CSRF-Token':'tok'}, json={'kind':'stroke','points':[[5,5],[9999,-50]]})
pts=st_c.get(BU).get_json()['strokes'][0]['points']
check('B6 coordinates clamped to the canvas', pts[1]==[800.0,0.0], pts)
check('B7 one-point stroke rejected (400)', te_c.post(BU, headers={'X-CSRF-Token':'tok'}, json={'kind':'stroke','points':[[1,1]]}).status_code==400)
check('B8 bad point rejected (400)', te_c.post(BU, headers={'X-CSRF-Token':'tok'}, json={'kind':'stroke','points':[[1,'x'],[2,2]]}).status_code==400)
check('B9 unknown action rejected (400)', te_c.post(BU, headers={'X-CSRF-Token':'tok'}, json={'kind':'wipe'}).status_code==400)
check('B10 outsider cannot read board (403)', out_c.get(BU).status_code==403)
check('B11 outsider cannot write board (403)', out_c.post(BU, headers={'X-CSRF-Token':'tok'}, json={'kind':'stroke','points':[[1,1],[2,2]]}).status_code==403)
ub=new_session('accepted','unpaid')
check('B12 board closed until lesson is paid (403)', client(STUDENT).get(f'/academic/room/session/{ub}/board').status_code==403)
page_t=te_c.get(f'/academic/room/session/{bs}').get_data(as_text=True)
page_s=st_c.get(f'/academic/room/session/{bs}').get_data(as_text=True)
check('P2 room page renders with whiteboard and leave button', 'id="ac-board"' in page_t and 'id="ac-leave"' in page_t)
check('P3 Clear button only for the teacher', 'id="ac-clear"' in page_t and 'id="ac-clear"' not in page_s)
CB=f'/academic/room/class/{CID}/board'
check('B13 enrolled-and-paid student can read class board', client(STUDENT).get(CB).status_code==200)
check('B14 unpaid enrolled student cannot read class board', client(OTHER).get(CB).status_code==403)

print()
passed=sum(1 for _,ok in RESULTS if ok)
print(f'SUMMARY {passed} PASS / {len(RESULTS)-passed} FAIL')
