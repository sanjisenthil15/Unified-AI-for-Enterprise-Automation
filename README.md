# Unified AI for Enterprise Automation

A modular, scalable enterprise web application with a centralized AI Decision Engine.

## Modules
1. Customer Support AI
2. Incident Management
3. Recruitment AI
4. Meeting Intelligence
5. Employee Management
6. Analytics Dashboard

## Tech Stack
- **Frontend**: React.js, JavaScript, HTML, CSS
- **Backend**: Python FastAPI
- **Database**: PostgreSQL 16 (SQLAlchemy ORM + Alembic migrations)
- **Auth**: JWT + RBAC
- **AI**: Gemini API, Whisper, Sentence Transformers, Embeddings
- **Charts**: Recharts

## Getting Started

**Prerequisites:** Python 3.12, Node 18+, and PostgreSQL 16 (or Docker).

Auth is currently **disabled for development** — no login screen, every request
runs as a seeded admin. (Set `AUTH_DISABLED=false` + `REACT_APP_AUTH_DISABLED=false`
to turn JWT/RBAC back on; a demo account `demo@demo.com` / `Demo1234` also exists.)

### 1. Database
```bash
docker compose up -d db          # PostgreSQL 16 on localhost:5432  (user/pass/db: enterprise)
```
No Docker? Use a local PostgreSQL and create a database, e.g. `createdb enterprise_ai`.

### 2. Backend  — terminal 1
```bat
cd backend
python -m venv .venv
.venv\Scripts\activate                       :: macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env                        :: then edit — see below
alembic upgrade head                          :: creates tables + seeds roles + demo user
uvicorn main:app --reload                     :: http://127.0.0.1:8000/docs
```
Edit `backend/.env`:
```
DATABASE_URL=postgresql+psycopg://enterprise:enterprise@localhost:5432/enterprise_ai
SECRET_KEY=any-long-random-string
GEMINI_API_KEY=your-key        # optional — only the meeting "analysis" step needs it
AUTH_DISABLED=true
```

Optional — real speaker diarization for Meeting Intelligence (adds PyTorch;
without it every speaker is labelled "Speaker 1"):
```bash
pip install -r requirements-ml.txt
pip install --no-deps resemblyzer==0.1.4
```

### 3. Frontend  — terminal 2
```bat
cd frontend
npm install
copy .env.example .env                        :: contains REACT_APP_AUTH_DISABLED=true
npm start                                     :: http://localhost:3000
```

Open `http://localhost:3000` — it lands straight on the dashboard. Sidebar →
**HR Recruitment** or **Meetings**.

### Database migrations
- Apply latest schema:    `cd backend && alembic upgrade head`
- Autogenerate after model changes: `alembic revision --autogenerate -m "message"`
- Roll back one step:      `alembic downgrade -1`

`backend/database/schema.sql` is a readable snapshot; the Alembic migrations
in `backend/migrations/versions/` are authoritative.
"# Unified-AI-for-Enterprise-Automation" 
