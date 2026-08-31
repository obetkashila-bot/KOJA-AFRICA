import os
import math
import logging
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
    jsonify,
    abort
)

from dotenv import load_dotenv
from werkzeug.utils import secure_filename


# ============================================================
# KOJA AFRICA
# Fresh Flask Application
# ============================================================

load_dotenv()

app = Flask(__name__)

app.secret_key = os.getenv(
    "SECRET_KEY",
    "CHANGE_THIS_SECRET_KEY"
)

app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024


# ============================================================
# CONFIGURATION
# ============================================================

SUPABASE_URL = os.getenv(
    "SUPABASE_URL",
    ""
).rstrip("/")

SUPABASE_SERVICE_KEY = os.getenv(
    "SUPABASE_SERVICE_KEY",
    ""
)

SUPABASE_ANON_KEY = os.getenv(
    "SUPABASE_ANON_KEY",
    SUPABASE_SERVICE_KEY
)

STORAGE_BUCKET = os.getenv(
    "KOJA_STORAGE_BUCKET",
    "koja-files"
)

NOMINATIM_URL = (
    "https://nominatim.openstreetmap.org/reverse"
)

NOMINATIM_HEADERS = {
    "User-Agent": "KOJA-AFRICA/1.0"
}


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO
)

logger = logging.getLogger("koja")


# ============================================================
# BASIC CHECK
# ============================================================

def configuration_ok():
    return bool(
        SUPABASE_URL
        and SUPABASE_SERVICE_KEY
    )


# ============================================================
# SUPABASE REST
# ============================================================

def supabase_request(
    method,
    endpoint,
    **kwargs
):

    if not configuration_ok():
        raise RuntimeError(
            "SUPABASE_URL or "
            "SUPABASE_SERVICE_KEY is missing."
        )

    url = (
        SUPABASE_URL
        + endpoint
    )

    headers = kwargs.pop(
        "headers",
        {}
    )

    headers.setdefault(
        "apikey",
        SUPABASE_SERVICE_KEY
    )

    headers.setdefault(
        "Authorization",
        "Bearer "
        + SUPABASE_SERVICE_KEY
    )

    headers.setdefault(
        "Content-Type",
        "application/json"
    )

    return requests.request(
        method,
        url,
        headers=headers,
        timeout=30,
        **kwargs
    )


def response_error(response):

    try:

        data = response.json()

        return (
            data.get("message")
            or data.get("error_description")
            or data.get("error")
            or response.text
        )

    except Exception:

        return response.text


# ============================================================
# AUTH
# ============================================================

def current_user():

    user = session.get(
        "user"
    )

    return user


def login_required(function):

    @wraps(function)
    def wrapper(*args, **kwargs):

        if not current_user():

            flash(
                "Please log in first.",
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

            return redirect(
                url_for("login")
            )

        if user.get("role") != "admin":

            abort(403)

        return function(
            *args,
            **kwargs
        )

    return wrapper


# ============================================================
# PROFILE
# ============================================================

def get_profile(user_id):

    response = supabase_request(
        "GET",
        "/rest/v1/koja_profiles",
        params={
            "user_id":
                f"eq.{user_id}",
            "select": "*",
            "limit": "1"
        }
    )

    if response.status_code != 200:

        logger.error(
            "Profile lookup failed: %s",
            response.text
        )

        return None

    data = response.json()

    return data[0] if data else None


def create_profile(
    user_id,
    full_name,
    phone,
    email
):

    payload = {
        "user_id": user_id,
        "full_name": full_name,
        "phone": phone,
        "email": email,
        "role": "student"
    }

    response = supabase_request(
        "POST",
        "/rest/v1/koja_profiles",
        json=payload,
        headers={
            "Prefer":
                "return=representation"
        }
    )

    if response.status_code not in (
        200,
        201
    ):

        logger.error(
            "Profile creation failed: %s",
            response.text
        )

        return None

    data = response.json()

    return data[0] if data else None


# ============================================================
# PASSWORD AUTH
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

        phone = request.form.get(
            "phone",
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

        if not full_name:
            flash(
                "Full name is required.",
                "danger"
            )
            return redirect(
                url_for("register")
            )

        if not email:
            flash(
                "Email is required.",
                "danger"
            )
            return redirect(
                url_for("register")
            )

        if len(password) < 6:

            flash(
                "Password must contain at least 6 characters.",
                "danger"
            )

            return redirect(
                url_for("register")
            )

        # Supabase Auth admin creation.
        response = supabase_request(
            "POST",
            "/auth/v1/admin/users",
            json={
                "email": email,
                "password": password,
                "email_confirm": True
            }
        )

        if response.status_code not in (
            200,
            201
        ):

            logger.error(
                "Auth registration failed: %s",
                response.text
            )

            flash(
                "Account creation failed: "
                + response_error(response),
                "danger"
            )

            return redirect(
                url_for("register")
            )

        try:

            auth_user = response.json()

            user_id = auth_user.get(
                "id"
            )

        except Exception:

            user_id = None

        if not user_id:

            flash(
                "Account was created but user ID was not returned.",
                "danger"
            )

            return redirect(
                url_for("login")
            )

        profile = create_profile(
            user_id,
            full_name,
            phone,
            email
        )

        if not profile:

            flash(
                "Account created, but profile could not be saved.",
                "danger"
            )

            return redirect(
                url_for("login")
            )

        flash(
            "KOJA account created successfully. You can now log in.",
            "success"
        )

        return redirect(
            url_for("login")
        )

    body = """

<div class="card">

<h1>Create KOJA Account</h1>

<form method="POST">

<label>Full name</label>

<input
    name="full_name"
    required
>

<label>Phone number</label>

<input
    name="phone"
    type="tel"
>

<label>Email</label>

<input
    name="email"
    type="email"
    required
>

<label>Password</label>

<input
    name="password"
    type="password"
    minlength="6"
    required
>

<button>
Create Account
</button>

</form>

<p>
Already have an account?
<a href="{{ url_for('login') }}">
Log in
</a>
</p>

</div>

"""

    return page(
        "Create Account",
        body
    )


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

        response = requests.post(
            SUPABASE_URL
            + "/auth/v1/token"
            + "?grant_type=password",
            headers={
                "apikey":
                    SUPABASE_ANON_KEY,
                "Content-Type":
                    "application/json"
            },
            json={
                "email": email,
                "password": password
            },
            timeout=30
        )

        if response.status_code != 200:

            logger.error(
                "Login failed: %s",
                response.text
            )

            flash(
                "Invalid email or password.",
                "danger"
            )

            return redirect(
                url_for("login")
            )

        data = response.json()

        auth_user = data.get(
            "user",
            {}
        )

        user_id = auth_user.get(
            "id"
        )

        profile = get_profile(
            user_id
        )

        if not profile:

            flash(
                "Your account profile could not be loaded.",
                "danger"
            )

            return redirect(
                url_for("login")
            )

        session["user"] = {
            "id": user_id,
            "email": email,
            "full_name":
                profile.get(
                    "full_name",
                    ""
                ),
            "role":
                profile.get(
                    "role",
                    "student"
                )
        }

        session["access_token"] = data.get(
            "access_token"
        )

        flash(
            "Welcome to KOJA AFRICA.",
            "success"
        )

        return redirect(
            url_for("dashboard")
        )

    body = """

<div class="card">

<h1>KOJA AFRICA</h1>

<p>
Knowledge • Questions • Answers
</p>

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

<button>
Login
</button>

</form>

<p>
No account?
<a href="{{ url_for('register') }}">
Create one
</a>
</p>

</div>

"""

    return page(
        "Login",
        body
    )


@app.route("/logout")
def logout():

    session.clear()

    flash(
        "You have been logged out.",
        "success"
    )

    return redirect(
        url_for("login")
    )


# ============================================================
# DASHBOARD
# ============================================================

@app.route("/")
def home():

    if current_user():

        return redirect(
            url_for("dashboard")
        )

    body = """

<div class="hero">

<h1>KOJA AFRICA</h1>

<p>
Knowledge • Questions • Answers
</p>

<p>
Assignments, CV services, universities,
rides, deliveries and professional services.
</p>

<a class="button"
   href="{{ url_for('login') }}">
Login
</a>

<a class="button secondary"
   href="{{ url_for('register') }}">
Create Account
</a>

</div>

"""

    return page(
        "KOJA AFRICA",
        body
    )


@app.route("/dashboard")
@login_required
def dashboard():

    user = current_user()

    body = """

<div class="hero">

<h1>
Welcome, {{ user.full_name }}
</h1>

<p>
KOJA AFRICA services
</p>

</div>

<div class="grid">

<a class="service" href="{{ url_for('assignments') }}">
📚
<strong>Assignments</strong>
<span>Ask questions and submit files.</span>
</a>

<a class="service" href="{{ url_for('cv_service') }}">
📄
<strong>CV Services</strong>
<span>Submit CV requirements.</span>
</a>

<a class="service" href="{{ url_for('universities') }}">
🎓
<strong>Universities</strong>
<span>Research universities and requirements.</span>
</a>

<a class="service" href="{{ url_for('nearby_drivers') }}">
🚗
<strong>Rides & Delivery</strong>
<span>Find nearby drivers.</span>
</a>

<a class="service" href="{{ url_for('farmer_register') }}">
🌾
<strong>Farmers</strong>
<span>Register as a farmer.</span>
</a>

<a class="service" href="{{ url_for('professionals') }}">
👨‍⚕️
<strong>Professionals</strong>
<span>Doctors, lawyers, teachers and specialists.</span>
</a>

<a class="service" href="{{ url_for('driver_dashboard') }}">
🚘
<strong>Driver Centre</strong>
<span>Register and manage your driver account.</span>
</a>

{% if user.role == "admin" %}

<a class="service admin"
   href="{{ url_for('admin_dashboard') }}">
⚙️
<strong>Admin</strong>
<span>Manage KOJA.</span>
</a>

{% endif %}

</div>

"""

    return page(
        "Dashboard",
        body,
        user=user
    )


# ============================================================
# ASSIGNMENTS
# ============================================================

@app.route(
    "/assignments",
    methods=["GET", "POST"]
)
@login_required
def assignments():

    user = current_user()

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

        if not title or not question:

            flash(
                "Title and question are required.",
                "danger"
            )

            return redirect(
                url_for("assignments")
            )

        response = supabase_request(
            "POST",
            "/rest/v1/koja_assignments",
            json={
                "student_id":
                    user["id"],
                "title":
                    title,
                "subject":
                    subject,
                "question":
                    question,
                "status":
                    "pending"
            },
            headers={
                "Prefer":
                    "return=representation"
            }
        )

        if response.status_code not in (
            200,
            201
        ):

            logger.error(
                "Assignment save error: %s",
                response.text
            )

            flash(
                "Assignment could not be saved: "
                + response_error(response),
                "danger"
            )

        else:

            flash(
                "Assignment sent to admin.",
                "success"
            )

        return redirect(
            url_for("assignments")
        )

    response = supabase_request(
        "GET",
        "/rest/v1/koja_assignments",
        params={
            "student_id":
                f"eq.{user['id']}",
            "select": "*",
            "order":
                "created_at.desc"
        }
    )

    records = []

    if response.status_code == 200:

        records = response.json()

    body = """

<div class="card">

<h1>Assignments</h1>

<form method="POST">

<label>Assignment title</label>

<input
    name="title"
    required
>

<label>Subject</label>

<input
    name="subject"
>

<label>Question</label>

<textarea
    name="question"
    rows="8"
    required
></textarea>

<button>
Send to Admin
</button>

</form>

</div>

<div class="card">

<h2>My Assignments</h2>

{% for item in records %}

<div class="item">

<strong>
{{ item.title }}
</strong>

<p>
{{ item.subject }}
</p>

<p>
Status:
<strong>
{{ item.status }}
</strong>
</p>

<p>
{{ item.question }}
</p>

</div>

{% else %}

<p>
No assignments submitted yet.
</p>

{% endfor %}

</div>

"""

    return page(
        "Assignments",
        body,
        records=records
    )


# ============================================================
# CV
# ============================================================

@app.route(
    "/cv",
    methods=["GET", "POST"]
)
@login_required
def cv_service():

    if request.method == "POST":

        description = request.form.get(
            "description",
            ""
        ).strip()

        response = supabase_request(
            "POST",
            "/rest/v1/koja_cv_requests",
            json={
                "user_id":
                    current_user()["id"],
                "description":
                    description,
                "status":
                    "pending"
            },
            headers={
                "Prefer":
                    "return=representation"
            }
        )

        if response.status_code not in (
            200,
            201
        ):

            logger.error(
                "CV request error: %s",
                response.text
            )

            flash(
                "CV request failed: "
                + response_error(response),
                "danger"
            )

        else:

            flash(
                "CV request sent to KOJA admin.",
                "success"
            )

        return redirect(
            url_for("cv_service")
        )

    body = """

<div class="card">

<h1>CV Services</h1>

<p>
Upload your CV requirements or tell the KOJA
administrator what you need.
</p>

<form method="POST">

<label>
CV requirements
</label>

<textarea
    name="description"
    rows="10"
    placeholder="Example: I need a CV for a teaching position..."
    required
></textarea>

<button>
Send to Admin
</button>

</form>

</div>

"""

    return page(
        "CV Services",
        body
    )


# ============================================================
# UNIVERSITIES
# ============================================================

@app.route("/universities")
@login_required
def universities():

    response = supabase_request(
        "GET",
        "/rest/v1/koja_universities",
        params={
            "select": "*",
            "order":
                "name.asc"
        }
    )

    schools = []

    if response.status_code == 200:

        schools = response.json()

    body = """

<div class="card">

<h1>
University Research
</h1>

<p>
Research universities, programmes and
application requirements.
</p>

</div>

{% for school in schools %}

<div class="card">

<h2>
{{ school.name }}
</h2>

<p>
{{ school.location or "" }}
</p>

<p>
{{ school.description or "" }}
</p>

{% if school.requirements %}

<h3>
Requirements
</h3>

<p>
{{ school.requirements }}
</p>

{% endif %}

</div>

{% else %}

<div class="card">

<p>
University information is being prepared.
</p>

</div>

{% endfor %}

"""

    return page(
        "Universities",
        body,
        schools=schools
    )


# ============================================================
# DRIVER HELPERS
# ============================================================

def reverse_geocode(
    latitude,
    longitude
):

    try:

        response = requests.get(
            NOMINATIM_URL,
            params={
                "lat":
                    latitude,
                "lon":
                    longitude,
                "format":
                    "jsonv2",
                "zoom":
                    18,
                "addressdetails":
                    1
            },
            headers=NOMINATIM_HEADERS,
            timeout=10
        )

        if response.status_code != 200:

            return "Location unavailable"

        data = response.json()

        address = data.get(
            "address",
            {}
        )

        place = (
            address.get("amenity")
            or address.get("building")
            or address.get("shop")
            or address.get("road")
        )

        area = (
            address.get("neighbourhood")
            or address.get("suburb")
            or address.get("quarter")
        )

        city = (
            address.get("city")
            or address.get("town")
            or address.get("municipality")
            or address.get("village")
        )

        country = address.get(
            "country"
        )

        parts = []

        for value in (
            place,
            area,
            city,
            country
        ):

            if value and value not in parts:

                parts.append(value)

        if parts:

            return ", ".join(parts)

        return data.get(
            "display_name",
            "Location unavailable"
        )

    except Exception as exc:

        logger.exception(
            "Reverse geocoding error: %s",
            exc
        )

        return "Location unavailable"


def distance_km(
    lat1,
    lon1,
    lat2,
    lon2
):

    try:

        lat1 = float(lat1)
        lon1 = float(lon1)
        lat2 = float(lat2)
        lon2 = float(lon2)

    except Exception:

        return None

    radius = 6371.0

    p1 = math.radians(
        lat1
    )

    p2 = math.radians(
        lat2
    )

    dp = math.radians(
        lat2 - lat1
    )

    dl = math.radians(
        lon2 - lon1
    )

    a = (
        math.sin(dp / 2) ** 2
        +
        math.cos(p1)
        *
        math.cos(p2)
        *
        math.sin(dl / 2) ** 2
    )

    return radius * (
        2
        * math.atan2(
            math.sqrt(a),
            math.sqrt(1 - a)
        )
    )


def get_driver(driver_id):

    response = supabase_request(
        "GET",
        "/rest/v1/koja_drivers",
        params={
            "id":
                f"eq.{driver_id}",
            "select":
                "*",
            "limit":
                "1"
        }
    )

    if response.status_code != 200:

        return None

    data = response.json()

    return data[0] if data else None


def get_my_driver():

    user = current_user()

    if not user:

        return None

    response = supabase_request(
        "GET",
        "/rest/v1/koja_drivers",
        params={
            "user_id":
                f"eq.{user['id']}",
            "select":
                "*",
            "limit":
                "1"
        }
    )

    if response.status_code != 200:

        return None

    data = response.json()

    return data[0] if data else None


# ============================================================
# DRIVER REGISTRATION
# ============================================================

@app.route(
    "/driver/register",
    methods=["GET", "POST"]
)
@login_required
def driver_register():

    existing = get_my_driver()

    if existing:

        return redirect(
            url_for(
                "driver_dashboard"
            )
        )

    if request.method == "POST":

        user = current_user()

        full_name = request.form.get(
            "full_name",
            ""
        ).strip()

        phone = request.form.get(
            "phone",
            ""
        ).strip()

        vehicle_type = request.form.get(
            "vehicle_type",
            ""
        ).strip()

        vehicle_number = request.form.get(
            "vehicle_number",
            ""
        ).strip()

        license_number = request.form.get(
            "license_number",
            ""
        ).strip()

        if not full_name or not phone:

            flash(
                "Name and phone are required.",
                "danger"
            )

            return redirect(
                url_for("driver_register")
            )

        response = supabase_request(
            "POST",
            "/rest/v1/koja_drivers",
            json={
                "user_id":
                    user["id"],
                "full_name":
                    full_name,
                "phone":
                    phone,
                "email":
                    user.get("email"),
                "vehicle_type":
                    vehicle_type,
                "vehicle_number":
                    vehicle_number,
                "license_number":
                    license_number,
                "status":
                    "pending",
                "is_online":
                    False
            },
            headers={
                "Prefer":
                    "return=representation"
            }
        )

        if response.status_code not in (
            200,
            201
        ):

            logger.error(
                "Driver registration error: %s",
                response.text
            )

            flash(
                "Driver registration failed: "
                + response_error(response),
                "danger"
            )

        else:

            flash(
                "Driver application submitted. "
                "Wait for admin approval.",
                "success"
            )

        return redirect(
            url_for(
                "driver_dashboard"
            )
        )

    body = """

<div class="card">

<h1>
Driver Registration
</h1>

<form method="POST">

<label>Full name</label>

<input
    name="full_name"
    value="{{ user.full_name }}"
    required
>

<label>Phone</label>

<input
    name="phone"
    required
>

<label>Vehicle type</label>

<select
    name="vehicle_type"
    required
>

<option value="">
Select vehicle
</option>

<option>Car</option>
<option>Taxi</option>
<option>Minibus</option>
<option>Motorcycle</option>
<option>Bicycle</option>
<option>Van</option>
<option>Truck</option>

</select>

<label>Vehicle number</label>

<input
    name="vehicle_number"
>

<label>Driver licence number</label>

<input
    name="license_number"
>

<button>
Submit Driver Registration
</button>

</form>

</div>

"""

    return page(
        "Driver Registration",
        body,
        user=current_user()
    )


# ============================================================
# DRIVER DASHBOARD
# ============================================================

@app.route("/driver")
@login_required
def driver_dashboard():

    driver = get_my_driver()

    if not driver:

        body = """

<div class="card">

<h1>
Become a KOJA Driver
</h1>

<p>
Provide rides and delivery services through KOJA.
</p>

<a class="button"
   href="{{ url_for('driver_register') }}">
Register as Driver
</a>

</div>

"""

        return page(
            "Driver",
            body
        )

    body = """

<div class="card">

<h1>
Driver Centre
</h1>

<h2>
{{ driver.full_name }}
</h2>

<p>
{{ driver.vehicle_type }}
{% if driver.vehicle_number %}
• {{ driver.vehicle_number }}
{% endif %}
</p>

<p>
Approval:
<strong>
{{ driver.status }}
</strong>
</p>

{% if driver.status == "approved" %}

{% if driver.is_online %}

<p class="online">
🟢 ONLINE
</p>

<form method="POST"
      action="{{ url_for('driver_offline') }}">

<button>
Go Offline
</button>

</form>

{% else %}

<p>
⚪ OFFLINE
</p>

<form method="POST"
      action="{{ url_for('driver_online') }}">

<button>
Go Online
</button>

</form>

{% endif %}

{% else %}

<p>
Admin approval is required before you can go online.
</p>

{% endif %}

</div>

<div class="card">

<h2>
Current location
</h2>

<p id="driver-location">
Waiting for GPS...
</p>

</div>

<div class="card">

<a class="button"
   href="{{ url_for('driver_requests') }}">
Ride & Delivery Requests
</a>

</div>

<script>

function sendLocation() {

    if (!navigator.geolocation) {

        document.getElementById(
            "driver-location"
        ).innerText =
            "GPS is not supported.";

        return;
    }

    navigator.geolocation.getCurrentPosition(
        function(position) {

            fetch(
                "{{ url_for(
                    'driver_location'
                ) }}",
                {
                    method: "POST",

                    headers: {
                        "Content-Type":
                            "application/json"
                    },

                    body: JSON.stringify({
                        latitude:
                            position.coords.latitude,

                        longitude:
                            position.coords.longitude
                    })
                }
            )
            .then(
                response => response.json()
            )
            .then(
                data => {

                    if (data.success) {

                        document.getElementById(
                            "driver-location"
                        ).innerText =
                            "📍 "
                            + data.location_name;

                    } else {

                        document.getElementById(
                            "driver-location"
                        ).innerText =
                            data.error;

                    }

                }
            );

        },
        function() {

            document.getElementById(
                "driver-location"
            ).innerText =
                "Please allow GPS access.";

        },
        {
            enableHighAccuracy: true,
            timeout: 15000,
            maximumAge: 10000
        }
    );
}

{% if driver.is_online %}

sendLocation();

setInterval(
    sendLocation,
    30000
);

{% endif %}

</script>

"""

    return page(
        "Driver Centre",
        body,
        driver=driver
    )


# ============================================================
# DRIVER ONLINE
# ============================================================

@app.route(
    "/driver/online",
    methods=["POST"]
)
@login_required
def driver_online():

    driver = get_my_driver()

    if not driver:

        flash(
            "Driver account not found.",
            "danger"
        )

        return redirect(
            url_for("driver_dashboard")
        )

    if driver["status"] != "approved":

        flash(
            "Admin approval is required.",
            "danger"
        )

        return redirect(
            url_for("driver_dashboard")
        )

    response = supabase_request(
        "PATCH",
        "/rest/v1/koja_drivers",
        params={
            "id":
                f"eq.{driver['id']}"
        },
        json={
            "is_online":
                True
        }
    )

    if response.status_code not in (
        200,
        204
    ):

        flash(
            "Could not go online.",
            "danger"
        )

    else:

        flash(
            "You are now online.",
            "success"
        )

    return redirect(
        url_for("driver_dashboard")
    )


# ============================================================
# DRIVER OFFLINE
# ============================================================

@app.route(
    "/driver/offline",
    methods=["POST"]
)
@login_required
def driver_offline():

    driver = get_my_driver()

    if not driver:

        return redirect(
            url_for("driver_dashboard")
        )

    response = supabase_request(
        "PATCH",
        "/rest/v1/koja_drivers",
        params={
            "id":
                f"eq.{driver['id']}"
        },
        json={
            "is_online":
                False
        }
    )

    if response.status_code not in (
        200,
        204
    ):

        flash(
            "Could not go offline.",
            "danger"
        )

    else:

        flash(
            "You are now offline.",
            "success"
        )

    return redirect(
        url_for("driver_dashboard")
    )


# ============================================================
# DRIVER GPS
# ============================================================

@app.route(
    "/driver/location",
    methods=["POST"]
)
@login_required
def driver_location():

    driver = get_my_driver()

    if not driver:

        return jsonify({
            "success":
                False,
            "error":
                "Driver account not found."
        }), 404

    if driver["status"] != "approved":

        return jsonify({
            "success":
                False,
            "error":
                "Driver not approved."
        }), 403

    if not driver["is_online"]:

        return jsonify({
            "success":
                False,
            "error":
                "Driver is offline."
        }), 400

    data = request.get_json(
        silent=True
    ) or {}

    latitude = data.get(
        "latitude"
    )

    longitude = data.get(
        "longitude"
    )

    try:

        latitude = float(
            latitude
        )

        longitude = float(
            longitude
        )

        if not -90 <= latitude <= 90:
            raise ValueError()

        if not -180 <= longitude <= 180:
            raise ValueError()

    except Exception:

        return jsonify({
            "success":
                False,
            "error":
                "Invalid GPS location."
        }), 400

    location_name = reverse_geocode(
        latitude,
        longitude
    )

    now = datetime.now(
        timezone.utc
    ).isoformat()

    response = supabase_request(
        "PATCH",
        "/rest/v1/koja_drivers",
        params={
            "id":
                f"eq.{driver['id']}"
        },
        json={
            "latitude":
                latitude,
            "longitude":
                longitude,
            "location_name":
                location_name,
            "last_location_update":
                now
        }
    )

    if response.status_code not in (
        200,
        204
    ):

        logger.error(
            "GPS save failed: %s",
            response.text
        )

        return jsonify({
            "success":
                False,
            "error":
                "Location could not be saved."
        }), 500

    return jsonify({
        "success":
            True,
        "location_name":
            location_name
    })


# ============================================================
# NEARBY DRIVERS
# ============================================================

@app.route("/drivers")
@login_required
def nearby_drivers():

    latitude = request.args.get(
        "latitude",
        type=float
    )

    longitude = request.args.get(
        "longitude",
        type=float
    )

    if latitude is None or longitude is None:

        body = """

<div class="card">

<h1>
Nearby Drivers
</h1>

<p id="message">
Getting your location...
</p>

</div>

<script>

navigator.geolocation.getCurrentPosition(
    function(position) {

        const lat =
            position.coords.latitude;

        const lon =
            position.coords.longitude;

        window.location.href =
            "{{ url_for('nearby_drivers') }}"
            + "?latitude="
            + encodeURIComponent(lat)
            + "&longitude="
            + encodeURIComponent(lon);

    },
    function() {

        document.getElementById(
            "message"
        ).innerText =
            "Please allow location access.";

    },
    {
        enableHighAccuracy: true,
        timeout: 15000
    }
);

</script>

"""

        return page(
            "Nearby Drivers",
            body
        )

    response = supabase_request(
        "GET",
        "/rest/v1/koja_drivers",
        params={
            "status":
                "eq.approved",
            "is_online":
                "eq.true",
            "select":
                "*"
        }
    )

    drivers = []

    if response.status_code == 200:

        for driver in response.json():

            dlat = driver.get(
                "latitude"
            )

            dlon = driver.get(
                "longitude"
            )

            if dlat is None or dlon is None:

                continue

            distance = distance_km(
                latitude,
                longitude,
                dlat,
                dlon
            )

            if distance is None:

                continue

            if distance <= 20:

                driver[
                    "distance_km"
                ] = round(
                    distance,
                    1
                )

                drivers.append(
                    driver
                )

    drivers.sort(
        key=lambda x:
            x["distance_km"]
    )

    body = """

<div class="card">

<h1>
Nearby Drivers
</h1>

<p>
Drivers are shown by distance from your current
location.
</p>

</div>

{% for driver in drivers %}

<div class="card">

<h2>
🚗 {{ driver.full_name }}
</h2>

<p>
{{ driver.vehicle_type }}
{% if driver.vehicle_number %}
• {{ driver.vehicle_number }}
{% endif %}
</p>

<p>
📍
{{ driver.location_name or
"Location updating..." }}
</p>

<p>
{{ driver.distance_km }} km away
</p>

<a class="button"
   href="{{ url_for(
       'service_request',
       driver_id=driver.id,
       service='ride'
   ) }}">
Request Ride
</a>

<a class="button secondary"
   href="{{ url_for(
       'service_request',
       driver_id=driver.id,
       service='delivery'
   ) }}">
Request Delivery
</a>

</div>

{% else %}

<div class="card">

<h2>
No nearby drivers
</h2>

<p>
No approved online drivers were found within
20 km.
</p>

</div>

{% endfor %}

"""

    return page(
        "Nearby Drivers",
        body,
        drivers=drivers
    )


# ============================================================
# RIDE / DELIVERY REQUEST
# ============================================================

@app.route(
    "/service/<driver_id>/<service>",
    methods=["GET", "POST"]
)
@login_required
def service_request(
    driver_id,
    service
):

    if service not in (
        "ride",
        "delivery"
    ):

        abort(404)

    driver = get_driver(
        driver_id
    )

    if not driver:

        flash(
            "Driver not found.",
            "danger"
        )

        return redirect(
            url_for("nearby_drivers")
        )

    if driver["status"] != "approved":

        flash(
            "Driver is not approved.",
            "danger"
        )

        return redirect(
            url_for("nearby_drivers")
        )

    if not driver["is_online"]:

        flash(
            "Driver is offline.",
            "danger"
        )

        return redirect(
            url_for("nearby_drivers")
        )

    if request.method == "POST":

        pickup = request.form.get(
            "pickup",
            ""
        ).strip()

        destination = request.form.get(
            "destination",
            ""
        ).strip()

        pickup_latitude = request.form.get(
            "pickup_latitude"
        )

        pickup_longitude = request.form.get(
            "pickup_longitude"
        )

        destination_latitude = request.form.get(
            "destination_latitude"
        )

        destination_longitude = request.form.get(
            "destination_longitude"
        )

        notes = request.form.get(
            "notes",
            ""
        ).strip()

        response = supabase_request(
            "POST",
            "/rest/v1/koja_service_requests",
            json={
                "customer_id":
                    current_user()["id"],
                "driver_id":
                    driver["id"],
                "service_type":
                    service,
                "pickup_location":
                    pickup,
                "destination_location":
                    destination,
                "pickup_latitude":
                    pickup_latitude or None,
                "pickup_longitude":
                    pickup_longitude or None,
                "destination_latitude":
                    destination_latitude or None,
                "destination_longitude":
                    destination_longitude or None,
                "notes":
                    notes,
                "status":
                    "pending"
            },
            headers={
                "Prefer":
                    "return=representation"
            }
        )

        if response.status_code not in (
            200,
            201
        ):

            logger.error(
                "Service request error: %s",
                response.text
            )

            flash(
                "Request failed: "
                + response_error(response),
                "danger"
            )

        else:

            flash(
                "Your request has been sent to the driver.",
                "success"
            )

        return redirect(
            url_for("my_service_requests")
        )

    body = """

<div class="card">

<h1>

{% if service == "ride" %}
Request Ride
{% else %}
Request Delivery
{% endif %}

</h1>

<h2>
🚗 {{ driver.full_name }}
</h2>

<p>
{{ driver.vehicle_type }}
</p>

<p>
📍 {{ driver.location_name }}
</p>

<form method="POST">

<label>
Pickup location
</label>

<input
    id="pickup"
    name="pickup"
    placeholder="Example: Chisokone Market, Kitwe"
    required
>

<input
    type="hidden"
    name="pickup_latitude"
    id="pickup_latitude"
>

<input
    type="hidden"
    name="pickup_longitude"
    id="pickup_longitude"
>

<label>
Destination
</label>

<input
    name="destination"
    placeholder="Example: Riverside, Kitwe"
    required
>

<label>
Details
</label>

<textarea
    name="notes"
    placeholder="Additional information"
></textarea>

<button>
Send Request
</button>

</form>

</div>

<script>

navigator.geolocation.getCurrentPosition(
    function(position) {

        document.getElementById(
            "pickup_latitude"
        ).value =
            position.coords.latitude;

        document.getElementById(
            "pickup_longitude"
        ).value =
            position.coords.longitude;

    }
);

</script>

"""

    return page(
        "Request Service",
        body,
        driver=driver,
        service=service
    )


# ============================================================
# CUSTOMER REQUESTS
# ============================================================

@app.route("/my-requests")
@login_required
def my_service_requests():

    response = supabase_request(
        "GET",
        "/rest/v1/koja_service_requests",
        params={
            "customer_id":
                f"eq.{current_user()['id']}",
            "select":
                "*",
            "order":
                "created_at.desc"
        }
    )

    records = []

    if response.status_code == 200:

        records = response.json()

    body = """

<div class="card">

<h1>
My Ride & Delivery Requests
</h1>

</div>

{% for item in records %}

<div class="card">

<h2>

{% if item.service_type == "ride" %}
🚗 Ride
{% else %}
📦 Delivery
{% endif %}

</h2>

<p>
Pickup:
<br>
📍 {{ item.pickup_location }}
</p>

<p>
Destination:
<br>
📍 {{ item.destination_location }}
</p>

<p>
Status:
<strong>
{{ item.status }}
</strong>
</p>

{% if item.status == "accepted" %}

<a class="button"
   href="{{ url_for(
       'track_service',
       request_id=item.id
   ) }}">
Track Driver
</a>

{% endif %}

</div>

{% else %}

<div class="card">

<p>
No requests yet.
</p>

<a class="button"
   href="{{ url_for('nearby_drivers') }}">
Find Drivers
</a>

</div>

{% endfor %}

"""

    return page(
        "My Requests",
        body,
        records=records
    )


# ============================================================
# DRIVER REQUESTS
# ============================================================

@app.route("/driver/requests")
@login_required
def driver_requests():

    driver = get_my_driver()

    if not driver:

        return redirect(
            url_for("driver_dashboard")
        )

    response = supabase_request(
        "GET",
        "/rest/v1/koja_service_requests",
        params={
            "driver_id":
                f"eq.{driver['id']}",
            "select":
                "*",
            "order":
                "created_at.desc"
        }
    )

    records = []

    if response.status_code == 200:

        records = response.json()

    body = """

<div class="card">

<h1>
Driver Requests
</h1>

</div>

{% for item in records %}

<div class="card">

<h2>

{% if item.service_type == "ride" %}
🚗 Ride Request
{% else %}
📦 Delivery Request
{% endif %}

</h2>

<p>
Pickup:
<br>
📍 {{ item.pickup_location }}
</p>

<p>
Destination:
<br>
📍 {{ item.destination_location }}
</p>

{% if item.notes %}

<p>
{{ item.notes }}
</p>

{% endif %}

<p>
Status:
<strong>
{{ item.status }}
</strong>
</p>

{% if item.status == "pending" %}

<form method="POST"
      action="{{ url_for(
          'accept_service',
          request_id=item.id
      ) }}">

<button>
Accept
</button>

</form>

<form method="POST"
      action="{{ url_for(
          'reject_service',
          request_id=item.id
      ) }}">

<button>
Reject
</button>

</form>

{% elif item.status == "accepted" %}

<form method="POST"
      action="{{ url_for(
          'complete_service',
          request_id=item.id
      ) }}">

<button>
Mark Completed
</button>

</form>

{% endif %}

</div>

{% else %}

<div class="card">

<p>
No requests.
</p>

</div>

{% endfor %}

"""

    return page(
        "Driver Requests",
        body,
        records=records
    )


@app.route(
    "/driver/request/<request_id>/accept",
    methods=["POST"]
)
@login_required
def accept_service(
    request_id
):

    driver = get_my_driver()

    if not driver:

        abort(403)

    response = supabase_request(
        "PATCH",
        "/rest/v1/koja_service_requests",
        params={
            "id":
                f"eq.{request_id}",
            "driver_id":
                f"eq.{driver['id']}",
            "status":
                "eq.pending"
        },
        json={
            "status":
                "accepted",
            "accepted_at":
                datetime.now(
                    timezone.utc
                ).isoformat()
        }
    )

    if response.status_code not in (
        200,
        204
    ):

        flash(
            "Unable to accept request.",
            "danger"
        )

    else:

        flash(
            "Request accepted.",
            "success"
        )

    return redirect(
        url_for("driver_requests")
    )


@app.route(
    "/driver/request/<request_id>/reject",
    methods=["POST"]
)
@login_required
def reject_service(
    request_id
):

    driver = get_my_driver()

    if not driver:

        abort(403)

    response = supabase_request(
        "PATCH",
        "/rest/v1/koja_service_requests",
        params={
            "id":
                f"eq.{request_id}",
            "driver_id":
                f"eq.{driver['id']}",
            "status":
                "eq.pending"
        },
        json={
            "status":
                "rejected"
        }
    )

    if response.status_code not in (
        200,
        204
    ):

        flash(
            "Unable to reject request.",
            "danger"
        )

    return redirect(
        url_for("driver_requests")
    )


@app.route(
    "/driver/request/<request_id>/complete",
    methods=["POST"]
)
@login_required
def complete_service(
    request_id
):

    driver = get_my_driver()

    if not driver:

        abort(403)

    response = supabase_request(
        "PATCH",
        "/rest/v1/koja_service_requests",
        params={
            "id":
                f"eq.{request_id}",
            "driver_id":
                f"eq.{driver['id']}",
            "status":
                "eq.accepted"
        },
        json={
            "status":
                "completed",
            "completed_at":
                datetime.now(
                    timezone.utc
                ).isoformat()
        }
    )

    if response.status_code not in (
        200,
        204
    ):

        flash(
            "Unable to complete request.",
            "danger"
        )

    else:

        flash(
            "Service completed.",
            "success"
        )

    return redirect(
        url_for("driver_requests")
    )


# ============================================================
# LIVE TRACKING
# ============================================================

@app.route(
    "/track/<request_id>"
)
@login_required
def track_service(
    request_id
):

    response = supabase_request(
        "GET",
        "/rest/v1/koja_service_requests",
        params={
            "id":
                f"eq.{request_id}",
            "customer_id":
                f"eq.{current_user()['id']}",
            "select":
                "*",
            "limit":
                "1"
        }
    )

    if response.status_code != 200:

        abort(404)

    records = response.json()

    if not records:

        abort(404)

    item = records[0]

    body = """

<div class="card">

<h1>
Live Driver Tracking
</h1>

<p>
Pickup:
<br>
📍 {{ item.pickup_location }}
</p>

<p>
Destination:
<br>
📍 {{ item.destination_location }}
</p>

<p id="driver-location">
Loading driver location...
</p>

</div>

<script>

function updateTracking() {

    fetch(
        "{{ url_for(
            'tracking_location',
            request_id=item.id
        ) }}"
    )
    .then(
        response => response.json()
    )
    .then(
        data => {

            document.getElementById(
                "driver-location"
            ).innerText =
                data.location_name
                || "Location updating...";

        }
    );

}

updateTracking();

setInterval(
    updateTracking,
    10000
);

</script>

"""

    return page(
        "Live Tracking",
        body,
        item=item
    )


@app.route(
    "/track/<request_id>/location"
)
@login_required
def tracking_location(
    request_id
):

    response = supabase_request(
        "GET",
        "/rest/v1/koja_service_requests",
        params={
            "id":
                f"eq.{request_id}",
            "customer_id":
                f"eq.{current_user()['id']}",
            "select":
                "driver_id,status",
            "limit":
                "1"
        }
    )

    if response.status_code != 200:

        return jsonify({
            "success":
                False,
            "error":
                "Request not found."
        }), 404

    records = response.json()

    if not records:

        return jsonify({
            "success":
                False,
            "error":
                "Request not found."
        }), 404

    item = records[0]

    if item["status"] != "accepted":

        return jsonify({
            "success":
                False,
            "error":
                "Tracking is not active."
        })

    driver = get_driver(
        item["driver_id"]
    )

    if not driver:

        return jsonify({
            "success":
                False,
            "error":
                "Driver not found."
        }), 404

    return jsonify({
        "success":
            True,
        "location_name":
            driver.get(
                "location_name"
            ),
        "latitude":
            driver.get(
                "latitude"
            ),
        "longitude":
            driver.get(
                "longitude"
            )
    })


# ============================================================
# FARMER
# ============================================================

@app.route(
    "/farmer/register",
    methods=["GET", "POST"]
)
@login_required
def farmer_register():

    if request.method == "POST":

        user = current_user()

        response = supabase_request(
            "POST",
            "/rest/v1/koja_farmers",
            json={
                "user_id":
                    user["id"],
                "full_name":
                    request.form.get(
                        "full_name",
                        ""
                    ).strip(),
                "phone":
                    request.form.get(
                        "phone",
                        ""
                    ).strip(),
                "farm_location":
                    request.form.get(
                        "farm_location",
                        ""
                    ).strip(),
                "products":
                    request.form.get(
                        "products",
                        ""
                    ).strip(),
                "status":
                    "pending"
            },
            headers={
                "Prefer":
                    "return=representation"
            }
        )

        if response.status_code not in (
            200,
            201
        ):

            flash(
                "Farmer registration failed: "
                + response_error(response),
                "danger"
            )

        else:

            flash(
                "Farmer registration submitted.",
                "success"
            )

        return redirect(
            url_for("dashboard")
        )

    body = """

<div class="card">

<h1>
Farmer Registration
</h1>

<form method="POST">

<label>Full name</label>

<input
    name="full_name"
    required
>

<label>Phone</label>

<input
    name="phone"
    required
>

<label>Farm location</label>

<input
    name="farm_location"
    placeholder="Example: Kitwe"
>

<label>
Products / crops / livestock
</label>

<textarea
    name="products"
></textarea>

<button>
Register Farmer
</button>

</form>

</div>

"""

    return page(
        "Farmer Registration",
        body
    )


# ============================================================
# PROFESSIONALS
# ============================================================

@app.route("/professionals")
@login_required
def professionals():

    response = supabase_request(
        "GET",
        "/rest/v1/koja_professionals",
        params={
            "status":
                "eq.approved",
            "select":
                "*",
            "order":
                "full_name.asc"
        }
    )

    professionals_data = []

    if response.status_code == 200:

        professionals_data = response.json()

    body = """

<div class="card">

<h1>
Professional Services
</h1>

<p>
Find doctors, lawyers, teachers and other
approved specialists.
</p>

</div>

{% for person in professionals_data %}

<div class="card">

<h2>
{{ person.full_name }}
</h2>

<p>
<strong>
{{ person.profession }}
</strong>
</p>

<p>
Speciality:
{{ person.speciality or "General" }}
</p>

<p>
Phone:
{{ person.phone }}
</p>

<a class="button"
   href="{{ url_for(
       'book_professional',
       professional_id=person.id
   ) }}">
Request Booking
</a>

</div>

{% else %}

<div class="card">

<p>
No approved professionals are currently listed.
</p>

</div>

{% endfor %}

"""

    return page(
        "Professionals",
        body,
        professionals_data=professionals_data
    )


@app.route(
    "/professional/book/<professional_id>",
    methods=["GET", "POST"]
)
@login_required
def book_professional(
    professional_id
):

    response = supabase_request(
        "GET",
        "/rest/v1/koja_professionals",
        params={
            "id":
                f"eq.{professional_id}",
            "status":
                "eq.approved",
            "select":
                "*",
            "limit":
                "1"
        }
    )

    if response.status_code != 200:

        abort(404)

    records = response.json()

    if not records:

        abort(404)

    professional = records[0]

    if request.method == "POST":

        response = supabase_request(
            "POST",
            "/rest/v1/koja_bookings",
            json={
                "client_id":
                    current_user()["id"],
                "professional_id":
                    professional_id,
                "requested_date":
                    request.form.get(
                        "date"
                    ),
                "requested_time":
                    request.form.get(
                        "time"
                    ),
                "notes":
                    request.form.get(
                        "notes",
                        ""
                    ),
                "status":
                    "pending"
            }
        )

        if response.status_code not in (
            200,
            201
        ):

            flash(
                "Booking request failed.",
                "danger"
            )

        else:

            flash(
                "Booking request sent.",
                "success"
            )

        return redirect(
            url_for("professionals")
        )

    body = """

<div class="card">

<h1>
Book {{ professional.full_name }}
</h1>

<p>
{{ professional.profession }}
</p>

<form method="POST">

<label>Date</label>

<input
    type="date"
    name="date"
    required
>

<label>Time</label>

<input
    type="time"
    name="time"
    required
>

<label>Message</label>

<textarea
    name="notes"
></textarea>

<button>
Send Booking Request
</button>

</form>

</div>

"""

    return page(
        "Book Professional",
        body,
        professional=professional
    )


# ============================================================
# ADMIN DASHBOARD
# ============================================================

@app.route("/admin")
@admin_required
def admin_dashboard():

    response = supabase_request(
        "GET",
        "/rest/v1/koja_drivers",
        params={
            "select":
                "*",
            "order":
                "created_at.desc"
        }
    )

    drivers = []

    if response.status_code == 200:

        drivers = response.json()

    body = """

<div class="card">

<h1>
KOJA Admin
</h1>

<p>
Driver applications
</p>

</div>

{% for driver in drivers %}

<div class="card">

<h2>
{{ driver.full_name }}
</h2>

<p>
Phone: {{ driver.phone }}
</p>

<p>
Vehicle:
{{ driver.vehicle_type }}
{{ driver.vehicle_number or "" }}
</p>

<p>
License:
{{ driver.license_number or "" }}
</p>

<p>
Status:
<strong>
{{ driver.status }}
</strong>
</p>

{% if driver.status == "pending" %}

<form method="POST"
      action="{{ url_for(
          'approve_driver',
          driver_id=driver.id
      ) }}">

<button>
Approve Driver
</button>

</form>

<form method="POST"
      action="{{ url_for(
          'reject_driver',
          driver_id=driver.id
      ) }}">

<button>
Reject Driver
</button>

</form>

{% endif %}

</div>

{% else %}

<div class="card">

<p>
No driver applications.
</p>

</div>

{% endfor %}

"""

    return page(
        "Admin",
        body,
        drivers=drivers
    )


@app.route(
    "/admin/driver/<driver_id>/approve",
    methods=["POST"]
)
@admin_required
def approve_driver(
    driver_id
):

    response = supabase_request(
        "PATCH",
        "/rest/v1/koja_drivers",
        params={
            "id":
                f"eq.{driver_id}"
        },
        json={
            "status":
                "approved",
            "is_online":
                False
        }
    )

    if response.status_code not in (
        200,
        204
    ):

        flash(
            "Driver approval failed.",
            "danger"
        )

    else:

        flash(
            "Driver approved.",
            "success"
        )

    return redirect(
        url_for("admin_dashboard")
    )


@app.route(
    "/admin/driver/<driver_id>/reject",
    methods=["POST"]
)
@admin_required
def reject_driver(
    driver_id
):

    response = supabase_request(
        "PATCH",
        "/rest/v1/koja_drivers",
        params={
            "id":
                f"eq.{driver_id}"
        },
        json={
            "status":
                "rejected",
            "is_online":
                False
        }
    )

    if response.status_code not in (
        200,
        204
    ):

        flash(
            "Driver rejection failed.",
            "danger"
        )

    else:

        flash(
            "Driver rejected.",
            "success"
        )

    return redirect(
        url_for("admin_dashboard")
    )


# ============================================================
# ERROR HANDLERS
# ============================================================

@app.errorhandler(403)
def forbidden(error):

    return page(
        "Access Denied",
        """
        <div class="card">
        <h1>Access Denied</h1>
        <p>You do not have permission to access this page.</p>
        </div>
        """
    ), 403


@app.errorhandler(404)
def not_found(error):

    return page(
        "Not Found",
        """
        <div class="card">
        <h1>Page Not Found</h1>
        <p>The requested page does not exist.</p>
        </div>
        """
    ), 404


@app.errorhandler(500)
def server_error(error):

    logger.exception(
        "Internal server error"
    )

    return page(
        "Server Error",
        """
        <div class="card">
        <h1>Server Error</h1>
        <p>
        KOJA encountered an internal error.
        Check the Render logs for the technical details.
        </p>
        </div>
        """
    ), 500


# ============================================================
# MAIN PAGE TEMPLATE
# ============================================================

def page(
    title,
    body,
    **context
):

    user = current_user()

    template = """

<!DOCTYPE html>

<html>

<head>

<meta charset="UTF-8">

<meta
    name="viewport"
    content="width=device-width,
             initial-scale=1.0"
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
        Helvetica,
        sans-serif;

    background:
        #f1f5f9;

    color:
        #0f172a;
}

nav {

    background:
        #0f172a;

    color:
        white;

    padding:
        14px;

    display:
        flex;

    justify-content:
        space-between;

    align-items:
        center;

    gap:
        10px;

    flex-wrap:
        wrap;
}

nav a {

    color:
        white;

    text-decoration:
        none;

    margin:
        4px 8px;
}

.container {

    width:
        min(1100px, 94%);

    margin:
        25px auto;
}

.hero {

    background:
        white;

    padding:
        35px;

    border-radius:
        18px;

    margin-bottom:
        20px;

    box-shadow:
        0 4px 20px
        rgba(0,0,0,.06);
}

.card {

    background:
        white;

    padding:
        22px;

    margin:
        15px 0;

    border-radius:
        16px;

    box-shadow:
        0 3px 15px
        rgba(0,0,0,.05);
}

.grid {

    display:
        grid;

    grid-template-columns:
        repeat(
            auto-fit,
            minmax(
                220px,
                1fr
            )
        );

    gap:
        15px;
}

.service {

    background:
        white;

    padding:
        22px;

    border-radius:
        16px;

    text-decoration:
        none;

    color:
        #0f172a;

    display:
        flex;

    flex-direction:
        column;

    gap:
        8px;

    box-shadow:
        0 3px 15px
        rgba(0,0,0,.05);
}

.service strong {

    font-size:
        18px;
}

.service span {

    color:
        #64748b;
}

form {

    display:
        flex;

    flex-direction:
        column;

    gap:
        10px;

}

label {

    font-weight:
        bold;

    margin-top:
        5px;
}

input,
textarea,
select {

    width:
        100%;

    padding:
        13px;

    border:
        1px solid
        #cbd5e1;

    border-radius:
        10px;

    font-size:
        16px;

    background:
        white;
}

textarea {

    resize:
        vertical;
}

button,
.button {

    display:
        inline-block;

    border:
        none;

    border-radius:
        10px;

    padding:
        12px 18px;

    background:
        #2563eb;

    color:
        white;

    text-decoration:
        none;

    cursor:
        pointer;

    font-size:
        15px;

    margin:
        4px 0;
}

.secondary {

    background:
        #475569;
}

.success {

    background:
        #16a34a;
}

.online {

    color:
        #16a34a;

    font-weight:
        bold;
}

.status {

    font-weight:
        bold;
}

.flash {

    padding:
        13px;

    border-radius:
        10px;

    background:
        #e2e8f0;

    margin-bottom:
        10px;
}

footer {

    text-align:
        center;

    padding:
        30px;

    color:
        #64748b;
}

.small {

    color:
        #64748b;

    font-size:
        13px;
}

</style>

</head>

<body>

<nav>

<div>
<strong>
KOJA AFRICA
</strong>
</div>

<div>

{% if user %}

<a href="{{ url_for('dashboard') }}">
Home
</a>

<a href="{{ url_for('assignments') }}">
Assignments
</a>

<a href="{{ url_for('nearby_drivers') }}">
Drivers
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

</div>

</nav>

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

""" + body + """

</div>

<footer>

KOJA AFRICA

<br>

Knowledge • Questions • Answers

</footer>

</body>

</html>

"""

    return render_template_string(
        template,
        title=title,
        user=user,
        **context
    )


# ============================================================
# HEALTH CHECK
# ============================================================

@app.route("/health")
def health():

    return jsonify({
        "status":
            "ok",
        "app":
            "KOJA AFRICA"
    })


# ============================================================
# RUN
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
        port=port
    )
