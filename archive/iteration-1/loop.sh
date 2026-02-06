#!/bin/bash
# Continuous loop - keeps running until all TODOs are done or blocked
set -e

# Navigate to script directory (so relative paths work from anywhere)
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Configuration
MAX_ITERS=${MAX_ITERS:-50}    # Override with: MAX_ITERS=50 ./loop.sh
iteration=0
start_time=$(date +%s)

# Header
echo "╔════════════════════════════════════════════════════════════╗"
echo "║                    CLAUDE LOOP                             ║"
echo "╠════════════════════════════════════════════════════════════╣"
echo "║  Directory:  $SCRIPT_DIR"
echo "║  Max Iters:  $MAX_ITERS"
echo "║  Press Ctrl+C to stop                                      ║"
echo "╚════════════════════════════════════════════════════════════╝"

while :; do
    iteration=$((iteration + 1))
    elapsed=$(($(date +%s) - start_time))

    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  Iteration $iteration / $MAX_ITERS    (elapsed: ${elapsed}s)"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    # Check max iterations
    if [ "$iteration" -gt "$MAX_ITERS" ]; then
        echo "  ⛔ Reached max iterations ($MAX_ITERS). Stopping."
        break
    fi

    # Check for pending questions BEFORE running Claude
    # Pattern matches "**Status**: PENDING" (actual question) but not "PENDING | ANSWERED" (template example)
    if grep -q '\*\*Status\*\*: PENDING$' QUESTIONS.md 2>/dev/null; then
        echo ""
        echo "  ⏸  PAUSED: Pending question in QUESTIONS.md"
        echo "     Answer the question and change status to ANSWERED, then re-run."
        break
    fi

    # Check if there are any TODOs to work on
    if ! grep -q '^\- \[ \]' TODO.md 2>/dev/null; then
        echo ""
        echo "  ✅ No pending [ ] TODOs remaining."
        echo "     Add more TODOs or check QUESTIONS.md for blocked items."
        echo ""
        echo "     Press Enter to check again, or Ctrl+C to stop..."
        read
        echo ""
        echo "  🔄 Resuming loop..."
        continue
    fi

    # Run Claude
    echo "  🤖 Running Claude..."
    claude -p "$(cat PROMPT.md)" --dangerously-skip-permissions

    # Brief pause between iterations
    sleep 1
done

# Footer
elapsed=$(($(date +%s) - start_time))
echo ""
echo "╔════════════════════════════════════════════════════════════╗"
echo "║                    LOOP COMPLETE                           ║"
echo "╠════════════════════════════════════════════════════════════╣"
echo "║  Total Iterations: $iteration"
echo "║  Total Time:       ${elapsed}s"
echo "╚════════════════════════════════════════════════════════════╝"
