import os
from flask import Flask, render_template, redirect, request, session, flash, url_for
from flask_mysqldb import MySQL
from dotenv import load_dotenv, find_dotenv
from flask_session import Session

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


@app.route("/login")
def login():
    return redirect(url_for("register"))


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

            # insert new users
            cur.execute(
                "INSERT INTO users (username, email, password) VALUES (%s, %s, %s)",
                (username, email, password),
            )

            mysql.connection.commit()
            flash("Registaration successful! you can now log in", "success")
            return redirect("/login")
        finally:
            cur.close()

    return render_template("register.html")
