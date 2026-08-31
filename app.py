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
    render_template_string,
    flash,
    jsonify,
    get_flashed_messages,
)

load_dotenv()

# ============================================================
# KOJA AFRICA
# Fresh Flask + Supabase Auth foundation
# ============================================================

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("koja-africa")

app = Flask(__name__)

app.secret_key = os.getenv("SECRET_KEY") or secrets.token_hex(32)
app.permanent_session_lifetime = timedelta(days=7)
app.config["MAX_CONTENT_LENGTH"] = 15 * 1024 * 1024

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "").strip()
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "").strip()

APP_NAME = "KOJA AFRICA"
APP_TAGLINE = "Knowledge • Questions • Answers"


# ============================================================
# SUPABASE
# ============================================================

def supabase_configured():
    return bool(
        SUPABASE_URL
        and (SUPABASE_ANON_KEY or SUPABASE_SERVICE_KEY)
    )


def public_key():
    return SUPABASE_ANON_KEY or SUPABASE_SERVICE_KEY


def auth_headers(access_token=None):
    key = public_key()

    headers = {
        "apikey": key,
        "Content-Type": "application/json",
    }

    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"
    else:
        headers["Authorization"] = f"Bearer {key}"

    return headers


def auth_url(path):
    return f"{SUPABASE_URL}/auth/v1/{path.lstrip('/')}"


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

    return f"Supabase error {response.status_code}"


# ============================================================
# SESSION
# ============================================================

def current_user():
    return session.get("user")


def login_required(function):
    @wraps(function)
    def wrapper(*args, **kwargs):
        if not current_user():
            flash("Please log in first.", "error")
            return redirect(url_for("login"))

        return function(*args, **kwargs)

    return wrapper


# ============================================================
# SUPABASE AUTH FUNCTIONS
# ============================================================

def signup_user(email, password, full_name):
    response = requests.post(
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

    return response


def login_user(email, password):
    response = requests.post(
        auth_url("token?grant_type=password"),
        headers=auth_headers(),
        json={
            "email": email,
            "password": password,
        },
        timeout=20,
    )

    return response


def logout_user(access_token):
    try:
        requests.post(
            auth_url("logout"),
            headers=auth_headers(access_token),
            timeout=10,
        )
    except requests.RequestException:
        pass


# ============================================================
# DESIGN
# ============================================================

CSS = """
<style>

* {
    box-sizing: border-box;
}

body {
    margin: 0;
    background: #f5f7fa;
    color: #172033;
    font-family: Arial, Helvetica, sans-serif;
}

.nav {
    background: #14532d;
    color: white;
}

.nav-inner {
    max-width: 1100px;
    margin: auto;
    padding: 14px 18px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 15px;
}

.logo {
    color: white;
    text-decoration: none;
    font-size: 20px;
    font-weight: 800;
}

.navlinks {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
}

.navlinks a {
    color: white;
    text-decoration: none;
    padding: 8px 10px;
    border-radius: 8px;
}

.navlinks a:hover {
    background: rgba(255,255,255,0.12);
}

.container {
    width: min(1100px, calc(100% - 28px));
    margin: 25px auto 50px;
}

.hero {
    background: linear-gradient(135deg, #14532d, #166534);
    color: white;
    padding: 30px 24px;
    border-radius: 18px;
}

.hero h1 {
    margin-top: 0;
    font-size: 38px;
}

.card {
    background: white;
    border: 1px solid #e4e7ec;
    border-radius: 16px;
    padding: 24px;
    box-shadow: 0 4px 18px rgba(16,24,40,0.04);
}

.grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 16px;
}

.service {
    background: white;
    border: 1px solid #e4e7ec;
    border-radius: 14px;
    padding: 20px;
}

.form {
    max-width: 560px;
    margin: auto;
}

label {
    display: block;
    margin: 14px 0 6px;
    font-weight: 700;
}

input,
textarea,
select {
    width: 100%;
    padding: 12px;
    border: 1px solid #d0d5dd;
    border-radius: 9px;
    font: inherit;
}

input:focus,
textarea:focus,
select:focus {
    outline: 2px solid #86efac;
    border-color: #16a34a;
}

.btn {
    display: inline-block;
    border: 0;
    background: #14532d;
    color: white;
    padding: 11px 17px;
    border-radius: 9px;
    text-decoration: none;
    cursor: pointer;
    font-weight: 700;
}

.btn.light {
    background: white;
    color: #14532d;
}

.actions {
    display: flex;
    flex-wrap: wrap;
    gap: 10px;
    margin-top: 20px;
}

.alert {
    padding: 12px 14px;
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

</style>
"""


# ============================================================
# PAGE TEMPLATE
# ============================================================

def page(title, body):

    user = current_user()

    if user:

        navigation = f"""
        <a href="{url_for('dashboard')}">Dashboard</a>
        <a href="{url_for('services')}">Services</a>
        <a href="{url_for('profile')}">Profile</a>
        <a href="{url_for('logout')}">Logout</a>
        """

        home_url = url_for("dashboard")

    else:

        navigation = f"""
        <a href="{url_for('home')}">Home</a>
        <a href="{url_for('login')}">Login</a>
        <a href="{url_for('register')}">Create Account</a>
        """

        home_url = url_for("home")

    flashes = ""

    for category, message in get_flashed_messages(
        with_categories=True
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
    content="width=device-width, initial-scale=1.0"
>

<title>{title} | {APP_NAME}</title>

{CSS}

</head>

<body>

<nav class="nav">

<div class="nav-inner">

<a class="logo" href="{home_url}">
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

<strong>{APP_NAME}</strong>

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

    body = """

<section class="hero">

<h1>KOJA AFRICA</h1>

<p>
Knowledge • Questions • Answers
</p>

<p>
A platform for academic support,
service requests and digital services.
</p>

<div class="actions">

<a class="btn light" href="/register">
Create Account
</a>

<a class="btn light" href="/login">
Login
</a>

</div>

</section>

<br>

<section class="grid">

<div class="service">

<h3>Assignments</h3>

<p class="muted">
Submit assignments and academic questions.
</p>

</div>

<div class="service">

<h3>Farmer Services</h3>

<p class="muted">
Access farmer registration services.
</p>

</div>

<div class="service">

<h3>Delivery</h3>

<p class="muted">
Connect customers with nearby drivers.
</p>

</div>

</section>

"""

    return page("Home", body)


# ============================================================
# HEALTH CHECK
# ============================================================

@app.route("/health")
def health():

    return jsonify({
        "status": "ok",
        "application": APP_NAME,
        "supabase_configured": supabase_configured(),
    })


# ============================================================
# REGISTER
# ============================================================

@app.route("/register", methods=["GET", "POST"])
def register():

    if current_user():
        return redirect(url_for("dashboard"))

    if request.method == "POST":

        full_name = request.form.get(
            "full_name", ""
        ).strip()

        email = request.form.get(
            "email", ""
        ).strip().lower()

        password = request.form.get(
            "password", ""
        )

        confirm_password = request.form.get(
            "confirm_password", ""
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

                if response.status_code not in (200, 201):

                    flash(
                        supabase_error(response),
                        "error"
                    )

                else:

                    data = response.json()

                    user = data.get("user") or {}

                    access_token = data.get(
                        "access_token"
                    )

                    refresh_token = data.get(
                        "refresh_token"
                    )

                    if access_token:

                        session.permanent = True

                        session["access_token"] = (
                            access_token
                        )

                        session["refresh_token"] = (
                            refresh_token
                        )

                        session["user"] = {
                            "id": user.get("id"),
                            "email": user.get(
                                "email",
                                email
                            ),
                            "full_name": full_name,
                        }

                        flash(
                            "Account created successfully.",
                            "success"
                        )

                        return redirect(
                            url_for("dashboard")
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
                    "Registration request failed"
                )

                flash(
                    "Could not connect to Supabase.",
                    "error"
                )

    return page(
        "Create Account",
        """

<section class="card form">

<h1>Create KOJA Account</h1>

<p class="muted">
Create an account using your email and password.
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

<button class="btn" type="submit">
Create Account
</button>

</form>

</section>

"""
    )


# ============================================================
# LOGIN
# ============================================================

@app.route("/login", methods=["GET", "POST"])
def login():

    if current_user():
        return redirect(url_for("dashboard"))

    if request.method == "POST":

        email = request.form.get(
            "email", ""
        ).strip().lower()

        password = request.form.get(
            "password", ""
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
                        supabase_error(response),
                        "error"
                    )

                else:

                    data = response.json()

                    user = data.get("user") or {}

                    session.permanent = True

                    session["access_token"] = (
                        data.get("access_token")
                    )

                    session["refresh_token"] = (
                        data.get("refresh_token")
                    )

                    metadata = (
                        user.get("user_metadata")
                        or {}
                    )

                    session["user"] = {
                        "id": user.get("id"),
                        "email": user.get(
                            "email",
                            email
                        ),
                        "full_name": metadata.get(
                            "full_name"
                        ) or user.get(
                            "email",
                            email
                        ),
                    }

                    flash(
                        "Login successful.",
                        "success"
                    )

                    return redirect(
                        url_for("dashboard")
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

<h1>KOJA Login</h1>

<p class="muted">
Login using your email and password.
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

<button class="btn" type="submit">
Login
</button>

</form>

<p class="muted">
Don't have an account?
<a href="/register">Create Account</a>
</p>

</section>

"""
    )


# ============================================================
# DASHBOARD
# ============================================================

@app.route("/dashboard")
@login_required
def dashboard():

    user = current_user()

    name = user.get(
        "full_name",
        user.get("email", "User")
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

</section>

<br>

<section class="grid">

<div class="service">

<h3>Assignments</h3>

<p class="muted">
Academic questions and assignment services.
</p>

<a class="btn" href="/services">
Open
</a>

</div>

<div class="service">

<h3>Farmer Registration</h3>

<p class="muted">
Farmer registration and agricultural services.
</p>

<a class="btn" href="/services">
Open
</a>

</div>

<div class="service">

<h3>Driver & Delivery</h3>

<p class="muted">
Nearby drivers and delivery requests.
</p>

<a class="btn" href="/services">
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

    return page(
        "Services",
        """

<section class="card">

<h1>KOJA Services</h1>

<p class="muted">
Choose the service you need.
</p>

</section>

<br>

<section class="grid">

<div class="service">
<h3>Assignments</h3>
<p class="muted">
Assignments and academic questions.
</p>
</div>

<div class="service">
<h3>Farmer Registration</h3>
<p class="muted">
Farmer registration.
</p>
</div>

<div class="service">
<h3>TPIN Services</h3>
<p class="muted">
TPIN-related services.
</p>
</div>

<div class="service">
<h3>University</h3>
<p class="muted">
University and college requests.
</p>
</div>

<div class="service">
<h3>CV & Jobs</h3>
<p class="muted">
CV and job application services.
</p>
</div>

<div class="service">
<h3>Driver & Delivery</h3>
<p class="muted">
Nearby drivers, requests and GPS.
</p>
</div>

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

<h1>My Profile</h1>

<p>
<strong>Name:</strong>
{user.get("full_name", "")}
</p>

<p>
<strong>Email:</strong>
{user.get("email", "")}
</p>

<p>
<strong>User ID:</strong>
{user.get("id", "")}
</p>

</section>

"""
    )


# ============================================================
# LOGOUT
# ============================================================

@app.route("/logout")
def logout():

    token = session.get("access_token")

    if token:
        logout_user(token)

    session.clear()

    flash(
        "You have been logged out.",
        "success"
    )

    return redirect(url_for("home"))


# ============================================================
# ERROR HANDLERS
# ============================================================

@app.errorhandler(413)
def file_too_large(error):

    return page(
        "File Too Large",
        """

<section class="card">

<h1>File Too Large</h1>

<p>
The maximum upload size is 15 MB.
</p>

</section>

"""
    ), 413


@app.errorhandler(500)
def internal_error(error):

    logger.exception(
        "Unhandled server error"
    )

    return page(
        "Server Error",
        """

<section class="card">

<h1>Server Error</h1>

<p>
The server encountered an unexpected error.
Check the Render logs for the exact error.
</p>

</section>

"""
    ), 500


# ============================================================
# LOCAL START
# ============================================================

if __name__ == "__main__":

    port = int(
        os.getenv("PORT", "5000")
    )

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False
    )
