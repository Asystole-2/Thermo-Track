import os
from flask import Flask, render_template, redirect, request, session, flash, url_for
from flask_mysqldb import MySQL
from dotenv import load_dotenv, find_dotenv
from flask_session import Session
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
# Load environment variables from .env file
_ = load_dotenv(find_dotenv())
# Secret key for sessions
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-change-me")

# Retrieve environment variables from .env file
app.config["MYSQL_HOST"] = os.environ.get("MYSQL_HOST")
app.config["MYSQL_USER"] = os.environ.get("MYSQL_USER")
app.config["MYSQL_PASSWORD"] = os.environ.get("MYSQL_PASSWORD")
app.config["MYSQL_DB"] = os.environ.get("MYSQL_DB")

# Initialize MySQL
mysql = MySQL(app)

app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)


@app.route("/")
def index():
    if not session.get("username"):
        return redirect("/login")
    return render_template("index.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = (request.form.get("username") or "").strip().lower()
        password = (request.form.get("password") or "").strip()

        if not username or not password:
            flash("Please enter both username and password", "error")
            return render_template("login.html")

        cur = mysql.connection.cursor()
        try:
            cur.execute(
                "SELECT id, username, email, password FROM users WHERE username=%s LIMIT 1",
                (username,),
            )
            row = cur.fetchone()
        except Exception as e:
            mysql.connection.rollback()
            flash(f"Database error: {e}", "error")
            return render_template("login.html")
        finally:
            cur.close()

        if not row:
            flash("Invalid username or password", "error")
            return render_template("login.html")

        user_id, username_db, email_db, pwd_hash = row  # 4 columns → 4 vars

        # Verify password (hashed preferred; fallback if any legacy plain rows)
        try:
            ok = check_password_hash(pwd_hash, password)
        except ValueError:
            ok = pwd_hash == password

        if not ok:
            flash("Invalid username or password", "error")
            return render_template("login.html")

        session["user_id"] = user_id
        session["username"] = username_db
        flash("Logged in successfully", "success")
        return redirect(url_for("index"))

    # GET
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = (request.form.get("username") or "").strip().lower()
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""

        if not username:
            return render_template("error.html", message="Missing Username")
        if not email:
            return render_template("error.html", message="Missing email")
        if not password:
            return render_template("error.html", message="Missing password")

        cur = mysql.connection.cursor()
        try:
            # check existing username
            cur.execute(
                "SELECT 1 FROM users WHERE username=%s OR email=%s LIMIT 1",
                (username, email),
            )
            if cur.fetchone():
                return render_template(
                    "failure.html",
                    message="Username or email already registerd. Try Again",
                )
            # insert hashed password
            pwd_hash = generate_password_hash(password)
            # insert new users
            cur.execute(
                "INSERT INTO users (username, email, password) VALUES (%s, %s, %s)",
                (username, email, pwd_hash),
            )

            mysql.connection.commit()
            flash("Registaration successful! you can now log in", "success")
            return redirect("/login")
        finally:
            cur.close()

    return render_template("register.html")
