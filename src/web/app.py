import os
import re
from functools import wraps

from flask import (
    Flask, render_template, redirect, request, session, flash, url_for, jsonify
)
from flask_mysqldb import MySQL
from dotenv import load_dotenv, find_dotenv

try:
    from flask_session import Session as ServerSession
except ModuleNotFoundError:
    ServerSession = None

from werkzeug.security import generate_password_hash, check_password_hash
import MySQLdb
from MySQLdb._exceptions import IntegrityError

# -----------------------------------------------------------------------------
# App & Config
# -----------------------------------------------------------------------------
app = Flask(__name__, template_folder="templates", static_folder="static")
load_dotenv(find_dotenv())

app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-change-me")
app.config["MYSQL_HOST"] = os.environ.get("MYSQL_HOST", "127.0.0.1")
app.config["MYSQL_USER"] = os.environ.get("MYSQL_USER", "root")
app.config["MYSQL_PASSWORD"] = os.environ.get("MYSQL_PASSWORD", "")
app.config["MYSQL_DB"] = os.environ.get("MYSQL_DB", "thermotrack")
app.config["MYSQL_PORT"] = int(os.environ.get("PORT", "3306"))
# Return dict-like rows everywhere
app.config["MYSQL_CURSORCLASS"] = "DictCursor"

# Sessions
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
if ServerSession:
    ServerSession(app)

mysql = MySQL(app)

# -----------------------------------------------------------------------------
# Utilities
# -----------------------------------------------------------------------------
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
PWD_RE = re.compile(r"^(?=.*[A-Z])(?=.*\d)(?=.*[!@#$%^&*()_\-+=\[{\]};:'\",.<>/?\\|`~]).{8,}$")

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get("username") is None:
            flash("Please log in to access this page.", "warning")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function

def db_cursor():
    return mysql.connection.cursor()

def get_rooms_summary():
    """
    Returns one row per room with:
      - devices_count
      - devices_with_readings
      - avg_temp / avg_humidity from latest reading per device
      - last_update
    Works even if a room has 0 devices/readings.
    """
    c = db_cursor()
    c.execute("""
        SELECT
            rm.id                                        AS id,
            rm.name                                      AS room_name,
            rm.location                                   AS location,
            COUNT(DISTINCT d.id)                          AS devices_count,
            COUNT(lr.id)                                  AS devices_with_readings,
            ROUND(AVG(lr.temperature), 1)                 AS avg_temp,
            ROUND(AVG(lr.humidity), 1)                    AS avg_humidity,
            MAX(lr.recorded_at)                           AS last_update
        FROM rooms rm
        LEFT JOIN devices d ON d.room_id = rm.id
        LEFT JOIN (
            SELECT r.*
            FROM readings r
            JOIN (
                SELECT device_id, MAX(recorded_at) AS max_time
                FROM readings
                GROUP BY device_id
            ) m ON m.device_id = r.device_id AND m.max_time = r.recorded_at
        ) lr ON lr.device_id = d.id
        GROUP BY rm.id, rm.name, rm.location
        ORDER BY rm.name
    """)
    rows = c.fetchall()
    c.close()
    return rows

# -----------------------------------------------------------------------------
# Routes: Landing & Auth
# -----------------------------------------------------------------------------
@app.route("/")
def index():
    if session.get("username"):
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
        except Exception:
            mysql.connection.rollback()
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
            ok = (pwd_hash == password)  # fallback only for legacy plaintext

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
            flash("Database error during registration.", "error")
            return render_template("register.html", values=values)

        except Exception as e:
            mysql.connection.rollback()
            flash(f"Unexpected error during registration: {e}", "error")
            return render_template("register.html", values=values)

        finally:
            cur.close()

    return render_template("register.html")

# -----------------------------------------------------------------------------
# Dashboard (Rooms + latest conditions)
# -----------------------------------------------------------------------------
@app.route("/dashboard")
@login_required
def dashboard():
    rooms = []
    try:
        rooms = get_rooms_summary()
    except Exception as e:
        # Keep the page loading; show toast in UI if you handle flashes
        print(f"[dashboard] error: {e}")
        flash("Could not load room data.", "error")
    return render_template("dashboard.html", active_page="dashboard", rooms=rooms)

# -----------------------------------------------------------------------------
# Optional pages — feed them rooms as well (non-blocking)
# -----------------------------------------------------------------------------
@app.route("/setup", methods=["GET", "POST"])
@login_required
def setup():
    rooms = []
    try:
        rooms = get_rooms_summary()
    except Exception as e:
        print(f"[setup] error: {e}")
    return render_template("setup.html", active_page="setup", rooms=rooms)

@app.route("/reports")
@login_required
def reports():
    rooms = []
    try:
        rooms = get_rooms_summary()
    except Exception as e:
        print(f"[reports] error: {e}")
    return render_template("reports.html", active_page="reports", rooms=rooms)

@app.route("/policies")
@login_required
def policies():
    rooms = []
    try:
        rooms = get_rooms_summary()
    except Exception as e:
        print(f"[policies] error: {e}")
    return render_template("policies.html", active_page="policies", rooms=rooms)

@app.route("/settings")
@login_required
def settings():
    rooms = []
    try:
        rooms = get_rooms_summary()
    except Exception as e:
        print(f"[settings] error: {e}")
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
# Debug/utility APIs (optional)
# -----------------------------------------------------------------------------
@app.get("/api/rooms")
@login_required
def api_rooms():
    try:
        return jsonify(get_rooms_summary())
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.get("/api/readings")
@login_required
def api_readings():
    c = db_cursor()
    c.execute("SELECT * FROM readings ORDER BY recorded_at DESC LIMIT 200")
    data = c.fetchall()
    c.close()
    return jsonify(data)

# -----------------------------------------------------------------------------
# Entrypoint
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    if not all([app.config["MYSQL_HOST"], app.config["MYSQL_USER"], app.config["MYSQL_DB"]]):
        print("\n!!! ERROR: Database environment variables are not set. !!!")
        raise SystemExit(1)
    app.run(debug=True)
