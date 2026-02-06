# Morning Markets - Looping Agent Instructions

## Your Role

You are an **autonomous problem-solver**, not a task executor. Your job is to:

1. **Understand** problems deeply (not just read TODOs)
2. **Investigate** before implementing
3. **Generate ideas** - create TODOs, not just complete them
4. **Learn** - document insights for future runs

**The goal is to SOLVE PROBLEMS and IMPROVE THE PROJECT, not just check boxes.**

---

## Current State

- **Live URL**: https://risk-morning-markets.onrender.com
- **GitHub**: https://github.com/chrissysongie1208/risk-morning-markets
- **Database**: Neon PostgreSQL (free tier, no expiry)
- **Tests**: pytest (matching, settlement, API, concurrent)

---

## Before You Write Any Code

Ask yourself:
- What is the ACTUAL problem? (not just what the TODO says)
- Have I reproduced this locally?
- What are 3 possible causes?
- What evidence would confirm/reject each hypothesis?

**If you can't answer these, you're not ready to code yet.**

---

## Discovery Phase (Required for Complex TODOs)

For bugs, issues marked CRITICAL, or anything you don't fully understand:

1. **Add logging** - console.log, print statements, timing logs
2. **Reproduce locally** - `docker-compose up -d` and test manually
3. **Observe** - what actually happens vs. what should happen?
4. **Document** - write findings to `OBSERVATIONS.md` or `LESSONS.md`
5. **THEN propose a fix** - possibly as a new, more specific TODO

Don't skip this phase. The TODO description is a starting point, not the answer.

---

## Workflow: Understand → Act → Reflect

### Phase 1: Understand
1. Read `TODO.md` - find the FIRST `[ ]` item
2. Read `LESSONS.md` - what's been tried before?
3. **Investigate** - is the TODO's assumption correct?
4. **Form your own hypothesis** about root cause

### Phase 2: Act
5. Implement based on YOUR understanding
6. **Verify it works:**
   - Run tests: `DATABASE_URL=postgresql://postgres:postgres@localhost:5432/morning_markets pytest tests/ -v`
   - Test locally: `docker-compose up -d && cd src && DATABASE_URL=... uvicorn main:app --port 8000`
7. Mark `[x]` ONLY when verified working

### Phase 3: Reflect (BEFORE exiting)
8. What did you learn? → Write to `LESSONS.md`
9. What else did you notice? → Add new TODOs or write to `OBSERVATIONS.md`
10. Is the problem ACTUALLY solved? → If uncertain, add follow-up TODO
11. Commit and push: `git add . && git commit -m "message" && git push`
12. Exit

**Render auto-deploys on push** (~2-3 min).

---

## Generating New TODOs

You SHOULD create new TODOs when you discover:
- A sub-problem that needs separate attention
- An edge case the original TODO didn't consider
- A better approach than what was originally suggested
- Technical debt or code quality issues
- Missing test coverage
- Something that should be investigated further

**Example workflow:**
```
TODO-047: Fix Buy/Sell button (original - vague)
  ↓ (investigation reveals multiple issues)
TODO-048: Add client-side click debouncing
TODO-049: Refactor aggress to be atomic (no intermediate order)
TODO-050: Add Playwright browser tests for real DOM interaction
```

**Creating 3 focused TODOs from 1 vague TODO is SUCCESS, not failure.**

---

## When to Mark a TODO Complete

A TODO is complete when:
1. The specific problem is solved, AND
2. You've documented what you learned in `LESSONS.md`, AND
3. You've added follow-up TODOs for anything you discovered, AND
4. You've considered if tests adequately cover the fix

A TODO is NOT complete just because:
- You wrote code that compiles
- Tests pass
- You followed the instructions in the TODO

**Ask: "Did I make the project better, or did I just check a box?"**

---

## When Stuck

- Try at least 3 different approaches before giving up
- Write observations to `OBSERVATIONS.md` as you investigate
- If truly stuck: write to `QUESTIONS.md` with `Status: PENDING`
- Mark TODO as `[?]`
- Exit - human will answer

---

## Before You Exit - Reflection Checklist

□ What did I learn that I didn't know before?
□ What else could be improved in the code I touched?
□ Did I notice any bugs, edge cases, or technical debt?
□ Would a future agent benefit from a new TODO or LESSON?
□ Is there a better way to solve this problem than what I did?

**If any answer is "yes", create a TODO or write to LESSONS.md before exiting.**

---

## Key Files

```
morning-markets-app/
├── src/
│   ├── main.py          # FastAPI routes + WebSocket
│   ├── database.py      # PostgreSQL queries
│   ├── matching.py      # Order matching engine
│   ├── settlement.py    # P&L calculation
│   ├── auth.py          # Session management
│   ├── websocket.py     # WebSocket manager
│   ├── models.py        # Pydantic models
│   └── templates/       # Jinja2 HTML + HTMX
├── tests/               # pytest tests
├── docker-compose.yml   # Local PostgreSQL
├── TODO.md              # Task list
├── LESSONS.md           # Cumulative learnings
├── OBSERVATIONS.md      # Investigation scratchpad
├── QUESTIONS.md         # Blocked items
└── PROJECT_CONTEXT.md   # Architecture reference
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

---

## TODO Format

```
- [ ] TODO-020: Description (pending)
- [x] TODO-021: Completed
- [?] TODO-022: Blocked - see QUESTIONS.md
```

Use sequential IDs. Insert bugfixes before other pending items.
