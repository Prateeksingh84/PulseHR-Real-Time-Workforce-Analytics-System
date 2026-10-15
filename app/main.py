"""Employee Attendance & Analytics API.

Single-file implementation adhering to OpenAPI contract and business rules R1-R10.
Start with: uvicorn app.main:app --port 8000
"""

import calendar
import os
import re
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, List, Optional

from bson import ObjectId
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Path, Query, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field, field_validator
from pymongo import ASCENDING, DESCENDING, MongoClient, ReturnDocument
from pymongo.errors import DuplicateKeyError, PyMongoError

# Load .env without overriding environment variables set by grader
load_dotenv(override=False)

MONGO_URI = os.getenv("MONGO_URI", "mongodb://127.0.0.1:27017")
MONGO_DB = os.getenv("MONGO_DB", "attendance_db")

client: MongoClient = MongoClient(MONGO_URI, tz_aware=True)
db = client[MONGO_DB]

IST = timezone(timedelta(hours=5, minutes=30))


def ensure_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """Ensure datetime is timezone-aware UTC."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def init_db():
    """Create indexes idempotently at startup."""
    try:
        # employees collection
        db.employees.create_index([("emp_code", ASCENDING)], unique=True)
        db.employees.create_index([("department", ASCENDING), ("joined_on", ASCENDING)])
        db.employees.create_index([("joined_on", ASCENDING)])

        # attendance_logs collection
        db.attendance_logs.create_index([("emp_code", ASCENDING), ("date", ASCENDING)], unique=True)
        db.attendance_logs.create_index([("date", DESCENDING), ("emp_code", ASCENDING)])
        db.attendance_logs.create_index([("emp_code", ASCENDING), ("date", DESCENDING)])
        db.attendance_logs.create_index([("date", ASCENDING), ("late_minutes", ASCENDING)])
        db.attendance_logs.create_index([("status", ASCENDING), ("date", DESCENDING), ("emp_code", ASCENDING)])
    except Exception as e:
        print(f"Index creation warning: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="Employee Attendance & Analytics API",
    version="2.0.0",
    lifespan=lifespan,
)


# --------------------------------------------------------------------------- #
# Date / Time & Business Rule Helpers (R1 - R8)
# --------------------------------------------------------------------------- #
def truncate_to_seconds(dt: datetime) -> datetime:
    """R1: Truncate instants to whole seconds."""
    return dt.replace(microsecond=0)


def epoch_ms_to_datetime(ms: int) -> datetime:
    """Convert epoch milliseconds integer to UTC datetime truncated to seconds."""
    sec = ms // 1000
    return datetime.fromtimestamp(sec, tz=timezone.utc)


def datetime_to_epoch_ms(dt: Optional[datetime]) -> Optional[int]:
    """Convert datetime to epoch milliseconds integer."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def parse_hh_mm(hh_mm: str) -> tuple[int, int]:
    h, m = map(int, hh_mm.split(":"))
    return h, m


def get_attendance_date_and_shifts(
    punch_in_dt: datetime, shift_start: str, shift_end: str
) -> tuple[str, datetime, datetime]:
    """R1: Attendance date & shift instants in IST.

    Overnight shifts: shift_end <= shift_start.
    A punch-in earlier than shift_end belongs to the shift that started the previous day.
    Instants are truncated to whole seconds.
    """
    punch_in_trunc = truncate_to_seconds(punch_in_dt)
    punch_in_ist = punch_in_trunc.astimezone(IST)

    sh_h, sh_m = parse_hh_mm(shift_start)
    eh_h, eh_m = parse_hh_mm(shift_end)

    is_overnight = (eh_h, eh_m) <= (sh_h, sh_m)

    punch_time = (punch_in_ist.hour, punch_in_ist.minute, punch_in_ist.second)
    shift_end_time = (eh_h, eh_m, 0)

    if is_overnight and punch_time < shift_end_time:
        att_date = punch_in_ist.date() - timedelta(days=1)
    else:
        att_date = punch_in_ist.date()

    shift_start_dt = datetime(
        att_date.year, att_date.month, att_date.day, sh_h, sh_m, 0, tzinfo=IST
    )

    if is_overnight:
        shift_end_date = att_date + timedelta(days=1)
    else:
        shift_end_date = att_date

    shift_end_dt = datetime(
        shift_end_date.year,
        shift_end_date.month,
        shift_end_date.day,
        eh_h,
        eh_m,
        0,
        tzinfo=IST,
    )

    return att_date.isoformat(), shift_start_dt, shift_end_dt


def compute_late_minutes(punch_in_dt: datetime, shift_start_dt: datetime) -> int:
    """R2: Grace period 10 minutes.

    Late only if punch-in is strictly > 10:00 (600s) after shift_start;
    then whole minutes (floor) since shift_start.
    """
    diff_sec = (truncate_to_seconds(punch_in_dt) - shift_start_dt).total_seconds()
    if diff_sec > 600:
        return int(diff_sec // 60)
    return 0


def compute_work_hours(punch_in_dt: datetime, punch_out_dt: datetime) -> float:
    """R4: (punch_out - punch_in) in seconds / 3600, rounded 2 decimals half-up."""
    diff_sec = (truncate_to_seconds(punch_out_dt) - truncate_to_seconds(punch_in_dt)).total_seconds()
    hours = Decimal(diff_sec) / Decimal(3600)
    return float(hours.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def compute_overtime_minutes(punch_out_dt: datetime, shift_end_dt: datetime) -> int:
    """R3: Whole minutes (floor) from shift_end to punch_out, only if >= 30; else 0."""
    diff_sec = (truncate_to_seconds(punch_out_dt) - shift_end_dt).total_seconds()
    if diff_sec >= 1800:
        return int(diff_sec // 60)
    return 0


def compute_half_day(work_hours: Optional[float]) -> bool:
    """R5: Half day = true when rounded work_hours < 4.50."""
    if work_hours is None:
        return False
    return work_hours < 4.50


def round_half_up(value: Optional[float], decimals: int = 2) -> Optional[float]:
    """R8: Round reported numbers half-up."""
    if value is None:
        return None
    d = Decimal(str(value))
    target = Decimal("0." + "0" * (decimals - 1) + "1") if decimals > 0 else Decimal("1")
    return float(d.quantize(target, rounding=ROUND_HALF_UP))


def format_history_entry(entry: dict) -> dict:
    changes_formatted = {}
    for k, v in entry.get("changes", {}).items():
        if k in ("punch_in", "punch_out"):
            frm = datetime_to_epoch_ms(v.get("from")) if isinstance(v.get("from"), datetime) else v.get("from")
            to_val = datetime_to_epoch_ms(v.get("to")) if isinstance(v.get("to"), datetime) else v.get("to")
            changes_formatted[k] = {"from": frm, "to": to_val}
        else:
            changes_formatted[k] = {"from": v.get("from"), "to": v.get("to")}

    at_val = entry.get("at")
    if isinstance(at_val, datetime):
        at_val = datetime_to_epoch_ms(at_val)

    return {
        "at": at_val,
        "by": entry.get("by"),
        "reason": entry.get("reason"),
        "changes": changes_formatted,
    }


def format_attendance_doc(doc: dict) -> dict:
    """Format MongoDB attendance document to OpenAPI AttendanceRecord."""
    history_raw = doc.get("history") or []
    formatted_history = [format_history_entry(h) for h in history_raw]

    return {
        "emp_code": doc["emp_code"],
        "date": doc["date"],
        "status": doc["status"],
        "punch_in": datetime_to_epoch_ms(doc.get("punch_in")),
        "punch_out": datetime_to_epoch_ms(doc.get("punch_out")),
        "work_hours": doc.get("work_hours"),
        "late_minutes": doc.get("late_minutes", 0),
        "overtime_minutes": doc.get("overtime_minutes", 0),
        "half_day": doc.get("half_day", False),
        "history": formatted_history,
    }


def clean_bson(obj: Any) -> Any:
    """Recursively clean BSON objects for JSON responses."""
    if isinstance(obj, dict):
        return {k: clean_bson(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [clean_bson(v) for v in obj]
    elif isinstance(obj, datetime):
        return obj.isoformat()
    elif isinstance(obj, ObjectId):
        return str(obj)
    elif isinstance(obj, Decimal):
        return float(obj)
    return obj


# --------------------------------------------------------------------------- #
# Pydantic Schemas
# --------------------------------------------------------------------------- #
class EmployeeCreate(BaseModel):
    emp_code: str = Field(..., pattern=r"^EMP\d{4,6}$")
    name: str = Field(..., min_length=1, max_length=100)
    email: str = Field(..., max_length=120, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    department: str = Field(..., min_length=1, max_length=50)
    shift_start: str = Field("09:30", pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    shift_end: str = Field("18:30", pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    joined_on: str

    @field_validator("joined_on")
    @classmethod
    def validate_joined_on(cls, v: str) -> str:
        try:
            datetime.strptime(v, "%Y-%m-%d")
        except ValueError:
            raise ValueError("joined_on must be YYYY-MM-DD")
        return v

    @field_validator("shift_end")
    @classmethod
    def validate_shifts(cls, v: str, info) -> str:
        start = info.data.get("shift_start")
        if start and v == start:
            raise ValueError("shift_start must differ from shift_end")
        return v


class PunchInRequest(BaseModel):
    emp_code: str
    punched_at: Optional[int] = None
    status: str = "PRESENT"

    @field_validator("punched_at")
    @classmethod
    def validate_punched_at(cls, v: Optional[int]) -> Optional[int]:
        if v is not None:
            if not isinstance(v, int) or isinstance(v, bool):
                raise ValueError("punched_at must be an integer")
            if v < 100000000000 or v > 4102444800000:
                raise ValueError("punched_at out of range epoch milliseconds")
        return v

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        if v not in ("PRESENT", "WFH", "ON_DUTY"):
            raise ValueError("status must be PRESENT, WFH, or ON_DUTY")
        return v


class PunchOutRequest(BaseModel):
    emp_code: str
    punched_at: Optional[int] = None

    @field_validator("punched_at")
    @classmethod
    def validate_punched_at(cls, v: Optional[int]) -> Optional[int]:
        if v is not None:
            if not isinstance(v, int) or isinstance(v, bool):
                raise ValueError("punched_at must be an integer")
            if v < 100000000000 or v > 4102444800000:
                raise ValueError("punched_at out of range epoch milliseconds")
        return v


class RegularizeRequest(BaseModel):
    reason: str = Field(..., min_length=5, max_length=200)
    regularized_by: str = Field(..., min_length=1, max_length=50)
    status: Optional[str] = None
    punch_in: Optional[int] = None
    punch_out: Optional[int] = None

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in ("PRESENT", "ABSENT", "LEAVE", "WFH", "ON_DUTY"):
            raise ValueError("Invalid status")
        return v

    @field_validator("punch_in", "punch_out")
    @classmethod
    def validate_punch_times(cls, v: Optional[int]) -> Optional[int]:
        if v is not None:
            if not isinstance(v, int) or isinstance(v, bool):
                raise ValueError("Must be integer epoch milliseconds")
            if v < 100000000000 or v > 4102444800000:
                raise ValueError("Out of range epoch milliseconds")
        return v


# --------------------------------------------------------------------------- #
# Endpoints
# --------------------------------------------------------------------------- #
@app.get("/health")
def health():
    """Readiness probe: 200 only if MongoDB answers ping; else 503."""
    try:
        client.admin.command("ping")
        return {"status": "ok"}
    except PyMongoError:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Database unavailable")


DASHBOARD_FILE = os.path.join(os.path.dirname(__file__), "dashboard.html")


@app.get("/dashboard", response_class=HTMLResponse, include_in_schema=False)
@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def dashboard():
    """Real-time attendance & analytics dashboard."""
    if os.path.exists(DASHBOARD_FILE):
        with open(DASHBOARD_FILE, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse(content="<h1>Dashboard file not found</h1>", status_code=404)



@app.post("/employees", status_code=201)
def create_employee(body: EmployeeCreate):
    """Create an employee.

    Enforced unique emp_code via MongoDB unique index.
    """
    now_utc = truncate_to_seconds(datetime.now(timezone.utc))
    doc = body.model_dump()
    doc["created_at"] = now_utc

    try:
        db.employees.insert_one(doc)
    except DuplicateKeyError:
        raise HTTPException(status_code=409, detail="emp_code already exists")

    doc.pop("_id", None)
    doc["created_at"] = datetime_to_epoch_ms(now_utc)
    return doc


@app.get("/employees")
def list_employees(
    department: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """List employees sorted by emp_code ascending."""
    q = {}
    if department is not None:
        q["department"] = department

    skip = (page - 1) * page_size
    total = db.employees.count_documents(q)
    cursor = db.employees.find(q, {"_id": 0}).sort("emp_code", ASCENDING).skip(skip).limit(page_size)

    items = []
    for emp in cursor:
        if isinstance(emp.get("created_at"), datetime):
            emp["created_at"] = datetime_to_epoch_ms(emp["created_at"])
        items.append(emp)

    return {"items": items, "total": total, "page": page, "page_size": page_size}


@app.post("/attendance/punch-in", status_code=201)
def punch_in(body: PunchInRequest):
    """Record a punch-in.

    Race-safe with compound unique index (emp_code, date).
    """
    emp = db.employees.find_one({"emp_code": body.emp_code})
    if emp is None:
        raise HTTPException(status_code=404, detail="Employee not found")

    if body.punched_at is not None:
        ts_utc = epoch_ms_to_datetime(body.punched_at)
    else:
        ts_utc = truncate_to_seconds(datetime.now(timezone.utc))

    att_date, shift_start_dt, _ = get_attendance_date_and_shifts(
        ts_utc, emp["shift_start"], emp["shift_end"]
    )

    late_mins = compute_late_minutes(ts_utc, shift_start_dt)

    doc = {
        "emp_code": body.emp_code,
        "date": att_date,
        "status": body.status,
        "punch_in": ts_utc,
        "punch_out": None,
        "work_hours": None,
        "late_minutes": late_mins,
        "overtime_minutes": 0,
        "half_day": False,
        "history": [],
    }

    try:
        db.attendance_logs.insert_one(doc)
    except DuplicateKeyError:
        raise HTTPException(status_code=409, detail="already punched in for this date")

    return format_attendance_doc(doc)


@app.post("/attendance/punch-out")
def punch_out(body: PunchOutRequest):
    """Record a punch-out.

    Closes most recent record where punch_in <= punched_at.
    Two simultaneous punch-outs yield exactly one 200.
    """
    emp = db.employees.find_one({"emp_code": body.emp_code})
    if emp is None:
        raise HTTPException(status_code=404, detail="Employee not found")

    if body.punched_at is not None:
        out_utc = epoch_ms_to_datetime(body.punched_at)
    else:
        out_utc = truncate_to_seconds(datetime.now(timezone.utc))

    # Find the employee's most recent record whose punch_in <= out_utc
    record = db.attendance_logs.find_one(
        {"emp_code": body.emp_code, "punch_in": {"$lte": out_utc}},
        sort=[("punch_in", DESCENDING)],
    )

    if record is None:
        raise HTTPException(status_code=404, detail="No punch-in found")

    in_utc = ensure_utc(record["punch_in"])
    if out_utc <= in_utc or (out_utc - in_utc).total_seconds() > 24 * 3600:
        raise HTTPException(status_code=422, detail="punched_at must be after punch_in and within 24 hours")

    if record.get("punch_out") is not None:
        raise HTTPException(status_code=409, detail="Record already punched out")

    # Shift end computation
    _, _, shift_end_dt = get_attendance_date_and_shifts(
        in_utc, emp["shift_start"], emp["shift_end"]
    )

    work_hrs = compute_work_hours(in_utc, out_utc)
    ot_mins = compute_overtime_minutes(out_utc, shift_end_dt)
    half_day = compute_half_day(work_hrs)

    updated = db.attendance_logs.find_one_and_update(
        {"_id": record["_id"], "punch_out": None},
        {
            "$set": {
                "punch_out": out_utc,
                "work_hours": work_hrs,
                "overtime_minutes": ot_mins,
                "half_day": half_day,
            }
        },
        return_document=ReturnDocument.AFTER,
    )

    if updated is None:
        raise HTTPException(status_code=409, detail="Record already punched out")

    return format_attendance_doc(updated)


@app.get("/attendance")
def list_attendance(
    emp_code: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    status: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """List attendance records sorted by date descending, then emp_code ascending."""
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=422, detail="date_from cannot be greater than date_to")

    q = {}
    if emp_code:
        q["emp_code"] = emp_code
    if date_from or date_to:
        q["date"] = {}
        if date_from:
            q["date"]["$gte"] = date_from
        if date_to:
            q["date"]["$lte"] = date_to
    if status:
        q["status"] = status

    skip = (page - 1) * page_size
    total = db.attendance_logs.count_documents(q)
    cursor = (
        db.attendance_logs.find(q)
        .sort([("date", DESCENDING), ("emp_code", ASCENDING)])
        .skip(skip)
        .limit(page_size)
    )

    items = [format_attendance_doc(d) for d in cursor]
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@app.patch("/attendance/{emp_code}/{date}")
def regularize_attendance(
    emp_code: str = Path(...),
    date: str = Path(..., pattern=r"^\d{4}-\d{2}-\d{2}$"),
    body: RegularizeRequest = ...,
):
    """Regularize (manually correct) one day's record. Recompute derived fields and append to history."""
    emp = db.employees.find_one({"emp_code": emp_code})
    if emp is None:
        raise HTTPException(status_code=404, detail="Employee not found")

    record = db.attendance_logs.find_one({"emp_code": emp_code, "date": date})
    if record is None:
        raise HTTPException(status_code=404, detail="Attendance record not found")

    target_status = body.status if body.status is not None else record["status"]

    if target_status in ("ABSENT", "LEAVE"):
        if body.punch_in is not None or body.punch_out is not None:
            raise HTTPException(status_code=422, detail="Cannot provide punch times with ABSENT or LEAVE")
        final_in_dt = None
        final_out_dt = None
        final_work_hours = None
        final_late_minutes = 0
        final_overtime_minutes = 0
        final_half_day = False
    else:
        # Presence status
        if body.punch_in is not None:
            final_in_dt = epoch_ms_to_datetime(body.punch_in)
        else:
            final_in_dt = ensure_utc(record.get("punch_in"))

        if final_in_dt is None:
            raise HTTPException(status_code=422, detail="Presence status requires a punch_in")

        final_in_dt = truncate_to_seconds(final_in_dt)

        calc_date, shift_start_dt, shift_end_dt = get_attendance_date_and_shifts(
            final_in_dt, emp["shift_start"], emp["shift_end"]
        )
        if calc_date != date:
            raise HTTPException(status_code=422, detail="punch_in does not match record attendance date")

        final_late_minutes = compute_late_minutes(final_in_dt, shift_start_dt)

        if body.punch_out is not None:
            final_out_dt = truncate_to_seconds(epoch_ms_to_datetime(body.punch_out))
        else:
            final_out_dt = ensure_utc(record.get("punch_out"))
            if final_out_dt is not None:
                final_out_dt = truncate_to_seconds(final_out_dt)

        if final_out_dt is not None:
            if final_out_dt <= final_in_dt:
                raise HTTPException(status_code=422, detail="punch_out must be after punch_in")
            if (final_out_dt - final_in_dt).total_seconds() > 24 * 3600:
                raise HTTPException(status_code=422, detail="punch_out cannot be more than 24 hours after punch_in")
            final_work_hours = compute_work_hours(final_in_dt, final_out_dt)
            final_overtime_minutes = compute_overtime_minutes(final_out_dt, shift_end_dt)
            final_half_day = compute_half_day(final_work_hours)
        else:
            final_work_hours = None
            final_overtime_minutes = 0
            final_half_day = False

    # Detect field differences
    changes_db = {}
    old_status = record.get("status")
    if target_status != old_status:
        changes_db["status"] = {"from": old_status, "to": target_status}

    old_in = ensure_utc(record.get("punch_in"))
    if final_in_dt != old_in:
        changes_db["punch_in"] = {"from": old_in, "to": final_in_dt}

    old_out = ensure_utc(record.get("punch_out"))
    if final_out_dt != old_out:
        changes_db["punch_out"] = {"from": old_out, "to": final_out_dt}

    old_wh = record.get("work_hours")
    if final_work_hours != old_wh:
        changes_db["work_hours"] = {"from": old_wh, "to": final_work_hours}

    old_late = record.get("late_minutes", 0)
    if final_late_minutes != old_late:
        changes_db["late_minutes"] = {"from": old_late, "to": final_late_minutes}

    old_ot = record.get("overtime_minutes", 0)
    if final_overtime_minutes != old_ot:
        changes_db["overtime_minutes"] = {"from": old_ot, "to": final_overtime_minutes}

    old_hd = record.get("half_day", False)
    if final_half_day != old_hd:
        changes_db["half_day"] = {"from": old_hd, "to": final_half_day}

    if not changes_db:
        raise HTTPException(status_code=422, detail="Request changes nothing")

    history_now = truncate_to_seconds(datetime.now(timezone.utc))
    new_entry = {
        "at": history_now,
        "by": body.regularized_by,
        "reason": body.reason,
        "changes": changes_db,
    }

    # Optimistic Concurrency Control on history array
    existing_history = record.get("history")
    filter_q = {"_id": record["_id"]}
    if existing_history is None:
        filter_q["history"] = {"$in": [None, []]}
    else:
        filter_q["history"] = existing_history

    update_doc = {
        "$set": {
            "status": target_status,
            "punch_in": final_in_dt,
            "punch_out": final_out_dt,
            "work_hours": final_work_hours,
            "late_minutes": final_late_minutes,
            "overtime_minutes": final_overtime_minutes,
            "half_day": final_half_day,
        },
        "$push": {"history": new_entry},
    }

    res = db.attendance_logs.find_one_and_update(
        filter_q,
        update_doc,
        return_document=ReturnDocument.AFTER,
    )

    if res is None:
        raise HTTPException(status_code=409, detail="Concurrent modification conflict")

    return format_attendance_doc(res)


# --------------------------------------------------------------------------- #
# Analytics Pipelines
# --------------------------------------------------------------------------- #
def build_employee_monthly_pipeline(emp_code: str, month: str) -> list[dict]:
    y, m = map(int, month.split("-"))
    last_day = calendar.monthrange(y, m)[1]
    start_date = f"{month}-01"
    end_date = f"{month}-{last_day:02d}"
    return [
        {
            "$match": {
                "emp_code": emp_code,
                "date": {"$gte": start_date, "$lte": end_date},
            }
        },
        {
            "$project": {
                "is_weekday": {
                    "$lte": [
                        {
                            "$isoDayOfWeek": {
                                "$dateFromString": {
                                    "dateString": "$date",
                                    "format": "%Y-%m-%d",
                                }
                            }
                        },
                        5,
                    ]
                },
                "status": 1,
                "late_minutes": {"$ifNull": ["$late_minutes", 0]},
                "overtime_minutes": {"$ifNull": ["$overtime_minutes", 0]},
                "half_day": {"$ifNull": ["$half_day", False]},
            }
        },
        {
            "$group": {
                "_id": None,
                "present_days": {
                    "$sum": {
                        "$cond": [
                            {
                                "$and": [
                                    "$is_weekday",
                                    {"$in": ["$status", ["PRESENT", "WFH", "ON_DUTY"]]},
                                ]
                            },
                            {"$cond": ["$half_day", 0.5, 1.0]},
                            0.0,
                        ]
                    }
                },
                "leave_days": {
                    "$sum": {"$cond": [{"$eq": ["$status", "LEAVE"]}, 1, 0]}
                },
                "late_count": {
                    "$sum": {"$cond": [{"$gt": ["$late_minutes", 0]}, 1, 0]}
                },
                "total_late_minutes": {"$sum": "$late_minutes"},
                "total_overtime_minutes": {"$sum": "$overtime_minutes"},
            }
        },
    ]


@app.get("/analytics/employees/{emp_code}/monthly")
def employee_monthly(
    emp_code: str = Path(...),
    month: str = Query(..., pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
):
    """Monthly attendance summary for one employee."""
    emp = db.employees.find_one({"emp_code": emp_code})
    if emp is None:
        raise HTTPException(status_code=404, detail="Employee not found")

    # Calculate working days (R7)
    y, m = map(int, month.split("-"))
    days_in_month = calendar.monthrange(y, m)[1]
    month_start = date(y, m, 1)
    month_end = date(y, m, days_in_month)

    joined_d = datetime.strptime(emp["joined_on"], "%Y-%m-%d").date()
    if joined_d > month_end:
        working_days = 0
    else:
        cur = max(month_start, joined_d)
        working_days = 0
        while cur <= month_end:
            if cur.weekday() < 5:
                working_days += 1
            cur += timedelta(days=1)

    pipeline = build_employee_monthly_pipeline(emp_code, month)
    res = list(db.attendance_logs.aggregate(pipeline))

    if res:
        agg = res[0]
        present_days = float(agg.get("present_days", 0.0))
        leave_days = int(agg.get("leave_days", 0))
        late_count = int(agg.get("late_count", 0))
        total_late = int(agg.get("total_late_minutes", 0))
        total_ot = int(agg.get("total_overtime_minutes", 0))
    else:
        present_days = 0.0
        leave_days = 0
        late_count = 0
        total_late = 0
        total_ot = 0

    if working_days > 0:
        pct_raw = (present_days / working_days) * 100.0
        attendance_pct = round_half_up(pct_raw, 2)
    else:
        attendance_pct = None

    return {
        "emp_code": emp_code,
        "month": month,
        "working_days": working_days,
        "present_days": present_days,
        "leave_days": leave_days,
        "late_count": late_count,
        "total_late_minutes": total_late,
        "total_overtime_minutes": total_ot,
        "attendance_pct": attendance_pct,
    }


def build_department_summary_pipeline(month: str, department: Optional[str] = None) -> list[dict]:
    y, m = map(int, month.split("-"))
    last_day = calendar.monthrange(y, m)[1]
    start_date = f"{month}-01"
    end_date = f"{month}-{last_day:02d}"

    match_filter = {"joined_on": {"$lte": end_date}}
    if department:
        match_filter["department"] = department

    return [
        {"$match": match_filter},
        {
            "$lookup": {
                "from": "attendance_logs",
                "let": {"emp": "$emp_code"},
                "pipeline": [
                    {
                        "$match": {
                            "$expr": {
                                "$and": [
                                    {"$eq": ["$emp_code", "$$emp"]},
                                    {"$gte": ["$date", start_date]},
                                    {"$lte": ["$date", end_date]},
                                ]
                            }
                        }
                    }
                ],
                "as": "logs",
            }
        },
        {"$unwind": {"path": "$logs", "preserveNullAndEmptyArrays": True}},
        {
            "$project": {
                "department": 1,
                "emp_code": 1,
                "is_weekday": {
                    "$cond": [
                        {"$ifNull": ["$logs.date", False]},
                        {
                            "$lte": [
                                {
                                    "$isoDayOfWeek": {
                                        "$dateFromString": {
                                            "dateString": "$logs.date",
                                            "format": "%Y-%m-%d",
                                        }
                                    }
                                },
                                5,
                            ]
                        },
                        False,
                    ]
                },
                "status": "$logs.status",
                "half_day": {"$ifNull": ["$logs.half_day", False]},
                "work_hours": "$logs.work_hours",
                "late_minutes": {"$ifNull": ["$logs.late_minutes", 0]},
            }
        },
        {
            "$group": {
                "_id": "$department",
                "employees": {"$addToSet": "$emp_code"},
                "present_days": {
                    "$sum": {
                        "$cond": [
                            {
                                "$and": [
                                    "$is_weekday",
                                    {"$in": ["$status", ["PRESENT", "WFH", "ON_DUTY"]]},
                                ]
                            },
                            {"$cond": ["$half_day", 0.5, 1.0]},
                            0.0,
                        ]
                    }
                },
                "wh_sum": {
                    "$sum": {
                        "$cond": [
                            {
                                "$and": [
                                    {"$in": ["$status", ["PRESENT", "WFH", "ON_DUTY"]]},
                                    {"$ne": [{"$type": "$work_hours"}, "missing"]},
                                    {"$ne": ["$work_hours", None]},
                                ]
                            },
                            "$work_hours",
                            0.0,
                        ]
                    }
                },
                "wh_count": {
                    "$sum": {
                        "$cond": [
                            {
                                "$and": [
                                    {"$in": ["$status", ["PRESENT", "WFH", "ON_DUTY"]]},
                                    {"$ne": [{"$type": "$work_hours"}, "missing"]},
                                    {"$ne": ["$work_hours", None]},
                                ]
                            },
                            1,
                            0,
                        ]
                    }
                },
                "late_count": {
                    "$sum": {
                        "$cond": [{"$gt": ["$late_minutes", 0]}, 1, 0]
                    }
                },
                "total_late_minutes": {"$sum": "$late_minutes"},
                "leave_count": {
                    "$sum": {"$cond": [{"$eq": ["$status", "LEAVE"]}, 1, 0]}
                },
                "on_duty_count": {
                    "$sum": {"$cond": [{"$eq": ["$status", "ON_DUTY"]}, 1, 0]}
                },
            }
        },
        {
            "$project": {
                "_id": 0,
                "department": "$_id",
                "headcount": {"$size": "$employees"},
                "present_days": 1,
                "wh_sum": 1,
                "wh_count": 1,
                "late_count": 1,
                "total_late_minutes": 1,
                "leave_count": 1,
                "on_duty_count": 1,
            }
        },
        {"$sort": {"department": ASCENDING}},
    ]


@app.get("/analytics/departments/summary")
def department_summary(
    month: str = Query(..., pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
    department: Optional[str] = None,
):
    """Department summary for a month with cross-collection aggregation and R9 headcount."""
    pipeline = build_department_summary_pipeline(month, department)
    docs = list(db.employees.aggregate(pipeline))

    items = []
    for d in docs:
        if d["headcount"] == 0:
            continue
        wh_count = d.pop("wh_count", 0)
        wh_sum = d.pop("wh_sum", 0.0)
        if wh_count > 0:
            avg_wh = round_half_up(wh_sum / wh_count, 2)
        else:
            avg_wh = None
        d["avg_work_hours"] = avg_wh
        items.append(d)

    return {"month": month, "items": items}


def build_leaderboard_pipeline(
    month: str, limit: int = 10, department: Optional[str] = None
) -> list[dict]:
    y, m = map(int, month.split("-"))
    last_day = calendar.monthrange(y, m)[1]
    start_date = f"{month}-01"
    end_date = f"{month}-{last_day:02d}"

    pipeline = [
        {
            "$match": {
                "date": {"$gte": start_date, "$lte": end_date},
                "late_minutes": {"$gt": 0},
            }
        },
        {
            "$group": {
                "_id": "$emp_code",
                "total_late_minutes": {"$sum": "$late_minutes"},
                "late_count": {"$sum": 1},
            }
        },
        {
            "$lookup": {
                "from": "employees",
                "localField": "_id",
                "foreignField": "emp_code",
                "as": "emp",
            }
        },
        {"$unwind": "$emp"},
    ]

    if department:
        pipeline.append({"$match": {"emp.department": department}})

    pipeline.extend([
        {
            "$setWindowFields": {
                "sortBy": {"total_late_minutes": -1},
                "output": {"rank": {"$rank": {}}},
            }
        },
        {"$match": {"rank": {"$lte": limit}}},
        {
            "$project": {
                "_id": 0,
                "rank": 1,
                "emp_code": "$_id",
                "name": "$emp.name",
                "department": "$emp.department",
                "total_late_minutes": 1,
                "late_count": 1,
            }
        },
        {"$sort": {"total_late_minutes": DESCENDING, "emp_code": ASCENDING}},
    ])
    return pipeline


@app.get("/analytics/leaderboard/late")
def late_leaderboard(
    month: str = Query(..., pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
    limit: int = Query(10, ge=1, le=50),
    department: Optional[str] = None,
):
    """Late-comers leaderboard for a month using standard competition ranking with ties."""
    pipeline = build_leaderboard_pipeline(month, limit, department)
    items = list(db.attendance_logs.aggregate(pipeline))
    return {"month": month, "items": items}


def build_department_trend_pipeline(department: str, from_str: str, to_str: str) -> list[dict]:
    from_dt = datetime.strptime(from_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    to_dt = datetime.strptime(to_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    to_dt_plus_1 = to_dt + timedelta(days=1)

    return [
        {"$match": {"department": department}},
        {
            "$lookup": {
                "from": "attendance_logs",
                "let": {"emp": "$emp_code"},
                "pipeline": [
                    {
                        "$match": {
                            "$expr": {
                                "$and": [
                                    {"$eq": ["$emp_code", "$$emp"]},
                                    {"$gte": ["$date", from_str]},
                                    {"$lte": ["$date", to_str]},
                                ]
                            }
                        }
                    }
                ],
                "as": "logs",
            }
        },
        {"$unwind": "$logs"},
        {
            "$group": {
                "_id": "$logs.date",
                "present_count": {
                    "$sum": {
                        "$cond": [
                            {"$in": ["$logs.status", ["PRESENT", "WFH", "ON_DUTY"]]},
                            {"$cond": ["$logs.half_day", 0.5, 1.0]},
                            0.0,
                        ]
                    }
                },
                "late_count": {
                    "$sum": {
                        "$cond": [
                            {"$gt": [{"$ifNull": ["$logs.late_minutes", 0]}, 0]},
                            1,
                            0,
                        ]
                    }
                },
            }
        },
        {
            "$project": {
                "date_dt": {"$dateFromString": {"dateString": "$_id", "format": "%Y-%m-%d"}},
                "present_count": 1,
                "late_count": 1,
            }
        },
        {
            "$densify": {
                "field": "date_dt",
                "range": {
                    "step": 1,
                    "unit": "day",
                    "bounds": [from_dt, to_dt_plus_1],
                },
            }
        },
        {
            "$project": {
                "date": {"$dateToString": {"date": "$date_dt", "format": "%Y-%m-%d"}},
                "date_dt": 1,
                "is_working_day": {"$lte": [{"$isoDayOfWeek": "$date_dt"}, 5]},
                "present_count": {"$ifNull": ["$present_count", 0.0]},
                "late_count": {"$ifNull": ["$late_count", 0]},
            }
        },
        {
            "$lookup": {
                "from": "employees",
                "pipeline": [
                    {"$match": {"department": department}},
                    {"$project": {"_id": 0, "joined_on": 1}},
                ],
                "as": "dept_emps",
            }
        },
        {
            "$project": {
                "date": 1,
                "date_dt": 1,
                "is_working_day": 1,
                "present_count": 1,
                "late_count": 1,
                "headcount": {
                    "$size": {
                        "$filter": {
                            "input": "$dept_emps",
                            "as": "e",
                            "cond": {"$lte": ["$$e.joined_on", "$date"]},
                        }
                    }
                },
            }
        },
        {
            "$project": {
                "date": 1,
                "date_dt": 1,
                "is_working_day": 1,
                "present_count": 1,
                "late_count": 1,
                "headcount": 1,
                "attendance_rate": {
                    "$cond": [
                        {
                            "$and": [
                                "$is_working_day",
                                {"$gt": ["$headcount", 0]},
                            ]
                        },
                        {"$divide": ["$present_count", "$headcount"]},
                        None,
                    ]
                },
            }
        },
        {
            "$setWindowFields": {
                "sortBy": {"date_dt": 1},
                "output": {
                    "moving_avg_7d": {
                        "$avg": "$attendance_rate",
                        "window": {"documents": [-6, 0]},
                    }
                },
            }
        },
        {"$sort": {"date_dt": ASCENDING}},
        {
            "$project": {
                "_id": 0,
                "date": 1,
                "is_working_day": 1,
                "headcount": 1,
                "present_count": 1,
                "late_count": 1,
                "attendance_rate": 1,
                "moving_avg_7d": 1,
            }
        },
    ]


@app.get("/analytics/departments/{department}/trend")
def department_trend(
    department: str = Path(...),
    from_date: str = Query(..., alias="from", pattern=r"^\d{4}-\d{2}-\d{2}$"),
    to_date: str = Query(..., alias="to", pattern=r"^\d{4}-\d{2}-\d{2}$"),
):
    """Daily attendance trend for a department with $densify gap filling and 7d moving average."""
    dept_exists = db.employees.find_one({"department": department})
    if dept_exists is None:
        raise HTTPException(status_code=404, detail="Department not found")

    d_from = datetime.strptime(from_date, "%Y-%m-%d").date()
    d_to = datetime.strptime(to_date, "%Y-%m-%d").date()

    if d_to < d_from:
        raise HTTPException(status_code=422, detail="to cannot be before from")

    if (d_to - d_from).days > 92:
        raise HTTPException(status_code=422, detail="Range cannot exceed 92 days")

    pipeline = build_department_trend_pipeline(department, from_date, to_date)
    rows = list(db.employees.aggregate(pipeline))

    for r in rows:
        if r.get("attendance_rate") is not None:
            r["attendance_rate"] = round_half_up(r["attendance_rate"], 4)
        if r.get("moving_avg_7d") is not None:
            r["moving_avg_7d"] = round_half_up(r["moving_avg_7d"], 4)

    return {"department": department, "items": rows}


@app.get("/admin/explain/{endpoint}")
def explain_endpoint(
    endpoint: str = Path(..., pattern=r"^(attendance_list|employee_monthly|department_summary|late_leaderboard|department_trend)$"),
    emp_code: Optional[str] = None,
    month: Optional[str] = Query(None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
    department: Optional[str] = None,
    limit: int = Query(10, ge=1, le=50),
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    status: Optional[str] = None,
    from_date: Optional[str] = Query(None, alias="from"),
    to_date: Optional[str] = Query(None, alias="to"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """MongoDB explain with executionStats verbosity for an endpoint's main query."""
    if endpoint == "attendance_list":
        if date_from and date_to and date_from > date_to:
            raise HTTPException(status_code=422, detail="date_from > date_to")
        q = {}
        if emp_code:
            q["emp_code"] = emp_code
        if date_from or date_to:
            q["date"] = {}
            if date_from:
                q["date"]["$gte"] = date_from
            if date_to:
                q["date"]["$lte"] = date_to
        if status:
            q["status"] = status
        skip = (page - 1) * page_size
        raw_plan = db.command(
            "explain",
            {
                "find": "attendance_logs",
                "filter": q,
                "sort": {"date": DESCENDING, "emp_code": ASCENDING},
                "skip": skip,
                "limit": page_size,
            },
            verbosity="executionStats",
        )
        return {
            "endpoint": endpoint,
            "collection": "attendance_logs",
            "explain": clean_bson(raw_plan),
        }

    elif endpoint == "employee_monthly":
        if not emp_code or not month:
            raise HTTPException(status_code=422, detail="emp_code and month are required")
        pipeline = build_employee_monthly_pipeline(emp_code, month)
        raw_plan = db.command(
            "explain",
            {"aggregate": "attendance_logs", "pipeline": pipeline, "cursor": {}},
            verbosity="executionStats",
        )
        return {
            "endpoint": endpoint,
            "collection": "attendance_logs",
            "explain": clean_bson(raw_plan),
        }

    elif endpoint == "department_summary":
        if not month:
            raise HTTPException(status_code=422, detail="month is required")
        pipeline = build_department_summary_pipeline(month, department)
        raw_plan = db.command(
            "explain",
            {"aggregate": "employees", "pipeline": pipeline, "cursor": {}},
            verbosity="executionStats",
        )
        return {
            "endpoint": endpoint,
            "collection": "employees",
            "explain": clean_bson(raw_plan),
        }

    elif endpoint == "late_leaderboard":
        if not month:
            raise HTTPException(status_code=422, detail="month is required")
        pipeline = build_leaderboard_pipeline(month, limit, department)
        raw_plan = db.command(
            "explain",
            {"aggregate": "attendance_logs", "pipeline": pipeline, "cursor": {}},
            verbosity="executionStats",
        )
        return {
            "endpoint": endpoint,
            "collection": "attendance_logs",
            "explain": clean_bson(raw_plan),
        }

    elif endpoint == "department_trend":
        if not department or not from_date or not to_date:
            raise HTTPException(status_code=422, detail="department, from, and to are required")
        pipeline = build_department_trend_pipeline(department, from_date, to_date)
        raw_plan = db.command(
            "explain",
            {"aggregate": "employees", "pipeline": pipeline, "cursor": {}},
            verbosity="executionStats",
        )
        return {
            "endpoint": endpoint,
            "collection": "employees",
            "explain": clean_bson(raw_plan),
        }

    raise HTTPException(status_code=422, detail="Invalid explain endpoint")
