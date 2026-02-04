#!/bin/bash
# Continuous loop - keeps running until all TODOs are done or blocked
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

MAX_ITERS=${MAX_ITERS:-50}
iteration=0
start_time=$(date +%s)

echo "╔════════════════════════════════════════════════════════════╗"
echo "║              MORNING MARKETS - CLAUDE LOOP                 ║"
echo "╠════════════════════════════════════════════════════════════╣"
echo "║  Live: https://risk-morning-markets.onrender.com           ║"
echo "║  Max Iters: $MAX_ITERS                                            ║"
echo "║  Press Ctrl+C to stop                                      ║"
echo "╚════════════════════════════════════════════════════════════╝"

while :; do
    iteration=$((iteration + 1))
    elapsed=$(($(date +%s) - start_time))

    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  Iteration $iteration / $MAX_ITERS    (elapsed: ${elapsed}s)"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    if [ "$iteration" -gt "$MAX_ITERS" ]; then
        echo "  ⛔ Reached max iterations ($MAX_ITERS). Stopping."
        break
    fi

    if grep -q '\*\*Status\*\*: PENDING$' QUESTIONS.md 2>/dev/null; then
        echo ""
        echo "  ⏸  PAUSED: Pending question in QUESTIONS.md"
        echo "     Answer the question and change status to ANSWERED, then re-run."
        break
    fi

    if ! grep -q '^\- \[ \]' TODO.md 2>/dev/null; then
        echo ""
        echo "  ✅ No pending [ ] TODOs remaining."
        echo "     Add more TODOs to TODO.md or Ctrl+C to stop."
        echo ""
        echo "     Press Enter to check again..."
        read
        continue
    fi

    echo "  🤖 Running Claude..."
    claude -p "$(cat PROMPT.md)" --dangerously-skip-permissions

    sleep 1
done

elapsed=$(($(date +%s) - start_time))
echo ""
echo "╔════════════════════════════════════════════════════════════╗"
echo "║                    LOOP COMPLETE                           ║"
echo "╠════════════════════════════════════════════════════════════╣"
echo "║  Total Iterations: $iteration"
echo "║  Total Time:       ${elapsed}s"
echo "╚════════════════════════════════════════════════════════════╝"
