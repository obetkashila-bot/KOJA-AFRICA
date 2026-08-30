import os
import io
import uuid
import logging
from datetime import datetime, timezone
from functools import wraps
from html import escape

import requests
from dotenv import load_dotenv

from flask import (
    Flask,
    request,
    redirect,
    url_for,
    session,
    render_template_string,
    flash,
    send_file,
    abort,
)

from werkzeug.security import (
    generate_password_hash,
    check_password_hash,
)

from werkzeug.utils import secure_filename

from reportlab.lib.pagesizes import A4
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
)
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.enums import TA_CENTER

from docx import Document
from openpyxl import Workbook


# ============================================================
# LOAD ENVIRONMENT
# ============================================================

load_dotenv()


# ============================================================
# APPLICATION
# ============================================================

app = Flask(__name__)

app.secret_key = os.environ.get(
    "SECRET_KEY",
    "CHANGE-THIS-SECRET-KEY-IN-RENDER"
)

app.config["MAX_CONTENT_LENGTH"] = 15 * 1024 * 1024


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)


# ============================================================
# CONFIGURATION
# ============================================================

SUPABASE_URL = os.environ.get(
    "SUPABASE_URL",
    ""
).rstrip("/")


SUPABASE_SERVICE_KEY = os.environ.get(
    "SUPABASE_SERVICE_KEY",
    ""
)


APP_NAME = "KOJA AFRICA"

APP_TAGLINE = (
    "Assignment Questions • Academic Answers • "
    "Learning Resources"
)


STORAGE_BUCKET = os.environ.get(
    "SUPABASE_STORAGE_BUCKET",
    "koja-assignments"
)


ADMIN_EMAIL = os.environ.get(
    "ADMIN_EMAIL",
    "admin@koja-africa.com"
)


ADMIN_PASSWORD = os.environ.get(
    "ADMIN_PASSWORD",
    "ChangeThisAdminPassword123!"
)


MAX_FILE_SIZE = 15 * 1024 * 1024


ALLOWED_EXTENSIONS = {
    "pdf",
    "doc",
    "docx",
    "xls",
    "xlsx",
    "png",
    "jpg",
    "jpeg",
    "webp",
    "txt",
}


# ============================================================
# BASIC HELPERS
# ============================================================

def utc_now():
    return datetime.now(timezone.utc).isoformat()


def allowed_file(filename):
    if not filename:
        return False

    if "." not in filename:
        return False

    extension = filename.rsplit(
        ".",
        1
    )[1].lower()

    return extension in ALLOWED_EXTENSIONS


def safe_text(value):
    if value is None:
        return ""

    return escape(str(value))


# ============================================================
# SUPABASE CONFIGURATION CHECK
# ============================================================

def check_supabase_config():
    if not SUPABASE_URL:
        raise RuntimeError(
            "SUPABASE_URL is missing in Render Environment Variables."
        )

    if not SUPABASE_SERVICE_KEY:
        raise RuntimeError(
            "SUPABASE_SERVICE_KEY is missing in Render Environment Variables."
        )


# ============================================================
# SUPABASE HEADERS
# ============================================================

def supabase_headers():
    check_supabase_config()

    return {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": (
            f"Bearer {SUPABASE_SERVICE_KEY}"
        ),
        "Content-Type": "application/json",
    }


# ============================================================
# SUPABASE REST REQUEST
# ============================================================

def supabase_request(
    method,
    table,
    params=None,
    data=None,
    headers=None,
    timeout=30,
):
    check_supabase_config()

    url = (
        f"{SUPABASE_URL}/rest/v1/{table}"
    )

    final_headers = supabase_headers()

    if headers:
        final_headers.update(headers)

    try:

        response = requests.request(
            method=method,
            url=url,
            params=params,
            json=data,
            headers=final_headers,
            timeout=timeout,
        )

    except requests.RequestException as exc:

        logging.exception(
            "Supabase connection failed"
        )

        raise RuntimeError(
            f"Could not connect to Supabase: {exc}"
        )


    if not response.ok:

        logging.error(
            "Supabase %s %s failed: HTTP %s: %s",
            method,
            table,
            response.status_code,
            response.text,
        )

        raise RuntimeError(
            "Database request failed: "
            f"{response.status_code} "
            f"{response.text}"
        )


    if not response.text:
        return []


    try:
        return response.json()

    except Exception:
        return response.text


# ============================================================
# DATABASE SELECT
# ============================================================

def db_select(
    table,
    columns="*",
    filters=None,
    limit=None,
    order=None,
):
    params = {
        "select": columns
    }

    if filters:
        params.update(filters)

    if limit:
        params["limit"] = str(limit)

    if order:
        params["order"] = order

    return supabase_request(
        "GET",
        table,
        params=params,
    )


# ============================================================
# DATABASE INSERT
# ============================================================

def db_insert(
    table,
    data,
    returning=True,
):
    headers = {}

    if returning:
        headers["Prefer"] = (
            "return=representation"
        )

    return supabase_request(
        "POST",
        table,
        data=data,
        headers=headers,
    )


# ============================================================
# DATABASE UPDATE
# ============================================================

def db_update(
    table,
    filters,
    data,
):
    headers = {
        "Prefer": "return=representation"
    }

    return supabase_request(
        "PATCH",
        table,
        params=filters,
        data=data,
        headers=headers,
    )


# ============================================================
# DATABASE DELETE
# ============================================================

def db_delete(
    table,
    filters,
):
    return supabase_request(
        "DELETE",
        table,
        params=filters,
    )


# ============================================================
# STORAGE UPLOAD
# ============================================================

def storage_upload(
    file_bytes,
    storage_path,
    content_type,
):
    check_supabase_config()

    url = (
        f"{SUPABASE_URL}/storage/v1/object/"
        f"{STORAGE_BUCKET}/{storage_path}"
    )

    headers = {
        "Authorization":
            f"Bearer {SUPABASE_SERVICE_KEY}",

        "apikey":
            SUPABASE_SERVICE_KEY,

        "Content-Type":
            content_type,

        "x-upsert":
            "true",
    }

    try:

        response = requests.post(
            url,
            headers=headers,
            data=file_bytes,
            timeout=60,
        )

    except requests.RequestException as exc:

        raise RuntimeError(
            f"Storage connection failed: {exc}"
        )


    if not response.ok:

        raise RuntimeError(
            "Storage upload failed: "
            f"{response.status_code} "
            f"{response.text}"
        )


    return storage_path


# ============================================================
# STORAGE DOWNLOAD
# ============================================================

def storage_download(storage_path):

    check_supabase_config()

    if not storage_path:
        raise RuntimeError(
            "Storage path is missing."
        )

    url = (
        f"{SUPABASE_URL}/storage/v1/object/"
        f"{STORAGE_BUCKET}/{storage_path}"
    )

    headers = {
        "Authorization":
            f"Bearer {SUPABASE_SERVICE_KEY}",

        "apikey":
            SUPABASE_SERVICE_KEY,
    }

    try:

        response = requests.get(
            url,
            headers=headers,
            timeout=60,
        )

    except requests.RequestException as exc:

        raise RuntimeError(
            f"Storage connection failed: {exc}"
        )


    if not response.ok:

        raise RuntimeError(
            "Storage download failed: "
            f"{response.status_code} "
            f"{response.text}"
        )


    return response.content


# ============================================================
# STORAGE DELETE
# ============================================================

def storage_delete(storage_path):

    check_supabase_config()

    if not storage_path:
        return False

    url = (
        f"{SUPABASE_URL}/storage/v1/object/"
        f"{STORAGE_BUCKET}"
    )

    headers = {
        "Authorization":
            f"Bearer {SUPABASE_SERVICE_KEY}",

        "apikey":
            SUPABASE_SERVICE_KEY,

        "Content-Type":
            "application/json",
    }

    try:

        response = requests.delete(
            url,
            headers=headers,
            json={
                "prefixes": [
                    storage_path
                ]
            },
            timeout=30,
        )

        return response.ok

    except requests.RequestException:

        logging.exception(
            "Storage delete failed"
        )

        return False


# ============================================================
# LOGIN HELPERS
# ============================================================

def current_user():
    return session.get("user")


def current_email():

    user = current_user()

    if not user:
        return None

    return user.get("email")


def login_required(function):

    @wraps(function)
    def wrapper(*args, **kwargs):

        if not current_user():

            flash(
                "Please login first.",
                "warning"
            )

            return redirect(
                url_for("login")
            )

        return function(
            *args,
            **kwargs
        )

    return wrapper


def admin_required(function):

    @wraps(function)
    def wrapper(*args, **kwargs):

        user = current_user()

        if not user:

            flash(
                "Please login first.",
                "warning"
            )

            return redirect(
                url_for("login")
            )


        if not user.get("is_admin"):

            flash(
                "Administrator access required.",
                "danger"
            )

            return redirect(
                url_for("dashboard")
            )


        return function(
            *args,
            **kwargs
        )

    return wrapper


# ============================================================
# PROFILE LOOKUP
# ============================================================

def find_profile(email):

    if not email:
        return None

    rows = db_select(
        "profiles",
        filters={
            "email": f"eq.{email}"
        },
        limit=1,
    )

    if rows:
        return rows[0]

    return None


# ============================================================
# CREATE PROFILE
# ============================================================
#
# IMPORTANT:
# The previous version failed because profiles.id was NULL.
#
# This version ALWAYS generates a UUID before inserting.
#
# ============================================================

def create_profile(
    email,
    name,
    password_hash,
    is_admin=False,
):

    profile_id = str(
        uuid.uuid4()
    )


    data = {
        "id": profile_id,

        "email": email,

        "full_name": name,

        "password_hash":
            password_hash,

        "is_admin":
            bool(is_admin),

        "created_at":
            utc_now(),
    }


    logging.info(
        "Creating profile %s for %s",
        profile_id,
        email
    )


    try:

        result = db_insert(
            "profiles",
            data,
            returning=True,
        )


        if (
            isinstance(result, list)
            and result
        ):

            return result[0]


        return data


    except Exception as exc:

        logging.exception(
            "Full profile insert failed"
        )


        # Compatibility attempt.
        #
        # IMPORTANT:
        # id is STILL included.
        #
        fallback = {
            "id": profile_id,

            "email": email,

            "full_name": name,

            "password_hash":
                password_hash,

            "is_admin":
                bool(is_admin),
        }


        try:

            result = db_insert(
                "profiles",
                fallback,
                returning=True,
            )


            if (
                isinstance(result, list)
                and result
            ):

                return result[0]


            return fallback


        except Exception:

            logging.exception(
                "Fallback profile insert failed"
            )

            raise exc


# ============================================================
# VERIFY USER
# ============================================================

def verify_user(
    email,
    password,
):

    profile = find_profile(
        email
    )

    if not profile:
        return None


    password_hash = profile.get(
        "password_hash"
    )


    if not password_hash:
        return None


    try:

        valid = check_password_hash(
            password_hash,
            password,
        )

    except Exception:

        logging.exception(
            "Password verification failed"
        )

        valid = False


    if not valid:
        return None


    return profile


# ============================================================
# ACTIVITY LOG
# ============================================================

def log_activity(
    action,
    description=""
):

    user = current_user()

    email = None

    if user:
        email = user.get(
            "email"
        )


    data = {
        "action":
            action,

        "description":
            description,

        "email":
            email,

        "created_at":
            utc_now(),
    }


    try:

        db_insert(
            "activity_logs",
            data,
            returning=False,
        )

    except Exception:

        logging.exception(
            "Activity log failed"
        )


# ============================================================
# SAVE ASSIGNMENT FILE RECORD
# ============================================================

def save_assignment_file(
    assignment_id,
    original_filename,
    storage_path,
    content_type,
    file_size,
    file_role="question",
):

    data = {

        "assignment_id":
            assignment_id,

        "original_filename":
            original_filename,

        "storage_path":
            storage_path,

        "content_type":
            content_type,

        "file_size":
            file_size,

        "file_role":
            file_role,

        "created_at":
            utc_now(),
    }


    result = db_insert(
        "assignment_files",
        data,
    )


    if (
        isinstance(result, list)
        and result
    ):

        return result[0]


    return data


# ============================================================
# PDF GENERATOR
# ============================================================

def build_pdf(
    title,
    student_name,
    question,
    answer,
):

    buffer = io.BytesIO()


    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=50,
        leftMargin=50,
        topMargin=50,
        bottomMargin=50,
    )


    styles = getSampleStyleSheet()


    title_style = styles["Title"]

    title_style.alignment = (
        TA_CENTER
    )


    heading = styles["Heading2"]

    normal = styles["BodyText"]


    story = []


    story.append(
        Paragraph(
            "KOJA AFRICA",
            title_style,
        )
    )


    story.append(
        Spacer(1, 15)
    )


    story.append(
        Paragraph(
            safe_text(title),
            heading,
        )
    )


    story.append(
        Spacer(1, 10)
    )


    story.append(
        Paragraph(
            "<b>Student:</b> "
            + safe_text(student_name),
            normal,
        )
    )


    story.append(
        Spacer(1, 15)
    )


    story.append(
        Paragraph(
            "Question",
            heading,
        )
    )


    question_html = safe_text(
        question
    ).replace(
        "\n",
        "<br/>"
    )


    story.append(
        Paragraph(
            question_html,
            normal,
        )
    )


    story.append(
        Spacer(1, 20)
    )


    story.append(
        Paragraph(
            "Answer",
            heading,
        )
    )


    answer_html = safe_text(
        answer
    ).replace(
        "\n",
        "<br/>"
    )


    story.append(
        Paragraph(
            answer_html,
            normal,
        )
    )


    story.append(
        Spacer(1, 30)
    )


    story.append(
        Paragraph(
            "Generated by KOJA AFRICA",
            normal,
        )
    )


    document.build(
        story
    )


    buffer.seek(0)

    return buffer.getvalue()


# ============================================================
# WORD GENERATOR
# ============================================================

def build_docx(
    title,
    student_name,
    question,
    answer,
):

    document = Document()


    document.add_heading(
        "KOJA AFRICA",
        0,
    )


    document.add_heading(
        title or "Assignment Answer",
        level=1,
    )


    document.add_paragraph(
        f"Student: {student_name}"
    )


    document.add_heading(
        "Question",
        level=2,
    )


    document.add_paragraph(
        question or ""
    )


    document.add_heading(
        "Answer",
        level=2,
    )


    document.add_paragraph(
        answer or ""
    )


    document.add_paragraph(
        "Generated by KOJA AFRICA"
    )


    buffer = io.BytesIO()


    document.save(
        buffer
    )


    buffer.seek(0)

    return buffer.getvalue()


# ============================================================
# EXCEL GENERATOR
# ============================================================

def build_xlsx(
    title,
    student_name,
    question,
    answer,
):

    workbook = Workbook()


    sheet = workbook.active


    sheet.title = (
        "Assignment Answer"
    )


    sheet["A1"] = (
        "KOJA AFRICA"
    )


    sheet["A2"] = (
        "Assignment"
    )

    sheet["B2"] = (
        title or ""
    )


    sheet["A3"] = (
        "Student"
    )

    sheet["B3"] = (
        student_name or ""
    )


    sheet["A5"] = (
        "Question"
    )

    sheet["B5"] = (
        question or ""
    )


    sheet["A7"] = (
        "Answer"
    )

    sheet["B7"] = (
        answer or ""
    )


    sheet.column_dimensions[
        "A"
    ].width = 25


    sheet.column_dimensions[
        "B"
    ].width = 100


    buffer = io.BytesIO()


    workbook.save(
        buffer
    )


    buffer.seek(0)

    return buffer.getvalue()


# ============================================================
# DOWNLOAD LOG
# ============================================================

def log_download(
    assignment_id,
    file_type,
):

    data = {

        "assignment_id":
            assignment_id,

        "student_email":
            current_email(),

        "file_type":
            file_type,

        "downloaded_at":
            utc_now(),
    }


    try:

        db_insert(
            "downloads",
            data,
            returning=False,
        )

    except Exception:

        logging.exception(
            "Download logging failed"
        )


# ============================================================
# BASE HTML
# ============================================================

BASE_HTML = """

<!doctype html>

<html lang="en">

<head>

<meta charset="utf-8">

<meta
    name="viewport"
    content="width=device-width, initial-scale=1"
>

<title>
{{ title }} - KOJA AFRICA
</title>


<style>

* {
    box-sizing: border-box;
}


body {

    margin: 0;

    font-family:
        Arial,
        sans-serif;

    background:
        #f4f7fb;

    color:
        #172033;

}


.nav {

    background:
        #0b3d91;

    color:
        white;

    padding:
        14px 18px;

}


.nav-inner {

    max-width:
        1100px;

    margin:
        auto;

    display:
        flex;

    justify-content:
        space-between;

    align-items:
        center;

    gap:
        15px;

    flex-wrap:
        wrap;

}


.brand {

    font-size:
        22px;

    font-weight:
        bold;

}


.nav a {

    color:
        white;

    text-decoration:
        none;

    margin:
        4px 7px;

}


.container {

    max-width:
        1100px;

    margin:
        25px auto;

    padding:
        0 15px;

}


.card {

    background:
        white;

    border-radius:
        12px;

    padding:
        22px;

    margin-bottom:
        18px;

    box-shadow:
        0 2px 12px
        rgba(0,0,0,.07);

}


h1,
h2,
h3 {

    margin-top:
        0;

}


input,
textarea,
select {

    width:
        100%;

    padding:
        12px;

    margin-top:
        6px;

    margin-bottom:
        14px;

    border:
        1px solid #ccd3df;

    border-radius:
        8px;

    font-size:
        15px;

}


textarea {

    min-height:
        180px;

    resize:
        vertical;

}


button,
.btn {

    display:
        inline-block;

    background:
        #0b3d91;

    color:
        white;

    border:
        0;

    border-radius:
        8px;

    padding:
        11px 16px;

    cursor:
        pointer;

    text-decoration:
        none;

    margin:
        4px;

}


.btn-green {

    background:
        #138a4b;

}


.btn-red {

    background:
        #b42318;

}


.btn-dark {

    background:
        #172033;

}


.grid {

    display:
        grid;

    grid-template-columns:
        repeat(
            auto-fit,
            minmax(220px, 1fr)
        );

    gap:
        15px;

}


.stat {

    padding:
        20px;

    border-radius:
        10px;

    background:
        #eef4ff;

}


.stat strong {

    display:
        block;

    font-size:
        30px;

    margin-bottom:
        5px;

}


table {

    width:
        100%;

    border-collapse:
        collapse;

}


th,
td {

    padding:
        10px;

    border-bottom:
        1px solid #ddd;

    text-align:
        left;

}


.badge {

    display:
        inline-block;

    padding:
        5px 9px;

    border-radius:
        15px;

    background:
        #e8eef8;

}


.flash {

    padding:
        12px;

    margin-bottom:
        12px;

    border-radius:
        8px;

    background:
        #eef4ff;

}


.footer {

    text-align:
        center;

    padding:
        30px;

    color:
        #687386;

}


.alert {

    padding:
        14px;

    border-radius:
        8px;

    background:
        #fff4e5;

    margin-bottom:
        15px;

}


.answer-box {

    white-space:
        pre-wrap;

    line-height:
        1.6;

    background:
        #f7f9fc;

    border-radius:
        8px;

    padding:
        18px;

}


@media(max-width:600px) {

    table {

        display:
            block;

        overflow-x:
            auto;

    }


    .nav-inner {

        align-items:
            flex-start;

    }

}

</style>

</head>


<body>


<div class="nav">

<div class="nav-inner">


<div class="brand">
KOJA AFRICA
</div>


<div>


<a href="{{ url_for('home') }}">
Home
</a>


{% if session.get('user') %}


<a href="{{ url_for('dashboard') }}">
Dashboard
</a>


<a href="{{ url_for('new_assignment') }}">
Ask Question
</a>


<a href="{{ url_for('assignments') }}">
My Assignments
</a>


<a href="{{ url_for('notifications') }}">
Notifications
</a>


{% if session.get('user', {}).get('is_admin') %}


<a href="{{ url_for('admin_dashboard') }}">
Admin
</a>


{% endif %}


<a href="{{ url_for('logout') }}">
Logout
</a>


{% else %}


<a href="{{ url_for('login') }}">
Login
</a>


<a href="{{ url_for('register') }}">
Register
</a>


{% endif %}


</div>


</div>

</div>


<div class="container">


{% with messages =
    get_flashed_messages(
        with_categories=true
    )
%}


{% for category, message in messages %}

<div class="flash">
{{ message }}
</div>

{% endfor %}


{% endwith %}


{{ body|safe }}


</div>


<div class="footer">

KOJA AFRICA

<br>

Assignment Questions • Academic Answers •
Learning Resources

</div>


</body>

</html>

"""


# ============================================================
# PAGE HELPER
# ============================================================

def page(
    title,
    body,
):

    return render_template_string(
        BASE_HTML,
        title=title,
        body=body,
    )


# ============================================================
# HOME
# ============================================================

@app.route("/")
def home():

    body = """

    <div class="card">

    <h1>KOJA AFRICA</h1>

    <p>
    Assignment Questions • Academic Answers •
    Learning Resources
    </p>

    <p>
    Submit academic questions, upload assignments
    and receive completed answers.
    </p>

    <a
        class="btn"
        href="/register"
    >
        Create Student Account
    </a>

    <a
        class="btn btn-dark"
        href="/login"
    >
        Login
    </a>

    </div>


    <div class="grid">


    <div class="card">

    <h3>
    Ask Questions
    </h3>

    <p>
    Send an academic question directly through
    your KOJA account.
    </p>

    </div>


    <div class="card">

    <h3>
    Upload Assignments
    </h3>

    <p>
    Upload PDF, Word, Excel, images or text
    question files.
    </p>

    </div>


    <div class="card">

    <h3>
    Download Answers
    </h3>

    <p>
    Completed answers can be downloaded in
    PDF, Word and Excel formats.
    </p>

    </div>


    </div>

    """

    return page(
        "Home",
        body
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

        name = request.form.get(
            "name",
            ""
        ).strip()


        email = request.form.get(
            "email",
            ""
        ).strip().lower()


        password = request.form.get(
            "password",
            ""
        )


        if (
            not name
            or not email
            or not password
        ):

            flash(
                "All fields are required.",
                "warning"
            )

            return redirect(
                url_for("register")
            )


        if len(password) < 6:

            flash(
                "Password must contain at least 6 characters.",
                "warning"
            )

            return redirect(
                url_for("register")
            )


        try:

            existing = find_profile(
                email
            )


            if existing:

                flash(
                    "An account with that email already exists.",
                    "warning"
                )

                return redirect(
                    url_for("login")
                )


            password_hash = (
                generate_password_hash(
                    password
                )
            )


            profile = create_profile(
                email=email,
                name=name,
                password_hash=password_hash,
                is_admin=False,
            )


            profile_id = (
                profile.get("id")
                if isinstance(profile, dict)
                else None
            )


            session.clear()


            session["user"] = {

                "id":
                    profile_id,

                "email":
                    email,

                "full_name":
                    name,

                "is_admin":
                    False,
            }


            log_activity(
                "register",
                "New student account created",
            )


            flash(
                "Account created successfully.",
                "success"
            )


            return redirect(
                url_for("dashboard")
            )


        except Exception as exc:

            logging.exception(
                "Registration error"
            )


            flash(
                f"Registration error: {exc}",
                "danger"
            )


    body = """

    <div class="card">

    <h1>
    Create Account
    </h1>


    <form
        method="post"
        autocomplete="on"
    >


    <label>
    Full name
    </label>


    <input
        type="text"
        name="name"
        required
        maxlength="150"
        placeholder="Your full name"
        autocomplete="name"
    >


    <label>
    Email
    </label>


    <input
        type="email"
        name="email"
        required
        maxlength="255"
        placeholder="you@example.com"
        autocomplete="email"
    >


    <label>
    Password
    </label>


    <input
        type="password"
        name="password"
        required
        minlength="6"
        maxlength="200"
        placeholder="At least 6 characters"
        autocomplete="new-password"
    >


    <button type="submit">
    Create Account
    </button>


    </form>


    <p>
    Already have an account?
    <a href="/login">
    Login
    </a>
    </p>


    </div>

    """

    return page(
        "Register",
        body
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

        email = request.form.get(
            "email",
            ""
        ).strip().lower()


        password = request.form.get(
            "password",
            ""
        )


        if (
            not email
            or not password
        ):

            flash(
                "Enter email and password.",
                "warning"
            )

            return redirect(
                url_for("login")
            )


        try:

            profile = verify_user(
                email,
                password
            )


            if not profile:

                # Emergency administrator login.
                #
                # These values should be changed
                # in Render Environment Variables.

                if (
                    email == ADMIN_EMAIL
                    and password == ADMIN_PASSWORD
                ):

                    session.clear()


                    session["user"] = {

                        "id":
                            "admin",

                        "email":
                            ADMIN_EMAIL,

                        "full_name":
                            "KOJA Administrator",

                        "is_admin":
                            True,
                    }


                    log_activity(
                        "admin_login",
                        "Emergency administrator login",
                    )


                    return redirect(
                        url_for(
                            "admin_dashboard"
                        )
                    )


                flash(
                    "Invalid email or password.",
                    "danger"
                )


                return redirect(
                    url_for("login")
                )


            session.clear()


            session["user"] = {

                "id":
                    profile.get("id"),

                "email":
                    profile.get("email"),

                "full_name":
                    profile.get(
                        "full_name",
                        profile.get(
                            "name",
                            ""
                        )
                    ),

                "is_admin":
                    bool(
                        profile.get(
                            "is_admin",
                            False
                        )
                    ),
            }


            log_activity(
                "login",
                "User logged in",
            )


            if profile.get(
                "is_admin"
            ):

                return redirect(
                    url_for(
                        "admin_dashboard"
                    )
                )


            return redirect(
                url_for("dashboard")
            )


        except Exception as exc:

            logging.exception(
                "Login error"
            )


            flash(
                f"Login error: {exc}",
                "danger"
            )


    body = """

    <div class="card">

    <h1>
    Login
    </h1>


    <form
        method="post"
        autocomplete="on"
    >


    <label>
    Email
    </label>


    <input
        type="email"
        name="email"
        required
        autocomplete="email"
    >


    <label>
    Password
    </label>


    <input
        type="password"
        name="password"
        required
        autocomplete="current-password"
    >


    <button type="submit">
    Login
    </button>


    </form>


    <p>
    Don't have an account?
    <a href="/register">
    Create one
    </a>
    </p>


    </div>

    """

    return page(
        "Login",
        body
    )


# ============================================================
# LOGOUT
# ============================================================

@app.route("/logout")
def logout():

    session.clear()


    flash(
        "You have been logged out.",
        "success"
    )


    return redirect(
        url_for("home")
    )


# ============================================================
# DASHBOARD
# ============================================================

@app.route("/dashboard")
@login_required
def dashboard():

    email = current_email()


    try:

        rows = db_select(
            "assignments",
            filters={
                "student_email":
                    f"eq.{email}"
            },
            limit=100,
            order="created_at.desc",
        )

    except Exception as exc:

        logging.exception(
            "Dashboard assignment query failed"
        )


        rows = []


        flash(
            f"Could not load assignments: {exc}",
            "danger"
        )


    pending = 0

    processing = 0

    completed = 0


    for item in rows:

        status = str(
            item.get(
                "status",
                ""
            )
        ).lower()


        if status == "pending":
            pending += 1

        elif status == "processing":
            processing += 1

        elif status == "completed":
            completed += 1


    user = current_user()


    name = safe_text(
        user.get(
            "full_name",
            "Student"
        )
    )


    body = f"""

    <div class="card">

    <h1>
    Welcome, {name}
    </h1>

    <p>
    Submit questions and manage your assignments.
    </p>

    </div>


    <div class="grid">


    <div class="stat">

    <strong>
    {len(rows)}
    </strong>

    Total Assignments

    </div>


    <div class="stat">

    <strong>
    {pending}
    </strong>

    Pending

    </div>


    <div class="stat">

    <strong>
    {processing}
    </strong>

    Processing

    </div>


    <div class="stat">

    <strong>
    {completed}
    </strong>

    Completed

    </div>


    </div>


    <div class="card">

    <h2>
    Quick Actions
    </h2>


    <a
        class="btn"
        href="/assignment/new"
    >
        Ask Question / Upload Assignment
    </a>


    <a
        class="btn btn-dark"
        href="/assignments"
    >
        View My Assignments
    </a>


    <a
        class="btn btn-dark"
        href="/notifications"
    >
        Notifications
    </a>


    </div>

    """


    return page(
        "Dashboard",
        body
    )


# ============================================================
# NEW ASSIGNMENT
# ============================================================

@app.route(
    "/assignment/new",
    methods=["GET", "POST"]
)
@login_required
def new_assignment():

    if request.method == "POST":

        title = request.form.get(
            "title",
            ""
        ).strip()


        subject = request.form.get(
            "subject",
            ""
        ).strip()


        question = request.form.get(
            "question",
            ""
        ).strip()


        file = request.files.get(
            "question_file"
        )


        if not title:

            title = (
                "Assignment Question"
            )


        if (
            not question
            and
            (
                not file
                or
                not file.filename
            )
        ):

            flash(
                "Enter a question or upload a question file.",
                "warning"
            )

            return redirect(
                url_for(
                    "new_assignment"
                )
            )


        # Validate file BEFORE creating
        # the assignment.

        file_bytes = None

        original_name = None

        extension = None

        content_type = None


        if file and file.filename:

            if not allowed_file(
                file.filename
            ):

                flash(
                    "Unsupported file type.",
                    "danger"
                )

                return redirect(
                    url_for(
                        "new_assignment"
                    )
                )


            file_bytes = file.read()


            if (
                len(file_bytes)
                >
                MAX_FILE_SIZE
            ):

                flash(
                    "File is too large. Maximum size is 15 MB.",
                    "danger"
                )

                return redirect(
                    url_for(
                        "new_assignment"
                    )
                )


            original_name = secure_filename(
                file.filename
            )


            if not original_name:

                flash(
                    "Invalid filename.",
                    "danger"
                )

                return redirect(
                    url_for(
                        "new_assignment"
                    )
                )


            extension = (
                original_name
                .rsplit(
                    ".",
                    1
                )[-1]
                .lower()
            )


            content_type = (
                file.content_type
                or
                "application/octet-stream"
            )


        try:

            assignment_data = {

                "student_email":
                    current_email(),

                "title":
                    title,

                "subject":
                    subject,

                "question":
                    question,

                "status":
                    "Pending",

                "created_at":
                    utc_now(),

                "updated_at":
                    utc_now(),
            }


            try:

                result = db_insert(
                    "assignments",
                    assignment_data,
                )


            except Exception as first_error:

                logging.exception(
                    "Full assignment insert failed"
                )


                # Compatibility fallback
                # for databases missing
                # optional columns.

                fallback = {

                    "student_email":
                        current_email(),

                    "title":
                        title,

                    "question":
                        question,

                    "status":
                        "Pending",
                }


                try:

                    result = db_insert(
                        "assignments",
                        fallback,
                    )


                except Exception:

                    raise first_error


            if (
                not result
                or
                not isinstance(
                    result,
                    list
                )
            ):

                raise RuntimeError(
                    "Assignment was not created."
                )


            assignment = result[0]


            assignment_id = (
                assignment.get("id")
            )


            if not assignment_id:

                raise RuntimeError(
                    "Assignment was created but Supabase did not return an ID."
                )


            # ------------------------------------------------
            # UPLOAD QUESTION FILE
            # ------------------------------------------------

            if file_bytes is not None:

                storage_path = (

                    f"questions/"
                    f"{assignment_id}/"
                    f"{uuid.uuid4().hex}."
                    f"{extension}"
                )


                storage_upload(
                    file_bytes,
                    storage_path,
                    content_type,
                )


                try:

                    save_assignment_file(
                        assignment_id,
                        original_name,
                        storage_path,
                        content_type,
                        len(file_bytes),
                        "question",
                    )

                except Exception:

                    # If database record fails,
                    # remove uploaded file.

                    storage_delete(
                        storage_path
                    )

                    raise


            log_activity(
                "assignment_created",
                (
                    f"Assignment "
                    f"{assignment_id} submitted"
                ),
            )


            flash(
                "Assignment submitted successfully.",
                "success"
            )


            return redirect(
                url_for(
                    "assignment_detail",
                    assignment_id=assignment_id,
                )
            )


        except Exception as exc:

            logging.exception(
                "Assignment creation failed"
            )


            flash(
                f"Could not submit assignment: {exc}",
                "danger"
            )


    body = """

    <div class="card">

    <h1>
    Assignment Request
    </h1>


    <p>
    Ask a question or upload your assignment.
    </p>


    <form
        method="post"
        enctype="multipart/form-data"
    >


    <label>
    Assignment title
    </label>


    <input
        name="title"
        maxlength="200"
        placeholder="Example: Chemistry Assignment 1"
    >


    <label>
    Subject
    </label>


    <input
        name="subject"
        maxlength="150"
        placeholder="Example: Chemistry"
    >


    <label>
    Ask your question
    </label>


    <textarea
        name="question"
        placeholder="Type your assignment question here..."
    ></textarea>


    <label>
    Upload question
    </label>


    <input
        type="file"
        name="question_file"
        accept=".pdf,.doc,.docx,.xls,.xlsx,.png,.jpg,.jpeg,.webp,.txt"
    >


    <p>
    Supported:
    PDF, Word, Excel, images and text files.
    Maximum: 15 MB.
    </p>


    <button type="submit">
    Submit Assignment
    </button>


    </form>


    </div>

    """


    return page(
        "Assignment Request",
        body
    )


# ============================================================
# ASSIGNMENTS
# ============================================================

@app.route("/assignments")
@login_required
def assignments():

    email = current_email()


    try:

        rows = db_select(
            "assignments",
            filters={
                "student_email":
                    f"eq.{email}"
            },
            limit=200,
            order="created_at.desc",
        )


    except Exception as exc:

        logging.exception(
            "Assignment listing failed"
        )


        flash(
            f"Could not load assignments: {exc}",
            "danger"
        )


        rows = []


    html = """

    <div class="card">

    <h1>
    My Assignments
    </h1>


    <a
        class="btn"
        href="/assignment/new"
    >
        New Assignment
    </a>


    </div>

    """


    if not rows:

        html += """

        <div class="card">

        <p>
        No assignments submitted yet.
        </p>

        </div>

        """


    else:

        html += """

        <div class="card">

        <table>

        <tr>

        <th>
        Title
        </th>

        <th>
        Subject
        </th>

        <th>
        Status
        </th>

        <th>
        Date
        </th>

        <th>
        </th>

        </tr>

        """


        for item in rows:

            assignment_id = safe_text(
                item.get(
                    "id",
                    ""
                )
            )


            title = safe_text(
                item.get(
                    "title",
                    "Assignment"
                )
            )


            subject = safe_text(
                item.get(
                    "subject",
                    ""
                )
            )


            status = safe_text(
                item.get(
                    "status",
                    "Pending"
                )
            )


            created = safe_text(
                item.get(
                    "created_at",
                    ""
                )
            )


            html += f"""

            <tr>

            <td>
            {title}
            </td>


            <td>
            {subject}
            </td>


            <td>

            <span class="badge">
            {status}
            </span>

            </td>


            <td>
            {created}
            </td>


            <td>

            <a
                class="btn"
                href="/assignment/{assignment_id}"
            >
                Open
            </a>

            </td>


            </tr>

            """


        html += """

        </table>

        </div>

        """


    return page(
        "My Assignments",
        html
    )


# ============================================================
# ASSIGNMENT DETAIL
# ============================================================

@app.route(
    "/assignment/<assignment_id>"
)
@login_required
def assignment_detail(
    assignment_id
):

    try:

        rows = db_select(
            "assignments",
            filters={
                "id":
                    f"eq.{assignment_id}",

                "student_email":
                    f"eq.{current_email()}",
            },
            limit=1,
        )


        if not rows:
            abort(404)


        assignment = rows[0]


        files = db_select(
            "assignment_files",
            filters={
                "assignment_id":
                    f"eq.{assignment_id}"
            },
            limit=100,
            order="created_at.desc",
        )


    except Exception as exc:

        logging.exception(
            "Assignment detail error"
        )


        flash(
            f"Could not load assignment: {exc}",
            "danger"
        )


        return redirect(
            url_for("assignments")
        )


    title = safe_text(
        assignment.get(
            "title",
            "Assignment"
        )
    )


    subject = safe_text(
        assignment.get(
            "subject",
            ""
        )
    )


    status = safe_text(
        assignment.get(
            "status",
            "Pending"
        )
    )


    question = safe_text(
        assignment.get(
            "question",
            ""
        )
    ).replace(
        "\n",
        "<br>"
    )


    html = f"""

    <div class="card">

    <h1>
    {title}
    </h1>


    <p>
    <b>Subject:</b>
    {subject}
    </p>


    <p>
    <b>Status:</b>

    <span class="badge">
    {status}
    </span>

    </p>


    <h2>
    Question
    </h2>


    <div class="card">

    {question}

    </div>


    </div>

    """


    if files:

        html += """

        <div class="card">

        <h2>
        Files
        </h2>

        """


        for file_record in files:

            file_id = safe_text(
                file_record.get(
                    "id",
                    ""
                )
            )


            name = safe_text(
                file_record.get(
                    "original_filename",
                    "File"
                )
            )


            role = safe_text(
                file_record.get(
                    "file_role",
                    "question"
                )
            )


            html += f"""

            <p>

            <b>
            {name}
            </b>

            ({role})


            <a
                class="btn"
                href="/file/{file_id}"
            >
                Download
            </a>


            </p>

            """


        html += """

        </div>

        """


    assignment_status = str(
        assignment.get(
            "status",
            ""
        )
    ).lower()


    if assignment_status == "completed":

        answer = assignment.get(
            "answer",
            ""
        )


        html += """

        <div class="card">

        <h2>
        Completed Answer
        </h2>

        <p>
        Your assignment has been completed.
        </p>

        """


        if answer:

            answer_html = safe_text(
                answer
            ).replace(
                "\n",
                "<br>"
            )


            html += f"""

            <div class="answer-box">

            {answer_html}

            </div>

            """


        html += f"""

        <br>


        <a
            class="btn"
            href="/answer/{assignment_id}/pdf"
        >
            Download PDF
        </a>


        <a
            class="btn btn-green"
            href="/answer/{assignment_id}/docx"
        >
            Download Word
        </a>


        <a
            class="btn btn-dark"
            href="/answer/{assignment_id}/xlsx"
        >
            Download Excel
        </a>


        </div>

        """


    return page(
        "Assignment",
        html
    )


# ============================================================
# QUESTION FILE DOWNLOAD
# ============================================================

@app.route(
    "/file/<file_id>"
)
@login_required
def download_question_file(
    file_id
):

    try:

        files = db_select(
            "assignment_files",
            filters={
                "id":
                    f"eq.{file_id}"
            },
            limit=1,
        )


        if not files:
            abort(404)


        file_record = files[0]


        assignment_id = (
            file_record.get(
                "assignment_id"
            )
        )


        if not assignment_id:
            abort(404)


        assignments_rows = db_select(
            "assignments",
            filters={
                "id":
                    f"eq.{assignment_id}"
            },
            limit=1,
        )


        if not assignments_rows:
            abort(404)


        assignment = (
            assignments_rows[0]
        )


        user = current_user()


        if (
            not user.get("is_admin")
            and
            assignment.get(
                "student_email"
            )
            !=
            current_email()
        ):

            abort(403)


        content = storage_download(
            file_record.get(
                "storage_path"
            )
        )


        filename = (
            file_record.get(
                "original_filename",
                "download"
            )
        )


        content_type = (
            file_record.get(
                "content_type",
                "application/octet-stream"
            )
        )


        return send_file(
            io.BytesIO(content),
            as_attachment=True,
            download_name=filename,
            mimetype=content_type,
        )


    except Exception as exc:

        logging.exception(
            "File download error"
        )


        flash(
            f"File download failed: {exc}",
            "danger"
        )


        return redirect(
            url_for("assignments")
        )


# ============================================================
# ADMIN DASHBOARD
# ============================================================

@app.route("/admin")
@admin_required
def admin_dashboard():

    try:

        assignments_rows = db_select(
            "assignments",
            limit=500,
            order="created_at.desc",
        )


    except Exception as exc:

        logging.exception(
            "Admin assignment query failed"
        )


        assignments_rows = []


        flash(
            f"Could not load assignments: {exc}",
            "danger"
        )


    try:

        profiles = db_select(
            "profiles",
            limit=500,
            order="created_at.desc",
        )


    except Exception as exc:

        logging.exception(
            "Admin profiles query failed"
        )


        profiles = []


    pending = 0

    processing = 0

    completed = 0


    for item in assignments_rows:

        status = str(
            item.get(
                "status",
                ""
            )
        ).lower()


        if status == "pending":
            pending += 1

        elif status == "processing":
            processing += 1

        elif status == "completed":
            completed += 1


    html = f"""

    <div class="card">

    <h1>
    KOJA AFRICA Admin
    </h1>


    <div class="grid">


    <div class="stat">

    <strong>
    {len(profiles)}
    </strong>

    Users

    </div>


    <div class="stat">

    <strong>
    {len(assignments_rows)}
    </strong>

    Assignments

    </div>


    <div class="stat">

    <strong>
    {pending}
    </strong>

    Pending

    </div>


    <div class="stat">

    <strong>
    {processing}
    </strong>

    Processing

    </div>


    <div class="stat">

    <strong>
    {completed}
    </strong>

    Completed

    </div>


    </div>


    </div>


    <div class="card">

    <h2>
    Assignment Requests
    </h2>

    """


    if not assignments_rows:

        html += """

        <p>
        No assignments.
        </p>

        """


    else:

        html += """

        <table>

        <tr>

        <th>
        Student
        </th>

        <th>
        Title
        </th>

        <th>
        Subject
        </th>

        <th>
        Status
        </th>

        <th>
        Action
        </th>

        </tr>

        """


        for item in assignments_rows:

            aid = safe_text(
                item.get(
                    "id",
                    ""
                )
            )


            student_email = safe_text(
                item.get(
                    "student_email",
                    ""
                )
            )


            title = safe_text(
                item.get(
                    "title",
                    ""
                )
            )


            subject = safe_text(
                item.get(
                    "subject",
                    ""
                )
            )


            status = safe_text(
                item.get(
                    "status",
                    "Pending"
                )
            )


            html += f"""

            <tr>


            <td>
            {student_email}
            </td>


            <td>
            {title}
            </td>


            <td>
            {subject}
            </td>


            <td>

            <span class="badge">
            {status}
            </span>

            </td>


            <td>

            <a
                class="btn"
                href="/admin/assignment/{aid}"
            >
                Process
            </a>

            </td>


            </tr>

            """


        html += """

        </table>

        """


    html += """

    </div>

    """


    return page(
        "Admin Dashboard",
        html
    )


# ============================================================
# ADMIN PROCESS ASSIGNMENT
# ============================================================

@app.route(
    "/admin/assignment/<assignment_id>",
    methods=["GET", "POST"]
)
@admin_required
def admin_assignment(
    assignment_id
):

    try:

        rows = db_select(
            "assignments",
            filters={
                "id":
                    f"eq.{assignment_id}"
            },
            limit=1,
        )


        if not rows:
            abort(404)


        assignment = rows[0]


    except Exception as exc:

        flash(
            f"Could not load assignment: {exc}",
            "danger"
        )


        return redirect(
            url_for(
                "admin_dashboard"
            )
        )


    if request.method == "POST":

        action = request.form.get(
            "action",
            ""
        )


        # ----------------------------------------------------
        # MARK PROCESSING
        # ----------------------------------------------------

        if action == "processing":

            try:

                db_update(
                    "assignments",
                    {
                        "id":
                            f"eq.{assignment_id}"
                    },
                    {
                        "status":
                            "Processing",

                        "updated_at":
                            utc_now(),
                    },
                )


                log_activity(
                    "assignment_processing",
                    (
                        f"{assignment_id} "
                        f"moved to processing"
                    ),
                )


                flash(
                    "Assignment marked as processing.",
                    "success"
                )


            except Exception as exc:

                logging.exception(
                    "Status update failed"
                )


                flash(
                    f"Could not update status: {exc}",
                    "danger"
                )


            return redirect(
                url_for(
                    "admin_assignment",
                    assignment_id=
                        assignment_id,
                )
            )


        # ----------------------------------------------------
        # COMPLETE ASSIGNMENT
        # ----------------------------------------------------

        if action == "complete":

            answer = request.form.get(
                "answer",
                ""
            ).strip()


            if not answer:

                flash(
                    "Enter the answer before completing the assignment.",
                    "warning"
                )


                return redirect(
                    url_for(
                        "admin_assignment",
                        assignment_id=
                            assignment_id,
                    )
                )


            try:

                db_update(
                    "assignments",
                    {
                        "id":
                            f"eq.{assignment_id}"
                    },
                    {
                        "answer":
                            answer,

                        "status":
                            "Completed",

                        "updated_at":
                            utc_now(),

                        "completed_at":
                            utc_now(),
                    },
                )


                # ------------------------------------------------
                # NOTIFICATION
                # ------------------------------------------------

                notification = {

                    "student_email":
                        assignment.get(
                            "student_email"
                        ),

                    "title":
                        "Assignment Completed",

                    "message":
                        (
                            "Your assignment answer "
                            "is ready for download."
                        ),

                    "created_at":
                        utc_now(),
                }


                try:

                    db_insert(
                        "notifications",
                        notification,
                        returning=False,
                    )


                except Exception:

                    logging.exception(
                        "Notification creation failed"
                    )


                log_activity(
                    "assignment_completed",
                    (
                        f"{assignment_id} "
                        f"completed"
                    ),
                )


                flash(
                    "Assignment completed successfully.",
                    "success"
                )


                return redirect(
                    url_for(
                        "admin_assignment",
                        assignment_id=
                            assignment_id,
                    )
                )


            except Exception as exc:

                logging.exception(
                    "Assignment completion failed"
                )


                flash(
                    f"Could not complete assignment: {exc}",
                    "danger"
                )


    try:

        files = db_select(
            "assignment_files",
            filters={
                "assignment_id":
                    f"eq.{assignment_id}"
            },
            limit=100,
            order="created_at.desc",
        )


    except Exception:

        logging.exception(
            "Admin file query failed"
        )


        files = []


    student_email = safe_text(
        assignment.get(
            "student_email",
            ""
        )
    )


    title = safe_text(
        assignment.get(
            "title",
            ""
        )
    )


    subject = safe_text(
        assignment.get(
            "subject",
            ""
        )
    )


    status = safe_text(
        assignment.get(
            "status",
            "Pending"
        )
    )


    question = safe_text(
        assignment.get(
            "question",
            ""
        )
    ).replace(
        "\n",
        "<br>"
    )


    existing_answer = safe_text(
        assignment.get(
            "answer",
            ""
        )
    )


    html = f"""

    <div class="card">

    <h1>
    Process Assignment
    </h1>


    <p>
    <b>Student:</b>
    {student_email}
    </p>


    <p>
    <b>Title:</b>
    {title}
    </p>


    <p>
    <b>Subject:</b>
    {subject}
    </p>


    <p>
    <b>Status:</b>

    <span class="badge">
    {status}
    </span>

    </p>


    <h2>
    Question
    </h2>


    <div class="card">

    {question}

    </div>

    """


    if files:

        html += """

        <h2>
        Uploaded Files
        </h2>

        """


        for file_record in files:

            file_id = safe_text(
                file_record.get(
                    "id",
                    ""
                )
            )


            filename = safe_text(
                file_record.get(
                    "original_filename",
                    "File"
                )
            )


            html += f"""

            <p>

            <b>
            {filename}
            </b>


            <a
                class="btn"
                href="/file/{file_id}"
            >
                Download
            </a>

            </p>

            """


    html += f"""

    <hr>


    <form method="post">

    <input
        type="hidden"
        name="action"
        value="processing"
    >


    <button type="submit">
    Mark Processing
    </button>


    </form>


    <h2>
    Write Answer
    </h2>


    <form method="post">

    <input
        type="hidden"
        name="action"
        value="complete"
    >


    <textarea
        name="answer"
        placeholder="Write the completed academic answer here..."
        required
    >{existing_answer}</textarea>


    <button
        type="submit"
        class="btn-green"
    >
    Complete Assignment
    </button>


    </form>


    </div>

    """


    return page(
        "Process Assignment",
        html
    )


# ============================================================
# GET COMPLETED ASSIGNMENT
# ============================================================

def get_completed_assignment(
    assignment_id
):

    rows = db_select(
        "assignments",
        filters={
            "id":
                f"eq.{assignment_id}"
        },
        limit=1,
    )


    if not rows:
        abort(404)


    assignment = rows[0]


    user = current_user()


    if (
        not user.get("is_admin")
        and
        assignment.get(
            "student_email"
        )
        !=
        current_email()
    ):

        abort(403)


    if (
        str(
            assignment.get(
                "status",
                ""
            )
        ).lower()
        !=
        "completed"
    ):

        flash(
            "This assignment has not been completed yet.",
            "warning"
        )

        abort(404)


    return assignment


# ============================================================
# ANSWER PDF
# ============================================================

@app.route(
    "/answer/<assignment_id>/pdf"
)
@login_required
def answer_pdf(
    assignment_id
):

    assignment = (
        get_completed_assignment(
            assignment_id
        )
    )


    data = build_pdf(

        assignment.get(
            "title",
            "Assignment Answer"
        ),

        assignment.get(
            "student_email",
            ""
        ),

        assignment.get(
            "question",
            ""
        ),

        assignment.get(
            "answer",
            ""
        ),
    )


    log_download(
        assignment_id,
        "pdf"
    )


    return send_file(

        io.BytesIO(data),

        as_attachment=True,

        download_name=(
            f"KOJA-Answer-"
            f"{assignment_id}.pdf"
        ),

        mimetype=
            "application/pdf",
    )


# ============================================================
# ANSWER WORD
# ============================================================

@app.route(
    "/answer/<assignment_id>/docx"
)
@login_required
def answer_docx(
    assignment_id
):

    assignment = (
        get_completed_assignment(
            assignment_id
        )
    )


    data = build_docx(

        assignment.get(
            "title",
            "Assignment Answer"
        ),

        assignment.get(
            "student_email",
            ""
        ),

        assignment.get(
            "question",
            ""
        ),

        assignment.get(
            "answer",
            ""
        ),
    )


    log_download(
        assignment_id,
        "docx"
    )


    return send_file(

        io.BytesIO(data),

        as_attachment=True,

        download_name=(
            f"KOJA-Answer-"
            f"{assignment_id}.docx"
        ),

        mimetype=(
            "application/vnd.openxmlformats-officedocument."
            "wordprocessingml.document"
        ),
    )


# ============================================================
# ANSWER EXCEL
# ============================================================

@app.route(
    "/answer/<assignment_id>/xlsx"
)
@login_required
def answer_xlsx(
    assignment_id
):

    assignment = (
        get_completed_assignment(
            assignment_id
        )
    )


    data = build_xlsx(

        assignment.get(
            "title",
            "Assignment Answer"
        ),

        assignment.get(
            "student_email",
            ""
        ),

        assignment.get(
            "question",
            ""
        ),

        assignment.get(
            "answer",
            ""
        ),
    )


    log_download(
        assignment_id,
        "xlsx"
    )


    return send_file(

        io.BytesIO(data),

        as_attachment=True,

        download_name=(
            f"KOJA-Answer-"
            f"{assignment_id}.xlsx"
        ),

        mimetype=(
            "application/vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet"
        ),
    )


# ============================================================
# NOTIFICATIONS
# ============================================================

@app.route(
    "/notifications"
)
@login_required
def notifications():

    try:

        rows = db_select(
            "notifications",
            filters={
                "student_email":
                    f"eq.{current_email()}"
            },
            limit=100,
            order="created_at.desc",
        )


    except Exception as exc:

        logging.exception(
            "Notification query failed"
        )


        rows = []


        flash(
            f"Could not load notifications: {exc}",
            "danger"
        )


    html = """

    <div class="card">

    <h1>
    Notifications
    </h1>

    """


    if not rows:

        html += """

        <p>
        No notifications.
        </p>

        """


    else:

        for notification in rows:

            title = safe_text(
                notification.get(
                    "title",
                    "Notification"
                )
            )


            message = safe_text(
                notification.get(
                    "message",
                    ""
                )
            )


            created = safe_text(
                notification.get(
                    "created_at",
                    ""
                )
            )


            html += f"""

            <div class="card">

            <h3>
            {title}
            </h3>


            <p>
            {message}
            </p>


            <small>
            {created}
            </small>


            </div>

            """


    html += """

    </div>

    """


    return page(
        "Notifications",
        html
    )


# ============================================================
# HEALTH CHECK
# ============================================================

@app.route(
    "/health"
)
def health():

    result = {

        "status":
            "ok",

        "application":
            APP_NAME,

        "time":
            utc_now(),

        "supabase_configured":
            bool(
                SUPABASE_URL
                and
                SUPABASE_SERVICE_KEY
            ),

        "storage_bucket":
            STORAGE_BUCKET,
    }


    return result


# ============================================================
# DATABASE HEALTH CHECK
# ============================================================

@app.route(
    "/health/database"
)
def database_health():

    result = {

        "application":
            APP_NAME,

        "supabase_configured":
            bool(
                SUPABASE_URL
                and
                SUPABASE_SERVICE_KEY
            ),

        "database":
            "unknown",
    }


    try:

        db_select(
            "profiles",
            columns="id",
            limit=1,
        )


        result["database"] = (
            "connected"
        )


        return result


    except Exception as exc:

        result["database"] = (
            "error"
        )


        result["error"] = str(
            exc
        )


        return result, 500


# ============================================================
# 404
# ============================================================

@app.errorhandler(404)
def error_404(error):

    return page(

        "Page Not Found",

        """

        <div class="card">

        <h1>
        404
        </h1>


        <p>
        The requested page was not found.
        </p>


        <a
            class="btn"
            href="/"
        >
            Return Home
        </a>


        </div>

        """

    ), 404


# ============================================================
# 403
# ============================================================

@app.errorhandler(403)
def error_403(error):

    return page(

        "Access Denied",

        """

        <div class="card">

        <h1>
        Access Denied
        </h1>


        <p>
        You do not have permission to access
        this resource.
        </p>


        <a
            class="btn"
            href="/"
        >
            Return Home
        </a>


        </div>

        """

    ), 403


# ============================================================
# 413
# ============================================================

@app.errorhandler(413)
def error_413(error):

    return page(

        "File Too Large",

        """

        <div class="card">

        <h1>
        File Too Large
        </h1>


        <p>
        The maximum upload size is 15 MB.
        </p>


        <a
            class="btn"
            href="/assignment/new"
        >
            Try Again
        </a>


        </div>

        """

    ), 413


# ============================================================
# 500
# ============================================================

@app.errorhandler(500)
def error_500(error):

    logging.exception(
        "Unhandled application error"
    )


    return page(

        "Application Error",

        """

        <div class="card">

        <h1>
        Application Error
        </h1>


        <p>
        KOJA AFRICA encountered an internal error.
        </p>


        <p>
        Please try again.
        </p>


        <a
            class="btn"
            href="/"
        >
            Return Home
        </a>


        </div>

        """

    ), 500


# ============================================================
# START APPLICATION
# ============================================================

if __name__ == "__main__":

    port = int(
        os.environ.get(
            "PORT",
            "10000"
        )
    )


    app.run(
        host="0.0.0.0",
        port=port,
        debug=False,
    )
