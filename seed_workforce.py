"""Seed script to populate MongoDB with a realistic enterprise workforce (25+ employees, attendance logs, and audit trails).

Usage:
    python seed_workforce.py
"""

import hashlib
import os
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP

from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI", "mongodb://127.0.0.1:27017")
MONGO_DB = os.getenv("MONGO_DB", "attendance_db")

client = MongoClient(MONGO_URI, tz_aware=True)
db = client[MONGO_DB]

IST = timezone(timedelta(hours=5, minutes=30))

EMPLOYEES = [
    {"emp_code": "EMP0001", "name": "Asha Rao", "email": "asha.rao@example.com", "department": "Engineering", "shift_start": "09:30", "shift_end": "18:30", "joined_on": "2026-01-05"},
    {"emp_code": "EMP0002", "name": "Vikram Mehta", "email": "vikram.mehta@example.com", "department": "Engineering", "shift_start": "09:30", "shift_end": "18:30", "joined_on": "2026-02-10"},
    {"emp_code": "EMP0003", "name": "Neha Iyer", "email": "neha.iyer@example.com", "department": "Sales", "shift_start": "09:30", "shift_end": "18:30", "joined_on": "2026-02-01"},
    {"emp_code": "EMP0004", "name": "Rahul Sharma", "email": "rahul.sharma@example.com", "department": "Sales", "shift_start": "09:30", "shift_end": "18:30", "joined_on": "2026-02-01"},
    {"emp_code": "EMP0005", "name": "Priya Nair", "email": "priya.nair@example.com", "department": "Support", "shift_start": "22:00", "shift_end": "06:00", "joined_on": "2026-03-10"},
    {"emp_code": "EMP0006", "name": "Aman Verma", "email": "aman.verma@example.com", "department": "Support", "shift_start": "14:00", "shift_end": "22:00", "joined_on": "2026-03-15"},
    {"emp_code": "EMP0007", "name": "Arjun Patel", "email": "arjun.patel@example.com", "department": "Engineering", "shift_start": "09:30", "shift_end": "18:30", "joined_on": "2026-01-15"},
    {"emp_code": "EMP0008", "name": "Sneha Kulkarni", "email": "sneha.k@example.com", "department": "HR", "shift_start": "09:00", "shift_end": "18:00", "joined_on": "2026-01-20"},
    {"emp_code": "EMP0009", "name": "Rohan Gupta", "email": "rohan.gupta@example.com", "department": "Marketing", "shift_start": "10:00", "shift_end": "19:00", "joined_on": "2026-02-15"},
    {"emp_code": "EMP0010", "name": "Ananya Deshmukh", "email": "ananya.d@example.com", "department": "Product", "shift_start": "09:30", "shift_end": "18:30", "joined_on": "2026-01-10"},
    {"emp_code": "EMP0011", "name": "Karthik Reddy", "email": "karthik.r@example.com", "department": "Engineering", "shift_start": "09:30", "shift_end": "18:30", "joined_on": "2026-03-01"},
    {"emp_code": "EMP0012", "name": "Meera Nambiar", "email": "meera.n@example.com", "department": "Product", "shift_start": "10:00", "shift_end": "19:00", "joined_on": "2026-03-05"},
    {"emp_code": "EMP0013", "name": "Devendra Singh", "email": "devendra.s@example.com", "department": "Operations", "shift_start": "08:30", "shift_end": "17:30", "joined_on": "2026-01-08"},
    {"emp_code": "EMP0014", "name": "Pooja Chawla", "email": "pooja.c@example.com", "department": "Finance", "shift_start": "09:00", "shift_end": "18:00", "joined_on": "2026-02-12"},
    {"emp_code": "EMP0015", "name": "Siddharth Sen", "email": "siddharth.s@example.com", "department": "Engineering", "shift_start": "09:30", "shift_end": "18:30", "joined_on": "2026-02-18"},
    {"emp_code": "EMP0016", "name": "Ritu Bhattacharya", "email": "ritu.b@example.com", "department": "Support", "shift_start": "06:00", "shift_end": "14:00", "joined_on": "2026-02-25"},
    {"emp_code": "EMP0017", "name": "Manish Joshi", "email": "manish.j@example.com", "department": "Sales", "shift_start": "09:30", "shift_end": "18:30", "joined_on": "2026-03-12"},
    {"emp_code": "EMP0018", "name": "Tanvi Kapoor", "email": "tanvi.k@example.com", "department": "Marketing", "shift_start": "10:00", "shift_end": "19:00", "joined_on": "2026-03-18"},
    {"emp_code": "EMP0019", "name": "Gaurav Malhotra", "email": "gaurav.m@example.com", "department": "Operations", "shift_start": "09:00", "shift_end": "18:00", "joined_on": "2026-02-05"},
    {"emp_code": "EMP0020", "name": "Divya Pillai", "email": "divya.p@example.com", "department": "HR", "shift_start": "09:30", "shift_end": "18:30", "joined_on": "2026-03-01"},
    {"emp_code": "EMP0021", "name": "Kunal Saxena", "email": "kunal.s@example.com", "department": "Engineering", "shift_start": "09:30", "shift_end": "18:30", "joined_on": "2026-03-20"},
    {"emp_code": "EMP0022", "name": "Swati Sundaram", "email": "swati.s@example.com", "department": "Product", "shift_start": "09:30", "shift_end": "18:30", "joined_on": "2026-02-22"},
    {"emp_code": "EMP0023", "name": "Abhishek Roy", "email": "abhishek.r@example.com", "department": "Finance", "shift_start": "09:00", "shift_end": "18:00", "joined_on": "2026-03-25"},
    {"emp_code": "EMP0024", "name": "Nidhi Agrawal", "email": "nidhi.a@example.com", "department": "Legal", "shift_start": "09:30", "shift_end": "18:30", "joined_on": "2026-02-08"},
    {"emp_code": "EMP0025", "name": "Zeeshan Khan", "email": "zeeshan.k@example.com", "department": "Support", "shift_start": "22:00", "shift_end": "06:00", "joined_on": "2026-03-28"}
]


def make_dt_utc(d: date, hh: int, mm: int) -> datetime:
    base = datetime(d.year, d.month, d.day, 0, 0, 0, tzinfo=IST)
    return (base + timedelta(hours=hh, minutes=mm)).astimezone(timezone.utc)


def seed():
    print("Seeding realistic enterprise workforce into MongoDB...")

    # 1. Clear existing documents
    db.employees.delete_many({})
    db.attendance_logs.delete_many({})

    # 2. Insert employees
    emp_docs = []
    for e in EMPLOYEES:
        doc = dict(e)
        doc["created_at"] = datetime.strptime(e["joined_on"], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        emp_docs.append(doc)
    db.employees.insert_many(emp_docs)
    print(f"[OK] Loaded {len(emp_docs)} employee records into 'attendance_db.employees'")

    # 3. Generate attendance records spanning July 2026 and current day
    # Let's seed rich historical records for 2026-07 (matching the kit's analytics test cases)
    # as well as today's live records so live date shows immediate activity!
    today = datetime.now(timezone.utc).astimezone(IST).date()
    dates_to_seed = [
        date(2026, 7, 6), date(2026, 7, 7), date(2026, 7, 8), date(2026, 7, 9),
        date(2026, 7, 10), date(2026, 7, 13), date(2026, 7, 14), date(2026, 7, 15),
        today
    ]

    logs = []

    for d in dates_to_seed:
        is_today = (d == today)
        for emp in EMPLOYEES:
            joined = datetime.strptime(emp["joined_on"], "%Y-%m-%d").date()
            if d < joined:
                continue

            emp_code = emp["emp_code"]
            sh_h, sh_m = map(int, emp["shift_start"].split(":"))
            eh_h, eh_m = map(int, emp["shift_end"].split(":"))

            # Determine status & timing
            # Default: present on time
            status = "PRESENT"
            late_mins = 0
            ot_mins = 0
            half_day = False
            history = []

            # Specific variance cases for rich analytics:
            if emp_code in ("EMP0011", "EMP0018", "EMP0023") and d.day % 3 == 0:
                # Leave / Absent
                status = "LEAVE" if d.day % 2 == 0 else "ABSENT"
                in_dt = None
                out_dt = None
                work_hours = 0.0
            elif emp_code in ("EMP0009", "EMP0017"):
                # Work from Home
                status = "WFH"
                in_dt = make_dt_utc(d, sh_h, sh_m)
                if is_today:
                    out_dt = None
                    work_hours = None
                else:
                    out_dt = make_dt_utc(d, eh_h, eh_m)
                    work_hours = 9.0
            elif emp_code in ("EMP0003", "EMP0007", "EMP0015") and d.day % 2 == 0:
                # Late arrival
                late_mins = 25 if emp_code == "EMP0003" else (18 if emp_code == "EMP0007" else 35)
                arr_m = sh_m + late_mins
                arr_h = sh_h + arr_m // 60
                arr_m %= 60
                in_dt = make_dt_utc(d, arr_h, arr_m)
                if is_today:
                    out_dt = None
                    work_hours = None
                else:
                    out_dt = make_dt_utc(d, eh_h, eh_m + 15)
                    work_hours = 9.0
                    ot_mins = 0
            else:
                # Regular present
                in_dt = make_dt_utc(d, sh_h, max(0, sh_m - 5))
                if is_today:
                    # Some clocked in active, some already clocked out
                    if int(emp_code[-2:]) % 2 == 0:
                        out_dt = None
                        work_hours = None
                    else:
                        out_dt = make_dt_utc(d, eh_h, eh_m)
                        diff_sec = (out_dt - in_dt).total_seconds()
                        work_hours = float((Decimal(diff_sec) / Decimal(3600)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
                else:
                    out_end_d = d + timedelta(days=1) if (eh_h, eh_m) <= (sh_h, sh_m) else d
                    out_dt = make_dt_utc(out_end_d, eh_h, eh_m + (35 if emp_code == "EMP0001" else 0))
                    if emp_code == "EMP0001":
                        ot_mins = 35
                    diff_sec = (out_dt - in_dt).total_seconds()
                    work_hours = float((Decimal(diff_sec) / Decimal(3600)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

            # Add an audit history entry for regularized cases
            if emp_code == "EMP0003" and d == date(2026, 7, 6):
                hist_ts = datetime(2026, 7, 6, 18, 45, 0, tzinfo=timezone.utc)
                audit_hash = hashlib.sha256(f"EMP0003:2026-07-06:punch_out:hr.lead".encode()).hexdigest()
                history.append({
                    "regularized_by": "hr.lead",
                    "timestamp": hist_ts,
                    "reason": "Biometric sensor timeout during evening egress batch",
                    "changes": {
                        "punch_out": {
                            "from": None,
                            "to": out_dt
                        }
                    },
                    "checksum": f"sha256:{audit_hash}"
                })
            elif emp_code == "EMP0007" and d == date(2026, 7, 7):
                hist_ts = datetime(2026, 7, 7, 11, 20, 0, tzinfo=timezone.utc)
                audit_hash = hashlib.sha256(f"EMP0007:2026-07-07:punch_in:deepak.manager".encode()).hexdigest()
                history.append({
                    "regularized_by": "deepak.manager",
                    "timestamp": hist_ts,
                    "reason": "On-site badge reader latency acknowledged at Gate 2",
                    "changes": {
                        "punch_in": {
                            "from": make_dt_utc(d, sh_h + 1, 0),
                            "to": in_dt
                        }
                    },
                    "checksum": f"sha256:{audit_hash}"
                })

            doc = {
                "emp_code": emp_code,
                "date": d.isoformat(),
                "status": status,
                "punch_in": in_dt,
                "punch_out": out_dt,
                "work_hours": work_hours,
                "late_minutes": late_mins,
                "overtime_minutes": ot_mins,
                "half_day": half_day,
                "history": history
            }
            logs.append(doc)

    db.attendance_logs.insert_many(logs)
    print(f"[OK] Loaded {len(logs)} attendance documents into 'attendance_db.attendance_logs'")
    print("Database seeding completed successfully.")


if __name__ == "__main__":
    seed()
