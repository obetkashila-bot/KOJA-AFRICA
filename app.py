import os
import secrets
import logging
from datetime import timedelta
from functools import wraps

import requests
from dotenv import load_dotenv
from flask import (
    Flask,
    request,
    redirect,
    url_for,
    session,
    flash,
    jsonify,
    get_flashed_messages,
)

# ============================================================
# KOJA AFRICA
# Complete Fresh Flask Foundation
#
# Stack:
#   Flask
#   Supabase Auth
#   Supabase REST API
#   Render
#
# No SQLite
# No psycopg
# No psycopg2
# ============================================================

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("koja-africa")

app = Flask(__name__)

# ============================================================
# APPLICATION CONFIGURATION
# ============================================================

app.secret_key = (
    os.getenv("SECRET_KEY")
    or secrets.token_hex(32)
)

app.permanent_session_lifetime = timedelta(days=7)

app.config["MAX_CONTENT_LENGTH"] = 15 * 1024 * 1024

APP_NAME = "KOJA AFRICA"
APP_TAGLINE = "Knowledge • Questions • Answers"


# ============================================================
# SUPABASE CONFIGURATION
# ============================================================

SUPABASE_URL = os.getenv(
    "SUPABASE_URL",
    ""
).rstrip("/")

SUPABASE_ANON_KEY = os.getenv(
    "SUPABASE_ANON_KEY",
    ""
).strip()

SUPABASE_SERVICE_KEY = os.getenv(
    "SUPABASE_SERVICE_KEY",
    ""
).strip()


# ============================================================
# SUPABASE HELPERS
# ============================================================

def supabase_configured():
    """
    Check whether the minimum Supabase configuration exists.
    """

    return bool(
        SUPABASE_URL
        and (
            SUPABASE_ANON_KEY
            or SUPABASE_SERVICE_KEY
        )
    )


def public_key():
    """
    Key used for Supabase Auth.

    Prefer the anon key.
    """

    return (
        SUPABASE_ANON_KEY
        or SUPABASE_SERVICE_KEY
    )


def auth_headers(access_token=None):
    """
    Headers for Supabase Auth requests.
    """

    key = public_key()

    headers = {
        "apikey": key,
        "Content-Type": "application/json",
    }

    if access_token:

        headers["Authorization"] = (
            f"Bearer {access_token}"
        )

    else:

        headers["Authorization"] = (
            f"Bearer {key}"
        )

    return headers


def rest_headers(access_token=None):
    """
    Headers for Supabase REST requests.

    Service key is preferred for server-side
    database operations.
    """

    key = (
        SUPABASE_SERVICE_KEY
        or SUPABASE_ANON_KEY
    )

    headers = {
        "apikey": key,
        "Content-Type": "application/json",
    }

    if access_token:

        headers["Authorization"] = (
            f"Bearer {access_token}"
        )

    else:

        headers["Authorization"] = (
            f"Bearer {key}"
        )

    return headers


def auth_url(path):
    return (
        f"{SUPABASE_URL}/auth/v1/"
        f"{path.lstrip('/')}"
    )


def rest_url(table):
    return (
        f"{SUPABASE_URL}/rest/v1/"
        f"{table}"
    )


def supabase_error(response):

    try:
        data = response.json()
    except Exception:
        data = {}

    if isinstance(data, dict):

        return (
            data.get("msg")
            or data.get("message")
            or data.get("error_description")
            or data.get("error")
            or f"Supabase error {response.status_code}"
        )

    return (
        f"Supabase error {response.status_code}"
    )


# ============================================================
# SESSION / AUTHENTICATION
# ============================================================

def current_user():
    return session.get("user")


def current_access_token():
    return session.get("access_token")


def login_required(function):

    @wraps(function)
    def wrapper(*args, **kwargs):

        if not current_user():

            flash(
                "Please log in first.",
                "error"
            )

            return redirect(
                url_for("login")
            )

        return function(*args, **kwargs)

    return wrapper


# ============================================================
# SUPABASE AUTH
# ============================================================

def signup_user(
    email,
    password,
    full_name
):

    return requests.post(

        auth_url("signup"),

        headers=auth_headers(),

        json={
            "email": email,
            "password": password,
            "data": {
                "full_name": full_name
            },
        },

        timeout=20,
    )


def login_user(
    email,
    password
):

    return requests.post(

        auth_url(
            "token?grant_type=password"
        ),

        headers=auth_headers(),

        json={
            "email": email,
            "password": password,
        },

        timeout=20,
    )


def logout_user(
    access_token
):

    try:

        requests.post(

            auth_url("logout"),

            headers=auth_headers(
                access_token
            ),

            timeout=10,
        )

    except requests.RequestException:

        logger.exception(
            "Supabase logout request failed"
        )


# ============================================================
# BASIC SUPABASE REST FUNCTIONS
# ============================================================

def supabase_select(
    table,
    params=None,
    access_token=None
):

    if not supabase_configured():
        return None, "Supabase is not configured."

    try:

        response = requests.get(

            rest_url(table),

            headers=rest_headers(
                access_token
            ),

            params=params or {},

            timeout=20,
        )

        if response.status_code >= 400:

            return None, supabase_error(
                response
            )

        try:

            return response.json(), None

        except Exception:

            return [], None

    except requests.RequestException as exc:

        logger.exception(
            "Supabase SELECT failed"
        )

        return None, str(exc)


def supabase_insert(
    table,
    payload,
    access_token=None
):

    if not supabase_configured():
        return None, "Supabase is not configured."

    try:

        headers = rest_headers(
            access_token
        )

        headers["Prefer"] = (
            "return=representation"
        )

        response = requests.post(

            rest_url(table),

            headers=headers,

            json=payload,

            timeout=20,
        )

        if response.status_code >= 400:

            return None, supabase_error(
                response
            )

        try:

            return response.json(), None

        except Exception:

            return [], None

    except requests.RequestException as exc:

        logger.exception(
            "Supabase INSERT failed"
        )

        return None, str(exc)


def supabase_update(
    table,
    params,
    payload,
    access_token=None
):

    if not supabase_configured():
        return None, "Supabase is not configured."

    try:

        headers = rest_headers(
            access_token
        )

        headers["Prefer"] = (
            "return=representation"
        )

        response = requests.patch(

            rest_url(table),

            headers=headers,

            params=params,

            json=payload,

            timeout=20,
        )

        if response.status_code >= 400:

            return None, supabase_error(
                response
            )

        try:

            return response.json(), None

        except Exception:

            return [], None

    except requests.RequestException as exc:

        logger.exception(
            "Supabase UPDATE failed"
        )

        return None, str(exc)


def supabase_delete(
    table,
    params,
    access_token=None
):

    if not supabase_configured():
        return None, "Supabase is not configured."

    try:

        response = requests.delete(

            rest_url(table),

            headers=rest_headers(
                access_token
            ),

            params=params,

            timeout=20,
        )

        if response.status_code >= 400:

            return None, supabase_error(
                response
            )

        return True, None

    except requests.RequestException as exc:

        logger.exception(
            "Supabase DELETE failed"
        )

        return None, str(exc)


# ============================================================
# KOJA SERVICES
# ============================================================

KOJA_SERVICES = [

    {
        "id": "assignments",
        "name": "Assignments",
        "description": (
            "Submit assignments and "
            "academic questions."
        ),
        "icon": "📚",
    },

    {
        "id": "farmer",
        "name": "Farmer Services",
        "description": (
            "Register farmers and "
            "access agricultural services."
        ),
        "icon": "🌾",
    },

    {
        "id": "driver",
        "name": "Driver & Delivery",
        "description": (
            "Find nearby drivers and "
            "request deliveries."
        ),
        "icon": "🚚",
    },

    {
        "id": "university",
        "name": "University Services",
        "description": (
            "University and college "
            "academic services."
        ),
        "icon": "🎓",
    },

    {
        "id": "cv",
        "name": "CV & Jobs",
        "description": (
            "Create CVs and manage "
            "job applications."
        ),
        "icon": "💼",
    },

    {
        "id": "tpin",
        "name": "TPIN Services",
        "description": (
            "Access TPIN-related "
            "services."
        ),
        "icon": "🧾",
    },

]


# ============================================================
# CSS
# ============================================================

CSS = """

* {
    box-sizing: border-box;
}

html {
    scroll-behavior: smooth;
}

body {

    margin: 0;

    background: #f5f7fa;

    color: #172033;

    font-family:
        Arial,
        Helvetica,
        sans-serif;

}

.nav {

    background:
        linear-gradient(
            135deg,
            #14532d,
            #166534
        );

    color: white;

}

.nav-inner {

    width:
        min(
            1100px,
            calc(100% - 28px)
        );

    margin: auto;

    padding:
        14px 0;

    display: flex;

    align-items: center;

    justify-content:
        space-between;

    gap: 15px;

}

.logo {

    color: white;

    text-decoration: none;

    font-size: 21px;

    font-weight: 800;

    letter-spacing: .4px;

}

.navlinks {

    display: flex;

    flex-wrap: wrap;

    gap: 5px;

}

.navlinks a {

    color: white;

    text-decoration: none;

    padding:
        8px 10px;

    border-radius: 8px;

}

.navlinks a:hover {

    background:
        rgba(
            255,
            255,
            255,
            .12
        );

}

.container {

    width:
        min(
            1100px,
            calc(100% - 28px)
        );

    margin:
        25px auto 50px;

}

.hero {

    background:
        linear-gradient(
            135deg,
            #14532d,
            #166534
        );

    color: white;

    padding: 32px 25px;

    border-radius: 18px;

    box-shadow:
        0 8px 25px
        rgba(
            16,
            24,
            40,
            .10
        );

}

.hero h1 {

    margin-top: 0;

    font-size: 38px;

}

.hero p {

    line-height: 1.6;

}

.card {

    background: white;

    border:
        1px solid
        #e4e7ec;

    border-radius: 16px;

    padding: 24px;

    box-shadow:
        0 4px 18px
        rgba(
            16,
            24,
            40,
            .04
        );

}

.grid {

    display: grid;

    grid-template-columns:
        repeat(
            3,
            1fr
        );

    gap: 16px;

}

.service {

    background: white;

    border:
        1px solid
        #e4e7ec;

    border-radius: 14px;

    padding: 20px;

    box-shadow:
        0 4px 15px
        rgba(
            16,
            24,
            40,
            .03
        );

}

.service h2 {

    margin-top: 0;

}

.form {

    max-width: 560px;

    margin: auto;

}

label {

    display: block;

    margin:
        14px 0 6px;

    font-weight: 700;

}

input,
textarea,
select {

    width: 100%;

    padding: 12px;

    border:
        1px solid
        #d0d5dd;

    border-radius: 9px;

    font: inherit;

    background: white;

}

input:focus,
textarea:focus,
select:focus {

    outline:
        2px solid
        #86efac;

    border-color:
        #16a34a;

}

textarea {

    min-height: 120px;

    resize: vertical;

}

.btn {

    display: inline-block;

    border: 0;

    background: #14532d;

    color: white;

    padding:
        11px 17px;

    border-radius: 9px;

    text-decoration: none;

    cursor: pointer;

    font-weight: 700;

}

.btn:hover {

    background: #166534;

}

.btn.light {

    background: white;

    color: #14532d;

}

.btn.light:hover {

    background: #f0fdf4;

}

.actions {

    display: flex;

    flex-wrap: wrap;

    gap: 10px;

    margin-top: 20px;

}

.alert {

    padding:
        12px 14px;

    border-radius: 9px;

    margin-bottom: 14px;

    border: 1px solid;

}

.alert.error {

    background: #fef3f2;

    color: #b42318;

    border-color: #fecdca;

}

.alert.success {

    background: #ecfdf3;

    color: #067647;

    border-color: #abefc6;

}

.muted {

    color: #667085;

}

.badge {

    display: inline-block;

    padding:
        5px 9px;

    border-radius: 20px;

    background:
        #ecfdf3;

    color:
        #067647;

    font-size: 13px;

    font-weight: 700;

}

.footer {

    text-align: center;

    color: #667085;

    padding: 25px;

}

@media (max-width: 760px) {

    .grid {

        grid-template-columns: 1fr;

    }

    .nav-inner {

        flex-direction: column;

        align-items: flex-start;

    }

    .hero h1 {

        font-size: 30px;

    }

}

"""


# ============================================================
# PAGE BUILDER
# ============================================================

def page(title, body):

    user = current_user()

    if user:

        navigation = f"""

        <a
            href="{url_for('dashboard')}"
        >
            Dashboard
        </a>

        <a
            href="{url_for('services')}"
        >
            Services
        </a>

        <a
            href="{url_for('profile')}"
        >
            Profile
        </a>

        <a
            href="{url_for('logout')}"
        >
            Logout
        </a>

        """

        home_url = url_for(
            "dashboard"
        )

    else:

        navigation = f"""

        <a href="{url_for('home')}">
            Home
        </a>

        <a href="{url_for('login')}">
            Login
        </a>

        <a href="{url_for('register')}">
            Create Account
        </a>

        """

        home_url = url_for(
            "home"
        )

    flashes = ""

    for category, message in (
        get_flashed_messages(
            with_categories=True
        )
    ):

        flashes += f"""

        <div class="alert {category}">
            {message}
        </div>

        """

    return f"""

<!DOCTYPE html>

<html lang="en">

<head>

<meta charset="UTF-8">

<meta
    name="viewport"
    content="width=device-width,
             initial-scale=1.0"
>

<title>
{title} | {APP_NAME}
</title>

{CSS}

</head>

<body>

<nav class="nav">

<div class="nav-inner">

<a
    class="logo"
    href="{home_url}"
>
{APP_NAME}
</a>

<div class="navlinks">

{navigation}

</div>

</div>

</nav>

<main class="container">

{flashes}

{body}

</main>

<footer class="footer">

<strong>
{APP_NAME}
</strong>

<br>

{APP_TAGLINE}

</footer>

</body>

</html>

"""


# ============================================================
# HOME
# ============================================================

@app.route("/")
def home():

    return page(

        "Home",

        """

<section class="hero">

<h1>
KOJA AFRICA
</h1>

<p>
Knowledge • Questions • Answers
</p>

<p>
A single platform for academic
support, service requests,
farmer services and delivery.
</p>

<div class="actions">

<a
    class="btn light"
    href="/register"
>
Create Account
</a>

<a
    class="btn light"
    href="/login"
>
Login
</a>

</div>

</section>

<br>

<section class="grid">

<div class="service">

<h2>📚</h2>

<h3>
Assignments
</h3>

<p class="muted">
Submit assignments and
academic questions.
</p>

</div>


<div class="service">

<h2>🌾</h2>

<h3>
Farmer Services
</h3>

<p class="muted">
Access farmer registration
and agricultural services.
</p>

</div>


<div class="service">

<h2>🚚</h2>

<h3>
Delivery
</h3>

<p class="muted">
Connect customers with
nearby drivers.
</p>

</div>

</section>

"""

    )


# ============================================================
# HEALTH CHECK
# ============================================================

@app.route("/health")
def health():

    return jsonify({

        "status": "ok",

        "application":
            APP_NAME,

        "version":
            "fresh-foundation",

        "supabase_configured":
            supabase_configured(),

    })


# ============================================================
# REGISTER
# ============================================================

@app.route(
    "/register",
    methods=["GET", "POST"]
)
def register():

    if current_user():

        return redirect(
            url_for("dashboard")
        )

    if request.method == "POST":

        full_name = request.form.get(
            "full_name",
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

        confirm_password = (
            request.form.get(
                "confirm_password",
                ""
            )
        )

        if not full_name:

            flash(
                "Full name is required.",
                "error"
            )

        elif not email:

            flash(
                "Email is required.",
                "error"
            )

        elif not password:

            flash(
                "Password is required.",
                "error"
            )

        elif password != confirm_password:

            flash(
                "Passwords do not match.",
                "error"
            )

        elif len(password) < 6:

            flash(
                "Password must be at least 6 characters.",
                "error"
            )

        elif not supabase_configured():

            flash(
                "Supabase is not configured on Render.",
                "error"
            )

        else:

            try:

                response = signup_user(

                    email,

                    password,

                    full_name

                )

                if response.status_code not in (
                    200,
                    201
                ):

                    flash(
                        supabase_error(
                            response
                        ),
                        "error"
                    )

                else:

                    data = response.json()

                    user = (
                        data.get("user")
                        or {}
                    )

                    access_token = (
                        data.get(
                            "access_token"
                        )
                    )

                    refresh_token = (
                        data.get(
                            "refresh_token"
                        )
                    )

                    if access_token:

                        session.permanent = True

                        session[
                            "access_token"
                        ] = access_token

                        session[
                            "refresh_token"
                        ] = refresh_token

                        session["user"] = {

                            "id":
                                user.get(
                                    "id"
                                ),

                            "email":
                                user.get(
                                    "email",
                                    email
                                ),

                            "full_name":
                                full_name,

                        }

                        flash(
                            "Account created successfully.",
                            "success"
                        )

                        return redirect(
                            url_for(
                                "dashboard"
                            )
                        )

                    flash(
                        "Account created. Check your email for confirmation, then log in.",
                        "success"
                    )

                    return redirect(
                        url_for("login")
                    )

            except requests.RequestException:

                logger.exception(
                    "Registration failed"
                )

                flash(
                    "Could not connect to Supabase.",
                    "error"
                )

    return page(

        "Create Account",

        """

<section class="card form">

<h1>
Create KOJA Account
</h1>

<p class="muted">
Create an account using your
email and password.
</p>

<form method="POST">

<label>
Full name
</label>

<input
    type="text"
    name="full_name"
    required
    autocomplete="name"
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
    minlength="6"
    autocomplete="new-password"
>

<label>
Confirm password
</label>

<input
    type="password"
    name="confirm_password"
    required
    minlength="6"
    autocomplete="new-password"
>

<br><br>

<button
    class="btn"
    type="submit"
>
Create Account
</button>

</form>

<p class="muted">

Already have an account?

<a href="/login">
Login
</a>

</p>

</section>

"""

    )


# ============================================================
# LOGIN
# ============================================================

@app.route(
    "/login",
    methods=["GET", "POST"]
)
def login():

    if current_user():

        return redirect(
            url_for("dashboard")
        )

    if request.method == "POST":

        email = request.form.get(
            "email",
            ""
        ).strip().lower()

        password = request.form.get(
            "password",
            ""
        )

        if not email or not password:

            flash(
                "Email and password are required.",
                "error"
            )

        elif not supabase_configured():

            flash(
                "Supabase is not configured on Render.",
                "error"
            )

        else:

            try:

                response = login_user(

                    email,

                    password

                )

                if response.status_code != 200:

                    flash(
                        supabase_error(
                            response
                        ),
                        "error"
                    )

                else:

                    data = response.json()

                    user = (
                        data.get("user")
                        or {}
                    )

                    metadata = (
                        user.get(
                            "user_metadata"
                        )
                        or {}
                    )

                    session.permanent = True

                    session[
                        "access_token"
                    ] = data.get(
                        "access_token"
                    )

                    session[
                        "refresh_token"
                    ] = data.get(
                        "refresh_token"
                    )

                    session["user"] = {

                        "id":
                            user.get(
                                "id"
                            ),

                        "email":
                            user.get(
                                "email",
                                email
                            ),

                        "full_name":
                            metadata.get(
                                "full_name"
                            )
                            or user.get(
                                "email",
                                email
                            ),

                    }

                    flash(
                        "Login successful.",
                        "success"
                    )

                    return redirect(
                        url_for(
                            "dashboard"
                        )
                    )

            except requests.RequestException:

                logger.exception(
                    "Login request failed"
                )

                flash(
                    "Could not connect to Supabase.",
                    "error"
                )

    return page(

        "Login",

        """

<section class="card form">

<h1>
KOJA Login
</h1>

<p class="muted">
Login with your email
and password.
</p>

<form method="POST">

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

<br><br>

<button
    class="btn"
    type="submit"
>
Login
</button>

</form>

<p class="muted">

Don't have an account?

<a href="/register">
Create Account
</a>

</p>

</section>

"""

    )


# ============================================================
# LOGOUT
# ============================================================

@app.route("/logout")
def logout():

    access_token = (
        current_access_token()
    )

    if access_token:

        logout_user(
            access_token
        )

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

    user = current_user()

    name = (
        user.get("full_name")
        or user.get("email")
        or "User"
    )

    return page(

        "Dashboard",

        f"""

<section class="hero">

<h1>
Welcome, {name}
</h1>

<p>
KOJA AFRICA is ready.
</p>

<span class="badge">
Account Active
</span>

</section>

<br>

<section class="grid">

<div class="service">

<h2>
📚 Assignments
</h2>

<p class="muted">
Submit assignments and
academic questions.
</p>

<a
    class="btn"
    href="/service/assignments"
>
Open
</a>

</div>


<div class="service">

<h2>
🌾 Farmer
</h2>

<p class="muted">
Farmer registration and
agricultural services.
</p>

<a
    class="btn"
    href="/service/farmer"
>
Open
</a>

</div>


<div class="service">

<h2>
🚚 Delivery
</h2>

<p class="muted">
Nearby drivers and
delivery requests.
</p>

<a
    class="btn"
    href="/service/driver"
>
Open
</a>

</div>

</section>

"""

    )


# ============================================================
# SERVICES
# ============================================================

@app.route("/services")
@login_required
def services():

    cards = ""

    for item in KOJA_SERVICES:

        cards += f"""

<div class="service">

<h2>
{item["icon"]}
{item["name"]}
</h2>

<p class="muted">
{item["description"]}
</p>

<a
    class="btn"
    href="/service/{item["id"]}"
>
Open Service
</a>

</div>

"""

    return page(

        "Services",

        f"""

<section class="card">

<h1>
KOJA Services
</h1>

<p class="muted">
Select the service you need.
</p>

</section>

<br>

<section class="grid">

{cards}

</section>

"""

    )


# ============================================================
# SERVICE ROUTER
# ============================================================

@app.route(
    "/service/<service_id>"
)
@login_required
def service(service_id):

    selected = None

    for item in KOJA_SERVICES:

        if item["id"] == service_id:

            selected = item

            break

    if not selected:

        flash(
            "Service not found.",
            "error"
        )

        return redirect(
            url_for("services")
        )

    if service_id == "assignments":

        return redirect(
            url_for(
                "assignments_home"
            )
        )

    if service_id == "farmer":

        return redirect(
            url_for(
                "farmer_home"
            )
        )

    if service_id == "driver":

        return redirect(
            url_for(
                "driver_home"
            )
        )

    return page(

        selected["name"],

        f"""

<section class="card">

<h1>
{selected["icon"]}
{selected["name"]}
</h1>

<p>
{selected["description"]}
</p>

<div class="alert success">

This KOJA module is ready
for database integration.

</div>

<div class="actions">

<a
    class="btn"
    href="/services"
>
Back to Services
</a>

</div>

</section>

"""

    )


# ============================================================
# ASSIGNMENTS
# ============================================================

@app.route("/assignments")
@login_required
def assignments_home():

    return page(

        "Assignments",

        """

<section class="hero">

<h1>
📚 Assignments
</h1>

<p>
Submit assignments, ask
academic questions and
receive answers.
</p>

</section>

<br>

<section class="grid">

<div class="service">

<h2>
My Assignments
</h2>

<p class="muted">
View assignments submitted
to KOJA.
</p>

</div>


<div class="service">

<h2>
Ask a Question
</h2>

<p class="muted">
Submit an academic question.
</p>

</div>


<div class="service">

<h2>
My Answers
</h2>

<p class="muted">
View answers provided
by KOJA.
</p>

</div>

</section>

<br>

<section class="card">

<h2>
Assignment Module
</h2>

<p class="muted">
The next stage will connect
this interface to the existing
Supabase assignment tables.
</p>

</section>

"""

    )


# ============================================================
# FARMER
# ============================================================

@app.route("/farmer")
@login_required
def farmer_home():

    return page(

        "Farmer Services",

        """

<section class="hero">

<h1>
🌾 Farmer Services
</h1>

<p>
KOJA agricultural and
farmer services.
</p>

</section>

<br>

<section class="card">

<h2>
Farmer Registration
</h2>

<p class="muted">
The farmer form will be
connected to your existing
Supabase farmer table using
its actual column names.
</p>

<div class="alert success">

Authentication is already
separate from the farmer
database.

</div>

</section>

"""

    )


# ============================================================
# DRIVER
# ============================================================

@app.route("/driver")
@login_required
def driver_home():

    return page(

        "Driver & Delivery",

        """

<section class="hero">

<h1>
🚚 Driver & Delivery
</h1>

<p>
Find nearby drivers and
request deliveries.
</p>

</section>

<br>

<section class="grid">

<div class="service">

<h2>
Nearby Drivers
</h2>

<p class="muted">
Online drivers sharing their
current GPS location will
appear here.
</p>

</div>


<div class="service">

<h2>
Request Delivery
</h2>

<p class="muted">
Select a nearby driver and
send a delivery request.
</p>

</div>


<div class="service">

<h2>
Track Delivery
</h2>

<p class="muted">
Track an accepted delivery
using GPS.
</p>

</div>

</section>

<br>

<section class="card">

<h2>
Driver Module
</h2>

<p class="muted">
The next stage will connect
driver registration, online
status, GPS locations,
delivery requests and tracking
to the existing Supabase
tables.
</p>

</section>

"""

    )


# ============================================================
# PROFILE
# ============================================================

@app.route("/profile")
@login_required
def profile():

    user = current_user()

    return page(

        "Profile",

        f"""

<section class="card">

<h1>
My Profile
</h1>

<p>
<strong>
Name:
</strong>

{user.get("full_name", "")}

</p>

<p>
<strong>
Email:
</strong>

{user.get("email", "")}

</p>

<p>
<strong>
User ID:
</strong>

{user.get("id", "")}

</p>

<p class="muted">
Your login is handled by
Supabase Auth.
</p>

</section>

"""

    )


# ============================================================
# API: CURRENT USER
# ============================================================

@app.route("/api/me")
@login_required
def api_me():

    user = current_user()

    return jsonify({

        "success": True,

        "user": {

            "id":
                user.get("id"),

            "email":
                user.get("email"),

            "full_name":
                user.get("full_name"),

        }

    })


# ============================================================
# API: SERVICES
# ============================================================

@app.route("/api/services")
@login_required
def api_services():

    return jsonify({

        "success": True,

        "services":
            KOJA_SERVICES,

    })


# ============================================================
# API: SUPABASE STATUS
# ============================================================

@app.route("/api/system")
def api_system():

    return jsonify({

        "success": True,

        "application":
            APP_NAME,

        "supabase_configured":
            supabase_configured(),

        "authentication":
            "supabase_auth",

        "database":
            "supabase_rest",

        "server":
            "flask",

    })


# ============================================================
# ERROR: 404
# ============================================================

@app.errorhandler(404)
def not_found(error):

    return page(

        "Page Not Found",

        """

<section class="card">

<h1>
Page Not Found
</h1>

<p class="muted">
The page you requested
does not exist.
</p>

<div class="actions">

<a
    class="btn"
    href="/"
>
Go Home
</a>

</div>

</section>

"""

    ), 404


# ============================================================
# ERROR: 413
# ============================================================

@app.errorhandler(413)
def file_too_large(error):

    return page(

        "File Too Large",

        """

<section class="card">

<h1>
File Too Large
</h1>

<p>
The maximum upload size
is 15 MB.
</p>

</section>

"""

    ), 413


# ============================================================
# ERROR: 500
# ============================================================

@app.errorhandler(500)
def internal_error(error):

    logger.exception(
        "Unhandled server error"
    )

    return page(

        "Server Error",

        """

<section class="card">

<h1>
Server Error
</h1>

<p>
The server encountered an
unexpected error.
</p>

<p class="muted">
Check the Render logs for
the exact error.
</p>

</section>

"""

    ), 500


# ============================================================
# START APPLICATION
# ============================================================

if __name__ == "__main__":

    port = int(
        os.getenv(
            "PORT",
            "5000"
        )
    )

    app.run(

        host="0.0.0.0",

        port=port,

        debug=False

    )
