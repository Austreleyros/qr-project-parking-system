# app.py (FULL FIXED VERSION WITH WORKING ADMIN LOGIN)
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
import psycopg2
import psycopg2.extras
import qrcode
import os
from datetime import datetime, date
import time
import json

app = Flask(__name__)
app.secret_key = "ADMIN"


# -----------------------------
# Database Config
# -----------------------------
DB_HOST = "localhost"
DB_NAME = "parking_system"
DB_USER = "postgres"
DB_PASS = "leyrosxvi"

# -----------------------------
# QR Code Folder
# -----------------------------
QR_FOLDER = os.path.join("static", "qrcodes")
os.makedirs(QR_FOLDER, exist_ok=True)

# -----------------------------
# Load Config (customizable home text)
# -----------------------------
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")
DEFAULT_CONFIG = {
    "home_title": "QR-BASED PARKING MANAGEMENT SYSTEM",
    "home_subtitle": "Manage vehicles, logs and parking areas.",
    "home_left_text": "Welcome to CSC Parking Registration!",
    "home_right_text": "Please complete the form to register your vehicle."
}

try:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        CONFIG = json.load(f)
except Exception:
    CONFIG = DEFAULT_CONFIG

# Make CONFIG available in templates
@app.context_processor
def inject_config():
    return {"config": CONFIG}

# -----------------------------
# Database Helper
# -----------------------------
def query_db(query, args=(), fetch=True, one=False):
    conn = None
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASS
        )
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(query, args)

        if fetch:
            data = cur.fetchall()
            if one:
                return data[0] if data else None
            return data

        conn.commit()
        return None
    finally:
        if conn:
            conn.close()


# -----------------------------
# Cooldown
# -----------------------------
scan_cooldown = {}
COOLDOWN_SEC = 2.5



# -----------------------------
# Extract plate from QR text
# -----------------------------
def extract_plate(qr_text: str):
    if not qr_text:
        return ""
    first_line = qr_text.splitlines()[0].strip()
    if first_line.lower().startswith("plate:"):
        return first_line.split(":", 1)[1].strip()
    return first_line



# -----------------------------
# Registration
# -----------------------------
@app.route("/", methods=["GET", "POST"])
def register():
    left_text = CONFIG.get("home_left_text", "")
    right_text = CONFIG.get("home_right_text", "")

    if request.method == "POST":
        full_name = request.form.get("full_name")
        id_number = request.form.get("id_number")
        vehicle_type = request.form.get("vehicle_type")
        mobile_no = request.form.get("mobile_no")
        plate_number = request.form.get("plate_number")

        try:
            query_db(
                "INSERT INTO users (full_name, id_number, vehicle_type, mobile_no, plate_number) "
                "VALUES (%s,%s,%s,%s,%s)",
                (full_name, id_number, vehicle_type, mobile_no, plate_number),
                fetch=False
            )
        except Exception as e:
            return render_template(
                "index.html",
                message=f"DB Error: {e}",
                left_text=left_text,
                right_text=right_text
            )

        qr_data = f"Plate: {plate_number}\nValid Until: {datetime.now().strftime('%Y-%m-%d')}"
        img = qrcode.make(qr_data)
        img.save(os.path.join(QR_FOLDER, f"{plate_number}.png"))

        return render_template("success.html", plate_number=plate_number)

    return render_template(
        "index.html",
        left_text=left_text,
        right_text=right_text
    )



# -----------------------------
# ADMIN LOGIN (FIXED)
# -----------------------------
ADMIN_PASSWORD = "ADMIN"

@app.route("/admin_login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        pw = request.form.get("password")

        if pw == ADMIN_PASSWORD:
            session["admin"] = True
            return redirect(url_for("admin_dashboard"))

        return render_template("admin_login.html", error="Incorrect password")

    return render_template("admin_login.html")



@app.route("/admin_logout")
def admin_logout():
    session.pop("admin", None)
    return redirect(url_for("admin_login"))





# -----------------------------
# Records (still uses its own password page)
# -----------------------------
@app.route("/records_password", methods=["GET", "POST"])
def records_password():
    if request.method == "POST":
        pw = request.form.get("password")

        if pw == ADMIN_PASSWORD:
            session["validated"] = True
            return redirect(url_for("records"))

        return render_template("records_password.html", error="Incorrect password")

    return render_template("records_password.html")



@app.route("/records")
def records():
    if "validated" not in session:
        return redirect(url_for("records_password"))

    users = query_db("SELECT * FROM users")
    session.pop("validated", None)
    return render_template("records.html", users=users)







# -----------------------------
# Logs
# -----------------------------
@app.route("/logs")
def logs():
    logs = query_db("SELECT * FROM parking_logs ORDER BY id DESC")
    return render_template("logs.html", logs=logs)



# -----------------------------
# Entry/Exit Page
# -----------------------------
@app.route("/entry_exit", methods=["GET", "POST"])
def entry_exit():
    message = ""

    if request.method == "POST":
        plate = request.form.get("plate_number")
        now = datetime.now()

        last_log = query_db(
            "SELECT id, time_out FROM parking_logs WHERE plate_number=%s "
            "ORDER BY id DESC LIMIT 1",
            (plate,)
        )

        entering = (not last_log) or (last_log[0]["time_out"] is not None)

        try:
            if entering:
                query_db(
                    "INSERT INTO parking_logs (plate_number, time_in) VALUES (%s,%s)",
                    (plate, now),
                    fetch=False
                )
                message = f"{plate} entered at {now}"
            else:
                query_db(
                    "UPDATE parking_logs SET time_out=%s WHERE plate_number=%s AND time_out IS NULL",
                    (now, plate),
                    fetch=False
                )
                message = f"{plate} exited at {now}"
        except Exception as e:
            message = f"DB error: {e}"

    return render_template("entry_exit.html", message=message)



# -----------------------------
# Browser QR Scan
# -----------------------------
@app.route("/scan_qr_browser", methods=["POST"])
def scan_qr_browser():
    payload = request.get_json() or {}
    plate = extract_plate(payload.get("plate_number", "")).strip()
    now = datetime.now()

    if not plate:
        return jsonify({"status": "error", "message": "No plate found"}), 400

    t = time.time()
    if t - scan_cooldown.get(plate, 0) < COOLDOWN_SEC:
        return jsonify({"status": "ignored", "message": "Duplicate scan"}), 200

    scan_cooldown[plate] = t

    try:
        last_log = query_db(
            "SELECT id, time_out FROM parking_logs WHERE plate_number=%s "
            "ORDER BY id DESC LIMIT 1",
            (plate,)
        )

        entering = (not last_log) or (last_log[0]["time_out"] is not None)

        if entering:
            query_db(
                "INSERT INTO parking_logs (plate_number, time_in) VALUES (%s,%s)",
                (plate, now),
                fetch=False
            )
            return jsonify({"status": "entered", "plate": plate, "time": str(now)})
        else:
            query_db(
                "UPDATE parking_logs SET time_out=%s WHERE plate_number=%s AND time_out IS NULL",
                (now, plate),
                fetch=False
            )
            return jsonify({"status": "exited", "plate": plate, "time": str(now)})

    except Exception as e:
        return jsonify({"status": "error", "message": f"DB error: {e}"}), 500





# -----------------------------
# History
# -----------------------------
@app.route("/history")
def history():
    logs = query_db(
        "SELECT id, plate_number, time_in, time_out, parking_area "
        "FROM parking_logs ORDER BY id DESC"
    )
    return render_template("history.html", logs=logs)




# -----------------------------
# Select Area
# -----------------------------
@app.route("/select_area")
def select_area():
    areas = query_db(
        "SELECT area_code, area_name, capacity, current_count "
        "FROM parking_areas ORDER BY area_code"
    )
    return render_template("select_area.html", areas=areas)




# -----------------------------
# Scanner Page
# -----------------------------
@app.route("/scanner/<area_code>")
def scanner_page(area_code):
    area = query_db(
        "SELECT area_code, area_name, capacity, current_count FROM parking_areas WHERE area_code=%s",
        (area_code,), one=True
    )

    if not area:
        return "Area not found", 404

    return render_template("scanner.html", area=area)




# -----------------------------
# Scan Area
# -----------------------------
@app.route("/scan_area/<area_code>", methods=["POST"])
def scan_area(area_code):
    payload = request.get_json() or {}
    plate_raw = payload.get("qr_text", "") or payload.get("plate_number", "")
    plate = extract_plate(plate_raw).strip()
    now = datetime.now()

    if not plate:
        return jsonify({"status": "error", "message": "No plate found"}), 400

    key = (area_code, plate)
    t = time.time()

    if t - scan_cooldown.get(key, 0) < COOLDOWN_SEC:
        return jsonify({"status": "ignored", "message": "Duplicate scan"}), 200

    scan_cooldown[key] = t

    try:
        area_info = query_db(
            "SELECT area_name, capacity, current_count FROM parking_areas WHERE area_code=%s",
            (area_code,), one=True
        )

        if not area_info:
            return jsonify({"status": "error", "message": "Unknown area"}), 404

        name = area_info["area_name"]
        cap = area_info["capacity"]
        count = area_info["current_count"]

        # Check last parking status
        last_log = query_db(
            "SELECT id, time_out FROM parking_logs WHERE plate_number=%s ORDER BY id DESC LIMIT 1",
            (plate,)
        )

        # If vehicle is currently inside ANY parking area → update only parking_area
        if last_log and last_log[0]["time_out"] is None:

            query_db(
                "UPDATE parking_logs SET parking_area=%s WHERE id=%s",
                (area_code, last_log[0]["id"]),
                fetch=False
            )

            return jsonify({
                "status": "updated",
                "plate": plate,
                "area": area_code,
                "area_name": name,
                "time": str(now),
                "note": "Vehicle already inside, parking area updated."
            })

        # Vehicle is entering
        else:
            if count >= cap:
                return jsonify({"status": "full", "message": f"{name} is full"}), 200

            query_db(
                "INSERT INTO parking_logs (plate_number, time_in, parking_area) VALUES (%s,%s,%s)",
                (plate, now, area_code),
                fetch=False
            )

            query_db(
                "UPDATE parking_areas SET current_count = current_count + 1 WHERE area_code=%s",
                (area_code,),
                fetch=False
            )

            return jsonify({
                "status": "entered",
                "plate": plate,
                "area": area_code,
                "area_name": name,
                "occupancy": count + 1,
                "time": str(now)
            })

    except Exception as e:
        return jsonify({"status": "error", "message": f"DB error: {e}"}), 500





# -----------------------------
# Delete Vehicle
# -----------------------------
@app.route("/delete_vehicle/<plate_number>")
def delete_vehicle(plate_number):
    try:
        query_db(
            "DELETE FROM users WHERE plate_number=%s",
            (plate_number,),
            fetch=False
        )

        qr_path = os.path.join(QR_FOLDER, f"{plate_number}.png")
        if os.path.exists(qr_path):
            os.remove(qr_path)

        message = f"Vehicle {plate_number} deleted successfully."

    except Exception as e:
        message = f"Error deleting vehicle: {e}"

    users = query_db("SELECT * FROM users")
    return render_template("records.html", users=users, message=message)





# -----------------------------
# Search endpoint
# -----------------------------
@app.route("/search")
def search():
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify({"logs": [], "vehicles": []})

    like = f"%{q}%"

    try:
        logs = query_db(
            "SELECT id, plate_number, time_in, time_out, parking_area FROM parking_logs "
            "WHERE plate_number ILIKE %s OR CAST(id AS TEXT)=%s "
            "ORDER BY id DESC LIMIT 200",
            (like, q)
        )

        vehicles = query_db(
            "SELECT plate_number, full_name, vehicle_type, mobile_no FROM users "
            "WHERE plate_number ILIKE %s OR full_name ILIKE %s "
            "ORDER BY plate_number LIMIT 200",
            (like, like)
        )

    except Exception as e:
        return jsonify({"error": str(e), "logs": [], "vehicles": []}), 500

    return jsonify({
        "logs": logs if logs else [],
        "vehicles": vehicles if vehicles else []
    })






# -----------------------------
# Admin Dashboard (unchanged)
# -----------------------------
@app.route("/admin_dashboard")
def admin_dashboard():

    if "admin" not in session:
        return redirect(url_for("admin_login"))

    # ------------------------------------
    # SUMMARY COUNTS
    # ------------------------------------
    users_today = query_db(
        "SELECT COUNT(*) AS count FROM users WHERE DATE(created_at) = CURRENT_DATE",
        one=True
    )["count"]

    total_registered = query_db(
        "SELECT COUNT(*) AS count FROM users",
        one=True
    )["count"]

    active_parked = query_db(
        "SELECT COUNT(*) AS count FROM parking_logs WHERE time_out IS NULL",
        one=True
    )["count"]

    entries_today = query_db(
        "SELECT COUNT(*) AS count FROM parking_logs WHERE DATE(time_in) = CURRENT_DATE",
        one=True
    )["count"]

    exits_today = query_db(
        "SELECT COUNT(*) AS count FROM parking_logs WHERE DATE(time_out) = CURRENT_DATE",
        one=True
    )["count"]

    overstay = query_db("""
        SELECT plate_number
        FROM parking_logs
        WHERE time_out IS NULL 
        AND DATE(time_in) < CURRENT_DATE
    """)
    overstay_count = len(overstay)

    # ------------------------------------
    # PARKING LOT SUMMARY
    # ------------------------------------
    areas = query_db(
        "SELECT area_code, area_name, capacity FROM parking_areas ORDER BY area_code"
    )

    active_logs = query_db(
        "SELECT plate_number, parking_area FROM parking_logs WHERE time_out IS NULL"
    )

    # Build mapping: area -> plates inside
    area_occupants = {area["area_code"]: [] for area in areas}

    for log in active_logs:
        if log["parking_area"] in area_occupants:
            area_occupants[log["parking_area"]].append(log["plate_number"])

    # Build final parking_lots list using correct field names
    parking_lots = []
    for area in areas:
        code = area["area_code"]

        parking_lots.append({
            "area_code": code,                       # ⭐ FIXED
            "name": f"Lot {code}",
            "area_name": area["area_name"],
            "capacity": area["capacity"],
            "current_count": len(area_occupants[code]),
            "parked_today": area_occupants[code]
        })


    # ------------------------------------
    # DAILY REPORT
    # ------------------------------------
    daily_entries = query_db("""
        SELECT DATE(time_in) AS day, COUNT(*) AS total
        FROM parking_logs
        GROUP BY DATE(time_in)
        ORDER BY DATE(time_in) DESC
        LIMIT 30
    """)

    daily_report = [
        {
            "date": row["day"],
            "entries": row["total"],
            "exits": query_db(
                "SELECT COUNT(*) AS c FROM parking_logs WHERE DATE(time_out)=%s",
                (row["day"],),
                one=True
            )["c"]
        }
        for row in daily_entries
    ]

    # ------------------------------------
    # MONTHLY REPORT
    # ------------------------------------
    monthly_entries = query_db("""
        SELECT TO_CHAR(DATE_TRUNC('month', time_in), 'YYYY-MM') AS month,
               COUNT(*) AS total
        FROM parking_logs
        GROUP BY DATE_TRUNC('month', time_in)
        ORDER BY DATE_TRUNC('month', time_in) DESC
    """)

    monthly_report = [
        {
            "month": m["month"],
            "entries": m["total"],
            "exits": query_db(
                "SELECT COUNT(*) AS c FROM parking_logs "
                "WHERE TO_CHAR(DATE_TRUNC('month', time_out), 'YYYY-MM') = %s",
                (m["month"],),
                one=True
            )["c"]
        }
        for m in monthly_entries
    ]

    # ------------------------------------
    # RENDER TEMPLATE
    # ------------------------------------
    return render_template(
        "admin_dashboard.html",
        total_registered_today=users_today,
        total_registered=total_registered,
        active_parked=active_parked,
        entries_today=entries_today,
        exits_today=exits_today,
        overstay_count=overstay_count,
        parking_lots=parking_lots,
        daily_report=daily_report,
        monthly_report=monthly_report
    )






# ---------------- DAILY CLICK VIEW ---------------- #
@app.route("/view_daily/<date_text>")
def view_daily(date_text):
    vehicles = query_db(
        """
        SELECT * FROM parking_logs
        WHERE DATE(time_in) = %s
        ORDER BY time_in DESC
        """,
        (date_text,)
    )

    return render_template("view_daily.html", date=date_text, vehicles=vehicles)



# ---------------- MONTH CLICK VIEW ---------------- #
@app.route("/view_month/<month>")
def view_month(month):
    vehicles = query_db(
        """
        SELECT * FROM parking_logs
        WHERE TO_CHAR(DATE_TRUNC('month', time_in), 'YYYY-MM') = %s
        ORDER BY time_in DESC
        """,
        (month,)
    )

    return render_template("view_month.html", month=month, vehicles=vehicles)

@app.route("/daily_summary")
def daily_summary():

    summary = query_db("""
        SELECT 
            DATE(time_in) AS date,
            COUNT(*) AS total_entries,
            SUM(CASE WHEN time_out IS NOT NULL THEN 1 ELSE 0 END) AS total_exits
        FROM parking_logs
        GROUP BY DATE(time_in)
        ORDER BY DATE(time_in) DESC
    """)

    return render_template("daily_summary.html", summary=summary)

@app.route("/view_lot/<lot_code>")
def view_lot(lot_code):
    # FIXED: parking_lots → parking_areas
    lot = query_db("""
        SELECT area_code, area_name, capacity, current_count
        FROM parking_areas
        WHERE area_code = %s
    """, (lot_code,), one=True)

    if not lot:
        return f"Parking lot '{lot_code}' not found", 404

    # FIXED: parking_logs uses parking_area, NOT area_code
    # FIXED: status='IN' does NOT exist → use time_out IS NULL
    vehicles = query_db("""
        SELECT plate_number, time_in 
        FROM parking_logs
        WHERE parking_area = %s 
        AND time_out IS NULL
        ORDER BY time_in DESC
    """, (lot_code,))

    return render_template(
        "view_lot.html",
        lot=lot,
        vehicles=vehicles
    )



@app.route('/dashboard')
def dashboard_only():

    total_registered_today = query_db("SELECT COUNT(*) AS c FROM registered WHERE DATE(registration_date)=CURDATE()", one=True)["c"]

    total_registered = query_db("SELECT COUNT(*) AS c FROM registered", one=True)["c"]

    active_parked = query_db("SELECT COUNT(*) AS c FROM parking_logs WHERE time_out IS NULL", one=True)["c"]

    entries_today = query_db("SELECT COUNT(*) AS c FROM parking_logs WHERE DATE(time_in)=CURDATE()", one=True)["c"]

    exits_today = query_db("SELECT COUNT(*) AS c FROM parking_logs WHERE DATE(time_out)=CURDATE()", one=True)["c"]

    overstay_count = query_db(
        "SELECT COUNT(*) AS c FROM parking_logs WHERE time_out IS NULL AND DATE(time_in) < CURDATE()",
        one=True
    )["c"]

    return render_template(
        'dashboard.html',
        total_registered_today=total_registered_today,
        total_registered=total_registered,
        active_parked=active_parked,
        entries_today=entries_today,
        exits_today=exits_today,
        overstay_count=overstay_count
    )
# ---------------- FIXED DASHBOARD EXTRA VIEWS (POSTGRES SAFE) ---------------- #

@app.route('/view_registered_today')
def registered_today_page():
    users = query_db(
        "SELECT * FROM users WHERE DATE(created_at) = CURRENT_DATE"
    )
    return render_template("admin_dashboard.html", section="registered_today", users=users)


@app.route('/view_total_registered')
def total_registered_page():
    users = query_db("SELECT * FROM users")
    return render_template("admin_dashboard.html", section="total_registered", users=users)


@app.route('/view_active_parked')
def active_parked_page():
    vehicles = query_db(
        "SELECT * FROM parking_logs WHERE time_out IS NULL"
    )
    return render_template("admin_dashboard.html", section="active_parked", vehicles=vehicles)


@app.route('/view_entries_today')
def entries_today_page():
    entries = query_db(
        "SELECT * FROM parking_logs WHERE DATE(time_in) = CURRENT_DATE"
    )
    return render_template("admin_dashboard.html", section="entries_today", entries=entries)

@app.route('/view_exits_today')
def exits_today_page():
    exits = query_db(
        "SELECT * FROM parking_logs WHERE DATE(time_out) = CURRENT_DATE"
    )
    return render_template("admin_dashboard.html", section="exits_today", exits=exits)


@app.route("/view_overstay")
def view_overstay():

    vehicles = query_db("""
        SELECT plate_number, time_in, parking_area
        FROM parking_logs
        WHERE time_out IS NULL
        AND DATE(time_in) < CURRENT_DATE
        ORDER BY time_in DESC
    """)

    # 🔁 RELOAD DASHBOARD DATA (same as admin_dashboard)
    users_today = query_db(
        "SELECT COUNT(*) AS count FROM users WHERE DATE(created_at) = CURRENT_DATE",
        one=True
    )["count"]

    total_registered = query_db(
        "SELECT COUNT(*) AS count FROM users",
        one=True
    )["count"]

    active_parked = query_db(
        "SELECT COUNT(*) AS count FROM parking_logs WHERE time_out IS NULL",
        one=True
    )["count"]

    entries_today = query_db(
        "SELECT COUNT(*) AS count FROM parking_logs WHERE DATE(time_in) = CURRENT_DATE",
        one=True
    )["count"]

    exits_today = query_db(
        "SELECT COUNT(*) AS count FROM parking_logs WHERE DATE(time_out) = CURRENT_DATE",
        one=True
    )["count"]

    overstay_count = len(vehicles)

    # Parking lots
    areas = query_db(
        "SELECT area_code, area_name, capacity FROM parking_areas ORDER BY area_code"
    )

    active_logs = query_db(
        "SELECT plate_number, parking_area FROM parking_logs WHERE time_out IS NULL"
    )

    area_occupants = {area["area_code"]: [] for area in areas}
    for log in active_logs:
        if log["parking_area"] in area_occupants:
            area_occupants[log["parking_area"]].append(log["plate_number"])

    parking_lots = []
    for area in areas:
        code = area["area_code"]
        parking_lots.append({
            "area_code": code,
            "name": f"Lot {code}",
            "area_name": area["area_name"],
            "capacity": area["capacity"],
            "current_count": len(area_occupants[code]),
            "parked_today": area_occupants[code]
        })

    # Daily Report
    daily_entries = query_db("""
        SELECT DATE(time_in) AS day, COUNT(*) AS total
        FROM parking_logs
        GROUP BY DATE(time_in)
        ORDER BY DATE(time_in) DESC
        LIMIT 30
    """)

    daily_report = [
        {
            "date": row["day"],
            "entries": row["total"],
            "exits": query_db(
                "SELECT COUNT(*) AS c FROM parking_logs WHERE DATE(time_out)=%s",
                (row["day"],),
                one=True
            )["c"]
        }
        for row in daily_entries
    ]

    # Monthly Report
    monthly_entries = query_db("""
        SELECT TO_CHAR(DATE_TRUNC('month', time_in), 'YYYY-MM') AS month,
               COUNT(*) AS total
        FROM parking_logs
        GROUP BY DATE_TRUNC('month', time_in)
        ORDER BY DATE_TRUNC('month', time_in) DESC
    """)

    monthly_report = [
        {
            "month": m["month"],
            "entries": m["total"],
            "exits": query_db(
                "SELECT COUNT(*) AS c FROM parking_logs "
                "WHERE TO_CHAR(DATE_TRUNC('month', time_out), 'YYYY-MM') = %s",
                (m["month"],),
                one=True
            )["c"]
        }
        for m in monthly_entries
    ]

    return render_template(
        "admin_dashboard.html",
        section="overstay",
        vehicles=vehicles,
        total_registered_today=users_today,
        total_registered=total_registered,
        active_parked=active_parked,
        entries_today=entries_today,
        exits_today=exits_today,
        overstay_count=overstay_count,
        parking_lots=parking_lots,
        daily_report=daily_report,
        monthly_report=monthly_report
    )









# -----------------------------
# Run App
# -----------------------------
if __name__ == "__main__":
    app.run(debug=True)
