# AGENTS.md — Support Ticket Triage & Assignment System

This file defines the architecture, constraints, and engineering rules for this project.
All contributors (human or AI agents) MUST follow these rules. Do not change the
architecture without explicit approval.

---

## 1. Project Goal

A small but complete AI-assisted customer-support ticket management application.

An authenticated support user can:

- Log in
- View a dashboard
- Create support tickets
- Save a ticket without AI
- Save a ticket and request AI analysis
- Review AI suggestions
- Accept, edit, or reject AI suggestions
- Continue manually if AI fails
- Assign tickets to teams and users
- Update ticket status
- Add internal comments
- View an activity/audit timeline
- Search and filter tickets
- Resolve and close tickets

**AI is an assistant only. Humans always control the final ticket values.**
**The application must remain usable even if AI is unavailable.**

---

## 2. Non-Negotiable Stack

Frontend:
- React, Vite, JavaScript
- Simple CSS / lightweight styling
- No paid UI libraries

Backend:
- Python, FastAPI, Pydantic, SQLAlchemy, Alembic

Database:
- SQLite

Authentication:
- JWT, seeded demo account, hashed passwords

AI:
- Ollama running locally, initial model `qwen3:4b`
- No paid AI API, no cloud provider dependency

Testing:
- pytest, FastAPI test utilities where appropriate

Repository:
- Single repository with `/backend` and `/frontend`

**Everything required to run the submitted project must be free.**
No paid AI APIs, paid databases, paid hosting, paid auth providers, or paid UI libraries.

---

## 3. Architecture Rules

Maintain clear separation between:

1. HTTP/API layer
2. Business/service layer
3. Database/ORM layer
4. AI provider/integration layer
5. Frontend/UI layer

Rules:
- FastAPI route handlers stay thin — no business logic in route handlers.
- No business logic in React components.
- Do NOT call Ollama directly from ticket routes.
- AI is accessed through a provider abstraction:

```
TicketService
    -> AIService
        -> AIProvider interface
            -> OllamaProvider
```

- The ticket workflow must not depend on Ollama-specific code.
- A future provider (OpenAI, Gemini, Azure OpenAI, Groq, …) must be addable by
  creating another provider implementation WITHOUT rewriting the ticket workflow.

---

## 4. Database Model

Main entities: `users`, `teams`, `tickets`, `ai_analysis_runs`, `comments`, `activities`.

### 4.1 users
- id, name, email, password_hash, role, is_active, created_at
- Role field exists for future extension; advanced RBAC is NOT required.

### 4.2 teams
- id, code, name, description
- Seeded teams:
  - PLATFORM_ENGINEERING
  - APPLICATION_ENGINEERING
  - SECURITY
  - DEVOPS
  - DATABASE
  - BILLING
  - CUSTOMER_SUPPORT
  - PRODUCT

### 4.3 tickets
Represents the **current human-controlled state** of a ticket.

Fields:
- id, customer_name, customer_email, subject, description_original,
  product_module, attachment_link
- Human-controlled triage values: summary, category, priority, priority_reason,
  recommended_team_id
- Assignment: assigned_team_id, assigned_user_id
- Customer response: initial_response
- Workflow: status
- Note: Latest AI analysis is derived dynamically by querying `ai_analysis_runs` (`WHERE ticket_id = <id> ORDER BY created_at DESC, id DESC LIMIT 1`) to avoid circular foreign-key dependencies.
- Metadata: created_by, created_at, updated_at

**IMPORTANT:** `description_original` is the original customer message. It must
NEVER be overwritten or replaced by AI-generated content. AI suggestions and
human-confirmed values are separate concepts.

### 4.4 ai_analysis_runs
Each AI attempt is stored separately so retries are auditable.

Fields:
- id, ticket_id, provider, model, summary, category, priority, priority_reason,
  recommended_team_code, suggested_response, raw_response, status, error_message,
  created_at

Statuses: `pending`, `success`, `failed`

- Retrying AI analysis creates a NEW ai_analysis_run for the SAME ticket.
- Retrying must NEVER create another ticket.

### 4.5 comments
- id, ticket_id, author_id, body, created_at
- Internal only. Empty comments must be rejected (client-side AND server-side).

### 4.6 activities
Append-only audit trail.
- id, ticket_id, type, description, actor_id, created_at
- Do NOT edit or delete activity records during the normal workflow.

---

## 5. Recommendation vs Assignment (must stay separate)

Three distinct concepts — never collapse into one field:

1. **AI recommended team** — what the AI suggested (in ai_analysis_runs)
2. **Human-confirmed recommended team** — `tickets.recommended_team_id`
3. **Actual assigned team** — `tickets.assigned_team_id`

Do NOT automatically assign a team based only on AI output.

---

## 6. Ticket Statuses

Use exactly these statuses:
- `Open`
- `Assigned`
- `In Progress`
- `Waiting for Customer`
- `Resolved`
- `Closed`

Expected flow:
- New ticket → Open
- Assignment may → Assigned
- Work begins → In Progress
- More customer info needed → Waiting for Customer
- Work completed → Resolved
- Confirmed completion → Closed

Do not build a complex state machine unless necessary.

---

## 7. Create Ticket Workflow

Two user actions:

**SAVE TICKET** (`POST /tickets`):
1. Validate request
2. Save original ticket, status = Open
3. Write TICKET_CREATED activity
4. Do NOT call AI
5. Return created ticket

**SAVE AND ANALYZE** — the frontend uses a two-step workflow:
1. `POST /tickets`
2. `POST /tickets/{id}/analyze`

This separation is intentional. The original ticket MUST be committed before AI
analysis begins.

If AI analysis fails:
- Ticket remains saved
- No duplicate ticket is created
- User sees a clear failure message
- User may retry
- User may continue manual triage without AI

---

## 8. AI Output

AI analyzes: subject, original description, optionally product/module.

It suggests:

```json
{
  "summary": "...",
  "category": "...",
  "priority": "...",
  "priority_reason": "...",
  "recommended_team": "...",
  "suggested_response": "..."
}
```

Allowed categories:
- Authentication, Billing, Performance, Data Issue, Integration,
  User Interface, Access Request, Feature Request, Security, General Support, Unknown

Allowed priorities:
- Low, Medium, High, Critical

Recommended team must correspond to one of the seeded team codes.

### 8.1 AI Validation Pipeline

Never trust AI output directly.

```
Ollama response
    -> JSON parsing
    -> Pydantic validation
    -> domain validation
    -> save only if valid
```

Validate:
- all required fields exist
- summary is not empty
- category is allowed
- priority is allowed
- priority_reason is not empty
- recommended_team is allowed
- suggested_response is not empty

Rules:
- Malformed output must NOT be stored as valid AI suggestions.
- Do NOT silently convert invalid values into valid business values.
- If validation fails:
  - mark the AI analysis run as failed
  - record a safe failure reason
  - create an AI_ANALYSIS_FAILED activity where possible
  - allow retry
  - keep the original ticket usable

### 8.2 AI Prompt Rules

The prompt must state:
- AI is a support-ticket triage assistant
- AI suggests; humans decide
- Use only information contained in the ticket
- Do not invent unsupported facts
- Use only allowed categories / priorities / team values
- Return structured JSON
- Customer response must be professional
- Do not promise a resolution time unless provided
- Do not claim the issue is resolved
- Do not expose sensitive internal technical information
- Do not blame the customer

---

## 9. Human-in-the-Loop

The user must be able to:
- Accept AI suggestions
- Edit AI suggestions
- Reject AI suggestions
- Retry AI analysis
- Continue manually if AI fails

The active ticket values are the **human-confirmed** values.

The UI must visibly distinguish:
- AI Suggested
- Human Confirmed
- Human Edited

---

## 10. Activity / Audit Events

Supported event types:
- TICKET_CREATED
- AI_ANALYSIS_COMPLETED
- AI_ANALYSIS_FAILED
- AI_SUGGESTIONS_ACCEPTED
- AI_SUGGESTIONS_EDITED
- AI_SUGGESTIONS_REJECTED
- CATEGORY_CHANGED
- PRIORITY_CHANGED
- TEAM_ASSIGNED
- USER_ASSIGNED
- STATUS_CHANGED
- COMMENT_ADDED
- TICKET_RESOLVED
- TICKET_CLOSED

Activities are created by reusable service/helper logic.

---

## 11. Transaction Rules

Important business mutations and their corresponding activity records must occur
in the SAME database transaction where practical.

Examples:
- status change + STATUS_CHANGED activity
- assignment change + assignment activity
- comment creation + COMMENT_ADDED activity
- human review update + review activity

If one operation fails, do not leave the database in a partially updated state.

---

## 12. Authentication

Endpoints:
- `POST /auth/login`
- `GET /auth/me`

Rules:
- Use JWT.
- Seed at least one demo login.
- All business routes require authentication.
- Do NOT implement: registration, forgot password, social login, MFA, email verification.

---

## 13. API Surface

```
POST   /auth/login
GET    /auth/me

GET    /dashboard/stats

GET    /tickets
POST   /tickets
GET    /tickets/{id}

POST   /tickets/{id}/analyze
GET    /tickets/{id}/ai-analysis/latest
PUT    /tickets/{id}/review

PUT    /tickets/{id}/assignment
PUT    /tickets/{id}/status

GET    /tickets/{id}/comments
POST   /tickets/{id}/comments

GET    /tickets/{id}/activities

GET    /teams
GET    /users
```

Do NOT implement ticket deletion in the initial solution.

---

## 14. Search and Filters

Ticket search supports:
- ticket ID, subject, customer name, customer email, description keyword

Filters support:
- status, category, priority, assigned team, assigned user

Pagination is optional and not a priority.

---

## 15. Frontend Pages

Build ONLY these pages:

- `/login`
- `/dashboard`
- `/tickets`
- `/tickets/new`
- `/tickets/:id`

Dashboard:
- Open count, Assigned count, In Progress count, Critical count, Resolved count, recent tickets

Tickets page:
- search, status filter, category filter, priority filter, assigned team filter,
  assigned user filter, ticket table

Create ticket form:
- Customer Name, Customer Email, Subject, Description, Product/Module, Attachment Link
- Actions: Save Ticket | Save and Analyze | Cancel

Ticket details:
- Original ticket information
- AI suggestion / human review section
- Assignment, status
- Internal comments
- Activity timeline
- Retry AI
- Manual triage fallback

---

## 16. Error Handling

- **Invalid ticket input:** reject request, field-level feedback, do NOT call AI.
- **AI unavailable:** preserve ticket, mark analysis failure, allow retry, allow manual triage.
- **Malformed AI output:** do not crash, do not save malformed results as valid, allow retry.
- **Database failure:** rollback transaction, generic user-safe error, no stack traces.
- **Unauthorized:** return 401; frontend redirects to login where appropriate.
- **Empty comment:** reject client-side AND server-side.

---

## 17. Security Basics

- Hash passwords.
- JWT secret comes from an environment variable.
- No secrets committed; no secrets exposed to frontend; do not log secrets.
- Ollama URL/model come from environment configuration.
- Restrict CORS to the frontend development origin.
- Do not expose Python stack traces to users.
- Provide `.env.example` with placeholders.

---

## 18. Alembic

- Use Alembic migrations.
- Do NOT rely only on `Base.metadata.create_all` as the primary setup.
- Target setup flow:

```
alembic upgrade head
python -m app.seed
```

---

## 19. Testing Priorities

Meaningful tests over maximum coverage. High-value tests:

- valid ticket creation
- invalid ticket creation
- Save Ticket does not call AI
- original description is preserved
- valid AI response is accepted
- malformed AI response is rejected
- invalid category/priority/team is rejected
- AI provider failure preserves ticket
- retry uses same ticket ID
- human-edited values override AI suggestion
- inactive user cannot be assigned
- empty internal comment rejected
- unauthenticated routes return 401
- search and filters work
- mutation and audit activity remain consistent

---

## 20. Development-Only AI Failure Simulation

Support a documented dev/test-only mechanism:

```
AI_SIMULATE_FAILURE=false
```

When enabled, AI analysis intentionally raises the same application-level provider
error used for real provider failures. For testing/demonstrating failure handling
only. Do NOT expose as a production UI feature.

---

## 21. Out of Scope (until core app is complete)

Do NOT add unless explicitly requested:
- email sending
- advanced RBAC
- SLA system
- WebSockets / real-time updates
- dashboard charts
- Docker / Kubernetes
- public deployment
- multiple AI providers
- actual file uploads
- bulk analysis
- workload balancing
- fancy animations
- complex design system

The core workflow must be complete before any bonus features.

---

## 22. Coding Quality

Prefer:
- clear names
- small focused functions
- typed Python
- Pydantic schemas
- enums/constants instead of duplicated strings
- reusable service logic
- consistent API error responses
- comments only where they explain a non-obvious decision
- no giant files
- no unnecessary abstraction

Avoid:
- business logic in React components
- business logic in FastAPI routes
- duplicated validation
- hard-coded secrets
- provider-specific AI logic throughout the app
- silent exception swallowing
- unnecessary dependencies
- premature optimization

---

## 23. Implementation Process (Checkpoints)

Do NOT jump ahead. Build in this order:

0. Project instructions and architecture (this file)
1. Backend skeleton + database models
2. Alembic migration + seed data
3. Authentication
4. Ticket CRUD and validation
5. Activity/audit system
6. Assignment, status, comments
7. Ollama provider + prompt + AI validation
8. Human review + retry + reject + manual fallback
9. Dashboard + search/filter APIs
10. React frontend
11. Integration and error-state cleanup
12. Tests
13. README + clean-install verification
14. Demo preparation and final cleanup

At the end of every checkpoint:
- run appropriate tests or validation commands
- report exactly what changed
- report any unresolved issues
- do NOT proceed to the next checkpoint until instructed
