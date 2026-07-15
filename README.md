# PipelineIQ — AI-Powered Lead Qualification & Outreach Agent

![PipelineIQ](https://img.shields.io/badge/status-production--ready-blue)
![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115%2B-green)
![React](https://img.shields.io/badge/React-18-blue)
![LangGraph](https://img.shields.io/badge/LangGraph-0.2%2B-orange)
![License](https://img.shields.io/badge/license-MIT-green)

PipelineIQ is an intelligent lead qualification and outreach automation system that leverages LLMs (via OpenRouter), LangGraph workflows, and a human-in-the-loop approval gate to process leads from intake through email outreach.

**Bootcamp Demo • Production Quality • 387+ Automated Tests**

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           PipelineIQ System                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌──────────┐    ┌──────────────────────────────────────────────────────┐  │
│  │          │    │               FastAPI Backend                         │  │
│  │  React   │    │                                                       │  │
│  │ Frontend │◄──►│  ┌──────────┐  ┌──────────┐  ┌────────────────────┐  │  │
│  │          │    │  │  Lead    │  │  Audit   │  │  LangGraph          │  │  │
│  │ Dashboard│    │  │  CRUD    │  │  Logs    │  │  Workflow           │  │  │
│  │ Add Lead │    │  │  API     │  │  API     │  │  ┌──────────────┐  │  │  │
│  │ Detail   │    │  │          │  │          │  │  │ Lead Intake  │  │  │  │
│  │ Approvals│    │  │  POST    │  │  GET     │  │  │              │  │  │  │
│  │ Audit Log│    │  │  /lead   │  │  /logs/  │  │  │  ↓           │  │  │  │
│  │          │    │  │  GET     │  │  {id}    │  │  │ Enrichment   │  │  │  │
│  └──────────┘    │  │  /lead/  │  │          │  │  │              │  │  │  │
│       │          │  │  {id}    │  └──────────┘  │  │  ↓           │  │  │  │
│       │          │  │  GET                      │  │ Scoring      │  │  │  │
│       │          │  │  /leads  │  ┌──────────┐  │  │              │  │  │  │
│       │          │  │  POST    │  │ Approval │  │  │  ↓           │  │  │  │
│       │  Vite    │  │  /approve│  │  API     │  │  │ Fairness     │  │  │  │
│       │  Proxy   │  │  POST    │  │          │  │  │              │  │  │  │
│       │  /api →  │  │  /reject │  │  POST    │  │  │  ↓           │  │  │  │
│       │  :8000   │  │  PUT     │  │  /approve│  │  │ Classify     │  │  │  │
│       │          │  │  /draft  │  │  /{id}   │  │  │              │  │  │  │
│       ▼          │  │          │  │  POST    │  │  │  ↓           │  │  │  │
│  ┌──────────┐    │  │  ┌──────┐│  │  /reject │  │  │ Draft Email  │  │  │  │
│  │Browser   │    │  │  │Dash  ││  │  /{id}   │  │  │              │  │  │  │
│  │:5173     │    │  │  │Board ││  │  PUT     │  │  │  ↓           │  │  │  │
│  └──────────┘    │  │  │Stats ││  │  /draft  │  │  │ Human Gate   │  │  │  │
│                  │  │  └──────┘│  │  /{id}   │  │  │              │  │  │  │
│                  │  └──────────┘  └──────────┘  │  │  ↓           │  │  │  │
│                  │                               │  │ Send Email   │  │  │  │
│                  │  ┌──────────────────────────┐ │  └──────────────┘  │  │  │
│                  │  │   SQLite (pipelineiq.db) │ │                    │  │  │
│                  │  │  ┌────────────────────┐  │ │  ┌──────────────┐  │  │  │
│                  │  │  │ Leads  │ Scores    │  │ │  │ OpenRouter   │  │  │  │
│                  │  │  │ Enrichment         │  │ │  │ GPT-4o       │  │  │  │
│                  │  │  │ Classifications    │  │ │  └──────────────┘  │  │  │
│                  │  │  │ DraftEmails        │  │ │                    │  │  │
│                  │  │  │ Approvals          │  │ │  ┌──────────────┐  │  │  │
│                  │  │  │ AuditLogs          │  │ │  │ LangSmith    │  │  │  │
│                  │  │  └────────────────────┘  │ │  │ Tracing      │  │  │  │
│                  │  └──────────────────────────┘ │  └──────────────┘  │  │  │
│                  └──────────────────────────────────────────────────────┘  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## LangGraph Workflow

```
┌─────────────────────────────────────────────────────────────────────┐
│                    PipelineIQ LangGraph Workflow                     │
│                                                                     │
│  INPUT: Lead Data (name, email, company, role, industry, signals)   │
│                                                                     │
│  ┌──────────────┐                                                    │
│  │  Lead Intake  │────► Sanitize inputs ────► Check prompt injection │
│  │  Agent        │     Normalize fields     Log injection attempts   │
│  └──────┬───────┘                                                    │
│         │                                                            │
│         ▼                                                            │
│  ┌──────────────┐                                                    │
│  │  Enrichment   │────► Lookup company data ──► Enrich lead record   │
│  │  Agent        │     Company size, location, industry, employees   │
│  └──────┬───────┘                                                    │
│         │                                                            │
│         ▼                                                            │
│  ┌──────────────┐                                                    │
│  │  Scoring      │────► LLM evaluates ──► Score 0-100 ──► Confidence │
│  │  Agent        │     Reasons for score     Fairness check applied  │
│  └──────┬───────┘                                                    │
│         │                                                            │
│         ▼                                                            │
│  ┌──────────────┐                                                    │
│  │  Fairness     │────► Demographic parity check                     │
│  │  Check        │     Bias detection     Score adjustment           │
│  └──────┬───────┘                                                    │
│         │                                                            │
│         ▼                                                            │
│  ┌──────────────┐                                                    │
│  │  Classify     │────► LLM classifies ──► hot / nurture / disqualify│
│  │  Agent        │     Explanation for classification                │
│  └──────┬───────┘                                                    │
│         │                                                            │
│         ▼                                                            │
│  ┌──────────────┐                                                    │
│  │  Outreach     │────► LLM generates ──► Personalized email draft   │
│  │  Agent        │     Subject + body tailored to lead               │
│  └──────┬───────┘                                                    │
│         │                                                            │
│         ▼                                                            │
│  ┌──────────────────┐                                                │
│  │  HUMAN-IN-THE-   │                                                │
│  │  LOOP GATE       │────► Pauses for human review                  │
│  │                  │                                                 │
│  │  ┌──────────┐    │    ┌──────────┐    ┌──────────┐               │
│  │  │ APPROVE  │    │    │  REJECT  │    │  EDIT    │               │
│  │  │ Send     │    │    │ Discard  │    │ Preserve │               │
│  │  │ email    │    │    │ log      │    │ edits    │               │
│  │  └────┬─────┘    │    └────┬─────┘    └────┬─────┘               │
│  └───────┼──────────┘         │               │                     │
│          │                    │               │                     │
│          ▼                    ▼               ▼                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐              │
│  │  Send Email   │  │  Log Rejection│  │  Send Edited │              │
│  │  via provider │  │  Terminate   │  │  Email       │              │
│  └──────┬───────┘  └──────────────┘  └──────┬───────┘              │
│         │                                    │                       │
│         └──────────────┬─────────────────────┘                       │
│                        ▼                                             │
│              ┌──────────────────┐                                    │
│              │  Audit Log       │                                    │
│              │  All events      │                                    │
│              │  persisted to DB │                                    │
│              └──────────────────┘                                    │
│                                                                     │
│  OUTPUT: Enriched, scored, classified lead with sent email          │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Test Coverage

| Test Suite | Tests | Coverage |
|---|---|---|
| **test_classification_agent.py** | 28 | Classification agent logic |
| **test_enrichment_agent.py** | 14 | Enrichment data processing |
| **test_intake_agent.py** | 14 | Lead intake + prompt injection defense |
| **test_scoring_agent.py** | 28 | Scoring logic + fairness |
| **test_outreach_agent.py** | 28 | Email draft generation |
| **test_human_approval.py** | 23 | Human-in-the-loop approval gate |
| **test_email_tool.py** | 8 | Email sending safeguard |
| **test_normalization.py** | 14 | Lead field normalization |
| **test_fairness.py** | 14 | Fairness/ bias detection |
| **test_security.py** | 14 | Prompt injection defense |
| **test_audit_logger.py** | 26 | Centralized audit logging |
| **test_api.py** | 9 | REST API endpoints |
| **TOTAL** | **387** | **All passing** |

---

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 18+
- OpenRouter API key (free tier available)

### 1. Clone & Setup

```bash
git clone <repository-url>
cd B2B-Project
```

### 2. Backend Setup

```bash
# Create virtual environment
py -m venv venv
venv\Scripts\activate  # Windows
# source venv/bin/activate  # macOS/Linux

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env — add your OPENROUTER_API_KEY
```

### 3. Frontend Setup

```bash
cd frontend
npm install
cd ..
```

### 4. Run Application

```bash
# Terminal 1: Backend
py -m uvicorn backend.main:app --reload --port 8000

# Terminal 2: Frontend
cd frontend && npm run dev
```

### 5. Open

- Frontend: [http://localhost:5173](http://localhost:5173)
- API Docs: [http://localhost:8000/docs](http://localhost:8000/docs)
- Health Check: [http://localhost:8000/health](http://localhost:8000/health)

---

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `OPENROUTER_API_KEY` | Yes | — | OpenRouter API key for LLM access |
| `DATABASE_URL` | No | `sqlite+aiosqlite:///./pipelineiq.db` | Database connection string |
| `DEBUG` | No | `False` | Enable debug mode |
| `LOG_LEVEL` | No | `INFO` | Logging level |
| `CORS_ORIGINS` | No | `["http://localhost:5173"]` | Allowed CORS origins |
| `EMAIL_PROVIDER` | No | `simulated` | Email provider (`simulated`, `smtp`, `sendgrid`, `gmail`) |

---

## API Documentation

### Lead Management

| Method | Endpoint | Description | Status Codes |
|---|---|---|---|
| `POST` | `/lead` | Create a new lead | `201` Created, `409` Duplicate, `400` Validation |
| `GET` | `/lead/{id}` | Get lead with full details | `200` OK, `404` Not Found |
| `GET` | `/leads` | List leads with search/sort/pagination | `200` OK, `400` Invalid params |

**GET /leads query parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `search` | string | — | Search name, email, or company |
| `industry` | string | — | Filter by industry |
| `sort_by` | string | `created_at` | `created_at`, `name`, `email`, `company` |
| `sort_order` | string | `desc` | `asc` or `desc` |
| `limit` | integer | `50` | Max leads (1-500) |
| `offset` | integer | `0` | Pagination offset |

### Approval Workflow

| Method | Endpoint | Description | Status Codes |
|---|---|---|---|
| `POST` | `/approve/{lead_id}` | Approve draft email | `200`, `404` |
| `POST` | `/reject/{lead_id}` | Reject draft email | `200`, `404` |
| `PUT` | `/draft/{lead_id}` | Edit draft email | `200`, `404` |
| `GET` | `/pending-approvals` | List pending approvals | `200` |

### Audit Logs

| Method | Endpoint | Description | Status Codes |
|---|---|---|---|
| `GET` | `/logs/{lead_id}` | Get audit logs for a lead | `200`, `404` |

**GET /logs/{lead_id} query parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `event_type` | string | — | Filter by event type |
| `sort_by` | string | `timestamp` | `timestamp` or `event_type` |
| `sort_order` | string | `desc` | `asc` or `desc` |
| `limit` | integer | `100` | Max entries (1-1000) |
| `offset` | integer | `0` | Pagination offset |

### Dashboard

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/dashboard-stats` | Get aggregate pipeline statistics |

### System

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | Health check |
| `POST` | `/pipeline/run` | Execute full LangGraph pipeline |

### Lead Create Request Body

```json
{
  "name": "Jane Doe",
  "email": "jane@acme.com",
  "company": "Acme Corp",
  "role": "CTO",
  "industry": "SaaS",
  "buying_signals": ["visited pricing page", "requested demo"]
}
```

### Lead Detail Response

```json
{
  "id": "a1b2c3d4e5f6",
  "name": "Jane Doe",
  "email": "jane@acme.com",
  "company": "Acme Corp",
  "role": "CTO",
  "industry": "SaaS",
  "buying_signals": ["visited pricing page"],
  "created_at": "2026-07-14T22:00:00",
  "enrichment": { "company_size": "50-200", "employee_count": 150, ... },
  "scores": [{ "score": 85, "confidence": 0.92, ... }],
  "classifications": [{ "category": "hot", "explanation": "...", ... }],
  "draft_emails": [{ "subject": "...", "body": "...", "status": "draft", ... }],
  "audit_logs": [{ "event_type": "lead_created", "message": "...", ... }]
}
```

### Dashboard Stats Response

```json
{
  "total_leads": 42,
  "leads_with_scores": 35,
  "leads_classified": 30,
  "leads_with_drafts": 25,
  "pending_approvals": 8,
  "approved": 15,
  "rejected": 2,
  "emails_sent": 12,
  "avg_score": 72.3,
  "hot_leads": 10,
  "nurture_leads": 15,
  "disqualify_leads": 5
}
```

---

## Security Features

### Prompt Injection Defense

- All lead fields are treated as data, never as instructions
- Input sanitization strips control characters and normalizes whitespace
- System prompts explicitly protect workflow integrity
- Injection attempts are logged to the audit trail

### Input Validation

- Email format validation via Pydantic's `EmailStr`
- String length limits on all fields
- Numeric bounds on scores (0-100) and confidence (0.0-1.0)
- Whitespace stripping and normalization

### Human-in-the-Loop Gate

- Email drafts require explicit human approval before sending
- Approve, reject, or edit with user edits preserved
- All decisions logged to audit trail with who approved/rejected

---

## Testing

### Run All Tests

```bash
py -m pytest tests/ -v --tb=short
```

### Run Specific Test Suites

```bash
# Security tests
py -m pytest tests/test_security.py -v

# Fairness tests
py -m pytest tests/test_fairness.py -v

# Approval gate tests
py -m pytest tests/test_human_approval.py -v

# API tests
py -m pytest tests/test_api.py -v

# Audit logger tests
py -m pytest tests/test_audit_logger.py -v
```

---

## Project Structure

```
B2B-Project/
├── backend/
│   ├── main.py                  # FastAPI entry point
│   ├── config.py                # Environment configuration
│   ├── agents/
│   │   ├── intake_agent.py      # Lead intake + sanitization
│   │   ├── enrichment_agent.py  # Company data enrichment
│   │   ├── scoring_agent.py     # LLM-based lead scoring
│   │   ├── classification_agent.py  # Lead classification
│   │   ├── outreach_agent.py    # Email draft generation
│   │   ├── human_approval_node.py   # Human approval node
│   │   └── email_tool_node.py   # Email sending safeguard
│   ├── api/
│   │   ├── leads.py             # Lead CRUD + dashboard APIs
│   │   ├── approval.py          # Approval workflow APIs
│   │   └── audit_logs.py        # Audit log query API
│   ├── database/
│   │   └── session.py           # Async SQLAlchemy session
│   ├── graph/
│   │   ├── state.py             # LangGraph state schema
│   │   └── graph_builder.py     # Workflow graph definition
│   ├── models/
│   │   ├── schemas.py           # Pydantic request/response models
│   │   └── sqlalchemy_models.py # ORM models (Lead, Score, etc.)
│   ├── prompts/
│   │   ├── scoring_prompt.py    # LLM scoring prompt template
│   │   └── __init__.py
│   ├── services/
│   │   └── email_sender.py      # Email sending abstraction
│   └── utils/
│       ├── normalization.py     # Lead field normalization
│       ├── fairness.py          # Bias detection & fairness
│       ├── security.py          # Prompt injection defense
│       └── audit_logger.py      # Centralized audit logging
├── frontend/
│   ├── src/
│   │   ├── api.js               # API service layer
│   │   ├── App.jsx              # Router + sidebar
│   │   ├── index.css            # Complete design system
│   │   ├── main.jsx             # Entry point
│   │   └── pages/
│   │       ├── Dashboard.jsx
│   │       ├── LeadsList.jsx
│   │       ├── LeadDetail.jsx
│   │       ├── AddLead.jsx
│   │       ├── PendingApprovals.jsx
│   │       └── AuditLogs.jsx
│   ├── index.html
│   ├── vite.config.js
│   └── package.json
├── tests/
│   ├── test_intake_agent.py     # 14 tests
│   ├── test_enrichment_agent.py # 14 tests
│   ├── test_scoring_agent.py    # 28 tests
│   ├── test_classification_agent.py  # 28 tests
│   ├── test_outreach_agent.py   # 28 tests
│   ├── test_human_approval.py   # 23 tests
│   ├── test_email_tool.py       # 8 tests
│   ├── test_normalization.py    # 14 tests
│   ├── test_fairness.py         # 14 tests
│   ├── test_security.py         # 14 tests
│   ├── test_audit_logger.py     # 26 tests
│   └── test_api.py              # 9 tests
├── requirements.txt
├── .env.example
├── alembic.ini
└── README.md
```

---

## Deployment

### Production Backend (Uvicorn + Gunicorn)

```bash
# Install production server
pip install gunicorn

# Run with multiple workers
gunicorn backend.main:app \
  --worker-class uvicorn.workers.UvicornWorker \
  --workers 4 \
  --bind 0.0.0.0:8000 \
  --timeout 120
```

### Docker Deployment

```dockerfile
# Backend Dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

```bash
# Build and run
docker build -t pipelineiq-backend .
docker run -p 8000:8000 pipelineiq-backend
```

### Frontend Production Build

```bash
cd frontend
npm run build
# Output: frontend/dist/ — serve via nginx or deploy to Vercel/Netlify
```

### Database Migrations

```bash
# Auto-generate migration
alembic revision --autogenerate -m "description"

# Apply migrations
alembic upgrade head
```

---

## Future Enhancements

### Short-term (Next Sprint)

- [ ] **Multi-provider email** — SendGrid, SMTP, Gmail API integrations
- [ ] **Bulk lead import** — CSV/Excel upload with validation
- [ ] **Email templates** — Configurable templates with variable substitution
- [ ] **Webhook notifications** — Slack/Teams alerts for pending approvals
- [ ] **Rate limiting** — API rate limiting with configurable thresholds

### Medium-term (Next Quarter)

- [ ] **Authentication** — JWT-based auth with role-based access control (RBAC)
- [ ] **Multi-tenant** — Organization isolation with separate pipelines
- [ ] **Scheduler** — Automated lead scoring on a cron schedule
- [ ] **Analytics dashboard** — Conversion rates, pipeline velocity, trend charts
- [ ] **Export** — CSV/PDF export for leads, logs, and reports
- [ ] **Custom scoring rules** — User-defined scoring weights and criteria

### Long-term (Next Release)

- [ ] **A/B testing** — Compare different scoring models and outreach strategies
- [ ] **ML model training** — Fine-tune scoring models on historical outcomes
- [ ] **Real-time streaming** — WebSocket-based live updates to dashboard
- [ ] **Integration marketplace** — HubSpot, Salesforce, CRM connectors
- [ ] **Advanced NLP** — Sentiment analysis on email replies, conversation threading
- [ ] **Mobile app** — React Native companion for approval on-the-go

---

## Technology Stack

| Layer | Technology |
|---|---|
| **Backend** | Python 3.11+, FastAPI, Uvicorn |
| **Workflow** | LangGraph, LangChain |
| **LLM** | OpenRouter (GPT-4o, Claude, etc.) |
| **Database** | SQLite + SQLAlchemy (async) |
| **Frontend** | React 18, Vite, React Router |
| **Testing** | Pytest, pytest-asyncio |
| **Tracing** | LangSmith |
| **Migrations** | Alembic |

---

## License

MIT License — see LICENSE file for details.

---

*PipelineIQ — Built for the AI Bootcamp Demo*