import os
import re
import logging
from decimal import Decimal
from functools import wraps
from datetime import datetime, date

from flask import (
    Flask, render_template, redirect, request, session, flash, url_for, jsonify
)
from flask_mysqldb import MySQL
from dotenv import load_dotenv, find_dotenv
from werkzeug.security import generate_password_hash, check_password_hash
from MySQLdb._exceptions import IntegrityError
from utils.weather_gemini import WeatherAIAnalyzer

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
    SESSION_TYPE="filesystem"
)

required_env_vars = ["MYSQL_HOST", "MYSQL_USER", "MYSQL_DB"]
if not all(app.config.get(k) for k in required_env_vars):
    missing = [k for k in required_env_vars if not app.config.get(k)]
    raise SystemExit(f"Missing required DB env vars: {', '.join(missing)}")

mysql = MySQL(app)
if ServerSession is not None:
    ServerSession(app)

# Constants & Validation
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
PWD_RE = re.compile(
    r"^(?=.*[A-Z])(?=.*\d)(?=.*[!@#$%^&*()_\-+\=\[\]{};:'\",.<>/?\\|`~]).{8,}$"
)


# Database Utilities
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


# Temperature Conversion Utilities
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

    if from_unit == 'fahrenheit':
        celsius = (value - 32) * 5 / 9
    elif from_unit == 'kelvin':
        celsius = value - 273.15
    else:
        celsius = value

    if to_unit == 'fahrenheit':
        return (celsius * 9 / 5) + 32
    elif to_unit == 'kelvin':
        return celsius + 273.15
    else:
        return celsius


def format_temperature(value, unit, decimals=1):
    if value is None:
        return "—"

    value = _ensure_numeric(value)
    symbols = {'celsius': '°C', 'fahrenheit': '°F', 'kelvin': 'K'}
    return f"{value:.{decimals}f}{symbols.get(unit, '°C')}"


# Data Access Functions
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


# Room Management Functions
def create_room(name, location=None, user_id=None, temperature_unit='celsius'):
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
            (name, location, user_id, temperature_unit)
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
            tuple(params)
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


# Authentication & Authorization
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get("user_id") is None:
            flash("Please log in to access this page.", "warning")
            return redirect(url_for("login"))
        return f(*args, **kwargs)

    return decorated_function


def is_admin(user_id):
    # Implement your admin check logic here
    # For now, let's assume user_id 1 is admin
    return user_id == 1


# Error Handlers
@app.after_request
def after_request(response):
    # Ensure API routes return JSON even on errors
    if request.path.startswith('/api/') or (request.path.startswith('/room/') and '/request_adjustment' in request.path):
        if response.status_code >= 400 and not response.is_json:
            # Convert HTML error pages to JSON for API routes
            data = {
                'success': False,
                'error': f'Request failed with status {response.status_code}',
                'status': response.status_code
            }
            response = jsonify(data)
            response.status_code = response.status_code
    return response


@app.errorhandler(404)
def not_found_error(error):
    if request.path.startswith('/api/'):
        return jsonify({'success': False, 'error': 'Endpoint not found'}), 404
    return error


@app.errorhandler(500)
def internal_error(error):
    if request.path.startswith('/api/') or (request.path.startswith('/room/') and '/request_adjustment' in request.path):
        return jsonify({'success': False, 'error': 'Internal server error'}), 500
    return error


# Route Handlers
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
                    "SELECT id, username, email, password FROM users WHERE LOWER(email)=%s LIMIT 1",
                    (ident_lc,),
                )
            else:
                cur.execute(
                    "SELECT id, username, email, password FROM users WHERE LOWER(username)=%s LIMIT 1",
                    (ident_lc,),
                )
            row = cur.fetchone()
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
        except Exception:
            ok = (pwd_hash == password)

        if not ok:
            flash("Incorrect username or password.", "error")
            return render_template("login.html")

        session["user_id"] = user_id
        session["username"] = row["username"]
        flash("Login successful!", "success")
        return redirect(url_for("dashboard"))

    return render_template("login.html")


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
            errors["password"] = "Password must be ≥ 8 chars, include one uppercase, one number, and one symbol."
        if not confirm:
            errors["confirmation"] = "Please confirm your password."
        elif password != confirm:
            errors["confirmation"] = "Passwords do not match."

        if errors:
            return render_template("register.html", errors=errors, values=values)

        cur = db_cursor()
        try:
            cur.execute("SELECT 1 FROM users WHERE LOWER(username)=%s LIMIT 1", (username_lc,))
            if cur.fetchone():
                errors["username"] = "This username is already taken."

            cur.execute("SELECT 1 FROM users WHERE LOWER(email)=%s LIMIT 1", (email_lc,))
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


# Main Application Routes
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


@app.route("/room/<int:room_id>")
@login_required
def room(room_id):
    user_id = session.get("user_id")

    try:
        room_data, devices_data = get_room_details(room_id, user_id=user_id)
    except Exception as e:
        log.exception("[room] error loading details for room %s: %s", room_id, e)
        flash("Could not load room details.", "error")
        return redirect(url_for("dashboard"))

    if not room_data:
        flash("Room not found or you do not have permission to view it.", "error")
        return redirect(url_for("dashboard"))

    room_data.setdefault('temperature_unit', 'celsius')

    current_temp = room_data.get('avg_temp', 21.0)
    current_humidity = room_data.get('avg_humidity', 50)
    occupancy = sum(1 for d in devices_data if d.get('motion_detected') == 1) if devices_data else 0

    if room_data['temperature_unit'] != 'celsius':
        current_temp_for_ai = convert_temperature(current_temp, room_data['temperature_unit'], 'celsius')
    else:
        current_temp_for_ai = _ensure_numeric(current_temp)

    ai_room_input = {
        'temperature': current_temp_for_ai,
        'humidity': current_humidity,
        'occupancy': occupancy,
        'room_type': room_data.get('location', 'Unspecified')
    }

    weather_analyzer = WeatherAIAnalyzer()
    weather_data = weather_analyzer.get_weather_data()
    recommendations = weather_analyzer.generate_recommendations(
        room_data=ai_room_input,
        weather_data=weather_data,
        room_type=ai_room_input['room_type']
    )

    if recommendations and 'target_temperature' in recommendations:
        recommendations['target_temperature_celsius'] = recommendations['target_temperature']
        recommendations['target_temperature'] = convert_temperature(
            recommendations['target_temperature'],
            'celsius',
            room_data['temperature_unit']
        )

    room_data['current_status'] = "Normal"
    room_data['status_class'] = "text-green-400"
    if current_temp_for_ai > 24 or current_temp_for_ai < 18:
        room_data['current_status'] = "Warning"
        room_data['status_class'] = "text-orange-400"
    if current_temp_for_ai > 26 or current_temp_for_ai < 16:
        room_data['current_status'] = "Critical"
        room_data['status_class'] = "text-red-400"

    room_data['current_setpoint'] = 22.0

    return render_template(
        "components/room.html",
        active_page="dashboard",
        room=room_data,
        devices=devices_data,
        recommendations=recommendations,
        weather_data=weather_data,
        convert_temperature=convert_temperature,
        format_temperature=format_temperature
    )


@app.post("/room/<int:room_id>/set_unit")
@login_required
def set_temperature_unit(room_id):
    unit = request.form.get("temperature_unit")
    user_id = session.get("user_id")

    if unit not in ['celsius', 'fahrenheit', 'kelvin']:
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
            flash(f"New setpoint {new_setpoint}°C applied successfully via AI recommendation.", "success")
        else:
            flash("Invalid temperature received.", "error")
    except Exception as e:
        log.exception("Error applying setpoint: %s", e)
        flash("Failed to apply setpoint.", "error")

    return redirect(url_for("room", room_id=room_id))


# Navigation Routes
@app.route("/setup", methods=["GET", "POST"])
@login_required
def setup():
    user_id = session.get("user_id")
    rooms = []

    try:
        rooms = get_rooms_summary(user_id=user_id)
    except Exception as e:
        log.exception("[setup] error: %s", e)

    return render_template("setup.html", active_page="setup", rooms=rooms)


@app.route("/reports")
@login_required
def reports():
    user_id = session.get("user_id")
    rooms = []

    try:
        rooms = get_rooms_summary(user_id=user_id)
    except Exception as e:
        log.exception("[reports] error: %s", e)

    return render_template("reports.html", active_page="reports", rooms=rooms)


@app.route("/policies")
@login_required
def policies():
    user_id = session.get("user_id")
    rooms = []

    try:
        rooms = get_rooms_summary(user_id=user_id)
    except Exception as e:
        log.exception("[policies] error: %s", e)

    return render_template("policies.html", active_page="policies", rooms=rooms)


@app.route("/settings")
@login_required
def settings():
    user_id = session.get("user_id")
    rooms = []

    try:
        rooms = get_rooms_summary(user_id=user_id)
    except Exception as e:
        log.exception("[settings] error: %s", e)

    return render_template("settings.html", active_page="settings", rooms=rooms)


# Room Management Routes
@app.post("/setuprooms/create")
@login_required
def setuprooms_create():
    room_name = request.form.get("room_name", "").strip()
    room_location = (request.form.get("room_location") or "").strip() or None

    try:
        create_room(room_name, location=room_location, user_id=session.get("user_id"))
        flash("Room added.", "success")
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
        changed = update_room(room_id, name=name, location=location, user_id=session.get("user_id"))
        if changed:
            flash("Room updated.", "success")
        else:
            flash("No changes applied.", "warning")
    except Exception as e:
        log.exception("[setuprooms_update] error: %s", e)
        flash("Could not update room.", "error")

    return redirect(url_for("setup"))


@app.post("/rooms/add")
@login_required
def rooms_add_alias():
    room_name = (request.form.get("name") or "").strip()
    room_location = (request.form.get("location") or "").strip() or None

    if not room_name:
        flash("Room name is required.", "error")
        return redirect(url_for("setup"))

    try:
        create_room(room_name, location=room_location, user_id=session.get("user_id"))
        flash("Room added.", "success")
    except Exception as e:
        log.exception("[rooms_add_alias] error: %s", e)
        flash("Could not add room.", "error")

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


# API Routes
@app.get("/api/rooms")
@login_required
def api_rooms():
    user_id = session.get("user_id")

    try:
        rows = get_rooms_summary(user_id=user_id)
        return jsonify(_jsonify_rows(rows))
    except Exception as e:
        log.exception("/api/rooms error: %s", e)
        return jsonify({"error": "Failed to load rooms"}), 500


@app.get("/api/readings")
@login_required
def api_readings():
    user_id = session.get("user_id")
    limit = request.args.get("limit", type=int, default=200)
    offset = request.args.get("offset", type=int, default=0)

    try:
        rows = get_recent_readings(limit=limit, offset=offset, user_id=user_id)
        return jsonify(_jsonify_rows(rows))
    except Exception as e:
        log.exception("/api/readings error: %s", e)
        return jsonify({"error": "Failed to load readings"}), 500


# Room Condition Request Routes
@app.route('/room/<int:room_id>/request_adjustment', methods=['POST'])
@login_required
def request_room_adjustment(room_id):
    cursor = None
    try:
        print(f"=== DEBUG: Starting room adjustment request ===")
        print(f"DEBUG: Room ID: {room_id}")
        print(f"DEBUG: User ID: {session.get('user_id')}")
        print(f"DEBUG: Session: {dict(session)}")

        if 'user_id' not in session:
            print("DEBUG: User not authenticated")
            return jsonify({'success': False, 'error': 'Not authenticated'}), 401

        data = request.form
        print(f"DEBUG: Form data: {dict(data)}")

        request_type = data.get('request_type')
        print(f"DEBUG: Request type: {request_type}")

        if not request_type:
            print("DEBUG: No request type provided")
            return jsonify({'success': False, 'error': 'Request type is required'}), 400

        # Get current room temperature with extensive debugging
        cursor = mysql.connection.cursor()
        print(f"DEBUG: Executing temperature query for room {room_id}")

        cursor.execute("""
                       SELECT AVG(r.temperature) as avg_temp
                       FROM readings r
                                JOIN devices d ON r.device_id = d.id
                       WHERE d.room_id = %s
                         AND r.temperature IS NOT NULL
                       """, (room_id,))

        result = cursor.fetchone()
        print(f"DEBUG: Temperature query result: {result}")
        print(f"DEBUG: Result type: {type(result)}")

        # FIX: Proper dictionary access
        current_temp = 22.0  # Default fallback
        if result and 'avg_temp' in result:
            temp_value = result['avg_temp']
            print(f"DEBUG: Raw temperature value: {temp_value}, type: {type(temp_value)}")
            if temp_value is not None:
                try:
                    current_temp = float(temp_value)
                    print(f"DEBUG: Converted temperature: {current_temp}")
                except (ValueError, TypeError) as e:
                    print(f"DEBUG: Temperature conversion error: {e}, using default")
            else:
                print("DEBUG: Temperature value is None, using default")
        else:
            print("DEBUG: No temperature result or missing key, using default")

        print(f"DEBUG: Final current temperature: {current_temp}")

        # Prepare data for insertion
        target_temp = data.get('target_temp')
        fan_level = data.get('fan_level')
        user_notes = data.get('user_notes')

        print(f"DEBUG: Target temp: {target_temp}, Fan level: {fan_level}, Notes: {user_notes}")

        # Validate temperature if it's a temperature change request
        if request_type == 'temperature_change' and target_temp:
            try:
                target_temp = float(target_temp)
                print(f"DEBUG: Validated target temperature: {target_temp}")
                # Validate temperature range (16-28°C)
                if target_temp < 16 or target_temp > 28:
                    print(f"DEBUG: Temperature out of range: {target_temp}")
                    return jsonify({'success': False, 'error': 'Temperature must be between 16°C and 28°C'}), 400
            except ValueError as e:
                print(f"DEBUG: Invalid temperature value: {target_temp}, Error: {e}")
                return jsonify({'success': False, 'error': 'Invalid temperature value'}), 400

        # Create request in database
        print("DEBUG: Attempting to insert into room_condition_requests")
        cursor.execute("""
                       INSERT INTO room_condition_requests
                       (room_id, user_id, request_type, current_temperature, target_temperature, fan_level_request,
                        user_notes)
                       VALUES (%s, %s, %s, %s, %s, %s, %s)
                       """, (
                           room_id,
                           session['user_id'],
                           request_type,
                           current_temp,
                           target_temp,
                           fan_level,
                           user_notes
                       ))

        request_id = cursor.lastrowid
        print(f"DEBUG: Request created with ID: {request_id}")

        # Create notification for user
        print("DEBUG: Creating user notification")
        cursor.execute("""
                       INSERT INTO user_notifications (user_id, request_id, title, message, type)
                       VALUES (%s, %s, %s, %s, 'info')
                       """, (
                           session['user_id'],
                           request_id,
                           "Request Submitted",
                           f"Your {request_type.replace('_', ' ')} request has been submitted and is pending review."
                       ))

        mysql.connection.commit()
        print("DEBUG: Database transaction committed successfully")

        response_data = {
            'success': True,
            'message': 'Request submitted successfully',
            'request_id': request_id
        }
        print(f"DEBUG: Returning success response: {response_data}")

        return jsonify(response_data)

    except Exception as e:
        print(f"=== DEBUG: ERROR OCCURRED ===")
        print(f"DEBUG: Error type: {type(e).__name__}")
        print(f"DEBUG: Error message: {str(e)}")
        import traceback
        print(f"DEBUG: Traceback: {traceback.format_exc()}")

        if mysql.connection:
            try:
                mysql.connection.rollback()
                print("DEBUG: Database transaction rolled back")
            except Exception as rollback_error:
                print(f"DEBUG: Rollback error: {rollback_error}")

        return jsonify({'success': False, 'error': 'Internal server error'}), 500

    finally:
        if cursor:
            try:
                cursor.close()
                print("DEBUG: Database cursor closed")
            except Exception as close_error:
                print(f"DEBUG: Cursor close error: {close_error}")

@app.route('/api/room/<int:room_id>/notifications')
@login_required
def get_room_notifications(room_id):
    if 'user_id' not in session:
        return jsonify([])

    cursor = mysql.connection.cursor()
    try:
        cursor.execute("""
            SELECT n.*, r.status as request_status, r.estimated_completion_time
            FROM user_notifications n
            LEFT JOIN room_condition_requests r ON n.request_id = r.id
            WHERE n.user_id = %s 
            ORDER BY n.created_at DESC
            LIMIT 10
        """, (session['user_id'],))

        notifications = []
        for row in cursor.fetchall():
            # FIX: Access by column names instead of indices
            notifications.append({
                'id': row['id'],
                'title': row['title'],
                'message': row['message'],
                'type': row['type'],
                'is_read': bool(row['is_read']),
                'created_at': row['created_at'].isoformat() if row['created_at'] else None,
                'estimated_completion': row['estimated_completion_time'].isoformat() if row['estimated_completion_time'] else None
            })

        return jsonify(notifications)

    except Exception as e:
        print(f"Error in get_room_notifications: {e}")
        import traceback
        traceback.print_exc()
        return jsonify([])
    finally:
        cursor.close()


# Admin Room Requests Routes
@app.route('/admin/room-requests')
@login_required
def admin_room_requests():
    if not is_admin(session['user_id']):
        flash('Access denied. Admin privileges required.', 'error')
        return redirect(url_for('dashboard'))

    cursor = mysql.connection.cursor()

    # Get counts for stats
    cursor.execute("SELECT COUNT(*) FROM room_condition_requests WHERE status = 'pending'")
    pending_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM room_condition_requests WHERE status = 'viewed'")
    viewed_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM room_condition_requests WHERE status = 'approved' AND DATE(created_at) = CURDATE()")
    approved_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM rooms")
    rooms_count = cursor.fetchone()[0]

    return render_template('admin_room_requests.html',
                         pending_count=pending_count,
                         viewed_count=viewed_count,
                         approved_count=approved_count,
                         rooms_count=rooms_count,
                         active_page='admin_room_requests')


@app.route('/api/admin/room-requests')
@login_required
def get_admin_room_requests():
    if not is_admin(session['user_id']):
        return jsonify([]), 403

    cursor = mysql.connection.cursor()
    cursor.execute("""
        SELECT r.*, u.username, rm.name as room_name
        FROM room_condition_requests r
        JOIN users u ON r.user_id = u.id
        JOIN rooms rm ON r.room_id = rm.id
        WHERE r.status IN ('pending', 'viewed')
        ORDER BY r.created_at DESC
    """)

    requests = []
    for row in cursor.fetchall():
        requests.append({
            'id': row[0],
            'room_id': row[1],
            'user_id': row[2],
            'request_type': row[3],
            'current_temperature': float(row[4]) if row[4] else None,
            'target_temperature': float(row[5]) if row[5] else None,
            'fan_level_request': row[6],
            'user_notes': row[7],
            'status': row[8],
            'estimated_completion_time': row[9].isoformat() if row[9] else None,
            'created_at': row[10].isoformat(),
            'username': row[12],
            'room_name': row[13]
        })

    return jsonify(requests)


@app.route('/api/admin/room-requests/<int:request_id>/view', methods=['POST'])
@login_required
def mark_request_viewed(request_id):
    if not is_admin(session['user_id']):
        return jsonify({'error': 'Unauthorized'}), 403

    cursor = mysql.connection.cursor()
    cursor.execute("""
        UPDATE room_condition_requests 
        SET status = 'viewed', updated_at = NOW() 
        WHERE id = %s
    """, (request_id,))

    # Create notification for user
    cursor.execute("SELECT user_id FROM room_condition_requests WHERE id = %s", (request_id,))
    result = cursor.fetchone()
    if result:
        user_id = result[0]
        cursor.execute("""
            INSERT INTO user_notifications (user_id, request_id, title, message, type)
            VALUES (%s, %s, 'Request Viewed', 'An admin is now reviewing your room adjustment request.', 'info')
        """, (user_id, request_id))

    mysql.connection.commit()
    return jsonify({'success': True})


@app.route('/api/admin/room-requests/<int:request_id>/approve', methods=['POST'])
@login_required
def approve_room_request(request_id):
    if not is_admin(session['user_id']):
        return jsonify({'error': 'Unauthorized'}), 403

    data = request.json
    cursor = mysql.connection.cursor()

    cursor.execute("""
        UPDATE room_condition_requests 
        SET status = 'approved', 
            estimated_completion_time = %s,
            updated_at = NOW()
        WHERE id = %s
    """, (data.get('estimated_completion_time'), request_id))

    # Get request details for notification
    cursor.execute("""
        SELECT r.user_id, r.request_type, r.room_id, r.target_temperature
        FROM room_condition_requests r WHERE id = %s
    """, (request_id,))
    req_data = cursor.fetchone()

    if req_data:
        # Create success notification for user
        completion_time = data.get('estimated_completion_time', 'soon')
        message = f"Your {req_data[1].replace('_', ' ')} request has been approved. "
        message += f"Estimated completion: {completion_time}"

        cursor.execute("""
            INSERT INTO user_notifications (user_id, request_id, title, message, type)
            VALUES (%s, %s, 'Request Approved', %s, 'success')
        """, (req_data[0], request_id, message))

        # Here you would integrate with your actual HVAC control system
        # apply_room_settings(req_data[2], req_data[1], req_data[3])

    mysql.connection.commit()
    return jsonify({'success': True})


@app.route('/api/admin/room-requests/<int:request_id>/deny', methods=['POST'])
@login_required
def deny_room_request(request_id):
    if not is_admin(session['user_id']):
        return jsonify({'error': 'Unauthorized'}), 403

    data = request.json
    cursor = mysql.connection.cursor()

    cursor.execute("""
        UPDATE room_condition_requests 
        SET status = 'denied', updated_at = NOW()
        WHERE id = %s
    """, (request_id,))

    # Get user ID for notification
    cursor.execute("SELECT user_id FROM room_condition_requests WHERE id = %s", (request_id,))
    result = cursor.fetchone()
    if result:
        user_id = result[0]
        reason = data.get('reason', 'No reason provided')
        cursor.execute("""
            INSERT INTO user_notifications (user_id, request_id, title, message, type)
            VALUES (%s, %s, 'Request Denied', %s, 'error')
        """, (user_id, request_id, f"Your request was denied. Reason: {reason}"))

    mysql.connection.commit()
    return jsonify({'success': True})


@app.route('/api/debug/room-request-test', methods=['POST'])
@login_required
def debug_room_request_test():
    """Debug endpoint to test room request functionality"""
    try:
        log.info("Debug endpoint called")
        data = request.form
        log.info(f"Debug form data: {dict(data)}")
        log.info(f"Session user_id: {session.get('user_id')}")

        # Just return success without database operations
        return jsonify({
            'success': True,
            'message': 'Debug test successful',
            'received_data': dict(data),
            'user_id': session.get('user_id')
        })
    except Exception as e:
        log.exception(f"Debug endpoint error: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/debug/simple-test', methods=['POST'])
@login_required
def debug_simple_test():
    """Simple test endpoint without database operations"""
    try:
        print("=== SIMPLE TEST ENDPOINT ===")
        print(f"Form data: {dict(request.form)}")
        print(f"User ID: {session.get('user_id')}")

        return jsonify({
            'success': True,
            'message': 'Simple test successful - no database operations',
            'received_data': dict(request.form),
            'user_id': session.get('user_id')
        })
    except Exception as e:
        print(f"Simple test error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/notifications')
    @login_required
    def notifications():
        user_id = session.get('user_id')

        # Get stats for the dashboard
        cursor = mysql.connection.cursor()

        # Total requests
        cursor.execute("""
                       SELECT COUNT(*)
                       FROM room_condition_requests
                       WHERE user_id = %s
                       """, (user_id,))
        total_requests = cursor.fetchone()['count(*)']

        # Pending requests
        cursor.execute("""
                       SELECT COUNT(*)
                       FROM room_condition_requests
                       WHERE user_id = %s
                         AND status = 'pending'
                       """, (user_id,))
        pending_requests = cursor.fetchone()['count(*)']

        # Approved requests
        cursor.execute("""
                       SELECT COUNT(*)
                       FROM room_condition_requests
                       WHERE user_id = %s
                         AND status = 'approved'
                       """, (user_id,))
        approved_requests = cursor.fetchone()['count(*)']

        # Denied requests
        cursor.execute("""
                       SELECT COUNT(*)
                       FROM room_condition_requests
                       WHERE user_id = %s
                         AND status = 'denied'
                       """, (user_id,))
        denied_requests = cursor.fetchone()['count(*)']

        cursor.close()

        return render_template(
            'notifications.html',
            active_page='notifications',
            total_requests=total_requests,
            pending_requests=pending_requests,
            approved_requests=approved_requests,
            denied_requests=denied_requests
        )


@app.route('/api/user/notifications')
@login_required
def get_user_notifications():
    """Get all notifications for the current user"""
    cursor = mysql.connection.cursor()
    try:
        cursor.execute("""
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
                       """, (session['user_id'],))

        notifications = []
        for row in cursor.fetchall():
            notifications.append({
                'id': row['id'],
                'title': row['title'],
                'message': row['message'],
                'type': row['type'],
                'is_read': bool(row['is_read']),
                'created_at': row['created_at'].isoformat() if row['created_at'] else None,
                'request_id': row['request_id'],
                'request_status': row['request_status'],
                'estimated_completion': row['estimated_completion_time'].isoformat() if row[
                    'estimated_completion_time'] else None,
                'room_name': row['room_name']
            })

        return jsonify(notifications)

    except Exception as e:
        print(f"Error in get_user_notifications: {e}")
        return jsonify([])
    finally:
        cursor.close()


@app.route('/api/user/notifications/<int:notification_id>/read', methods=['POST'])
@login_required
def mark_notification_read(notification_id):
    """Mark a single notification as read"""
    cursor = mysql.connection.cursor()
    try:
        cursor.execute("""
                       UPDATE user_notifications
                       SET is_read = TRUE
                       WHERE id = %s
                         AND user_id = %s
                       """, (notification_id, session['user_id']))

        mysql.connection.commit()
        return jsonify({'success': True})
    except Exception as e:
        mysql.connection.rollback()
        print(f"Error marking notification as read: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cursor.close()


@app.route('/api/user/notifications/read-all', methods=['POST'])
@login_required
def mark_all_notifications_read():
    """Mark all notifications as read for the current user"""
    cursor = mysql.connection.cursor()
    try:
        cursor.execute("""
                       UPDATE user_notifications
                       SET is_read = TRUE
                       WHERE user_id = %s
                         AND is_read = FALSE
                       """, (session['user_id'],))

        mysql.connection.commit()
        return jsonify({'success': True})
    except Exception as e:
        mysql.connection.rollback()
        print(f"Error marking all notifications as read: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cursor.close()


@app.route('/api/user/notifications/unread-count')
@login_required
def get_unread_notification_count():
    """Get count of unread notifications for the bell"""
    cursor = mysql.connection.cursor()
    try:
        cursor.execute("""
                       SELECT COUNT(*) as unread_count
                       FROM user_notifications
                       WHERE user_id = %s
                         AND is_read = FALSE
                       """, (session['user_id'],))

        result = cursor.fetchone()
        return jsonify({'unread_count': result['unread_count']})
    except Exception as e:
        print(f"Error getting unread count: {e}")
        return jsonify({'unread_count': 0})
    finally:
        cursor.close()


@app.route('/notifications')
@login_required
def notifications():
    user_id = session.get('user_id')

    # Get stats for the dashboard
    cursor = mysql.connection.cursor()

    try:
        # Total requests
        cursor.execute("""
                       SELECT COUNT(*) as count
                       FROM room_condition_requests
                       WHERE user_id = %s
                       """, (user_id,))
        total_requests = cursor.fetchone()['count']

        # Pending requests
        cursor.execute("""
                       SELECT COUNT(*) as count
                       FROM room_condition_requests
                       WHERE user_id = %s AND status = 'pending'
                       """, (user_id,))
        pending_requests = cursor.fetchone()['count']

        # Approved requests
        cursor.execute("""
                       SELECT COUNT(*) as count
                       FROM room_condition_requests
                       WHERE user_id = %s AND status = 'approved'
                       """, (user_id,))
        approved_requests = cursor.fetchone()['count']

        # Denied requests
        cursor.execute("""
                       SELECT COUNT(*) as count
                       FROM room_condition_requests
                       WHERE user_id = %s AND status = 'denied'
                       """, (user_id,))
        denied_requests = cursor.fetchone()['count']

    except Exception as e:
        print(f"Error getting notification stats: {e}")
        total_requests = pending_requests = approved_requests = denied_requests = 0
    finally:
        cursor.close()

    return render_template(
        'notifications.html',
        active_page='notifications',
        total_requests=total_requests,
        pending_requests=pending_requests,
        approved_requests=approved_requests,
        denied_requests=denied_requests
    )

# Theme Management
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


# Application Entry Point
if __name__ == "__main__":
    app.run(debug=True)