# Morning Markets - Looping Agent Instructions

## Current State

**The app is LIVE and WORKING.** Your job is to add new features.

- **Live URL**: https://risk-morning-markets.onrender.com
- **GitHub**: https://github.com/chrissysongie1208/risk-morning-markets
- **Database**: Neon PostgreSQL (free tier, no expiry)
- **Tests**: 53 passing (matching, settlement, API, concurrent)

---

## How You Work

You are a looping agent. Each run, you complete ONE TODO from TODO.md, then exit.

### Each Run

1. Read `TODO.md` - find the FIRST `[ ]` item
2. Read `LESSONS.md` - check for relevant past learnings
3. Complete that ONE task
4. **Verify it works:**
   - Run tests: `DATABASE_URL=postgresql://postgres:postgres@localhost:5432/morning_markets pytest tests/ -v`
   - Test locally: `docker-compose up -d && cd src && DATABASE_URL=... uvicorn main:app --port 8000`
5. Mark `[x]` ONLY when verified working
6. Write to `LESSONS.md` - at least one lesson per TODO
7. Commit and push: `git add . && git commit -m "message" && git push`
8. Exit cleanly

**Render auto-deploys on push** (~2-3 min). No manual deployment needed.

### When Stuck

- Write question to `QUESTIONS.md` with `Status: PENDING`
- Mark TODO as `[?]`
- Exit - human will answer

### TODO Format

```
- [ ] TODO-020: Description
- [x] TODO-021: Completed
- [?] TODO-022: Blocked - see QUESTIONS.md
```

### Adding TODOs

Feel free to add TODOs for bugs, improvements, or sub-tasks. Use sequential IDs. Insert bugfixes before other pending items.

---

## Key Files

```
morning-markets-deploy/
├── src/
│   ├── main.py          # FastAPI routes
│   ├── database.py      # PostgreSQL queries
│   ├── matching.py      # Order matching engine
│   ├── settlement.py    # P&L calculation
│   ├── auth.py          # Session management
│   ├── models.py        # Pydantic models
│   └── templates/       # Jinja2 HTML
├── tests/               # pytest tests (53 total)
├── docker-compose.yml   # Local PostgreSQL
└── requirements.txt
```

---

## Quick Reference

### Local Dev
```bash
docker-compose up -d
source .venv/bin/activate
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/morning_markets \
  cd src && uvicorn main:app --port 8000 --reload
```

### Run Tests
```bash
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/morning_markets \
  pytest tests/ -v
```

### Deploy (automatic)
```bash
git add . && git commit -m "feat: description" && git push
# Render auto-deploys in ~2-3 min
```

### Admin Login
- Username: `chrson`
- Password: `optiver`
