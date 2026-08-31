import os
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
    abort,
)

from werkzeug.security import (
    generate_password_hash,
    check_password_hash,
)

from werkzeug.utils import secure_filename


# ============================================================
# KOJA AFRICA
# Knowledge • Questions • Answers
#
# SUPABASE REST VERSION
#
# IMPORTANT:
# This version does NOT use SQLite.
#
# Authentication:
#   public.koja_users
#
# User profile / role:
#   public.profiles
#
# Existing password hashes such as:
#   scrypt:32768:8:1$...
#
# are verified with Werkzeug check_password_hash().
# ============================================================


load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)

logger = logging.getLogger("koja")


# ============================================================
# CONFIGURATION
# ============================================================

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").strip().rstrip("/")

SUPABASE_SERVICE_KEY = os.environ.get(
    "SUPABASE_SERVICE_KEY",
    ""
).strip()

SECRET_KEY = os.environ.get(
    "SECRET_KEY",
    ""
).strip()

if not SECRET_KEY:
    SECRET_KEY = secrets.token_hex(32)


app = Flask(__name__)

app.secret_key = SECRET_KEY

app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024

app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

if os.environ.get("RENDER"):
    app.config["SESSION_COOKIE_SECURE"] = True


# ============================================================
# SUPABASE CHECK
# ============================================================

def supabase_configured():
    return bool(
        SUPABASE_URL and
        SUPABASE_SERVICE_KEY
    )


def require_supabase():
    if not supabase_configured():
        raise RuntimeError(
            "SUPABASE_URL and SUPABASE_SERVICE_KEY "
            "must be configured in Render environment variables."
        )


def supabase_headers():
    require_supabase()

    return {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
    }


# ============================================================
# SUPABASE REST HELPERS
# ============================================================

def supabase_get(
    table,
    params=None,
    timeout=20
):
    """
    GET rows from Supabase PostgREST.
    """

    url = f"{SUPABASE_URL}/rest/v1/{quote(table, safe='')}"

    response = requests.get(
        url,
        headers=supabase_headers(),
        params=params or {},
        timeout=timeout,
    )

    if not response.ok:
        logger.error(
            "Supabase GET %s failed: %s",
            table,
            response.text[:1000]
        )

        raise RuntimeError(
            f"Supabase error while reading {table}: "
            f"{response.status_code} {response.text[:500]}"
        )

    try:
        return response.json()
    except Exception:
        return []


def supabase_insert(
    table,
    data,
    select="*",
    timeout=20
):
    """
    INSERT one row into Supabase.
    """

    url = f"{SUPABASE_URL}/rest/v1/{quote(table, safe='')}"

    headers = supabase_headers()

    headers["Prefer"] = (
        f"return=representation"
    )

    response = requests.post(
        url,
        headers=headers,
        params={
            "select": select
        },
        json=data,
        timeout=timeout,
    )

    if not response.ok:
        logger.error(
            "Supabase INSERT %s failed: %s",
            table,
            response.text[:1500]
        )

        raise RuntimeError(
            f"Supabase insert error in {table}: "
            f"{response.status_code} "
            f"{response.text[:800]}"
        )

    try:
        return response.json()
    except Exception:
        return []


def supabase_update(
    table,
    filters,
    data,
    timeout=20
):
    """
    UPDATE rows.
    """

    url = f"{SUPABASE_URL}/rest/v1/{quote(table, safe='')}"

    response = requests.patch(
        url,
        headers=supabase_headers(),
        params=filters,
        json=data,
        timeout=timeout,
    )

    if not response.ok:
        logger.error(
            "Supabase UPDATE %s failed: %s",
            table,
            response.text[:1000]
        )

        raise RuntimeError(
            f"Supabase update error in {table}: "
            f"{response.status_code} "
            f"{response.text[:500]}"
        )

    try:
        return response.json()
    except Exception:
        return []


def supabase_delete(
    table,
    filters,
    timeout=20
):
    url = f"{SUPABASE_URL}/rest/v1/{quote(table, safe='')}"

    response = requests.delete(
        url,
        headers=supabase_headers(),
        params=filters,
        timeout=timeout,
    )

    if not response.ok:
        logger.error(
            "Supabase DELETE %s failed: %s",
            table,
            response.text[:1000]
        )

        raise RuntimeError(
            f"Supabase delete error in {table}: "
            f"{response.status_code}"
        )

    return True


# ============================================================
# GENERAL HELPERS
# ============================================================

def now_iso():
    return datetime.now(timezone.utc).isoformat()


def clean(value):
    return (value or "").strip()


def current_user():
    """
    Retrieve the authenticated user from koji_users.

    The session stores only the UUID.
    """

    user_id = session.get("user_id")

    if not user_id:
        return None

    try:
        rows = supabase_get(
            "koja_users",
            {
                "id": f"eq.{user_id}",
                "limit": "1",
            }
        )

        if not rows:
            return None

        return rows[0]

    except Exception as exc:
        logger.exception(
            "Unable to load current user: %s",
            exc
        )

        return None


def current_profile():
    """
    Load profile using the same UUID as koji_users.id.
    """

    user = current_user()

    if not user:
        return None

    try:
        rows = supabase_get(
            "profiles",
            {
                "id": f"eq.{user['id']}",
                "limit": "1",
            }
        )

        if rows:
            return rows[0]

    except Exception as exc:
        logger.warning(
            "Profile lookup failed: %s",
            exc
        )

    return None


def get_user_role():
    profile = current_profile()

    if not profile:
        return "student"

    return profile.get(
        "role",
        "student"
    )


def is_admin_user():
    profile = current_profile()

    if not profile:
        return False

    return bool(
        profile.get("is_admin", False)
    )


# ============================================================
# AUTH DECORATORS
# ============================================================

def login_required(view):

    @wraps(view)
    def wrapped(*args, **kwargs):

        if not session.get("user_id"):
            flash(
                "Please log in first.",
                "error"
            )

            return redirect(
                url_for(
                    "login",
                    next=request.path
                )
            )

        user = current_user()

        if not user:
            session.clear()

            flash(
                "Your session has expired. Please log in again.",
                "error"
            )

            return redirect(
                url_for("login")
            )

        return view(*args, **kwargs)

    return wrapped


def admin_required(view):

    @wraps(view)
    def wrapped(*args, **kwargs):

        if not session.get("user_id"):
            return redirect(
                url_for("login")
            )

        if not is_admin_user():
            flash(
                "Administrator access required.",
                "error"
            )

            return redirect(
                url_for("dashboard")
            )

        return view(*args, **kwargs)

    return wrapped


# ============================================================
# AUDIT LOG
# ============================================================

def activity_log(
    action,
    description="",
    user_id=None
):

    try:

        data = {
            "action": action,
            "description": description,
            "user_id": user_id,
            "created_at": now_iso(),
        }

        # Your activity_logs table has these core fields.
        supabase_insert(
            "activity_logs",
            data
        )

    except Exception as exc:

        # Logging must never destroy a normal user request.
        logger.warning(
            "Activity log failed: %s",
            exc
        )


# ============================================================
# HTML / CSS
# ============================================================

CSS = """
<style>

:root{
    --blue:#1756a8;
    --blue2:#0f3f80;
    --green:#16834b;
    --green2:#0f6739;
    --ink:#162235;
    --muted:#667085;
    --bg:#f4f7fb;
    --card:#ffffff;
    --line:#dfe5ec;
    --danger:#c62828;
    --warning:#a66a00;
}

*{
    box-sizing:border-box;
}

body{
    margin:0;
    background:var(--bg);
    color:var(--ink);
    font-family:
        Arial,
        Helvetica,
        sans-serif;
}

a{
    text-decoration:none;
    color:inherit;
}

.nav{
    background:#fff;
    border-bottom:1px solid var(--line);
    position:sticky;
    top:0;
    z-index:100;
}

.nav-inner{
    max-width:1150px;
    margin:auto;
    padding:15px 18px;
    display:flex;
    justify-content:space-between;
    align-items:center;
    gap:15px;
}

.logo{
    color:var(--blue);
    font-size:25px;
    font-weight:900;
    letter-spacing:-.7px;
}

.navlinks{
    display:flex;
    flex-wrap:wrap;
    gap:5px;
    justify-content:flex-end;
}

.navlinks a{
    padding:9px 11px;
    border-radius:9px;
    color:#344054;
    font-size:14px;
}

.navlinks a:hover{
    background:#edf4ff;
}

.container{
    max-width:1150px;
    margin:auto;
    padding:30px 18px 55px;
}

.hero{
    background:
        linear-gradient(
            135deg,
            #eaf3ff,
            #ffffff
        );
    border:1px solid #d8e7fa;
    border-radius:24px;
    padding:38px 28px;
    margin-bottom:22px;
}

.hero h1{
    color:var(--blue);
    font-size:42px;
    margin:0 0 10px;
}

.hero p{
    color:var(--muted);
    line-height:1.6;
    font-size:18px;
}

.card{
    background:var(--card);
    border:1px solid var(--line);
    border-radius:19px;
    padding:25px;
    margin-bottom:20px;
    box-shadow:
        0 5px 20px
        rgba(20,40,70,.05);
}

.card h2{
    margin-top:0;
}

.grid{
    display:grid;
    grid-template-columns:
        repeat(
            2,
            minmax(0,1fr)
        );
    gap:17px;
}

.grid3{
    display:grid;
    grid-template-columns:
        repeat(
            3,
            minmax(0,1fr)
        );
    gap:17px;
}

.field{
    margin-bottom:17px;
}

label{
    display:block;
    font-weight:700;
    margin-bottom:7px;
}

input,
select,
textarea{
    width:100%;
    padding:13px 14px;
    border:
        1px solid #cfd7e2;
    border-radius:10px;
    background:#fff;
    color:var(--ink);
    font-size:16px;
}

textarea{
    min-height:130px;
    resize:vertical;
}

.btn{
    display:inline-block;
    border:0;
    cursor:pointer;
    padding:12px 17px;
    border-radius:10px;
    background:var(--blue);
    color:#fff;
    font-size:15px;
    font-weight:700;
}

.btn:hover{
    background:var(--blue2);
}

.btn.green{
    background:var(--green);
}

.btn.green:hover{
    background:var(--green2);
}

.btn.light{
    background:#edf4ff;
    color:var(--blue);
}

.btn.danger{
    background:var(--danger);
}

.actions{
    display:flex;
    gap:10px;
    flex-wrap:wrap;
    margin-top:15px;
}

.service{
    background:#fff;
    border:
        1px solid var(--line);
    border-radius:16px;
    padding:21px;
}

.service h3{
    margin-top:0;
}

.service p{
    color:var(--muted);
    line-height:1.5;
}

.alert{
    padding:13px 15px;
    border-radius:10px;
    margin-bottom:17px;
}

.alert.success{
    background:#e8f7ee;
    color:#126a3c;
}

.alert.error{
    background:#fdecec;
    color:#a12424;
}

.alert.info{
    background:#eaf2fc;
    color:#24508e;
}

.stat{
    font-size:31px;
    font-weight:900;
    margin-top:7px;
}

.small{
    color:var(--muted);
    font-size:13px;
}

.status{
    display:inline-block;
    padding:7px 10px;
    border-radius:999px;
    background:#eaf2fc;
    color:#24508e;
    font-weight:700;
    font-size:13px;
}

.footer{
    text-align:center;
    color:#7a8798;
    padding:30px 18px;
}

.admin-bar{
    background:#14263d;
    color:#fff;
    padding:14px 18px;
}

.admin-inner{
    max-width:1150px;
    margin:auto;
    display:flex;
    justify-content:space-between;
    gap:15px;
    align-items:center;
}

table{
    width:100%;
    border-collapse:collapse;
}

th,
td{
    padding:11px 9px;
    border-bottom:
        1px solid var(--line);
    text-align:left;
}

th{
    color:var(--muted);
    font-size:13px;
}

.badge{
    display:inline-block;
    background:#edf4ff;
    color:var(--blue);
    padding:6px 9px;
    border-radius:8px;
    font-size:12px;
    font-weight:700;
}

@media(max-width:760px){

    .nav-inner{
        flex-direction:column;
        align-items:flex-start;
    }

    .navlinks{
        justify-content:flex-start;
    }

    .grid,
    .grid3{
        grid-template-columns:1fr;
    }

    .hero h1{
        font-size:31px;
    }

    .container{
        padding:
            22px 13px 45px;
    }

    .card{
        padding:20px;
    }

    table{
        display:block;
        overflow-x:auto;
    }

}

</style>
"""


# ============================================================
# PAGE WRAPPER
# ============================================================

def page(
    title,
    body,
    admin=False
):

    user = current_user()

    if admin:

        nav = """
        <div class="admin-bar">
            <div class="admin-inner">
                <strong>
                    KOJA AFRICA — ADMIN
                </strong>

                <a
                    href="/logout"
                    style="color:white"
                >
                    Logout
                </a>
            </div>
        </div>
        """

    elif user:

        nav = f"""
        <nav class="nav">
            <div class="nav-inner">

                <a
                    class="logo"
                    href="/dashboard"
                >
                    KOJA AFRICA
                </a>

                <div class="navlinks">

                    <a href="/dashboard">
                        Dashboard
                    </a>

                    <a href="/services">
                        Services
                    </a>

                    <a href="/questions">
                        Questions
                    </a>

                    <a href="/assignments">
                        Assignments
                    </a>

                    <a href="/universities">
                        Universities
                    </a>

                    <a href="/profile">
                        Profile
                    </a>

                    <a href="/logout">
                        Logout
                    </a>

                </div>

            </div>
        </nav>
        """

    else:

        nav = """
        <nav class="nav">
            <div class="nav-inner">

                <a
                    class="logo"
                    href="/"
                >
                    KOJA AFRICA
                </a>

                <div class="navlinks">

                    <a href="/">
                        Home
                    </a>

                    <a href="/login">
                        Login
                    </a>

                    <a href="/register">
                        Create Account
                    </a>

                </div>

            </div>
        </nav>
        """

    messages = ""

    from flask import get_flashed_messages

    for category, message in get_flashed_messages(
        with_categories=True
    ):

        messages += (
            f'<div class="alert {category}">'
            f'{message}'
            f'</div>'
        )

    return f"""
<!doctype html>

<html lang="en">

<head>

<meta charset="utf-8">

<meta
    name="viewport"
    content="width=device-width,initial-scale=1"
>

<title>
    {title} | KOJA AFRICA
</title>

{CSS}

</head>

<body>

{nav}

<main class="container">

{messages}

{body}

</main>

<footer class="footer">

<strong>KOJA AFRICA</strong>

<br>

Knowledge • Questions • Answers

<br>

Assignments • Services • Learning • Support

</footer>

</body>

</html>
"""


# ============================================================
# HOME
# ============================================================

@app.route("/")
def home():

    if session.get("user_id"):
        return redirect(
            url_for("dashboard")
        )

    body = """
    <section class="hero">

        <h1>KOJA AFRICA</h1>

        <p>
            Knowledge • Questions • Answers
        </p>

        <p>
            Access academic support, assignments,
            university information and KOJA services
            from one platform.
        </p>

        <div class="actions">

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


    <section class="card">

        <h2>KOJA Services</h2>

        <div class="grid3">

            <div class="service">
                <h3>Academic Support</h3>
                <p>
                    Questions, assignments and
                    learning resources.
                </p>
            </div>

            <div class="service">
                <h3>University Applications</h3>
                <p>
                    Explore universities and
                    application information.
                </p>
            </div>

            <div class="service">
                <h3>KOJA Services</h3>
                <p>
                    Farmer, CV, doctor, delivery
                    and other service requests.
                </p>
            </div>

        </div>

    </section>
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

        full_name = clean(
            request.form.get("full_name")
        )

        email = clean(
            request.form.get("email")
        ).lower()

        phone = clean(
            request.form.get("phone")
        )

        password = request.form.get(
            "password",
            ""
        )

        confirmation = request.form.get(
            "confirm_password",
            ""
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

        elif len(password) < 6:
            flash(
                "Password must contain at least 6 characters.",
                "error"
            )

        elif password != confirmation:
            flash(
                "Passwords do not match.",
                "error"
            )

        else:

            try:

                existing = supabase_get(
                    "koja_users",
                    {
                        "email": f"eq.{email}",
                        "limit": "1",
                    }
                )

                if existing:

                    flash(
                        "An account with this email already exists.",
                        "error"
                    )

                else:

                    user_id = str(
                        uuid.uuid4()
                    )

                    password_hash = (
                        generate_password_hash(
                            password
                        )
                    )

                    user_rows = supabase_insert(
                        "koja_users",
                        {
                            "id": user_id,
                            "full_name": full_name,
                            "email": email,
                            "phone": phone or None,
                            "password_hash": password_hash,
                            "created_at": now_iso(),
                            "updated_at": now_iso(),
                        }
                    )

                    # Create matching profile.
                    try:

                        supabase_insert(
                            "profiles",
                            {
                                "id": user_id,
                                "name": full_name,
                                "full_name": full_name,
                                "email": email,
                                "phone": phone or None,
                                "role": "student",
                                "is_admin": False,
                                "is_active": True,
                                "created_at": now_iso(),
                                "updated_at": now_iso(),
                            }
                        )

                    except Exception as profile_error:

                        logger.warning(
                            "Profile creation failed: %s",
                            profile_error
                        )

                    activity_log(
                        "register",
                        f"New KOJA account registered: {email}",
                        user_id
                    )

                    flash(
                        "Account created successfully. You can now log in.",
                        "success"
                    )

                    return redirect(
                        url_for("login")
                    )

            except Exception as exc:

                logger.exception(
                    "Registration error"
                )

                flash(
                    f"Registration failed: {str(exc)}",
                    "error"
                )

    body = """
    <section class="card">

        <h2>Create KOJA Account</h2>

        <p class="small">
            Create your KOJA Africa account.
        </p>

        <form method="post">

            <div class="field">

                <label>
                    Full Name
                </label>

                <input
                    name="full_name"
                    autocomplete="name"
                    required
                >

            </div>


            <div class="field">

                <label>
                    Email
                </label>

                <input
                    type="email"
                    name="email"
                    autocomplete="email"
                    required
                >

            </div>


            <div class="field">

                <label>
                    Phone
                </label>

                <input
                    name="phone"
                    autocomplete="tel"
                >

            </div>


            <div class="field">

                <label>
                    Password
                </label>

                <input
                    type="password"
                    name="password"
                    autocomplete="new-password"
                    required
                >

            </div>


            <div class="field">

                <label>
                    Confirm Password
                </label>

                <input
                    type="password"
                    name="confirm_password"
                    autocomplete="new-password"
                    required
                >

            </div>


            <button
                class="btn green"
                type="submit"
            >
                Create Account
            </button>

        </form>

    </section>
    """

    return page(
        "Create Account",
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

        email = clean(
            request.form.get("email")
        ).lower()

        password = request.form.get(
            "password",
            ""
        )

        next_url = clean(
            request.form.get("next")
        )

        if not email or not password:

            flash(
                "Enter your email and password.",
                "error"
            )

        else:

            try:

                # =================================================
                # THIS IS THE IMPORTANT FIX.
                #
                # We search public.koja_users.
                #
                # We DO NOT use:
                #   SQLite
                #   Supabase Auth signInWithPassword
                #   public.users
                #
                # The existing account has a Werkzeug scrypt hash.
                # =================================================

                users = supabase_get(
                    "koja_users",
                    {
                        "email": f"eq.{email}",
                        "limit": "1",
                    }
                )

                if not users:

                    flash(
                        "Invalid email or password.",
                        "error"
                    )

                else:

                    user = users[0]

                    stored_hash = user.get(
                        "password_hash"
                    )

                    if not stored_hash:

                        logger.error(
                            "User %s has no password_hash.",
                            user.get("id")
                        )

                        flash(
                            "This account has no valid password configured.",
                            "error"
                        )

                    else:

                        try:

                            password_ok = (
                                check_password_hash(
                                    stored_hash,
                                    password
                                )
                            )

                        except Exception as hash_error:

                            logger.exception(
                                "Password verification error: %s",
                                hash_error
                            )

                            password_ok = False

                        if not password_ok:

                            flash(
                                "Invalid email or password.",
                                "error"
                            )

                        else:

                            # -----------------------------------------
                            # Profile lookup
                            # -----------------------------------------

                            profiles = supabase_get(
                                "profiles",
                                {
                                    "id": f"eq.{user['id']}",
                                    "limit": "1",
                                }
                            )

                            profile = (
                                profiles[0]
                                if profiles
                                else {}
                            )

                            # -----------------------------------------
                            # Active account check
                            # -----------------------------------------

                            if (
                                profile and
                                profile.get(
                                    "is_active"
                                ) is False
                            ):

                                flash(
                                    "Your account is inactive. Please contact KOJA.",
                                    "error"
                                )

                            else:

                                # -------------------------------------
                                # SUCCESS
                                # -------------------------------------

                                session.clear()

                                session["user_id"] = (
                                    user["id"]
                                )

                                session["user_email"] = (
                                    user.get(
                                        "email"
                                    )
                                )

                                session["user_name"] = (
                                    user.get(
                                        "full_name"
                                    )
                                    or profile.get(
                                        "full_name"
                                    )
                                    or profile.get(
                                        "name"
                                    )
                                    or "KOJA User"
                                )

                                session["role"] = (
                                    profile.get(
                                        "role",
                                        "student"
                                    )
                                )

                                session["is_admin"] = bool(
                                    profile.get(
                                        "is_admin",
                                        False
                                    )
                                )

                                activity_log(
                                    "login",
                                    f"Successful login: {email}",
                                    user["id"]
                                )

                                # Prevent unsafe external redirects.
                                if (
                                    next_url.startswith("/")
                                    and not next_url.startswith("//")
                                ):

                                    return redirect(
                                        next_url
                                    )

                                return redirect(
                                    url_for("dashboard")
                                )

            except Exception as exc:

                logger.exception(
                    "LOGIN ERROR"
                )

                flash(
                    "Unable to connect to the KOJA database. "
                    "Please try again.",
                    "error"
                )

    next_value = clean(
        request.args.get("next")
    )

    body = f"""
    <section class="card">

        <h2>KOJA Africa Login</h2>

        <p class="small">
            Sign in using your KOJA account.
        </p>

        <form method="post">

            <input
                type="hidden"
                name="next"
                value="{next_value}"
            >

            <div class="field">

                <label>
                    Email
                </label>

                <input
                    type="email"
                    name="email"
                    autocomplete="email"
                    required
                >

            </div>


            <div class="field">

                <label>
                    Password
                </label>

                <input
                    type="password"
                    name="password"
                    autocomplete="current-password"
                    required
                >

            </div>


            <button
                class="btn"
                type="submit"
            >
                Login
            </button>

        </form>


        <div class="actions">

            <a
                href="/register"
                class="btn light"
            >
                Create Account
            </a>

        </div>

    </section>
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

    user_id = session.get(
        "user_id"
    )

    if user_id:

        activity_log(
            "logout",
            "User logged out.",
            user_id
        )

    session.clear()

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
    profile = current_profile()

    role = (
        profile.get(
            "role",
            "student"
        )
        if profile
        else "student"
    )

    admin = (
        bool(
            profile.get(
                "is_admin",
                False
            )
        )
        if profile
        else False
    )

    body = f"""
    <section class="hero">

        <h1>
            Welcome,
            {user.get('full_name', 'KOJA User')}
        </h1>

        <p>
            KOJA AFRICA — Knowledge • Questions • Answers
        </p>

        <div class="actions">

            <a
                class="btn green"
                href="/services"
            >
                KOJA Services
            </a>

            <a
                class="btn"
                href="/questions"
            >
                Ask a Question
            </a>

        </div>

    </section>


    <div class="grid3">

        <div class="service">

            <h3>
                Academic Support
            </h3>

            <p>
                Submit questions and academic
                requests.
            </p>

            <a
                class="btn light"
                href="/questions"
            >
                Open
            </a>

        </div>


        <div class="service">

            <h3>
                Assignments
            </h3>

            <p>
                Submit and track assignment
                requests.
            </p>

            <a
                class="btn light"
                href="/assignments"
            >
                Open
            </a>

        </div>


        <div class="service">

            <h3>
                University
            </h3>

            <p>
                Explore universities and
                application information.
            </p>

            <a
                class="btn light"
                href="/universities"
            >
                Open
            </a>

        </div>

    </div>


    <section class="card">

        <h2>Your Account</h2>

        <p>
            <strong>Email:</strong>
            {user.get('email', '')}
        </p>

        <p>
            <strong>Role:</strong>
            <span class="badge">
                {role}
            </span>
        </p>

        <p>
            <strong>Administrator:</strong>
            {'Yes' if admin else 'No'}
        </p>

    </section>
    """

    return page(
        "Dashboard",
        body
    )


# ============================================================
# PROFILE
# ============================================================

@app.route(
    "/profile",
    methods=["GET", "POST"]
)
@login_required
def profile():

    user = current_user()

    if not user:
        return redirect(
            url_for("login")
        )

    if request.method == "POST":

        full_name = clean(
            request.form.get("full_name")
        )

        phone = clean(
            request.form.get("phone")
        )

        if not full_name:

            flash(
                "Full name is required.",
                "error"
            )

        else:

            try:

                supabase_update(
                    "koja_users",
                    {
                        "id": f"eq.{user['id']}"
                    },
                    {
                        "full_name": full_name,
                        "phone": phone or None,
                        "updated_at": now_iso(),
                    }
                )

                # Keep profile synchronized.
                try:

                    supabase_update(
                        "profiles",
                        {
                            "id": f"eq.{user['id']}"
                        },
                        {
                            "name": full_name,
                            "full_name": full_name,
                            "phone": phone or None,
                            "updated_at": now_iso(),
                        }
                    )

                except Exception as exc:

                    logger.warning(
                        "Profile synchronization failed: %s",
                        exc
                    )

                flash(
                    "Profile updated successfully.",
                    "success"
                )

            except Exception as exc:

                logger.exception(
                    "Profile update failed"
                )

                flash(
                    "Unable to update profile.",
                    "error"
                )

    user = current_user()

    body = f"""
    <section class="card">

        <h2>My Profile</h2>

        <form method="post">

            <div class="field">

                <label>
                    Full Name
                </label>

                <input
                    name="full_name"
                    value="{user.get('full_name', '')}"
                    required
                >

            </div>


            <div class="field">

                <label>
                    Email
                </label>

                <input
                    type="email"
                    value="{user.get('email', '')}"
                    disabled
                >

            </div>


            <div class="field">

                <label>
                    Phone
                </label>

                <input
                    name="phone"
                    value="{user.get('phone') or ''}"
                >

            </div>


            <button
                class="btn green"
                type="submit"
            >
                Save Changes
            </button>

        </form>

    </section>
    """

    return page(
        "Profile",
        body
    )


# ============================================================
# SERVICES
# ============================================================

SERVICES = [

    (
        "assignment",
        "Assignments",
        "Submit an assignment or academic work request."
    ),

    (
        "cv",
        "CV & Job Application",
        "Request CV creation, editing or formatting."
    ),

    (
        "farmer",
        "Farmer Registration",
        "Submit a farmer registration request."
    ),

    (
        "doctor",
        "Doctor Booking",
        "Request a non-emergency medical appointment."
    ),

    (
        "delivery",
        "Delivery",
        "Request delivery or driver services."
    ),

    (
        "university",
        "University Application",
        "Get help with university applications."
    ),

    (
        "lawyer",
        "Lawyer",
        "Request legal service assistance."
    ),

    (
        "teacher",
        "Teacher / Tutor",
        "Request a teacher or tutor."
    ),

    (
        "tpin",
        "TPIN Services",
        "Submit a TPIN-related request."
    ),

]


@app.route("/services")
@login_required
def services():

    cards = ""

    for key, name, description in SERVICES:

        cards += f"""
        <div class="service">

            <h3>
                {name}
            </h3>

            <p>
                {description}
            </p>

            <a
                class="btn green"
                href="/service/{key}"
            >
                Open Service
            </a>

        </div>
        """

    body = f"""
    <section class="card">

        <h2>
            KOJA Africa Services
        </h2>

        <p class="small">
            Select the service you need.
        </p>

        <div class="grid">

            {cards}

        </div>

    </section>
    """

    return page(
        "Services",
        body
    )


# ============================================================
# GENERIC SERVICE REQUEST
# ============================================================

@app.route(
    "/service/<service_type>",
    methods=["GET", "POST"]
)
@login_required
def service_request(service_type):

    allowed = {
        x[0]: x[1]
        for x in SERVICES
    }

    if service_type not in allowed:
        abort(404)

    service_name = allowed[
        service_type
    ]

    user = current_user()

    if request.method == "POST":

        subject = clean(
            request.form.get("subject")
        )

        message = clean(
            request.form.get("message")
        )

        phone = clean(
            request.form.get("phone")
        )

        if not subject or not message:

            flash(
                "Subject and description are required.",
                "error"
            )

        else:

            # ----------------------------------------------------
            # We try the existing generic KOJA request tables.
            #
            # The application does not create another SQLite
            # database.
            # ----------------------------------------------------

            request_id = str(
                uuid.uuid4()
            )

            request_no = (
                "KOJA-"
                + datetime.now(
                    timezone.utc
                ).strftime("%Y%m%d")
                + "-"
                + secrets.token_hex(4).upper()
            )

            payload = {
                "id": request_id,
                "request_no": request_no,
                "user_id": user["id"],
                "service_type": service_type,
                "service_name": service_name,
                "subject": subject,
                "message": message,
                "description": message,
                "phone": phone or user.get("phone"),
                "status": "Request Received",
                "created_at": now_iso(),
                "updated_at": now_iso(),
            }

            inserted = False

            # First try koja_service_requests.
            try:

                supabase_insert(
                    "koja_service_requests",
                    payload
                )

                inserted = True

            except Exception as first_error:

                logger.warning(
                    "koja_service_requests insert failed: %s",
                    first_error
                )

            # Second option: service_requests.
            if not inserted:

                try:

                    supabase_insert(
                        "service_requests",
                        payload
                    )

                    inserted = True

                except Exception as second_error:

                    logger.warning(
                        "service_requests insert failed: %s",
                        second_error
                    )

            # Third option: requests.
            if not inserted:

                try:

                    supabase_insert(
                        "requests",
                        payload
                    )

                    inserted = True

                except Exception as third_error:

                    logger.warning(
                        "requests insert failed: %s",
                        third_error
                    )

            if inserted:

                activity_log(
                    "service_request",
                    f"{service_name}: {request_no}",
                    user["id"]
                )

                flash(
                    f"Your {service_name} request "
                    f"{request_no} has been submitted.",
                    "success"
                )

                return redirect(
                    url_for("dashboard")
                )

            flash(
                "The service request could not be saved. "
                "Please contact KOJA administration.",
                "error"
            )

    body = f"""
    <section class="card">

        <h2>
            {service_name}
        </h2>

        <p class="small">
            Submit your request and KOJA will review it.
        </p>

        <form method="post">

            <div class="field">

                <label>
                    Subject
                </label>

                <input
                    name="subject"
                    required
                >

            </div>


            <div class="field">

                <label>
                    Phone
                </label>

                <input
                    name="phone"
                    value="{user.get('phone') or ''}"
                >

            </div>


            <div class="field">

                <label>
                    Description
                </label>

                <textarea
                    name="message"
                    required
                    placeholder="Describe what you need..."
                ></textarea>

            </div>


            <button
                class="btn green"
                type="submit"
            >
                Submit Request
            </button>

        </form>

    </section>
    """

    return page(
        service_name,
        body
    )


# ============================================================
# QUESTIONS
# ============================================================

@app.route("/questions")
@login_required
def questions():

    rows = []

    try:

        rows = supabase_get(
            "questions",
            {
                "select": "*",
                "order": "created_at.desc",
                "limit": "30",
            }
        )

    except Exception as exc:

        logger.warning(
            "Questions load failed: %s",
            exc
        )

    table_rows = ""

    for row in rows:

        title = (
            row.get("title")
            or row.get("question")
            or row.get("subject")
            or "Question"
        )

        status = (
            row.get("status")
            or "Submitted"
        )

        table_rows += f"""
        <tr>

            <td>
                {title}
            </td>

            <td>
                <span class="badge">
                    {status}
                </span>
            </td>

        </tr>
        """

    body = f"""
    <section class="card">

        <div style="
            display:flex;
            justify-content:space-between;
            gap:10px;
            flex-wrap:wrap;
        ">

            <div>

                <h2>
                    Questions
                </h2>

                <p class="small">
                    Academic questions and answers.
                </p>

            </div>

            <a
                class="btn green"
                href="/questions/new"
            >
                Ask Question
            </a>

        </div>

        <table>

            <tr>
                <th>Question</th>
                <th>Status</th>
            </tr>

            {table_rows or '''
            <tr>
                <td colspan="2">
                    No questions found.
                </td>
            </tr>
            '''}

        </table>

    </section>
    """

    return page(
        "Questions",
        body
    )


@app.route(
    "/questions/new",
    methods=["GET", "POST"]
)
@login_required
def new_question():

    user = current_user()

    if request.method == "POST":

        question_text = clean(
            request.form.get("question")
        )

        subject = clean(
            request.form.get("subject")
        )

        if not question_text:

            flash(
                "Please enter your question.",
                "error"
            )

        else:

            payload = {
                "id": str(uuid.uuid4()),
                "user_id": user["id"],
                "question": question_text,
                "subject": subject or None,
                "created_at": now_iso(),
            }

            try:

                supabase_insert(
                    "questions",
                    payload
                )

                activity_log(
                    "question_created",
                    "New academic question submitted.",
                    user["id"]
                )

                flash(
                    "Question submitted successfully.",
                    "success"
                )

                return redirect(
                    url_for("questions")
                )

            except Exception as exc:

                logger.warning(
                    "Question insert failed: %s",
                    exc
                )

                flash(
                    "The question could not be submitted. "
                    "Your current questions table may require "
                    "additional fields.",
                    "error"
                )

    body = """
    <section class="card">

        <h2>
            Ask an Academic Question
        </h2>

        <form method="post">

            <div class="field">

                <label>
                    Subject
                </label>

                <input
                    name="subject"
                    placeholder="e.g. Biology"
                >

            </div>


            <div class="field">

                <label>
                    Question
                </label>

                <textarea
                    name="question"
                    required
                    placeholder="Write your question..."
                ></textarea>

            </div>


            <button
                class="btn green"
                type="submit"
            >
                Submit Question
            </button>

        </form>

    </section>
    """

    return page(
        "Ask Question",
        body
    )


# ============================================================
# ASSIGNMENTS
# ============================================================

@app.route("/assignments")
@login_required
def assignments():

    rows = []

    try:

        rows = supabase_get(
            "assignments",
            {
                "select": "*",
                "order": "created_at.desc",
                "limit": "30",
            }
        )

    except Exception as exc:

        logger.warning(
            "Assignments load failed: %s",
            exc
        )

    table_rows = ""

    for row in rows:

        title = (
            row.get("title")
            or row.get("assignment_title")
            or row.get("subject")
            or "Assignment"
        )

        status = (
            row.get("status")
            or "Submitted"
        )

        table_rows += f"""
        <tr>

            <td>
                {title}
            </td>

            <td>
                <span class="badge">
                    {status}
                </span>
            </td>

        </tr>
        """

    body = f"""
    <section class="card">

        <h2>
            Assignments
        </h2>

        <p class="small">
            Submit and track academic assignments.
        </p>

        <div class="actions">

            <a
                class="btn green"
                href="/service/assignment"
            >
                Submit Assignment Request
            </a>

        </div>

        <br>

        <table>

            <tr>
                <th>Assignment</th>
                <th>Status</th>
            </tr>

            {table_rows or '''
            <tr>
                <td colspan="2">
                    No assignment records found.
                </td>
            </tr>
            '''}

        </table>

    </section>
    """

    return page(
        "Assignments",
        body
    )


# ============================================================
# UNIVERSITIES
# ============================================================

@app.route("/universities")
@login_required
def universities():

    rows = []

    try:

        rows = supabase_get(
            "universities",
            {
                "select": "*",
                "limit": "100",
            }
        )

    except Exception as exc:

        logger.warning(
            "Universities load failed: %s",
            exc
        )

    cards = ""

    for row in rows:

        name = (
            row.get("name")
            or row.get("university_name")
            or row.get("title")
            or "University"
        )

        location = (
            row.get("location")
            or row.get("city")
            or row.get("province")
            or "Zambia"
        )

        cards += f"""
        <div class="service">

            <h3>
                {name}
            </h3>

            <p>
                {location}
            </p>

            <a
                class="btn light"
                href="/service/university"
            >
                Request Application Help
            </a>

        </div>
        """

    body = f"""
    <section class="card">

        <h2>
            Universities
        </h2>

        <p class="small">
            Universities available in the KOJA database.
        </p>

        <div class="grid">

            {cards or '''
            <div class="service">
                <h3>University Application</h3>
                <p>
                    University records are currently unavailable.
                </p>
                <a
                    class="btn green"
                    href="/service/university"
                >
                    Request University Help
                </a>
            </div>
            '''}

        </div>

    </section>
    """

    return page(
        "Universities",
        body
    )


# ============================================================
# ADMIN DASHBOARD
# ============================================================

@app.route("/admin")
@admin_required
def admin_dashboard():

    users_count = 0
    questions_count = 0
    universities_count = 0

    try:

        result = supabase_get(
            "koja_users",
            {
                "select": "id",
                "limit": "1000",
            }
        )

        users_count = len(result)

    except Exception:
        pass

    try:

        result = supabase_get(
            "questions",
            {
                "select": "id",
                "limit": "1000",
            }
        )

        questions_count = len(result)

    except Exception:
        pass

    try:

        result = supabase_get(
            "universities",
            {
                "select": "id",
                "limit": "1000",
            }
        )

        universities_count = len(result)

    except Exception:
        pass

    body = f"""
    <section class="hero">

        <h1>
            KOJA AFRICA ADMIN
        </h1>

        <p>
            Administrator control panel.
        </p>

    </section>


    <div class="grid3">

        <div class="service">

            <h3>
                Users
            </h3>

            <div class="stat">
                {users_count}
            </div>

        </div>


        <div class="service">

            <h3>
                Questions
            </h3>

            <div class="stat">
                {questions_count}
            </div>

        </div>


        <div class="service">

            <h3>
                Universities
            </h3>

            <div class="stat">
                {universities_count}
            </div>

        </div>

    </div>


    <section class="card">

        <h2>
            Administration
        </h2>

        <div class="actions">

            <a
                class="btn"
                href="/admin/users"
            >
                Users
            </a>

            <a
                class="btn"
                href="/admin/questions"
            >
                Questions
            </a>

            <a
                class="btn"
                href="/admin/logs"
            >
                Activity Logs
            </a>

        </div>

    </section>
    """

    return page(
        "Admin Dashboard",
        body,
        admin=True
    )


# ============================================================
# ADMIN USERS
# ============================================================

@app.route("/admin/users")
@admin_required
def admin_users():

    try:

        users = supabase_get(
            "koja_users",
            {
                "select": "id,full_name,email,phone,created_at",
                "order": "created_at.desc",
                "limit": "200",
            }
        )

    except Exception as exc:

        logger.warning(
            "Admin users error: %s",
            exc
        )

        users = []

    rows = ""

    for user in users:

        rows += f"""
        <tr>

            <td>
                {user.get('full_name', '')}
            </td>

            <td>
                {user.get('email', '')}
            </td>

            <td>
                {user.get('phone') or ''}
            </td>

            <td>
                {user.get('created_at') or ''}
            </td>

        </tr>
        """

    body = f"""
    <section class="card">

        <h2>
            KOJA Users
        </h2>

        <table>

            <tr>
                <th>Name</th>
                <th>Email</th>
                <th>Phone</th>
                <th>Created</th>
            </tr>

            {rows or '''
            <tr>
                <td colspan="4">
                    No users found.
                </td>
            </tr>
            '''}

        </table>

    </section>
    """

    return page(
        "Admin Users",
        body,
        admin=True
    )


# ============================================================
# ADMIN QUESTIONS
# ============================================================

@app.route("/admin/questions")
@admin_required
def admin_questions():

    try:

        rows = supabase_get(
            "questions",
            {
                "select": "*",
                "order": "created_at.desc",
                "limit": "100",
            }
        )

    except Exception as exc:

        logger.warning(
            "Admin questions error: %s",
            exc
        )

        rows = []

    table = ""

    for row in rows:

        question = (
            row.get("question")
            or row.get("title")
            or row.get("subject")
            or "Question"
        )

        table += f"""
        <tr>

            <td>
                {question}
            </td>

            <td>
                {row.get('created_at') or ''}
            </td>

        </tr>
        """

    body = f"""
    <section class="card">

        <h2>
            Questions
        </h2>

        <table>

            <tr>
                <th>Question</th>
                <th>Date</th>
            </tr>

            {table or '''
            <tr>
                <td colspan="2">
                    No questions found.
                </td>
            </tr>
            '''}

        </table>

    </section>
    """

    return page(
        "Admin Questions",
        body,
        admin=True
    )


# ============================================================
# ADMIN ACTIVITY LOGS
# ============================================================

@app.route("/admin/logs")
@admin_required
def admin_logs():

    try:

        logs = supabase_get(
            "activity_logs",
            {
                "select": "*",
                "order": "created_at.desc",
                "limit": "100",
            }
        )

    except Exception as exc:

        logger.warning(
            "Logs error: %s",
            exc
        )

        logs = []

    rows = ""

    for log in logs:

        rows += f"""
        <tr>

            <td>
                {log.get('action') or ''}
            </td>

            <td>
                {log.get('description') or ''}
            </td>

            <td>
                {log.get('created_at') or ''}
            </td>

        </tr>
        """

    body = f"""
    <section class="card">

        <h2>
            Activity Logs
        </h2>

        <table>

            <tr>
                <th>Action</th>
                <th>Description</th>
                <th>Date</th>
            </tr>

            {rows or '''
            <tr>
                <td colspan="3">
                    No logs found.
                </td>
            </tr>
            '''}

        </table>

    </section>
    """

    return page(
        "Activity Logs",
        body,
        admin=True
    )


# ============================================================
# HEALTH CHECK
# ============================================================

@app.route("/health")
def health():

    if not supabase_configured():

        return {
            "status": "error",
            "message": (
                "SUPABASE_URL or "
                "SUPABASE_SERVICE_KEY is missing."
            )
        }, 500

    try:

        supabase_get(
            "koja_users",
            {
                "select": "id",
                "limit": "1",
            }
        )

        return {
            "status": "ok",
            "database": "connected",
            "authentication": "koja_users"
        }

    except Exception as exc:

        logger.exception(
            "Health check failed"
        )

        return {
            "status": "error",
            "message": str(exc)
        }, 500


# ============================================================
# ERROR HANDLERS
# ============================================================

@app.errorhandler(413)
def too_large(error):

    return page(
        "File Too Large",
        """
        <section class="card">

            <h2>
                File Too Large
            </h2>

            <p>
                The maximum upload size is 10 MB.
            </p>

            <a
                class="btn"
                href="/dashboard"
            >
                Back to Dashboard
            </a>

        </section>
        """
    ), 413


@app.errorhandler(404)
def not_found(error):

    return page(
        "Page Not Found",
        """
        <section class="card">

            <h2>
                Page Not Found
            </h2>

            <p>
                The page you requested does not exist.
            </p>

            <a
                class="btn"
                href="/dashboard"
            >
                Dashboard
            </a>

        </section>
        """
    ), 404


@app.errorhandler(500)
def internal_error(error):

    logger.exception(
        "Unhandled server error"
    )

    return page(
        "Server Error",
        """
        <section class="card">

            <h2>
                KOJA AFRICA Server Error
            </h2>

            <p>
                The server encountered an unexpected
                error while processing your request.
            </p>

            <p class="small">
                Check the Render logs for the technical
                traceback.
            </p>

            <a
                class="btn"
                href="/"
            >
                Return Home
            </a>

        </section>
        """
    ), 500


# ============================================================
# STARTUP
# ============================================================

@app.before_request
def before_request():

    # Do not make every request dependent on Supabase.
    # The health endpoint will report configuration errors.
    pass


if __name__ == "__main__":

    port = int(
        os.environ.get(
            "PORT",
            "5000"
        )
    )

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False
    )
