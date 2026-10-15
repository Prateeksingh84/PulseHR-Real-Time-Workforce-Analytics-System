<div align="center">

<!-- Animated waving header -->
<img src="https://capsule-render.vercel.app/api?type=waving&color=0:0f2027,50:203a43,100:2c5364&height=220&section=header&text=PulseHR&fontSize=80&fontColor=ffffff&animation=fadeIn&fontAlignY=38&desc=Real-Time%20Workforce%20Analytics%20System&descAlignY=60&descSize=22" alt="PulseHR header" width="100%"/>

<!-- Animated typing banner -->
<a href="https://git.io/typing-svg">
  <img src="https://readme-typing-svg.demolab.com?font=Fira+Code&weight=600&size=22&duration=3000&pause=800&color=00D4FF&center=true&vCenter=true&width=820&lines=Employee+Attendance+%26+Biometric+Punch+Lifecycle;SHA-256+Cryptographic+Audit+Trail+Regularizations;Real-Time+SSE+Push+Streams;MongoDB+7.0+Aggregation+Analytics;Race-Safe.+IST-Aware.+Production-Grade." alt="Typing animation" />
</a>

<br/>

![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white)
![Pydantic](https://img.shields.io/badge/Pydantic-v2-E92063?style=for-the-badge&logo=pydantic&logoColor=white)
![MongoDB](https://img.shields.io/badge/MongoDB-7.0-47A248?style=for-the-badge&logo=mongodb&logoColor=white)
![PyMongo](https://img.shields.io/badge/PyMongo-4.7%2B-13AA52?style=for-the-badge&logo=mongodb&logoColor=white)
![Uvicorn](https://img.shields.io/badge/Uvicorn-ASGI-499848?style=for-the-badge&logo=gunicorn&logoColor=white)

![Timezone](https://img.shields.io/badge/Timezone-IST%20(UTC%2B05%3A30)-orange?style=flat-square)
![Index Scans](https://img.shields.io/badge/Explain-IXSCAN%20only%20%7C%200%20COLLSCAN-brightgreen?style=flat-square)
![Rate Limit](https://img.shields.io/badge/Rate%20Limit-300%20req%2Fmin-blue?style=flat-square)
![Audit](https://img.shields.io/badge/Audit-SHA--256-blueviolet?style=flat-square)
![Status](https://img.shields.io/badge/Status-Production--Grade-success?style=flat-square)

<br/>

**[Features](#-features)** •
**[Architecture](#-architecture)** •
**[Business Rules](#-business-rules-r1--r10)** •
**[Concurrency](#-race-safety--concurrency)** •
**[Analytics](#-analytics-endpoints)** •
**[Quick Start](#-quick-start)** •
**[Repository](#-repository-contents)**

</div>

---

## 📖 Overview

> **Enterprise Employee Attendance, Biometric Punch Lifecycle & MongoDB 7.0 Aggregation Analytics Platform**

**PulseHR** is a production-grade **FastAPI + MongoDB** service for:

- 🕒 Tracking employee attendance and punch-in / punch-out business rules
- 🔐 Cryptographic **SHA-256** audit trail for attendance regularizations
- 📡 Real-time **Server-Sent Events (SSE)** push streams
- 📊 High-performance reporting powered by **MongoDB 7.0 aggregation pipelines**

---

## 🧰 Tech Stack

| Layer | Technology |
|:------|:-----------|
| 🐍 **Language** | Python 3.11+ |
| ⚡ **Framework** | FastAPI, Pydantic v2 |
| 🍃 **Database** | MongoDB 6.0+ *(tested against MongoDB 7.0.14)* |
| 🔌 **Driver** | PyMongo 4.7+ |
| 🚀 **Server** | Uvicorn |

---

## ✨ Features

<table>
<tr>
<td width="50%" valign="top">

### 📏 Business Rules (R1 – R10)
- India Standard Time (IST, UTC+05:30)
- Overnight shift support
- 10-minute grace period (`> 10:00`)
- 30-minute minimum overtime threshold
- Mathematical **half-up** rounding via `Decimal`
- Working-days logic

</td>
<td width="50%" valign="top">

### 🛡️ Race Safety & Concurrency
- Atomic `(emp_code, date)` constraint
- Atomic `find_one_and_update` on `punch_out: None`
- Optimistic concurrency control on `history`
- No lost audit trails

</td>
</tr>
<tr>
<td width="50%" valign="top">

### 📈 Aggregations & Analytics
- Monthly presence / leave / late stats
- Cross-collection department summary
- Competition-ranked late leaderboard
- Gap-filled trends with moving averages

</td>
<td width="50%" valign="top">

### 🔎 Explain Endpoint
- Validates index usage on **100k+ records**
- Asserts `IXSCAN`, **0** `COLLSCAN`
- Available at `/admin/explain/{endpoint}`

</td>
</tr>
</table>

---

## 🏗️ Architecture

```mermaid
flowchart LR
    A[Biometric Terminal / Dashboard] -->|HTTP| B[FastAPI App]
    B --> C[(MongoDB 7.0)]
    B -->|SSE /events| D[Live Clients]
    B --> E[Rate Limiter<br/>300 req/min per IP]
    B --> F[Security Headers]
    C --> G[Aggregation Pipelines]
    G --> B
```

### 🔄 Punch Lifecycle

```mermaid
stateDiagram-v2
    [*] --> PunchedIn: Punch-in (201)
    PunchedIn --> PunchedIn: Duplicate punch-in (409)
    PunchedIn --> PunchedOut: Punch-out (200)
    PunchedOut --> PunchedOut: Repeat punch-out (409)
    PunchedOut --> Regularized: Manual correction + SHA-256 audit entry
    Regularized --> Regularized: Further regularizations (optimistic concurrency)
```

---

## 📏 Business Rules (R1 – R10)

| Concern | Rule |
|:--------|:-----|
| 🌏 **Timezone** | Strict India Standard Time (IST, UTC+05:30) |
| 🌙 **Shifts** | Overnight shifts supported |
| ⏱️ **Grace period** | 10 minutes — late if punch-in is after `10:00` |
| ➕ **Overtime** | Counted only at a 30-minute minimum threshold |
| 🔢 **Rounding** | Mathematical half-up using Python `Decimal` |
| 📅 **Working days** | Working-days logic applied to attendance calculations |

---

## 🛡️ Race Safety & Concurrency

```mermaid
sequenceDiagram
    participant C1 as Client 1
    participant C2 as Client 2
    participant API as FastAPI
    participant DB as MongoDB
    C1->>API: Punch-in
    C2->>API: Punch-in (simultaneous)
    API->>DB: Insert (unique emp_code + date)
    DB-->>API: OK
    DB-->>API: Duplicate key
    API-->>C1: 201 Created
    API-->>C2: 409 Conflict
```

| Scenario | Mechanism | Guaranteed Outcome |
|:---------|:----------|:-------------------|
| Simultaneous punch-ins | Atomic constraint on `(emp_code, date)` | Exactly **one 201**, the rest **409** |
| Simultaneous punch-outs | Atomic `find_one_and_update` on `punch_out: None` | Exactly **one 200** |
| Concurrent regularizations | Optimistic concurrency control on `history` | No lost audit trail |

---

## 📊 Analytics Endpoints

| Endpoint | Description |
|:---------|:------------|
| `GET /analytics/employees/{emp_code}/monthly` | Monthly presence, leave, late count, and half-up percentage |
| `GET /analytics/departments/summary` | Cross-collection pipeline counting headcounts with zero logs (R9) and average work hours across records |
| `GET /analytics/leaderboard/late` | Standard competition ranking (1, 2, 2, 4) via `$setWindowFields` + `$rank`, limits applied **post-ranking** |
| `GET /analytics/departments/{department}/trend` | Calendar-gap densification via `$densify` and 7-day moving averages via `$setWindowFields` |
| `GET /admin/explain/{endpoint}` | Query plan validation — `IXSCAN`, 0 `COLLSCAN` on 100k+ records |
| `GET /events` | Server-Sent Events stream for creations, punches, and regularizations |

---

## 🚀 Quick Start

### 1️⃣ Environment & Dependencies

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# Linux / macOS
source .venv/bin/activate

python -m pip install -r requirements.txt
```

### 2️⃣ Configure Environment

Set `MONGO_URI` and `MONGO_DB` (or define them in a local `.env`):

```bash
# Default values if omitted:
# MONGO_URI="mongodb://localhost:27017"
# MONGO_DB="attendance_db"
```

### 3️⃣ Seed Realistic Workforce & Attendance

```bash
# Seeds 25 employees across 9 departments with 225 real attendance logs and audit history
python seed_workforce.py
```

### 4️⃣ Run the Application

```bash
uvicorn app.main:app --port 8000
```

> 💡 Indexes are created **idempotently at startup** during the lifespan event — no manual migration needed.

---

## 🖥️ Live Surfaces

| Surface | URL | What you get |
|:--------|:----|:-------------|
| 📊 **Admin Dashboard** | [http://localhost:8000/dashboard](http://localhost:8000/dashboard) (or `/`) | Live KPI cards, interactive biometric punch terminal, 30-day attendance trends, manual correction modal, cryptographic audit log inspection |
| 📘 **OpenAPI Docs** | [http://localhost:8000/docs](http://localhost:8000/docs) | Interactive API documentation |
| 📡 **SSE Stream** | `GET /events` | Instant push updates on employee creations, punches, and regularizations |

<details>
<summary><b>🔒 Enterprise Security (click to expand)</b></summary>

<br/>

- Production headers: `X-Frame-Options`, `X-Content-Type-Options`, `X-RateLimit-Limit`
- IP sliding-window rate limiting: **300 requests / minute**

</details>

<details>
<summary><b>📡 Try the live stream (click to expand)</b></summary>

<br/>

```bash
curl -N http://localhost:8000/events
```

Then punch in from the dashboard and watch events arrive instantly.

</details>

---

## 📂 Repository Contents

```text
candidate_kit/
├── app/
│   └── main.py            # Complete application implementation (single file)
├── sample_data/           # Seed data
├── sample_seed.py         # Seed data loader script
├── seed_workforce.py      # Realistic workforce & attendance seeder
├── requirements.txt       # Python package requirements
├── REVIEW.md              # Detailed audit and defect report for starter code
├── DECISIONS.md           # Indexing, concurrency, ranking, headcount, scaling strategies
├── DATA_MODEL.md          # Collection structures and field conventions
├── openapi.yaml           # OpenAPI 3.0 specification contract
└── README.md              # You are here
```

| File | Purpose |
|:-----|:--------|
| `app/main.py` | Complete application implementation in a single file |
| `requirements.txt` | Python package requirements |
| `REVIEW.md` | Detailed audit and defect report for starter code |
| `DECISIONS.md` | Explanations of indexing, concurrency, ranking, headcount, and scaling strategies |
| `DATA_MODEL.md` | Specification of collection structures and field conventions |
| `openapi.yaml` | OpenAPI 3.0 specification contract |
| `sample_seed.py` & `sample_data/` | Seed data and loader script |

---

<div align="center">

<img src="https://readme-typing-svg.demolab.com?font=Fira+Code&size=16&duration=2500&pause=1000&color=2C5364&center=true&vCenter=true&width=600&lines=Built+with+FastAPI+%2B+MongoDB+7.0;Every+punch+counted.+Every+change+audited." alt="Footer typing" />

<img src="https://capsule-render.vercel.app/api?type=waving&color=0:2c5364,50:203a43,100:0f2027&height=120&section=footer" alt="footer" width="100%"/>

</div>
