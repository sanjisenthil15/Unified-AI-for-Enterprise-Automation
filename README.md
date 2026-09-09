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

### 1. Database
```bash
docker compose up -d db          # PostgreSQL 16 on localhost:5432
```
Or point `DATABASE_URL` at your own PostgreSQL instance.

### 2. Backend
```bash
cd backend
python -m venv .venv && source .venv/Scripts/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env             # then edit SECRET_KEY / GEMINI_API_KEY
alembic upgrade head             # create/upgrade all tables
uvicorn main:app --reload        # http://127.0.0.1:8000/docs
```

Optional — offline speaker-diarization stack for Meeting Intelligence
(the app runs without it; diarization falls back to a single speaker):
```bash
pip install -r requirements-ml.txt
pip install --no-deps resemblyzer==0.1.4
```

### 3. Frontend
```bash
cd frontend
npm install
npm start                        # http://localhost:3000
```

### Database migrations
- Apply latest schema:    `cd backend && alembic upgrade head`
- Autogenerate after model changes: `alembic revision --autogenerate -m "message"`
- Roll back one step:      `alembic downgrade -1`

`backend/database/schema.sql` is a readable snapshot; the Alembic migrations
in `backend/migrations/versions/` are authoritative.
"# Unified-AI-for-Enterprise-Automation" 
