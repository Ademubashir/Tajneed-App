from flask import Flask, render_template, request, redirect, url_for, flash, send_file, session
import sqlite3
import io
import csv
from functools import wraps

app = Flask(__name__)
app.secret_key = "change-this-secret-key"
DB = "tajneed.db"
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "welcome"

SCHOOLS = [
    "Obafemi Awolowo University",
    "University of Ilesa",
    "Osun State University",
    "Federal Polytechnic Ede",
    "Fountain University",
]

LEVELS = ["100 level", "200 level", "300 level", "400 level", "500 level"]


def db():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c


def init_db():
    c = db()
    c.execute("""
        CREATE TABLE IF NOT EXISTS members(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
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


@app.route("/", methods=["GET", "POST"])
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
            return redirect(url_for("register"))
        except sqlite3.IntegrityError:
            flash("That phone number is already registered.", "error")
            return render_template("register.html", data=d, schools=SCHOOLS, levels=LEVELS)
        finally:
            c.close()

    return render_template("register.html", data={}, schools=SCHOOLS, levels=LEVELS)


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        if (request.form.get("username") == ADMIN_USERNAME
                and request.form.get("password") == ADMIN_PASSWORD): 
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
        sql += """ AND (
            full_name LIKE ? OR phone LIKE ? OR state LIKE ? OR
            school LIKE ? OR level LIKE ? OR course LIKE ? OR email LIKE ?
        )"""
        p += ["%" + q + "%"] * 7

    if gender:
        sql += " AND gender=?"
        p.append(gender)

    if school:
        sql += " AND school=?"
        p.append(school)

    if level:
        sql += " AND level=?"
        p.append(level)

    rows = c.execute(sql + " ORDER BY id DESC", p).fetchall()
    total = c.execute("SELECT COUNT(*) FROM members").fetchone()[0]
    males = c.execute("SELECT COUNT(*) FROM members WHERE gender='Male'").fetchone()[0]
    females = c.execute("SELECT COUNT(*) FROM members WHERE gender='Female'").fetchone()[0]
    c.close()

    return render_template(
        "admin.html",
        members=rows,
        total=total,
        males=males,
        females=females,
        q=q,
        gender=gender,
        school=school,
        level=level,
        schools=SCHOOLS,
        levels=LEVELS,
    )

@app.route("/admin/edit/<int:i>", methods=["GET", "POST"])
@admin_required
def edit(i):
    c = db()
    member=c.execute("SELECT * FROM members WHERE id=?", (i,)).fetchone()
    if not member:
        c.close()
        return "Member not found", 404
    if request.method == "POST":
        d = {k: request.form.get(k, "").strip() for k in [
            "full_name", "phone", "gender", "dob", "state",
            "school", "level", "course", "email"
        ]}

        try:
            c.execute("""UPDATE members SET full_name=?, phone=?, gender=?, dob=?, state=?, school=?, level=?, email=? WHERE id=?""", 
                      (d["full_name"], d["phone"], d["gender"], d["dob"], d["state"], d["school"], d["level"], d["email"], i))
            c.commit()
            flash("Member updated successfully.", "success")
            return redirect(url_for("admin"))
        except sqlite3.IntegrityError:
            flash("That phone number is already registered.", "error")
            
    c.close()
    return render_template("edit.html", member=member,
                           schools=SCHOOLS,
                           levels=LEVELS)

@app.post("/admin/delete/<int:i>")
@admin_required
def delete(i):
    c = db()
    c.execute("DELETE FROM members WHERE id=?", (i,))
    c.commit()
    c.close()
    return redirect(url_for("admin"))


@app.route("/admin/export")
@admin_required
def export():
    c = db()
    rows = c.execute("""
        SELECT id, full_name, phone, gender, dob, state, school, level,
               course, email, created_at
        FROM members ORDER BY id
    """).fetchall()
    c.close()

    s = io.StringIO()
    w = csv.writer(s)
    w.writerow([
        "ID", "Full Name", "Phone", "Gender", "Date of Birth", "State",
        "School Attended", "Level of Study", "Course of Study",
        "Email Address", "Registered At"
    ])
    w.writerows([tuple(r) for r in rows])

    return send_file(
        io.BytesIO(s.getvalue().encode()),
        mimetype="text/csv",
        as_attachment=True,
        download_name="tajneed_list.csv"
    )


init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
