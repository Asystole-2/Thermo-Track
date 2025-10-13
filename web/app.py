import os
import re
from flask import Flask, render_template, redirect, request, session, flash, url_for
from flask_mysqldb import MySQL
from dotenv import load_dotenv, find_dotenv

try:
    from flask_session import Session as ServerSession
except ModuleNotFoundError:
    ServerSession = None

from werkzeug.security import generate_password_hash, check_password_hash

# Add MySQLdb to catch IntegrityError (duplicate key) cleanly
import MySQLdb
from MySQLdb import IntegrityError

# ---------------------------
# App & Config
# ---------------------------
app = Flask(__name__)

# Load .env
_ = load_dotenv(find_dotenv())

# Secret key for sessions
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-change-me")

# MySQL config from .env
app.config["MYSQL_HOST"] = os.environ.get("MYSQL_HOST")
app.config["MYSQL_USER"] = os.environ.get("MYSQL_USER")
app.config["MYSQL_PASSWORD"] = os.environ.get("MYSQL_PASSWORD")
app.config["MYSQL_DB"] = os.environ.get("MYSQL_DB")

# Initialize MySQL
mysql = MySQL(app)

# Optional server-side session
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
if ServerSession:
    ServerSession(app)

# Regex (REGISTER only)
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
PWD_RE   = re.compile(r"^(?=.*[A-Z])(?=.*\d)(?=.*[!@#$%^&*()_\-+=\[{\]};:'\",.<>/?\\|`~]).{8,}$")


# ---------------------------
# Routes
# ---------------------------
@app.route("/")
def index():
    if session.get("username"):
        return redirect(url_for("dashboard"))
    return render_template("index.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    """
    Low-friction login:
      - Require both fields
      - No email/password strength checks
      - Try username OR email (case-insensitive)
      - On failure: generic 'Incorrect username or password.'
    """
    if request.method == "POST":
        identifier = (request.form.get("identifier") or "").strip()
        password   = (request.form.get("password") or "").strip()

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
            ok = (pwd_hash == password)

        if not ok:
            flash("Incorrect username or password.", "error")
            return render_template("login.html")

        session["user_id"] = user_id
        session["username"] = username_db  # keep original casing for display
        flash("Login successful!", "success")
        return redirect(url_for("dashboard"))

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect("/")


@app.route("/register", methods=["GET", "POST"])
def register():
    """
    Registration:
      - Required fields
      - Email format
      - Strong password (≥8, uppercase, number, symbol)
      - Confirm matches
      - Username/email uniqueness (case-insensitive)
      - Returns inline errors via `errors` + preserves inputs via `values`
      - Also catches DB UNIQUE constraint violations
    """
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        email    = (request.form.get("email") or "").strip()
        password = (request.form.get("password") or "")
        confirm  = (request.form.get("confirmation") or "")

        username_lc = username.lower()
        email_lc    = email.lower()

        errors = {}
        values = {"username": username, "email": email}

        # --- Field validation ---
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

        # --- Uniqueness checks (case-insensitive) ---
        cur = mysql.connection.cursor()
        try:
            cur.execute("SELECT 1 FROM users WHERE LOWER(username)=%s LIMIT 1", (username_lc,))
            if cur.fetchone():
                errors["username"] = "This username is already taken."

            cur.execute("SELECT 1 FROM users WHERE LOWER(email)=%s LIMIT 1", (email_lc,))
            if cur.fetchone():
                errors["email"] = "This email is already registered."

            if errors:
                return render_template("register.html", errors=errors, values=values)

            # --- Insert (store normalized) ---
            pwd_hash = generate_password_hash(password)
            cur.execute(
                "INSERT INTO users (username, email, password) VALUES (%s, %s, %s)",
                (username_lc, email_lc, pwd_hash),
            )
            mysql.connection.commit()
            flash("Registration successful! You can now log in.", "success")
            return redirect(url_for("login"))

        except IntegrityError as e:
            # DB UNIQUE constraint caught a duplicate (error code 1062)
            mysql.connection.rollback()
            msg = str(e).lower()
            if "1062" in msg or "duplicate entry" in msg:
                # Map to the correct field if we can
                if "username" in msg:
                    errors["username"] = "This username is already taken."
                if "email" in msg:
                    errors["email"] = "This email is already registered."
                return render_template("register.html", errors=errors, values=values)

            # Generic DB error
            flash("Database error during registration.", "error")
            return render_template("register.html", values=values)

        except Exception as e:
            mysql.connection.rollback()
            flash(f"Unexpected error during registration: {e}", "error")
            return render_template("register.html", values=values)

        finally:
            cur.close()

    # GET
    return render_template("register.html")


@app.route("/dashboard")
def dashboard():
    if not session.get("username"):
        flash("Please log in to access the dashboard.", "warning")
        return redirect(url_for("login"))
    return render_template("dashboard.html")


# ---------------------------
# Entrypoint
# ---------------------------
if __name__ == "__main__":
    # Sanity check: DB envs present
    if not all([app.config["MYSQL_HOST"], app.config["MYSQL_USER"], app.config["MYSQL_DB"]]):
        print("\n!!! ERROR: Database environment variables are not set. !!!")
        print("Please create a .env file with MYSQL_HOST, MYSQL_USER, MYSQL_PASSWORD, MYSQL_DB.")
        raise SystemExit(1)

    app.run(debug=True)
