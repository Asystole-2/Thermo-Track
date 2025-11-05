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
                # If exactness matters, consider str(v) instead
                r[k] = float(v)
    return rows

def get_rooms_summary(user_id=None):
    """
    Returns one row per room with:
      - devices_count
      - devices_with_readings
      - avg_temp / avg_humidity from latest reading per device
      - last_update

    If user_id provided, aggregate using only readings for that user.
    """
    c = db_cursor()

    params = []
    # Latest-reading-per-device subquery, optionally filtered by user_id
    if user_id is not None:
        latest_subquery = """
            SELECT r.*
            FROM readings r
            JOIN (
                SELECT device_id, MAX(recorded_at) AS max_time
                FROM readings
                WHERE user_id = %s
                GROUP BY device_id
            ) m ON m.device_id = r.device_id AND m.max_time = r.recorded_at
            WHERE r.user_id = %s
        """
        params.extend([user_id, user_id])
    else:
        latest_subquery = """
            SELECT r.*
            FROM readings r
            JOIN (
                SELECT device_id, MAX(recorded_at) AS max_time
                FROM readings
                GROUP BY device_id
            ) m ON m.device_id = r.device_id AND m.max_time = r.recorded_at
        """

    query = f"""
        SELECT
            rm.id                                        AS id,
            rm.name                                      AS room_name,
            rm.location                                  AS location,
            COUNT(DISTINCT d.id)                         AS devices_count,
            COUNT(lr.id)                                 AS devices_with_readings,
            ROUND(AVG(lr.temperature), 1)                AS avg_temp,
            ROUND(AVG(lr.humidity), 1)                   AS avg_humidity,
            MAX(lr.recorded_at)                          AS last_update
        FROM rooms rm
        LEFT JOIN devices d ON d.room_id = rm.id
        LEFT JOIN (
            {latest_subquery}
        ) lr ON lr.device_id = d.id
        GROUP BY rm.id, rm.name, rm.location
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
    where_user = ""
    if user_id is not None:
        where_user = "WHERE r.user_id = %s"
        params.append(user_id)

    query = f"""
        SELECT
            r.id,
            r.device_id,
            r.temperature,
            r.humidity,
            r.pressure,
            r.recorded_at,
            d.name          AS device_name,
            d.device_uid    AS device_uid,
            d.type          AS device_type,
            rm.id           AS room_id,
            rm.name         AS room_name
        FROM readings r
        JOIN devices d ON d.id = r.device_id
        JOIN rooms rm   ON rm.id = d.room_id
        {where_user}
        ORDER BY r.recorded_at DESC
        LIMIT %s OFFSET %s
    """
    params.extend([limit, offset])

    c.execute(query, tuple(params))
    rows = c.fetchall()
    c.close()
    return rows

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
        rows=rows,   # ✅ provide for template’s “Recent Readings” table
    )

# -----------------------------------------------------------------------------
# Optional pages — feed them rooms as well (scoped)
# -----------------------------------------------------------------------------
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
