# ============================================================
# KOJA AFRICA
# KNOWLEDGE • QUESTIONS • ANSWERS
#
# SINGLE FILE FLASK APPLICATION
#
# DATABASE:
#   Supabase PostgreSQL REST API
#
# STORAGE:
#   Supabase Storage
#
# PAYMENTS:
#   Flutterwave
#   Zambia Mobile Money:
#       MTN
#       Airtel
#       Zamtel
#
# DEPLOYMENT:
#   Render
#   Railway
#   VPS
#   Pydroid 3
#
# NO SQLITE
# NO psycopg
# NO psycopg2
#
# ============================================================

import os
import uuid
import mimetypes
import requests
import hmac
import hashlib
import base64

from decimal import Decimal, InvalidOperation
from datetime import datetime, timezone
from functools import wraps

from flask import (
    Flask,
    request,
    redirect,
    url_for,
    flash,
    session,
    abort,
    Response,
    render_template_string
)

from werkzeug.security import (
    generate_password_hash,
    check_password_hash
)

from werkzeug.utils import secure_filename


# ============================================================
# APPLICATION CONFIGURATION
# ============================================================

APP_NAME = "KOJA AFRICA"

APP_TAGLINE = (
    "Assignment Questions • Academic Answers • Learning Resources"
)


# ============================================================
# SUPABASE CONFIGURATION
# ============================================================

SUPABASE_URL = os.environ.get(
    "SUPABASE_URL",
    ""
).strip().rstrip("/")


SUPABASE_SERVICE_KEY = os.environ.get(
    "SUPABASE_SERVICE_KEY",
    ""
).strip()


if not SUPABASE_SERVICE_KEY:

    SUPABASE_SERVICE_KEY = os.environ.get(
        "SUPABASE_SERVICE_ROLE_KEY",
        ""
    ).strip()


if not SUPABASE_SERVICE_KEY:

    SUPABASE_SERVICE_KEY = os.environ.get(
        "sb_se",
        ""
    ).strip()


# ============================================================
# SUPABASE STORAGE
# ============================================================

STORAGE_BUCKET = os.environ.get(
    "KOJA_STORAGE_BUCKET",
    "koja-assignments"
).strip()


# ============================================================
# FLASK SECURITY
# ============================================================

SECRET_KEY = os.environ.get(
    "KOJA_SECRET_KEY",
    ""
).strip()


if not SECRET_KEY:

    SECRET_KEY = os.urandom(32)


# ============================================================
# FLUTTERWAVE
# ============================================================

FLW_SECRET_KEY = os.environ.get(
    "FLW_SECRET_KEY",
    ""
).strip()


FLW_SECRET_HASH = os.environ.get(
    "FLW_SECRET_HASH",
    ""
).strip()


try:

    KOJA_PAYMENT_AMOUNT = Decimal(
        os.environ.get(
            "KOJA_PAYMENT_AMOUNT",
            "10"
        ).strip()
    )

except (
    InvalidOperation,
    ValueError
):

    KOJA_PAYMENT_AMOUNT = Decimal(
        "10.00"
    )


FLW_API_URL = (
    "https://api.flutterwave.com/v3"
)


# Zambia mobile-money networks
ZAMBIA_NETWORKS = [
    "MTN",
    "Airtel",
    "Zamtel"
]


# ============================================================
# SERVER
# ============================================================

HOST = os.environ.get(
    "HOST",
    "0.0.0.0"
)


try:

    PORT = int(
        os.environ.get(
            "PORT",
            "5000"
        )
    )

except ValueError:

    PORT = 5000


# ============================================================
# HTTPS
# ============================================================

HTTPS_ENABLED = (
    os.environ.get(
        "KOJA_HTTPS",
        "0"
    ).strip() == "1"
)


# ============================================================
# FLASK
# ============================================================

app = Flask(__name__)

app.secret_key = SECRET_KEY

app.config[
    "MAX_CONTENT_LENGTH"
] = 10 * 1024 * 1024

app.config[
    "SESSION_COOKIE_HTTPONLY"
] = True

app.config[
    "SESSION_COOKIE_SAMESITE"
] = "Lax"

app.config[
    "SESSION_COOKIE_SECURE"
] = HTTPS_ENABLED


# ============================================================
# AFRICAN COUNTRIES
# ============================================================

AFRICAN_COUNTRIES = [
    "Algeria",
    "Angola",
    "Benin",
    "Botswana",
    "Burkina Faso",
    "Burundi",
    "Cabo Verde",
    "Cameroon",
    "Central African Republic",
    "Chad",
    "Comoros",
    "Democratic Republic of the Congo",
    "Republic of the Congo",
    "Côte d'Ivoire",
    "Djibouti",
    "Egypt",
    "Equatorial Guinea",
    "Eritrea",
    "Eswatini",
    "Ethiopia",
    "Gabon",
    "Gambia",
    "Ghana",
    "Guinea",
    "Guinea-Bissau",
    "Kenya",
    "Lesotho",
    "Liberia",
    "Libya",
    "Madagascar",
    "Malawi",
    "Mali",
    "Mauritania",
    "Mauritius",
    "Morocco",
    "Mozambique",
    "Namibia",
    "Niger",
    "Nigeria",
    "Rwanda",
    "São Tomé and Príncipe",
    "Senegal",
    "Seychelles",
    "Sierra Leone",
    "Somalia",
    "South Africa",
    "South Sudan",
    "Sudan",
    "Tanzania",
    "Togo",
    "Tunisia",
    "Uganda",
    "Zambia",
    "Zimbabwe"
]


# ============================================================
# SUBJECTS
# ============================================================

SUBJECTS = [
    "Mathematics",
    "English",
    "Chemistry",
    "Biology",
    "Physics",
    "Computer Science",
    "Information Technology",
    "Engineering",
    "Agriculture",
    "Business",
    "Accounting",
    "Economics",
    "Education",
    "Geography",
    "History",
    "Civic Education",
    "Law",
    "Medicine",
    "Nursing",
    "Social Sciences",
    "Environmental Science",
    "Other"
]


# ============================================================
# ALLOWED FILE TYPES
# ============================================================

ALLOWED_EXTENSIONS = {
    "jpg",
    "jpeg",
    "png",
    "gif",
    "webp",
    "pdf",
    "doc",
    "docx",
    "txt",
    "ppt",
    "pptx",
    "xls",
    "xlsx"
}


# ============================================================
# DATABASE HELPERS
# ============================================================

def database_ready():

    return bool(
        SUPABASE_URL
        and SUPABASE_SERVICE_KEY
        and SUPABASE_URL.startswith(
            "https://"
        )
    )


def db_headers():

    return {
        "apikey":
            SUPABASE_SERVICE_KEY,

        "Authorization":
            "Bearer "
            + SUPABASE_SERVICE_KEY,

        "Content-Type":
            "application/json",

        "Accept":
            "application/json"
    }


def rest_url(table):

    return (
        SUPABASE_URL
        + "/rest/v1/"
        + table
    )


def db_select(
    table,
    params=None
):

    if not database_ready():

        raise RuntimeError(
            "Supabase is not configured."
        )

    response = requests.get(
        rest_url(table),
        headers=db_headers(),
        params=params or {},
        timeout=30
    )

    if not response.ok:

        raise RuntimeError(
            "Database SELECT failed: "
            + response.text
        )

    try:

        return response.json()

    except Exception:

        return []


def db_insert(
    table,
    data
):

    if not database_ready():

        raise RuntimeError(
            "Supabase is not configured."
        )

    headers = db_headers()

    headers["Prefer"] = (
        "return=representation"
    )

    response = requests.post(
        rest_url(table),
        headers=headers,
        json=data,
        timeout=30
    )

    if not response.ok:

        raise RuntimeError(
            "Database INSERT failed: "
            + response.text
        )

    try:

        return response.json()

    except Exception:

        return []


def db_update(
    table,
    filters,
    data
):

    if not database_ready():

        raise RuntimeError(
            "Supabase is not configured."
        )

    params = {}

    for key, value in filters.items():

        params[key] = (
            "eq."
            + str(value)
        )

    headers = db_headers()

    headers["Prefer"] = (
        "return=representation"
    )

    response = requests.patch(
        rest_url(table),
        headers=headers,
        params=params,
        json=data,
        timeout=30
    )

    if not response.ok:

        raise RuntimeError(
            "Database UPDATE failed: "
            + response.text
        )

    try:

        return response.json()

    except Exception:

        return []


def db_delete(
    table,
    filters
):

    if not database_ready():

        raise RuntimeError(
            "Supabase is not configured."
        )

    params = {}

    for key, value in filters.items():

        params[key] = (
            "eq."
            + str(value)
        )

    response = requests.delete(
        rest_url(table),
        headers=db_headers(),
        params=params,
        timeout=30
    )

    if not response.ok:

        raise RuntimeError(
            "Database DELETE failed: "
            + response.text
        )

    return True


# ============================================================
# TIME
# ============================================================

def current_time():

    return datetime.now(
        timezone.utc
    ).isoformat()


# ============================================================
# USER FUNCTIONS
# ============================================================

def get_user_by_username(
    username,
    role=None
):

    params = {
        "username":
            "eq."
            + username,

        "select":
            "*",

        "limit":
            "1"
    }

    if role:

        params["role"] = (
            "eq."
            + role
        )

    rows = db_select(
        "users",
        params
    )

    return (
        rows[0]
        if rows
        else None
    )


def get_user_by_id(
    user_id
):

    rows = db_select(
        "users",
        {
            "id":
                "eq."
                + str(user_id),

            "select":
                "*",

            "limit":
                "1"
        }
    )

    return (
        rows[0]
        if rows
        else None
    )


def email_exists(
    email
):

    rows = db_select(
        "users",
        {
            "email":
                "eq."
                + email,

            "select":
                "id",

            "limit":
                "1"
        }
    )

    return bool(rows)


# ============================================================
# QUESTION FUNCTIONS
# ============================================================

def get_question(
    question_id
):

    rows = db_select(
        "questions",
        {
            "id":
                "eq."
                + str(question_id),

            "select":
                "*",

            "limit":
                "1"
        }
    )

    return (
        rows[0]
        if rows
        else None
    )


def get_student_question(
    question_id,
    user_id
):

    rows = db_select(
        "questions",
        {
            "id":
                "eq."
                + str(question_id),

            "user_id":
                "eq."
                + str(user_id),

            "select":
                "*",

            "limit":
                "1"
        }
    )

    return (
        rows[0]
        if rows
        else None
    )


def get_answer(
    question_id
):

    rows = db_select(
        "answers",
        {
            "question_id":
                "eq."
                + str(question_id),

            "select":
                "*",

            "limit":
                "1"
        }
    )

    return (
        rows[0]
        if rows
        else None
    )


# ============================================================
# STORAGE
# ============================================================

def allowed_file(
    filename
):

    if not filename:
        return False

    if "." not in filename:
        return False

    extension = (
        filename
        .rsplit(".", 1)[1]
        .lower()
    )

    return (
        extension
        in ALLOWED_EXTENSIONS
    )


def storage_upload(
    file_storage,
    folder
):

    if (
        not file_storage
        or not file_storage.filename
    ):

        return None

    if not database_ready():

        raise RuntimeError(
            "Supabase is not configured."
        )

    original = secure_filename(
        file_storage.filename
    )

    if not original:

        raise ValueError(
            "Invalid filename."
        )

    if not allowed_file(
        original
    ):

        raise ValueError(
            "Unsupported file type."
        )

    extension = ""

    if "." in original:

        extension = (
            "."
            + original
            .rsplit(".", 1)[1]
            .lower()
        )

    storage_path = (
        folder
        + "/"
        + uuid.uuid4().hex
        + extension
    )

    url = (
        SUPABASE_URL
        + "/storage/v1/object/"
        + STORAGE_BUCKET
        + "/"
        + storage_path
    )

    content_type = (
        file_storage.mimetype
        or mimetypes.guess_type(
            original
        )[0]
        or "application/octet-stream"
    )

    headers = {

        "Authorization":
            "Bearer "
            + SUPABASE_SERVICE_KEY,

        "apikey":
            SUPABASE_SERVICE_KEY,

        "Content-Type":
            content_type,

        "x-upsert":
            "false"
    }

    response = requests.post(
        url,
        headers=headers,
        data=file_storage.stream,
        timeout=120
    )

    if not response.ok:

        raise RuntimeError(
            "Storage upload failed: "
            + response.text
        )

    return {

        "original_name":
            original,

        "storage_path":
            storage_path,

        "content_type":
            content_type
    }


def storage_get(
    path
):

    if not path:
        return None

    url = (
        SUPABASE_URL
        + "/storage/v1/object/"
        + STORAGE_BUCKET
        + "/"
        + path
    )

    try:

        response = requests.get(
            url,
            headers={
                "Authorization":
                    "Bearer "
                    + SUPABASE_SERVICE_KEY,

                "apikey":
                    SUPABASE_SERVICE_KEY
            },
            timeout=120
        )

        if response.ok:

            return response

    except Exception:

        pass

    return None


def storage_delete(
    path
):

    if not path:
        return

    if not database_ready():
        return

    url = (
        SUPABASE_URL
        + "/storage/v1/object/"
        + STORAGE_BUCKET
        + "/"
        + path
    )

    try:

        requests.delete(
            url,
            headers={
                "Authorization":
                    "Bearer "
                    + SUPABASE_SERVICE_KEY,

                "apikey":
                    SUPABASE_SERVICE_KEY
            },
            timeout=30
        )

    except Exception:

        pass


def send_storage_file(
    path,
    filename
):

    response = storage_get(
        path
    )

    if response is None:

        abort(404)

    safe_filename = (
        secure_filename(filename)
        or "download"
    )

    content_type = (
        response.headers.get(
            "Content-Type"
        )
        or "application/octet-stream"
    )

    return Response(
        response.content,
        headers={
            "Content-Type":
                content_type,

            "Content-Disposition":
                (
                    'attachment; filename="'
                    + safe_filename
                    + '"'
                )
        }
    )


# ============================================================
# AUTHORIZATION
# ============================================================

def student_required(function):

    @wraps(function)
    def wrapper(
        *args,
        **kwargs
    ):

        if session.get(
            "role"
        ) != "student":

            flash(
                "Please log in as a student."
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
    def wrapper(
        *args,
        **kwargs
    ):

        if session.get(
            "role"
        ) != "admin":

            flash(
                "Administrator login required."
            )

            return redirect(
                url_for("admin_login")
            )

        return function(
            *args,
            **kwargs
        )

    return wrapper


# ============================================================
# NOTIFICATIONS
# ============================================================

def unread_count():

    if session.get(
        "role"
    ) != "student":

        return 0

    try:

        rows = db_select(
            "questions",
            {
                "user_id":
                    "eq."
                    + str(
                        session[
                            "user_id"
                        ]
                    ),

                "status":
                    "eq.Answered",

                "answer_seen":
                    "eq.0",

                "select":
                    "id"
            }
        )

        return len(rows)

    except Exception:

        return 0


# ============================================================
# PAYMENT FUNCTIONS
# ============================================================

def payment_ready():

    return bool(
        FLW_SECRET_KEY
        and FLW_SECRET_HASH
    )


def create_flutterwave_payment(
    phone_number,
    network,
    customer_name,
    email,
    tx_ref
):

    if not FLW_SECRET_KEY:

        raise RuntimeError(
            "FLW_SECRET_KEY is not configured."
        )

    if network not in ZAMBIA_NETWORKS:

        raise ValueError(
            "Invalid Zambia mobile-money network."
        )

    payload = {

        "phone_number":
            phone_number,

        "network":
            network,

        "amount":
            float(
                KOJA_PAYMENT_AMOUNT
            ),

        "currency":
            "ZMW",

        "fullname":
            customer_name,

        "email":
            email,

        "tx_ref":
            tx_ref
    }

    response = requests.post(

        FLW_API_URL
        + "/charges?type=mobile_money_zambia",

        headers={

            "Authorization":
                "Bearer "
                + FLW_SECRET_KEY,

            "Content-Type":
                "application/json",

            "Accept":
                "application/json"
        },

        json=payload,

        timeout=60
    )

    if not response.ok:

        raise RuntimeError(
            "Flutterwave rejected payment: "
            + response.text
        )

    result = response.json()

    if result.get(
        "status"
    ) != "success":

        raise RuntimeError(
            result.get(
                "message",
                "Payment could not be initiated."
            )
        )

    return result


def verify_flutterwave_transaction(
    transaction_id
):

    if not FLW_SECRET_KEY:

        raise RuntimeError(
            "FLW_SECRET_KEY is not configured."
        )

    response = requests.get(

        FLW_API_URL
        + "/transactions/"
        + str(transaction_id)
        + "/verify",

        headers={

            "Authorization":
                "Bearer "
                + FLW_SECRET_KEY,

            "Content-Type":
                "application/json",

            "Accept":
                "application/json"
        },

        timeout=60
    )

    if not response.ok:

        raise RuntimeError(
            "Flutterwave verification failed: "
            + response.text
        )

    return response.json()


def verify_payment(
    transaction_id,
    expected_reference,
    expected_amount
):

    result = verify_flutterwave_transaction(
        transaction_id
    )

    if result.get(
        "status"
    ) != "success":

        return False, result

    data = result.get(
        "data"
    ) or {}

    status = str(
        data.get(
            "status",
            ""
        )
    ).lower()

    reference = (
        data.get("tx_ref")
        or data.get("reference")
    )

    currency = str(
        data.get(
            "currency",
            ""
        )
    ).upper()

    try:

        amount = Decimal(
            str(
                data.get(
                    "amount",
                    "0"
                )
            )
        )

    except Exception:

        amount = Decimal("0")

    if status not in (
        "successful",
        "succeeded"
    ):

        return False, data

    if reference != expected_reference:

        return False, data

    if currency != "ZMW":

        return False, data

    if amount < expected_amount:

        return False, data

    return True, data


def mark_payment_successful(
    payment
):

    payment_id = payment["id"]

    question_id = payment.get(
        "question_id"
    )

    db_update(
        "payments",
        {
            "id":
                payment_id
        },
        {
            "status":
                "successful",

            "updated_at":
                current_time()
        }
    )

    if question_id:

        db_update(
            "questions",
            {
                "id":
                    question_id
            },
            {
                "payment_status":
                    "paid",

                "status":
                    "Pending",

                "updated_at":
                    current_time()
            }
        )


# ============================================================
# HTML
# ============================================================

PAGE = """
<!doctype html>

<html>

<head>

<meta charset="utf-8">

<meta name="viewport"
content="width=device-width,initial-scale=1">

<meta name="theme-color"
content="#071426">

<title>
{{ title }} - KOJA Africa
</title>

<style>

*{
box-sizing:border-box;
}

body{
margin:0;
font-family:Arial,Helvetica,sans-serif;
background:#eef2f7;
color:#172033;
}

nav{
background:#071426;
color:white;
padding:14px;
}

.nav{
max-width:1150px;
margin:auto;
display:flex;
justify-content:space-between;
align-items:center;
gap:10px;
flex-wrap:wrap;
}

.logo{
font-size:25px;
font-weight:bold;
}

.logo small{
display:block;
font-size:11px;
font-weight:normal;
opacity:.7;
}

.links{
display:flex;
gap:5px;
flex-wrap:wrap;
}

.links a{
color:white;
text-decoration:none;
padding:8px 10px;
border-radius:6px;
}

.links a:hover{
background:#1e293b;
}

.container{
max-width:1150px;
margin:25px auto;
padding:0 15px;
}

.card{
background:white;
border-radius:13px;
padding:20px;
margin-bottom:18px;
box-shadow:0 3px 14px rgba(0,0,0,.07);
}

.hero{
background:linear-gradient(
135deg,
#071426,
#1d4ed8
);
color:white;
border-radius:15px;
padding:40px 25px;
margin-bottom:20px;
}

.hero h1{
font-size:36px;
margin-top:0;
}

.btn{
display:inline-block;
background:#2563eb;
color:white;
border:0;
border-radius:7px;
padding:10px 15px;
text-decoration:none;
cursor:pointer;
}

.btn:hover{
opacity:.9;
}

.green{
background:#15803d;
}

.red{
background:#dc2626;
}

.gray{
background:#475569;
}

.orange{
background:#d97706;
}

.purple{
background:#7c3aed;
}

.stats{
display:grid;
grid-template-columns:
repeat(auto-fit,minmax(160px,1fr));
gap:15px;
margin-bottom:20px;
}

.stat{
background:white;
padding:20px;
border-radius:10px;
}

.num{
font-size:30px;
font-weight:bold;
color:#1e3a8a;
}

.question{
border-left:5px solid #2563eb;
}

.answer{
border-left:5px solid #16a34a;
background:#f0fdf4;
}

.badge{
display:inline-block;
padding:5px 10px;
border-radius:20px;
font-size:12px;
font-weight:bold;
}

.pending{
background:#fef3c7;
color:#92400e;
}

.answered{
background:#dcfce7;
color:#166534;
}

.actions{
display:flex;
gap:8px;
flex-wrap:wrap;
margin-top:15px;
}

.text{
white-space:pre-wrap;
line-height:1.75;
}

.small{
font-size:13px;
color:#64748b;
}

.flash{
padding:12px;
border-radius:7px;
background:#dbeafe;
color:#1e40af;
margin-bottom:15px;
}

.empty{
text-align:center;
padding:40px;
color:#64748b;
}

.footer{
text-align:center;
padding:35px;
color:#64748b;
font-size:13px;
}

.error{
background:#fee2e2;
color:#991b1b;
padding:15px;
border-radius:8px;
}

.success{
background:#dcfce7;
color:#166534;
padding:15px;
border-radius:8px;
}

.info{
background:#e0f2fe;
color:#075985;
padding:15px;
border-radius:8px;
}

.form{
margin-bottom:16px;
}

label{
display:block;
font-weight:bold;
margin-bottom:7px;
}

input,
select,
textarea{
width:100%;
padding:12px;
border:1px solid #cbd5e1;
border-radius:7px;
font-size:15px;
font-family:inherit;
background:white;
}

textarea{
resize:vertical;
}

input:focus,
select:focus,
textarea:focus{
outline:none;
border-color:#2563eb;
box-shadow:0 0 0 2px rgba(37,99,235,.12);
}

table{
width:100%;
border-collapse:collapse;
}

th,
td{
padding:10px;
border-bottom:1px solid #e2e8f0;
text-align:left;
}

@media(max-width:650px){

.hero{
padding:25px 18px;
}

.hero h1{
font-size:27px;
}

.links a{
font-size:12px;
}

}

</style>

</head>

<body>

<nav>

<div class="nav">

<div class="logo">

KOJA AFRICA

<small>
Assignment Questions • Academic Answers
</small>

</div>

<div class="links">

{% if session.get("role") == "student" %}

<a href="{{ url_for('student_dashboard') }}">
Dashboard
</a>

<a href="{{ url_for('submit_question') }}">
Ask
</a>

<a href="{{ url_for('my_questions') }}">
My Questions
</a>

<a href="{{ url_for('notifications') }}">
Notifications
{% if unread_count %}
({{ unread_count }})
{% endif %}
</a>

<a href="{{ url_for('logout') }}">
Logout
</a>

{% elif session.get("role") == "admin" %}

<a href="{{ url_for('admin_dashboard') }}">
Dashboard
</a>

<a href="{{ url_for('admin_questions') }}">
Questions
</a>

<a href="{{ url_for('admin_payments') }}">
Payments
</a>

<a href="{{ url_for('logout') }}">
Logout
</a>

{% else %}

<a href="{{ url_for('index') }}">
Home
</a>

<a href="{{ url_for('login') }}">
Login
</a>

<a href="{{ url_for('register') }}">
Register
</a>

{% endif %}

</div>

</div>

</nav>

<div class="container">

{% with messages =
get_flashed_messages() %}

{% for message in messages %}

<div class="flash">
{{ message }}
</div>

{% endfor %}

{% endwith %}

{{ content|safe }}

</div>

<div class="footer">

<b>KOJA AFRICA</b>

<br>

Assignment Questions • Academic Answers

<br><br>

Connecting students with academic help across Africa.

</div>

</body>

</html>
"""


# ============================================================
# PAGE RENDERER
# ============================================================

def page(
    content,
    title="KOJA",
    **extra
):

    return render_template_string(
        PAGE,

        content=render_template_string(
            content,

            countries=AFRICAN_COUNTRIES,

            subjects=SUBJECTS,

            amount=KOJA_PAYMENT_AMOUNT,

            **extra
        ),

        title=title,

        unread_count=unread_count()
    )


# ============================================================
# HOME
# ============================================================

@app.route("/")
def index():

    return page(
        """
<div class="hero">

<h1>KOJA AFRICA</h1>

<h2>
Assignment Questions & Academic Answers
</h2>

<p>
Ask assignment questions, attach documents,
receive academic answers and access learning
resources.
</p>

<div class="actions">

<a class="btn"
href="{{ url_for('register') }}">
Create Student Account
</a>

<a class="btn gray"
href="{{ url_for('login') }}">
Student Login
</a>

<a class="btn green"
href="{{ url_for('admin_login') }}">
Administrator
</a>

</div>

</div>

<div class="stats">

<div class="stat">
<div class="num">🌍</div>
Africa-wide
</div>

<div class="stat">
<div class="num">📚</div>
Academic Questions
</div>

<div class="stat">
<div class="num">💳</div>
Mobile Payments
</div>

<div class="stat">
<div class="num">🔔</div>
Notifications
</div>

</div>

<div class="card">

<h2>How KOJA Works</h2>

<p>1. Create your student account.</p>

<p>2. Submit your assignment question.</p>

<p>3. Pay using supported mobile money.</p>

<p>4. KOJA verifies the payment.</p>

<p>5. Your question enters the administrator queue.</p>

<p>6. Administrator provides the academic answer.</p>

<p>7. You receive an in-site notification.</p>

</div>

<div class="card">

<h2>System Status</h2>

{% if database_ready() %}

<div class="success">
Supabase configuration detected.
</div>

{% else %}

<div class="error">
Supabase is not configured.
</div>

{% endif %}

{% if payment_ready() %}

<br>

<div class="success">
Payment configuration detected.
</div>

{% else %}

<br>

<div class="info">
Payment system is not configured yet.
</div>

{% endif %}

</div>
        """,
        "Home"
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

        username = request.form.get(
            "username",
            ""
        ).strip().lower()

        email = request.form.get(
            "email",
            ""
        ).strip().lower()

        password = request.form.get(
            "password",
            ""
        )

        country = request.form.get(
            "country",
            ""
        ).strip()

        institution = request.form.get(
            "institution",
            ""
        ).strip()

        academic_level = request.form.get(
            "academic_level",
            ""
        ).strip()

        if not all([
            name,
            username,
            email,
            password,
            country
        ]):

            flash(
                "Complete all required fields."
            )

            return redirect(
                url_for("register")
            )

        if country not in AFRICAN_COUNTRIES:

            flash(
                "Select a valid African country."
            )

            return redirect(
                url_for("register")
            )

        if len(username) < 3:

            flash(
                "Username must contain at least 3 characters."
            )

            return redirect(
                url_for("register")
            )

        if len(password) < 6:

            flash(
                "Password must contain at least 6 characters."
            )

            return redirect(
                url_for("register")
            )

        try:

            if get_user_by_username(
                username
            ):

                flash(
                    "Username already exists."
                )

                return redirect(
                    url_for("register")
                )

            if email_exists(
                email
            ):

                flash(
                    "Email already exists."
                )

                return redirect(
                    url_for("register")
                )

            db_insert(
                "users",
                {

                    "name":
                        name,

                    "username":
                        username,

                    "email":
                        email,

                    "password":
                        generate_password_hash(
                            password
                        ),

                    "role":
                        "student",

                    "country":
                        country,

                    "institution":
                        institution,

                    "academic_level":
                        academic_level,

                    "created_at":
                        current_time()
                }
            )

            flash(
                "Account created successfully. You can now log in."
            )

            return redirect(
                url_for("login")
            )

        except Exception as error:

            flash(
                "Registration failed: "
                + str(error)
            )

    return page(
        """
<div class="card">

<h1>Create KOJA Account</h1>

<form method="POST">

<div class="form">

<label>Full Name</label>

<input
name="name"
autocomplete="name"
required>

</div>

<div class="form">

<label>Username</label>

<input
name="username"
autocomplete="username"
required>

</div>

<div class="form">

<label>Email</label>

<input
name="email"
type="email"
autocomplete="email"
required>

</div>

<div class="form">

<label>Country</label>

<select name="country" required>

<option value="">
Select country
</option>

{% for country in countries %}

<option value="{{ country }}">
{{ country }}
</option>

{% endfor %}

</select>

</div>

<div class="form">

<label>Institution</label>

<input
name="institution"
placeholder="University / College / School">

</div>

<div class="form">

<label>Academic Level</label>

<select name="academic_level">

<option value="">
Select level
</option>

<option>Certificate</option>
<option>Diploma</option>
<option>Undergraduate</option>
<option>Postgraduate</option>
<option>Master's</option>
<option>PhD</option>

</select>

</div>

<div class="form">

<label>Password</label>

<input
name="password"
type="password"
minlength="6"
autocomplete="new-password"
required>

</div>

<button class="btn">
Create Account
</button>

</form>

</div>
        """,
        "Register"
    )


# ============================================================
# STUDENT LOGIN
# ============================================================

@app.route(
    "/login",
    methods=["GET", "POST"]
)
def login():

    if request.method == "POST":

        username = request.form.get(
            "username",
            ""
        ).strip().lower()

        password = request.form.get(
            "password",
            ""
        )

        try:

            user = get_user_by_username(
                username,
                "student"
            )

            if (
                user
                and check_password_hash(
                    user["password"],
                    password
                )
            ):

                session.clear()

                session["user_id"] = user["id"]

                session["name"] = user["name"]

                session["username"] = (
                    user["username"]
                )

                session["role"] = "student"

                return redirect(
                    url_for(
                        "student_dashboard"
                    )
                )

            flash(
                "Invalid username or password."
            )

        except Exception as error:

            flash(
                "Login error: "
                + str(error)
            )

    return page(
        """
<div class="card">

<h1>Student Login</h1>

<form method="POST">

<div class="form">

<label>Username</label>

<input
name="username"
autocomplete="username"
required>

</div>

<div class="form">

<label>Password</label>

<input
name="password"
type="password"
autocomplete="current-password"
required>

</div>

<button class="btn">
Login
</button>

</form>

<br>

<a href="{{ url_for('register') }}">
Create an account
</a>

</div>
        """,
        "Login"
    )


# ============================================================
# LOGOUT
# ============================================================

@app.route("/logout")
def logout():

    session.clear()

    return redirect(
        url_for("index")
    )


# ============================================================
# STUDENT DASHBOARD
# ============================================================

@app.route("/student")
@student_required
def student_dashboard():

    try:

        questions = db_select(
            "questions",
            {
                "user_id":
                    "eq."
                    + str(
                        session[
                            "user_id"
                        ]
                    ),

                "select":
                    "*",

                "order":
                    "id.desc"
            }
        )

    except Exception as error:

        flash(
            "Could not load questions: "
            + str(error)
        )

        questions = []

    total = len(
        questions
    )

    pending = len([
        q for q in questions
        if q.get("status") == "Pending"
    ])

    answered = len([
        q for q in questions
        if q.get("status") == "Answered"
    ])

    paid = len([
        q for q in questions
        if q.get("payment_status") == "paid"
    ])

    return page(
        """
<div class="hero">

<h1>
Welcome, {{ session.get("name") }}
</h1>

<p>
KOJA AFRICA assignment assistance portal.
</p>

<a class="btn"
href="{{ url_for('submit_question') }}">
Ask New Question
</a>

</div>

<div class="stats">

<div class="stat">
<div class="num">{{ total }}</div>
Questions
</div>

<div class="stat">
<div class="num">{{ paid }}</div>
Paid
</div>

<div class="stat">
<div class="num">{{ pending }}</div>
Pending
</div>

<div class="stat">
<div class="num">{{ answered }}</div>
Answered
</div>

</div>

<div class="card">

<h2>My Recent Questions</h2>

{% for q in questions[:10] %}

<div class="card question">

<h3>
{{ q["subject"] }}
</h3>

<p>
{{ q["question"][:250] }}
</p>

{% if q.get("payment_status") != "paid" %}

<span class="badge pending">
Payment Required
</span>

{% elif q["status"] == "Answered" %}

<span class="badge answered">
Answered
</span>

{% else %}

<span class="badge pending">
Paid / Pending Answer
</span>

{% endif %}

<div class="actions">

<a class="btn"
href="{{ url_for(
'view_question',
question_id=q['id']
) }}">
Open
</a>

{% if q.get("payment_status") != "paid" %}

<a class="btn orange"
href="{{ url_for(
'pay_question',
question_id=q['id']
) }}">
Pay K{{ "%.2f"|format(amount) }}
</a>

{% endif %}

</div>

</div>

{% else %}

<p>No questions yet.</p>

{% endfor %}

</div>
        """,
        "Dashboard"
    )


# ============================================================
# SUBMIT QUESTION
# ============================================================

@app.route(
    "/submit",
    methods=["GET", "POST"]
)
@student_required
def submit_question():

    if request.method == "POST":

        subject = request.form.get(
            "subject",
            ""
        ).strip()

        question = request.form.get(
            "question",
            ""
        ).strip()

        attachment = request.files.get(
            "attachment"
        )

        if not subject or not question:

            flash(
                "Subject and question are required."
            )

            return redirect(
                url_for("submit_question")
            )

        if subject not in SUBJECTS:

            flash(
                "Select a valid subject."
            )

            return redirect(
                url_for("submit_question")
            )

        uploaded = None

        try:

            if (
                attachment
                and attachment.filename
            ):

                uploaded = storage_upload(
                    attachment,
                    "questions"
                )

            result = db_insert(
                "questions",
                {

                    "user_id":
                        session[
                            "user_id"
                        ],

                    "student_name":
                        session[
                            "name"
                        ],

                    "subject":
                        subject,

                    "question":
                        question,

                    "attachment_name":
                        (
                            uploaded[
                                "original_name"
                            ]
                            if uploaded
                            else None
                        ),

                    "attachment_file":
                        (
                            uploaded[
                                "storage_path"
                            ]
                            if uploaded
                            else None
                        ),

                    "status":
                        "Awaiting Payment",

                    "answer_seen":
                        0,

                    "payment_required":
                        True,

                    "payment_status":
                        "unpaid",

                    "created_at":
                        current_time()
                }
            )

            question_id = None

            if result:

                question_id = result[0].get(
                    "id"
                )

            if not question_id:

                raise RuntimeError(
                    "Question was created but its ID was not returned."
                )

            flash(
                "Question created. Complete payment to send it to the administrator."
            )

            return redirect(
                url_for(
                    "pay_question",
                    question_id=question_id
                )
            )

        except Exception as error:

            if uploaded:

                storage_delete(
                    uploaded[
                        "storage_path"
                    ]
                )

            flash(
                "Submission failed: "
                + str(error)
            )

    return page(
        """
<div class="card">

<h1>Ask KOJA</h1>

<div class="info">

Questions require payment before they enter
the administrator answering queue.

Current price:
<b>K{{ "%.2f"|format(amount) }}</b>

</div>

<br>

<form
method="POST"
enctype="multipart/form-data">

<div class="form">

<label>Subject</label>

<select name="subject" required>

<option value="">
Select subject
</option>

{% for subject in subjects %}

<option value="{{ subject }}">
{{ subject }}
</option>

{% endfor %}

</select>

</div>

<div class="form">

<label>Assignment Question</label>

<textarea
name="question"
rows="10"
required
placeholder="Write your complete assignment question..."
></textarea>

</div>

<div class="form">

<label>
Attachment — Maximum 10 MB
</label>

<input
type="file"
name="attachment">

</div>

<button class="btn">
Continue to Payment
</button>

</form>

</div>
        """,
        "Ask Question"
    )


# ============================================================
# PAYMENT PAGE
# ============================================================

@app.route(
    "/pay/<int:question_id>",
    methods=["GET", "POST"]
)
@student_required
def pay_question(
    question_id
):

    question = get_student_question(
        question_id,
        session["user_id"]
    )

    if not question:

        abort(404)

    if question.get(
        "payment_status"
    ) == "paid":

        flash(
            "This question has already been paid for."
        )

        return redirect(
            url_for(
                "view_question",
                question_id=question_id
            )
        )

    if request.method == "POST":

        network = request.form.get(
            "network",
            ""
        ).strip()

        phone = request.form.get(
            "phone",
            ""
        ).strip()

        if network not in ZAMBIA_NETWORKS:

            flash(
                "Select MTN, Airtel or Zamtel."
            )

            return redirect(
                url_for(
                    "pay_question",
                    question_id=question_id
                )
            )

        if not phone:

            flash(
                "Enter your mobile-money phone number."
            )

            return redirect(
                url_for(
                    "pay_question",
                    question_id=question_id
                )
            )

        if not payment_ready():

            flash(
                "Payment system is not configured on the server."
            )

            return redirect(
                url_for(
                    "pay_question",
                    question_id=question_id
                )
            )

        user = get_user_by_id(
            session["user_id"]
        )

        if not user:

            flash(
                "Student account could not be found."
            )

            return redirect(
                url_for("logout")
            )

        tx_ref = (
            "KOJA-"
            + uuid.uuid4().hex.upper()
        )

        try:

            db_insert(
                "payments",
                {

                    "user_id":
                        session[
                            "user_id"
                        ],

                    "question_id":
                        question_id,

                    "tx_ref":
                        tx_ref,

                    "amount":
                        float(
                            KOJA_PAYMENT_AMOUNT
                        ),

                    "currency":
                        "ZMW",

                    "network":
                        network,

                    "phone_number":
                        phone,

                    "status":
                        "pending",

                    "payment_type":
                        "mobile_money",

                    "created_at":
                        current_time()
                }
            )

            result = create_flutterwave_payment(

                phone_number=phone,

                network=network,

                customer_name=
                    user.get(
                        "name",
                        session.get(
                            "name",
                            "KOJA Student"
                        )
                    ),

                email=
                    user.get(
                        "email"
                    ),

                tx_ref=tx_ref
            )

            data = result.get(
                "data"
            ) or {}

            authorization = (
                result.get(
                    "meta"
                ) or {}
            ).get(
                "authorization"
            ) or {}

            redirect_url = authorization.get(
                "redirect"
            )

            transaction_id = data.get(
                "id"
            )

            if transaction_id:

                db_update(
                    "payments",
                    {
                        "tx_ref":
                            tx_ref
                    },
                    {
                        "flutterwave_transaction_id":
                            str(
                                transaction_id
                            )
                    }
                )

            if redirect_url:

                return redirect(
                    redirect_url
                )

            flash(
                "Payment initiated. Approve the mobile-money request on your phone."
            )

            return redirect(
                url_for(
                    "payment_status",
                    tx_ref=tx_ref
                )
            )

        except Exception as error:

            try:

                db_update(
                    "payments",
                    {
                        "tx_ref":
                            tx_ref
                    },
                    {
                        "status":
                            "failed",

                        "updated_at":
                            current_time()
                    }
                )

            except Exception:

                pass

            flash(
                "Payment could not be started: "
                + str(error)
            )

    return page(
        """
<div class="card">

<h1>Pay for Question</h1>

<div class="info">

<b>Amount: K{{ "%.2f"|format(amount) }}</b>

<br><br>

Supported Zambia mobile-money networks:

<br><br>

<b>MTN</b> |
<b>Airtel</b> |
<b>Zamtel</b>

</div>

<br>

<h3>
{{ question["subject"] }}
</h3>

<p>
{{ question["question"][:500] }}
</p>

<form method="POST">

<div class="form">

<label>Mobile Money Network</label>

<select name="network" required>

<option value="">
Select network
</option>

<option value="MTN">
MTN
</option>

<option value="Airtel">
Airtel
</option>

<option value="Zamtel">
Zamtel
</option>

</select>

</div>

<div class="form">

<label>Mobile Money Phone Number</label>

<input
name="phone"
type="tel"
placeholder="097XXXXXXX"
required>

</div>

<button class="btn green">
Pay K{{ "%.2f"|format(amount) }}
</button>

</form>

</div>
        """,
        "Payment"
    )


# ============================================================
# PAYMENT STATUS
# ============================================================

@app.route(
    "/payment/<tx_ref>"
)
@student_required
def payment_status(
    tx_ref
):

    rows = db_select(
        "payments",
        {

            "tx_ref":
                "eq."
                + tx_ref,

            "user_id":
                "eq."
                + str(
                    session[
                        "user_id"
                    ]
                ),

            "select":
                "*",

            "limit":
                "1"
        }
    )

    if not rows:

        abort(404)

    payment = rows[0]

    return page(
        """
<div class="card">

<h1>Payment Status</h1>

{% if payment["status"] == "successful" %}

<div class="success">

Payment successful.

<br><br>

Your question has been sent to the KOJA
administrator queue.

</div>

<br>

<a class="btn green"
href="{{ url_for(
'view_question',
question_id=payment['question_id']
) }}">
Open Question
</a>

{% elif payment["status"] == "failed" %}

<div class="error">

Payment failed.

</div>

{% else %}

<div class="info">

Payment is still pending.

<br><br>

Approve the mobile-money request on your
phone and then check the status again.

</div>

<br>

<a class="btn"
href="{{ url_for(
'check_payment',
tx_ref=payment['tx_ref']
) }}">
Check Payment
</a>

{% endif %}

<br><br>

<p>
<b>Reference:</b>
{{ payment["tx_ref"] }}
</p>

<p>
<b>Network:</b>
{{ payment["network"] }}
</p>

<p>
<b>Amount:</b>
K{{ payment["amount"] }}
</p>

</div>
        """,
        "Payment Status",
        payment=payment
    )


# ============================================================
# CHECK PAYMENT
# ============================================================

@app.route(
    "/payment/<tx_ref>/check"
)
@student_required
def check_payment(
    tx_ref
):

    rows = db_select(
        "payments",
        {

            "tx_ref":
                "eq."
                + tx_ref,

            "user_id":
                "eq."
                + str(
                    session[
                        "user_id"
                    ]
                ),

            "select":
                "*",

            "limit":
                "1"
        }
    )

    if not rows:

        abort(404)

    payment = rows[0]

    transaction_id = payment.get(
        "flutterwave_transaction_id"
    )

    if not transaction_id:

        flash(
            "Payment is still being processed. Please try again shortly."
        )

        return redirect(
            url_for(
                "payment_status",
                tx_ref=tx_ref
            )
        )

    try:

        valid, data = verify_payment(

            transaction_id,

            payment["tx_ref"],

            Decimal(
                str(
                    payment["amount"]
                )
            )
        )

        if valid:

            mark_payment_successful(
                payment
            )

            flash(
                "Payment verified successfully."
            )

        else:

            status = str(
                data.get(
                    "status",
                    ""
                )
            ).lower()

            if status in (
                "failed",
                "cancelled"
            ):

                db_update(
                    "payments",
                    {
                        "id":
                            payment["id"]
                    },
                    {
                        "status":
                            status,

                        "updated_at":
                            current_time()
                    }
                )

                flash(
                    "Payment was not successful."
                )

            else:

                flash(
                    "Payment is still pending."
                )

    except Exception as error:

        flash(
            "Payment verification error: "
            + str(error)
        )

    return redirect(
        url_for(
            "payment_status",
            tx_ref=tx_ref
        )
    )


# ============================================================
# FLUTTERWAVE WEBHOOK
# ============================================================

@app.route(
    "/flutterwave/webhook",
    methods=["POST"]
)
def flutterwave_webhook():

    if not FLW_SECRET_HASH:

        return "", 401

    raw_body = request.get_data()

    signature = request.headers.get(
        "flutterwave-signature"
    )

    # Current Flutterwave HMAC-SHA256 signature
    if signature:

        digest = hmac.new(
            FLW_SECRET_HASH.encode(
                "utf-8"
            ),
            raw_body,
            hashlib.sha256
        ).digest()

        calculated = base64.b64encode(
            digest
        ).decode(
            "utf-8"
        )

        if not hmac.compare_digest(
            calculated,
            signature
        ):

            return "", 401

    else:

        # Compatibility with older
        # Flutterwave webhook format.
        old_signature = request.headers.get(
            "verif-hash"
        )

        if (
            not old_signature
            or not hmac.compare_digest(
                old_signature,
                FLW_SECRET_HASH
            )
        ):

            return "", 401

    payload = request.get_json(
        silent=True
    ) or {}

    data = payload.get(
        "data"
    ) or {}

    transaction_id = data.get(
        "id"
    )

    tx_ref = (
        data.get("tx_ref")
        or data.get("reference")
    )

    if not transaction_id or not tx_ref:

        return "", 200

    try:

        payments = db_select(
            "payments",
            {

                "tx_ref":
                    "eq."
                    + str(tx_ref),

                "select":
                    "*",

                "limit":
                    "1"
            }
        )

        if not payments:

            return "", 200

        payment = payments[0]

        # Save transaction ID if this is
        # the first callback.
        db_update(
            "payments",
            {
                "id":
                    payment["id"]
            },
            {
                "flutterwave_transaction_id":
                    str(
                        transaction_id
                    ),

                "updated_at":
                    current_time()
            }
        )

        # Re-fetch after update.
        payment["flutterwave_transaction_id"] = (
            str(transaction_id)
        )

        valid, verified = verify_payment(

            transaction_id,

            payment["tx_ref"],

            Decimal(
                str(
                    payment["amount"]
                )
            )
        )

        if valid:

            if payment.get(
                "status"
            ) != "successful":

                mark_payment_successful(
                    payment
                )

        else:

            status = str(
                verified.get(
                    "status",
                    ""
                )
            ).lower()

            if status in (
                "failed",
                "cancelled"
            ):

                db_update(
                    "payments",
                    {
                        "id":
                            payment["id"]
                    },
                    {
                        "status":
                            status,

                        "updated_at":
                            current_time()
                    }
                )

    except Exception as error:

        print(
            "Flutterwave webhook error:",
            error
        )

    return "", 200


# ============================================================
# MY QUESTIONS
# ============================================================

@app.route(
    "/my-questions"
)
@student_required
def my_questions():

    try:

        questions = db_select(
            "questions",
            {

                "user_id":
                    "eq."
                    + str(
                        session[
                            "user_id"
                        ]
                    ),

                "select":
                    "*",

                "order":
                    "id.desc"
            }
        )

    except Exception as error:

        flash(
            "Could not load questions: "
            + str(error)
        )

        questions = []

    return page(
        """
<div class="card">

<h1>My Questions</h1>

<a class="btn"
href="{{ url_for('submit_question') }}">
+ New Question
</a>

</div>

{% for q in questions %}

<div class="card question">

<h2>
{{ q["subject"] }}
</h2>

<p class="small">
{{ q["created_at"] }}
</p>

<div class="text">
{{ q["question"] }}
</div>

<br>

{% if q.get("payment_status") != "paid" %}

<span class="badge pending">
Payment Required
</span>

{% elif q["status"] == "Answered" %}

<span class="badge answered">
Answered
</span>

{% else %}

<span class="badge pending">
Paid / Pending Answer
</span>

{% endif %}

<div class="actions">

<a class="btn"
href="{{ url_for(
'view_question',
question_id=q['id']
) }}">
View
</a>

{% if q.get("payment_status") != "paid" %}

<a class="btn orange"
href="{{ url_for(
'pay_question',
question_id=q['id']
) }}">
Pay K{{ "%.2f"|format(amount) }}
</a>

{% endif %}

{% if q.get("attachment_file") %}

<a class="btn purple"
href="{{ url_for(
'download_question_file',
question_id=q['id']
) }}">
Download Assignment
</a>

{% endif %}

</div>

</div>

{% else %}

<div class="card empty">
No questions yet.
</div>

{% endfor %}
        """,
        "My Questions"
    )


# ============================================================
# VIEW QUESTION
# ============================================================

@app.route(
    "/question/<int:question_id>"
)
@student_required
def view_question(
    question_id
):

    question = get_student_question(
        question_id,
        session["user_id"]
    )

    if not question:

        abort(404)

    answer = None

    if question.get(
        "payment_status"
    ) == "paid":

        answer = get_answer(
            question_id
        )

    if answer:

        try:

            db_update(
                "questions",
                {

                    "id":
                        question_id,

                    "user_id":
                        session[
                            "user_id"
                        ]
                },
                {
                    "answer_seen":
                        1
                }
            )

        except Exception:

            pass

    return page(
        """
<div class="card question">

<h1>
{{ question["subject"] }}
</h1>

<p class="small">
{{ question["created_at"] }}
</p>

<h3>Your Question</h3>

<div class="text">
{{ question["question"] }}
</div>

{% if question.get("attachment_file") %}

<div class="actions">

<a class="btn purple"
href="{{ url_for(
'download_question_file',
question_id=question['id']
) }}">
Download Assignment
</a>

</div>

{% endif %}

</div>

{% if question.get("payment_status") != "paid" %}

<div class="card">

<h2>Payment Required</h2>

<div class="info">

Your question has been saved but has not
entered the answering queue.

</div>

<br>

<a class="btn orange"
href="{{ url_for(
'pay_question',
question_id=question['id']
) }}">
Pay K{{ "%.2f"|format(amount) }}
</a>

</div>

{% elif answer %}

<div class="card answer">

<h2>KOJA Answer</h2>

<div class="text">
{{ answer["answer"] }}
</div>

<p class="small">
Answered {{ answer["answered_at"] }}
</p>

{% if answer.get("attachment_file") %}

<a class="btn purple"
href="{{ url_for(
'download_answer_file',
question_id=question['id']
) }}">
Download Answer Resource
</a>

{% endif %}

</div>

{% else %}

<div class="card">

<h2>Answer Pending</h2>

<p>
Payment has been confirmed. The administrator
has not answered this question yet.
</p>

</div>

{% endif %}
        """,
        "Question"
    )


# ============================================================
# NOTIFICATIONS
# ============================================================

@app.route(
    "/notifications"
)
@student_required
def notifications():

    try:

        questions = db_select(
            "questions",
            {

                "user_id":
                    "eq."
                    + str(
                        session[
                            "user_id"
                        ]
                    ),

                "status":
                    "eq.Answered",

                "select":
                    "*",

                "order":
                    "id.desc"
            }
        )

    except Exception as error:

        flash(
            "Could not load notifications: "
            + str(error)
        )

        questions = []

    return page(
        """
<div class="card">

<h1>Notifications</h1>

<p>
Questions that have received answers appear here.
</p>

</div>

{% for q in questions %}

<div class="card">

<h2>
{{ q["subject"] }}
</h2>

{% if q["answer_seen"] == 0 %}

<span class="badge"
style="background:#fee2e2;color:#991b1b">
NEW
</span>

{% else %}

<span class="badge answered">
READ
</span>

{% endif %}

<div class="actions">

<a class="btn green"
href="{{ url_for(
'view_question',
question_id=q['id']
) }}">
Read Answer
</a>

</div>

</div>

{% else %}

<div class="card empty">
No answers yet.
</div>

{% endfor %}
        """,
        "Notifications"
    )


# ============================================================
# QUESTION FILE DOWNLOAD
# ============================================================

@app.route(
    "/download/question/<int:question_id>"
)
@student_required
def download_question_file(
    question_id
):

    question = get_student_question(
        question_id,
        session["user_id"]
    )

    if not question:

        abort(404)

    path = question.get(
        "attachment_file"
    )

    if not path:

        abort(404)

    return send_storage_file(
        path,
        question.get(
            "attachment_name"
        ) or "assignment"
    )


# ============================================================
# ANSWER FILE DOWNLOAD
# ============================================================

@app.route(
    "/download/answer/<int:question_id>"
)
@student_required
def download_answer_file(
    question_id
):

    question = get_student_question(
        question_id,
        session["user_id"]
    )

    if not question:

        abort(404)

    answer = get_answer(
        question_id
    )

    if not answer:

        abort(404)

    path = answer.get(
        "attachment_file"
    )

    if not path:

        abort(404)

    return send_storage_file(
        path,
        answer.get(
            "attachment_name"
        ) or "answer-resource"
    )


# ============================================================
# ADMIN LOGIN
# ============================================================

@app.route(
    "/admin/login",
    methods=["GET", "POST"]
)
def admin_login():

    if request.method == "POST":

        username = request.form.get(
            "username",
            ""
        ).strip().lower()

        password = request.form.get(
            "password",
            ""
        )

        try:

            admin = get_user_by_username(
                username,
                "admin"
            )

            if (
                admin
                and check_password_hash(
                    admin["password"],
                    password
                )
            ):

                session.clear()

                session["user_id"] = admin["id"]

                session["name"] = admin["name"]

                session["username"] = (
                    admin["username"]
                )

                session["role"] = "admin"

                return redirect(
                    url_for(
                        "admin_dashboard"
                    )
                )

            flash(
                "Invalid administrator credentials."
            )

        except Exception as error:

            flash(
                "Admin login error: "
                + str(error)
            )

    return page(
        """
<div class="card">

<h1>KOJA Administrator</h1>

<form method="POST">

<div class="form">

<label>Username</label>

<input
name="username"
autocomplete="username"
required>

</div>

<div class="form">

<label>Password</label>

<input
name="password"
type="password"
autocomplete="current-password"
required>

</div>

<button class="btn">
Administrator Login
</button>

</form>

</div>
        """,
        "Admin Login"
    )


# ============================================================
# ADMIN DASHBOARD
# ============================================================

@app.route(
    "/admin"
)
@admin_required
def admin_dashboard():

    try:

        questions = db_select(
            "questions",
            {

                "payment_status":
                    "eq.paid",

                "select":
                    "*",

                "order":
                    "id.desc"
            }
        )

        students = db_select(
            "users",
            {

                "role":
                    "eq.student",

                "select":
                    "id"
            }
        )

        payments = db_select(
            "payments",
            {

                "status":
                    "eq.successful",

                "select":
                    "id,amount"
            }
        )

    except Exception as error:

        flash(
            "Could not load administrator data: "
            + str(error)
        )

        questions = []
        students = []
        payments = []

    pending = len([
        q for q in questions
        if q.get("status") == "Pending"
    ])

    answered = len([
        q for q in questions
        if q.get("status") == "Answered"
    ])

    revenue = sum(
        Decimal(
            str(
                p.get(
                    "amount",
                    0
                )
            )
        )
        for p in payments
    )

    return page(
        """
<div class="hero">

<h1>KOJA Administrator</h1>

<p>
Manage paid student questions,
answers and payments.
</p>

<div class="actions">

<a class="btn"
href="{{ url_for('admin_questions') }}">
Manage Questions
</a>

<a class="btn green"
href="{{ url_for('admin_payments') }}">
Payments
</a>

</div>

</div>

<div class="stats">

<div class="stat">
<div class="num">
{{ questions|length }}
</div>
Paid Questions
</div>

<div class="stat">
<div class="num">
{{ pending }}
</div>
Pending
</div>

<div class="stat">
<div class="num">
{{ answered }}
</div>
Answered
</div>

<div class="stat">
<div class="num">
K{{ "%.2f"|format(revenue) }}
</div>
Revenue
</div>

</div>
        """,
        "Admin Dashboard"
    )


# ============================================================
# ADMIN QUESTIONS
# ============================================================

@app.route(
    "/admin/questions"
)
@admin_required
def admin_questions():

    search = request.args.get(
        "search",
        ""
    ).strip()

    status = request.args.get(
        "status",
        ""
    ).strip()

    params = {

        "payment_status":
            "eq.paid",

        "select":
            "*",

        "order":
            "id.desc"
    }

    if status in (
        "Pending",
        "Answered"
    ):

        params["status"] = (
            "eq."
            + status
        )

    if search:

        safe_search = (
            search
            .replace(
                "*",
                ""
            )
            .replace(
                ",",
                " "
            )
        )

        value = (
            "*"
            + safe_search
            + "*"
        )

        params["or"] = (
            "(student_name.ilike."
            + value
            + ",subject.ilike."
            + value
            + ",question.ilike."
            + value
            + ")"
        )

    try:

        questions = db_select(
            "questions",
            params
        )

    except Exception as error:

        questions = []

        flash(
            "Question search failed: "
            + str(error)
        )

    return page(
        """
<div class="card">

<h1>Questions</h1>

<form method="GET">

<div class="form">

<label>Search</label>

<input
name="search"
value="{{ search }}"
placeholder="Student, subject or question">

</div>

<div class="form">

<label>Status</label>

<select name="status">

<option value="">
All
</option>

<option
value="Pending"
{% if status == "Pending" %}
selected
{% endif %}
>
Pending
</option>

<option
value="Answered"
{% if status == "Answered" %}
selected
{% endif %}
>
Answered
</option>

</select>

</div>

<button class="btn">
Search
</button>

</form>

</div>

{% for q in questions %}

<div class="card question">

<h2>
{{ q["student_name"] }}
</h2>

<p>
<b>{{ q["subject"] }}</b>
</p>

<p>
{{ q["question"][:400] }}
</p>

{% if q["status"] == "Answered" %}

<span class="badge answered">
Answered
</span>

{% else %}

<span class="badge pending">
Pending
</span>

{% endif %}

<div class="actions">

<a class="btn"
href="{{ url_for(
'admin_view_question',
question_id=q['id']
) }}">
Open
</a>

</div>

</div>

{% else %}

<div class="card empty">
No paid questions found.
</div>

{% endfor %}
        """,
        "Admin Questions"
    )


# ============================================================
# ADMIN VIEW QUESTION
# ============================================================

@app.route(
    "/admin/question/<int:question_id>"
)
@admin_required
def admin_view_question(
    question_id
):

    question = get_question(
        question_id
    )

    if not question:

        abort(404)

    if question.get(
        "payment_status"
    ) != "paid":

        flash(
            "This question has not been paid for."
        )

        return redirect(
            url_for(
                "admin_questions"
            )
        )

    answer = get_answer(
        question_id
    )

    return page(
        """
<div class="card question">

<h1>
{{ question["subject"] }}
</h1>

<p>
<b>Student:</b>
{{ question["student_name"] }}
</p>

<p class="small">
{{ question["created_at"] }}
</p>

<h3>Assignment Question</h3>

<div class="text">
{{ question["question"] }}
</div>

{% if question.get("attachment_file") %}

<div class="actions">

<a class="btn purple"
href="{{ url_for(
'admin_download_question',
question_id=question['id']
) }}">
Download Assignment
</a>

</div>

{% endif %}

</div>

<div class="card">

<h2>

{% if answer %}
Update Answer
{% else %}
Write Answer
{% endif %}

</h2>

<form
method="POST"
enctype="multipart/form-data"
action="{{ url_for(
'write_answer',
question_id=question['id']
) }}">

<div class="form">

<label>Academic Answer</label>

<textarea
name="answer"
rows="16"
required>{% if answer %}{{ answer["answer"] }}{% endif %}</textarea>

</div>

<div class="form">

<label>
Additional Answer Resource
</label>

<input
type="file"
name="answer_attachment">

</div>

<button class="btn green">

{% if answer %}
Update Answer
{% else %}
Send Answer
{% endif %}

</button>

</form>

</div>
        """,
        "Answer Question"
    )


# ============================================================
# WRITE ANSWER
# ============================================================

@app.route(
    "/admin/question/<int:question_id>/answer",
    methods=["POST"]
)
@admin_required
def write_answer(
    question_id
):

    text = request.form.get(
        "answer",
        ""
    ).strip()

    attachment = request.files.get(
        "answer_attachment"
    )

    if not text:

        flash(
            "Answer cannot be empty."
        )

        return redirect(
            url_for(
                "admin_view_question",
                question_id=question_id
            )
        )

    question = get_question(
        question_id
    )

    if not question:

        abort(404)

    if question.get(
        "payment_status"
    ) != "paid":

        flash(
            "Question has not been paid for."
        )

        return redirect(
            url_for(
                "admin_questions"
            )
        )

    uploaded = None

    try:

        if (
            attachment
            and attachment.filename
        ):

            uploaded = storage_upload(
                attachment,
                "answers"
            )

        existing = get_answer(
            question_id
        )

        if existing:

            update = {

                "answer":
                    text,

                "answered_at":
                    current_time()
            }

            old_file = existing.get(
                "attachment_file"
            )

            if uploaded:

                update[
                    "attachment_name"
                ] = uploaded[
                    "original_name"
                ]

                update[
                    "attachment_file"
                ] = uploaded[
                    "storage_path"
                ]

            db_update(
                "answers",
                {
                    "id":
                        existing["id"]
                },
                update
            )

            if uploaded and old_file:

                storage_delete(
                    old_file
                )

        else:

            db_insert(
                "answers",
                {

                    "question_id":
                        question_id,

                    "answer":
                        text,

                    "attachment_name":
                        (
                            uploaded[
                                "original_name"
                            ]
                            if uploaded
                            else None
                        ),

                    "attachment_file":
                        (
                            uploaded[
                                "storage_path"
                            ]
                            if uploaded
                            else None
                        ),

                    "answered_at":
                        current_time()
                }
            )

        db_update(
            "questions",
            {
                "id":
                    question_id
            },
            {

                "status":
                    "Answered",

                "answer_seen":
                    0,

                "updated_at":
                    current_time()
            }
        )

        flash(
            "Answer saved successfully."
        )

    except Exception as error:

        if uploaded:

            storage_delete(
                uploaded[
                    "storage_path"
                ]
            )

        flash(
            "Could not save answer: "
            + str(error)
        )

    return redirect(
        url_for(
            "admin_view_question",
            question_id=question_id
        )
    )


# ============================================================
# ADMIN QUESTION DOWNLOAD
# ============================================================

@app.route(
    "/admin/download/question/<int:question_id>"
)
@admin_required
def admin_download_question(
    question_id
):

    question = get_question(
        question_id
    )

    if not question:

        abort(404)

    path = question.get(
        "attachment_file"
    )

    if not path:

        abort(404)

    return send_storage_file(
        path,
        question.get(
            "attachment_name"
        ) or "assignment"
    )


# ============================================================
# ADMIN ANSWER DOWNLOAD
# ============================================================

@app.route(
    "/admin/download/answer/<int:question_id>"
)
@admin_required
def admin_download_answer(
    question_id
):

    answer = get_answer(
        question_id
    )

    if not answer:

        abort(404)

    path = answer.get(
        "attachment_file"
    )

    if not path:

        abort(404)

    return send_storage_file(
        path,
        answer.get(
            "attachment_name"
        ) or "answer"
    )


# ============================================================
# ADMIN PAYMENTS
# ============================================================

@app.route(
    "/admin/payments"
)
@admin_required
def admin_payments():

    try:

        payments = db_select(
            "payments",
            {

                "select":
                    "*",

                "order":
                    "id.desc"
            }
        )

    except Exception as error:

        flash(
            "Could not load payments: "
            + str(error)
        )

        payments = []

    return page(
        """
<div class="card">

<h1>Payments</h1>

<p>
KOJA payment transactions.
</p>

</div>

<div class="card">

<table>

<tr>

<th>Reference</th>
<th>Amount</th>
<th>Network</th>
<th>Status</th>
<th>Date</th>

</tr>

{% for p in payments %}

<tr>

<td>
{{ p["tx_ref"] }}
</td>

<td>
K{{ p["amount"] }}
</td>

<td>
{{ p["network"] }}
</td>

<td>

{% if p["status"] == "successful" %}

<span class="badge answered">
Successful
</span>

{% elif p["status"] == "pending" %}

<span class="badge pending">
Pending
</span>

{% else %}

<span class="badge"
style="background:#fee2e2;color:#991b1b">
{{ p["status"] }}
</span>

{% endif %}

</td>

<td>
{{ p["created_at"] }}
</td>

</tr>

{% else %}

<tr>

<td colspan="5">
No payments found.
</td>

</tr>

{% endfor %}

</table>

</div>
        """,
        "Payments",
        payments=payments
    )


# ============================================================
# HEALTH CHECK
# ============================================================

@app.route(
    "/health"
)
def health():

    if not database_ready():

        return {

            "status":
                "error",

            "application":
                APP_NAME,

            "database":
                "not configured"

        }, 500

    try:

        db_select(
            "users",
            {
                "select":
                    "id",

                "limit":
                    "1"
            }
        )

        return {

            "status":
                "ok",

            "application":
                APP_NAME,

            "database":
                "connected",

            "payments":
                (
                    "configured"
                    if payment_ready()
                    else
                    "not configured"
                ),

            "storage":
                STORAGE_BUCKET

        }

    except Exception as error:

        return {

            "status":
                "error",

            "database":
                "not connected",

            "error":
                str(error)

        }, 500


# ============================================================
# STATUS
# ============================================================

@app.route(
    "/status"
)
def status():

    return {

        "application":
            APP_NAME,

        "supabase_configured":
            database_ready(),

        "payment_configured":
            payment_ready(),

        "storage_bucket":
            STORAGE_BUCKET,

        "host":
            HOST,

        "port":
            PORT,

        "https":
            HTTPS_ENABLED
    }


# ============================================================
# ERROR 413
# ============================================================

@app.errorhandler(413)
def too_large(error):

    return (
        "File too large. Maximum allowed size is 10 MB.",
        413
    )


# ============================================================
# ERROR 404
# ============================================================

@app.errorhandler(404)
def not_found(error):

    return page(
        """
<div class="card empty">

<h1>404</h1>

<h2>Page Not Found</h2>

<a class="btn"
href="{{ url_for('index') }}">
KOJA Home
</a>

</div>
        """,
        "404"
    ), 404


# ============================================================
# ERROR 500
# ============================================================

@app.errorhandler(500)
def server_error(error):

    return page(
        """
<div class="card">

<h1>Server Error</h1>

<div class="error">

KOJA encountered a server-side error.

</div>

<br>

<a class="btn"
href="{{ url_for('index') }}">
Return Home
</a>

</div>
        """,
        "Server Error"
    ), 500


# ============================================================
# START SERVER
# ============================================================

if __name__ == "__main__":

    print()
    print("=" * 60)
    print("KOJA AFRICA")
    print("=" * 60)

    print(
        "Supabase configured:",
        database_ready()
    )

    print(
        "Flutterwave configured:",
        payment_ready()
    )

    print(
        "Payment amount:",
        "K"
        + str(
            KOJA_PAYMENT_AMOUNT
        )
    )

    print(
        "Storage bucket:",
        STORAGE_BUCKET
    )

    print(
        "Host:",
        HOST
    )

    print(
        "Port:",
        PORT
    )

    print("=" * 60)
    print()

    app.run(
        host=HOST,
        port=PORT,
        debug=False,
        threaded=True,
        use_reloader=False
    ) 
