import os
from flask import flask, render_template, redirect, request, session, flash, url_for
from flask_mysqldb import MySQL
from dotenv import load_dotenv, find_dotenv

app = flask(__name__)
# Load environment variables from .env file
_ = load_dotenv(find_dotenv())

# Retrieve environment variables from .env file
app.config["MYSQL_HOST"] = os.environ.get("MYSQL_HOST")
app.config["MYSQL_USER"] = os.environ.get("MYSQL_USER")
app.config["MYSQL_PASSWORD"] = os.environ.get("MYSQL_PASSWORD")
app.config["MYSQL_DB"] = os.environ.get("MYSQL_DB")

# Initialize MySQL
mysql = MySQL(app)
