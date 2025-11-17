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
except ImportError:  # if authlib not installed; Google login will be disabled
    OAuth = None

try:
    from flask_session import Session as ServerSession
except Exception:
    ServerSession = None

# =============================================================================
# APPLICATION CONFIGURATION
# =============================================================================

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

# =============================================================================
# GOOGLE OAUTH CONFIGURATION
# =============================================================================

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

# =============================================================================
# CONSTANTS & VALIDATION
# =============================================================================

EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
PWD_RE = re.compile(
    r"^(?=.*[A-Z])(?=.*\d)(?=.*[!@#$%^&*()_\-+\=\[\]{};:'\",.<>/?\\|`~]).{8,}$"
)


# =============================================================================
# DATABASE UTILITIES
# =============================================================================

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


# =============================================================================
# TEMPERATURE CONVERSION UTILITIES
# =============================================================================

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


# =============================================================================
# DATA ACCESS FUNCTIONS
# =============================================================================

def get_rooms_summary(user_id=None, user_role=None):
    """Get rooms summary based on user role"""
    c = db_cursor()

    if user_role in ['admin', 'technician']:
        # Admin/technician sees ALL rooms
        query = """
                SELECT r.id, \
                       r.name                        AS room_name, \
                       r.location, \
                       r.created_at, \
                       COUNT(DISTINCT d.id)          AS devices_count, \
                       COUNT(DISTINCT lr.device_id)  AS devices_with_readings, \
                       ROUND(AVG(lr.temperature), 1) AS avg_temp, \
                       ROUND(AVG(lr.humidity), 1)    AS avg_humidity, \
                       MAX(lr.recorded_at)           AS last_update, \
                       u.username                    as owner_username
                FROM rooms r
                         LEFT JOIN devices d ON d.room_id = r.id
                         LEFT JOIN v_latest_device_reading lr ON lr.device_id = d.id
                         LEFT JOIN users u ON r.user_id = u.id
                GROUP BY r.id, r.name, r.location, r.created_at, u.username
                ORDER BY r.name \
                """
        c.execute(query)
    else:
        # Regular users see only rooms they have access to via user_rooms
        query = """
                SELECT r.id, \
                       r.name                        AS room_name, \
                       r.location, \
                       r.created_at, \
                       COUNT(DISTINCT d.id)          AS devices_count, \
                       COUNT(DISTINCT lr.device_id)  AS devices_with_readings, \
                       ROUND(AVG(lr.temperature), 1) AS avg_temp, \
                       ROUND(AVG(lr.humidity), 1)    AS avg_humidity, \
                       MAX(lr.recorded_at)           AS last_update, \
                       u.username                    as owner_username
                FROM user_rooms ur
                         JOIN rooms r ON ur.room_id = r.id
                         LEFT JOIN devices d ON d.room_id = r.id
                         LEFT JOIN v_latest_device_reading lr ON lr.device_id = d.id
                         LEFT JOIN users u ON r.user_id = u.id
                WHERE ur.user_id = %s
                GROUP BY r.id, r.name, r.location, r.created_at, u.username
                ORDER BY r.name \
                """
        c.execute(query, (user_id,))

    rows = c.fetchall()
    c.close()
    return rows


def get_recent_readings(limit=50, offset=0, user_id=None, user_role=None):
    limit = max(1, min(int(limit or 50), 500))
    offset = max(0, int(offset or 0))

    c = db_cursor()

    if user_role in ['admin', 'technician']:
        # Admin/technician sees ALL readings
        query = """
                SELECT r.id, \
                       r.device_id, \
                       r.temperature, \
                       r.humidity, \
                       r.motion_detected, \
                       r.pressure, \
                       r.light_level, \
                       r.recorded_at, \
                       d.name     AS device_name, \
                       d.device_uid, \
                       d.type     AS device_type, \
                       rm.id      AS room_id, \
                       rm.name    AS room_name, \
                       u.username as room_owner
                FROM readings r
                         JOIN devices d ON d.id = r.device_id
                         JOIN rooms rm ON rm.id = d.room_id
                         LEFT JOIN users u ON rm.user_id = u.id
                ORDER BY r.recorded_at DESC
                    LIMIT %s \
                OFFSET %s \
                """
        c.execute(query, (limit, offset))
    else:
        # Regular users see only readings from rooms they have access to
        query = """
                SELECT r.id, \
                       r.device_id, \
                       r.temperature, \
                       r.humidity, \
                       r.motion_detected, \
                       r.pressure, \
                       r.light_level, \
                       r.recorded_at, \
                       d.name     AS device_name, \
                       d.device_uid, \
                       d.type     AS device_type, \
                       rm.id      AS room_id, \
                       rm.name    AS room_name, \
                       u.username as room_owner
                FROM readings r
                         JOIN devices d ON d.id = r.device_id
                         JOIN rooms rm ON rm.id = d.room_id
                         JOIN user_rooms ur ON ur.room_id = rm.id
                         LEFT JOIN users u ON rm.user_id = u.id
                WHERE ur.user_id = %s
                ORDER BY r.recorded_at DESC
                    LIMIT %s \
                OFFSET %s \
                """
        c.execute(query, (user_id, limit, offset))

    rows = c.fetchall()
    c.close()
    return rows


def get_room_details(room_id, user_id=None, user_role=None):
    c = db_cursor()

    # Check if user has access to this room
    if user_role not in ['admin', 'technician']:
        # For regular users, check if they have access via user_rooms
        c.execute(
            "SELECT 1 FROM user_rooms WHERE user_id = %s AND room_id = %s",
            (user_id, room_id)
        )
        if not c.fetchone():
            c.close()
            return None, None

    # Get room details
    room_query = """
                 SELECT rm.id, \
                        rm.name                                       AS room_name, \
                        rm.location, \
                        rm.created_at, \
                        rm.temperature_unit, \
                        COUNT(DISTINCT d.id)                          AS devices_count, \
                        COALESCE(ROUND(AVG(lr.temperature), 1), 21.0) AS avg_temp, \
                        COALESCE(ROUND(AVG(lr.humidity), 1), 50.0)    AS avg_humidity, \
                        MAX(lr.recorded_at)                           AS last_update, \
                        u.username                                    as owner_username
                 FROM rooms rm
                          LEFT JOIN devices d ON d.room_id = rm.id
                          LEFT JOIN v_latest_device_reading lr ON lr.device_id = d.id
                          LEFT JOIN users u ON rm.user_id = u.id
                 WHERE rm.id = %s
                 GROUP BY rm.id, rm.name, rm.location, rm.created_at, rm.temperature_unit, u.username \
                 """

    c.execute(room_query, (room_id,))
    room_data = c.fetchone()

    if not room_data:
        c.close()
        return None, None

    # Get devices for this room
    devices_query = """
                    SELECT d.id, \
                           d.name AS device_name, \
                           d.device_uid, \
                           d.type, \
                           d.status,
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


# =============================================================================
# ROOM MANAGEMENT FUNCTIONS
# =============================================================================

def create_room(name, location=None, user_id=None, temperature_unit="celsius"):
    name = (name or "").strip()
    location = (location or "").strip() or None

    if not name:
        raise ValueError("Room name is required.")
    if not user_id:
        raise ValueError("User ID is required.")

    cur = db_cursor()
    try:
        # Create the room
        cur.execute(
            "INSERT INTO rooms (name, location, user_id, temperature_unit) VALUES (%s, %s, %s, %s)",
            (name, location, user_id, temperature_unit),
        )
        room_id = cur.lastrowid

        # Add the creator to user_rooms for this room
        cur.execute(
            "INSERT IGNORE INTO user_rooms (user_id, room_id) VALUES (%s, %s)",
            (user_id, room_id)
        )

        mysql.connection.commit()
        return room_id
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
        # Only the original creator can delete the room
        cur.execute("DELETE FROM rooms WHERE id=%s AND user_id=%s", (room_id, user_id))
        mysql.connection.commit()
        return cur.rowcount
    except Exception as e:
        mysql.connection.rollback()
        raise e
    finally:
        cur.close()


def get_all_rooms_with_stats():
    """Get all rooms with device counts and average readings for admin/technician view"""
    c = db_cursor()
    try:
        query = """
                SELECT r.id, \
                       r.name                                                                                        as room_name, \
                       r.location, \
                       u.username                                                                                    as owner_username, \
                       COUNT(DISTINCT d.id)                                                                          as devices_count, \
                       COUNT(DISTINCT CASE \
                                          WHEN lr.temperature IS NOT NULL OR lr.humidity IS NOT NULL \
                                              THEN d.id END)                                                         as devices_with_readings, \
                       ROUND(AVG(lr.temperature), 1)                                                                 as avg_temp, \
                       ROUND(AVG(lr.humidity), 1)                                                                    as avg_humidity, \
                       MAX(lr.recorded_at)                                                                           as last_update
                FROM rooms r
                         LEFT JOIN users u ON r.user_id = u.id
                         LEFT JOIN devices d ON d.room_id = r.id
                         LEFT JOIN v_latest_device_reading lr ON lr.device_id = d.id
                GROUP BY r.id, r.name, r.location, u.username
                ORDER BY r.name \
                """

        c.execute(query)
        rooms = c.fetchall()

        # Convert decimal values to float for JSON serialization
        for room in rooms:
            if room['avg_temp'] is not None:
                room['avg_temp'] = float(room['avg_temp'])
            if room['avg_humidity'] is not None:
                room['avg_humidity'] = float(room['avg_humidity'])

        return rooms
    except Exception as e:
        log.error(f"Error getting all rooms with stats: {e}")
        return []
    finally:
        c.close()


def get_user_rooms(user_id):
    """Get rooms that the current user has access to"""
    c = db_cursor()
    try:
        query = """
                SELECT r.id, \
                       r.name                        as room_name, \
                       r.location, \
                       u.username                    as owner_username, \
                       COUNT(DISTINCT d.id)          as devices_count, \
                       ROUND(AVG(lr.temperature), 1) as avg_temp, \
                       ROUND(AVG(lr.humidity), 1)    as avg_humidity, \
                       MAX(lr.recorded_at)           as last_update
                FROM user_rooms ur
                         JOIN rooms r ON ur.room_id = r.id
                         LEFT JOIN devices d ON d.room_id = r.id
                         LEFT JOIN v_latest_device_reading lr ON lr.device_id = d.id
                         LEFT JOIN users u ON r.user_id = u.id
                WHERE ur.user_id = %s
                GROUP BY r.id, r.name, r.location, u.username
                ORDER BY r.name \
                """

        c.execute(query, (user_id,))
        return c.fetchall()
    except Exception as e:
        log.error(f"Error getting user rooms: {e}")
        return []
    finally:
        c.close()


def get_available_rooms(user_id):
    """Get rooms that the user doesn't have access to but can request access"""
    c = db_cursor()
    try:
        query = """
                SELECT r.id, \
                       r.name                        as room_name, \
                       r.location, \
                       u.username                    as owner_username, \
                       COUNT(DISTINCT d.id)          as devices_count, \
                       ROUND(AVG(lr.temperature), 1) as avg_temp, \
                       ROUND(AVG(lr.humidity), 1)    as avg_humidity, \
                       MAX(lr.recorded_at)           as last_update
                FROM rooms r
                         JOIN users u ON r.user_id = u.id
                         LEFT JOIN devices d ON d.room_id = r.id
                         LEFT JOIN v_latest_device_reading lr ON lr.device_id = d.id
                WHERE r.id NOT IN (SELECT room_id \
                                   FROM user_rooms \
                                   WHERE user_id = %s)
                GROUP BY r.id, r.name, r.location, u.username
                ORDER BY r.name \
                """

        c.execute(query, (user_id,))
        return c.fetchall()
    except Exception as e:
        log.error(f"Error getting available rooms: {e}")
        return []
    finally:
        c.close()


def add_room_to_user(user_id, room_id):
    """Add a room to user's accessible rooms"""
    c = db_cursor()
    try:
        c.execute(
            "INSERT IGNORE INTO user_rooms (user_id, room_id) VALUES (%s, %s)",
            (user_id, room_id)
        )
        mysql.connection.commit()
        return c.rowcount > 0
    except Exception as e:
        mysql.connection.rollback()
        raise e
    finally:
        c.close()


def remove_room_from_user(user_id, room_id):
    """Remove a room from user's accessible rooms"""
    c = db_cursor()
    try:
        c.execute(
            "DELETE FROM user_rooms WHERE user_id = %s AND room_id = %s",
            (user_id, room_id)
        )
        mysql.connection.commit()
        return c.rowcount > 0
    except Exception as e:
        mysql.connection.rollback()
        raise e
    finally:
        c.close()


# =============================================================================
# AUTHENTICATION & AUTHORIZATION
# =============================================================================

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
        log.debug(f"Invalid user_id: {user_id}")
        return False

    cursor = None
    try:
        cursor = mysql.connection.cursor()
        cursor.execute("SELECT role FROM users WHERE id = %s", (user_id,))
        result = cursor.fetchone()

        if result:
            role = result["role"]
            is_admin_result = role == "admin"
            return is_admin_result

        log.debug(f"No user found with id {user_id}")
        return False

    except Exception as e:
        log.error(f"Error checking admin status: {e}")
        return False
    finally:
        if cursor:
            cursor.close()


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


# =============================================================================
# ERROR HANDLERS
# =============================================================================

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


# =============================================================================
# ROUTE HANDLERS – LANDING & AUTH
# =============================================================================

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
            cur.close()

            if not row:
                flash("Incorrect username or password.", "error")
                return render_template("login.html")

            user_id = row["id"]
            pwd_hash = row["password"]

            try:
                ok = check_password_hash(pwd_hash, password)
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

        except Exception as e:
            mysql.connection.rollback()
            log.exception("Login query failed: %s", e)
            flash("Incorrect username or password.", "error")
            return render_template("login.html")

    return render_template("login.html")


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


@app.route("/logout")
@login_required
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("index"))


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


# =============================================================================
# MAIN APPLICATION ROUTES
# =============================================================================

@app.route("/dashboard")
@login_required
def dashboard():
    user_id = session.get("user_id")
    user_role = session.get("role")
    rooms = []
    rows = []

    try:
        rooms = get_rooms_summary(user_id=user_id, user_role=user_role)
    except Exception as e:
        log.exception("[dashboard] rooms load error: %s", e)
        flash("Could not load room data.", "error")

    try:
        rows = get_recent_readings(limit=50, user_id=user_id, user_role=user_role)
    except Exception as e:
        log.exception("[dashboard] readings load error: %s", e)
        flash("Could not load recent readings.", "error")

    return render_template(
        "dashboard.html",
        active_page="dashboard",
        rooms=rooms,
        rows=rows,
    )


@app.route('/setup')
@login_required
def setup():
    try:
        user_id = session.get('user_id')
        user_role = session.get('role')

        if user_role in ['admin', 'technician']:
            all_rooms = get_all_rooms_with_stats()
            return render_template('setup.html',
                                   all_rooms=all_rooms,
                                   user_role=user_role,
                                   user_rooms=[],
                                   available_rooms=[])
        else:
            user_rooms = get_user_rooms(user_id)
            available_rooms = get_available_rooms(user_id)
            return render_template('setup.html',
                                   user_rooms=user_rooms,
                                   available_rooms=available_rooms,
                                   user_role=user_role,
                                   all_rooms=[])

    except Exception as e:
        log.error(f"Setup error: {str(e)}", exc_info=True)

        user_role = session.get('role', 'user')
        if user_role in ['admin', 'technician']:
            return render_template('setup.html',
                                   all_rooms=[],
                                   user_role=user_role,
                                   user_rooms=[],
                                   available_rooms=[],
                                   error="Failed to load room data")
        else:
            return render_template('setup.html',
                                   user_rooms=[],
                                   available_rooms=[],
                                   user_role=user_role,
                                   all_rooms=[],
                                   error="Failed to load room data")


@app.route('/dashboard/add_room/<int:room_id>', methods=['POST'])
@login_required
def dashboard_add_room(room_id):
    if session.get('role') in ['admin', 'technician']:
        flash('Admins and technicians automatically have access to all rooms.', 'info')
        return redirect(url_for('setup'))

    user_id = session.get('user_id')
    if add_room_to_user(user_id, room_id):
        flash('Room added to your dashboard successfully!', 'success')
    else:
        flash('Room is already in your dashboard.', 'warning')

    return redirect(url_for('setup'))


@app.route('/dashboard/remove_room/<int:room_id>', methods=['POST'])
@login_required
def dashboard_remove_room(room_id):
    if session.get('role') in ['admin', 'technician']:
        flash('Admins and technicians cannot remove rooms from dashboard.', 'info')
        return redirect(url_for('setup'))

    user_id = session.get('user_id')
    if remove_room_from_user(user_id, room_id):
        flash('Room removed from your dashboard.', 'success')
    else:
        flash('Room was not in your dashboard.', 'warning')

    return redirect(url_for('setup'))


@app.route("/room/<int:room_id>")
@login_required
def room(room_id):
    user_id = session.get("user_id")
    user_role = session.get("role")

    try:
        room_data, devices_data = get_room_details(room_id, user_id=user_id, user_role=user_role)
    except Exception as e:
        log.exception("[room] error loading details for room %s: %s", room_id, e)
        flash("Could not load room details.", "error")
        return redirect(url_for("dashboard"))

    if not room_data:
        flash("Room not found or you do not have permission to view it.", "error")
        return redirect(url_for("dashboard"))

    room_data.setdefault("temperature_unit", "celsius")

    current_temp = room_data.get("avg_temp", 21.0) or 21.0
    current_humidity = room_data.get("avg_humidity", 50) or 50

    occupancy = (
        sum(1 for d in devices_data if d.get("motion_detected") == 1)
        if devices_data
        else 0
    )

    if room_data["temperature_unit"] != "celsius":
        current_temp_for_ai = convert_temperature(
            current_temp, room_data["temperature_unit"], "celsius"
        )
    else:
        current_temp_for_ai = _ensure_numeric(current_temp)

    ai_room_input = {
        "temperature": current_temp_for_ai or 21.0,
        "humidity": current_humidity or 50,
        "occupancy": occupancy,
        "room_type": room_data.get("location", "Unspecified") or "Unspecified",
    }

    weather_analyzer = WeatherAIAnalyzer()
    weather_data = weather_analyzer.get_weather_data()
    recommendations = weather_analyzer.generate_recommendations(
        room_data=ai_room_input,
        weather_data=weather_data,
        room_type=ai_room_input["room_type"],
    )

    if recommendations and "target_temperature" in recommendations:
        recommendations["target_temperature_celsius"] = recommendations[
            "target_temperature"
        ]
        recommendations["target_temperature"] = convert_temperature(
            recommendations["target_temperature"],
            "celsius",
            room_data["temperature_unit"],
        )

    room_data["current_status"] = "Normal"
    room_data["status_class"] = "text-green-400"
    if current_temp_for_ai > 24 or current_temp_for_ai < 18:
        room_data["current_status"] = "Warning"
        room_data["status_class"] = "text-orange-400"
    if current_temp_for_ai > 26 or current_temp_for_ai < 16:
        room_data["current_status"] = "Critical"
        room_data["status_class"] = "text-red-400"

    room_data["current_setpoint"] = 22.0

    return render_template(
        "components/room.html",
        active_page="dashboard",
        room=room_data,
        devices=devices_data,
        recommendations=recommendations,
        weather_data=weather_data,
        convert_temperature=convert_temperature,
        format_temperature=format_temperature,
    )


@app.post("/room/<int:room_id>/set_unit")
@login_required
def set_temperature_unit(room_id):
    unit = request.form.get("temperature_unit")
    user_id = session.get("user_id")

    if unit not in ["celsius", "fahrenheit", "kelvin"]:
        flash("Invalid temperature unit.", "error")
        return redirect(url_for("room", room_id=room_id))

    try:
        changed = update_room(room_id, temperature_unit=unit, user_id=user_id)
        if changed:
            flash(f"Temperature unit changed to {unit}.", "success")
        else:
            flash("Room not found or no changes applied.", "warning")
    except Exception as e:
        log.exception("Error changing temperature unit: %s", e)
        flash("Could not change temperature unit.", "error")

    return redirect(url_for("room", room_id=room_id))


@app.post("/room/<int:room_id>/apply_ai")
@login_required
def room_apply_ai(room_id):
    try:
        new_setpoint = request.form.get("new_setpoint", type=float)
        if new_setpoint:
            flash(
                f"New setpoint {new_setpoint}°C applied successfully via AI recommendation.",
                "success",
            )
        else:
            flash("Invalid temperature received.", "error")
    except Exception as e:
        log.exception("Error applying setpoint: %s", e)
        flash("Failed to apply setpoint.", "error")

    return redirect(url_for("room", room_id=room_id))


@app.route("/reports")
@login_required
def reports():
    user_id = session.get("user_id")
    user_role = session.get("role")
    rooms = []

    try:
        rooms = get_rooms_summary(user_id=user_id, user_role=user_role)
    except Exception as e:
        log.exception("[reports] error: %s", e)

    return render_template("reports.html", active_page="reports", rooms=rooms)


@app.route("/policies")
@login_required
def policies():
    user_id = session.get("user_id")
    user_role = session.get("role")
    rooms = []

    try:
        rooms = get_rooms_summary(user_id=user_id, user_role=user_role)
    except Exception as e:
        log.exception("[policies] error: %s", e)

    return render_template("policies.html", active_page="policies", rooms=rooms)


# =============================================================================
# ROOM MANAGEMENT ROUTES
# =============================================================================

@app.post("/setuprooms/create")
@login_required
def setuprooms_create():
    room_name = request.form.get("room_name", "").strip()
    room_location = (request.form.get("room_location") or "").strip() or None
    user_id = session.get("user_id")

    try:
        create_room(room_name, location=room_location, user_id=user_id)
        flash("Room added successfully!", "success")
    except ValueError as ve:
        flash(str(ve), "error")
    except Exception as e:
        log.exception("[setuprooms_create] error: %s", e)
        flash("Could not add room.", "error")

    return redirect(url_for("setup"))


@app.post("/setuprooms/<int:room_id>/delete")
@login_required
def setuprooms_delete(room_id):
    try:
        deleted = delete_room(room_id, user_id=session.get("user_id"))
        if deleted:
            flash("Room deleted.", "success")
        else:
            flash("Room not found.", "warning")
    except Exception as e:
        log.exception("[setuprooms_delete] error: %s", e)
        flash("Could not delete room.", "error")

    return redirect(url_for("setup"))


@app.post("/setuprooms/<int:room_id>/update")
@login_required
def setuprooms_update(room_id):
    name = request.form.get("room_name")
    location = request.form.get("room_location")

    try:
        changed = update_room(
            room_id, name=name, location=location, user_id=session.get("user_id")
        )
        if changed:
            flash("Room updated.", "success")
        else:
            flash("No changes applied.", "warning")
    except Exception as e:
        log.exception("[setuprooms_update] error: %s", e)
        flash("Could not update room.", "error")

    return redirect(url_for("setup"))


@app.post("/devices/add")
@login_required
def add_device():
    name = (request.form.get("name") or "").strip()
    device_uid = (request.form.get("device_uid") or "").strip()
    device_type = (request.form.get("type") or "").strip()
    status = (request.form.get("status") or "active").strip()
    room_id = request.form.get("room_id", type=int)

    errors = []
    if not room_id:
        errors.append("Room is required.")
    if not name:
        errors.append("Device name is required.")
    if not device_uid:
        errors.append("Device UID is required.")

    if errors:
        for e in errors:
            flash(e, "error")
        return redirect(url_for("setup"))

    cur = db_cursor()
    try:
        cur.execute(
            "INSERT INTO devices (room_id, name, device_uid, type, status) VALUES (%s, %s, %s, %s, %s)",
            (room_id, name, device_uid, device_type or None, status or "active"),
        )
        mysql.connection.commit()
        flash("Device added successfully.", "success")
    except IntegrityError as e:
        mysql.connection.rollback()
        log.exception("Add device integrity error: %s", e)
        flash("Could not add device: device UID must be unique.", "error")
    except Exception as e:
        mysql.connection.rollback()
        log.exception("Add device failed: %s", e)
        flash("Could not add device. Ensure the room exists.", "error")
    finally:
        try:
            cur.close()
        except Exception:
            pass

    return redirect(url_for("setup"))


# =============================================================================
# API ROUTES
# =============================================================================

@app.get("/api/rooms")
@login_required
def api_rooms():
    user_id = session.get("user_id")
    user_role = session.get("role")

    try:
        rows = get_rooms_summary(user_id=user_id, user_role=user_role)
        return jsonify(_jsonify_rows(rows))
    except Exception as e:
        log.exception("/api/rooms error: %s", e)
        return jsonify({"error": "Failed to load rooms"}), 500


@app.get("/api/readings")
@login_required
def api_readings():
    user_id = session.get("user_id")
    user_role = session.get("role")
    limit = request.args.get("limit", type=int, default=200)
    offset = request.args.get("offset", type=int, default=0)

    try:
        rows = get_recent_readings(limit=limit, offset=offset, user_id=user_id, user_role=user_role)
        return jsonify(_jsonify_rows(rows))
    except Exception as e:
        log.exception("/api/readings error: %s", e)
        return jsonify({"error": "Failed to load readings"}), 500


# =============================================================================
# ROOM CONDITION REQUEST ROUTES
# =============================================================================

@app.route("/room/<int:room_id>/request_adjustment", methods=["POST"])
@login_required
def request_room_adjustment(room_id):
    cursor = None
    try:
        if "user_id" not in session:
            return jsonify({"success": False, "error": "Not authenticated"}), 401

        data = request.form
        request_type = data.get("request_type")

        if not request_type:
            return jsonify({"success": False, "error": "Request type is required"}), 400

        # Get current room temperature
        cursor = mysql.connection.cursor()
        cursor.execute(
            """
            SELECT AVG(r.temperature) as avg_temp
            FROM readings r
                     JOIN devices d ON r.device_id = d.id
            WHERE d.room_id = %s
              AND r.temperature IS NOT NULL
            """,
            (room_id,),
        )

        result = cursor.fetchone()
        current_temp = 22.0
        if result and "avg_temp" in result and result["avg_temp"] is not None:
            current_temp = float(result["avg_temp"])

        # Prepare data for insertion
        target_temp = data.get("target_temp")
        fan_level = data.get("fan_level")
        user_notes = data.get("user_notes")

        # Validate temperature if it's a temperature change request
        if request_type == "temperature_change" and target_temp:
            try:
                target_temp = float(target_temp)
                if target_temp < 16 or target_temp > 28:
                    return jsonify({"success": False, "error": "Temperature must be between 16°C and 28°C"}), 400
            except ValueError:
                return jsonify({"success": False, "error": "Invalid temperature value"}), 400

        # Create request in database
        cursor.execute(
            """
            INSERT INTO room_condition_requests
            (room_id, user_id, request_type, current_temperature, target_temperature, fan_level_request,
             user_notes)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                room_id,
                session["user_id"],
                request_type,
                current_temp,
                target_temp,
                fan_level,
                user_notes,
            ),
        )

        request_id = cursor.lastrowid

        # Create notification for user
        cursor.execute(
            """
            INSERT INTO user_notifications (user_id, request_id, title, message, type)
            VALUES (%s, %s, %s, %s, 'info')
            """,
            (
                session["user_id"],
                request_id,
                "Request Submitted",
                f"Your {request_type.replace('_', ' ')} request has been submitted and is pending review.",
            ),
        )

        mysql.connection.commit()

        return jsonify({
            "success": True,
            "message": "Request submitted successfully",
            "request_id": request_id,
        })

    except Exception as e:
        log.error(f"Error in room adjustment request: {e}")
        if mysql.connection:
            mysql.connection.rollback()
        return jsonify({"success": False, "error": "Internal server error"}), 500
    finally:
        if cursor:
            cursor.close()


# =============================================================================
# NOTIFICATION ROUTES
# =============================================================================

@app.route("/notifications")
@login_required
def notifications():
    user_id = session.get("user_id")

    cursor = mysql.connection.cursor()
    try:
        cursor.execute(
            "SELECT COUNT(*) as count FROM room_condition_requests WHERE user_id = %s",
            (user_id,),
        )
        total_requests = cursor.fetchone()["count"]

        cursor.execute(
            "SELECT COUNT(*) as count FROM room_condition_requests WHERE user_id = %s AND status = 'pending'",
            (user_id,),
        )
        pending_requests = cursor.fetchone()["count"]

        cursor.execute(
            "SELECT COUNT(*) as count FROM room_condition_requests WHERE user_id = %s AND status = 'approved'",
            (user_id,),
        )
        approved_requests = cursor.fetchone()["count"]

        cursor.execute(
            "SELECT COUNT(*) as count FROM room_condition_requests WHERE user_id = %s AND status = 'denied'",
            (user_id,),
        )
        denied_requests = cursor.fetchone()["count"]

    except Exception as e:
        log.error(f"Error getting notification stats: {e}")
        total_requests = pending_requests = approved_requests = denied_requests = 0
    finally:
        cursor.close()

    return render_template(
        "notifications.html",
        active_page="notifications",
        total_requests=total_requests,
        pending_requests=pending_requests,
        approved_requests=approved_requests,
        denied_requests=denied_requests,
    )

@app.route("/api/user/notifications")
@login_required
def get_user_notifications():
    """Get all notifications for the current user"""
    cursor = mysql.connection.cursor()
    try:
        cursor.execute(
            """
            SELECT n.id,
                   n.title,
                   n.message,
                   n.type,
                   n.is_read,
                   n.created_at,
                   n.request_id,
                   r.status as request_status,
                   r.estimated_completion_time,
                   rm.name  as room_name
            FROM user_notifications n
                     LEFT JOIN room_condition_requests r ON n.request_id = r.id
                     LEFT JOIN rooms rm ON r.room_id = rm.id
            WHERE n.user_id = %s
            ORDER BY n.created_at DESC LIMIT 50
            """,
            (session["user_id"],),
        )

        notifications = []
        for row in cursor.fetchall():
            notifications.append(
                {
                    "id": row["id"],
                    "title": row["title"],
                    "message": row["message"],
                    "type": row["type"],
                    "is_read": bool(row["is_read"]),
                    "created_at": (
                        row["created_at"].isoformat() if row["created_at"] else None
                    ),
                    "request_id": row["request_id"],
                    "request_status": row["request_status"],
                    "estimated_completion": (
                        row["estimated_completion_time"].isoformat()
                        if row["estimated_completion_time"]
                        else None
                    ),
                    "room_name": row["room_name"],
                }
            )

        return jsonify(notifications)

    except Exception as e:
        log.error(f"Error in get_user_notifications: {e}")
        return jsonify([])
    finally:
        cursor.close()

@app.route("/api/user/notifications/<int:notification_id>/read", methods=["POST"])
@login_required
def mark_notification_read(notification_id):
    """Mark a single notification as read"""
    cursor = mysql.connection.cursor()
    try:
        cursor.execute(
            """
            UPDATE user_notifications
            SET is_read = TRUE
            WHERE id = %s
              AND user_id = %s
            """,
            (notification_id, session["user_id"]),
        )

        mysql.connection.commit()
        return jsonify({"success": True})
    except Exception as e:
        mysql.connection.rollback()
        log.error(f"Error marking notification as read: {e}")
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        cursor.close()

@app.route("/api/user/notifications/read-all", methods=["POST"])
@login_required
def mark_all_notifications_read():
    """Mark all notifications as read for the current user"""
    cursor = mysql.connection.cursor()
    try:
        cursor.execute(
            """
            UPDATE user_notifications
            SET is_read = TRUE
            WHERE user_id = %s
              AND is_read = FALSE
            """,
            (session["user_id"],),
        )

        mysql.connection.commit()
        return jsonify({"success": True})
    except Exception as e:
        mysql.connection.rollback()
        log.error(f"Error marking all notifications as read: {e}")
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        cursor.close()

@app.route("/api/user/notifications/unread-count")
@login_required
def get_unread_notification_count():
    """Get count of unread notifications for the bell"""
    cursor = mysql.connection.cursor()
    try:
        cursor.execute(
            """
            SELECT COUNT(*) as unread_count
            FROM user_notifications
            WHERE user_id = %s
              AND is_read = FALSE
            """,
            (session["user_id"],),
        )

        result = cursor.fetchone()
        return jsonify({"unread_count": result["unread_count"] if result else 0})
    except Exception as e:
        log.error(f"Error getting unread count: {e}")
        return jsonify({"unread_count": 0})
    finally:
        cursor.close()

# =============================================================================
# SETTINGS & USER MANAGEMENT ROUTES
# =============================================================================

@app.route("/settings")
@login_required
def settings():
    users = []

    if session.get("role") in ["admin", "technician"]:
        cur = db_cursor()
        if session.get("role") == "technician":
            cur.execute("SELECT id, username, email, role FROM users ORDER BY id ASC")
        else:
            cur.execute("SELECT id, username, email, role FROM users WHERE role != 'technician' ORDER BY id ASC")
        users = cur.fetchall()
        cur.close()

    return render_template(
        "settings.html",
        users=users,
        rooms=get_user_rooms(session["user_id"]),
        active_page="settings",
    )


# =============================================================================
# THEME MANAGEMENT
# =============================================================================

@app.context_processor
def inject_theme():
    return dict(current_theme=session.get("theme", "system"))


@app.route("/set-theme/<theme>")
@login_required
def set_theme(theme):
    if theme in ["light", "dark", "system"]:
        session["theme"] = theme
        flash(f"Theme changed to {theme} mode", "success")
    return redirect(request.referrer or url_for("dashboard"))


# =============================================================================
# APPLICATION ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    app.run(debug=True)