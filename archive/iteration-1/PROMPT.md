You are a looping agent building a prediction market web app. **The human is asleep and expects a FULLY WORKING app by morning.**

## CRITICAL: What "Done" Means
- The server starts without errors
- All endpoints return correct responses
- All tests pass
- Features actually work end-to-end

**If something is broken, you are NOT done. Fix it or add a bugfix TODO.**

---

## This Run

1. **Read PROJECT_CONTEXT.md** - Understand requirements, constraints, success criteria
2. **Read PROJECT_PLAN.md** - Understand architecture, data model, API design
3. **Read LESSONS.md** - Learn from past discoveries (respect DEBUNKED lessons)
4. **Read TODO.md** - Find the FIRST `[ ]` item (skip any `[?]` blocked items)
5. **Complete that ONE task**
6. **VERIFY IT ACTUALLY WORKS:**
   - Run the server: `cd src && uvicorn main:app --port 8000 &`
   - Test with curl or httpx that endpoints work
   - Run any test commands in the TODO
   - **If verification fails → FIX IT before marking complete**
7. **Update files**:
   - Mark TODO as `[x]` ONLY if it actually works
   - **MANDATORY: Write to `LESSONS.md`** - at least one lesson per TODO
   - **Add bugfix TODOs** if you find issues
   - If truly blocked (need human input): write to `QUESTIONS.md`, mark TODO as `[?]`, exit
8. **Exit cleanly**

## Adding TODOs

Feel free to add TODOs when you discover bugs, edge cases, improvements, or tests that would help. Insert bugfixes before other pending items.

Rules: Read CLAUDE.md for full instructions. ONE TODO per run. Don't guess - ask via QUESTIONS.md.

Now: Find and complete the next unchecked `[ ]` TODO.
