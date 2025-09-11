from flask import Flask, jsonify, request, render_template
import sqlite3, re 
from datetime import datetime
import os 

import logging
from dotenv import load_dotenv

load_dotenv()

APP_HEADING = os.getenv("APP_HEADING")
LOGGING_ENABLED = os.getenv("LOGGING", "false").lower() == "true"
LOG_FILE = os.getenv("LOG_FILE", "student_actions.log")

# Configure logging if enabled
if LOGGING_ENABLED:
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s | %(levelname)s | %(message)s',
        handlers=[logging.FileHandler(LOG_FILE, encoding='utf-8')]
    )
else:
    logging.disable(logging.CRITICAL)

students = []

app = Flask(__name__, template_folder="templetes" ) 

def get_db_connection():
    conn = sqlite3.connect("students.db")
    conn.row_factory = sqlite3.Row 
    return conn

def create_db():
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS students(
            id INTEGER PRIMARY KEY,
            first_name VARCHAR(50),
            last_name VARCHAR(50),
            number VARCHAR(15),
            birthdate DATE,
            email TEXT UNIQUE NOT NULL
        )
        """)
        conn.commit()
        cursor.close()
        conn.close()

create_db()


def validate_student(data):
    errors = []

    if not data.get("first_name") or not re.match(r"^[A-Za-z\s-]{2,50}$",data["first_name"]):
        errors.append("Invalid first name. It should be 2-50 characters long and contains only letters, spaces, or hyphens.")

    if not data.get("last_name") or not re.match(r"^[A-Za-z\s-]{2,50}$",data["last_name"]):
        errors.append("Invalid last name. It should be 2-50 characters long and contains only letters, spaces, or hyphens.")

    # phone number should be 10 digits starting with 5-9
    phone = data.get("phone", "")
    if not phone or not re.match(r"^[5-9]\d{9}$", phone):
        errors.append("Invalid phone number. It should be 10 digits and start with 5,6,7,8 or 9.")
  
    try:
        birth = datetime.strptime(data.get("birthdate", ""), "%Y-%m-%d").date()
        today = datetime.today().date()
        age = today.year - birth.year - ((today.month, today.day) < (birth.month, birth.day))
        if birth > today or not (5 <= age <= 100):
            errors.append("Invalid birthdate (age must be 5–100)")
    except Exception:
        errors.append("Invalid birthdate format (YYYY-MM-DD)")

    email = data.get("email", "")
    if not re.match(r"^[^@]+@[^@]+\.[^@]+$", email):
        errors.append("Invalid email format")

    return errors
                   

@app.route("/api/students", methods = ["POST"])
def add_student():
    data = request.json 
    if not data:
        return jsonify({"success": False, "errors": ["Invalid JSON"]}), 400
    errors = validate_student(data)
    if errors:
        return jsonify({"success": False, "errors": errors}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    # Check for repeated phone number
    cursor.execute("SELECT id FROM students WHERE number = ?", (data["phone"],))
    if cursor.fetchone():
        cursor.close()
        conn.close()
        return jsonify({"success": False, "errors": ["A student with this phone number already exists."]}), 400
    try:
        cursor.execute(
            """
            INSERT INTO students (first_name, last_name, number, birthdate, email)
            VALUES (?, ?, ?, ?, ?)
            """,
            (data["first_name"], data["last_name"], data["phone"], data["birthdate"], data["email"]),
        )
        conn.commit()
        if LOGGING_ENABLED:
            logging.info(f"Student added: {{'first_name': '{data['first_name']}', 'last_name': '{data['last_name']}', 'phone': '{data['phone']}', 'birthdate': '{data['birthdate']}', 'email': '{data['email']}'}}")
    except sqlite3.IntegrityError as exc:
        # likely a UNIQUE constraint violation on email
        msg = "Database integrity error"
        err_text = str(exc).upper()
        if "UNIQUE" in err_text or "EMAIL" in err_text:
            msg = "A student with this email already exists."
        cursor.close()
        conn.close()
        return jsonify({"success": False, "errors": [msg]}), 400
    finally:
        try:
            cursor.close()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass

    return jsonify({"success": True, "message": "Student registered successfully!"})


@app.route("/api/students", methods=["GET"])
def get_students():
    conn = get_db_connection()
    cursor = conn.cursor()
    # return the number column aliased as phone for clarity in the API
    cursor.execute("SELECT id, first_name, last_name, number AS phone, birthdate, email FROM students")
    rows = cursor.fetchall()
    students = [dict(row) for row in rows]
    cursor.close()
    conn.close()
    return jsonify(students)


@app.route('/api/students/<int:student_id>', methods=['PUT'])
def edit_student(student_id):
    data = request.json
    if not data:
        return jsonify({"success": False, "errors": ["Invalid JSON"]}), 400
    errors = validate_student(data)
    if errors:
        return jsonify({"success": False, "errors": errors}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    # Check for repeated phone number (exclude current student)
    cursor.execute("SELECT id FROM students WHERE number = ? AND id != ?", (data["phone"], student_id))
    if cursor.fetchone():
        cursor.close()
        conn.close()
        return jsonify({"success": False, "errors": ["A student with this phone number already exists."]}), 400
    try:
        cursor.execute(
            """
            UPDATE students
            SET first_name = ?, last_name = ?, number = ?, birthdate = ?, email = ?
            WHERE id = ?
            """,
            (data["first_name"], data["last_name"], data["phone"], data["birthdate"], data["email"], student_id),
        )
        conn.commit()
        if cursor.rowcount == 0:
            cursor.close()
            conn.close()
            return jsonify({"success": False, "errors": ["Student not found"]}), 404
        if LOGGING_ENABLED:
            logging.info(f"Student updated: {{'id': {student_id}, 'first_name': '{data['first_name']}', 'last_name': '{data['last_name']}', 'phone': '{data['phone']}', 'birthdate': '{data['birthdate']}', 'email': '{data['email']}'}}")
    except sqlite3.IntegrityError as exc:
        msg = "Database integrity error"
        err_text = str(exc).upper()
        if "UNIQUE" in err_text or "EMAIL" in err_text:
            msg = "A student with this email already exists."
        cursor.close()
        conn.close()
        return jsonify({"success": False, "errors": [msg]}), 400
    finally:
        try:
            cursor.close()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass

    return jsonify({"success": True, "message": "Student updated successfully!"})


@app.route('/api/students/<int:student_id>', methods=['DELETE'])
def delete_student(student_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM students WHERE id = ?", (student_id,))
    conn.commit()
    deleted = cursor.rowcount
    cursor.close()
    conn.close()
    if deleted == 0:
        return jsonify({"success": False, "errors": ["Student not found"]}), 404
    # resequence IDs so they remain compact after deletions
    try:
        resequence_students()
    except Exception:
        # non-fatal: if resequence fails, still report successful deletion
        pass

    return jsonify({"success": True, "message": "Student deleted"})


def resequence_students():
    """Rebuild the students table with compact sequential IDs starting from 1.

    This drops and recreates the table and reinserts rows ordered by the old id.
    Use with care; kept simple for local/testing use.
    """
    conn = get_db_connection()
    cur = conn.cursor()
    # fetch existing rows in order
    cur.execute("SELECT first_name, last_name, number, birthdate, email FROM students ORDER BY id")
    rows = cur.fetchall()

    # drop and recreate table without AUTOINCREMENT
    cur.execute("DROP TABLE students")
    cur.execute('''
                   create table students(
                   id INTEGER PRIMARY KEY,
    first_name VARCHAR(50),
    last_name VARCHAR(50),
    number VARCHAR(15),
    birthdate DATE,
    email TEXT UNIQUE NOT NULL
                   )
                   ''')

    # reinsert rows with compact ids
    for idx, r in enumerate(rows, start=1):
        cur.execute(
            "INSERT INTO students (id, first_name, last_name, number, birthdate, email) VALUES (?, ?, ?, ?, ?, ?)",
            (idx, r[0], r[1], r[2], r[3], r[4])
        )

    conn.commit()
    cur.close()
    conn.close()

@app.route("/")
def index():
    return render_template("index.html",heading=APP_HEADING)

if __name__ == "__main__":
    app.run(debug=True)