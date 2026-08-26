import os
import json
import uuid
import hashlib
import secrets
import threading
from datetime import datetime, timezone
from functools import wraps

import requests

from flask import (
    Flask,
    request,
    redirect,
    url_for,
    session,
    render_template_string,
    flash,
    send_from_directory,
    abort,
    Response,
)

# ============================================================
# KOJA AFRICA
# Knowledge • Questions • Answers
#
# SINGLE-FILE FLASK PORTAL
#
# LOCAL-FIRST + OPTIONAL SUPABASE
# ============================================================

app = Flask(__name__)

# ============================================================
# SECURITY / APPLICATION
# ============================================================

app.secret_key = os.environ.get(
    "FLASK_SECRET_KEY",
    "CHANGE_THIS_SECRET_IN_PRODUCTION"
)

app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

if os.environ.get("FLASK_SECURE_COOKIE", "0") == "1":
    app.config["SESSION_COOKIE_SECURE"] = True

# ============================================================
# SITE CONFIGURATION
# ============================================================

SITE_URL = os.environ.get(
    "SITE_URL",
    "http://127.0.0.1:9999"
).rstrip("/")

SITE_NAME = "KOJA AFRICA"

SITE_DESCRIPTION = (
    "KOJA AFRICA is a knowledge, questions and answers "
    "platform for academic research, assignments, "
    "learning resources and educational questions."
)

GOOGLE_VERIFICATION = os.environ.get(
    "GOOGLE_VERIFICATION",
    ""
)

# ============================================================
# LOCAL STORAGE
# ============================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DATA_DIR = os.path.join(BASE_DIR, "koja_data")
UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")

STUDENT_UPLOAD_DIR = os.path.join(
    UPLOAD_DIR,
    "student"
)

ADMIN_UPLOAD_DIR = os.path.join(
    UPLOAD_DIR,
    "admin"
)

for directory in (
    DATA_DIR,
    UPLOAD_DIR,
    STUDENT_UPLOAD_DIR,
    ADMIN_UPLOAD_DIR,
):
    os.makedirs(directory, exist_ok=True)

USERS_FILE = os.path.join(
    DATA_DIR,
    "users.json"
)

QUESTIONS_FILE = os.path.join(
    DATA_DIR,
    "questions.json"
)

LOGS_FILE = os.path.join(
    DATA_DIR,
    "logs.json"
)

LOCK = threading.Lock()

# ============================================================
# ADMIN
# ============================================================

ADMIN_EMAIL = os.environ.get(
    "KOJA_ADMIN_EMAIL",
    "admin@koja.africa"
).strip().lower()

ADMIN_PASSWORD = os.environ.get(
    "KOJA_ADMIN_PASSWORD",
    "ChangeMe123!"
)

# ============================================================
# SUPABASE
# ============================================================

SUPABASE_URL = os.environ.get(
    "SUPABASE_URL",
    ""
).strip().rstrip("/")

SUPABASE_SERVICE_KEY = os.environ.get(
    "SUPABASE_SERVICE_KEY",
    ""
).strip()

STORAGE_BUCKET = os.environ.get(
    "KOJA_STORAGE_BUCKET",
    "koja-files"
).strip()

# ============================================================
# FILE TYPES
# ============================================================

ALLOWED_EXTENSIONS = {
    "pdf",
    "png",
    "jpg",
    "jpeg",
    "webp",
    "gif",
    "doc",
    "docx",
    "txt",
    "ppt",
    "pptx",
    "xls",
    "xlsx",
    "csv",
}

IMAGE_EXTENSIONS = {
    "png",
    "jpg",
    "jpeg",
    "webp",
    "gif",
}

# ============================================================
# BASIC HELPERS
# ============================================================

def now():
    return datetime.now(timezone.utc).isoformat()


def esc(value):
    from markupsafe import escape

    return str(
        escape(
            "" if value is None else value
        )
    )


def ensure_file(path, default):
    if not os.path.exists(path):
        with open(
            path,
            "w",
            encoding="utf-8"
        ) as file:
            json.dump(
                default,
                file,
                indent=2,
                ensure_ascii=False
            )


ensure_file(USERS_FILE, [])
ensure_file(QUESTIONS_FILE, [])
ensure_file(LOGS_FILE, [])


def read_json(path):
    try:
        with LOCK:
            with open(
                path,
                "r",
                encoding="utf-8"
            ) as file:
                value = json.load(file)

        return value if isinstance(value, list) else []

    except Exception:
        return []


def write_json(path, data):
    with LOCK:
        temporary = path + ".tmp"

        with open(
            temporary,
            "w",
            encoding="utf-8"
        ) as file:
            json.dump(
                data,
                file,
                indent=2,
                ensure_ascii=False
            )

        os.replace(
            temporary,
            path
        )

# ============================================================
# SUPABASE
# ============================================================

def supabase_configured():
    return bool(
        SUPABASE_URL
        and
        SUPABASE_SERVICE_KEY
    )


def supabase_headers(content_type=True):
    headers = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization":
            "Bearer " + SUPABASE_SERVICE_KEY,
    }

    if content_type:
        headers["Content-Type"] = (
            "application/json"
        )

    return headers


def supabase_request(
    method,
    endpoint,
    data=None,
    timeout=10
):
    if not supabase_configured():
        return None

    try:
        response = requests.request(
            method,
            SUPABASE_URL + endpoint,
            headers=supabase_headers(),
            json=data,
            timeout=timeout,
        )

        if response.status_code >= 400:
            return None

        if not response.text:
            return {}

        try:
            return response.json()
        except Exception:
            return {}

    except Exception:
        return None


def supabase_insert(table, row):
    return supabase_request(
        "POST",
        "/rest/v1/" + table,
        row
    )


def supabase_update(
    table,
    key,
    value,
    row
):
    return supabase_request(
        "PATCH",
        f"/rest/v1/{table}?{key}=eq.{value}",
        row
    )


def supabase_test():
    if not supabase_configured():
        return False

    try:
        response = requests.get(
            SUPABASE_URL + "/rest/v1/",
            headers=supabase_headers(False),
            timeout=5
        )

        return response.status_code < 400

    except Exception:
        return False

# ============================================================
# LOGGING
#
# Logs are stored locally but displayed only through
# administrator-protected routes.
# ============================================================

def client_ip():
    forwarded = request.headers.get(
        "X-Forwarded-For",
        ""
    )

    if forwarded:
        return (
            forwarded
            .split(",")[0]
            .strip()
        )

    return (
        request.remote_addr
        or
        "unknown"
    )


def log_event(
    action,
    category="System",
    level="INFO",
    details="",
    user_id=None,
    user_email=None,
):
    try:
        uid = (
            user_id
            or
            session.get("user_id")
            or
            "system"
        )

        email = (
            user_email
            or
            session.get("email")
            or
            "system"
        )

        entry = {
            "id": str(uuid.uuid4()),
            "created_at": now(),
            "level": level.upper(),
            "category": category,
            "user_id": str(uid),
            "user_email": str(email),
            "action": action,
            "details": str(details)[:2000],
            "ip_address": client_ip(),
            "user_agent": request.headers.get(
                "User-Agent",
                ""
            )[:1000],
        }

        local_logs = read_json(
            LOGS_FILE
        )

        local_logs.append(entry)

        if len(local_logs) > 5000:
            local_logs = local_logs[-5000:]

        write_json(
            LOGS_FILE,
            local_logs
        )

        if supabase_configured():
            supabase_insert(
                "koja_logs",
                entry
            )

    except Exception:
        pass


def logs():
    return read_json(LOGS_FILE)

# ============================================================
# PASSWORD SECURITY
# ============================================================

def hash_password(password):
    salt = secrets.token_hex(16)

    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        200000,
    )

    return salt + "$" + digest.hex()


def verify_password(
    password,
    stored
):
    try:
        salt, digest = stored.split(
            "$",
            1
        )

        check = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt.encode("utf-8"),
            200000,
        ).hex()

        return secrets.compare_digest(
            check,
            digest
        )

    except Exception:
        return False

# ============================================================
# USERS
# ============================================================

def users():
    return read_json(USERS_FILE)


def find_user(email):
    email = (
        email
        or
        ""
    ).strip().lower()

    for user in users():
        if (
            user.get("email", "")
            .strip()
            .lower()
            ==
            email
        ):
            return user

    return None


def create_admin():
    data = users()

    for user in data:
        if (
            user.get("email", "")
            .strip()
            .lower()
            ==
            ADMIN_EMAIL
        ):
            user["role"] = "admin"
            user["name"] = (
                "KOJA Administrator"
            )

            if not user.get("password"):
                user["password"] = (
                    hash_password(
                        ADMIN_PASSWORD
                    )
                )

            write_json(
                USERS_FILE,
                data
            )

            return

    data.append({
        "id": "ADMIN",
        "name": "KOJA Administrator",
        "email": ADMIN_EMAIL,
        "password": hash_password(
            ADMIN_PASSWORD
        ),
        "role": "admin",
        "created_at": now(),
    })

    write_json(
        USERS_FILE,
        data
    )


create_admin()

# ============================================================
# QUESTIONS
# ============================================================

def questions():
    return read_json(
        QUESTIONS_FILE
    )


def save_questions(data):
    write_json(
        QUESTIONS_FILE,
        data
    )


def find_question(question_id):
    for question in questions():
        if (
            str(question.get("id"))
            ==
            str(question_id)
        ):
            return question

    return None


def sync_question(question):
    if not supabase_configured():
        return False

    row = {
        "id": question["id"],
        "student_id": question["student_id"],
        "student_name": question["student_name"],
        "student_email": question["student_email"],
        "subject": question["subject"],
        "question": question["question"],
        "status": question["status"],
        "answer": question.get(
            "answer",
            ""
        ),
        "created_at": question[
            "created_at"
        ],
        "answered_at": question.get(
            "answered_at"
        ),
    }

    try:
        result = supabase_insert(
            "koja_questions",
            row
        )

        return bool(result)

    except Exception:
        return False

# ============================================================
# AUTH
# ============================================================

def login_required(fn):

    @wraps(fn)
    def wrapper(*args, **kwargs):

        if not session.get(
            "user_id"
        ):
            flash(
                "Please log in first.",
                "error"
            )

            return redirect(
                url_for("login")
            )

        return fn(
            *args,
            **kwargs
        )

    return wrapper


def is_admin_session():
    return (
        session.get("role")
        ==
        "admin"
        and
        session.get("email", "")
        .strip()
        .lower()
        ==
        ADMIN_EMAIL
    )


def admin_required(fn):

    @wraps(fn)
    def wrapper(*args, **kwargs):

        if not session.get(
            "user_id"
        ):
            return redirect(
                url_for("login")
            )

        if not is_admin_session():

            log_event(
                "Unauthorized Admin Access",
                "Security",
                "WARNING",
                request.path,
            )

            flash(
                "Administrator access required.",
                "error"
            )

            return redirect(
                url_for("student_dashboard")
            )

        return fn(
            *args,
            **kwargs
        )

    return wrapper

# ============================================================
# FILE HELPERS
# ============================================================

def extension_of(filename):
    filename = (
        filename
        or
        ""
    ).strip()

    if "." not in filename:
        return ""

    return filename.rsplit(
        ".",
        1
    )[1].lower()


def allowed_file(filename):
    return (
        extension_of(filename)
        in
        ALLOWED_EXTENSIONS
    )


def safe_storage_name(filename):
    extension = extension_of(
        filename
    )

    if not extension:
        return str(uuid.uuid4())

    return (
        str(uuid.uuid4())
        +
        "."
        +
        extension
    )


def upload_to_supabase(
    local_path,
    storage_path,
    content_type
):
    if not supabase_configured():
        return False

    try:
        with open(
            local_path,
            "rb"
        ) as file:

            response = requests.post(
                (
                    f"{SUPABASE_URL}"
                    f"/storage/v1/object/"
                    f"{STORAGE_BUCKET}/"
                    f"{storage_path}"
                ),
                headers={
                    "apikey":
                        SUPABASE_SERVICE_KEY,
                    "Authorization":
                        "Bearer "
                        +
                        SUPABASE_SERVICE_KEY,
                    "Content-Type":
                        content_type,
                    "x-upsert":
                        "false",
                },
                data=file,
                timeout=30,
            )

        return response.status_code in (
            200,
            201
        )

    except Exception:
        return False


def save_upload(
    file,
    category,
    question_id=None
):
    if not file:
        return None

    if not file.filename:
        return None

    original = file.filename.strip()

    if not allowed_file(original):

        log_event(
            "Upload Failed",
            "Storage",
            "ERROR",
            "Invalid file type: " + original,
        )

        return None

    extension = extension_of(
        original
    )

    stored = safe_storage_name(
        original
    )

    if category == "student":
        directory = STUDENT_UPLOAD_DIR

    elif category == "admin":
        directory = ADMIN_UPLOAD_DIR

    else:
        return None

    destination = os.path.join(
        directory,
        stored
    )

    try:
        file.save(destination)

    except Exception as exc:

        log_event(
            "Upload Failed",
            "Storage",
            "ERROR",
            str(exc),
        )

        return None

    storage_path = (
        f"{category}/"
        f"{question_id or 'general'}/"
        f"{stored}"
    )

    uploaded = upload_to_supabase(
        destination,
        storage_path,
        file.mimetype
        or
        "application/octet-stream"
    )

    log_event(
        "File Uploaded"
        if uploaded
        else
        "File Saved Locally",
        "Storage",
        "SUCCESS"
        if uploaded
        else
        "INFO",
        original,
    )

    return {
        "id": str(uuid.uuid4()),
        "original_name": original,
        "stored_name": stored,
        "category": category,
        "extension": extension,
        "is_image":
            extension in IMAGE_EXTENSIONS,
        "storage_path": storage_path,
        "supabase_uploaded": uploaded,
    }


def save_multiple_uploads(
    files,
    category,
    question_id=None
):
    result = []

    for file in files:
        saved = save_upload(
            file,
            category,
            question_id
        )

        if saved:
            result.append(saved)

    return result


def attachment_html(
    attachments,
    viewer,
    question_id=None
):
    if not attachments:
        return (
            '<p class="muted">'
            'No attachments.'
            '</p>'
        )

    output = ""

    for attachment in attachments:

        stored = attachment.get(
            "stored_name",
            ""
        )

        if not stored:
            continue

        name = esc(
            attachment.get(
                "original_name",
                "Attachment"
            )
        )

        category = attachment.get(
            "category",
            "student"
        )

        if viewer == "admin":

            route = url_for(
                "admin_file",
                category=category,
                filename=stored,
            )

        else:

            route = url_for(
                "student_file",
                question_id=question_id,
                category=category,
                filename=stored,
            )

        preview = ""

        if attachment.get(
            "is_image"
        ):

            preview = (
                f'<img '
                f'class="attachment-image" '
                f'src="{route}" '
                f'alt="Uploaded file">'
            )

        output += f"""
        <div class="attachment">
            <strong>📎 {name}</strong>
            {preview}
            <br>
            <a
                class="btn small"
                href="{route}"
                target="_blank"
            >
                Open File
            </a>
        </div>
        """

    return output

# ============================================================
# MAIN HTML
# ============================================================

HTML = r"""
<!DOCTYPE html>
<html lang="en">

<head>

<meta charset="UTF-8">

<meta
    name="viewport"
    content="width=device-width, initial-scale=1"
>

<meta
    name="theme-color"
    content="#101828"
>

<meta
    name="description"
    content="{{ site_description }}"
>

<meta
    name="robots"
    content="index, follow"
>

{% if google_verification %}
<meta
    name="google-site-verification"
    content="{{ google_verification }}"
>
{% endif %}

<link
    rel="canonical"
    href="{{ canonical_url }}"
>

<title>{{ title }} - KOJA AFRICA</title>

<style>

* {
    box-sizing: border-box;
}

html,
body {
    margin: 0;
    padding: 0;
    width: 100%;
    min-height: 100%;
    font-family:
        Arial,
        Helvetica,
        sans-serif;
    background: #f5f7fa;
    color: #101828;
}

body {
    overflow-x: hidden;
}

a {
    color: inherit;
}

button,
input,
textarea,
select {
    font: inherit;
}

button,
.btn {
    display: inline-block;
    border: 0;
    border-radius: 10px;
    padding: 12px 18px;
    background: #101828;
    color: white;
    text-decoration: none;
    cursor: pointer;
    margin: 4px;
}

button:hover,
.btn:hover {
    opacity: .9;
}

.btn.green {
    background: #087443;
}

.btn.purple {
    background: #6941c6;
}

.btn.small {
    padding: 8px 12px;
    font-size: 14px;
}

.container {
    width: 100%;
    max-width: 1400px;
    margin: 0 auto;
    padding: 18px;
}

.topbar {
    width: 100%;
    background: #101828;
    color: white;
}

.topbar-inner {
    width: 100%;
    max-width: 1400px;
    margin: auto;
    min-height: 64px;
    padding: 10px 18px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 15px;
}

.logo {
    font-size: 22px;
    font-weight: 900;
    white-space: nowrap;
}

.logo .k {
    color: #2563eb;
}

.logo .o {
    color: #16a34a;
}

.logo .j {
    color: #dc2626;
}

.logo .a {
    color: #1d4ed8;
}

.navlinks {
    display: flex;
    flex-wrap: wrap;
    justify-content: flex-end;
    gap: 6px;
}

.navlinks a {
    text-decoration: none;
    padding: 8px 10px;
    border-radius: 8px;
    font-size: 14px;
}

.navlinks a:hover {
    background: rgba(255,255,255,.12);
}

main {
    width: 100%;
}

.hero {
    width: 100%;
    padding: 50px 25px;
    background: white;
    border-radius: 16px;
    margin-bottom: 20px;
}

.hero h1 {
    margin-top: 0;
    font-size: clamp(30px, 6vw, 58px);
}

.hero p {
    max-width: 800px;
    line-height: 1.7;
    font-size: 17px;
}

.card {
    background: white;
    border-radius: 14px;
    padding: 24px;
    margin-bottom: 18px;
    width: 100%;
}

.grid {
    width: 100%;
    display: grid;
    grid-template-columns:
        repeat(
            auto-fit,
            minmax(240px, 1fr)
        );
    gap: 18px;
    margin-bottom: 20px;
}

.stat {
    background: white;
    border-radius: 14px;
    padding: 25px;
}

.stat h2 {
    font-size: 35px;
    margin: 0 0 5px;
}

.search-box {
    display: flex;
    width: 100%;
    gap: 8px;
}

.search-box input {
    flex: 1;
}

input,
textarea,
select {
    width: 100%;
    padding: 13px;
    margin: 6px 0 16px;
    border: 1px solid #d0d5dd;
    border-radius: 9px;
    background: white;
}

textarea {
    min-height: 180px;
    resize: vertical;
}

label {
    font-weight: 700;
}

.question,
.answer {
    white-space: pre-wrap;
    line-height: 1.75;
    padding: 18px;
    border-radius: 10px;
    background: #f8fafc;
}

.answer {
    background: #f0fdf4;
}

.subject {
    display: inline-block;
    padding: 5px 10px;
    border-radius: 999px;
    background: #e0e7ff;
    font-weight: 700;
    font-size: 13px;
}

.badge {
    display: inline-block;
    padding: 5px 10px;
    border-radius: 999px;
    font-size: 13px;
    font-weight: 700;
}

.badge.answered {
    background: #dcfce7;
    color: #166534;
}

.badge.pending {
    background: #fef3c7;
    color: #92400e;
}

.muted {
    color: #667085;
}

.alert {
    padding: 13px 16px;
    margin-bottom: 15px;
    border-radius: 9px;
}

.alert.success {
    background: #dcfce7;
    color: #166534;
}

.alert.error {
    background: #fee2e2;
    color: #991b1b;
}

table {
    width: 100%;
    border-collapse: collapse;
    min-width: 800px;
}

th,
td {
    text-align: left;
    padding: 12px;
    border-bottom: 1px solid #eaecf0;
    vertical-align: top;
}

.live {
    display: inline-block;
    padding: 8px 12px;
    background: #ecfdf3;
    color: #027a48;
    border-radius: 999px;
    font-weight: 700;
}

.attachment {
    border: 1px solid #eaecf0;
    padding: 14px;
    border-radius: 10px;
    margin: 10px 0;
}

.attachment-image {
    display: block;
    max-width: 100%;
    max-height: 350px;
    margin: 12px 0;
    border-radius: 8px;
}

footer {
    width: 100%;
    padding: 35px 18px;
    text-align: center;
    color: #667085;
}

.auth {
    max-width: 600px;
    margin: 30px auto;
}

.empty {
    text-align: center;
}

/* =========================================================
   OPENING ANIMATION
   ========================================================= */

#koja-opening {
    position: fixed;
    inset: 0;
    width: 100vw;
    height: 100vh;
    z-index: 999999;
    background: #101828;
    display: flex;
    align-items: center;
    justify-content: center;
    overflow: hidden;
    animation:
        openingExit .65s ease 3.4s forwards;
}

.opening-inner {
    width: 100%;
    text-align: center;
    padding: 20px;
}

.opening-logo {
    font-size: clamp(60px, 17vw, 150px);
    font-weight: 1000;
    letter-spacing: 2px;
    line-height: 1;
    animation:
        logoEntrance 1.1s ease forwards;
}

.opening-logo span:nth-child(1) {
    color: #2563eb;
}

.opening-logo span:nth-child(2) {
    color: #16a34a;
}

.opening-logo span:nth-child(3) {
    color: #dc2626;
}

.opening-logo span:nth-child(4) {
    color: #1d4ed8;
}

.opening-title {
    color: white;
    font-size: clamp(20px, 5vw, 38px);
    margin-top: 18px;
    opacity: 0;
    animation:
        fadeIn .8s ease 1s forwards;
}

.opening-line {
    height: 3px;
    width: 0;
    margin: 20px auto;
    background: white;
    animation:
        lineGrow 1s ease 1.2s forwards;
}

.opening-status {
    color: #d0d5dd;
    opacity: 0;
    animation:
        fadeIn .8s ease 1.8s forwards;
}

@keyframes logoEntrance {

    0% {
        opacity: 0;
        transform:
            scale(.45)
            translateY(35px);
    }

    60% {
        opacity: 1;
        transform:
            scale(1.08)
            translateY(0);
    }

    100% {
        opacity: 1;
        transform:
            scale(1)
            translateY(0);
    }
}

@keyframes lineGrow {

    from {
        width: 0;
    }

    to {
        width: min(420px, 70vw);
    }
}

@keyframes fadeIn {

    from {
        opacity: 0;
    }

    to {
        opacity: 1;
    }
}

@keyframes openingExit {

    to {
        opacity: 0;
        visibility: hidden;
        pointer-events: none;
    }
}

/*
The opening animation is only created on the first page
request of the browser session.
*/

@media (max-width: 700px) {

    .topbar-inner {
        align-items: flex-start;
        flex-direction: column;
    }

    .navlinks {
        width: 100%;
        justify-content: flex-start;
    }

    .hero {
        padding: 30px 18px;
    }

    .search-box {
        flex-direction: column;
    }

    .search-box button {
        width: 100%;
    }

    .container {
        padding: 12px;
    }

}

</style>

</head>

<body>

{% if show_opening %}

<div id="koja-opening">

    <div class="opening-inner">

        <div class="opening-logo">
            <span>K</span>
            <span>O</span>
            <span>J</span>
            <span>A</span>
        </div>

        <div class="opening-title">
            KOJA AFRICA
        </div>

        <div class="opening-line"></div>

        <div class="opening-status">
            Knowledge • Questions • Answers
        </div>

    </div>

</div>

{% endif %}

<header class="topbar">

    <div class="topbar-inner">

        <div class="logo">
            <span class="k">k</span><span class="o">o</span><span class="j">j</span><span class="a">a</span>
            AFRICA
        </div>

        <nav class="navlinks">

            <a href="/">
                Home
            </a>

            <a href="/research">
                Research
            </a>

            {% if session.get("user_id") %}

                {% if session.get("role") == "admin" %}

                    <a href="/admin">
                        Dashboard
                    </a>

                    <a href="/admin/questions">
                        Questions
                    </a>

                    <a href="/admin/answers">
                        Answers
                    </a>

                    <a href="/admin/logs">
                        Logs
                    </a>

                    <a href="/admin/config">
                        Config
                    </a>

                {% else %}

                    <a href="/student">
                        My Dashboard
                    </a>

                    <a href="/student/ask">
                        Ask
                    </a>

                {% endif %}

                <a href="/logout">
                    Logout
                </a>

            {% else %}

                <a href="/login">
                    Login
                </a>

                <a href="/register">
                    Create Account
                </a>

            {% endif %}

        </nav>

    </div>

</header>

<main>

<div class="container">

{% with messages = get_flashed_messages(
    with_categories=true
) %}

    {% for category, message in messages %}

        <div class="alert {{ category }}">
            {{ message }}
        </div>

    {% endfor %}

{% endwith %}

{{ content|safe }}

</div>

</main>

<footer>

    <strong>KOJA AFRICA</strong>

    <br>

    Knowledge • Questions • Answers

    <br><br>

    Academic Research • Learning • Questions

    <br><br>

    <a href="/research">
        Research
    </a>

    &nbsp; | &nbsp;

    <a href="/about">
        About
    </a>

</footer>

</body>

</html>
"""

# ============================================================
# PAGE RENDERER
# ============================================================

def render_page(
    title,
    content,
    canonical=None,
    show_opening=False
):

    return render_template_string(
        HTML,
        title=title,
        content=content,
        canonical_url=(
            canonical
            or
            SITE_URL
        ),
        site_description=SITE_DESCRIPTION,
        google_verification=GOOGLE_VERIFICATION,
        show_opening=show_opening,
    )

# ============================================================
# OPENING / HOME
#
# Animation is shown only on the root page.
# Therefore navigating to another page does not replay it.
# ============================================================

@app.route("/")
def home():

    content = """
    <section class="hero">

        <h1>
            How KOJA AFRICA Works
        </h1>

        <p>
            KOJA AFRICA is a knowledge,
            questions and answers platform
            designed for academic learning,
            research and educational support.
        </p>

        <div class="grid">

            <div class="card">
                <h2>
                    1. Create an Account
                </h2>

                <p>
                    Students create a personal
                    KOJA AFRICA account.
                </p>

                <a
                    class="btn"
                    href="/register"
                >
                    Create Account
                </a>
            </div>

            <div class="card">
                <h2>
                    2. Ask a Question
                </h2>

                <p>
                    Submit an academic question
                    and, when necessary, upload
                    supporting documents.
                </p>

                <a
                    class="btn"
                    href="/login"
                >
                    Login to Ask
                </a>
            </div>

            <div class="card">
                <h2>
                    3. KOJA Reviews It
                </h2>

                <p>
                    Submitted questions are handled
                    through the protected administrator
                    workspace.
                </p>
            </div>

            <div class="card">
                <h2>
                    4. Receive an Answer
                </h2>

                <p>
                    The administrator can provide
                    an academic answer and supporting
                    files.
                </p>
            </div>

            <div class="card">
                <h2>
                    5. Research
                </h2>

                <p>
                    Published answered questions
                    can become part of the public
                    KOJA research collection.
                </p>

                <a
                    class="btn"
                    href="/research"
                >
                    Research
                </a>
            </div>

        </div>

        <div style="margin-top:20px">

            <a
                class="btn"
                href="/login"
            >
                Login
            </a>

            <a
                class="btn green"
                href="/register"
            >
                Create Account
            </a>

        </div>

    </section>
    """

    return render_page(
        "Home",
        content,
        SITE_URL + "/",
        show_opening=True
    )

# ============================================================
# RESEARCH
#
# Only answered questions are public.
# Pending questions never appear here.
# ============================================================

@app.route("/research")
def research():

    query = request.args.get(
        "q",
        ""
    ).strip()

    public_questions = [
        q
        for q in questions()
        if q.get("status")
        ==
        "Answered"
    ]

    if query:

        terms = [
            word.lower()
            for word in query.split()
            if len(word) > 1
        ]

        def matches(q):

            haystack = " ".join([
                str(q.get(
                    "subject",
                    ""
                )),
                str(q.get(
                    "question",
                    ""
                )),
                str(q.get(
                    "answer",
                    ""
                )),
            ]).lower()

            return all(
                term in haystack
                for term in terms
            )

        public_questions = [
            q
            for q in public_questions
            if matches(q)
        ]

        log_event(
            "Public Research Search",
            "Research",
            "INFO",
            query,
        )

    public_questions.sort(
        key=lambda q:
            q.get(
                "answered_at",
                ""
            ),
        reverse=True
    )

    cards = ""

    for q in public_questions:

        question_text = q.get(
            "question",
            ""
        )

        answer_text = q.get(
            "answer",
            ""
        )

        preview = answer_text[:350]

        if len(answer_text) > 350:
            preview += "..."

        cards += f"""
        <div class="card">

            <span class="subject">
                {esc(q.get("subject"))}
            </span>

            <h2>
                <a
                    href="/question/{esc(q.get('id'))}"
                >
                    {esc(question_text)}
                </a>
            </h2>

            <p class="muted">
                Published:
                {esc(q.get("answered_at"))}
            </p>

            <div class="answer">
                {esc(preview)}
            </div>

            <br>

            <a
                class="btn small"
                href="/question/{esc(q.get('id'))}"
            >
                Read Full Answer
            </a>

        </div>
        """

    if not cards:

        cards = """
        <div class="card empty">

            <h2>
                No research results found.
            </h2>

            <p>
                Search for an academic topic
                or question.
            </p>

            <a
                class="btn"
                href="/login"
            >
                Login
            </a>

        </div>
        """

    content = f"""

    <div class="hero">

        <h1>
            KOJA AFRICA Research
        </h1>

        <p>
            Search publicly available
            academic questions and answers.
        </p>

        <form
            action="/research"
            method="get"
        >

            <div class="search-box">

                <input
                    type="search"
                    name="q"
                    value="{esc(query)}"
                    placeholder="Search KOJA AFRICA..."
                >

                <button type="submit">
                    Search
                </button>

            </div>

        </form>

    </div>

    <h2>
        {"Search Results" if query else "Research"}
    </h2>

    {cards}

    """

    return render_page(
        "Research",
        content,
        SITE_URL + "/research"
    )

# ============================================================
# PUBLIC ANSWERED QUESTION
# ============================================================

@app.route(
    "/question/<question_id>"
)
def public_question(question_id):

    question = find_question(
        question_id
    )

    if not question:
        return (
            render_page(
                "Question Not Found",
                """
                <div class="card">

                    <h1>
                        Question Not Found
                    </h1>

                    <a
                        class="btn"
                        href="/research"
                    >
                        Research
                    </a>

                </div>
                """
            ),
            404
        )

    if question.get(
        "status"
    ) != "Answered":

        return (
            render_page(
                "Research Question",
                """
                <div class="card">

                    <h1>
                        Research Question
                    </h1>

                    <p>
                        This question has not
                        been publicly answered.
                    </p>

                    <a
                        class="btn"
                        href="/research"
                    >
                        Back to Research
                    </a>

                </div>
                """
            ),
            404
        )

    log_event(
        "Public Research Viewed",
        "Research",
        "INFO",
        question_id
    )

    content = f"""

    <div class="card">

        <span class="subject">
            {esc(question.get("subject"))}
        </span>

        <h1>
            {esc(question.get("question"))}
        </h1>

        <p class="muted">
            Published:
            {esc(question.get("answered_at"))}
        </p>

    </div>

    <div class="card">

        <h2>
            Academic Answer
        </h2>

        <div class="answer">
            {esc(question.get("answer"))}
        </div>

    </div>

    <div class="card">

        <h2>
            Research More
        </h2>

        <a
            class="btn"
            href="/research?q={esc(question.get("subject"))}"
        >
            Related Research
        </a>

    </div>

    """

    return render_page(
        question.get(
            "subject",
            "Research"
        ),
        content,
        SITE_URL
        +
        "/question/"
        +
        str(question_id)
    )

# ============================================================
# ABOUT
# ============================================================

@app.route("/about")
def about():

    content = """

    <div class="card">

        <h1>
            About KOJA AFRICA
        </h1>

        <p>
            KOJA AFRICA means
            Knowledge • Questions • Answers.
        </p>

        <p>
            The platform provides a structured
            environment where students can submit
            academic questions while administrators
            manage answers and learning resources.
        </p>

        <p>
            Only answers that have been processed
            and published become part of the public
            research area.
        </p>

    </div>

    """

    return render_page(
        "About",
        content,
        SITE_URL + "/about"
    )

# ============================================================
# ROBOTS
# ============================================================

@app.route("/robots.txt")
def robots():

    text = f"""User-agent: *
Allow: /
Disallow: /admin
Disallow: /student
Disallow: /login
Disallow: /register
Disallow: /logout

Sitemap: {SITE_URL}/sitemap.xml
"""

    return Response(
        text,
        mimetype="text/plain"
    )

# ============================================================
# SITEMAP
# ============================================================

@app.route("/sitemap.xml")
def sitemap():

    public_urls = [
        SITE_URL + "/",
        SITE_URL + "/research",
        SITE_URL + "/about",
    ]

    for question in questions():

        if question.get(
            "status"
        ) == "Answered":

            public_urls.append(
                SITE_URL
                +
                "/question/"
                +
                str(question.get("id"))
            )

    urls = ""

    for item in public_urls:

        urls += (
            "<url>"
            "<loc>"
            +
            esc(item)
            +
            "</loc>"
            "</url>"
        )

    xml = (
        '<?xml version="1.0" '
        'encoding="UTF-8"?>'
        '<urlset '
        'xmlns="http://www.sitemaps.org/'
        'schemas/sitemap/0.9">'
        +
        urls
        +
        "</urlset>"
    )

    return Response(
        xml,
        mimetype="application/xml"
    )

# ============================================================
# GOOGLE VERIFICATION
# ============================================================

@app.route(
    "/google4d3d8178b7b4659e.html"
)
def google_verification():

    return (
        "google-site-verification: "
        "google4d3d8178b7b4659e.html"
    )

# ============================================================
# LOGIN
# ============================================================

@app.route(
    "/login",
    methods=["GET", "POST"]
)
def login():

    if request.method == "POST":

        email = (
            request.form.get(
                "email",
                ""
            )
            .strip()
            .lower()
        )

        password = request.form.get(
            "password",
            ""
        )

        # ADMIN
        if (
            email == ADMIN_EMAIL
            and
            secrets.compare_digest(
                password,
                ADMIN_PASSWORD
            )
        ):

            session.clear()

            session["user_id"] = "ADMIN"
            session["email"] = ADMIN_EMAIL
            session["name"] = (
                "KOJA Administrator"
            )
            session["role"] = "admin"

            log_event(
                "Admin Login",
                "Auth",
                "SUCCESS",
                "Administrator logged in"
            )

            return redirect(
                url_for(
                    "admin_dashboard"
                )
            )

        # STUDENT
        user = find_user(
            email
        )

        if (
            not user
            or
            not verify_password(
                password,
                user.get(
                    "password",
                    ""
                )
            )
        ):

            log_event(
                "Failed Login",
                "Auth",
                "WARNING",
                "Invalid credentials",
                user_email=email,
            )

            flash(
                "Invalid email or password.",
                "error"
            )

            return redirect(
                url_for("login")
            )

        session.clear()

        session["user_id"] = user["id"]
        session["email"] = user["email"]
        session["name"] = user["name"]
        session["role"] = "student"

        log_event(
            "Student Login",
            "Auth",
            "SUCCESS",
            "Student logged in"
        )

        return redirect(
            url_for(
                "student_dashboard"
            )
        )

    content = """

    <div class="auth card">

        <h1>
            Login
        </h1>

        <p class="muted">
            Access your KOJA AFRICA account.
        </p>

        <form method="post">

            <label>
                Email
            </label>

            <input
                type="email"
                name="email"
                required
            >

            <label>
                Password
            </label>

            <input
                type="password"
                name="password"
                required
            >

            <button type="submit">
                Login
            </button>

        </form>

        <p>
            Do not have an account?
            <a href="/register">
                Create Account
            </a>
        </p>

    </div>

    """

    return render_page(
        "Login",
        content,
        SITE_URL + "/login"
    )

# ============================================================
# REGISTER
# ============================================================

@app.route(
    "/register",
    methods=["GET", "POST"]
)
def register():

    if request.method == "POST":

        name = (
            request.form.get(
                "name",
                ""
            ).strip()
        )

        email = (
            request.form.get(
                "email",
                ""
            )
            .strip()
            .lower()
        )

        password = request.form.get(
            "password",
            ""
        )

        confirm = request.form.get(
            "confirm",
            ""
        )

        if len(name) < 2:

            flash(
                "Enter your full name.",
                "error"
            )

            return redirect(
                url_for("register")
            )

        if email == ADMIN_EMAIL:

            flash(
                "That email is reserved.",
                "error"
            )

            return redirect(
                url_for("register")
            )

        if len(password) < 6:

            flash(
                "Password must contain at least 6 characters.",
                "error"
            )

            return redirect(
                url_for("register")
            )

        if password != confirm:

            flash(
                "Passwords do not match.",
                "error"
            )

            return redirect(
                url_for("register")
            )

        if find_user(email):

            flash(
                "An account with this email already exists.",
                "error"
            )

            return redirect(
                url_for("register")
            )

        user = {
            "id": str(uuid.uuid4()),
            "name": name,
            "email": email,
            "password": hash_password(
                password
            ),
            "role": "student",
            "created_at": now(),
        }

        data = users()

        data.append(user)

        write_json(
            USERS_FILE,
            data
        )

        if supabase_configured():

            supabase_insert(
                "koja_users",
                {
                    "id": user["id"],
                    "name": name,
                    "email": email,
                    "role": "student",
                    "created_at":
                        user["created_at"],
                }
            )

        log_event(
            "User Registered",
            "Auth",
            "SUCCESS",
            "New student account created",
            user_id=user["id"],
            user_email=email,
        )

        flash(
            "Account created successfully.",
            "success"
        )

        return redirect(
            url_for("login")
        )

    content = """

    <div class="auth card">

        <h1>
            Create Student Account
        </h1>

        <form method="post">

            <label>
                Full Name
            </label>

            <input
                name="name"
                required
            >

            <label>
                Email
            </label>

            <input
                type="email"
                name="email"
                required
            >

            <label>
                Password
            </label>

            <input
                type="password"
                name="password"
                minlength="6"
                required
            >

            <label>
                Confirm Password
            </label>

            <input
                type="password"
                name="confirm"
                minlength="6"
                required
            >

            <button type="submit">
                Create Account
            </button>

        </form>

        <p>
            Already registered?
            <a href="/login">
                Login
            </a>
        </p>

    </div>

    """

    return render_page(
        "Register",
        content,
        SITE_URL + "/register"
    )

# ============================================================
# LOGOUT
# ============================================================

@app.route("/logout")
def logout():

    if session.get("user_id"):

        log_event(
            "User Logout",
            "Auth",
            "INFO",
            "Session ended"
        )

    session.clear()

    return redirect(
        url_for("home")
    )

# ============================================================
# STUDENT DASHBOARD
# ============================================================

@app.route("/student")
@login_required
def student_dashboard():

    if is_admin_session():

        return redirect(
            url_for(
                "admin_dashboard"
            )
        )

    data = [
        q
        for q in questions()
        if q.get("student_id")
        ==
        session.get("user_id")
    ]

    data.sort(
        key=lambda q:
            q.get(
                "created_at",
                ""
            ),
        reverse=True
    )

    cards = ""

    for q in data:

        status = q.get(
            "status",
            "Pending"
        )

        badge = (
            "answered"
            if status == "Answered"
            else
            "pending"
        )

        answer = q.get(
            "answer",
            ""
        )

        answer_html = (
            f"""
            <div class="answer">
                {esc(answer)}
            </div>
            """
            if answer
            else
            """
            <p class="muted">
                Waiting for an answer.
            </p>
            """
        )

        cards += f"""

        <div class="card">

            <span class="subject">
                {esc(q.get("subject"))}
            </span>

            <span class="badge {badge}">
                {esc(status)}
            </span>

            <p class="muted">
                Submitted:
                {esc(q.get("created_at"))}
            </p>

            <h3>
                Your Question
            </h3>

            <div class="question">
                {esc(q.get("question"))}
            </div>

            <h3>
                Your Files
            </h3>

            {
                attachment_html(
                    q.get(
                        "attachments",
                        []
                    ),
                    "student",
                    q.get("id")
                )
            }

            <h3>
                KOJA Answer
            </h3>

            {answer_html}

            <h3>
                Answer Files
            </h3>

            {
                attachment_html(
                    q.get(
                        "answer_attachments",
                        []
                    ),
                    "student",
                    q.get("id")
                )
            }

        </div>

        """

    if not cards:

        cards = """

        <div class="card">

            <h2>
                You have not submitted
                a question yet.
            </h2>

            <a
                class="btn"
                href="/student/ask"
            >
                Ask KOJA
            </a>

        </div>

        """

    content = f"""

    <div class="hero">

        <h1>
            Welcome,
            {esc(session.get("name"))}
        </h1>

        <p>
            Your questions are private
            to your account and the
            KOJA administrator.
        </p>

        <a
            class="btn"
            href="/student/ask"
        >
            Ask Question
        </a>

        <a
            class="btn"
            href="/research"
        >
            Research
        </a>

    </div>

    <h2>
        My Questions
    </h2>

    {cards}

    """

    return render_page(
        "Student Dashboard",
        content
    )

# ============================================================
# ASK QUESTION
# ============================================================

@app.route(
    "/student/ask",
    methods=["GET", "POST"]
)
@login_required
def ask_question():

    if is_admin_session():

        return redirect(
            url_for(
                "admin_dashboard"
            )
        )

    if request.method == "POST":

        subject = (
            request.form.get(
                "subject",
                ""
            ).strip()
        )

        question_text = (
            request.form.get(
                "question",
                ""
            ).strip()
        )

        if (
            len(subject) < 2
            or
            len(question_text) < 3
        ):

            flash(
                "Enter a valid subject and question.",
                "error"
            )

            return redirect(
                url_for(
                    "ask_question"
                )
            )

        question_id = str(
            uuid.uuid4()
        )

        attachments = (
            save_multiple_uploads(
                request.files.getlist(
                    "attachments"
                ),
                "student",
                question_id
            )
        )

        item = {
            "id": question_id,
            "student_id":
                session.get(
                    "user_id"
                ),
            "student_name":
                session.get(
                    "name"
                ),
            "student_email":
                session.get(
                    "email"
                ),
            "subject": subject,
            "question":
                question_text,
            "attachments":
                attachments,
            "status":
                "Pending",
            "answer": "",
            "answer_attachments": [],
            "answered_at": None,
            "answered_by": None,
            "created_at": now(),
        }

        data = questions()

        data.append(item)

        save_questions(data)

        sync_question(item)

        log_event(
            "Question Submitted",
            "Question",
            "INFO",
            (
                subject
                +
                " | "
                +
                question_id
            )
        )

        flash(
            "Question submitted successfully.",
            "success"
        )

        return redirect(
            url_for(
                "student_dashboard"
            )
        )

    content = """

    <div class="card">

        <h1>
            Ask KOJA AFRICA
        </h1>

        <p class="muted">
            Your submitted question is not
            publicly displayed while it is
            pending.
        </p>

        <form
            method="post"
            enctype="multipart/form-data"
        >

            <label>
                Subject
            </label>

            <input
                name="subject"
                placeholder="e.g. Chemistry"
                required
            >

            <label>
                Question
            </label>

            <textarea
                name="question"
                placeholder="Write your academic question..."
                required
            ></textarea>

            <label>
                Supporting Files
            </label>

            <input
                type="file"
                name="attachments"
                multiple
                accept=".pdf,.doc,.docx,.txt,.ppt,.pptx,.xls,.xlsx,.csv,.png,.jpg,.jpeg,.webp,.gif"
            >

            <button type="submit">
                Submit Question
            </button>

        </form>

    </div>

    """

    return render_page(
        "Ask Question",
        content
    )

# ============================================================
# ADMIN DASHBOARD
# ============================================================

@app.route("/admin")
@admin_required
def admin_dashboard():

    data = questions()

    total = len(data)

    pending = sum(
        q.get("status")
        !=
        "Answered"
        for q in data
    )

    answered = (
        total
        -
        pending
    )

    total_logs = len(
        logs()
    )

    content = f"""

    <div class="hero">

        <h1>
            KOJA Administrator
        </h1>

        <p>
            Private administrator workspace
            for questions, answers, files,
            research and security logs.
        </p>

    </div>

    <div class="grid">

        <div class="stat">
            <h2>{total}</h2>
            <p>Total Questions</p>
        </div>

        <div class="stat">
            <h2>{pending}</h2>
            <p>Pending</p>
        </div>

        <div class="stat">
            <h2>{answered}</h2>
            <p>Answered</p>
        </div>

        <div class="stat">
            <h2>{total_logs}</h2>
            <p>System Logs</p>
        </div>

    </div>

    <div class="card">

        <a
            class="btn"
            href="/admin/questions"
        >
            Questions
        </a>

        <a
            class="btn green"
            href="/admin/answers"
        >
            Answers
        </a>

        <a
            class="btn purple"
            href="/admin/logs"
        >
            System Logs
        </a>

        <a
            class="btn"
            href="/admin/config"
        >
            Configuration
        </a>

    </div>

    """

    return render_page(
        "Admin Dashboard",
        content
    )

# ============================================================
# ADMIN QUESTIONS
#
# This is private.
# Students/public cannot access it.
# ============================================================

@app.route("/admin/questions")
@admin_required
def admin_questions():

    data = [
        q
        for q in questions()
        if q.get("status")
        !=
        "Answered"
    ]

    data.sort(
        key=lambda q:
            q.get(
                "created_at",
                ""
            ),
        reverse=True
    )

    rows = ""

    for q in data:

        text = q.get(
            "question",
            ""
        )

        if len(text) > 200:
            text = (
                text[:200]
                +
                "..."
            )

        rows += f"""

        <tr>

            <td>
                {esc(q.get("student_name"))}
                <br>
                <small>
                    {esc(q.get("student_email"))}
                </small>
            </td>

            <td>
                {esc(q.get("subject"))}
            </td>

            <td>
                {esc(text)}
            </td>

            <td>
                <span class="badge pending">
                    Pending
                </span>
            </td>

            <td>

                <a
                    class="btn small"
                    href="/admin/question/{esc(q.get('id'))}"
                >
                    Open
                </a>

                <a
                    class="btn purple small"
                    href="/admin/question/{esc(q.get('id'))}/upload"
                >
                    Answer + Files
                </a>

            </td>

        </tr>

        """

    if not rows:

        rows = """

        <tr>
            <td colspan="5">
                No pending questions.
            </td>
        </tr>

        """

    content = f"""

    <div class="card">

        <h1>
            Student Questions
        </h1>

        <p>
            Only administrators can see
            submitted questions here.
        </p>

    </div>

    <div class="card">

        <div style="overflow-x:auto">

            <table>

                <thead>

                    <tr>

                        <th>
                            Student
                        </th>

                        <th>
                            Subject
                        </th>

                        <th>
                            Question
                        </th>

                        <th>
                            Status
                        </th>

                        <th>
                            Actions
                        </th>

                    </tr>

                </thead>

                <tbody>

                    {rows}

                </tbody>

            </table>

        </div>

    </div>

    """

    return render_page(
        "Questions",
        content
    )

# ============================================================
# ADMIN QUESTION
# ============================================================

@app.route(
    "/admin/question/<question_id>",
    methods=["GET", "POST"]
)
@admin_required
def admin_question(question_id):

    question = find_question(
        question_id
    )

    if not question:

        flash(
            "Question not found.",
            "error"
        )

        return redirect(
            url_for(
                "admin_questions"
            )
        )

    if request.method == "POST":

        answer = (
            request.form.get(
                "answer",
                ""
            ).strip()
        )

        if len(answer) < 2:

            flash(
                "Write an answer first.",
                "error"
            )

            return redirect(
                url_for(
                    "admin_question",
                    question_id=question_id
                )
            )

        answered_at = now()

        data = questions()

        for item in data:

            if (
                str(item.get("id"))
                ==
                str(question_id)
            ):

                item["answer"] = answer
                item["status"] = "Answered"
                item["answered_at"] = answered_at
                item["answered_by"] = session.get(
                    "email"
                )

                break

        save_questions(data)

        supabase_update(
            "koja_questions",
            "id",
            question_id,
            {
                "answer": answer,
                "status": "Answered",
                "answered_at": answered_at,
            }
        )

        log_event(
            "Answer Posted",
            "Answer",
            "SUCCESS",
            "Answer posted to "
            +
            question_id
        )

        flash(
            "Answer saved.",
            "success"
        )

        return redirect(
            url_for(
                "admin_upload_answer",
                question_id=question_id
            )
        )

    content = f"""

    <div class="card">

        <a href="/admin/questions">
            ← Questions
        </a>

        <h1>
            {esc(question.get("subject"))}
        </h1>

        <p>
            <strong>
                Student:
            </strong>
            {esc(question.get("student_name"))}

            <br>

            <strong>
                Email:
            </strong>
            {esc(question.get("student_email"))}
        </p>

    </div>

    <div class="card">

        <h2>
            Student Question
        </h2>

        <div class="question">
            {esc(question.get("question"))}
        </div>

        <h2>
            Student Attachments
        </h2>

        {
            attachment_html(
                question.get(
                    "attachments",
                    []
                ),
                "admin",
                question_id
            )
        }

    </div>

    <div class="card">

        <h2>
            Academic Answer
        </h2>

        <form method="post">

            <textarea
                name="answer"
                required
            >{esc(question.get("answer", ""))}</textarea>

            <button
                class="green"
                type="submit"
            >
                Save Answer
            </button>

        </form>

        <br>

        <a
            class="btn purple"
            href="/admin/question/{question_id}/upload"
        >
            Answer + Files
        </a>

    </div>

    """

    return render_page(
        "Open Question",
        content
    )

# ============================================================
# ADMIN ANSWER + FILES
# ============================================================

@app.route(
    "/admin/question/<question_id>/upload",
    methods=["GET", "POST"]
)
@admin_required
def admin_upload_answer(question_id):

    question = find_question(
        question_id
    )

    if not question:

        flash(
            "Question not found.",
            "error"
        )

        return redirect(
            url_for(
                "admin_questions"
            )
        )

    if request.method == "POST":

        answer = (
            request.form.get(
                "answer",
                ""
            ).strip()
        )

        if not answer:

            answer = (
                question.get(
                    "answer",
                    ""
                ).strip()
            )

        if len(answer) < 2:

            flash(
                "Write an answer before sending.",
                "error"
            )

            return redirect(
                url_for(
                    "admin_upload_answer",
                    question_id=question_id
                )
            )

        attachments = (
            save_multiple_uploads(
                request.files.getlist(
                    "answer_attachments"
                ),
                "admin",
                question_id
            )
        )

        answered_at = now()

        data = questions()

        for item in data:

            if (
                str(item.get("id"))
                ==
                str(question_id)
            ):

                item["answer"] = answer
                item["status"] = "Answered"
                item["answered_at"] = answered_at
                item["answered_by"] = session.get(
                    "email"
                )

                existing = item.get(
                    "answer_attachments",
                    []
                )

                if not isinstance(
                    existing,
                    list
                ):
                    existing = []

                existing.extend(
                    attachments
                )

                item["answer_attachments"] = (
                    existing
                )

                break

        save_questions(data)

        supabase_update(
            "koja_questions",
            "id",
            question_id,
            {
                "answer": answer,
                "status": "Answered",
                "answered_at": answered_at,
            }
        )

        log_event(
            "Answer Sent",
            "Answer",
            "SUCCESS",
            (
                f"Answer and "
                f"{len(attachments)} "
                f"attachment(s) sent to "
                f"{question_id}"
            )
        )

        flash(
            "Answer sent successfully.",
            "success"
        )

        return redirect(
            url_for(
                "admin_answers"
            )
        )

    content = f"""

    <div class="card">

        <a href="/admin/questions">
            ← Questions
        </a>

        <h1>
            Answer + Files
        </h1>

        <p>
            Student:
            <strong>
                {esc(question.get("student_name"))}
            </strong>
        </p>

        <div class="question">
            {esc(question.get("question"))}
        </div>

    </div>

    <div class="card">

        <form
            method="post"
            enctype="multipart/form-data"
        >

            <label>
                Academic Answer
            </label>

            <textarea
                name="answer"
                required
            >{esc(question.get("answer", ""))}</textarea>

            <label>
                Answer Files
            </label>

            <input
                type="file"
                name="answer_attachments"
                multiple
                accept=".pdf,.doc,.docx,.txt,.ppt,.pptx,.xls,.xlsx,.csv,.png,.jpg,.jpeg,.webp,.gif"
            >

            <button
                class="green"
                type="submit"
            >
                Send Answer + Files
            </button>

        </form>

    </div>

    <div class="card">

        <h2>
            Previously Sent Files
        </h2>

        {
            attachment_html(
                question.get(
                    "answer_attachments",
                    []
                ),
                "admin",
                question_id
            )
        }

    </div>

    """

    return render_page(
        "Answer + Files",
        content
    )

# ============================================================
# ADMIN ANSWERS
# ============================================================

@app.route("/admin/answers")
@admin_required
def admin_answers():

    data = [
        q
        for q in questions()
        if q.get("status")
        ==
        "Answered"
    ]

    data.sort(
        key=lambda q:
            q.get(
                "answered_at",
                ""
            ),
        reverse=True
    )

    cards = ""

    for q in data:

        cards += f"""

        <div class="card">

            <span class="subject">
                {esc(q.get("subject"))}
            </span>

            <span class="badge answered">
                Answered
            </span>

            <p>
                <strong>
                    Student:
                </strong>

                {esc(q.get("student_name"))}
            </p>

            <div class="question">
                {esc(q.get("question"))}
            </div>

            <h3>
                Answer
            </h3>

            <div class="answer">
                {esc(q.get("answer"))}
            </div>

            <br>

            <a
                class="btn"
                href="/admin/question/{esc(q.get('id'))}"
            >
                Open
            </a>

        </div>

        """

    if not cards:

        cards = """

        <div class="card">

            <h2>
                No previous answers.
            </h2>

        </div>

        """

    return render_page(
        "Previous Answers",
        cards
    )

# ============================================================
# ADMIN LOGS
#
# PRIVATE ADMIN ONLY.
# There is no public route to logs.
# ============================================================

@app.route("/admin/logs")
@admin_required
def admin_logs():

    all_logs = logs()

    all_logs.sort(
        key=lambda x:
            x.get(
                "created_at",
                ""
            ),
        reverse=True
    )

    level_filter = (
        request.args.get(
            "level",
            ""
        )
        .upper()
        .strip()
    )

    category_filter = (
        request.args.get(
            "category",
            ""
        )
        .strip()
        .lower()
    )

    user_filter = (
        request.args.get(
            "user",
            ""
        )
        .strip()
        .lower()
    )

    filtered = []

    for item in all_logs:

        if (
            level_filter
            and
            item.get("level")
            !=
            level_filter
        ):
            continue

        if (
            category_filter
            and
            category_filter
            not in
            item.get(
                "category",
                ""
            ).lower()
        ):
            continue

        if (
            user_filter
            and
            user_filter
            not in
            (
                item.get(
                    "user_email",
                    ""
                )
                or
                ""
            ).lower()
        ):
            continue

        filtered.append(item)

    today = (
        datetime.now(
            timezone.utc
        )
        .date()
        .isoformat()
    )

    today_count = sum(
        str(
            x.get(
                "created_at",
                ""
            )
        ).startswith(today)
        for x in all_logs
    )

    errors = sum(
        x.get("level")
        ==
        "ERROR"
        for x in all_logs
    )

    rows = ""

    for item in filtered[:500]:

        level = item.get(
            "level",
            "INFO"
        )

        css = {
            "SUCCESS": "log-success",
            "WARNING": "log-warning",
            "ERROR": "log-error",
            "INFO": "log-info",
        }.get(
            level,
            "log-info"
        )

        rows += f"""

        <tr>

            <td>
                {esc(item.get("created_at"))}
            </td>

            <td class="{css}">
                <strong>
                    {esc(level)}
                </strong>
            </td>

            <td>
                {esc(item.get("category"))}
            </td>

            <td>
                {esc(item.get("user_email"))}
            </td>

            <td>
                {esc(item.get("action"))}
            </td>

            <td>
                {esc(item.get("details"))}
            </td>

            <td>
                {esc(item.get("ip_address"))}
            </td>

        </tr>

        """

    if not rows:

        rows = """

        <tr>
            <td colspan="7">
                No matching logs.
            </td>
        </tr>

        """

    categories = sorted({
        str(
            x.get(
                "category",
                ""
            )
        )
        for x in all_logs
        if x.get("category")
    })

    options = "".join(
        f"""
        <option
            value="{esc(category)}"
            {"selected" if category_filter == category.lower() else ""}
        >
            {esc(category)}
        </option>
        """
        for category in categories
    )

    content = f"""

    <div class="hero">

        <h1>
            KOJA System Logs
        </h1>

        <p>
            Private administrator activity
            and security monitoring.
        </p>

        <span class="live">
            ● Logging active
        </span>

    </div>

    <div class="grid">

        <div class="stat">
            <h2>{len(all_logs)}</h2>
            <p>Total Logs</p>
        </div>

        <div class="stat">
            <h2>{today_count}</h2>
            <p>Today</p>
        </div>

        <div class="stat">
            <h2>{errors}</h2>
            <p>Errors</p>
        </div>

        <div class="stat">
            <h2>{len(users())}</h2>
            <p>Registered Users</p>
        </div>

    </div>

    <div class="card">

        <h2>
            Filter Logs
        </h2>

        <form method="get">

            <label>
                Level
            </label>

            <select name="level">

                <option value="">
                    All Levels
                </option>

                <option
                    value="INFO"
                    {"selected" if level_filter == "INFO" else ""}
                >
                    INFO
                </option>

                <option
                    value="SUCCESS"
                    {"selected" if level_filter == "SUCCESS" else ""}
                >
                    SUCCESS
                </option>

                <option
                    value="WARNING"
                    {"selected" if level_filter == "WARNING" else ""}
                >
                    WARNING
                </option>

                <option
                    value="ERROR"
                    {"selected" if level_filter == "ERROR" else ""}
                >
                    ERROR
                </option>

            </select>

            <label>
                Category
            </label>

            <select name="category">

                <option value="">
                    All Categories
                </option>

                {options}

            </select>

            <label>
                User
            </label>

            <input
                name="user"
                value="{esc(user_filter)}"
                placeholder="Search email"
            >

            <button type="submit">
                Filter
            </button>

            <a
                class="btn"
                href="/admin/logs"
            >
                Clear
            </a>

        </form>

    </div>

    <div class="card">

        <div style="overflow-x:auto">

            <table>

                <thead>

                    <tr>

                        <th>Time</th>
                        <th>Level</th>
                        <th>Category</th>
                        <th>User</th>
                        <th>Action</th>
                        <th>Details</th>
                        <th>IP</th>

                    </tr>

                </thead>

                <tbody>

                    {rows}

                </tbody>

            </table>

        </div>

    </div>

    """

    return render_page(
        "System Logs",
        content
    )

# ============================================================
# ADMIN FILE ACCESS
# ============================================================

@app.route(
    "/admin/file/<category>/<filename>"
)
@admin_required
def admin_file(
    category,
    filename
):

    if category == "student":
        directory = STUDENT_UPLOAD_DIR

    elif category == "admin":
        directory = ADMIN_UPLOAD_DIR

    else:
        abort(404)

    log_event(
        "File Viewed",
        "Storage",
        "INFO",
        f"{category}/{filename}"
    )

    return send_from_directory(
        directory,
        filename
    )

# ============================================================
# STUDENT FILE ACCESS
# ============================================================

@app.route(
    "/student/file/<question_id>/<category>/<filename>"
)
@login_required
def student_file(
    question_id,
    category,
    filename
):

    if is_admin_session():

        return redirect(
            url_for(
                "admin_dashboard"
            )
        )

    question = find_question(
        question_id
    )

    if not question:
        return (
            "File not found",
            404
        )

    if (
        question.get(
            "student_id"
        )
        !=
        session.get("user_id")
    ):

        log_event(
            "Unauthorized File Access",
            "Security",
            "WARNING",
            question_id
        )

        return (
            "Access denied",
            403
        )

    if category == "student":

        attachments = question.get(
            "attachments",
            []
        )

        directory = STUDENT_UPLOAD_DIR

    elif category == "admin":

        attachments = question.get(
            "answer_attachments",
            []
        )

        directory = ADMIN_UPLOAD_DIR

    else:

        return (
            "Invalid category",
            404
        )

    for attachment in attachments:

        if (
            attachment.get(
                "stored_name"
            )
            ==
            filename
        ):

            log_event(
                "File Viewed",
                "Storage",
                "INFO",
                f"{category}/{filename}"
            )

            return send_from_directory(
                directory,
                filename
            )

    return (
        "File not found",
        404
    )

# ============================================================
# ADMIN CONFIGURATION
# ============================================================

@app.route("/admin/config")
@admin_required
def admin_config():

    configured = (
        supabase_configured()
    )

    connected = (
        supabase_test()
        if configured
        else
        False
    )

    content = f"""

    <div class="card">

        <h1>
            KOJA Configuration
        </h1>

        <h2>
            Supabase
        </h2>

        <p>
            Configured:

            <span class="badge
                {"answered" if configured else "pending"}
            ">
                {"YES" if configured else "NO"}
            </span>
        </p>

        <p>
            Connection:

            <span class="badge
                {"answered" if connected else "pending"}
            ">
                {"WORKING" if connected else "UNAVAILABLE"}
            </span>
        </p>

        <p>
            Storage bucket:
            <strong>
                {esc(STORAGE_BUCKET)}
            </strong>
        </p>

        <h2>
            Local Storage
        </h2>

        <p>
            Local JSON storage is active.
            KOJA can continue operating even
            when Supabase is unavailable.
        </p>

        <h2>
            Security
        </h2>

        <p>
            Administrator logs are private.
        </p>

        <p>
            Student questions remain private
            until an administrator answers
            and publishes them.
        </p>

    </div>

    """

    return render_page(
        "Configuration",
        content
    )

# ============================================================
# HEALTH
# ============================================================

@app.route("/health")
def health():

    return {
        "status": "ok",
        "application": SITE_NAME,
        "supabase_configured":
            supabase_configured(),
        "supabase_connected":
            supabase_test(),
        "logging": True,
        "local_fallback": True,
        "research": True,
        "public_pending_questions":
            False,
        "admin_dashboard_protected":
            True,
        "timestamp": now(),
    }

# ============================================================
# ERROR HANDLERS
# ============================================================

@app.errorhandler(413)
def too_large(error):

    try:

        log_event(
            "Upload Failed",
            "Storage",
            "ERROR",
            "Request exceeded 10 MB"
        )

    except Exception:
        pass

    flash(
        "Maximum upload size is 10 MB.",
        "error"
    )

    if session.get("user_id"):

        return redirect(
            url_for(
                "admin_dashboard"
                if is_admin_session()
                else
                "ask_question"
            )
        )

    return redirect(
        url_for("login")
    )


@app.errorhandler(404)
def not_found(error):

    return (
        render_page(
            "Not Found",
            """

            <div class="card">

                <h1>
                    Page Not Found
                </h1>

                <p>
                    The requested KOJA AFRICA
                    page does not exist.
                </p>

                <a
                    class="btn"
                    href="/"
                >
                    Go Home
                </a>

            </div>

            """
        ),
        404
    )


@app.errorhandler(500)
def server_error(error):

    try:

        log_event(
            "Internal Server Error",
            "System",
            "ERROR",
            str(error)
        )

    except Exception:
        pass

    return (
        render_page(
            "KOJA Error",
            """

            <div class="card">

                <h1>
                    KOJA AFRICA
                </h1>

                <p>
                    An unexpected error occurred.
                </p>

                <a
                    class="btn"
                    href="/"
                >
                    Go Home
                </a>

            </div>

            """
        ),
        500
    )

# ============================================================
# START APPLICATION
# ============================================================

if __name__ == "__main__":

    port = int(
        os.environ.get(
            "PORT",
            "9999"
        )
    )

    print("=" * 60)
    print("KOJA AFRICA")
    print("Knowledge • Questions • Answers")
    print("Opening Animation: ENABLED")
    print("Animation Location: HOME ONLY")
    print("Public Pending Questions: DISABLED")
    print("Admin Dashboard: PROTECTED")
    print("Admin Logs: PROTECTED")
    print("Local Fallback: ENABLED")
    print(
        "Supabase:",
        supabase_configured()
    )
    print(
        "Port:",
        port
    )
    print("=" * 60)

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False
    )
