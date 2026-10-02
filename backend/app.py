
import json
import sqlite3
import secrets
from datetime import datetime
from flask import (
    Flask,
    request,
    jsonify,
    render_template,
    redirect,
    session,
    send_from_directory
)
from flask_cors import CORS

from werkzeug.utils import secure_filename
from werkzeug.security import check_password_hash, generate_password_hash
import os

# =========================================================
# SCHOLARMATCH AI
# Flask + SQLite backend
# =========================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", "frontend"))
DB_PATH = os.path.join(BASE_DIR, "scholarmatch.db")
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")

os.makedirs(UPLOAD_DIR, exist_ok=True)

app = Flask(
    __name__,
    template_folder=FRONTEND_DIR,
    static_folder=FRONTEND_DIR
)

app.secret_key = os.environ.get("SECRET_KEY") or secrets.token_hex(32)

DEFAULT_ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://localhost:5000",
    "http://localhost:8000",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:5000",
    "http://127.0.0.1:8000",
]

allowed_origins = []
for raw_origin in (
    os.environ.get("ALLOWED_ORIGINS") or
    os.environ.get("FRONTEND_URL") or
    ",".join(DEFAULT_ALLOWED_ORIGINS)
).split(","):
    origin = raw_origin.strip()
    if origin:
        allowed_origins.append(origin)

if not allowed_origins:
    allowed_origins = DEFAULT_ALLOWED_ORIGINS

app.config["API_BASE_URL"] = os.environ.get("API_BASE_URL") or "http://localhost:5000"
app.config["CORS_ALLOWED_ORIGINS"] = allowed_origins
CORS(
    app,
    resources={r"/*": {"origins": allowed_origins}},
    supports_credentials=True,
    expose_headers=["Content-Type", "Authorization"],
)

ALLOWED_EXTENSIONS = {"pdf", "jpg", "jpeg", "png"}

OFFICIAL_NSP = "https://scholarships.gov.in/"
OFFICIAL_NSP_ALL = "https://scholarships.gov.in/All-Scholarships"


# =========================================================
# DATABASE HELPERS
# =========================================================

def get_db():
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    return db


def column_exists(db, table_name, column_name):
    rows = db.execute(f"PRAGMA table_info({table_name})").fetchall()
    return any(row["name"] == column_name for row in rows)


def ensure_column(db, table_name, column_name, column_type):
    if not column_exists(db, table_name, column_name):
        db.execute(
            f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}"
        )


def normalize_email(email):
    return str(email or "").strip().lower()


def now_text():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def allowed_file(filename):
    if not filename:
        return False

    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS
    )


# =========================================================
# DATABASE INITIALIZATION / MIGRATION
# =========================================================

def init_db():
    db = get_db()

    # -----------------------------------------------------
    # USERS
    # -----------------------------------------------------

    db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            email TEXT,
            password TEXT
        )
    """)

    # Older versions of the project used different columns.
    ensure_column(db, "users", "name", "TEXT")
    ensure_column(db, "users", "email", "TEXT")
    ensure_column(db, "users", "password", "TEXT")
    ensure_column(db, "users", "full_name", "TEXT")
    ensure_column(db, "users", "created_at", "TEXT")

    # -----------------------------------------------------
    # PROFILE
    # -----------------------------------------------------

    db.execute("""
        CREATE TABLE IF NOT EXISTS profiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER UNIQUE,
            full_name TEXT,
            age INTEGER,
            state TEXT,
            course TEXT,
            academic_percentage REAL,
            annual_family_income REAL,
            category TEXT,
            gender TEXT,
            email TEXT,
            phone TEXT,
            college TEXT,
            additional_details TEXT,
            created_at TEXT,
            updated_at TEXT
        )
    """)

    ensure_column(db, "profiles", "user_id", "INTEGER")
    ensure_column(db, "profiles", "full_name", "TEXT")
    ensure_column(db, "profiles", "age", "INTEGER")
    ensure_column(db, "profiles", "state", "TEXT")
    ensure_column(db, "profiles", "course", "TEXT")
    ensure_column(db, "profiles", "academic_percentage", "REAL")
    ensure_column(db, "profiles", "annual_family_income", "REAL")
    ensure_column(db, "profiles", "category", "TEXT")
    ensure_column(db, "profiles", "gender", "TEXT")
    ensure_column(db, "profiles", "email", "TEXT")
    ensure_column(db, "profiles", "phone", "TEXT")
    ensure_column(db, "profiles", "college", "TEXT")
    ensure_column(db, "profiles", "additional_details", "TEXT")
    ensure_column(db, "profiles", "created_at", "TEXT")
    ensure_column(db, "profiles", "updated_at", "TEXT")

    # -----------------------------------------------------
    # APPLICATIONS
    # -----------------------------------------------------

    db.execute("""
        CREATE TABLE IF NOT EXISTS applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            scholarship_id TEXT,
            scholarship_name TEXT,
            full_name TEXT,
            email TEXT,
            phone TEXT,
            state TEXT,
            course TEXT,
            college TEXT,
            academic_percentage REAL,
            annual_family_income REAL,
            category TEXT,
            gender TEXT,
            additional_details TEXT,
            status TEXT DEFAULT 'Draft',
            otp_verified INTEGER DEFAULT 0,
            created_at TEXT
        )
    """)

    ensure_column(db, "applications", "user_id", "INTEGER")
    ensure_column(db, "applications", "scholarship_id", "TEXT")
    ensure_column(db, "applications", "scholarship_name", "TEXT")
    ensure_column(db, "applications", "full_name", "TEXT")
    ensure_column(db, "applications", "email", "TEXT")
    ensure_column(db, "applications", "phone", "TEXT")
    ensure_column(db, "applications", "state", "TEXT")
    ensure_column(db, "applications", "course", "TEXT")
    ensure_column(db, "applications", "college", "TEXT")
    ensure_column(db, "applications", "academic_percentage", "REAL")
    ensure_column(db, "applications", "annual_family_income", "REAL")
    ensure_column(db, "applications", "category", "TEXT")
    ensure_column(db, "applications", "gender", "TEXT")
    ensure_column(db, "applications", "additional_details", "TEXT")
    ensure_column(db, "applications", "status", "TEXT")
    ensure_column(db, "applications", "otp_verified", "INTEGER")
    ensure_column(db, "applications", "created_at", "TEXT")

    # -----------------------------------------------------
    # MIGRATE OLD USER DATA
    # -----------------------------------------------------

    # If an old record has name but no full_name, copy name.
    db.execute("""
        UPDATE users
        SET full_name = name
        WHERE (full_name IS NULL OR TRIM(full_name) = '')
        AND name IS NOT NULL
        AND TRIM(name) != ''
    """)

    # If an old record has full_name but no name, copy full_name.
    db.execute("""
        UPDATE users
        SET name = full_name
        WHERE (name IS NULL OR TRIM(name) = '')
        AND full_name IS NOT NULL
        AND TRIM(full_name) != ''
    """)

    # Fill missing created_at values.
    db.execute("""
        UPDATE users
        SET created_at = ?
        WHERE created_at IS NULL OR TRIM(created_at) = ''
    """, (now_text(),))

    # Normalize all existing emails.
    users = db.execute("SELECT id, email FROM users").fetchall()

    for user in users:
        email = normalize_email(user["email"])

        if email:
            db.execute(
                "UPDATE users SET email = ? WHERE id = ?",
                (email, user["id"])
            )

    db.commit()
    db.close()


# Initialize database when application starts.
init_db()


# =========================================================
# SCHOLARSHIP DATA
# =========================================================

SCHOLARSHIPS = [
    {
        "id": "pragati-degree",
        "name": "AICTE Pragati Scholarship for Technical Degree",
        "short_name": "AICTE Pragati",
        "description": "Scholarship support for eligible girl students pursuing technical degree programmes.",
        "official_url": "https://scholarships.gov.in/",
        "categories": ["General", "OBC", "SC", "ST", "EWS"],
        "genders": ["Female"],
        "max_income": 800000,
        "min_percentage": 50,
        "courses": ["B.Tech", "B.E", "Engineering", "AI & ML", "Computer Science"]
    },
    {
        "id": "pm-usp-csss",
        "name": "PM-USP Central Sector Scheme of Scholarship",
        "short_name": "PM-USP CSSS",
        "description": "Central sector scholarship for meritorious students subject to scheme conditions.",
        "official_url": "https://scholarships.gov.in/",
        "categories": ["General", "OBC", "SC", "ST", "EWS"],
        "genders": ["Female", "Male", "Other"],
        "max_income": 450000,
        "min_percentage": 80,
        "courses": ["B.Tech", "B.E", "Engineering", "Degree", "AI & ML", "Computer Science"]
    },
    {
        "id": "yasasvi-college",
        "name": "PM YASASVI Top Class Education",
        "short_name": "PM YASASVI",
        "description": "Support for eligible OBC, EBC and DNT students under applicable scheme conditions.",
        "official_url": "https://scholarships.gov.in/",
        "categories": ["OBC", "EBC", "DNT"],
        "genders": ["Female", "Male", "Other"],
        "max_income": 250000,
        "min_percentage": 60,
        "courses": ["B.Tech", "B.E", "Engineering", "Degree", "AI & ML", "Computer Science"]
    },
    {
        "id": "sc-top-class",
        "name": "Top Class Education Scheme for SC Students",
        "short_name": "Top Class SC",
        "description": "Higher education support for eligible SC students.",
        "official_url": "https://scholarships.gov.in/",
        "categories": ["SC"],
        "genders": ["Female", "Male", "Other"],
        "max_income": 800000,
        "min_percentage": 60,
        "courses": ["B.Tech", "B.E", "Engineering", "Degree", "AI & ML", "Computer Science"]
    },
    {
        "id": "st-higher-education",
        "name": "National Scholarship for Higher Education of ST Students",
        "short_name": "ST Higher Education",
        "description": "Scholarship support for eligible ST students pursuing higher education.",
        "official_url": "https://scholarships.gov.in/",
        "categories": ["ST"],
        "genders": ["Female", "Male", "Other"],
        "max_income": 800000,
        "min_percentage": 50,
        "courses": ["B.Tech", "B.E", "Engineering", "Degree", "AI & ML", "Computer Science"]
    },
    {
        "id": "disability-post-matric",
        "name": "Post Matric Scholarship for Students with Disabilities",
        "short_name": "Disability Post Matric",
        "description": "Scholarship support for eligible students with disabilities under applicable conditions.",
        "official_url": "https://scholarships.gov.in/",
        "categories": ["General", "OBC", "SC", "ST", "EWS"],
        "genders": ["Female", "Male", "Other"],
        "max_income": 250000,
        "min_percentage": 40,
        "courses": ["B.Tech", "B.E", "Engineering", "Degree", "AI & ML", "Computer Science"]
    },
    {
        "id": "ishan-uday",
        "name": "Ishan Uday Special Scholarship Scheme",
        "short_name": "Ishan Uday",
        "description": "Special scholarship scheme for eligible students from the North Eastern Region.",
        "official_url": "https://scholarships.gov.in/",
        "categories": ["General", "OBC", "SC", "ST", "EWS"],
        "genders": ["Female", "Male", "Other"],
        "max_income": 450000,
        "min_percentage": 50,
        "courses": ["B.Tech", "B.E", "Engineering", "Degree", "AI & ML", "Computer Science"]
    },
    {
        "id": "swanath",
        "name": "AICTE Swanath Scholarship Scheme",
        "short_name": "AICTE Swanath",
        "description": "Scholarship scheme for eligible students under AICTE Swanath conditions.",
        "official_url": "https://scholarships.gov.in/",
        "categories": ["General", "OBC", "SC", "ST", "EWS"],
        "genders": ["Female", "Male", "Other"],
        "max_income": 800000,
        "min_percentage": 50,
        "courses": ["B.Tech", "B.E", "Engineering", "Degree", "AI & ML", "Computer Science"]
    }
]


def get_scholarship(scholarship_id):
    for scholarship in SCHOLARSHIPS:
        if scholarship["id"] == scholarship_id:
            return scholarship
    return None


# =========================================================
# LOGIN / REGISTER
# =========================================================

@app.route("/")
def home():
    return render_template("index.html")


@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "GET":
        return render_template("login.html")

    data = request.get_json(silent=True)

    if data is None:
        data = request.form.to_dict()

    email = normalize_email(data.get("email"))
    password = str(data.get("password", ""))

    if not email or not password:
        return jsonify({
            "success": False,
            "message": "Please enter email and password."
        }), 400

    db = get_db()

    user = db.execute("""
        SELECT id, name, full_name, email, password
        FROM users
        WHERE LOWER(TRIM(email)) = ?
        LIMIT 1
    """, (email,)).fetchone()

    db.close()

    if not user:
        return jsonify({
            "success": False,
            "message": "Invalid email or password."
        }), 401

    stored_password = str(user["password"] or "")
    is_hashed = stored_password.startswith(("scrypt:", "pbkdf2:"))

    password_matches = (
        check_password_hash(stored_password, password)
        if is_hashed
        else stored_password == password
    )

    if not password_matches:
        return jsonify({
            "success": False,
            "message": "Invalid email or password."
        }), 401

    if not is_hashed:
        db = get_db()
        db.execute(
            "UPDATE users SET password = ? WHERE id = ?",
            (generate_password_hash(password), user["id"])
        )
        db.commit()
        db.close()

    full_name = user["full_name"] or user["name"] or ""

    session["user_id"] = user["id"]
    session["email"] = user["email"]
    session["full_name"] = full_name

    return jsonify({
        "success": True,
        "message": "Login successful.",
        "redirect": "/dashboard"
    })


@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "GET":
        return render_template("register.html")

    data = request.get_json(silent=True)

    if data is None:
        data = request.form.to_dict()

    full_name = str(
        data.get("full_name")
        or data.get("name")
        or ""
    ).strip()

    email = normalize_email(data.get("email"))

    password = str(data.get("password", ""))
    confirm_password = str(
        data.get("confirm_password")
        or data.get("confirmPassword")
        or ""
    )

    if not full_name or not email or not password or not confirm_password:
        return jsonify({
            "success": False,
            "message": "Please fill all required fields."
        }), 400

    if "@" not in email:
        return jsonify({
            "success": False,
            "message": "Please enter a valid email address."
        }), 400

    if len(password) < 6:
        return jsonify({
            "success": False,
            "message": "Password must contain at least 6 characters."
        }), 400

    if password != confirm_password:
        return jsonify({
            "success": False,
            "message": "Passwords do not match."
        }), 400

    db = get_db()

    # IMPORTANT:
    # Normalize existing email before checking.
    existing = db.execute("""
        SELECT id
        FROM users
        WHERE LOWER(TRIM(email)) = ?
        LIMIT 1
    """, (email,)).fetchone()

    if existing:
        db.close()

        return jsonify({
            "success": False,
            "message": "An account with this email already exists."
        }), 409

    created_at = now_text()
    hashed_password = generate_password_hash(password)

    cursor = db.execute("""
        INSERT INTO users
        (name, email, password, full_name, created_at)
        VALUES (?, ?, ?, ?, ?)
    """, (
        full_name,
        email,
        hashed_password,
        full_name,
        created_at
    ))

    user_id = cursor.lastrowid

    # Create an empty profile automatically.
    db.execute("""
        INSERT INTO profiles
        (user_id, full_name, email, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?)
    """, (
        user_id,
        full_name,
        email,
        created_at,
        created_at
    ))

    db.commit()
    db.close()

    # Automatically login the new user.
    session["user_id"] = user_id
    session["email"] = email
    session["full_name"] = full_name

    return jsonify({
        "success": True,
        "message": "Account created successfully.",
        "redirect": "/dashboard"
    })


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


# =========================================================
# AUTH HELPER
# =========================================================

def require_login():
    return session.get("user_id")


# =========================================================
# DASHBOARD
# =========================================================

@app.route("/dashboard")
def dashboard():

    if not require_login():
        return redirect("/login")

    return render_template("dashboard.html")


# =========================================================
# APPLY PAGE
# =========================================================

@app.route("/apply")
def apply_page():

    if not require_login():
        return redirect("/login")

    return render_template("apply.html")


# =========================================================
# APPLICATIONS PAGE
# =========================================================

@app.route("/applications")
def applications_page():

    if not require_login():
        return redirect("/login")

    return render_template("applications.html")


# =========================================================
# PROFILE API
# =========================================================

@app.route("/api/profile", methods=["GET", "POST"])
def profile_api():

    user_id = require_login()

    if not user_id:
        return jsonify({
            "success": False,
            "message": "Please login first."
        }), 401

    db = get_db()

    if request.method == "GET":

        profile = db.execute("""
            SELECT *
            FROM profiles
            WHERE user_id = ?
            LIMIT 1
        """, (user_id,)).fetchone()

        db.close()

        if not profile:
            return jsonify({
                "success": True,
                "profile": {}
            })

        return jsonify({
            "success": True,
            "profile": dict(profile)
        })

    data = request.get_json(silent=True) or request.form.to_dict()

    full_name = str(data.get("full_name", "")).strip()
    age = data.get("age")
    state = str(data.get("state", "")).strip()
    course = str(data.get("course", "")).strip()
    academic_percentage = data.get("academic_percentage")
    annual_family_income = data.get("annual_family_income")
    category = str(data.get("category", "")).strip()
    gender = str(data.get("gender", "")).strip()
    email = normalize_email(data.get("email") or session.get("email"))
    phone = str(data.get("phone", "")).strip()
    college = str(data.get("college", "")).strip()
    additional_details = str(
        data.get("additional_details", "")
    ).strip()

    def number_or_none(value):
        try:
            if value is None or str(value).strip() == "":
                return None
            return float(value)
        except Exception:
            return None

    age_value = number_or_none(age)
    percentage_value = number_or_none(academic_percentage)
    income_value = number_or_none(annual_family_income)

    existing = db.execute("""
        SELECT id
        FROM profiles
        WHERE user_id = ?
        LIMIT 1
    """, (user_id,)).fetchone()

    timestamp = now_text()

    if existing:

        db.execute("""
            UPDATE profiles
            SET
                full_name = ?,
                age = ?,
                state = ?,
                course = ?,
                academic_percentage = ?,
                annual_family_income = ?,
                category = ?,
                gender = ?,
                email = ?,
                phone = ?,
                college = ?,
                additional_details = ?,
                updated_at = ?
            WHERE user_id = ?
        """, (
            full_name,
            age_value,
            state,
            course,
            percentage_value,
            income_value,
            category,
            gender,
            email,
            phone,
            college,
            additional_details,
            timestamp,
            user_id
        ))

    else:

        db.execute("""
            INSERT INTO profiles
            (
                user_id,
                full_name,
                age,
                state,
                course,
                academic_percentage,
                annual_family_income,
                category,
                gender,
                email,
                phone,
                college,
                additional_details,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            user_id,
            full_name,
            age_value,
            state,
            course,
            percentage_value,
            income_value,
            category,
            gender,
            email,
            phone,
            college,
            additional_details,
            timestamp,
            timestamp
        ))

    # Keep user name/email synchronized.
    db.execute("""
        UPDATE users
        SET name = ?,
            full_name = ?,
            email = ?
        WHERE id = ?
    """, (
        full_name,
        full_name,
        email,
        user_id
    ))

    db.commit()
    db.close()

    session["full_name"] = full_name
    session["email"] = email

    return jsonify({
        "success": True,
        "message": "Profile saved successfully."
    })


# =========================================================
# SCHOLARSHIP MATCHING
# =========================================================

@app.route("/api/match-scholarships", methods=["POST"])
def match_scholarships():

    if not require_login():
        return jsonify({
            "success": False,
            "message": "Please login first."
        }), 401

    data = request.get_json(silent=True) or {}

    category = str(data.get("category", "")).strip()
    gender = str(data.get("gender", "")).strip()
    course = str(data.get("course", "")).strip()
    state = str(data.get("state", "")).strip()

    try:
        percentage = float(data.get("academic_percentage") or 0)
    except Exception:
        percentage = 0

    try:
        income = float(data.get("annual_family_income") or 0)
    except Exception:
        income = 0

    results = []

    for scholarship in SCHOLARSHIPS:

        score = 0
        reasons = []

        # Gender
        if gender and gender in scholarship["genders"]:
            score += 20
            reasons.append("Gender requirement appears compatible.")

        # Category
        if category and category in scholarship["categories"]:
            score += 25
            reasons.append("Category requirement appears compatible.")

        # Income
        if income > 0:

            if income <= scholarship["max_income"]:
                score += 25
                reasons.append("Family income is within the demo income threshold.")
            else:
                score -= 15
                reasons.append("Family income may exceed the demo threshold.")

        # Percentage
        if percentage > 0:

            if percentage >= scholarship["min_percentage"]:
                score += 20
                reasons.append("Academic percentage meets the demo threshold.")
            else:
                score -= 10
                reasons.append("Academic percentage may be below the demo threshold.")

        # Course
        course_lower = course.lower()

        if course:

            course_match = False

            for allowed_course in scholarship["courses"]:

                if (
                    allowed_course.lower() in course_lower
                    or course_lower in allowed_course.lower()
                ):
                    course_match = True
                    break

            if course_match:
                score += 10
                reasons.append("Course appears relevant.")

        # Keep between 0 and 100.
        score = max(0, min(100, score))

        if not reasons:
            reasons.append(
                "Add more profile details for a more useful demo match."
            )

        results.append({
            "id": scholarship["id"],
            "name": scholarship["name"],
            "short_name": scholarship["short_name"],
            "description": scholarship["description"],
            "official_url": scholarship["official_url"],
            "match_percentage": score,
            "match": score,
            "reasons": reasons
        })

    results.sort(
        key=lambda item: item["match_percentage"],
        reverse=True
    )

    return jsonify({
        "success": True,
        "scholarships": results,
        "results": results
    })


# =========================================================
# GET ALL SCHOLARSHIPS
# =========================================================

@app.route("/api/scholarships", methods=["GET"])
def scholarships_api():

    return jsonify({
        "success": True,
        "scholarships": SCHOLARSHIPS
    })


# =========================================================
# APPLICATION CREATION
# =========================================================

@app.route("/api/applications", methods=["POST"])
def create_application():

    user_id = require_login()

    if not user_id:
        return jsonify({
            "success": False,
            "message": "Please login first."
        }), 401

    db = get_db()

    try:

        # Multipart form from apply.html
        form = request.form

        scholarship_id = str(
            form.get("scholarship_id", "")
        ).strip()

        scholarship_name = str(
            form.get("scholarship_name", "")
        ).strip()

        scholarship = get_scholarship(scholarship_id)

        if scholarship and not scholarship_name:
            scholarship_name = scholarship["name"]

        full_name = str(form.get("full_name", "")).strip()
        email = normalize_email(form.get("email"))
        phone = str(form.get("phone", "")).strip()
        state = str(form.get("state", "")).strip()
        course = str(form.get("course", "")).strip()
        college = str(form.get("college", "")).strip()

        try:
            academic_percentage = float(
                form.get("academic_percentage") or 0
            )
        except Exception:
            academic_percentage = 0

        try:
            annual_family_income = float(
                form.get("annual_family_income") or 0
            )
        except Exception:
            annual_family_income = 0

        category = str(form.get("category", "")).strip()
        gender = str(form.get("gender", "")).strip()

        additional_details = str(
            form.get("additional_details", "")
        ).strip()

        # -------------------------------------------------
        # Collect scholarship-specific details.
        # -------------------------------------------------

        extra_details = {}

        for key in form.keys():

            if key.startswith("scholarship_"):
                extra_details[key] = form.get(key)

        if additional_details:
            try:
                existing_details = json.loads(additional_details)

                if isinstance(existing_details, dict):
                    extra_details.update(existing_details)

            except Exception:
                extra_details["additional_details"] = additional_details

        additional_details_json = json.dumps(
            extra_details,
            ensure_ascii=False
        )

        # -------------------------------------------------
        # Save uploaded documents.
        # -------------------------------------------------

        uploaded_files = []

        for field_name in request.files:

            files = request.files.getlist(field_name)

            for file in files:

                if not file or not file.filename:
                    continue

                if not allowed_file(file.filename):
                    continue

                safe_name = secure_filename(file.filename)

                unique_name = (
                    f"{user_id}_"
                    f"{secrets.token_hex(6)}_"
                    f"{safe_name}"
                )

                file_path = os.path.join(
                    UPLOAD_DIR,
                    unique_name
                )

                file.save(file_path)

                uploaded_files.append({
                    "field": field_name,
                    "filename": safe_name,
                    "stored_as": unique_name
                })

        extra_details["uploaded_documents"] = uploaded_files

        additional_details_json = json.dumps(
            extra_details,
            ensure_ascii=False
        )

        created_at = now_text()

        cursor = db.execute("""
            INSERT INTO applications
            (
                user_id,
                scholarship_id,
                scholarship_name,
                full_name,
                email,
                phone,
                state,
                course,
                college,
                academic_percentage,
                annual_family_income,
                category,
                gender,
                additional_details,
                status,
                otp_verified,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            user_id,
            scholarship_id,
            scholarship_name,
            full_name,
            email,
            phone,
            state,
            course,
            college,
            academic_percentage,
            annual_family_income,
            category,
            gender,
            additional_details_json,
            "Draft",
            0,
            created_at
        ))

        application_id = cursor.lastrowid

        db.commit()

        return jsonify({
            "success": True,
            "message": "Application created successfully.",
            "application_id": application_id,
            "id": application_id,
            "status": "Draft"
        })

    except Exception as e:

        db.rollback()

        return jsonify({
            "success": False,
            "message": f"Could not create application: {str(e)}"
        }), 500

    finally:
        db.close()


# =========================================================
# GET APPLICATIONS
# =========================================================

@app.route("/api/applications", methods=["GET"])
def get_applications():

    user_id = require_login()

    if not user_id:
        return jsonify({
            "success": False,
            "message": "Please login first."
        }), 401

    db = get_db()

    rows = db.execute("""
        SELECT *
        FROM applications
        WHERE user_id = ?
        ORDER BY id DESC
    """, (user_id,)).fetchall()

    db.close()

    applications = []

    for row in rows:

        item = dict(row)

        item["otp_verified"] = bool(
            item.get("otp_verified") or 0
        )

        applications.append(item)

    return jsonify({
        "success": True,
        "applications": applications,
        "results": applications,
        "data": applications
    })


# =========================================================
# GET SINGLE APPLICATION
# =========================================================

@app.route("/api/application/<int:application_id>", methods=["GET"])
def get_application(application_id):

    user_id = require_login()

    if not user_id:
        return jsonify({
            "success": False,
            "message": "Please login first."
        }), 401

    db = get_db()

    row = db.execute("""
        SELECT *
        FROM applications
        WHERE id = ?
        AND user_id = ?
        LIMIT 1
    """, (
        application_id,
        user_id
    )).fetchone()

    db.close()

    if not row:
        return jsonify({
            "success": False,
            "message": "Application not found."
        }), 404

    application = dict(row)

    if application.get("additional_details"):

        try:
            application["additional_details_parsed"] = json.loads(
                application["additional_details"]
            )
        except Exception:
            application["additional_details_parsed"] = {}

    application["otp_verified"] = bool(
        application.get("otp_verified") or 0
    )

    return jsonify({
        "success": True,
        "application": application
    })


# =========================================================
# DEMO OTP VERIFICATION
# =========================================================

@app.route(
    "/api/application/<int:application_id>/verify-otp",
    methods=["POST"]
)
def verify_otp(application_id):

    user_id = require_login()

    if not user_id:
        return jsonify({
            "success": False,
            "message": "Please login first."
        }), 401

    data = request.get_json(silent=True) or request.form.to_dict()

    otp = str(data.get("otp", "")).strip()

    # Demo OTP.
    if otp != "123456":

        return jsonify({
            "success": False,
            "message": "Invalid demo OTP."
        }), 400

    db = get_db()

    row = db.execute("""
        SELECT id
        FROM applications
        WHERE id = ?
        AND user_id = ?
        LIMIT 1
    """, (
        application_id,
        user_id
    )).fetchone()

    if not row:

        db.close()

        return jsonify({
            "success": False,
            "message": "Application not found."
        }), 404

    db.execute("""
        UPDATE applications
        SET
            otp_verified = 1,
            status = 'Ready for Official Submission'
        WHERE id = ?
        AND user_id = ?
    """, (
        application_id,
        user_id
    ))

    db.commit()
    db.close()

    return jsonify({
        "success": True,
        "message": "Demo OTP verified successfully.",
        "status": "Ready for Official Submission",
        "official_url": OFFICIAL_NSP
    })


# =========================================================
# HEALTH CHECK
# =========================================================

@app.route("/health")
@app.route("/api/health")
def health():
    return jsonify({"status": "ok"})


# =========================================================
# FAVICON
# =========================================================

@app.route("/favicon.ico")
def favicon():
    return "", 204


# =========================================================
# START SERVER
# =========================================================

if __name__ == "__main__":

    port = int(os.environ.get("PORT", 5000))

    print("==============================================")
    print("ScholarMatch AI")
    print("==============================================")
    print(f"Database: {DB_PATH}")
    print(f"Frontend: {FRONTEND_DIR}")
    print(f"Server: http://0.0.0.0:{port}")
    print("Demo OTP: 123456")
    print("==============================================")

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False
    )