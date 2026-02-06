# Looping Agent Project

## YOUR CRITICAL MISSION

**You MUST deliver a fully functioning web app.** The human is running you overnight and expects a working prediction market app by morning. Do NOT stop until:
1. All TODOs are complete
2. All tests pass (`pytest tests/ -v`)
3. The app actually runs (`uvicorn main:app`) without errors
4. All features work end-to-end

**If something is broken, FIX IT.** Add new TODOs to fix bugs. Do not mark a TODO complete if the feature doesn't actually work.

---

## How You Work
You are a looping agent. Each run, you complete ONE TODO from TODO.md, then exit.

## Workflow Rules

### 1. On Each Run
1. Read `LESSONS.md` - consult accumulated knowledge first
2. Read `TODO.md` - find the FIRST unchecked `[ ]` item (skip any `[?]` blocked items)
3. Work on ONLY that one item
4. **Actually verify it works:**
   - Run the verification commands in the TODO
   - Start the server (`cd src && uvicorn main:app --port 8000 &`) and test endpoints with curl/httpx
   - If verification FAILS, do NOT mark complete - fix it first or add a bugfix TODO
5. Mark it `[x]` ONLY when the feature actually works
6. **Write to `LESSONS.md`** - record at least one lesson per TODO
7. Add new TODOs if you discover bugs or missing pieces
8. Exit cleanly

**IMPORTANT:** A TODO is NOT complete unless the feature works. If tests fail, if the server crashes, if the endpoint returns errors - it's not done.

**Note**: If a TODO is `[?]` blocked, skip it and work on the next `[ ]`. The loop only pauses when there are NO `[ ]` items left.

### 2. When Stuck or Confused
- Write your question(s) to `QUESTIONS.md` with timestamp and TODO reference
- Mark current TODO as `[?]` (blocked)
- Exit immediately - human will answer before next loop
- DO NOT guess or hallucinate answers
- The loop will pause until human answers in QUESTIONS.md

### 3. TODO Format
```
- [ ] TODO-001: Description here
- [x] TODO-002: Completed item
- [?] TODO-003: Blocked - see QUESTIONS.md
```

**Important**: TODOs are processed in order. The first `[ ]` is always the next task.

### 4. Lessons Format (in LESSONS.md)

**MANDATORY: Write at least one lesson per completed TODO.** Lessons help future runs avoid mistakes and understand decisions.

Good lessons include:
- Technical discoveries ("aiosqlite requires row_factory set per connection")
- Design decisions ("used INSERT OR IGNORE for idempotent config init")
- Gotchas or edge cases found
- Why you chose one approach over another

```
### LESSON-001 (TODO-003) - YYYY-MM-DD HH:MM
What I learned...

### LESSON-002 (TODO-005) - YYYY-MM-DD HH:MM (DEBUNKED)
Old understanding...
**UPDATE (YYYY-MM-DD)**: New understanding is...
```

When a lesson is proven wrong, mark it DEBUNKED and add UPDATE with new learning. Never delete lessons.

### 5. Adding New TODOs

**The TODO list is yours to evolve.** Feel free to add TODOs whenever it makes sense.

**You can add TODOs for:**
- Bugs or edge cases you discover
- Tests for scenarios you just handled
- Improvements you notice would help
- Breaking down a task that's bigger than expected
- Missing validation, error handling, or UX issues

**Where to insert:**
- **Bugfixes**: Insert BEFORE other pending `[ ]` items
- **Related work**: Insert near related pending TODOs
- **Nice-to-have**: Append at end

**Rules:**
- Never delete existing TODOs (only mark `[x]` or `[?]`)
- Use next sequential ID (TODO-XXX)

### 6. Writing Findings
- Document discoveries in `LESSONS.md` with TODO reference
- For substantial output (reports, analysis), write to `output/` folder
- Keep `src/` for code only

## File Structure
```
project/
├── CLAUDE.md           # This file - agent instructions (read-only)
├── PROMPT.md           # Loop prompt (read-only)
├── PROJECT_CONTEXT.md  # Project goals and context (update as needed)
├── TODO.md             # Task list (primary work tracker)
├── QUESTIONS.md        # Questions for human (blocking mechanism)
├── LESSONS.md          # Accumulated knowledge (append-only)
├── src/                # Source code
└── output/             # Generated outputs, reports, analysis
```

---

## Project Context

Read `PROJECT_CONTEXT.md` for the specific goals and context of this project.
