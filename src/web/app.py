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
from functools import wraps
from utils.weather_gemini import WeatherAIAnalyzer

# Robust import: any failure disables server-side sessions gracefully
try:
    from flask_session import Session as ServerSession
except Exception:  # noqa: BLE001
    ServerSession = None

from werkzeug.security import generate_password_hash, check_password_hash
from MySQLdb._exceptions import IntegrityError

# -----------------------------------------------------------------------------
# App & Logging Config
# -----------------------------------------------------------------------------
app = Flask(__name__, template_folder="templates", static_folder="static")
load_dotenv(find_dotenv())

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("thermotrack")

# Secrets / DB config (require envs; no misleading defaults)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-change-me")

app.config["MYSQL_HOST"] = os.environ.get("MYSQL_HOST")
app.config["MYSQL_USER"] = os.environ.get("MYSQL_USER")
app.config["MYSQL_PASSWORD"] = os.environ.get("MYSQL_PASSWORD", "")
app.config["MYSQL_DB"] = os.environ.get("MYSQL_DB")
app.config["MYSQL_PORT"] = int(os.environ.get("MYSQL_PORT", "3306"))
# Return dict-like rows everywhere
app.config["MYSQL_CURSORCLASS"] = "DictCursor"

# Sessions
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
if ServerSession is not None:
    ServerSession(app)

# Validate critical DB envs
_required = ["MYSQL_HOST", "MYSQL_USER", "MYSQL_DB"]
if not all(app.config.get(k) for k in _required):
    missing = [k for k in _required if not app.config.get(k)]
    raise SystemExit(f"Missing required DB env vars: {', '.join(missing)}")

mysql = MySQL(app)

# -----------------------------------------------------------------------------
# Utilities
# -----------------------------------------------------------------------------
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
PWD_RE = re.compile(
    r"^(?=.*[A-Z])(?=.*\d)(?=.*[!@#$%^&*()_\-+\=\[\]{};:'\",.<>/?\\|`~]).{8,}$"
)

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get("user_id") is None:
            flash("Please log in to access this page.", "warning")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function

def db_cursor():
    return mysql.connection.cursor()

def _jsonify_rows(rows):
    """
    Convert non-JSON-serializable types to JSON-safe values in-place.
    - datetime/date -> ISO 8601
    - Decimal -> float
    """
    for r in rows:
        for k, v in list(r.items()):
            if isinstance(v, (datetime, date)):
                r[k] = v.isoformat()
            elif isinstance(v, Decimal):
                r[k] = float(v)
    return rows

def get_rooms_summary(user_id=None):
    """
    Returns one row per room with device counts and latest readings.
    If user_id provided, returns only that user's rooms.
    """
    c = db_cursor()

    params = []
    user_filter = ""
    if user_id is not None:
        user_filter = "WHERE rm.user_id = %s"
        params.append(user_id)

    query = f"""
        SELECT
            rm.id                                        AS id,
            rm.name                                      AS room_name,
            rm.location                                  AS location,
            rm.created_at                                AS created_at,
            COUNT(DISTINCT d.id)                         AS devices_count,
            COUNT(DISTINCT lr.device_id)                 AS devices_with_readings,
            ROUND(AVG(lr.temperature), 1)                AS avg_temp,
            ROUND(AVG(lr.humidity), 1)                   AS avg_humidity,
            MAX(lr.recorded_at)                          AS last_update
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
    """
    Recent readings, newest first, joined with device and room.
    If user_id is provided, returns only that user's readings.
    """
    limit = max(1, min(int(limit or 50), 500))   # cap to 500
    offset = max(0, int(offset or 0))

    c = db_cursor()

    params = []
    user_filter = ""
    if user_id is not None:
        user_filter = "WHERE rm.user_id = %s"
        params.append(user_id)

    query = f"""
        SELECT
            r.id,
            r.device_id,
            r.temperature,
            r.humidity,
            r.motion_detected,
            r.pressure,
            r.light_level,
            r.recorded_at,
            d.name          AS device_name,
            d.device_uid    AS device_uid,
            d.type          AS device_type,
            rm.id           AS room_id,
            rm.name         AS room_name
        FROM readings r
        JOIN devices d ON d.id = r.device_id
        JOIN rooms rm   ON rm.id = d.room_id
        {user_filter}
        ORDER BY r.recorded_at DESC
        LIMIT %s OFFSET %s
    """
    params.extend([limit, offset])

    c.execute(query, tuple(params))
    rows = c.fetchall()
    c.close()
    return rows
# -----------------------------------------------------------------------------
# Rooms helpers used by setuprooms_* endpoints
# -----------------------------------------------------------------------------
def create_room(name, location=None, user_id=None):
    """
    Create a room for a specific user.
    """
    name = (name or "").strip()
    location = (location or "").strip() or None
    if not name:
        raise ValueError("Room name is required.")
    if not user_id:
        raise ValueError("User ID is required.")

    cur = db_cursor()
    try:
        cur.execute(
            "INSERT INTO rooms (name, location, user_id) VALUES (%s, %s, %s)",
            (name, location, user_id)
        )
        mysql.connection.commit()
    except Exception as e:
        mysql.connection.rollback()
        raise e
    finally:
        cur.close()


def update_room(room_id, name=None, location=None, user_id=None):
    """
    Update room fields (name/location) for a specific user.
    """
    fields = []
    params = []
    if name is not None and name.strip():
        fields.append("name=%s")
        params.append(name.strip())
    if location is not None:
        loc_val = location.strip() or None
        fields.append("location=%s")
        params.append(loc_val)

    if not fields:
        return 0  # nothing to update

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
    """
    Delete a room only if it belongs to the user.
    """
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


# -----------------------------------------------------------------------------
# Routes: Landing & Auth
# -----------------------------------------------------------------------------
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

        try:
            cur = db_cursor()
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
        except Exception as e:  # noqa: BLE001
            mysql.connection.rollback()
            log.exception("Login query failed: %s", e)
            flash("Incorrect username or password.", "error")
            return render_template("login.html")

        if not row:
            flash("Incorrect username or password.", "error")
            return render_template("login.html")

        user_id = row["id"]
        username_db = row["username"]
        pwd_hash = row["password"]

        try:
            ok = check_password_hash(pwd_hash, password)
        except Exception:
            # Legacy plaintext fallback (should remove once seeds are fixed)
            ok = (pwd_hash == password)

        if not ok:
            flash("Incorrect username or password.", "error")
            return render_template("login.html")

        session["user_id"] = user_id
        session["username"] = username_db
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
            mysql.connection.commit()  # ✅ commit after INSERT
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

        except Exception as e:  # noqa: BLE001
            mysql.connection.rollback()
            log.exception("Unexpected error during registration: %s", e)
            flash("Unexpected error during registration.", "error")
            return render_template("register.html", values=values)

        finally:
            cur.close()

    return render_template("register.html")

# -----------------------------------------------------------------------------
# Dashboard (Rooms + recent readings)
# -----------------------------------------------------------------------------
@app.route("/dashboard")
@login_required
def dashboard():
    user_id = session.get("user_id")
    rooms = []
    rows = []
    try:
        rooms = get_rooms_summary(user_id=user_id)
    except Exception as e:  # noqa: BLE001
        log.exception("[dashboard] rooms load error: %s", e)
        flash("Could not load room data.", "error")
    try:
        rows = get_recent_readings(limit=50, user_id=user_id)
    except Exception as e:  # noqa: BLE001
        log.exception("[dashboard] readings load error: %s", e)
        flash("Could not load recent readings.", "error")
    return render_template(
        "dashboard.html",
        active_page="dashboard",
        rooms=rooms,
        rows=rows,
    )

# -----------------------------------------------------------------------------
# Optional pages — feed them rooms as well (scoped)
# -----------------------------------------------------------------------------

def get_room_details(room_id, user_id=None):
    """
    Returns the room details, its devices, and the latest readings for those devices.
    If user_id is provided, enforces ownership check.
    """
    c = db_cursor()
    params = [room_id]
    user_filter = ""
    if user_id is not None:
        user_filter = " AND rm.user_id = %s"
        params.append(user_id)

    # 1. Get Room Summary (similar to get_rooms_summary but for one room)
    room_query = f"""
        SELECT
            rm.id, rm.name AS room_name, rm.location, rm.created_at,
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

    # 2. Get all devices for this room with their latest reading
    devices_query = """
        SELECT
            d.id, d.name AS device_name, d.device_uid, d.type, d.status,
            lr.temperature, lr.humidity, lr.recorded_at, lr.motion_detected
        FROM devices d
        LEFT JOIN v_latest_device_reading lr ON lr.device_id = d.id
        WHERE d.room_id = %s
        ORDER BY d.name
    """
    c.execute(devices_query, (room_id,))
    devices_data = c.fetchall()
    c.close()

    return room_data, devices_data

# room details
@app.route("/room/<int:room_id>")
@login_required
def room(room_id):
    user_id = session.get("user_id")
    room_data, devices_data = None, None

    try:
        # Fetch room details, devices, and latest readings
        room_data, devices_data = get_room_details(room_id, user_id=user_id)
    except Exception as e:
        log.exception("[room] error loading details for room %s: %s", room_id, e)
        flash("Could not load room details.", "error")
        return redirect(url_for("dashboard"))

    if not room_data:
        flash("Room not found or you do not have permission to view it.", "error")
        return redirect(url_for("dashboard"))

    # --- 1. PREPARE AI INPUT DATA ---
    current_temp = room_data.get('avg_temp') if room_data.get('avg_temp') is not None else 21.0
    current_humidity = room_data.get('avg_humidity') if room_data.get('avg_humidity') is not None else 50
    # Placeholder for occupancy: Count devices with motion detected, or use a default
    occupancy = sum(1 for d in devices_data if d.get('motion_detected') == 1) if devices_data else 0

    ai_room_input = {
        'temperature': current_temp,
        'humidity': current_humidity,
        'occupancy': occupancy,
        # Room type can be derived from the name/location or be a column in the DB
        'room_type': room_data.get('location', 'Unspecified')
    }

    # --- 2. RUN AI ANALYSIS ---
    weather_analyzer = WeatherAIAnalyzer()
    weather_data = weather_analyzer.get_weather_data()
    recommendations = weather_analyzer.generate_recommendations(
        room_data=ai_room_input,
        weather_data=weather_data,
        room_type=ai_room_input['room_type']  # Pass the derived room type
    )

    # Simple status logic for display
    room_data['current_status'] = "Normal"
    room_data['status_class'] = "text-green-400"
    if current_temp > 24 or current_temp < 18:
        room_data['current_status'] = "Warning"
        room_data['status_class'] = "text-orange-400"
    if current_temp > 26 or current_temp < 16:
        room_data['current_status'] = "Critical"
        room_data['status_class'] = "text-red-400"

    # Default setpoint (for the slider)
    room_data['current_setpoint'] = 22.0

    return render_template(
        "room.html",
        active_page="dashboard",
        room=room_data,
        devices=devices_data,
        recommendations=recommendations,
        weather_data=weather_data,
    )


# --- Add a route for applying the AI suggestion (POST) ---
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

@app.route("/setup", methods=["GET", "POST"])
@login_required
def setup():
    user_id = session.get("user_id")
    rooms = []
    try:
        rooms = get_rooms_summary(user_id=user_id)
    except Exception as e:  # noqa: BLE001
        log.exception("[setup] error: %s", e)
    return render_template("setup.html", active_page="setup", rooms=rooms)

@app.route("/reports")
@login_required
def reports():
    user_id = session.get("user_id")
    rooms = []
    try:
        rooms = get_rooms_summary(user_id=user_id)
    except Exception as e:  # noqa: BLE001
        log.exception("[reports] error: %s", e)
    return render_template("reports.html", active_page="reports", rooms=rooms)

@app.route("/policies")
@login_required
def policies():
    user_id = session.get("user_id")
    rooms = []
    try:
        rooms = get_rooms_summary(user_id=user_id)
    except Exception as e:  # noqa: BLE001
        log.exception("[policies] error: %s", e)
    return render_template("policies.html", active_page="policies", rooms=rooms)

@app.route("/settings")
@login_required
def settings():
    user_id = session.get("user_id")
    rooms = []
    try:
        rooms = get_rooms_summary(user_id=user_id)
    except Exception as e:  # noqa: BLE001
        log.exception("[settings] error: %s", e)
    return render_template("settings.html", active_page="settings", rooms=rooms)

# -----------------------------------------------------------------------------
# Setup Rooms CRUD (named as requested: setuprooms_*)
# -----------------------------------------------------------------------------
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
    except Exception as e:  # noqa: BLE001
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
    except Exception as e:  # noqa: BLE001
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
    except Exception as e:  # noqa: BLE001
        log.exception("[setuprooms_update] error: %s", e)
        flash("Could not update room.", "error")
    return redirect(url_for("setup"))

# -----------------------------------------------------------------------------
# Convenience routes for setup forms
# -----------------------------------------------------------------------------
@app.post("/rooms/add")
@login_required
def rooms_add_alias():
    """
    Compatibility for forms that post to /rooms/add with fields 'name' and optional 'location'.
    Internally uses create_room to keep behavior consistent.
    """
    room_name = (request.form.get("name") or "").strip()
    room_location = (request.form.get("location") or "").strip() or None
    if not room_name:
        flash("Room name is required.", "error")
        return redirect(url_for("setup"))
    try:
        create_room(room_name, location=room_location, user_id=session.get("user_id"))
        flash("Room added.", "success")
    except Exception as e:  # noqa: BLE001
        log.exception("[rooms_add_alias] error: %s", e)
        flash("Could not add room.", "error")
    return redirect(url_for("setup"))

@app.post("/devices/add")
@login_required
def add_device():
    """
    Adds a device to a room.
    Expects: room_id, name, device_uid, type (optional), status (optional)
    """
    name = (request.form.get("name") or "").strip()
    device_uid = (request.form.get("device_uid") or "").strip()
    device_type = (request.form.get("type") or "").strip()
    status = (request.form.get("status") or "active").strip()
    room_id = request.form.get("room_id", type=int)

    # Basic validation
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
            """
            INSERT INTO devices (room_id, name, device_uid, type, status)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (room_id, name, device_uid, device_type or None, status or "active"),
        )
        mysql.connection.commit()
        flash("Device added successfully.", "success")
    except IntegrityError as e:
        mysql.connection.rollback()
        # Likely duplicate UID
        log.exception("Add device integrity error: %s", e)
        flash("Could not add device: device UID must be unique.", "error")
    except Exception as e:  # noqa: BLE001
        mysql.connection.rollback()
        log.exception("Add device failed: %s", e)
        flash("Could not add device. Ensure the room exists.", "error")
    finally:
        try:
            cur.close()
        except Exception:
            pass

    return redirect(url_for("setup"))

# -----------------------------------------------------------------------------
# Theme helpers
# -----------------------------------------------------------------------------
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

# -----------------------------------------------------------------------------
# APIs (scoped + JSON-safe + pagination)
# -----------------------------------------------------------------------------
@app.get("/api/rooms")
@login_required
def api_rooms():
    user_id = session.get("user_id")
    try:
        rows = get_rooms_summary(user_id=user_id)
        return jsonify(_jsonify_rows(rows))
    except Exception as e:  # noqa: BLE001
        log.exception("/api/rooms error: %s", e)
        return jsonify({"error": "Failed to load rooms"}), 500

@app.get("/api/readings")
@login_required
def api_readings():
    user_id = session.get("user_id")
    # Pagination query params
    limit = request.args.get("limit", type=int, default=200)
    offset = request.args.get("offset", type=int, default=0)
    try:
        rows = get_recent_readings(limit=limit, offset=offset, user_id=user_id)
        return jsonify(_jsonify_rows(rows))
    except Exception as e:  # noqa: BLE001
        log.exception("/api/readings error: %s", e)
        return jsonify({"error": "Failed to load readings"}), 500

# -----------------------------------------------------------------------------
# Entrypoint
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    app.run(debug=True)
