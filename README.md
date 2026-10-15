# Employee Attendance & Analytics API

A FastAPI and MongoDB service for tracking employee attendance, punch-in/out business rules, audit trail regularizations, and reporting analytics powered by MongoDB aggregation pipelines.

## Tech Stack
- **Language**: Python 3.11+
- **Framework**: FastAPI, Pydantic v2
- **Database**: MongoDB 6.0+ (Tested against MongoDB 7.0.14)
- **Driver**: PyMongo 4.7+
- **Server**: Uvicorn

## Features & Implementation
- **Business Rules (R1 - R10)**: Strict adherence to India Standard Time (IST, UTC+05:30), overnight shifts, 10-minute grace period (`> 10:00`), 30-minute minimum overtime threshold, mathematical half-up rounding (`Decimal`), and working days logic.
- **Race Safety & Concurrency**:
  - Atomic constraint on `(emp_code, date)` prevents double punch-ins (yielding exactly one 201 and the rest 409).
  - Atomic `find_one_and_update` on `punch_out: None` ensures exactly one 200 for simultaneous punch-outs.
  - Optimistic concurrency control on `history` prevents lost audit trails during concurrent regularizations.
- **Aggregations & Analytics**:
  - `GET /analytics/employees/{emp_code}/monthly`: Monthly presence, leave, late count, and half-up percentage.
  - `GET /analytics/departments/summary`: Cross-collection pipeline counting headcounts with zero logs (R9) and average work hours across records.
  - `GET /analytics/leaderboard/late`: Standard competition ranking (1, 2, 2, 4) using `$setWindowFields` and `$rank`, applying limits post-ranking.
  - `GET /analytics/departments/{department}/trend`: Calendar-gap densification via `$densify` and 7-day moving averages via `$setWindowFields`.
- **Explain Endpoint (`/admin/explain/{endpoint}`)**:
  - Validates index usage (`IXSCAN`, 0 `COLLSCAN`) on 100k+ records.

## Local Setup & Run

### 1. Environment & Dependencies
```bash
python -m venv .venv
# On Windows: .venv\Scripts\activate
# On Linux/macOS: source .venv/bin/activate

python -m pip install -r requirements.txt
```

### 2. Configure Environment
Set `MONGO_URI` and `MONGO_DB` (or define in a local `.env`):
```bash
# Default values if omitted:
# MONGO_URI="mongodb://localhost:27017"
# MONGO_DB="attendance_db"
```

### 3. Seed Realistic Workforce & Attendance
```bash
# Seed 25 employees across 9 departments with 225 real attendance logs and audit history:
python seed_workforce.py
```

### 4. Run Application
```bash
uvicorn app.main:app --port 8000
```
- **Real-Time Admin Dashboard**: Open [http://localhost:8000/dashboard](http://localhost:8000/dashboard) (or root `/`) in any modern browser for live KPI cards, interactive biometric punch terminal, 30-day attendance trends, manual correction modal, and cryptographic audit log inspection.
- **Interactive OpenAPI Documentation**: Open [http://localhost:8000/docs](http://localhost:8000/docs).
- **Real-Time SSE Stream**: Connect to `GET /events` for instant server-sent push updates on employee creations, punches, and regularizations.
- **Enterprise Security**: Production headers (`X-Frame-Options`, `X-Content-Type-Options`, `X-RateLimit-Limit`) and IP sliding-window rate limiting (300 req/min).

Indexes are automatically created idempotently at application startup during the lifespan event.

## Repository Contents
- `app/main.py`: Complete application implementation in a single file.
- `requirements.txt`: Python package requirements.
- `REVIEW.md`: Detailed audit and defect report for starter code.
- `DECISIONS.md`: Explanations of indexing, concurrency, ranking, headcount, and scaling strategies.
- `DATA_MODEL.md`: Specification of collection structures and field conventions.
- `openapi.yaml`: OpenAPI 3.0 specification contract.
- `sample_seed.py` & `sample_data/`: Seed data and loader script.
