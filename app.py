import os

from flask import Flask, render_template, request, redirect, url_for, flash, send_file, session
import io
import csv
from functools import wraps

app = Flask(__name__)
app.secret_key = "change-this-secret-key"
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "welcome"

# --- Database setup: Postgres on Render (when DATABASE_URL is set),
# --- SQLite when running locally with no DATABASE_URL.
DATABASE_URL = os.environ.get("DATABASE_URL")
USE_PG = bool(DATABASE_URL)

if USE_PG:
    import psycopg2
    import psycopg2.extras
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    IntegrityError = psycopg2.IntegrityError
else:
    import sqlite3
    DB = "tajneed.db"
    IntegrityError = sqlite3.IntegrityError


class PGConn:
    """Thin wrapper so Postgres connections support the same
    .execute(sql, params).fetchall()/.fetchone() chaining style
    that sqlite3 connections support natively."""
    def __init__(self, conn):
        self.conn = conn
        self.cur = conn.cursor()

    def execute(self, sql, params=()):
        self.cur.execute(sql.replace("?", "%s"), params)
        return self.cur

    def commit(self):
        self.conn.commit()

    def close(self):
        self.cur.close()
        self.conn.close()


def db():
    if USE_PG:
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)
        return PGConn(conn)
    else:
        c = sqlite3.connect(DB)
        c.row_factory = sqlite3.Row
        return c

SCHOOLS = [
    "Obafemi Awolowo University",
    "University of Ilesa",
    "Osun State University",
    "Federal Polytechnic Ede",
    "Fountain University",
]

LEVELS = ["100 level", "200 level", "300 level", "400 level", "500 level"]


def init_db():
    c = db()
    id_col = "id SERIAL PRIMARY KEY" if USE_PG else "id INTEGER PRIMARY KEY AUTOINCREMENT"
    c.execute(f"""
        CREATE TABLE IF NOT EXISTS members(
            {id_col},
            full_name TEXT NOT NULL,
            phone TEXT NOT NULL UNIQUE,
            gender TEXT NOT NULL,
            dob TEXT,
            state TEXT,
            school TEXT,
            level TEXT,
            course TEXT,
            email TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Upgrade an older copy of the app without deleting existing registrations.
    if USE_PG:
        rows = c.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name = 'members'"
        ).fetchall()
        columns = {row["column_name"] for row in rows}
    else:
        columns = {row["name"] for row in c.execute("PRAGMA table_info(members)").fetchall()}

    for name, definition in [
        ("school", "TEXT"),
        ("level", "TEXT"),
        ("course", "TEXT"),
        ("email", "TEXT"),
    ]:
        if name not in columns:
            c.execute(f"ALTER TABLE members ADD COLUMN {name} {definition}")

    c.commit()
    c.close()


def admin_required(f):
    @wraps(f)
    def w(*a, **k):
        if not session.get("admin"):
            return redirect(url_for("admin_login"))
        return f(*a, **k)
    return w

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/success")
def success():
    return render_template("success.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        d = {k: request.form.get(k, "").strip() for k in [
            "full_name", "phone", "gender", "dob", "state",
            "school", "level", "course", "email"
        ]}

        if not d["full_name"] or not d["phone"] or not d["gender"]:
            flash("Please complete all required fields.", "error")
            return render_template("register.html", data=d, schools=SCHOOLS, levels=LEVELS)

        if d["school"] not in SCHOOLS:
            flash("Please select a valid school.", "error")
            return render_template("register.html", data=d, schools=SCHOOLS, levels=LEVELS)

        if d["level"] not in LEVELS:
            flash("Please select a valid level of study.", "error")
            return render_template("register.html", data=d, schools=SCHOOLS, levels=LEVELS)

        c = db()
        try:
            c.execute("""
                INSERT INTO members
                (full_name, phone, gender, dob, state, school, level, course, email)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, tuple(d.values()))
            c.commit()
            flash("Registration submitted successfully.", "success")
            return redirect(url_for("success"))
        except IntegrityError:
            flash("That phone number is already registered.", "error")
            return render_template("register.html", data=d, schools=SCHOOLS, levels=LEVELS)

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        if (request.form.get('username') == ADMIN_USERNAME and request.form.get('password') == ADMIN_PASSWORD):
            session["admin"] = True
            return redirect(url_for("admin"))
        return render_template("login.html")

@app.route("/admin/logout")
def admin_logout():
    session.clear()
    return redirect(url_for("admin_login"))

@app.route("/admin")
@admin_required
def admin():
    q = request.args.get("q", "").strip()
    gender = request.args.get("gender", "")
    school = request.args.get("school", "")
    level = request.args.get("level", "")

    c = db()
    sql = "SELECT * FROM members WHERE 1=1"
    p = []

    

    if q:
        sql += """ AND (full_name LIKE ? OR phone LIKE ? OR state LIKE ? OR school LIKE ? OR level LIKE ? OR course LIKE ? OR email LIKE ?)"""
        p +=["%" + q + "%"] * 7

    if gender:
        sql += "AND gender = ?"
        p.append(gender)

    if level:
        sql += "AND level=?"
        p.append(level)

    rows = c.execute(sql + "ORDER BY id DESC", p).fetchall()
    total = c.execute("SELECT COUNT(*) AS n FROM members").fetchone()["n"]
    males = c.execute("SELECT COUNT(*) AS n FROM members WHERE gender='male' ").fetchone()["n"]
    females = c.execute("SELECT COUNT(*) AS n FROM members WHERE gender='female' ").fetchone()["n"]

    return render_template(
        "admin.html",
        members=rows,
        total=total,
        male=males,
        female=females,
        q=q,
        gender=gender,
        school=school,
        level=level,
        schools=SCHOOLS,
        levels=LEVELS
    )

@app.route("/admin/edit/<int:i>", methods=["GET", "POST"])
@admin_required
def admin_edit(i):
    c = db()
    members=c.execute("SELECT * FROM members WHERE id=?", (i,)).fetchone()
    if not members:
        c.close()
        return "MEMBER not found", 404
    if request.method == "POST":
        d = {k: request.form.get(k, "").strip() for k in [
            "full_name", "phone", "gender", "dob", "state",
            "school", "level", "course", "email"
        ]}

        try:
            c.execute("""
                UPDATE members SET
                full_name=?, phone=?, gender=?, dob=?, state=?, school=?, level=?, course=?, email=?
                WHERE id=?""", (d["full_name"], d["phone"], d["gender"], d["dob"], d["state"], d["level"], d["email"], i))
            c.commit()
            flash("Member updated successfully.", "success")
            return redirect(url_for("admin"))
        except IntegrityError:
            flash("That phone number has already being registered." "error")

    c.close()
    return render_template("edit.html", member=members, schools=SCHOOLS, levels=LEVELS)

@app.post("/admin/delete/<int:i>")
@admin_required
def admin_delete(i):
    c = db()
    c.execute("DELETE FROM members WHERE id=?", (i,))
    c.commit()
    c.close()
    return redirect(url_for("admin"))


@app.route("/admin/export")
@admin_required
def export():
    c = db()
    rows = c.execute("""SELECT id, full_name, phone, gender, dob, state, school, level, course, email, created_at FROM members ORDER BY id""").fetchall()
    c.close()

    s = io.StringIO()
    w = csv.writer(s)
    w.writerow(["ID", "Full Name", "Phone", "Gender", "Date of Birth", "State", "School Attended", "Level Of Study", "Course of Study", "Email Address", "Registered At"])
    w.writerows([
        (r["id"], r["full_name"], r["phone"], r["gender"], r["dob"], r["state"], r["school"], r["level"], r["course"], r["email"], r["created_at"])
        for r in rows
    ])

    return send_file(
        io.BytesIO(s.getvalue().encode()),
        mintype="text/csv",
        at_attachment=True,
        download_name="tajneed_list.csv"
        )

init_db()

if __name__=="_main_":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)