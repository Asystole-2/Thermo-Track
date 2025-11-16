import os
import re
import logging
import secrets
from decimal import Decimal
from functools import wraps
from datetime import datetime, date

from flask import (
    Flask,
    render_template,
    redirect,
    request,
    session,
    flash,
    url_for,
    jsonify,
)
from flask_mysqldb import MySQL
from dotenv import load_dotenv, find_dotenv
from werkzeug.security import generate_password_hash, check_password_hash
from MySQLdb._exceptions import IntegrityError, Error
from utils.weather_gemini import WeatherAIAnalyzer

# Google OAuth (Authlib)
try:
    from authlib.integrations.flask_client import OAuth
except ImportError:  # if authlib not installed, Google login will be disabled
    OAuth = None

try:
    from flask_session import Session as ServerSession
except Exception:
    ServerSession = None

# Application Configuration
app = Flask(__name__, template_folder="templates", static_folder="static")
load_dotenv(find_dotenv())

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("thermotrack")

app.config.update(
    SECRET_KEY=os.environ.get("SECRET_KEY", "dev-change-me"),
    MYSQL_HOST=os.environ.get("MYSQL_HOST"),
    MYSQL_USER=os.environ.get("MYSQL_USER"),
    MYSQL_PASSWORD=os.environ.get("MYSQL_PASSWORD", ""),
    MYSQL_DB=os.environ.get("MYSQL_DB"),
    MYSQL_PORT=int(os.environ.get("MYSQL_PORT", "3306")),
    MYSQL_CURSORCLASS="DictCursor",
    SESSION_PERMANENT=False,
    SESSION_TYPE="filesystem",
)

required_env_vars = ["MYSQL_HOST", "MYSQL_USER", "MYSQL_DB"]
if not all(app.config.get(k) for k in required_env_vars):
    missing = [k for k in required_env_vars if not app.config.get(k)]
    raise SystemExit(f"Missing required DB env vars: {', '.join(missing)}")

mysql = MySQL(app)
if ServerSession is not None:
    ServerSession(app)

# ----------------------------------------------------------------------
# Google OAuth configuration
# ----------------------------------------------------------------------
oauth = None
google = None

if OAuth is None:
    log.warning("Authlib is not installed; Google login is disabled.")
else:
    google_client_id = os.environ.get("GOOGLE_CLIENT_ID")
    google_client_secret = os.environ.get("GOOGLE_CLIENT_SECRET")

    if google_client_id and google_client_secret:
        oauth = OAuth(app)
        app.config["GOOGLE_CLIENT_ID"] = google_client_id
        app.config["GOOGLE_CLIENT_SECRET"] = google_client_secret

        google = oauth.register(
            name="google",
            client_id=google_client_id,
            client_secret=google_client_secret,
            server_metadata_url=(
                "https://accounts.google.com/.well-known/openid-configuration"
            ),
            client_kwargs={"scope": "openid email profile"},
        )
        log.info("Google OAuth client registered.")
    else:
        log.warning(
            "GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET not set; Google login disabled."
        )

# ----------------------------------------------------------------------
# Constants & Validation
# ----------------------------------------------------------------------
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
PWD_RE = re.compile(
    r"^(?=.*[A-Z])(?=.*\d)(?=.*[!@#$%^&*()_\-+\=\[\]{};:'\",.<>/?\\|`~]).{8,}$"
)

# ----------------------------------------------------------------------
# Database Utilities
# ----------------------------------------------------------------------
def db_cursor():
    return mysql.connection.cursor()


def _jsonify_rows(rows):
    for r in rows:
        for k, v in list(r.items()):
            if isinstance(v, (datetime, date)):
                r[k] = v.isoformat()
            elif isinstance(v, Decimal):
                r[k] = float(v)
    return rows


# ----------------------------------------------------------------------
# Temperature Conversion Utilities
# ----------------------------------------------------------------------
def _ensure_numeric(value):
    if isinstance(value, Decimal):
        return float(value)
    return value


def convert_temperature(value, from_unit, to_unit):
    if value is None:
        return None

    value = _ensure_numeric(value)

    if from_unit == to_unit:
        return value

    if from_unit == "fahrenheit":
        celsius = (value - 32) * 5 / 9
    elif from_unit == "kelvin":
        celsius = value - 273.15
    else:
        celsius = value

    if to_unit == "fahrenheit":
        return (celsius * 9 / 5) + 32
    elif to_unit == "kelvin":
        return celsius + 273.15
    else:
        return celsius


def format_temperature(value, unit, decimals=1):
    if value is None:
        return "—"

    value = _ensure_numeric(value)
    symbols = {"celsius": "°C", "fahrenheit": "°F", "kelvin": "K"}
    return f"{value:.{decimals}f}{symbols.get(unit, '°C')}"


# ----------------------------------------------------------------------
# Data Access Functions
# ----------------------------------------------------------------------
def get_rooms_summary(user_id=None):
    c = db_cursor()
    params = []
    user_filter = ""

    if user_id is not None:
        user_filter = "WHERE rm.user_id = %s"
        params.append(user_id)

    query = f"""
        SELECT
            rm.id, rm.name AS room_name, rm.location, rm.created_at,
            COUNT(DISTINCT d.id) AS devices_count,
            COUNT(DISTINCT lr.device_id) AS devices_with_readings,
            ROUND(AVG(lr.temperature), 1) AS avg_temp,
            ROUND(AVG(lr.humidity), 1) AS avg_humidity,
            MAX(lr.recorded_at) AS last_update
        FROM rooms rm
        LEFT JOIN devices d ON d.room_id = rm.id
        LEFT JOIN v_latest_device_reading lr ON lr.device_id = d.id
        {user_filter}
        GROUP BY rm.id, rm.name, rm.location, rm.created_at
        ORDER BY rm.name
    """

    c.execute(query, tuple(params))
    rows = c.fetchall()
    c.close()
    return rows


def get_recent_readings(limit=50, offset=0, user_id=None):
    limit = max(1, min(int(limit or 50), 500))
    offset = max(0, int(offset or 0))

    c = db_cursor()
    params = []
    user_filter = ""

    if user_id is not None:
        user_filter = "WHERE rm.user_id = %s"
        params.append(user_id)

    query = f"""
        SELECT
            r.id, r.device_id, r.temperature, r.humidity, r.motion_detected,
            r.pressure, r.light_level, r.recorded_at,
            d.name AS device_name, d.device_uid, d.type AS device_type,
            rm.id AS room_id, rm.name AS room_name
        FROM readings r
        JOIN devices d ON d.id = r.device_id
        JOIN rooms rm ON rm.id = d.room_id
        {user_filter}
        ORDER BY r.recorded_at DESC
        LIMIT %s OFFSET %s
    """
    params.extend([limit, offset])

    c.execute(query, tuple(params))
    rows = c.fetchall()
    c.close()
    return rows


def get_room_details(room_id, user_id=None):
    c = db_cursor()
    params = [room_id]
    user_filter = ""

    if user_id is not None:
        user_filter = " AND rm.user_id = %s"
        params.append(user_id)

    room_query = f"""
        SELECT
            rm.id, rm.name AS room_name, rm.location, rm.created_at, rm.temperature_unit,
            COUNT(DISTINCT d.id) AS devices_count,
            ROUND(AVG(lr.temperature), 1) AS avg_temp,
            ROUND(AVG(lr.humidity), 1) AS avg_humidity,
            MAX(lr.recorded_at) AS last_update
        FROM rooms rm
        LEFT JOIN devices d ON d.room_id = rm.id
        LEFT JOIN v_latest_device_reading lr ON lr.device_id = d.id
        WHERE rm.id = %s {user_filter}
        GROUP BY rm.id
    """

    c.execute(room_query, tuple(params))
    room_data = c.fetchone()

    if not room_data:
        c.close()
        return None, None

    devices_query = """
                    SELECT d.id, \
                           d.name AS device_name, \
                           d.device_uid, \
                           d.type, \
                           d.status, \
                           lr.temperature, \
                           lr.humidity, \
                           lr.recorded_at, \
                           lr.motion_detected
                    FROM devices d
                             LEFT JOIN v_latest_device_reading lr ON lr.device_id = d.id
                    WHERE d.room_id = %s
                    ORDER BY d.name \
                    """

    c.execute(devices_query, (room_id,))
    devices_data = c.fetchall()
    c.close()

    return room_data, devices_data


# ----------------------------------------------------------------------
# Room Management Functions
# ----------------------------------------------------------------------
def create_room(name, location=None, user_id=None, temperature_unit="celsius"):
    name = (name or "").strip()
    location = (location or "").strip() or None

    if not name:
        raise ValueError("Room name is required.")
    if not user_id:
        raise ValueError("User ID is required.")

    cur = db_cursor()
    try:
        cur.execute(
            "INSERT INTO rooms (name, location, user_id, temperature_unit) VALUES (%s, %s, %s, %s)",
            (name, location, user_id, temperature_unit),
        )
        mysql.connection.commit()
    except Exception as e:
        mysql.connection.rollback()
        raise e
    finally:
        cur.close()


def update_room(room_id, name=None, location=None, user_id=None, temperature_unit=None):
    fields = []
    params = []

    if name is not None and name.strip():
        fields.append("name=%s")
        params.append(name.strip())
    if location is not None:
        loc_val = location.strip() or None
        fields.append("location=%s")
        params.append(loc_val)
    if temperature_unit is not None:
        fields.append("temperature_unit=%s")
        params.append(temperature_unit)

    if not fields:
        return 0

    params.extend([room_id, user_id])
    cur = db_cursor()
    try:
        cur.execute(
            f"UPDATE rooms SET {', '.join(fields)} WHERE id=%s AND user_id=%s",
            tuple(params),
        )
        mysql.connection.commit()
        return cur.rowcount
    except Exception as e:
        mysql.connection.rollback()
        raise e
    finally:
        cur.close()


def delete_room(room_id, user_id=None):
    cur = db_cursor()
    try:
        cur.execute("DELETE FROM rooms WHERE id=%s AND user_id=%s", (room_id, user_id))
        mysql.connection.commit()
        return cur.rowcount
    except Exception as e:
        mysql.connection.rollback()
        raise e
    finally:
        cur.close()


# ----------------------------------------------------------------------
# Authentication & Authorization
# ----------------------------------------------------------------------
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get("user_id") is None:
            flash("Please log in to access this page.", "warning")
            return redirect(url_for("login"))
        return f(*args, **kwargs)

    return decorated_function


def is_admin(user_id):
    """Check if user has admin role"""
    if not isinstance(user_id, int) or user_id is None:
        print(f"DEBUG: Invalid user_id: {user_id}")
        return False

    cursor = None
    try:
        cursor = mysql.connection.cursor()
        cursor.execute("SELECT role FROM users WHERE id = %s", (user_id,))
        result = cursor.fetchone()

        print(f"DEBUG: User {user_id} role query result: {result}")

        if result:
            role = result["role"]  # Access by column name
            print(f"DEBUG: User {user_id} has role: '{role}'")
            is_admin_result = role == "admin"
            print(f"DEBUG: Is admin? {is_admin_result}")
            return is_admin_result

        print(f"DEBUG: No user found with id {user_id}")
        return False

    except Exception as e:
        print(f"Error checking admin status: {e}")
        import traceback

        print(f"Full traceback: {traceback.format_exc()}")
        return False
    finally:
        if cursor:
            cursor.close()

# ----------------------------------------------------------------------
# Error Handlers
# ----------------------------------------------------------------------
@app.after_request
def after_request(response):
    # Ensure API routes return JSON even on errors
    if request.path.startswith("/api/") or (
        request.path.startswith("/room/") and "/request_adjustment" in request.path
    ):
        if response.status_code >= 400 and not response.is_json:
            data = {
                "success": False,
                "error": f"Request failed with status {response.status_code}",
                "status": response.status_code,
            }
            response = jsonify(data)
            response.status_code = response.status_code
    return response


@app.errorhandler(404)
def not_found_error(error):
    if request.path.startswith("/api/"):
        return jsonify({"success": False, "error": "Endpoint not found"}), 404
    return error


@app.errorhandler(500)
def internal_error(error):
    if request.path.startswith("/api/") or (
        request.path.startswith("/room/") and "/request_adjustment" in request.path
    ):
        return jsonify({"success": False, "error": "Internal server error"}), 500
    return error


# ----------------------------------------------------------------------
# Route Handlers – Landing & Login
# ----------------------------------------------------------------------
@app.route("/")
def index():
    if session.get("user_id"):
        return redirect(url_for("dashboard"))
    return render_template("index.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        identifier = (request.form.get("identifier") or "").strip()
        password = (request.form.get("password") or "").strip()

        if not identifier or not password:
            flash("Please enter both username/email and password.", "error")
            return render_template("login.html")

        ident_lc = identifier.lower()
        cur = db_cursor()

        try:
            # Load role as well
            if "@" in ident_lc:
                cur.execute(
                    "SELECT id, username, email, password, role FROM users WHERE LOWER(email)=%s LIMIT 1",
                    (ident_lc,),
                )
            else:
                cur.execute(
                    "SELECT id, username, email, password, role FROM users WHERE LOWER(username)=%s LIMIT 1",
                    (ident_lc,),
                )
            row = cur.fetchone()
            print("LOGIN DEBUG — identifier:", identifier)
            print("LOGIN DEBUG — fetched row:", row)

            cur.close()
        except Exception as e:
            mysql.connection.rollback()
            log.exception("Login query failed: %s", e)
            flash("Incorrect username or password.", "error")
            return render_template("login.html")

        if not row:
            flash("Incorrect username or password.", "error")
            return render_template("login.html")

        user_id = row["id"]
        pwd_hash = row["password"]

        try:
            ok = check_password_hash(pwd_hash, password)
            print("PASSWORD CHECK:", ok)
        except Exception:
            ok = pwd_hash == password

        if not ok:
            flash("Incorrect username or password.", "error")
            return render_template("login.html")

        session["user_id"] = user_id
        session["username"] = row["username"]
        session["role"] = row["role"]

        flash("Login successful!", "success")
        return redirect(url_for("dashboard"))

    return render_template("login.html")


# ----------------------------------------------------------------------
# Google Login Routes
# ----------------------------------------------------------------------
@app.route("/login/google")
def login_google():
    """Start Google OAuth login"""
    if not google:
        flash("Google login is not configured.", "error")
        return redirect(url_for("login"))

    redirect_uri = url_for("auth_google", _external=True)
    return google.authorize_redirect(redirect_uri)


@app.route("/auth/google")
def auth_google():
    """Google OAuth callback"""
    if not google:
        flash("Google login is not configured.", "error")
        return redirect(url_for("login"))

    try:
        token = google.authorize_access_token()
    except Exception as e:
        log.exception("Google OAuth error: %s", e)
        flash("Google login failed.", "error")
        return redirect(url_for("login"))

    # Get user info
    userinfo = token.get("userinfo")
    if not userinfo:
        try:
            resp = google.get("userinfo")
            userinfo = resp.json()
        except Exception as e:
            log.exception("Failed to fetch Google userinfo: %s", e)
            flash("Google login failed.", "error")
            return redirect(url_for("login"))

    email = (userinfo.get("email") or "").lower()
    name = userinfo.get("name") or email.split("@")[0]

    if not email:
        flash("Google account has no email address.", "error")
        return redirect(url_for("login"))

    cur = db_cursor()
    try:
        # Try to find existing user by email
        cur.execute(
            "SELECT id, username, email, role FROM users WHERE LOWER(email)=%s LIMIT 1",
            (email,),
        )
        row = cur.fetchone()

        if row:
            user_id = row["id"]
            username = row["username"]
            role = row.get("role", "user")
        else:
            # Create a new local user for this Google account
            username = name.lower().replace(" ", "_")
            dummy_password = generate_password_hash(secrets.token_hex(16))

            cur.execute(
                "INSERT INTO users (username, email, password) VALUES (%s, %s, %s)",
                (username, email, dummy_password),
            )
            mysql.connection.commit()
            user_id = cur.lastrowid
            role = "user"

        session["user_id"] = user_id
        session["username"] = username
        session["role"] = role
        session["google_email"] = email

        flash("Logged in with Google.", "success")
        return redirect(url_for("dashboard"))

    except Exception as e:
        mysql.connection.rollback()
        log.exception("Error handling Google login: %s", e)
        flash("Google login failed.", "error")
        return redirect(url_for("login"))
    finally:
        cur.close()


# ----------------------------------------------------------------------
# Role helper
# ----------------------------------------------------------------------
def role_required(*roles):
    def wrapper(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            user_role = session.get("role")
            if user_role not in roles:
                flash("You do not have permission to access this page.", "error")
                return redirect(url_for("dashboard"))
            return f(*args, **kwargs)

        return decorated_function

    return wrapper


@app.route("/logout")
@login_required
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("index"))


# ----------------------------------------------------------------------
# Registration
# ----------------------------------------------------------------------
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        email = (request.form.get("email") or "").strip()
        password = request.form.get("password") or ""
        confirm = request.form.get("confirmation") or ""

        username_lc = username.lower()
        email_lc = email.lower()
        errors = {}
        values = {"username": username, "email": email}

        if not username:
            errors["username"] = "Username is required."
        if not email:
            errors["email"] = "Email address is required."
        elif not EMAIL_RE.match(email):
            errors["email"] = "Please enter a valid email address."
        if not password:
            errors["password"] = "Password is required."
        elif not PWD_RE.match(password):
            errors["password"] = (
                "Password must be ≥ 8 chars, include one uppercase, one number, and one symbol."
            )
        if not confirm:
            errors["confirmation"] = "Please confirm your password."
        elif password != confirm:
            errors["confirmation"] = "Passwords do not match."

        if errors:
            return render_template("register.html", errors=errors, values=values)

        cur = db_cursor()
        try:
            cur.execute(
                "SELECT 1 FROM users WHERE LOWER(username)=%s LIMIT 1", (username_lc,)
            )
            if cur.fetchone():
                errors["username"] = "This username is already taken."

            cur.execute(
                "SELECT 1 FROM users WHERE LOWER(email)=%s LIMIT 1", (email_lc,)
            )
            if cur.fetchone():
                errors["email"] = "This email is already registered."

            if errors:
                return render_template("register.html", errors=errors, values=values)

            pwd_hash = generate_password_hash(password)
            cur.execute(
                "INSERT INTO users (username, email, password) VALUES (%s, %s, %s)",
                (username_lc, email_lc, pwd_hash),
            )
            mysql.connection.commit()
            flash("Registration successful! You can now log in.", "success")
            return redirect(url_for("login"))

        except IntegrityError as e:
            mysql.connection.rollback()
            msg = str(e).lower()
            if "1062" in msg or "duplicate entry" in msg:
                if "username" in msg:
                    errors["username"] = "This username is already taken."
                if "email" in msg:
                    errors["email"] = "This email is already registered."
                return render_template("register.html", errors=errors, values=values)
            log.exception("IntegrityError during registration: %s", e)
            flash("Database error during registration.", "error")
            return render_template("register.html", values=values)

        except Exception as e:
            mysql.connection.rollback()
            log.exception("Unexpected error during registration: %s", e)
            flash("Unexpected error during registration.", "error")
            return render_template("register.html", values=values)

        finally:
            cur.close()

    return render_template("register.html")


# ----------------------------------------------------------------------
# Main Application Routes (dashboard, rooms, etc.)
# ----------------------------------------------------------------------
@app.route("/dashboard")
@login_required
def dashboard():
    user_id = session.get("user_id")
    rooms = []
    rows = []

    try:
        rooms = get_rooms_summary(user_id=user_id)
    except Exception as e:
        log.exception("[dashboard] rooms load error: %s", e)
        flash("Could not load room data.", "error")

    try:
        rows = get_recent_readings(limit=50, user_id=user_id)
    except Exception as e:
        log.exception("[dashboard] readings load error: %s", e)
        flash("Could not load recent readings.", "error")

    return render_template(
        "dashboard.html",
        active_page="dashboard",
        rooms=rooms,
        rows=rows,
    )

# Application Entry Point
if __name__ == "__main__":
    app.run(debug=True)
