import os
import logging
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
    render_template_string,
)

load_dotenv()

# ============================================================
# CONFIGURATION
# ============================================================

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")
SECRET_KEY = os.getenv("SECRET_KEY", "change-this-secret-key")

app = Flask(__name__)
app.secret_key = SECRET_KEY

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("KOJA")

# ============================================================
# SUPABASE HELPERS
# ============================================================

def supabase_headers():
    return {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
    }


def supabase_request(method, path, **kwargs):
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        raise RuntimeError(
            "SUPABASE_URL or SUPABASE_SERVICE_KEY is missing."
        )

    url = f"{SUPABASE_URL}{path}"

    headers = kwargs.pop("headers", {})
    merged_headers = supabase_headers()
    merged_headers.update(headers)

    response = requests.request(
        method,
        url,
        headers=merged_headers,
        timeout=30,
        **kwargs,
    )

    return response


# ============================================================
# AUTH HELPERS
# ============================================================

def current_user():
    return session.get("user")


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user():
            flash("Please log in first.", "warning")
            return redirect(url_for("login"))
        return view(*args, **kwargs)

    return wrapped


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        user = current_user()

        if not user:
            flash("Please log in first.", "warning")
            return redirect(url_for("login"))

        if user.get("role") != "admin":
            flash("Administrator access required.", "danger")
            return redirect(url_for("dashboard"))

        return view(*args, **kwargs)

    return wrapped


# ============================================================
# DATABASE PROFILE
# ============================================================

def get_profile(user_id):
    response = supabase_request(
        "GET",
        "/rest/v1/profiles",
        params={
            "id": f"eq.{user_id}",
            "select": "*",
            "limit": "1",
        },
    )

    if response.status_code != 200:
        logger.error(
            "Profile lookup failed: %s",
            response.text
        )
        return None

    data = response.json()

    if not data:
        return None

    return data[0]


def create_profile(
    user_id,
    full_name,
    email,
    phone="",
    role="student",
):
    payload = {
        "id": user_id,
        "full_name": full_name,
        "email": email,
        "phone": phone,
        "role": role,
    }

    response = supabase_request(
        "POST",
        "/rest/v1/profiles",
        json=payload,
        headers={
            "Prefer": "return=representation",
        },
    )

    if response.status_code not in (200, 201):
        logger.error(
            "Profile creation failed: %s",
            response.text
        )
        return False

    return True


# ============================================================
# PAGE TEMPLATE
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

    <title>{{ title }} - KOJA AFRICA</title>

    <style>
        * {
            box-sizing: border-box;
        }

        body {
            margin: 0;
            font-family: Arial, sans-serif;
            background: #f4f7fb;
            color: #172033;
        }

        nav {
            background: #102a43;
            color: white;
            padding: 15px 20px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 10px;
            flex-wrap: wrap;
        }

        nav a {
            color: white;
            text-decoration: none;
            margin-left: 12px;
        }

        .brand {
            font-size: 21px;
            font-weight: bold;
        }

        .container {
            width: min(1100px, 94%);
            margin: 25px auto;
        }

        .card {
            background: white;
            border-radius: 12px;
            padding: 22px;
            margin-bottom: 20px;
            box-shadow: 0 3px 15px rgba(0,0,0,.07);
        }

        .hero {
            padding: 30px 10px;
        }

        h1 {
            margin-top: 0;
        }

        h2 {
            margin-top: 0;
        }

        input,
        select,
        textarea {
            width: 100%;
            padding: 12px;
            margin-top: 7px;
            margin-bottom: 15px;
            border: 1px solid #ccd5e0;
            border-radius: 8px;
            font-size: 16px;
        }

        textarea {
            min-height: 120px;
            resize: vertical;
        }

        button,
        .button {
            display: inline-block;
            border: 0;
            border-radius: 8px;
            padding: 12px 18px;
            background: #1677ff;
            color: white;
            text-decoration: none;
            cursor: pointer;
            font-size: 15px;
        }

        .button.secondary {
            background: #52606d;
        }

        .button.success {
            background: #16803c;
        }

        .grid {
            display: grid;
            grid-template-columns:
                repeat(auto-fit, minmax(220px, 1fr));
            gap: 15px;
        }

        .service {
            border: 1px solid #e0e6ed;
            border-radius: 10px;
            padding: 18px;
            background: white;
        }

        .flash {
            padding: 12px 15px;
            border-radius: 8px;
            margin-bottom: 12px;
            background: #e8f1ff;
        }

        .small {
            color: #66788a;
            font-size: 14px;
        }

        .danger {
            background: #ffe8e8;
        }

        .warning {
            background: #fff5d9;
        }

        .success-message {
            background: #e4f8ea;
        }

        footer {
            text-align: center;
            color: #718096;
            padding: 30px 10px;
        }

        @media (max-width: 600px) {
            nav {
                align-items: flex-start;
            }

            nav a {
                margin-left: 0;
                margin-right: 10px;
            }
        }
    </style>
</head>

<body>

<nav>
    <div class="brand">
        KOJA AFRICA
    </div>

    <div>
        {% if user %}
            <a href="{{ url_for('dashboard') }}">
                Dashboard
            </a>

            {% if user.get('role') == 'admin' %}
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
</nav>

<div class="container">

    {% with messages = get_flashed_messages(
        with_categories=true
    ) %}

        {% for category, message in messages %}
            <div class="flash {{ category }}">
                {{ message }}
            </div>
        {% endfor %}

    {% endwith %}

    {{ body|safe }}

</div>

<footer>
    KOJA AFRICA
    <br>
    Knowledge • Questions • Answers
</footer>

</body>
</html>
"""


def render_page(title, body):
    return render_template_string(
        BASE_HTML,
        title=title,
        body=body,
        user=current_user(),
    )


# ============================================================
# HOME
# ============================================================

@app.route("/")
def home():
    body = """
    <div class="card hero">
        <h1>KOJA AFRICA</h1>

        <p>
            One platform for academic assistance,
            CV services, university information,
            transport, delivery, farmers and
            professional services.
        </p>

        <p>
            <a class="button"
               href="{{ url_for('register') }}">
                Create Account
            </a>

            <a class="button secondary"
               href="{{ url_for('login') }}">
                Login
            </a>
        </p>
    </div>

    <div class="grid">

        <div class="service">
            <h2>Assignments</h2>
            <p>
                Submit questions and documents,
                receive answers and communicate
                with KOJA.
            </p>
        </div>

        <div class="service">
            <h2>CV</h2>
            <p>
                Submit your CV requirements and
                receive the completed document.
            </p>
        </div>

        <div class="service">
            <h2>Universities</h2>
            <p>
                Research universities and obtain
                application information.
            </p>
        </div>

        <div class="service">
            <h2>Drivers & Delivery</h2>
            <p>
                Find nearby available drivers,
                request rides and deliveries.
            </p>
        </div>

        <div class="service">
            <h2>Farmers</h2>
            <p>
                Register farmers and eventually
                connect them with customers.
            </p>
        </div>

        <div class="service">
            <h2>Professionals</h2>
            <p>
                Find doctors, lawyers, teachers
                and other professionals.
            </p>
        </div>

    </div>
    """

    return render_template_string(
        BASE_HTML,
        title="Home",
        body=render_template_string(body),
        user=current_user(),
    )


# ============================================================
# REGISTER
# ============================================================

@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        full_name = request.form.get(
            "full_name",
            ""
        ).strip()

        email = request.form.get(
            "email",
            ""
        ).strip().lower()

        phone = request.form.get(
            "phone",
            ""
        ).strip()

        password = request.form.get(
            "password",
            ""
        )

        if not full_name:
            flash(
                "Full name is required.",
                "danger"
            )
            return redirect(url_for("register"))

        if not email:
            flash(
                "Email is required.",
                "danger"
            )
            return redirect(url_for("register"))

        if len(password) < 6:
            flash(
                "Password must contain at least 6 characters.",
                "danger"
            )
            return redirect(url_for("register"))

        payload = {
            "email": email,
            "password": password,
            "data": {
                "full_name": full_name,
                "phone": phone,
            },
        }

        try:
            response = supabase_request(
                "POST",
                "/auth/v1/signup",
                json=payload,
            )

            if response.status_code not in (200, 201):
                try:
                    error_data = response.json()
                    error_message = (
                        error_data.get("msg")
                        or error_data.get("message")
                        or error_data.get("error_description")
                        or "Registration failed."
                    )
                except Exception:
                    error_message = response.text

                logger.error(
                    "Registration failed: %s",
                    response.text
                )

                flash(
                    error_message,
                    "danger"
                )

                return redirect(
                    url_for("register")
                )

            data = response.json()

            user_data = data.get("user")

            if user_data:
                user_id = user_data.get("id")

                create_profile(
                    user_id=user_id,
                    full_name=full_name,
                    email=email,
                    phone=phone,
                    role="student",
                )

            flash(
                "Account created. You can now log in.",
                "success-message"
            )

            return redirect(url_for("login"))

        except Exception as exc:
            logger.exception(
                "Registration exception"
            )

            flash(
                f"Registration error: {exc}",
                "danger"
            )

            return redirect(
                url_for("register")
            )

    body = """
    <div class="card">

        <h1>Create KOJA Account</h1>

        <p class="small">
            Use your email and password to create
            one KOJA account.
        </p>

        <form method="POST">

            <label>Full name</label>
            <input
                type="text"
                name="full_name"
                required
            >

            <label>Email</label>
            <input
                type="email"
                name="email"
                required
            >

            <label>Phone</label>
            <input
                type="tel"
                name="phone"
            >

            <label>Password</label>
            <input
                type="password"
                name="password"
                minlength="6"
                required
            >

            <button type="submit">
                Create Account
            </button>

        </form>

        <p>
            Already have an account?
            <a href="{{ url_for('login') }}">
                Login
            </a>
        </p>

    </div>
    """

    return render_template_string(
        BASE_HTML,
        title="Register",
        body=render_template_string(body),
        user=current_user(),
    )


# ============================================================
# LOGIN
# ============================================================

@app.route("/login", methods=["GET", "POST"])
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

        if not email or not password:
            flash(
                "Email and password are required.",
                "danger"
            )
            return redirect(url_for("login"))

        payload = {
            "email": email,
            "password": password,
        }

        try:
            response = supabase_request(
                "POST",
                "/auth/v1/token?grant_type=password",
                json=payload,
            )

            if response.status_code != 200:

                try:
                    error_data = response.json()

                    error_message = (
                        error_data.get("msg")
                        or error_data.get("message")
                        or error_data.get("error_description")
                        or "Invalid email or password."
                    )

                except Exception:
                    error_message = (
                        "Invalid email or password."
                    )

                logger.error(
                    "Login failed: %s",
                    response.text
                )

                flash(
                    error_message,
                    "danger"
                )

                return redirect(
                    url_for("login")
                )

            data = response.json()

            user_data = data.get("user")

            if not user_data:
                flash(
                    "Login succeeded but user information was missing.",
                    "danger"
                )
                return redirect(
                    url_for("login")
                )

            user_id = user_data.get("id")

            profile = get_profile(user_id)

            if not profile:
                create_profile(
                    user_id=user_id,
                    full_name=(
                        user_data
                        .get("user_metadata", {})
                        .get("full_name", "")
                    ),
                    email=email,
                    phone=(
                        user_data
                        .get("user_metadata", {})
                        .get("phone", "")
                    ),
                    role="student",
                )

                profile = get_profile(user_id)

            session["user"] = {
                "id": user_id,
                "email": email,
                "role": (
                    profile.get("role", "student")
                    if profile
                    else "student"
                ),
                "full_name": (
                    profile.get("full_name", "")
                    if profile
                    else ""
                ),
            }

            session["access_token"] = data.get(
                "access_token"
            )

            flash(
                "Login successful.",
                "success-message"
            )

            return redirect(
                url_for("dashboard")
            )

        except Exception as exc:

            logger.exception(
                "Login exception"
            )

            flash(
                f"Login error: {exc}",
                "danger"
            )

            return redirect(
                url_for("login")
            )

    body = """
    <div class="card">

        <h1>KOJA Login</h1>

        <form method="POST">

            <label>Email</label>

            <input
                type="email"
                name="email"
                required
            >

            <label>Password</label>

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
            Don't have an account?
            <a href="{{ url_for('register') }}">
                Create one
            </a>
        </p>

    </div>
    """

    return render_template_string(
        BASE_HTML,
        title="Login",
        body=render_template_string(body),
        user=current_user(),
    )


# ============================================================
# DASHBOARD
# ============================================================

@app.route("/dashboard")
@login_required
def dashboard():

    user = current_user()

    body = """
    <div class="card">

        <h1>
            Welcome,
            {{ user.get("full_name") or user.get("email") }}
        </h1>

        <p>
            Your KOJA account is active.
        </p>

        <p class="small">
            Account role:
            {{ user.get("role") }}
        </p>

    </div>

    <div class="grid">

        <div class="service">
            <h2>Assignment</h2>
            <p>
                Submit an academic question or
                document to KOJA.
            </p>

            <a class="button"
               href="#">
                Coming Next
            </a>
        </div>

        <div class="service">
            <h2>CV</h2>
            <p>
                Submit your CV requirements.
            </p>

            <a class="button"
               href="#">
                Coming Next
            </a>
        </div>

        <div class="service">
            <h2>University</h2>
            <p>
                Search university information.
            </p>

            <a class="button"
               href="#">
                Coming Next
            </a>
        </div>

        <div class="service">
            <h2>Drivers & Delivery</h2>
            <p>
                Find nearby drivers and request
                transport or delivery.
            </p>

            <a class="button"
               href="#">
                Coming Next
            </a>
        </div>

        <div class="service">
            <h2>Farmer</h2>
            <p>
                Create your farmer profile.
            </p>

            <a class="button"
               href="#">
                Coming Next
            </a>
        </div>

        <div class="service">
            <h2>Professionals</h2>
            <p>
                Doctors, lawyers, teachers and
                other professional services.
            </p>

            <a class="button"
               href="#">
                Coming Next
            </a>
        </div>

    </div>
    """

    return render_template_string(
        BASE_HTML,
        title="Dashboard",
        body=render_template_string(
            body,
            user=user,
        ),
        user=user,
    )


# ============================================================
# ADMIN DASHBOARD
# ============================================================

@app.route("/admin")
@admin_required
def admin_dashboard():

    body = """
    <div class="card">

        <h1>KOJA AFRICA ADMIN</h1>

        <p>
            This is the central administration
            area for the KOJA platform.
        </p>

    </div>

    <div class="grid">

        <div class="service">
            <h2>Assignments</h2>
            <p>Manage student questions.</p>
        </div>

        <div class="service">
            <h2>CV Requests</h2>
            <p>Manage CV requests.</p>
        </div>

        <div class="service">
            <h2>Universities</h2>
            <p>Manage university information.</p>
        </div>

        <div class="service">
            <h2>Drivers</h2>
            <p>Verify and manage drivers.</p>
        </div>

        <div class="service">
            <h2>Farmers</h2>
            <p>Manage farmer accounts.</p>
        </div>

        <div class="service">
            <h2>Professionals</h2>
            <p>Manage professional accounts.</p>
        </div>

    </div>
    """

    return render_template_string(
        BASE_HTML,
        title="Admin",
        body=render_template_string(body),
        user=current_user(),
    )


# ============================================================
# LOGOUT
# ============================================================

@app.route("/logout")
def logout():

    session.clear()

    flash(
        "You have been logged out.",
        "success-message"
    )

    return redirect(url_for("home"))


# ============================================================
# HEALTH CHECK
# ============================================================

@app.route("/health")
def health():

    return {
        "status": "ok",
        "application": "KOJA AFRICA",
        "version": "1.0-foundation",
    }


# ============================================================
# ERROR HANDLERS
# ============================================================

@app.errorhandler(404)
def not_found(error):

    return render_page(
        "Page Not Found",
        """
        <div class="card">
            <h1>Page Not Found</h1>
            <p>
                The page you requested does not exist.
            </p>
            <a class="button"
               href="/">
                Return Home
            </a>
        </div>
        """
    ), 404


@app.errorhandler(500)
def internal_error(error):

    logger.exception(
        "Internal server error"
    )

    return render_page(
        "Server Error",
        """
        <div class="card">
            <h1>KOJA Server Error</h1>

            <p>
                KOJA encountered an unexpected
                server error.
            </p>

            <p class="small">
                Check the Render logs for the
                exact technical error.
            </p>

            <a class="button"
               href="/">
                Return Home
            </a>
        </div>
        """
    ), 500


# ============================================================
# START SERVER
# ============================================================

if __name__ == "__main__":

    port = int(
        os.getenv("PORT", "5000")
    )

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False,
    )
