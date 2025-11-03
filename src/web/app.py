import os
import re
from flask import Flask, render_template, redirect, request, session, flash, url_for
from flask_mysqldb import MySQL
from dotenv import load_dotenv, find_dotenv
from functools import wraps
from utils.weather_gemini import WeatherAIAnalyzer

try:
    from flask_session import Session as ServerSession
except ModuleNotFoundError:
    ServerSession = None

from werkzeug.security import generate_password_hash, check_password_hash
import MySQLdb
from MySQLdb import IntegrityError

# App & Config
app = Flask(__name__)

load_dotenv(find_dotenv())

app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-change-me")
app.config["MYSQL_HOST"] = os.environ.get("MYSQL_HOST")
app.config["MYSQL_USER"] = os.environ.get("MYSQL_USER")
app.config["MYSQL_PASSWORD"] = os.environ.get("MYSQL_PASSWORD")
app.config["MYSQL_DB"] = os.environ.get("MYSQL_DB")

mysql = MySQL(app)

app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
if ServerSession:
    ServerSession(app)

# Regex (REGISTER only)
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
PWD_RE = re.compile(
    r"^(?=.*[A-Z])(?=.*\d)(?=.*[!@#$%^&*()_\-+=\[{\]};:'\",.<>/?\\|`~]).{8,}$"
)


# Authentication Decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get("username") is None:
            flash("Please log in to access this page.", "warning")
            return redirect(url_for("login"))
        return f(*args, **kwargs)

    return decorated_function


# Routes
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
            cur = mysql.connection.cursor()
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

        user_id, username_db, email_db, pwd_hash = row

        try:
            ok = check_password_hash(pwd_hash, password)
        except Exception:
            ok = pwd_hash == password  # Fallback for old/bad hashes

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
    return redirect("/")


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

        # Field validation
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

        cur = mysql.connection.cursor()
        try:
            # Uniqueness checks
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

            # Insert new user
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


def get_user_rooms(user_id):
    """Utility function to fetch all rooms for the logged-in user."""
    rooms = []
    if user_id is None:
        return rooms

    cur = mysql.connection.cursor()
    try:
        cur.execute(
            "SELECT id, room_name, bms_zone_id, default_setpoint FROM rooms WHERE user_id=%s ORDER BY room_name ASC",
            (user_id,),
        )
        rooms_tuple = cur.fetchall()

        # Convert tuples to list of dictionaries
        column_names = [desc[0] for desc in cur.description]
        rooms = [dict(zip(column_names, row)) for row in rooms_tuple]

    except Exception as e:
        # In a production app, you would log this error more formally
        print(f"Error fetching rooms: {e}")
        flash("Could not load room data.", "error")
    finally:
        cur.close()

    return rooms


@app.route("/dashboard")
@login_required
def dashboard():
    user_id = session.get("user_id")
    rooms = get_user_rooms(user_id)
    return render_template("dashboard.html", active_page="dashboard", rooms=rooms)


@app.route("/setup", methods=["GET", "POST"])
@login_required
def setup():
    user_id = session.get("user_id")
    errors = {}
    values = {}

    if request.method == "POST":
        room_name = (request.form.get("room_name") or "").strip()
        bms_zone_id = (request.form.get("bms_zone_id") or "").strip()
        default_setpoint = request.form.get("default_setpoint")

        try:
            default_setpoint = float(default_setpoint)
            if not (15.0 <= default_setpoint <= 30.0):
                errors["default_setpoint"] = (
                    "Setpoint must be between 15.0 and 30.0 °C."
                )
        except (ValueError, TypeError):
            errors["default_setpoint"] = "Invalid setpoint value."

        if not room_name:
            errors["room_name"] = "Room Name is required."
        if not bms_zone_id:
            errors["bms_zone_id"] = "BMS Zone ID is required."

        values = {
            "room_name": room_name,
            "bms_zone_id": bms_zone_id,
            "default_setpoint": default_setpoint,
        }

        if not errors:
            cur = mysql.connection.cursor()
            try:
                cur.execute(
                    "INSERT INTO rooms (user_id, room_name, bms_zone_id, default_setpoint) VALUES (%s, %s, %s, %s)",
                    (user_id, room_name, bms_zone_id, default_setpoint),
                )
                mysql.connection.commit()
                flash(
                    f"Room '{room_name}' added successfully! (Zone ID: {bms_zone_id})",
                    "success",
                )
                values = {}

            except IntegrityError:
                mysql.connection.rollback()
                flash(
                    "A room with that name or zone ID already exists for your account.",
                    "error",
                )
            except Exception as e:
                mysql.connection.rollback()
                print(f"Room insertion error: {e}")
                flash(f"Unexpected error while adding room.", "error")
            finally:
                cur.close()

    # Re-fetch rooms after a POST or for a GET request
    rooms = get_user_rooms(user_id)

    return render_template(
        "setup.html", active_page="setup", rooms=rooms, errors=errors, values=values
    )


@app.route("/reports")
@login_required
def reports():
    user_id = session.get("user_id")
    rooms = get_user_rooms(user_id)
    return render_template("reports.html", active_page="reports", rooms=rooms)


@app.route("/policies")
@login_required
def policies():
    user_id = session.get("user_id")
    rooms = get_user_rooms(user_id)
    return render_template("policies.html", active_page="policies", rooms=rooms)


@app.route("/settings")
@login_required
def settings():
    user_id = session.get("user_id")
    rooms = get_user_rooms(user_id)
    return render_template("settings.html", active_page="settings", rooms=rooms)

@app.context_processor
def inject_theme():
    """Inject theme preference into all templates"""
    theme = session.get('theme', 'system')
    return dict(current_theme=theme)

@app.route('/set-theme/<theme>')
@login_required
def set_theme(theme):
    """Set user's theme preference"""
    if theme in ['light', 'dark', 'system']:
        session['theme'] = theme
        flash(f'Themed changed to {theme} mode', 'success')
    return redirect(request.referrer or url_for('dashboard'))

@app.route('/ai-recommendations')
@login_required
def ai_recommendations():
    """Get AI-powered HVAC recommendations"""
    user_id = session.get('user_id')

    # Get room data
    room_data = get_current_room_data(user_id)

    # Initialize AI analyzer
    analyzer = WeatherAIAnalyzer()

    # Get weather data
    weather_data = analyzer.get_weather_data()

    # Generate AI recommendations
    recommendations = analyzer.generate_recommendations(room_data, weather_data)

    return render_template('ai_recommendations.html',
                           active_page='ai_recommendations',
                           room_data=room_data,
                           weather_data=weather_data,
                           recommendations=recommendations,
                           rooms=get_user_rooms(user_id))


def get_current_room_data(user_id):
    """Get current room sensor data """
    # This is a placeholder
    return {
        'temperature': 22.5,  # From DHT22 sensor
        'humidity': 65,  # From DHT22 sensor
        'occupancy': 3,  # From PIR sensor or manual input
        'room_type': 'office'
    }

if __name__ == "__main__":
    if not all(
        [app.config["MYSQL_HOST"], app.config["MYSQL_USER"], app.config["MYSQL_DB"]]
    ):
        print("\n!!! ERROR: Database environment variables are not set. !!!")
        raise SystemExit(1)

    app.run(debug=True)
