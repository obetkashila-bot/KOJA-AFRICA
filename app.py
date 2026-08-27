import os
import json
import uuid
import hashlib
import secrets
from datetime import datetime, timezone
from functools import wraps

from flask import (
    Flask, request, redirect, url_for, session,
    render_template_string, flash, send_from_directory,
    abort, make_response
)

# ============================================================
# KOJA AFRICA - MODERN SINGLE-FILE FLASK PORTAL
# ============================================================

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", secrets.token_hex(32))

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "koja_data")
STUDENT_UPLOAD_DIR = os.path.join(DATA_DIR, "uploads", "students")
ADMIN_UPLOAD_DIR = os.path.join(DATA_DIR, "uploads", "admin")

for folder in (DATA_DIR, STUDENT_UPLOAD_DIR, ADMIN_UPLOAD_DIR):
    os.makedirs(folder, exist_ok=True)

USERS_FILE = os.path.join(DATA_DIR, "users.json")
QUESTIONS_FILE = os.path.join(DATA_DIR, "questions.json")
LOGS_FILE = os.path.join(DATA_DIR, "logs.json")
DOCUMENTS_FILE = os.path.join(DATA_DIR, "documents.json")

MAX_FILE_SIZE = 15 * 1024 * 1024
ALLOWED_EXTENSIONS = {
    "pdf", "doc", "docx", "txt", "jpg", "jpeg", "png",
    "xls", "xlsx", "ppt", "pptx", "csv"
}


# ------------------------- STORAGE ----------------------------

def ensure_file(path, default):
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(default, f, indent=2, ensure_ascii=False)


for _file in (USERS_FILE, QUESTIONS_FILE, LOGS_FILE, DOCUMENTS_FILE):
    ensure_file(_file, [])


def read_json(path, default=None):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return [] if default is None else default


def write_json(path, data):
    temp = path + ".tmp"
    with open(temp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(temp, path)


# ------------------------- SECURITY ---------------------------

def hash_password(password):
    salt = secrets.token_bytes(16)
    key = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, 150000
    )
    return salt.hex() + "$" + key.hex()


def verify_password(password, stored):
    try:
        salt_hex, key_hex = stored.split("$", 1)
        actual = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            bytes.fromhex(salt_hex),
            150000
        )
        return secrets.compare_digest(actual, bytes.fromhex(key_hex))
    except Exception:
        return False


def ensure_admin():
    users = read_json(USERS_FILE, [])
    if any(u.get("role") == "admin" for u in users):
        return

    email = os.environ.get(
        "KOJA_ADMIN_EMAIL", "admin@koja.africa"
    ).strip().lower()
    password = os.environ.get(
        "KOJA_ADMIN_PASSWORD", "ChangeMe123!"
    )

    users.append({
        "id": str(uuid.uuid4()),
        "name": "KOJA Administrator",
        "email": email,
        "password": hash_password(password),
        "role": "admin",
        "created_at": datetime.now(timezone.utc).isoformat()
    })
    write_json(USERS_FILE, users)


ensure_admin()


def current_user():
    uid = session.get("user_id")
    if not uid:
        return None
    return next(
        (u for u in read_json(USERS_FILE, []) if u.get("id") == uid),
        None
    )


def get_user(user_id):
    return next(
        (u for u in read_json(USERS_FILE, []) if u.get("id") == user_id),
        None
    )


def students():
    return [
        u for u in read_json(USERS_FILE, [])
        if u.get("role") == "student"
    ]


def login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not current_user():
            flash("Please log in first.", "error")
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapper


def admin_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        user = current_user()
        if not user:
            flash("Please log in first.", "error")
            return redirect(url_for("login"))
        if user.get("role") != "admin":
            abort(403)
        return view(*args, **kwargs)
    return wrapper


# ------------------------- HELPERS ----------------------------

def esc(value):
    if value is None:
        return ""
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


def log_event(event, category="System", level="INFO", details=""):
    logs = read_json(LOGS_FILE, [])
    logs.append({
        "id": str(uuid.uuid4()),
        "event": event,
        "category": category,
        "level": level,
        "details": details,
        "time": datetime.now(timezone.utc).isoformat(),
        "user_id": session.get("user_id")
    })
    write_json(LOGS_FILE, logs[-5000:])


def allowed_file(filename):
    return bool(
        filename and "." in filename and
        filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS
    )


def save_file(file, directory):
    if not file or not file.filename:
        return None

    original = os.path.basename(file.filename).replace("\x00", "")[:200]

    if not allowed_file(original):
        raise ValueError("This file type is not allowed.")

    data = file.read()

    if len(data) > MAX_FILE_SIZE:
        raise ValueError("Maximum file size is 15 MB.")

    stored = str(uuid.uuid4()) + "_" + original

    with open(os.path.join(directory, stored), "wb") as f:
        f.write(data)

    return {
        "original_name": original,
        "stored_name": stored,
        "size": len(data)
    }


def size_text(size):
    try:
        size = int(size)
    except Exception:
        return ""
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / (1024 * 1024):.1f} MB"


# ------------------------- DESIGN -----------------------------

CSS = r"""
<style>
:root{
 --navy:#07142f;--navy2:#0e1c40;--panel:#172653;--panel2:#202e5c;
 --line:rgba(255,255,255,.10);--text:#f4f6ff;--muted:#adb7d8;
 --blue:#5968ff;--green:#70df55;--cyan:#18c7ed;--orange:#ff8b18;
 --pink:#ff3d78;--purple:#743fc1;
}
*{box-sizing:border-box}
html,body{margin:0;min-height:100%;font-family:Arial,Helvetica,sans-serif}
body{
 color:var(--text);
 background:
 radial-gradient(circle at 80% 10%,rgba(84,96,206,.25),transparent 30%),
 linear-gradient(145deg,#07142f,#121d43 48%,#2a285b);
}
a{text-decoration:none;color:inherit}
button,input,textarea,select{font:inherit}

.topbar{
 position:sticky;top:0;z-index:100;
 background:rgba(5,17,43,.97);
 border-bottom:1px solid var(--line);
 backdrop-filter:blur(14px);
}
.topbar-inner{
 max-width:1450px;margin:auto;min-height:82px;padding:10px 22px;
 display:flex;align-items:center;gap:18px;
}
.brand{display:flex;align-items:center;min-width:210px}
.logo{
 font-size:43px;font-weight:900;letter-spacing:-5px;line-height:.8;
}
.k{color:#29aff6}.o{color:#65d84e}.j{color:#ff3f51}.a{color:#4c72df}
.africa{
 text-align:center;font-size:8px;letter-spacing:5px;color:#d4d9ef;margin-top:8px;
}
.search{flex:1;max-width:520px;position:relative}
.search input{
 width:100%;background:#101c3d;color:white;border:1px solid rgba(255,255,255,.06);
 border-radius:16px;padding:15px 18px 15px 50px;outline:none;
}
.search-icon{
 position:absolute;left:17px;top:50%;transform:translateY(-50%);
 font-size:26px;color:#aeb8d8;
}
.profile{
 margin-left:auto;width:50px;height:50px;border-radius:50%;
 display:flex;align-items:center;justify-content:center;
 background:#d7b38e;color:#563e32;font-weight:900;
 border:3px solid rgba(255,255,255,.3);position:relative;
}
.online{
 position:absolute;right:-1px;bottom:1px;width:13px;height:13px;
 border-radius:50%;background:#62e644;border:2px solid #10204a;
}
.nav{display:flex;gap:4px;align-items:center}
.nav a{padding:10px 10px;border-radius:9px;color:#cbd3ef;font-weight:700;font-size:14px}
.nav a:hover{background:rgba(255,255,255,.08);color:white}
.menu{display:none;border:0;background:none;color:#b8c1df;font-size:30px}

.container{max-width:1450px;margin:auto;padding:28px 24px 75px}
.card{
 background:linear-gradient(145deg,rgba(27,42,88,.96),rgba(20,31,68,.97));
 border:1px solid var(--line);border-radius:20px;padding:24px;margin-bottom:20px;
 box-shadow:0 18px 45px rgba(0,0,0,.18);
}
.hero{
 min-height:600px;position:relative;overflow:hidden;padding:38px 44px;
 background:
 radial-gradient(circle at 82% 35%,rgba(91,104,255,.24),transparent 33%),
 linear-gradient(135deg,#172857,#292a63);
}
.greeting{
 display:inline-block;padding:10px 19px;border-radius:25px;
 background:linear-gradient(90deg,#3e4aa2,#5364d3);
 color:#dce1ff;font-weight:800;
}
.hero h1{font-size:clamp(42px,5vw,67px);margin:25px 0 12px;letter-spacing:-2px}
.hero h1 span{color:#6371ff}
.hero p{max-width:610px;color:#b7bfda;font-size:19px;line-height:1.65;margin:0}
.actions{display:flex;gap:13px;flex-wrap:wrap;margin-top:32px;position:relative;z-index:5}
.btn,.btn2{
 display:inline-flex;align-items:center;justify-content:center;gap:8px;
 padding:14px 21px;border-radius:15px;font-weight:800;border:0;cursor:pointer;
 transition:.2s;
}
.btn:hover,.btn2:hover{transform:translateY(-2px)}
.btn{background:linear-gradient(135deg,#5b6aff,#6554ff);color:#fff;box-shadow:0 12px 30px rgba(83,91,255,.25)}
.btn2{background:rgba(255,255,255,.04);border:1px solid var(--line);color:#dbe0f7}
.btn.green{background:rgba(67,146,60,.28);color:#9af072}
.btn.orange{background:rgba(255,139,24,.2);color:#ffb35d}
.btn.red{background:#b52e4c}
.btn.gray{background:#3a4766}

.stats{
 display:grid;grid-template-columns:repeat(4,1fr);
 margin-top:42px;border:1px solid var(--line);border-radius:19px;
 overflow:hidden;background:rgba(7,18,44,.25);position:relative;z-index:5;
}
.stat{text-align:center;padding:21px 12px;border-right:1px solid var(--line)}
.stat:last-child{border-right:0}
.stat-icon{
 width:51px;height:51px;margin:auto auto 9px;border-radius:50%;
 display:flex;align-items:center;justify-content:center;
 font-size:25px;font-weight:900;background:#276bd4;
}
.stat:nth-child(2) .stat-icon{background:#4b9143}
.stat:nth-child(3) .stat-icon{background:#6b3fc0}
.stat:nth-child(4) .stat-icon{background:#cb6e13}
.stat h2{font-size:31px;margin:0 0 4px}
.stat p{margin:0;color:#aeb8d8;line-height:1.35}

.illustration{position:absolute;right:5%;bottom:18px;width:330px;height:250px;opacity:.95}
.person{
 position:absolute;right:65px;bottom:5px;width:150px;height:175px;
 background:#5e68ef;border-radius:58% 58% 25% 25%;
}
.head{
 position:absolute;width:85px;height:85px;border-radius:50%;
 background:#f1b795;top:-48px;left:33px;
}
.hair{
 position:absolute;width:90px;height:57px;border-radius:50% 50% 35% 35%;
 background:#20294f;top:-58px;left:29px;
}
.eye{position:absolute;width:9px;height:9px;background:#fff;border-radius:50%;top:29px}
.eye.one{left:24px}.eye.two{right:24px}
.laptop{
 position:absolute;bottom:0;left:0;width:190px;height:105px;
 background:#b8bee2;border-radius:8px 8px 3px 3px;transform:skew(-8deg);
}
.laptop:after{
 content:"";position:absolute;left:-10px;bottom:-11px;width:210px;height:12px;
 background:#8e96bd;border-radius:0 0 9px 9px;
}
.plant{position:absolute;right:0;bottom:0;width:40px;height:55px;background:#e8e9f2}
.plant:before,.plant:after{
 content:"";position:absolute;bottom:44px;width:14px;height:66px;
 background:#24c5e8;border-radius:100% 0 100% 0;
}
.plant:before{left:-12px;transform:rotate(-25deg)}
.plant:after{right:-9px;transform:rotate(25deg)}
.clock{
 position:absolute;right:23px;top:28px;width:52px;height:52px;border-radius:50%;
 background:white;border:4px solid #cfd4e9;
}
.clock:after{
 content:"";position:absolute;width:2px;height:18px;background:#7c829d;
 left:23px;top:8px;transform-origin:bottom;transform:rotate(10deg);
}

.section-title{display:flex;justify-content:space-between;align-items:center;margin:25px 3px 14px}
.section-title h2{margin:0;font-size:25px}
.quick-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}
.quick{
 min-height:165px;padding:21px;border-radius:18px;
 background:rgba(29,43,84,.82);border:1px solid var(--line);
 transition:.2s;
}
.quick:hover{transform:translateY(-3px);background:rgba(38,54,102,.95)}
.quick-icon{
 width:52px;height:52px;border-radius:13px;display:flex;align-items:center;
 justify-content:center;font-size:25px;margin-bottom:16px;background:#5c49ef;
}
.quick:nth-child(2) .quick-icon{background:#1675d2}
.quick:nth-child(3) .quick-icon{background:#4aa23d}
.quick:nth-child(4) .quick-icon{background:#e77908}
.quick:nth-child(5) .quick-icon{background:#ed3970}
.quick:nth-child(6) .quick-icon{background:#743dbc}
.quick h3{margin:0 0 7px;font-size:18px}
.quick p{margin:0;color:#aeb8d8;line-height:1.45}

.form-control{
 width:100%;padding:14px 15px;margin:7px 0 15px;border-radius:11px;
 border:1px solid #34466f;background:#0e1b3d;color:white;outline:none;
}
textarea.form-control{min-height:180px;resize:vertical}
label{display:block;font-weight:800;color:#dde2f7;margin-top:10px}
.question,.answer{white-space:pre-wrap;padding:18px;border-radius:13px;line-height:1.7}
.question{background:#101d40;border:1px solid var(--line)}
.answer{background:#102b40;border:1px solid rgba(24,199,237,.16)}
.document-box{padding:16px;border-radius:12px;background:#101d40;border:1px solid var(--line);margin-top:12px}
.badge{display:inline-block;padding:6px 10px;border-radius:30px;font-size:12px;font-weight:800}
.pending{background:#55451d;color:#ffd86a}.answered{background:#1f5330;color:#9af19c}
.table-wrap{overflow:auto}
table{width:100%;border-collapse:collapse;min-width:700px}
th,td{padding:13px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
th{color:#e0e4f8}td{color:#b8c1dd}
.muted{color:#9fa9ca}
.empty{text-align:center;padding:35px;color:#9fa9ca}
.alert{max-width:1000px;margin:14px auto;padding:13px 18px;border-radius:12px;background:#1d3969}
.alert.error{background:#57283a;color:#ffd9e2}
.alert.success{background:#1d5138;color:#caffd8}
.auth{max-width:560px;margin:45px auto}
footer{text-align:center;color:#8994b6;padding:30px}
.mobile-bottom{display:none}

@media(max-width:1100px){
 .nav{display:none}.menu{display:block}.brand{min-width:auto}
 .quick-grid{grid-template-columns:repeat(2,1fr)}
 .illustration{right:-10px;opacity:.75}
}
@media(max-width:760px){
 .topbar-inner{min-height:75px;padding:9px 13px;gap:10px;flex-wrap:wrap}
 .brand{order:2}.logo{font-size:36px}
 .profile{order:3;width:44px;height:44px}
 .menu{order:1}
 .search{order:4;flex-basis:100%;max-width:none}
 .container{padding:18px 12px 90px}
 .hero{min-height:680px;padding:24px 19px}
 .hero h1{font-size:42px}.hero p{font-size:16px}
 .actions{margin-top:25px}
 .actions .btn,.actions .btn2{flex:1;min-width:140px}
 .illustration{transform:scale(.66);transform-origin:bottom right;right:-25px;bottom:18px}
 .stats{grid-template-columns:repeat(2,1fr);margin-top:30px}
 .stat{border-bottom:1px solid var(--line)}
 .stat:nth-child(2),.stat:nth-child(4){border-right:0}
 .quick-grid{grid-template-columns:1fr 1fr;gap:11px}
 .quick{min-height:145px;padding:16px}
 .quick h3{font-size:16px}.quick p{font-size:13px}
 .card{padding:18px}
 .mobile-bottom{
   position:fixed;left:0;right:0;bottom:0;height:68px;z-index:90;
   display:flex;align-items:center;justify-content:space-around;
   background:rgba(8,20,49,.98);border-top:1px solid var(--line)
 }
 .mobile-bottom a{text-align:center;color:#adb7d7;font-size:12px}
 .mobile-bottom strong{display:block;color:#6071ff;font-size:22px;line-height:25px}
}
</style>
"""


PUBLIC_LAYOUT = r"""
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="index,follow">
<title>{{ title }} | KOJA AFRICA</title>
""" + CSS + r"""
</head>
<body>
<header class="topbar">
<div class="topbar-inner">
<a class="brand" href="/">
<div>
<div class="logo"><span class="k">k</span><span class="o">o</span><span class="j">j</span><span class="a">a</span></div>
<div class="africa">AFRICA</div>
</div>
</a>
<nav class="nav" style="margin-left:auto">
<a href="/login">Log In</a>
<a class="btn" href="/register">Create Account</a>
</nav>
</div>
</header>
{% with messages=get_flashed_messages(with_categories=true) %}
{% for category,message in messages %}
<div class="alert {{ category }}">{{ message }}</div>
{% endfor %}
{% endwith %}
<main class="container">{{ content|safe }}</main>
<footer><strong>KOJA AFRICA</strong><br>Knowledge • Questions • Answers</footer>
</body>
</html>
"""


PRIVATE_LAYOUT = r"""
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow,noarchive">
<title>{{ title }} | KOJA AFRICA</title>
""" + CSS + r"""
</head>
<body>
<header class="topbar">
<div class="topbar-inner">
<button class="menu" onclick="document.getElementById('nav').classList.toggle('open')">☰</button>
<a class="brand" href="/">
<div>
<div class="logo"><span class="k">k</span><span class="o">o</span><span class="j">j</span><span class="a">a</span></div>
<div class="africa">AFRICA</div>
</div>
</a>
<div class="search">
<span class="search-icon">⌕</span>
<input placeholder="Search research..." onkeydown="if(event.key==='Enter'){location='/research?q='+encodeURIComponent(this.value)}">
</div>
<div class="profile">{{ (session.get('role','U')[0] if session.get('role') else 'U')|upper }}<span class="online"></span></div>
<nav class="nav" id="nav">
{% if session.get("role") == "admin" %}
<a href="/admin">Dashboard</a>
<a href="/admin/questions">Questions</a>
<a href="/admin/answers">Answers</a>
<a href="/admin/documents">Documents</a>
<a href="/admin/logs">Logs</a>
{% else %}
<a href="/student">Dashboard</a>
<a href="/ask">Ask Question</a>
<a href="/student/questions">My Questions</a>
<a href="/research">Research</a>
<a href="/student/documents">Documents</a>
{% endif %}
<a href="/logout">Logout</a>
</nav>
</div>
</header>
{% with messages=get_flashed_messages(with_categories=true) %}
{% for category,message in messages %}
<div class="alert {{ category }}">{{ message }}</div>
{% endfor %}
{% endwith %}
<main class="container">{{ content|safe }}</main>
{% if session.get("role") == "student" %}
<nav class="mobile-bottom">
<a href="/student"><strong>⌂</strong>Dashboard</a>
<a href="/ask"><strong>＋</strong>Ask</a>
<a href="/student/documents"><strong>□</strong>Documents</a>
<a href="/logout"><strong>→</strong>Logout</a>
</nav>
{% endif %}
<footer><strong>KOJA AFRICA</strong><br>Knowledge • Questions • Answers</footer>
</body>
</html>
"""


def public_page(title, content):
    return render_template_string(PUBLIC_LAYOUT, title=title, content=content)


def private_page(title, content):
    return render_template_string(PRIVATE_LAYOUT, title=title, content=content)


# ============================================================
# PUBLIC
# ============================================================

@app.route("/")
def home():
    content = r"""
<section class="card" style="text-align:center;max-width:1050px;margin:65px auto;padding:70px 25px">
<div class="logo"><span class="k">K</span><span class="o">O</span><span class="j">J</span><span class="a">A</span></div>
<div class="africa">AFRICA</div>
<h2>Knowledge • Questions • Answers</h2>
<p style="max-width:760px;margin:20px auto;color:#b7bfda;font-size:19px;line-height:1.7">
Academic questions, research, learning resources and educational support in one platform.
</p>
<div class="actions" style="justify-content:center">
<a class="btn" href="/login">Log In</a>
<a class="btn2" href="/register">Create Account</a>
</div>
</section>
"""
    return public_page("Home", content)


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not name or not email or not password:
            flash("Complete all fields.", "error")
            return redirect("/register")
        if len(password) < 6:
            flash("Password must contain at least 6 characters.", "error")
            return redirect("/register")

        users = read_json(USERS_FILE, [])
        if any(u.get("email") == email for u in users):
            flash("An account with that email already exists.", "error")
            return redirect("/register")

        users.append({
            "id": str(uuid.uuid4()),
            "name": name,
            "email": email,
            "password": hash_password(password),
            "role": "student",
            "created_at": datetime.now(timezone.utc).isoformat()
        })
        write_json(USERS_FILE, users)
        log_event("Student Account Created", "Authentication", "INFO", email)
        flash("Account created successfully. Please log in.", "success")
        return redirect("/login")

    content = r"""
<div class="auth"><div class="card">
<h1>Create Account</h1>
<p class="muted">Create your KOJA AFRICA student account.</p>
<form method="post">
<label>Name</label><input class="form-control" name="name" required>
<label>Email</label><input class="form-control" type="email" name="email" required>
<label>Password</label><input class="form-control" type="password" name="password" minlength="6" required>
<button class="btn" type="submit">Create Account</button>
</form>
</div></div>
"""
    return public_page("Create Account", content)


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = next(
            (u for u in read_json(USERS_FILE, []) if u.get("email") == email),
            None
        )

        if not user or not verify_password(password, user.get("password", "")):
            log_event("Failed Login", "Authentication", "WARNING", email)
            flash("Invalid email or password.", "error")
            return redirect("/login")

        session.clear()
        session["user_id"] = user["id"]
        session["role"] = user["role"]
        log_event("Login", "Authentication", "INFO", email)

        return redirect("/admin" if user["role"] == "admin" else "/student")

    content = r"""
<div class="auth"><div class="card">
<h1>Log In</h1>
<p class="muted">Access your KOJA AFRICA portal.</p>
<form method="post">
<label>Email</label><input class="form-control" type="email" name="email" required>
<label>Password</label><input class="form-control" type="password" name="password" required>
<button class="btn" type="submit">Log In</button>
</form>
</div></div>
"""
    return public_page("Log In", content)


@app.route("/logout")
def logout():
    if current_user():
        log_event("Logout", "Authentication", "INFO")
    session.clear()
    return redirect("/")


# ============================================================
# STUDENT DASHBOARD - SCREENSHOT STYLE
# ============================================================

@app.route("/student")
@login_required
def student_dashboard():
    user = current_user()

    if user["role"] == "admin":
        return redirect("/admin")

    questions = read_json(QUESTIONS_FILE, [])
    documents = read_json(DOCUMENTS_FILE, [])

    mine = [q for q in questions if q.get("student_id") == user["id"]]
    answered = sum(1 for q in mine if q.get("answer"))
    received = [
        d for d in documents
        if d.get("direction") == "admin_to_student"
        and d.get("recipient_id") == user["id"]
    ]
    sent = [
        d for d in documents
        if d.get("direction") == "student_to_admin"
        and d.get("sender_id") == user["id"]
    ]

    first = esc(user.get("name", "Student").split()[0])

    content = f"""
<section class="card hero">
<div class="greeting">☼ &nbsp; Good morning, {first}</div>
<h1>Welcome back<span>.</span></h1>
<p>Here is a quick overview of your dashboard. Manage your <strong>KOJA AFRICA</strong> portal activities and monitor your progress below.</p>

<div class="actions">
<a class="btn" href="/ask">▤ &nbsp; Ask Question</a>
<a class="btn2" href="/student/questions">□ &nbsp; My Questions</a>
<a class="btn green" href="/research">⌕ &nbsp; Research</a>
</div>

<div class="illustration">
<div class="clock"></div>
<div class="person"><div class="head"><i class="eye one"></i><i class="eye two"></i></div><div class="hair"></div></div>
<div class="laptop"></div>
<div class="plant"></div>
</div>

<div class="stats">
<div class="stat"><div class="stat-icon">?</div><h2>{len(mine)}</h2><p>My Questions<br>Total</p></div>
<div class="stat"><div class="stat-icon">✓</div><h2>{answered}</h2><p>Answered<br>Questions</p></div>
<div class="stat"><div class="stat-icon">▤</div><h2>{len(received)}</h2><p>Documents<br>Received</p></div>
<div class="stat"><div class="stat-icon">↑</div><h2>{len(sent)}</h2><p>Documents<br>Sent</p></div>
</div>
</section>

<div class="section-title"><h2>Quick Access</h2></div>
<section class="quick-grid">
<a class="quick" href="/ask"><div class="quick-icon">▤</div><h3>Ask Question</h3><p>Get academic answers</p></a>
<a class="quick" href="/student/questions"><div class="quick-icon">□</div><h3>My Questions</h3><p>Track your questions</p></a>
<a class="quick" href="/research"><div class="quick-icon">▥</div><h3>Research</h3><p>Explore answered questions</p></a>
<a class="quick" href="/student/documents"><div class="quick-icon">▱</div><h3>My Documents</h3><p>Upload and download files</p></a>
<a class="quick" href="/student/documents"><div class="quick-icon">♧</div><h3>Notifications</h3><p>Stay updated with KOJA</p></a>
<a class="quick" href="/student"><div class="quick-icon">♙</div><h3>My Profile</h3><p>{esc(user.get("name"))}</p></a>
</section>
"""
    return private_page("Student Dashboard", content)


# ============================================================
# ASK QUESTION
# ============================================================

@app.route("/ask", methods=["GET", "POST"])
@login_required
def ask_question():
    user = current_user()

    if user["role"] == "admin":
        return redirect("/admin")

    if request.method == "POST":
        text = request.form.get("question", "").strip()

        if not text:
            flash("Enter your question.", "error")
            return redirect("/ask")

        question = {
            "id": str(uuid.uuid4()),
            "student_id": user["id"],
            "student_name": user["name"],
            "question": text,
            "answer": "",
            "answer_by": "",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "answered_at": "",
            "attachments": [],
            "answer_attachments": []
        }

        file = request.files.get("document")
        if file and file.filename:
            try:
                question["attachments"].append(
                    save_file(file, STUDENT_UPLOAD_DIR)
                )
            except ValueError as exc:
                flash(str(exc), "error")
                return redirect("/ask")

        questions = read_json(QUESTIONS_FILE, [])
        questions.append(question)
        write_json(QUESTIONS_FILE, questions)
        log_event("Question Submitted", "Questions", "INFO", question["id"])
        flash("Your question has been submitted.", "success")
        return redirect("/student/questions")

    content = r"""
<div class="card">
<h1>Ask KOJA</h1>
<p class="muted">Submit an academic question to KOJA Administration.</p>
<form method="post" enctype="multipart/form-data">
<label>Question</label>
<textarea class="form-control" name="question" required></textarea>
<label>Optional supporting document</label>
<input class="form-control" type="file" name="document">
<p class="muted">PDF, Word, Excel, PowerPoint, text, images and CSV. Maximum 15 MB.</p>
<button class="btn" type="submit">Submit Question</button>
</form>
</div>
"""
    return private_page("Ask Question", content)


# ============================================================
# STUDENT QUESTIONS
# ============================================================

@app.route("/student/questions")
@login_required
def student_questions():
    user = current_user()
    questions = [
        q for q in read_json(QUESTIONS_FILE, [])
        if q.get("student_id") == user["id"]
    ]

    blocks = []

    for q in reversed(questions):
        status = "Answered" if q.get("answer") else "Pending"
        status_class = "answered" if q.get("answer") else "pending"

        attachments = ""
        for a in q.get("attachments", []):
            attachments += f"""
<div class="document-box">
<strong>Your supporting document</strong><br><br>
{esc(a.get("original_name"))}<br><br>
<a class="btn2" href="{url_for('student_question_file', question_id=q['id'], stored_name=a['stored_name'])}">Download</a>
</div>
"""

        answer = ""
        if q.get("answer"):
            answer = f"""
<h3>Answer</h3>
<div class="answer">{esc(q.get("answer"))}</div>
"""

        answer_files = ""
        for a in q.get("answer_attachments", []):
            answer_files += f"""
<div class="document-box">
<strong>Document from KOJA Administration</strong><br><br>
{esc(a.get("original_name"))}<br><br>
<a class="btn green" href="{url_for('student_answer_file', question_id=q['id'], stored_name=a['stored_name'])}">Download Document</a>
</div>
"""

        blocks.append(f"""
<div class="card">
<h2>{esc(q.get("question"))}</h2>
<p><span class="badge {status_class}">{status}</span></p>
{attachments}
{answer}
{answer_files}
</div>
""")

    content = """
<div class="card">
<h1>My Questions</h1>
<p class="muted">Only your questions and their answers are shown here.</p>
</div>
"""
    content += "".join(blocks) if blocks else '<div class="card empty">You have not submitted a question yet.</div>'

    return private_page("My Questions", content)


# ============================================================
# RESEARCH
# ============================================================

@app.route("/research")
@login_required
def research():
    query = request.args.get("q", "").strip().lower()

    results = [
        q for q in read_json(QUESTIONS_FILE, [])
        if q.get("answer")
    ]

    if query:
        results = [
            q for q in results
            if query in q.get("question", "").lower()
            or query in q.get("answer", "").lower()
        ]

    blocks = [
        f"""
<div class="card">
<h2>{esc(q.get("question"))}</h2>
<div class="answer">{esc(q.get("answer"))}</div>
</div>
"""
        for q in reversed(results)
    ]

    content = f"""
<div class="card">
<h1>Research</h1>
<p class="muted">Search answered academic questions and learning content.</p>
<form method="get">
<input class="form-control" name="q" value="{esc(request.args.get('q',''))}" placeholder="Search questions and answers">
<button class="btn" type="submit">Search</button>
</form>
</div>
"""
    content += "".join(blocks) if blocks else '<div class="card empty">No answered research results found.</div>'

    return private_page("Research", content)


# ============================================================
# STUDENT DOCUMENTS
# ============================================================

@app.route("/student/documents", methods=["GET", "POST"])
@login_required
def student_documents():
    user = current_user()

    if user["role"] == "admin":
        return redirect("/admin/documents")

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        file = request.files.get("document")

        if not title:
            flash("Enter a document title.", "error")
            return redirect("/student/documents")

        if not file or not file.filename:
            flash("Select a document.", "error")
            return redirect("/student/documents")

        try:
            saved = save_file(file, STUDENT_UPLOAD_DIR)
        except ValueError as exc:
            flash(str(exc), "error")
            return redirect("/student/documents")

        documents = read_json(DOCUMENTS_FILE, [])
        documents.append({
            "id": str(uuid.uuid4()),
            "direction": "student_to_admin",
            "sender_id": user["id"],
            "sender_name": user["name"],
            "recipient_id": "",
            "recipient_name": "KOJA Administration",
            "title": title,
            "description": description,
            "original_name": saved["original_name"],
            "stored_name": saved["stored_name"],
            "size": saved["size"],
            "created_at": datetime.now(timezone.utc).isoformat()
        })

        write_json(DOCUMENTS_FILE, documents)
        log_event("Student Document Submitted", "Documents", "INFO", saved["original_name"])
        flash("Your document has been sent to KOJA Administration.", "success")
        return redirect("/student/documents")

    documents = read_json(DOCUMENTS_FILE, [])

    sent = [
        d for d in documents
        if d.get("direction") == "student_to_admin"
        and d.get("sender_id") == user["id"]
    ]

    received = [
        d for d in documents
        if d.get("direction") == "admin_to_student"
        and d.get("recipient_id") == user["id"]
    ]

    received_rows = "".join(
        f"""
<tr>
<td>{esc(d.get("created_at",""))}</td>
<td><strong>{esc(d.get("title",""))}</strong></td>
<td>{esc(d.get("original_name",""))}<br><span class="muted">{size_text(d.get("size",0))}</span></td>
<td>{esc(d.get("description",""))}</td>
<td><a class="btn green" href="{url_for('student_document_download', document_id=d['id'])}">Download</a></td>
</tr>
"""
        for d in reversed(received)
    ) or '<tr><td colspan="5">No documents received yet.</td></tr>'

    sent_rows = "".join(
        f"""
<tr>
<td>{esc(d.get("created_at",""))}</td>
<td>{esc(d.get("title",""))}</td>
<td>{esc(d.get("original_name",""))}<br><span class="muted">{size_text(d.get("size",0))}</span></td>
<td>Sent to KOJA Administration</td>
</tr>
"""
        for d in reversed(sent)
    ) or '<tr><td colspan="4">You have not sent a document yet.</td></tr>'

    content = f"""
<div class="card">
<h1>My Documents</h1>
<p class="muted">Send documents to KOJA Administration and download documents sent specifically to you.</p>
</div>

<div class="card">
<h2>Send Document To KOJA Administration</h2>
<form method="post" enctype="multipart/form-data">
<label>Document Title</label>
<input class="form-control" name="title" required>
<label>Description</label>
<textarea class="form-control" name="description" style="min-height:120px"></textarea>
<label>Document</label>
<input class="form-control" type="file" name="document" required>
<button class="btn" type="submit">Send Document</button>
</form>
</div>

<div class="card">
<h2>Documents Received From KOJA</h2>
<div class="table-wrap"><table>
<tr><th>Date</th><th>Title</th><th>File</th><th>Description</th><th>Download</th></tr>
{received_rows}
</table></div>
</div>

<div class="card">
<h2>Documents I Sent</h2>
<div class="table-wrap"><table>
<tr><th>Date</th><th>Title</th><th>File</th><th>Status</th></tr>
{sent_rows}
</table></div>
</div>
"""
    return private_page("My Documents", content)


@app.route("/student/documents/download/<document_id>")
@login_required
def student_document_download(document_id):
    user = current_user()

    if user["role"] == "admin":
        return redirect("/admin/documents")

    document = next(
        (
            d for d in read_json(DOCUMENTS_FILE, [])
            if d.get("id") == document_id
            and d.get("direction") == "admin_to_student"
            and d.get("recipient_id") == user["id"]
        ),
        None
    )

    if not document:
        abort(403)

    filename = document.get("stored_name", "")
    path = os.path.join(ADMIN_UPLOAD_DIR, filename)

    if not filename or not os.path.isfile(path):
        abort(404)

    log_event("Student Document Downloaded", "Documents", "INFO", document.get("original_name", filename))
    return send_from_directory(ADMIN_UPLOAD_DIR, filename, as_attachment=True)


@app.route("/student/question-file/<question_id>/<stored_name>")
@login_required
def student_question_file(question_id, stored_name):
    user = current_user()

    question = next(
        (
            q for q in read_json(QUESTIONS_FILE, [])
            if q.get("id") == question_id
            and q.get("student_id") == user["id"]
        ),
        None
    )

    if not question:
        abort(403)

    if not any(
        a.get("stored_name") == stored_name
        for a in question.get("attachments", [])
    ):
        abort(404)

    path = os.path.join(STUDENT_UPLOAD_DIR, stored_name)

    if not os.path.isfile(path):
        abort(404)

    return send_from_directory(STUDENT_UPLOAD_DIR, stored_name, as_attachment=True)


@app.route("/student/answer-file/<question_id>/<stored_name>")
@login_required
def student_answer_file(question_id, stored_name):
    user = current_user()

    question = next(
        (
            q for q in read_json(QUESTIONS_FILE, [])
            if q.get("id") == question_id
            and q.get("student_id") == user["id"]
        ),
        None
    )

    if not question:
        abort(403)

    if not any(
        a.get("stored_name") == stored_name
        for a in question.get("answer_attachments", [])
    ):
        abort(404)

    path = os.path.join(ADMIN_UPLOAD_DIR, stored_name)

    if not os.path.isfile(path):
        abort(404)

    log_event("Student Answer Document Downloaded", "Documents", "INFO", stored_name)
    return send_from_directory(ADMIN_UPLOAD_DIR, stored_name, as_attachment=True)


# ============================================================
# ADMIN DASHBOARD
# ============================================================

@app.route("/admin")
@admin_required
def admin_dashboard():
    users = read_json(USERS_FILE, [])
    questions = read_json(QUESTIONS_FILE, [])
    documents = read_json(DOCUMENTS_FILE, [])

    student_list = [u for u in users if u.get("role") == "student"]
    answered = [q for q in questions if q.get("answer")]
    received = [d for d in documents if d.get("direction") == "student_to_admin"]

    content = f"""
<section class="card hero">
<div class="greeting">◉ &nbsp; Administration</div>
<h1>KOJA AFRICA<span>.</span></h1>
<p>Manage student questions, academic answers, documents and private system activity.</p>
<div class="actions">
<a class="btn" href="/admin/questions">▤ &nbsp; Questions</a>
<a class="btn2" href="/admin/documents">□ &nbsp; Documents</a>
<a class="btn green" href="/admin/answers">✓ &nbsp; Answers</a>
</div>
<div class="stats">
<div class="stat"><div class="stat-icon">♙</div><h2>{len(student_list)}</h2><p>Students</p></div>
<div class="stat"><div class="stat-icon">?</div><h2>{len(questions)}</h2><p>Questions</p></div>
<div class="stat"><div class="stat-icon">✓</div><h2>{len(answered)}</h2><p>Answered</p></div>
<div class="stat"><div class="stat-icon">□</div><h2>{len(received)}</h2><p>Student Documents</p></div>
</div>
</section>

<div class="section-title"><h2>Admin Quick Access</h2></div>
<section class="quick-grid">
<a class="quick" href="/admin/questions"><div class="quick-icon">?</div><h3>Questions</h3><p>Review and answer student questions.</p></a>
<a class="quick" href="/admin/answers"><div class="quick-icon">✓</div><h3>Answers</h3><p>Review completed academic answers.</p></a>
<a class="quick" href="/admin/documents"><div class="quick-icon">□</div><h3>Documents</h3><p>Receive and send student files.</p></a>
<a class="quick" href="/admin/logs"><div class="quick-icon">◌</div><h3>Logs</h3><p>Private administrator activity records.</p></a>
</section>
"""
    return private_page("Admin Dashboard", content)


@app.route("/admin/questions")
@admin_required
def admin_questions():
    blocks = []

    for q in reversed(read_json(QUESTIONS_FILE, [])):
        status = "Answered" if q.get("answer") else "Pending"
        cls = "answered" if q.get("answer") else "pending"

        files = ""
        for a in q.get("attachments", []):
            files += f"""
<div class="document-box">
<strong>Student Document</strong><br><br>
{esc(a.get("original_name"))}<br><br>
<a class="btn2" href="{url_for('admin_question_file', question_id=q['id'], stored_name=a['stored_name'])}">Download Student Document</a>
</div>
"""

        blocks.append(f"""
<div class="card">
<h2>{esc(q.get("question"))}</h2>
<p>Student: <strong>{esc(q.get("student_name"))}</strong></p>
<p><span class="badge {cls}">{status}</span></p>
{files}
<a class="btn" href="{url_for('admin_answer', question_id=q['id'])}">Answer Question</a>
</div>
""")

    content = '<div class="card"><h1>Questions</h1><p class="muted">Only administrators can see submitted student questions.</p></div>'
    content += "".join(blocks) if blocks else '<div class="card empty">No questions have been submitted.</div>'
    return private_page("Questions", content)


@app.route("/admin/answer/<question_id>", methods=["GET", "POST"])
@admin_required
def admin_answer(question_id):
    questions = read_json(QUESTIONS_FILE, [])
    question = next(
        (q for q in questions if q.get("id") == question_id),
        None
    )

    if not question:
        abort(404)

    if request.method == "POST":
        answer = request.form.get("answer", "").strip()

        if not answer:
            flash("Enter an answer.", "error")
            return redirect(url_for("admin_answer", question_id=question_id))

        question["answer"] = answer
        question["answer_by"] = current_user().get("name")
        question["answered_at"] = datetime.now(timezone.utc).isoformat()
        question.setdefault("answer_attachments", [])

        file = request.files.get("document")

        if file and file.filename:
            try:
                question["answer_attachments"].append(
                    save_file(file, ADMIN_UPLOAD_DIR)
                )
            except ValueError as exc:
                flash(str(exc), "error")
                return redirect(url_for("admin_answer", question_id=question_id))

        write_json(QUESTIONS_FILE, questions)
        log_event("Question Answered", "Answers", "INFO", question_id)
        flash("Answer saved successfully.", "success")
        return redirect("/admin/questions")

    existing = "".join(
        f'<div class="document-box">{esc(a.get("original_name"))}</div>'
        for a in question.get("answer_attachments", [])
    )

    content = f"""
<div class="card">
<h1>Answer Question</h1>
<p>Student: <strong>{esc(question.get("student_name"))}</strong></p>
<div class="question">{esc(question.get("question"))}</div>
{existing}
<form method="post" enctype="multipart/form-data">
<label>Answer</label>
<textarea class="form-control" name="answer" required>{esc(question.get("answer",""))}</textarea>
<label>Attach answer document</label>
<input class="form-control" type="file" name="document">
<button class="btn" type="submit">Save Answer</button>
</form>
</div>
"""
    return private_page("Answer Question", content)


@app.route("/admin/answers")
@admin_required
def admin_answers():
    answered = [
        q for q in read_json(QUESTIONS_FILE, [])
        if q.get("answer")
    ]

    blocks = [
        f"""
<div class="card">
<h2>{esc(q.get("question"))}</h2>
<div class="answer">{esc(q.get("answer"))}</div>
<p>Student: {esc(q.get("student_name"))}</p>
<p>Answered by: {esc(q.get("answer_by","Admin"))}</p>
</div>
"""
        for q in reversed(answered)
    ]

    content = '<div class="card"><h1>Answers</h1><p class="muted">This section is visible only to administrators.</p></div>'
    content += "".join(blocks) if blocks else '<div class="card empty">No answers yet.</div>'
    return private_page("Answers", content)


# ============================================================
# ADMIN DOCUMENTS
# ============================================================

@app.route("/admin/documents", methods=["GET", "POST"])
@admin_required
def admin_documents():
    admin = current_user()
    student_list = students()

    if request.method == "POST":
        student_id = request.form.get("student_id", "").strip()
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        file = request.files.get("document")
        student = get_user(student_id)

        if not student or student.get("role") != "student":
            flash("Please select a valid student.", "error")
            return redirect("/admin/documents")
        if not title:
            flash("Enter a document title.", "error")
            return redirect("/admin/documents")
        if not file or not file.filename:
            flash("Select a document.", "error")
            return redirect("/admin/documents")

        try:
            saved = save_file(file, ADMIN_UPLOAD_DIR)
        except ValueError as exc:
            flash(str(exc), "error")
            return redirect("/admin/documents")

        documents = read_json(DOCUMENTS_FILE, [])
        documents.append({
            "id": str(uuid.uuid4()),
            "direction": "admin_to_student",
            "sender_id": admin["id"],
            "sender_name": admin["name"],
            "recipient_id": student["id"],
            "recipient_name": student["name"],
            "title": title,
            "description": description,
            "original_name": saved["original_name"],
            "stored_name": saved["stored_name"],
            "size": saved["size"],
            "created_at": datetime.now(timezone.utc).isoformat()
        })

        write_json(DOCUMENTS_FILE, documents)
        log_event(
            "Document Sent To Student",
            "Documents",
            "INFO",
            f'{saved["original_name"]} -> {student["email"]}'
        )
        flash(f'Document sent to {student["name"]}.', "success")
        return redirect("/admin/documents")

    documents = read_json(DOCUMENTS_FILE, [])

    received = [
        d for d in documents
        if d.get("direction") == "student_to_admin"
    ]
    sent = [
        d for d in documents
        if d.get("direction") == "admin_to_student"
    ]

    options = "".join(
        f'<option value="{esc(s["id"])}">{esc(s["name"])} - {esc(s["email"])}</option>'
        for s in student_list
    )

    received_rows = "".join(
        f"""
<tr>
<td>{esc(d.get("created_at",""))}</td>
<td>{esc(d.get("sender_name","Student"))}</td>
<td>{esc(d.get("title",""))}</td>
<td>{esc(d.get("original_name",""))}<br><span class="muted">{size_text(d.get("size",0))}</span></td>
<td><a class="btn2" href="{url_for('admin_document_download', document_id=d['id'])}">Download</a></td>
</tr>
"""
        for d in reversed(received)
    ) or '<tr><td colspan="5">No documents received.</td></tr>'

    sent_rows = "".join(
        f"""
<tr>
<td>{esc(d.get("created_at",""))}</td>
<td>{esc(d.get("recipient_name",""))}</td>
<td>{esc(d.get("title",""))}</td>
<td>{esc(d.get("original_name",""))}</td>
<td><a class="btn2" href="{url_for('admin_document_download', document_id=d['id'])}">Download</a></td>
</tr>
"""
        for d in reversed(sent)
    ) or '<tr><td colspan="5">No documents sent.</td></tr>'

    content = f"""
<div class="card">
<h1>Documents</h1>
<p class="muted">Private administrator document management.</p>
</div>

<div class="card">
<h2>Send Document To Student</h2>
<form method="post" enctype="multipart/form-data">
<label>Student</label>
<select class="form-control" name="student_id" required>
<option value="">Select student</option>
{options}
</select>
<label>Document Title</label>
<input class="form-control" name="title" required>
<label>Description</label>
<textarea class="form-control" name="description" style="min-height:120px"></textarea>
<label>Document</label>
<input class="form-control" type="file" name="document" required>
<button class="btn" type="submit">Send Document</button>
</form>
</div>

<div class="card">
<h2>Documents Received From Students</h2>
<div class="table-wrap"><table>
<tr><th>Date</th><th>Student</th><th>Title</th><th>File</th><th>Download</th></tr>
{received_rows}
</table></div>
</div>

<div class="card">
<h2>Documents Sent To Students</h2>
<div class="table-wrap"><table>
<tr><th>Date</th><th>Student</th><th>Title</th><th>File</th><th>Download</th></tr>
{sent_rows}
</table></div>
</div>
"""
    return private_page("Documents", content)


@app.route("/admin/documents/download/<document_id>")
@admin_required
def admin_document_download(document_id):
    document = next(
        (
            d for d in read_json(DOCUMENTS_FILE, [])
            if d.get("id") == document_id
        ),
        None
    )

    if not document:
        abort(404)

    filename = document.get("stored_name", "")
    directory = (
        STUDENT_UPLOAD_DIR
        if document.get("direction") == "student_to_admin"
        else ADMIN_UPLOAD_DIR
    )
    path = os.path.join(directory, filename)

    if not filename or not os.path.isfile(path):
        abort(404)

    log_event("Admin Document Downloaded", "Documents", "INFO", document.get("original_name", filename))
    return send_from_directory(directory, filename, as_attachment=True)


@app.route("/admin/question-file/<question_id>/<stored_name>")
@admin_required
def admin_question_file(question_id, stored_name):
    question = next(
        (
            q for q in read_json(QUESTIONS_FILE, [])
            if q.get("id") == question_id
        ),
        None
    )

    if not question:
        abort(404)

    if not any(
        a.get("stored_name") == stored_name
        for a in question.get("attachments", [])
    ):
        abort(404)

    path = os.path.join(STUDENT_UPLOAD_DIR, stored_name)

    if not os.path.isfile(path):
        abort(404)

    log_event("Admin Student Attachment Downloaded", "Documents", "INFO", stored_name)
    return send_from_directory(STUDENT_UPLOAD_DIR, stored_name, as_attachment=True)


# ============================================================
# ADMIN LOGS
# ============================================================

@app.route("/admin/logs")
@admin_required
def admin_logs():
    logs = read_json(LOGS_FILE, [])

    rows = "".join(
        f"""
<tr>
<td>{esc(x.get("time",""))}</td>
<td>{esc(x.get("event",""))}</td>
<td>{esc(x.get("category",""))}</td>
<td>{esc(x.get("level",""))}</td>
<td>{esc(x.get("details",""))}</td>
</tr>
"""
        for x in reversed(logs[-500:])
    ) or '<tr><td colspan="5">No logs.</td></tr>'

    content = f"""
<div class="card">
<h1>System Logs</h1>
<p class="muted">Private administrator information. Students cannot access this page.</p>
<div class="table-wrap">
<table>
<tr><th>Time</th><th>Event</th><th>Category</th><th>Level</th><th>Details</th></tr>
{rows}
</table>
</div>
</div>
"""
    return private_page("Logs", content)


# ============================================================
# SECURITY / ERRORS
# ============================================================

@app.after_request
def security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

    if request.path.startswith(
        ("/admin", "/student", "/ask", "/research")
    ):
        response.headers["Cache-Control"] = (
            "no-store, no-cache, must-revalidate, private"
        )
        response.headers["Pragma"] = "no-cache"
        response.headers["X-Robots-Tag"] = "noindex,nofollow,noarchive"

    return response


@app.errorhandler(403)
def forbidden(error):
    return public_page(
        "Access Denied",
        '<div class="card"><h1>Access Denied</h1><p>You do not have permission to access this page.</p><a class="btn" href="/">Return Home</a></div>'
    ), 403


@app.errorhandler(404)
def not_found(error):
    return public_page(
        "Page Not Found",
        '<div class="card"><h1>Page Not Found</h1><p>The requested page does not exist.</p><a class="btn" href="/">Return Home</a></div>'
    ), 404


@app.route("/robots.txt")
def robots():
    response = make_response("""User-agent: *
Allow: /
Disallow: /admin
Disallow: /student
Disallow: /ask
Disallow: /research
Disallow: /logout
""")
    response.headers["Content-Type"] = "text/plain"
    return response


@app.route("/sitemap.xml")
def sitemap():
    base = request.url_root.rstrip("/")
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
<url><loc>{base}/</loc></url>
<url><loc>{base}/login</loc></url>
<url><loc>{base}/register</loc></url>
</urlset>"""
    response = make_response(xml)
    response.headers["Content-Type"] = "application/xml"
    return response


# ============================================================
# START
# ============================================================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "9999"))

    print("=" * 60)
    print("KOJA AFRICA - MODERN DASHBOARD")
    print("Knowledge • Questions • Answers")
    print(f"Server: http://0.0.0.0:{port}")
    print("=" * 60)

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False
    )
