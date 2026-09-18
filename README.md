# BIS Sahayak — SIH26107

AI-powered assistant for Indian Standards and BIS services (Bureau of Indian Standards), built for Smart India Hackathon 2026, problem statement SIH26107.

## Repository layout

```
frontend/   React + Vite + TypeScript UI (see frontend/README.md)
backend/    FastAPI + SQLAlchemy API (see docs/LOCAL_DEVELOPMENT.md)
docs/       Architecture, database design, roadmap, local setup
```

## Quick start

See `docs/LOCAL_DEVELOPMENT.md` for full setup instructions. In short:

```bash
# Backend
cd backend
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
python -m app.db.seed
uvicorn app.main:app --reload --port 8000

# Frontend (separate terminal)
cd frontend
npm install
npm run dev
```

Frontend: http://localhost:5173 · Backend: http://localhost:8000

## Documentation

- `docs/ARCHITECTURE.md` — system architecture and design
- `docs/DATABASE.md` — database schema, migrations, seed data
- `docs/IMPLEMENTATION_ROADMAP.md` — phased build plan and current status
- `docs/LOCAL_DEVELOPMENT.md` — full local dev setup and troubleshooting
