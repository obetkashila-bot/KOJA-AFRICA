import os
import io
import uuid
import secrets
import logging

from datetime import datetime, timezone
from functools import wraps
from urllib.parse import quote

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


# ============================================================
# CONFIGURATION
# ============================================================

load_dotenv()

app = Flask(__name__)

app.secret_key = os.getenv(
    "SECRET_KEY",
    secrets.token_hex(32)
)

app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024

logging.basicConfig(level=logging.INFO)

SUPABASE_URL = os.getenv(
    "SUPABASE_URL",
    ""
).rstrip("/")

SUPABASE_SERVICE_KEY = os.getenv(
    "SUPABASE_SERVICE_KEY",
    ""
)

ADMIN_USERNAME = os.getenv(
    "ADMIN_USERNAME",
    "admin"
)

ADMIN_PASSWORD = os.getenv(
    "ADMIN_PASSWORD",
    ""
)

STORAGE_BUCKET = os.getenv(
    "SUPABASE_STORAGE_BUCKET",
    "koja-assignments"
)

APP_NAME = "KOJA AFRICA"

APP_TAGLINE = "Your Request • KOJA Handles It"

STATUS_NEW = "New"
STATUS_PROCESSING = "Processing"
STATUS_COMPLETED = "Completed"

ALLOWED_EXTENSIONS = {
    "pdf",
    "doc",
    "docx",
    "txt",
    "jpg",
    "jpeg",
    "png",
    "webp",
    "xls",
    "xlsx",
    "ppt",
    "pptx",
    "zip",
}


# ============================================================
# SERVICES
# ============================================================

PUBLIC_SERVICES = [
    "Assignments",
    "University Applications",
    "Result Verification & Certification",
    "Farmer Registration",
    "TPN Centre",
    "Higher Education Materials",
]

SERVICE_DESCRIPTIONS = {
    "Assignments":
        "Submit academic assignments, questions, "
        "supporting documents and related academic work.",

    "University Applications":
        "Get assistance with university and higher "
        "education application requests and documents.",

    "Result Verification & Certification":
        "Submit academic result verification, "
        "certification and related document requests.",

    "Farmer Registration":
        "Submit farmer registration requests "
        "and supporting information.",

    "TPN Centre":
        "Submit TPN-related requests and "
        "supporting documents through KOJA.",

    "Higher Education Materials":
        "Request higher education materials, "
        "academic documents and related resources.",
}


# ============================================================
# HELPERS
# ============================================================

def configuration_ok():
    return bool(
        SUPABASE_URL and
        SUPABASE_SERVICE_KEY
    )


def require_configuration():
    if not configuration_ok():
        raise RuntimeError(
            "SUPABASE_URL and SUPABASE_SERVICE_KEY "
            "are not configured."
        )


def now_iso():
    return datetime.now(
        timezone.utc
    ).isoformat()


def clean(value, maximum=5000):
    return (value or "").strip()[:maximum]


def allowed_file(filename):
    if not filename:
        return False

    if "." not in filename:
        return False

    extension = (
        filename.rsplit(".", 1)[1].lower()
    )

    return extension in ALLOWED_EXTENSIONS


def safe_filename(filename):
    filename = os.path.basename(
        filename or "file"
    )

    filename = filename.replace(
        "\x00",
        ""
    )

    return filename[:180]


def client_status_label(status):
    if status == STATUS_NEW:
        return "Request Received"

    if status == STATUS_PROCESSING:
        return "KOJA Is Working on It"

    if status == STATUS_COMPLETED:
        return "Ready — Completed"

    return status or "Request Received"


def status_class(status):
    if status == STATUS_COMPLETED:
        return "completed"

    if status == STATUS_PROCESSING:
        return "processing"

    return "new"


# ============================================================
# SUPABASE REST API
# ============================================================

def supabase_headers(prefer=None):
    require_configuration()

    headers = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization":
            "Bearer " + SUPABASE_SERVICE_KEY,
        "Content-Type": "application/json",
    }

    if prefer:
        headers["Prefer"] = prefer

    return headers


def supabase_request(
    method,
    path,
    **kwargs
):
    require_configuration()

    url = (
        SUPABASE_URL
        + "/rest/v1/"
        + path
    )

    supplied_headers = kwargs.pop(
        "headers",
        {}
    )

    headers = supabase_headers()

    headers.update(
        supplied_headers
    )

    response = requests.request(
        method,
        url,
        headers=headers,
        timeout=30,
        **kwargs
    )

    if not response.ok:
        logging.error(
            "Supabase request failed: "
            "%s %s %s %s",
            method,
            path,
            response.status_code,
            response.text[:2000]
        )

        raise RuntimeError(
            "Supabase request failed "
            f"({response.status_code}): "
            f"{response.text[:700]}"
        )

    if not response.text:
        return None

    try:
        return response.json()
    except Exception:
        return response.text


def db_select(
    table,
    select="*",
    filters=None,
    order=None,
    limit=None
):
    params = {
        "select": select
    }

    if filters:
        params.update(filters)

    if order:
        params["order"] = order

    if limit:
        params["limit"] = str(limit)

    return supabase_request(
        "GET",
        table,
        params=params
    )


def db_insert(
    table,
    data,
    returning=True
):
    prefer = (
        "return=representation"
        if returning
        else
        "return=minimal"
    )

    return supabase_request(
        "POST",
        table,
        headers={
            "Prefer": prefer
        },
        json=data
    )


def db_update(
    table,
    filters,
    data,
    returning=True
):
    prefer = (
        "return=representation"
        if returning
        else
        "return=minimal"
    )

    return supabase_request(
        "PATCH",
        table,
        headers={
            "Prefer": prefer
        },
        params=dict(filters),
        json=data
    )


# ============================================================
# SUPABASE STORAGE
# ============================================================

def storage_upload(
    file_storage,
    folder="supporting"
):
    require_configuration()

    original_name = safe_filename(
        file_storage.filename
    )

    extension = ""

    if "." in original_name:
        extension = (
            original_name
            .rsplit(".", 1)[1]
            .lower()
        )

    unique_name = (
        uuid.uuid4().hex
        + (
            "." + extension
            if extension
            else ""
        )
    )

    storage_path = (
        folder
        + "/"
        + unique_name
    )

    content_type = (
        file_storage.mimetype
        or "application/octet-stream"
    )

    url = (
        SUPABASE_URL
        + "/storage/v1/object/"
        + quote(
            STORAGE_BUCKET,
            safe=""
        )
        + "/"
        + quote(
            storage_path,
            safe="/"
        )
    )

    headers = {
        "Authorization":
            "Bearer " + SUPABASE_SERVICE_KEY,

        "apikey":
            SUPABASE_SERVICE_KEY,

        "Content-Type":
            content_type,

        "x-upsert":
            "false",
    }

    file_storage.stream.seek(0)

    response = requests.post(
        url,
        headers=headers,
        data=file_storage.stream,
        timeout=90
    )

    if not response.ok:
        raise RuntimeError(
            "File upload failed "
            f"({response.status_code}): "
            f"{response.text[:700]}"
        )

    return {
        "path": storage_path,
        "file_name": original_name,
        "content_type": content_type,
        "size": request.content_length or 0,
    }


def storage_download(path):
    require_configuration()

    url = (
        SUPABASE_URL
        + "/storage/v1/object/"
        + quote(
            STORAGE_BUCKET,
            safe=""
        )
        + "/"
        + quote(
            path,
            safe="/"
        )
    )

    headers = {
        "Authorization":
            "Bearer " + SUPABASE_SERVICE_KEY,

        "apikey":
            SUPABASE_SERVICE_KEY,
    }

    response = requests.get(
        url,
        headers=headers,
        timeout=90
    )

    if not response.ok:
        raise RuntimeError(
            "Storage download failed "
            f"({response.status_code}): "
            f"{response.text[:700]}"
        )

    return response


# ============================================================
# REQUEST NUMBER
# ============================================================

def generate_request_number():
    date_part = datetime.now(
        timezone.utc
    ).strftime("%Y%m%d")

    random_part = secrets.token_hex(
        4
    ).upper()

    return (
        "KOJA-"
        + date_part
        + "-"
        + random_part
    )


def create_unique_request_number():
    for _ in range(15):

        number = generate_request_number()

        existing = db_select(
            "koja_service_requests",
            select="id",
            filters={
                "request_number":
                    "eq." + number
            },
            limit=1
        )

        if not existing:
            return number

    raise RuntimeError(
        "Could not generate a unique request number."
    )


# ============================================================
# AUTH DECORATORS
# ============================================================

def client_login_required(function):

    @wraps(function)
    def wrapper(*args, **kwargs):

        if not session.get("client_id"):

            flash(
                "Please create a KOJA account "
                "or log in first."
            )

            return redirect(
                url_for(
                    "login",
                    next_service=session.get(
                        "selected_service",
                        ""
                    )
                )
            )

        return function(
            *args,
            **kwargs
        )

    return wrapper


def admin_required(function):

    @wraps(function)
    def wrapper(*args, **kwargs):

        if not session.get(
            "admin_logged_in"
        ):

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
# HTML / DESIGN
# ============================================================

BASE_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">

<meta name="viewport"
      content="width=device-width,
               initial-scale=1.0">

<title>{{ title or "KOJA AFRICA" }}</title>

<style>

* {
    box-sizing: border-box;
}

body {
    margin: 0;
    font-family:
        Arial,
        Helvetica,
        sans-serif;

    background: #f5f7fb;
    color: #172033;
}

header {
    background: #ffffff;
    border-bottom: 1px solid #e5e7eb;
    padding: 15px;
    position: sticky;
    top: 0;
    z-index: 20;
}

.nav {
    max-width: 1100px;
    margin: auto;

    display: flex;
    align-items: center;
    justify-content: space-between;

    gap: 15px;
}

.logo {
    font-size: 23px;
    font-weight: 800;
    color: #173b8f;
}

.logo span:nth-child(1) {
    color: #1769e0;
}

.logo span:nth-child(2) {
    color: #18a957;
}

.logo span:nth-child(3) {
    color: #e53935;
}

.logo span:nth-child(4) {
    color: #173b8f;
}

nav {
    display: flex;
    flex-wrap: wrap;
    gap: 7px;
}

nav a {
    text-decoration: none;
    color: #243047;
    padding: 9px 11px;
    border-radius: 8px;
    font-size: 14px;
}

nav a:hover {
    background: #eef3ff;
}

.container {
    width: 94%;
    max-width: 1100px;
    margin: 30px auto;
}

.hero {
    background: linear-gradient(
        135deg,
        #173b8f,
        #1769e0
    );

    color: white;
    padding: 55px 25px;
    border-radius: 20px;
    text-align: center;
}

.hero h1 {
    font-size: 42px;
    margin: 0 0 12px;
}

.hero p {
    font-size: 18px;
    line-height: 1.6;
    max-width: 700px;
    margin: 0 auto 25px;
}

.btn {
    display: inline-block;
    border: none;
    cursor: pointer;
    text-decoration: none;

    background: #1769e0;
    color: white;

    padding: 12px 18px;
    border-radius: 9px;

    font-weight: 700;
}

.btn:hover {
    opacity: .9;
}

.btn-light {
    background: white;
    color: #173b8f;
}

.btn-success {
    background: #168a48;
}

.btn-warning {
    background: #c98200;
}

.card-grid {
    display: grid;

    grid-template-columns:
        repeat(
            auto-fit,
            minmax(240px, 1fr)
        );

    gap: 18px;
}

.card {
    background: white;

    border: 1px solid #e3e7ef;
    border-radius: 16px;

    padding: 22px;

    box-shadow:
        0 5px 20px
        rgba(0,0,0,.04);
}

.card h3 {
    margin-top: 0;
}

.service-icon {
    font-size: 38px;
    margin-bottom: 8px;
}

.form-card {
    background: white;
    max-width: 720px;
    margin: auto;

    padding: 25px;

    border-radius: 16px;

    box-shadow:
        0 5px 25px
        rgba(0,0,0,.05);
}

label {
    display: block;
    font-weight: 700;
    margin-top: 15px;
    margin-bottom: 6px;
}

input,
select,
textarea {
    width: 100%;

    padding: 12px;

    border: 1px solid #ccd3df;
    border-radius: 8px;

    font-size: 15px;
}

textarea {
    min-height: 150px;
    resize: vertical;
}

.flash {
    max-width: 1100px;
    width: 94%;
    margin: 15px auto;

    padding: 12px 15px;

    background: #fff8df;
    border: 1px solid #f0d675;

    border-radius: 8px;
}

footer {
    margin-top: 50px;
    padding: 30px 15px;

    background: #172033;
    color: white;

    text-align: center;
}

.small {
    color: #667085;
    font-size: 14px;
    line-height: 1.6;
}

.service-card {
    display: flex;
    flex-direction: column;
    justify-content: space-between;
}

@media(max-width: 700px) {

    .hero h1 {
        font-size: 31px;
    }

    nav {
        display: none;
    }

    .container {
        margin-top: 20px;
    }
}

</style>
</head>

<body>

<header>

<div class="nav">

<a href="{{ url_for('home') }}"
   style="text-decoration:none">

<div class="logo">
<span>k</span><span>o</span><span>j</span><span>a</span>
<span style="margin-left:5px">
AFRICA
</span>
</div>

</a>

<nav>

{% if session.get("client_id") %}

<a href="{{ url_for('dashboard') }}">
Dashboard
</a>

<a href="{{ url_for('services') }}">
Services
</a>

<a href="{{ url_for('new_request') }}">
New Request
</a>

<a href="{{ url_for('my_requests') }}">
My Requests
</a>

<a href="{{ url_for('notifications') }}">
Notifications
</a>

<a href="{{ url_for('profile') }}">
Profile
</a>

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

</nav>

</div>

</header>

{% with messages = get_flashed_messages() %}

{% for message in messages %}

<div class="flash">
{{ message }}
</div>

{% endfor %}

{% endwith %}

<main class="container">

{{ body|safe }}

</main>

<footer>

<strong>KOJA AFRICA</strong>

<p>
{{ tagline }}
</p>

<p class="small" style="color:#cbd5e1">
Your Request → KOJA Handles It → You Receive the Result
</p>

</footer>

</body>
</html>
"""


def page(
    title,
    body_template,
    **context
):

    body = render_template_string(
        body_template,
        **context
    )

    return render_template_string(
        BASE_HTML,
        title=title,
        body=body,
        tagline=APP_TAGLINE
    )


# ============================================================
# HOME
# ============================================================

@app.route("/")
def home():

    body = """

<div class="hero">

<h1>KOJA AFRICA</h1>

<p>
Your Request • KOJA Handles It
</p>

<p>
Choose the service you need and let
KOJA AFRICA handle your request.
</p>

<a class="btn btn-light"
   href="{{ url_for('services') }}">

Get Started

</a>

</div>

"""

    return page(
        "KOJA AFRICA",
        body
    )


# ============================================================
# SERVICES
# ============================================================

@app.route("/services")
def services():

    body = """

<h1>KOJA AFRICA Services</h1>

<p class="small">
Choose the service you need. You will be
asked for the information relevant to that
specific service.
</p>

<div class="card-grid">

{% for service in services %}

<div class="card service-card">

<div>

<div class="service-icon">

{% if service == "Assignments" %}
📚
{% elif service == "University Applications" %}
🎓
{% elif service == "Result Verification & Certification" %}
📄
{% elif service == "Farmer Registration" %}
🧑‍🌾
{% elif service == "TPN Centre" %}
📋
{% else %}
📖
{% endif %}

</div>

<h3>
{{ service }}
</h3>

<p class="small">
{{ descriptions.get(service, "") }}
</p>

</div>

<a class="btn"
   href="{{ url_for(
       'service_start',
       service=service
   ) }}">

Select Service

</a>

</div>

{% endfor %}

</div>

"""

    return page(
        "KOJA Services",
        body,
        services=PUBLIC_SERVICES,
        descriptions=SERVICE_DESCRIPTIONS
    )


# ============================================================
# SERVICE START
# ============================================================

@app.route("/service/<service>")
def service_start(service):

    service = clean(
        service,
        200
    )

    if service not in PUBLIC_SERVICES:
        abort(404)

    session[
        "selected_service"
    ] = service

    if session.get("client_id"):

        return redirect(
            url_for(
                "new_request",
                service=service
            )
        )

    return redirect(
        url_for(
            "register",
            service=service
        )
    )


# ============================================================
# REGISTER
# ============================================================

@app.route(
    "/register",
    methods=["GET", "POST"]
)
def register():

    selected_service = clean(
        request.args.get("service")
        or session.get(
            "selected_service",
            ""
        ),
        200
    )

    if (
        selected_service
        and
        selected_service not in PUBLIC_SERVICES
    ):
        selected_service = ""

    if selected_service:

        session[
            "selected_service"
        ] = selected_service

    if request.method == "POST":

        name = clean(
            request.form.get("name"),
            150
        )

        email = clean(
            request.form.get("email"),
            180
        ).lower()

        phone = clean(
            request.form.get("phone"),
            60
        )

        password = request.form.get(
            "password",
            ""
        )

        if not name:

            flash(
                "Full name is required."
            )

            return redirect(
                url_for(
                    "register",
                    service=selected_service
                )
            )

        if not email:

            flash(
                "Email address is required."
            )

            return redirect(
                url_for(
                    "register",
                    service=selected_service
                )
            )

        if not phone:

            flash(
                "Phone/contact is required."
            )

            return redirect(
                url_for(
                    "register",
                    service=selected_service
                )
            )

        if len(password) < 6:

            flash(
                "Password must be at least "
                "6 characters."
            )

            return redirect(
                url_for(
                    "register",
                    service=selected_service
                )
            )

        try:

            existing = db_select(
                "koja_clients",
                select="id",
                filters={
                    "email":
                        "eq." + email
                },
                limit=1
            )

            if existing:

                flash(
                    "An account with "
                    "that email already exists."
                )

                return redirect(
                    url_for(
                        "login",
                        next_service=selected_service
                    )
                )

            result = db_insert(
                "koja_clients",
                {
                    "name": name,
                    "email": email,
                    "phone": phone,

                    # University fields deliberately
                    # remain empty at registration.
                    "university": "",
                    "mode_of_study": "",
                    "school": "",
                    "programme": "",
                    "academic_level": "",
                    "year_of_study": "",
                    "student_number": "",

                    "password_hash":
                        generate_password_hash(
                            password
                        ),

                    "created_at":
                        now_iso(),

                    "updated_at":
                        now_iso(),
                }
            )

            client = result[0]

            session.clear()

            session[
                "client_id"
            ] = client["id"]

            session[
                "client_name"
            ] = client["name"]

            session[
                "client_email"
            ] = client["email"]

            if selected_service:

                session[
                    "selected_service"
                ] = selected_service

            flash(
                "Account created successfully."
            )

            # IMPORTANT:
            # We now send the user to Services.
            return redirect(
                url_for("services")
            )

        except Exception as exc:

            logging.exception(
                "Registration failed"
            )

            flash(
                "Registration error: "
                + str(exc)[:350]
            )

    body = """

<div class="form-card">

<h2>Create KOJA Account</h2>

<p class="small">

Create your KOJA AFRICA account first.
University information is NOT required here.

</p>

{% if selected_service %}

<p>

<strong>Selected Service:</strong><br>

{{ selected_service }}

</p>

{% endif %}

<form method="POST">

<label>
Full Name *
</label>

<input
    name="name"
    required
    autocomplete="name"
    placeholder="Your full name"
>

<label>
Email Address *
</label>

<input
    type="email"
    name="email"
    required
    autocomplete="email"
    placeholder="you@example.com"
>

<label>
Phone / Contact *
</label>

<input
    name="phone"
    required
    placeholder="e.g. 097xxxxxxx"
>

<label>
Password *
</label>

<input
    type="password"
    name="password"
    required
    minlength="6"
    autocomplete="new-password"
    placeholder="At least 6 characters"
>

<br><br>

<button
    class="btn"
    type="submit"
>
Create Account
</button>

</form>

<p>
Already have an account?

<a href="{{ url_for(
    'login',
    next_service=selected_service
) }}">
Login
</a>

</p>

</div>

"""

    return page(
        "Create Account",
        body,
        selected_service=selected_service
    )
   # ============================================================
# LOGIN
# ============================================================

@app.route("/login", methods=["GET", "POST"])
def login():

    next_service = clean(
        request.args.get("next_service")
        or session.get("selected_service", ""),
        200
    )

    if next_service not in PUBLIC_SERVICES:
        next_service = ""

    if next_service:
        session["selected_service"] = next_service

    if request.method == "POST":

        email = clean(
            request.form.get("email"),
            180
        ).lower()

        password = request.form.get(
            "password",
            ""
        )

        try:

            clients = db_select(
                "koja_clients",
                select="*",
                filters={
                    "email": "eq." + email
                },
                limit=1
            )

            if not clients:
                flash(
                    "Invalid email or password."
                )
                return redirect(
                    url_for(
                        "login",
                        next_service=next_service
                    )
                )

            client = clients[0]

            if not check_password_hash(
                client["password_hash"],
                password
            ):
                flash(
                    "Invalid email or password."
                )
                return redirect(
                    url_for(
                        "login",
                        next_service=next_service
                    )
                )

            session.clear()

            session["client_id"] = client["id"]
            session["client_name"] = client["name"]
            session["client_email"] = client["email"]

            if next_service:
                session["selected_service"] = next_service

                return redirect(
                    url_for(
                        "new_request",
                        service=next_service
                    )
                )

            return redirect(
                url_for("services")
            )

        except Exception as exc:

            logging.exception(
                "Login failed"
            )

            flash(
                "Login error: "
                + str(exc)[:350]
            )

    body = """

<div class="form-card">

<h2>KOJA Client Login</h2>

<form method="POST">

<label>Email Address</label>

<input
    type="email"
    name="email"
    required
    autocomplete="email"
>

<label>Password</label>

<input
    type="password"
    name="password"
    required
    autocomplete="current-password"
>

<br><br>

<button
    class="btn"
    type="submit"
>
Login
</button>

</form>

<p>
No account?

<a href="{{ url_for(
    'register',
    service=next_service
) }}">
Create one
</a>
</p>

</div>

"""

    return page(
        "Client Login",
        body,
        next_service=next_service
    )


# ============================================================
# LOGOUT
# ============================================================

@app.route("/logout")
def logout():

    session.clear()

    flash(
        "You have been logged out."
    )

    return redirect(
        url_for("home")
    )


# ============================================================
# PROFILE
# ============================================================

@app.route(
    "/profile",
    methods=["GET", "POST"]
)
@client_login_required
def profile():

    rows = db_select(
        "koja_clients",
        select="*",
        filters={
            "id":
                "eq." + session["client_id"]
        },
        limit=1
    )

    if not rows:

        session.clear()

        flash(
            "Client profile not found."
        )

        return redirect(
            url_for("register")
        )

    client = rows[0]

    if request.method == "POST":

        data = {
            "name": clean(
                request.form.get("name"),
                150
            ),

            "phone": clean(
                request.form.get("phone"),
                60
            ),

            "updated_at": now_iso()
        }

        if not data["name"]:

            flash(
                "Name is required."
            )

            return redirect(
                url_for("profile")
            )

        try:

            db_update(
                "koja_clients",
                {
                    "id":
                        "eq." + session["client_id"]
                },
                data,
                returning=False
            )

            session["client_name"] = data["name"]

            flash(
                "Profile updated successfully."
            )

            return redirect(
                url_for("profile")
            )

        except Exception as exc:

            logging.exception(
                "Profile update failed"
            )

            flash(
                "Profile update error: "
                + str(exc)[:350]
            )

    body = """

<div class="form-card">

<h2>My Profile</h2>

<form method="POST">

<label>Full Name</label>

<input
    name="name"
    value="{{ client.name or '' }}"
    required
>

<label>Email</label>

<input
    value="{{ client.email or '' }}"
    disabled
>

<label>Phone / Contact</label>

<input
    name="phone"
    value="{{ client.phone or '' }}"
    required
>

<br><br>

<button
    class="btn"
    type="submit"
>
Save Profile
</button>

</form>

</div>

"""

    return page(
        "My Profile",
        body,
        client=client
    )


# ============================================================
# NEW REQUEST
#
# IMPORTANT:
# University information is ONLY displayed for
# "University Applications".
# ============================================================

@app.route(
    "/request/new",
    methods=["GET", "POST"]
)
@client_login_required
def new_request():

    selected_service = clean(
        request.args.get("service")
        or session.get(
            "selected_service",
            ""
        ),
        200
    )

    if (
        selected_service
        and selected_service not in PUBLIC_SERVICES
    ):
        selected_service = ""

    if selected_service:
        session["selected_service"] = selected_service

    services = db_select(
        "koja_services",
        select="*",
        filters={
            "active": "eq.true"
        },
        order="name.asc"
    )

    # Fallback in case the database service table
    # has not yet been populated.
    if not services:

        services = [
            {
                "name": service
            }
            for service in PUBLIC_SERVICES
        ]

    universities = []

    if selected_service == "University Applications":

        universities = db_select(
            "koja_universities",
            select="*",
            filters={
                "active": "eq.true"
            },
            order="name.asc"
        )

    clients = db_select(
        "koja_clients",
        select="*",
        filters={
            "id":
                "eq." + session["client_id"]
        },
        limit=1
    )

    client = (
        clients[0]
        if clients
        else {}
    )

    if request.method == "POST":

        service_type = clean(
            request.form.get(
                "service_type"
            ),
            200
        )

        description = clean(
            request.form.get(
                "description"
            ),
            10000
        )

        supporting_file = request.files.get(
            "supporting_file"
        )

        if service_type not in PUBLIC_SERVICES:

            flash(
                "Please select a valid service."
            )

            return redirect(
                url_for(
                    "new_request",
                    service=selected_service
                )
            )

        if not description:

            flash(
                "Please describe the request."
            )

            return redirect(
                url_for(
                    "new_request",
                    service=service_type
                )
            )

        # ----------------------------------------------------
        # UNIVERSITY INFORMATION
        # Only collect this for University Applications.
        # ----------------------------------------------------

        university = ""
        mode_of_study = ""
        school = ""
        programme = ""
        academic_level = ""
        year_of_study = ""
        student_number = ""

        if service_type == "University Applications":

            university = clean(
                request.form.get("university"),
                200
            )

            mode_of_study = clean(
                request.form.get(
                    "mode_of_study"
                ),
                80
            )

            school = clean(
                request.form.get("school"),
                200
            )

            programme = clean(
                request.form.get("programme"),
                250
            )

            academic_level = clean(
                request.form.get(
                    "academic_level"
                ),
                100
            )

            year_of_study = clean(
                request.form.get(
                    "year_of_study"
                ),
                80
            )

            student_number = clean(
                request.form.get(
                    "student_number"
                ),
                100
            )

            if not university:

                flash(
                    "Please select the university."
                )

                return redirect(
                    url_for(
                        "new_request",
                        service=service_type
                    )
                )

        # ----------------------------------------------------
        # FILE VALIDATION
        # ----------------------------------------------------

        if (
            supporting_file
            and
            supporting_file.filename
        ):

            if not allowed_file(
                supporting_file.filename
            ):

                flash(
                    "Unsupported file type."
                )

                return redirect(
                    url_for(
                        "new_request",
                        service=service_type
                    )
                )

        try:

            request_number = (
                create_unique_request_number()
            )

            created = db_insert(
                "koja_service_requests",
                {
                    "request_number":
                        request_number,

                    "client_id":
                        session["client_id"],

                    "client_name":
                        session["client_name"],

                    "client_email":
                        session["client_email"],

                    "client_phone":
                        client.get(
                            "phone",
                            ""
                        ),

                    "service_type":
                        service_type,

                    "description":
                        description,

                    # University information is blank
                    # for non-university services.
                    "university":
                        university,

                    "mode_of_study":
                        mode_of_study,

                    "school":
                        school,

                    "programme":
                        programme,

                    "academic_level":
                        academic_level,

                    "year_of_study":
                        year_of_study,

                    "student_number":
                        student_number,

                    "status":
                        STATUS_NEW,

                    "admin_message":
                        "",

                    "created_at":
                        now_iso(),

                    "updated_at":
                        now_iso(),
                }
            )

            item = created[0]

            request_id = item["id"]

            # ------------------------------------------------
            # SUPPORTING FILE
            # ------------------------------------------------

            if (
                supporting_file
                and
                supporting_file.filename
            ):

                upload = storage_upload(
                    supporting_file,
                    folder=(
                        "supporting/"
                        + str(request_id)
                    )
                )

                db_insert(
                    "koja_request_files",
                    {
                        "request_id":
                            request_id,

                        "file_name":
                            upload["file_name"],

                        "file_url":
                            upload["path"],

                        "file_type":
                            upload["content_type"],

                        "file_size":
                            upload["size"],

                        "uploaded_by":
                            session["client_email"],

                        "created_at":
                            now_iso(),
                    },
                    returning=False
                )

            # ------------------------------------------------
            # HISTORY
            # ------------------------------------------------

            db_insert(
                "koja_request_history",
                {
                    "request_id":
                        request_id,

                    "old_status":
                        None,

                    "new_status":
                        STATUS_NEW,

                    "message":
                        "Request submitted to KOJA AFRICA.",

                    "changed_by":
                        session["client_email"],

                    "created_at":
                        now_iso(),
                },
                returning=False
            )

            # ------------------------------------------------
            # NOTIFICATION
            # ------------------------------------------------

            db_insert(
                "koja_notifications",
                {
                    "client_email":
                        session["client_email"],

                    "request_id":
                        request_id,

                    "title":
                        "KOJA Request Received",

                    "message":
                        (
                            "Your KOJA request "
                            + request_number
                            + " has been received. "
                            "KOJA will handle your "
                            "request and update you "
                            "through your account."
                        ),

                    "is_read":
                        False,

                    "created_at":
                        now_iso(),
                },
                returning=False
            )

            session.pop(
                "selected_service",
                None
            )

            flash(
                "Request received successfully. "
                "Reference: "
                + request_number
            )

            return redirect(
                url_for(
                    "request_detail",
                    request_id=request_id
                )
            )

        except Exception as exc:

            logging.exception(
                "Request submission failed"
            )

            flash(
                "Could not submit request: "
                + str(exc)[:400]
            )

    modes = [
        "Full-Time",
        "Part-Time",
        "Distance Learning",
        "Online",
        "Evening",
        "Weekend",
        "Blended",
        "Other"
    ]

    levels = [
        "Certificate",
        "Diploma",
        "Undergraduate",
        "Postgraduate",
        "Masters",
        "PhD",
        "Other"
    ]

    body = """

<div class="form-card">

<h2>Start a KOJA Request</h2>

{% if selected_service %}

<p>

<strong>Selected Service:</strong>

<br>

{{ selected_service }}

</p>

{% endif %}

<form
    method="POST"
    enctype="multipart/form-data"
>

<label>
Service *
</label>

<select
    name="service_type"
    required
    onchange="changeService(this.value)"
>

<option value="">
-- Select Service --
</option>

{% for service in services %}

<option
    value="{{ service.name }}"
    {% if selected_service == service.name %}
    selected
    {% endif %}
>
{{ service.name }}
</option>

{% endfor %}

</select>


<label>
Describe the Work / Request *
</label>

<textarea
    name="description"
    required
    placeholder="Explain what you need KOJA to handle..."
></textarea>


<!-- ======================================================
     UNIVERSITY SECTION
     ONLY VISIBLE FOR UNIVERSITY APPLICATIONS
     ====================================================== -->

<div
    id="universitySection"
    style="
        display:
        {% if selected_service == 'University Applications' %}
        block
        {% else %}
        none
        {% endif %};
        margin-top:25px;
        padding:20px;
        background:#f4f7ff;
        border-radius:12px;
    "
>

<h3>
University Application Information
</h3>

<p class="small">
These details are required because you selected
University Applications.
</p>


<label>
University *
</label>

<select
    name="university"
>

<option value="">
-- Select University --
</option>

{% for university in universities %}

<option value="{{ university.name }}">
{{ university.name }}
</option>

{% endfor %}

</select>


<label>
Mode of Study
</label>

<select
    name="mode_of_study"
>

<option value="">
-- Select Mode --
</option>

{% for mode in modes %}

<option value="{{ mode }}">
{{ mode }}
</option>

{% endfor %}

</select>


<label>
School / Faculty
</label>

<input
    name="school"
    placeholder="e.g. School of Natural Sciences"
>


<label>
Programme / Course
</label>

<input
    name="programme"
    placeholder="e.g. Bachelor of Science"
>


<label>
Academic Level
</label>

<select
    name="academic_level"
>

<option value="">
-- Select Level --
</option>

{% for level in levels %}

<option value="{{ level }}">
{{ level }}
</option>

{% endfor %}

</select>


<label>
Year of Study
</label>

<input
    name="year_of_study"
    placeholder="e.g. Year 2"
>


<label>
Student Number
</label>

<input
    name="student_number"
    placeholder="University student number"
>

</div>


<label>
Supporting Document
</label>

<input
    type="file"
    name="supporting_file"
>

<p class="small">
Maximum upload size: 25 MB.
<br>
Supported formats:
PDF, Word, TXT, images, Excel,
PowerPoint and ZIP.
</p>

<br>

<button
    class="btn"
    type="submit"
>
Send Request to KOJA
</button>

</form>

</div>


<script>

function changeService(value) {

    const section =
        document.getElementById(
            "universitySection"
        );

    if (
        value ===
        "University Applications"
    ) {

        section.style.display =
            "block";

    } else {

        section.style.display =
            "none";

    }
}

</script>

"""

    return page(
        "New Request",
        body,
        services=services,
        universities=universities,
        client=client,
        modes=modes,
        levels=levels,
        selected_service=selected_service
    )


# ============================================================
# CLIENT DASHBOARD
# ============================================================

@app.route("/dashboard")
@client_login_required
def dashboard():

    email = session[
        "client_email"
    ]

    requests_data = db_select(
        "koja_service_requests",
        select="*",
        filters={
            "client_email":
                "eq." + email
        },
        order="created_at.desc",
        limit=100
    )

    unread = db_select(
        "koja_notifications",
        select="id",
        filters={
            "client_email":
                "eq." + email,

            "is_read":
                "eq.false"
        },
        limit=100
    )

    completed_count = sum(
        1
        for r in requests_data
        if r.get("status")
        == STATUS_COMPLETED
    )

    body = """

<h1>
Welcome, {{ session.get("client_name") }}
</h1>

<p class="small">
Manage your KOJA requests and receive
completed results here.
</p>

<p>

<a
    class="btn"
    href="{{ url_for('services') }}"
>
Start a Request
</a>

</p>


<div class="card-grid">

<div class="card">
<h3>Total Requests</h3>
<h2>{{ requests_data|length }}</h2>
</div>

<div class="card">
<h3>Unread Notifications</h3>
<h2>{{ unread|length }}</h2>
</div>

<div class="card">
<h3>Completed</h3>
<h2>{{ completed_count }}</h2>
</div>

</div>


<br>

<div class="card">

<h2>Recent Requests</h2>

{% if requests_data %}

{% for r in requests_data %}

<div style="
    padding:15px 0;
    border-bottom:1px solid #eee;
">

<strong>
{{ r.request_number }}
</strong>

<br>

{{ r.service_type }}

<br>

<span>
{{ client_status_label(r.status) }}
</span>

<br><br>

<a
    class="btn"
    href="{{ url_for(
        'request_detail',
        request_id=r.id
    ) }}"
>
View Request
</a>

</div>

{% endfor %}

{% else %}

<p>
You have not submitted any requests yet.
</p>

{% endif %}

</div>

"""

    return page(
        "Dashboard",
        body,
        requests_data=requests_data,
        unread=unread,
        completed_count=completed_count
    )


# ============================================================
# MY REQUESTS
# ============================================================

@app.route("/requests")
@client_login_required
def my_requests():

    requests_data = db_select(
        "koja_service_requests",
        select="*",
        filters={
            "client_email":
                "eq." + session[
                    "client_email"
                ]
        },
        order="created_at.desc"
    )

    body = """

<h2>My KOJA Requests</h2>

{% if requests_data %}

<div class="card">

{% for r in requests_data %}

<div style="
    padding:18px 0;
    border-bottom:1px solid #eee;
">

<strong>
{{ r.request_number }}
</strong>

<p>
{{ r.service_type }}
</p>

<p>
{{ client_status_label(r.status) }}
</p>

<p class="small">
{{ r.created_at[:10]
   if r.created_at else '' }}
</p>

<a
    class="btn"
    href="{{ url_for(
        'request_detail',
        request_id=r.id
    ) }}"
>
Open Request
</a>

</div>

{% endfor %}

</div>

{% else %}

<div class="card">

<p>
No requests found.
</p>

<a
    class="btn"
    href="{{ url_for('services') }}"
>
Start a Request
</a>

</div>

{% endif %}

"""

    return page(
        "My Requests",
        body,
        requests_data=requests_data
    )


# ============================================================
# REQUEST DETAIL
# ============================================================

@app.route(
    "/request/<request_id>"
)
@client_login_required
def request_detail(request_id):

    rows = db_select(
        "koja_service_requests",
        select="*",
        filters={
            "id":
                "eq." + request_id,

            "client_email":
                "eq." + session[
                    "client_email"
                ]
        },
        limit=1
    )

    if not rows:
        abort(404)

    item = rows[0]

    files = db_select(
        "koja_request_files",
        select="*",
        filters={
            "request_id":
                "eq." + request_id
        },
        order="created_at.asc"
    )

    history = db_select(
        "koja_request_history",
        select="*",
        filters={
            "request_id":
                "eq." + request_id
        },
        order="created_at.desc"
    )

    body = """

<div class="card">

<h2>
{{ item.request_number }}
</h2>

<p>
<strong>
{{ client_status_label(item.status) }}
</strong>
</p>


<h3>Service</h3>

<p>
<strong>
{{ item.service_type }}
</strong>
</p>

<p>
{{ item.description }}
</p>


{% if item.service_type ==
      'University Applications' %}

<h3>
University Information
</h3>

<p>
<strong>University:</strong>
{{ item.university or 'Not provided' }}
</p>

<p>
<strong>Mode of Study:</strong>
{{ item.mode_of_study or 'Not provided' }}
</p>

<p>
<strong>School:</strong>
{{ item.school or 'Not provided' }}
</p>

<p>
<strong>Programme:</strong>
{{ item.programme or 'Not provided' }}
</p>

<p>
<strong>Academic Level:</strong>
{{ item.academic_level or 'Not provided' }}
</p>

<p>
<strong>Year:</strong>
{{ item.year_of_study or 'Not provided' }}
</p>

<p>
<strong>Student Number:</strong>
{{ item.student_number or 'Not provided' }}
</p>

{% endif %}


<h3>
Supporting Documents
</h3>

{% if files %}

{% for f in files %}

<p>

<strong>
{{ f.file_name }}
</strong>

<br>

<a
    class="btn"
    href="{{ url_for(
        'download_supporting_file',
        file_id=f.id
    ) }}"
>
Download Supporting Document
</a>

</p>

{% endfor %}

{% else %}

<p>
No supporting document uploaded.
</p>

{% endif %}


{% if item.admin_message %}

<h3>
Message from KOJA
</h3>

<div class="card">
{{ item.admin_message }}
</div>

{% endif %}


{% if item.status == 'Completed'
      and item.completed_file_url %}

<h3>
KOJA Completed Result
</h3>

<p>
<strong>
{{ item.completed_file_name }}
</strong>
</p>

<a
    class="btn btn-success"
    href="{{ url_for(
        'download_completed_file',
        request_id=item.id
    ) }}"
>
Download Your KOJA Result
</a>

{% endif %}


<h3>
Request History
</h3>

{% for h in history %}

<div style="
    padding:12px 0;
    border-bottom:1px solid #eee;
">

<strong>
{{ client_status_label(
    h.new_status
) }}
</strong>

<br>

{{ h.message or '' }}

<br>

<span class="small">
{{ h.created_at or '' }}
</span>

</div>

{% endfor %}

</div>

"""

    return page(
        "Request " + item["request_number"],
        body,
        item=item,
        files=files,
        history=history
    )


# ============================================================
# SUPPORTING FILE DOWNLOAD
# ============================================================

@app.route(
    "/file/supporting/<file_id>"
)
@client_login_required
def download_supporting_file(file_id):

    files = db_select(
        "koja_request_files",
        select="*",
        filters={
            "id":
                "eq." + file_id
        },
        limit=1
    )

    if not files:
        abort(404)

    record = files[0]

    owned = db_select(
        "koja_service_requests",
        select="id",
        filters={
            "id":
                "eq." + record["request_id"],

            "client_email":
                "eq." + session[
                    "client_email"
                ]
        },
        limit=1
    )

    if not owned:
        abort(403)

    response = storage_download(
        record["file_url"]
    )

    return send_file(
        io.BytesIO(
            response.content
        ),
        mimetype=(
            record.get("file_type")
            or
            "application/octet-stream"
        ),
        as_attachment=True,
        download_name=record[
            "file_name"
        ]
    )


# ============================================================
# COMPLETED FILE DOWNLOAD
# ============================================================

@app.route(
    "/request/<request_id>/download"
)
@client_login_required
def download_completed_file(
    request_id
):

    rows = db_select(
        "koja_service_requests",
        select="*",
        filters={
            "id":
                "eq." + request_id,

            "client_email":
                "eq." + session[
                    "client_email"
                ],

            "status":
                "eq." + STATUS_COMPLETED
        },
        limit=1
    )

    if not rows:
        abort(404)

    item = rows[0]

    if not item.get(
        "completed_file_url"
    ):
        abort(404)

    response = storage_download(
        item["completed_file_url"]
    )

    return send_file(
        io.BytesIO(
            response.content
        ),
        mimetype=(
            item.get(
                "completed_file_type"
            )
            or
            "application/octet-stream"
        ),
        as_attachment=True,
        download_name=(
            item.get(
                "completed_file_name"
            )
            or
            "KOJA-completed-document"
        )
    )


# ============================================================
# NOTIFICATIONS
# ============================================================

@app.route("/notifications")
@client_login_required
def notifications():

    data = db_select(
        "koja_notifications",
        select="*",
        filters={
            "client_email":
                "eq." + session[
                    "client_email"
                ]
        },
        order="created_at.desc",
        limit=100
    )

    try:

        db_update(
            "koja_notifications",
            {
                "client_email":
                    "eq." + session[
                        "client_email"
                    ],

                "is_read":
                    "eq.false"
            },
            {
                "is_read":
                    True,

                "read_at":
                    now_iso()
            },
            returning=False
        )

    except Exception:

        logging.exception(
            "Notification update failed"
        )

    body = """

<h2>Notifications</h2>

{% if data %}

<div class="card">

{% for n in data %}

<div style="
    padding:18px 0;
    border-bottom:1px solid #eee;
">

<strong>
{{ n.title }}
</strong>

<p>
{{ n.message }}
</p>

<span class="small">
{{ n.created_at or '' }}
</span>

</div>

{% endfor %}

</div>

{% else %}

<div class="card">

<p>
No notifications.
</p>

</div>

{% endif %}

"""

    return page(
        "Notifications",
        body,
        data=data
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

        username = clean(
            request.form.get(
                "username"
            ),
            100
        )

        password = request.form.get(
            "password",
            ""
        )

        if (
            username == ADMIN_USERNAME
            and ADMIN_PASSWORD
            and secrets.compare_digest(
                password,
                ADMIN_PASSWORD
            )
        ):

            session.clear()

            session[
                "admin_logged_in"
            ] = True

            session[
                "admin_username"
            ] = username

            return redirect(
                url_for(
                    "admin_dashboard"
                )
            )

        flash(
            "Invalid administrator credentials."
        )

    body = """

<div class="form-card">

<h2>
KOJA AFRICA Administrator
</h2>

<form method="POST">

<label>
Username
</label>

<input
    name="username"
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

<br><br>

<button
    class="btn"
    type="submit"
>
Administrator Login
</button>

</form>

</div>

"""

    return page(
        "Administrator",
        body
    )


# ============================================================
# ADMIN LOGOUT
# ============================================================

@app.route("/admin/logout")
def admin_logout():

    session.clear()

    return redirect(
        url_for("admin_login")
    )


# ============================================================
# ADMIN DASHBOARD
# ============================================================

@app.route("/admin")
@admin_required
def admin_dashboard():

    requests_data = db_select(
        "koja_service_requests",
        select="*",
        order="created_at.desc",
        limit=500
    )

    new_count = sum(
        1
        for r in requests_data
        if r.get("status")
        == STATUS_NEW
    )

    processing_count = sum(
        1
        for r in requests_data
        if r.get("status")
        == STATUS_PROCESSING
    )

    completed_count = sum(
        1
        for r in requests_data
        if r.get("status")
        == STATUS_COMPLETED
    )

    body = """

<h1>
KOJA AFRICA Admin Dashboard
</h1>

<p class="small">

Manage client requests, download submitted
work, process requests, send messages and
upload completed documents.

</p>


<div class="card-grid">

<div class="card">
<h3>New</h3>
<h2>{{ new_count }}</h2>
</div>

<div class="card">
<h3>Processing</h3>
<h2>{{ processing_count }}</h2>
</div>

<div class="card">
<h3>Completed</h3>
<h2>{{ completed_count }}</h2>
</div>

<div class="card">
<h3>Total</h3>
<h2>{{ requests_data|length }}</h2>
</div>

</div>


<br>

<div class="card">

<h2>Client Requests</h2>

{% for r in requests_data %}

<div style="
    padding:18px 0;
    border-bottom:1px solid #eee;
">

<strong>
{{ r.request_number }}
</strong>

<p>
{{ r.client_name }}
<br>
{{ r.client_email }}
<br>
{{ r.client_phone }}
</p>

<p>
<strong>
{{ r.service_type }}
</strong>
</p>

<p>
{{ r.status }}
</p>

<p class="small">
{{ r.created_at[:10]
   if r.created_at else '' }}
</p>

<a
    class="btn"
    href="{{ url_for(
        'admin_request',
        request_id=r.id
    ) }}"
>
Open
</a>

</div>

{% endfor %}

</div>

<p>

<a
    class="btn btn-warning"
    href="{{ url_for('admin_logout') }}"
>
Administrator Logout
</a>

</p>

"""

    return page(
        "Admin Dashboard",
        body,
        requests_data=requests_data,
        new_count=new_count,
        processing_count=processing_count,
        completed_count=completed_count
    )


# ============================================================
# ADMIN REQUEST
# ============================================================

@app.route(
    "/admin/request/<request_id>",
    methods=["GET", "POST"]
)
@admin_required
def admin_request(request_id):

    rows = db_select(
        "koja_service_requests",
        select="*",
        filters={
            "id":
                "eq." + request_id
        },
        limit=1
    )

    if not rows:
        abort(404)

    item = rows[0]

    files = db_select(
        "koja_request_files",
        select="*",
        filters={
            "request_id":
                "eq." + request_id
        },
        order="created_at.asc"
    )

    if request.method == "POST":

        action = request.form.get(
            "action",
            ""
        )

        message = clean(
            request.form.get(
                "admin_message"
            ),
            10000
        )

        # ====================================================
        # PROCESSING
        # ====================================================

        if action == "processing":

            old_status = item["status"]

            db_update(
                "koja_service_requests",
                {
                    "id":
                        "eq." + request_id
                },
                {
                    "status":
                        STATUS_PROCESSING,

                    "admin_message":
                        message,

                    "updated_at":
                        now_iso()
                },
                returning=False
            )

            db_insert(
                "koja_request_history",
                {
                    "request_id":
                        request_id,

                    "old_status":
                        old_status,

                    "new_status":
                        STATUS_PROCESSING,

                    "message":
                        (
                            message
                            or
                            "KOJA has started "
                            "working on the request."
                        ),

                    "changed_by":
                        session.get(
                            "admin_username",
                            "admin"
                        ),

                    "created_at":
                        now_iso()
                },
                returning=False
            )

            db_insert(
                "koja_notifications",
                {
                    "client_email":
                        item["client_email"],

                    "request_id":
                        request_id,

                    "title":
                        "KOJA Is Working on Your Request",

                    "message":
                        (
                            "KOJA is now working "
                            "on your request "
                            + item["request_number"]
                            + ". You will be "
                            "notified when it is ready."
                        ),

                    "is_read":
                        False,

                    "created_at":
                        now_iso()
                },
                returning=False
            )

            flash(
                "Request marked as Processing."
            )

            return redirect(
                url_for(
                    "admin_request",
                    request_id=request_id
                )
            )

        # ====================================================
        # MESSAGE
        # ====================================================

        if action == "message":

            if not message:

                flash(
                    "Enter a message first."
                )

                return redirect(
                    url_for(
                        "admin_request",
                        request_id=request_id
                    )
                )

            db_update(
                "koja_service_requests",
                {
                    "id":
                        "eq." + request_id
                },
                {
                    "admin_message":
                        message,

                    "updated_at":
                        now_iso()
                },
                returning=False
            )

            db_insert(
                "koja_notifications",
                {
                    "client_email":
                        item["client_email"],

                    "request_id":
                        request_id,

                    "title":
                        "Message from KOJA",

                    "message":
                        message,

                    "is_read":
                        False,

                    "created_at":
                        now_iso()
                },
                returning=False
            )

            flash(
                "Message sent to client."
            )

            return redirect(
                url_for(
                    "admin_request",
                    request_id=request_id
                )
            )

        # ====================================================
        # COMPLETE
        # ====================================================

        if action == "complete":

            completed_file = request.files.get(
                "completed_file"
            )

            if (
                not completed_file
                or
                not completed_file.filename
            ):

                flash(
                    "Please upload the completed document."
                )

                return redirect(
                    url_for(
                        "admin_request",
                        request_id=request_id
                    )
                )

            if not allowed_file(
                completed_file.filename
            ):

                flash(
                    "Unsupported completed file type."
                )

                return redirect(
                    url_for(
                        "admin_request",
                        request_id=request_id
                    )
                )

            try:

                upload = storage_upload(
                    completed_file,
                    folder=(
                        "completed/"
                        + str(request_id)
                    )
                )

                old_status = item["status"]

                db_update(
                    "koja_service_requests",
                    {
                        "id":
                            "eq." + request_id
                    },
                    {
                        "status":
                            STATUS_COMPLETED,

                        "admin_message":
                            message,

                        "completed_file_url":
                            upload["path"],

                        "completed_file_name":
                            upload["file_name"],

                        "completed_file_type":
                            upload["content_type"],

                        "completed_at":
                            now_iso(),

                        "updated_at":
                            now_iso()
                    },
                    returning=False
                )

                db_insert(
                    "koja_request_history",
                    {
                        "request_id":
                            request_id,

                        "old_status":
                            old_status,

                        "new_status":
                            STATUS_COMPLETED,

                        "message":
                            (
                                message
                                or
                                "KOJA completed the request."
                            ),

                        "changed_by":
                            session.get(
                                "admin_username",
                                "admin"
                            ),

                        "created_at":
                            now_iso()
                    },
                    returning=False
                )

                db_insert(
                    "koja_notifications",
                    {
                        "client_email":
                            item["client_email"],

                        "request_id":
                            request_id,

                        "title":
                            "Your KOJA Request Is Ready",

                        "message":
                            (
                                "Your KOJA request "
                                + item["request_number"]
                                + " is complete. "
                                "Your finished document "
                                "is now available in your account."
                            ),

                        "is_read":
                            False,

                        "created_at":
                            now_iso()
                    },
                    returning=False
                )

                flash(
                    "Request completed successfully."
                )

                return redirect(
                    url_for(
                        "admin_request",
                        request_id=request_id
                    )
                )

            except Exception as exc:

                logging.exception(
                    "Completion failed"
                )

                flash(
                    "Could not complete request: "
                    + str(exc)[:400]
                )

                return redirect(
                    url_for(
                        "admin_request",
                        request_id=request_id
                    )
                )

    body = """

<div class="card">

<h2>
{{ item.request_number }}
</h2>

<p>
<strong>
{{ item.status }}
</strong>
</p>


<h3>
Client Information
</h3>

<p>
<strong>Name:</strong>
{{ item.client_name }}
</p>

<p>
<strong>Email:</strong>
{{ item.client_email }}
</p>

<p>
<strong>Phone:</strong>
{{ item.client_phone }}
</p>


<h3>
Service
</h3>

<p>
<strong>
{{ item.service_type }}
</strong>
</p>

<p>
{{ item.description }}
</p>


{% if item.service_type ==
      'University Applications' %}

<h3>
University Information
</h3>

<p>
<strong>University:</strong>
{{ item.university or 'Not provided' }}
</p>

<p>
<strong>Mode:</strong>
{{ item.mode_of_study or 'Not provided' }}
</p>

<p>
<strong>School:</strong>
{{ item.school or 'Not provided' }}
</p>

<p>
<strong>Programme:</strong>
{{ item.programme or 'Not provided' }}
</p>

<p>
<strong>Academic Level:</strong>
{{ item.academic_level or 'Not provided' }}
</p>

<p>
<strong>Year:</strong>
{{ item.year_of_study or 'Not provided' }}
</p>

<p>
<strong>Student Number:</strong>
{{ item.student_number or 'Not provided' }}
</p>

{% endif %}


<h3>
Supporting Documents
</h3>

{% for f in files %}

<p>

<strong>
{{ f.file_name }}
</strong>

<br>

<a
    class="btn"
    href="{{ url_for(
        'admin_download_file',
        file_id=f.id
    ) }}"
>
Download Supporting Document
</a>

</p>

{% else %}

<p>
No supporting files.
</p>

{% endfor %}

</div>


<div class="card">

<h3>
Move to Processing
</h3>

<form
    method="POST"
>

<input
    type="hidden"
    name="action"
    value="processing"
>

<label>
Message to Client
</label>

<textarea
    name="admin_message"
    placeholder="Optional message..."
></textarea>

<br><br>

<button
    class="btn btn-warning"
    type="submit"
>
Mark Processing
</button>

</form>

</div>


<div class="card">

<h3>
Send Message
</h3>

<form
    method="POST"
>

<input
    type="hidden"
    name="action"
    value="message"
>

<label>
Message
</label>

<textarea
    name="admin_message"
    required
></textarea>

<br><br>

<button
    class="btn"
    type="submit"
>
Send Message
</button>

</form>

</div>


<div class="card">

<h3>
Complete Request
</h3>

<p class="small">
Upload the finished document that the
client should receive.
</p>

<form
    method="POST"
    enctype="multipart/form-data"
>

<input
    type="hidden"
    name="action"
    value="complete"
>

<label>
Finished Document *
</label>

<input
    type="file"
    name="completed_file"
    required
>

<label>
Completion Message
</label>

<textarea
    name="admin_message"
    placeholder="Tell the client what has been completed..."
></textarea>

<br><br>

<button
    class="btn btn-success"
    type="submit"
>
Upload & Mark Completed
</button>

</form>

</div>


{% if item.status == 'Completed'
      and item.completed_file_url %}

<div class="card">

<h3>
Current Completed File
</h3>

<p>
{{ item.completed_file_name }}
</p>

<a
    class="btn btn-success"
    href="{{ url_for(
        'admin_download_completed',
        request_id=item.id
    ) }}"
>
Download Completed File
</a>

</div>

{% endif %}


<p>

<a
    class="btn"
    href="{{ url_for(
        'admin_history',
        request_id=item.id
    ) }}"
>
View Full Request History
</a>

</p>

"""

    return page(
        "Admin Request",
        body,
        item=item,
        files=files
    )


# ============================================================
# ADMIN SUPPORTING DOWNLOAD
# ============================================================

@app.route(
    "/admin/file/<file_id>"
)
@admin_required
def admin_download_file(file_id):

    files = db_select(
        "koja_request_files",
        select="*",
        filters={
            "id":
                "eq." + file_id
        },
        limit=1
    )

    if not files:
        abort(404)

    record = files[0]

    response = storage_download(
        record["file_url"]
    )

    return send_file(
        io.BytesIO(
            response.content
        ),
        mimetype=(
            record.get("file_type")
            or
            "application/octet-stream"
        ),
        as_attachment=True,
        download_name=record[
            "file_name"
        ]
    )


# ============================================================
# ADMIN COMPLETED DOWNLOAD
# ============================================================

@app.route(
    "/admin/request/<request_id>/completed"
)
@admin_required
def admin_download_completed(
    request_id
):

    rows = db_select(
        "koja_service_requests",
        select="*",
        filters={
            "id":
                "eq." + request_id
        },
        limit=1
    )

    if not rows:
        abort(404)

    item = rows[0]

    if not item.get(
        "completed_file_url"
    ):
        abort(404)

    response = storage_download(
        item["completed_file_url"]
    )

    return send_file(
        io.BytesIO(
            response.content
        ),
        mimetype=(
            item.get(
                "completed_file_type"
            )
            or
            "application/octet-stream"
        ),
        as_attachment=True,
        download_name=(
            item.get(
                "completed_file_name"
            )
            or
            "completed-document"
        )
    )


# ============================================================
# ADMIN HISTORY
# ============================================================

@app.route(
    "/admin/request/<request_id>/history"
)
@admin_required
def admin_history(request_id):

    history = db_select(
        "koja_request_history",
        select="*",
        filters={
            "request_id":
                "eq." + request_id
        },
        order="created_at.desc"
    )

    body = """

<div class="card">

<h2>
Request History
</h2>

{% if history %}

{% for h in history %}

<div style="
    padding:15px 0;
    border-bottom:1px solid #eee;
">

<strong>
{{ h.new_status }}
</strong>

<p>
{{ h.message or '' }}
</p>

<p class="small">
By:
{{ h.changed_by or 'System' }}

<br>

{{ h.created_at or '' }}
</p>

</div>

{% endfor %}

{% else %}

<p>
No history found.
</p>

{% endif %}

</div>

"""

    return page(
        "Request History",
        body,
        history=history
    )


# ============================================================
# HEALTH
# ============================================================

@app.route("/health")
def health():

    return {
        "status": "ok",
        "app": APP_NAME,
        "supabase_configured":
            configuration_ok(),
        "time": now_iso()
    }


@app.route("/health/database")
def database_health():

    try:

        services = db_select(
            "koja_services",
            select="id,name",
            limit=1
        )

        universities = db_select(
            "koja_universities",
            select="id,name",
            limit=1
        )

        return {
            "status": "ok",
            "database": "connected",

            "services_table": True,

            "universities_table": True,

            "sample_services":
                len(services or []),

            "sample_universities":
                len(universities or [])
        }

    except Exception as exc:

        return {
            "status": "error",
            "database": "failed",
            "error":
                str(exc)[:700]
        }, 500


# ============================================================
# ERROR HANDLERS
# ============================================================

@app.errorhandler(413)
def file_too_large(error):

    flash(
        "File is too large. "
        "Maximum allowed size is 25 MB."
    )

    if session.get(
        "admin_logged_in"
    ):

        return redirect(
            url_for(
                "admin_dashboard"
            )
        )

    if session.get("client_id"):

        return redirect(
            url_for("services")
        )

    return redirect(
        url_for("home")
    )


@app.errorhandler(404)
def not_found(error):

    body = """

<div class="card">

<h1>
404
</h1>

<p>
The requested page or document
was not found.
</p>

<a
    class="btn"
    href="{{ url_for('home') }}"
>
Return Home
</a>

</div>

"""

    return page(
        "Not Found",
        body
    ), 404


@app.errorhandler(500)
def server_error(error):

    logging.exception(
        "Internal server error"
    )

    body = """

<div class="card">

<h1>
Something went wrong
</h1>

<p>
KOJA AFRICA encountered an internal
error. Please try again.
</p>

<a
    class="btn"
    href="{{ url_for('home') }}"
>
Return Home
</a>

</div>

"""

    return page(
        "Server Error",
        body
    ), 500


# ============================================================
# START APPLICATION
# ============================================================

if __name__ == "__main__":

    port = int(
        os.getenv(
            "PORT",
            "10000"
        )
    )

    host = os.getenv(
        "HOST",
        "0.0.0.0"
    )

    logging.info(
        "Starting %s on %s:%s",
        APP_NAME,
        host,
        port
    )

    app.run(
        host=host,
        port=port,
        debug=False
    ) 
