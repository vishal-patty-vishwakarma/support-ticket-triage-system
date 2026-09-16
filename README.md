# Support Ticket Triage & Assignment System

An AI-assisted customer-support ticket management application. AI suggests triage values; a human always makes the final decision. The application remains fully usable if AI is unavailable.

## Technology Stack

### Frontend

- React 19
- Vite
- JavaScript
- React Router v7
- Vitest + React Testing Library

### Backend

- Python
- FastAPI
- Pydantic v2
- SQLAlchemy 2
- Alembic
- SQLite
- JWT authentication (PyJWT + argon2 password hashing)

### AI Integration

- Ollama (local, open-source)
- Default model: `qwen3:4b`
- Provider abstraction (`AIProvider` interface)
- Structured JSON output with schema validation

## Architecture

The application maintains clear separation between five layers:

```
React UI  -->  FastAPI Routes  -->  Service Layer  -->  SQLAlchemy/SQLite
                                      |
                                  AIService
                                      |
                                AIProvider (interface)
                                      |
                                OllamaProvider
```

**Key design principle:** Two distinct entities prevent AI from overriding human decisions:

- **Ticket** — the current human-controlled state (summary, category, priority, team, assignment, status)
- **AIAnalysisRun** — a record of one AI analysis attempt (suggestions only, stored separately)

AI suggestions are never written directly to the ticket. A human must explicitly accept, edit, or reject them.

## Main Features

- **Authentication** — JWT-based login with a seeded demo account
- **Dashboard** — open/assigned/in-progress/critical/resolved counts, recent tickets
- **Ticket creation** — customer name, email, subject, description, product/module, optional attachment link
- **Original description preserved** — `description_original` is never overwritten by AI or edits
- **AI analysis** — structured triage suggestions via Ollama
- **Human review** — accept, edit, or reject AI suggestions; retry on failure; manual triage fallback
- **Assignment** — assign tickets to teams and individual users
- **Status workflow** — Open > Assigned > In Progress > Waiting for Customer > Resolved > Closed
- **Internal comments** — staff-only notes on tickets
- **Activity timeline** — append-only audit trail of all changes
- **Search and filters** — search by ID/subject/customer/email/description; filter by status, category, priority, team, user
- **AI failure recovery** — ticket remains saved if AI fails; user can retry or continue manually

## AI Design

### Structured Output Fields

The AI model returns structured JSON with these fields:

| Field | Description |
|---|---|
| `summary` | 1-3 sentence summary of the problem |
| `category` | One of: Authentication, Billing, Performance, Data Issue, Integration, User Interface, Access Request, Feature Request, Security, General Support, Unknown |
| `priority` | Low, Medium, High, or Critical |
| `priority_reason` | Short justification for the selected priority |
| `recommended_team` | One of the 8 seeded team codes |
| `suggested_response` | Professional draft response to the customer |

### Validation Pipeline

AI output passes through multiple validation stages before storage:

1. JSON parsing from model response
2. Pydantic schema validation (required fields, types, non-empty strings)
3. Enum validation (category, priority, team code must be in allowed sets)
4. Database team existence check (recommended team must exist in the `teams` table)

If any stage fails, the analysis run is marked as `failed` and the user can retry.

### Provider Abstraction

```
TicketService -> AIService -> AIProvider (interface) -> OllamaProvider
```

A future provider (OpenAI, Gemini, etc.) can be added by implementing `AIProvider` without changing the ticket workflow.

## Local AI Model

The application connects to Ollama running locally. The configured model is `qwen3:4b`.

**Development note:** On the available CPU-only development machine (Intel UHD Graphics, no dedicated GPU), `qwen3:4b` was impractically slow (8+ minutes per inference). A smaller already-installed model, `phi:latest`, was successfully verified through the real end-to-end Ollama integration and produces valid structured output in approximately 46 seconds.

**Small-model limitation:** Smaller models like `phi:latest` may occasionally echo prompt instructions in the `suggested_response` field instead of generating a natural customer-facing reply. This is a model-quality limitation, not a workflow or validation failure. The structured triage fields (summary, category, priority, team) are reliably accurate.

## Setup Instructions (Windows)

### Prerequisites

- Python 3.10+
- Node.js 18+
- [Ollama](https://ollama.com/) installed and running

### Backend Setup

```bash
cd backend

# Create and activate virtual environment
python -m venv venv
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
copy .env.example .env
# Edit .env and set a secure JWT_SECRET

# Run database migration
python -m alembic upgrade head

# Seed demo data (8 teams, 5 users)
python -m app.seed

# Start the backend server
python -m uvicorn app.main:app --reload
```

Backend runs at `http://localhost:8000`. API docs at `http://localhost:8000/docs`.

### Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Configure environment (optional, defaults to localhost:8000)
copy .env.example .env

# Start the development server
npm run dev
```

Frontend runs at `http://localhost:5173`.

### Ollama Setup

```bash
# Install Ollama from https://ollama.com/

# Pull the default model
ollama pull qwen3:4b

# Or use a smaller/faster model for CPU-only machines
ollama pull phi:latest

# Verify installed models
ollama list
```

Ensure Ollama is running before starting the backend. The backend connects to `http://localhost:11434` by default.

## Demo Credentials

| Field | Value |
|---|---|
| Email | `demo@support.local` |
| Password | `DemoPass123!` |

## Environment Variables

### Backend (`backend/.env`)

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./ticket_triage.db` | Database connection string |
| `JWT_SECRET` | *(required)* | Secret key for JWT signing |
| `JWT_ALGORITHM` | `HS256` | JWT signing algorithm |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `60` | Token expiry in minutes |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama API endpoint |
| `OLLAMA_MODEL` | `qwen3:4b` | Model name for AI analysis |
| `FRONTEND_URL` | `http://localhost:5173` | Allowed CORS origin |
| `AI_SIMULATE_FAILURE` | `false` | Dev-only: simulate AI provider failure |

### Frontend (`frontend/.env`)

| Variable | Default | Description |
|---|---|---|
| `VITE_API_BASE_URL` | `http://localhost:8000` | Backend API base URL |

## Testing

### Backend Tests

```bash
cd backend
python -m pytest tests/ -q
```

**231 tests passing** across 9 test files covering authentication, ticket CRUD, AI analysis, human review, activities, search/filter, and integration scenarios.

### Frontend Tests

```bash
cd frontend
npm test -- --run
```

**14 tests passing** covering login, dashboard, ticket list, ticket creation, ticket detail, AI review, and error handling.

### Production Build

```bash
cd frontend
npm run build
```

## Data Model

### Users
Support staff accounts with email, name, role (agent/manager), and active status. Seeded with 5 demo users.

### Teams
8 predefined teams: Platform Engineering, Application Engineering, Security, DevOps, Database, Billing, Customer Support, Product.

### Tickets
The central entity representing the current human-controlled state. Stores original customer input (`description_original`) separately from triage values (`summary`, `category`, `priority`, `recommended_team_id`). Assignment and status fields track workflow progression.

### AI Analysis Runs
Each AI analysis attempt is stored as a separate record linked to a ticket. Retrying creates a new record (never a new ticket). Stores the AI suggestions, model used, status (pending/success/failed), and raw response for audit.

### Comments
Internal staff-only notes on tickets. Empty comments are rejected server-side and client-side.

### Activities
Append-only audit trail. Every significant action (ticket created, AI analysis completed, suggestions accepted/edited/rejected, assignment changed, status changed, comment added) is recorded with timestamp and actor.

## Failure Handling

| Scenario | Behavior |
|---|---|
| **AI provider unavailable** | Ticket remains saved, analysis marked as failed, user can retry or triage manually |
| **Malformed AI output** | Validation rejects it, analysis marked as failed, ticket remains usable |
| **Invalid ticket input** | Request rejected with field-level errors, AI is never called |
| **Unauthorized access** | 401 response; frontend redirects to login |
| **Database failure** | Transaction rolled back, generic error returned to user |

## Design Decisions

- **SQLite** is appropriate for a 48-hour assignment scope; no external database setup required
- **Simple authenticated-user flow** rather than advanced RBAC; role field exists for future extension
- **Local AI via Ollama** avoids paid API dependencies; all tools are free
- **Human-in-the-loop design** ensures AI never silently overwrites ticket values
- **No generic `PUT /tickets/{id}` endpoint** — specific sub-endpoints for review, assignment, and status prevent unintended field overwrites
- **Append-only activity history** provides a complete audit trail without complexity
- **No production deployment** configuration; designed for local development and demonstration

## Known Limitations

- **Small local model quality** — smaller models may produce less natural customer responses
- **CPU inference performance** — larger models are impractically slow without a GPU
- **Simple authentication** — no registration, password reset, MFA, or social login
- **SQLite** — not intended for large-scale concurrent production use
- **No email sending**, SLA tracking, real-time updates, or file upload handling

## Future Improvements

- PostgreSQL for production durability and concurrency
- Role-based access control with team-level permissions
- Background AI analysis jobs for non-blocking inference
- Observability: structured logging, metrics, tracing
- Multiple AI provider support (OpenAI, Gemini, Azure OpenAI)
- Docker/containerized deployment
- Rate limiting and request throttling
- Real-time updates via WebSockets
- Email notifications and SLA tracking

## Demo Walkthrough (5-10 minutes)

1. **Login** — Navigate to `http://localhost:5173`, enter `demo@support.local` / `DemoPass123!`
2. **Dashboard** — View ticket counts by status and priority; see recent tickets list
3. **Create Ticket** — Click "New Ticket", fill in customer details and problem description
4. **AI Analysis** — Click "Save and Analyze"; wait for AI to return structured suggestions
5. **Review Suggestions** — See AI-suggested summary, category, priority, team, and response displayed with "AI Suggested" labels
6. **Accept** — Click "Accept Suggestions" to promote AI values to the active ticket values ("Human Confirmed")
7. **Or Edit** — Modify specific fields before accepting; edited fields show "Human Edited"
8. **Or Reject** — Dismiss AI suggestions and continue with manual triage
9. **Assignment** — Assign the ticket to a team and optionally a specific user
10. **Status Update** — Change status through the workflow (Open > Assigned > In Progress > ...)
11. **Comment** — Add an internal note visible only to staff
12. **Activity Timeline** — Review the complete audit trail of all changes
13. **Search/Filter** — Return to the tickets list, use search and filters to find specific tickets
14. **AI Failure** — If AI is unavailable (stop Ollama), create a ticket to see it save successfully with a failure notice; retry or triage manually

## Repository Structure

```
support_ticket_triage_system/
├── AGENTS.md                          # Architecture rules and engineering constraints
├── README.md
├── backend/
│   ├── .env.example                   # Backend environment template
│   ├── alembic.ini                    # Alembic configuration
│   ├── alembic/
│   │   └── versions/
│   │       └── 3fa9bc4f9077_initial_schema.py
│   ├── requirements.txt               # Python dependencies
│   ├── app/
│   │   ├── main.py                    # FastAPI app, CORS, router registration
│   │   ├── config.py                  # pydantic-settings configuration
│   │   ├── database.py                # SQLAlchemy engine, session, FK enforcement
│   │   ├── enums.py                   # All enums (status, priority, category, etc.)
│   │   ├── seed.py                    # Demo data seeder (8 teams, 5 users)
│   │   ├── api/
│   │   │   ├── auth.py                # POST /auth/login, GET /auth/me
│   │   │   ├── dashboard.py           # GET /dashboard/stats
│   │   │   ├── tickets.py             # Ticket CRUD, analyze, review, assignment, status, comments
│   │   │   ├── teams.py               # GET /teams
│   │   │   └── users.py               # GET /users
│   │   ├── core/
│   │   │   ├── security.py            # Password hashing, JWT creation
│   │   │   └── dependencies.py        # Auth dependency, get_current_user
│   │   ├── models/
│   │   │   ├── ticket.py              # Ticket ORM model
│   │   │   ├── ai_analysis.py         # AIAnalysisRun ORM model
│   │   │   ├── user.py                # User ORM model
│   │   │   ├── team.py                # Team ORM model
│   │   │   ├── comment.py             # Comment ORM model
│   │   │   └── activity.py            # Activity ORM model
│   │   ├── schemas/
│   │   │   ├── ticket.py              # Request/response schemas for tickets
│   │   │   ├── ai.py                  # AIAnalysisOutput, AIAnalysisRunResponse
│   │   │   ├── auth.py                # LoginRequest, TokenResponse
│   │   │   ├── comment.py             # CommentCreate, CommentResponse
│   │   │   ├── dashboard.py           # DashboardStats
│   │   │   ├── team.py                # TeamResponse
│   │   │   ├── user.py                # UserResponse
│   │   │   └── activity.py            # ActivityResponse
│   │   └── services/
│   │       ├── ticket_service.py      # Ticket CRUD and search
│   │       ├── ai_service.py          # AI analysis lifecycle (3-phase)
│   │       ├── review_service.py      # Accept/Edit/Reject/Manual logic
│   │       ├── activity_service.py    # Audit trail creation
│   │       ├── comment_service.py     # Internal comments
│   │       ├── dashboard_service.py   # Stats aggregation
│   │       ├── team_service.py        # Team queries
│   │       ├── user_service.py        # User queries
│   │       └── ai/
│   │           ├── base.py            # AIProvider abstract interface
│   │           ├── ollama_provider.py  # Ollama implementation
│   │           ├── prompts.py         # System and user prompts
│   │           └── exceptions.py      # AIProviderError, AIValidationError
│   └── tests/                         # 231 backend tests
│       ├── test_integration.py        # End-to-end scenario tests
│       ├── test_tickets.py            # Ticket CRUD and validation
│       ├── test_ai.py                 # AI analysis and provider
│       ├── test_review.py             # Human review workflows
│       ├── test_auth.py               # Authentication
│       ├── test_activities.py         # Activity/audit trail
│       ├── test_checkpoint6.py        # Checkpoint 6 tests
│       ├── test_checkpoint9.py        # Checkpoint 9 tests
│       └── test_ai_prompts.py         # Prompt construction tests
└── frontend/
    ├── .env.example                   # Frontend environment template
    ├── package.json                   # Node dependencies
    ├── vite.config.js                 # Vite + React + Vitest config
    ├── index.html                     # Entry HTML
    └── src/
        ├── main.jsx                   # React entry point
        ├── App.jsx                    # Route definitions
        ├── App.test.jsx               # 14 frontend tests
        ├── index.css                  # Application styles
        ├── test-setup.js              # Test configuration
        ├── api/
        │   └── client.js             # Centralized API helper (JWT, error handling)
        ├── context/
        │   └── AuthContext.jsx        # Authentication state management
        ├── components/
        │   ├── Layout.jsx             # Sidebar + main content shell
        │   ├── ProtectedRoute.jsx     # Auth guard
        │   ├── ErrorAlert.jsx         # Error display
        │   ├── StatusBadge.jsx        # Status pill display
        │   ├── PriorityBadge.jsx      # Priority pill display
        │   └── LoadingSpinner.jsx     # Loading indicator
        ├── pages/
        │   ├── LoginPage.jsx          # Login form
        │   ├── DashboardPage.jsx      # Stats and recent tickets
        │   ├── TicketsPage.jsx        # Ticket list with search/filters
        │   ├── CreateTicketPage.jsx   # Ticket creation form
        │   ├── TicketDetailPage.jsx   # Full ticket detail and triage workflow
        │   └── NotFoundPage.jsx       # 404 page
        └── utils/
            └── dates.js               # Date formatting helpers
```
