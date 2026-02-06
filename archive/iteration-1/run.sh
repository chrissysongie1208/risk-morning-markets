#!/bin/bash
# Single run - completes one TODO then exits
set -e

# Navigate to script directory (so relative paths work from anywhere)
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  🤖 Single Run - $SCRIPT_DIR"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Check for pending questions first
# Pattern matches "**Status**: PENDING" (actual question) but not "PENDING | ANSWERED" (template example)
if grep -q '\*\*Status\*\*: PENDING$' QUESTIONS.md 2>/dev/null; then
    echo ""
    echo "  ⏸  Pending question in QUESTIONS.md"
    echo "     Answer the question and change status to ANSWERED, then re-run."
    exit 1
fi

# Check if there are any TODOs to work on
if ! grep -q '^\- \[ \]' TODO.md 2>/dev/null; then
    echo ""
    echo "  ✅ No pending [ ] TODOs remaining."
    exit 0
fi

# Run Claude
claude -p "$(cat PROMPT.md)" --dangerously-skip-permissions

echo ""
echo "  ✅ Run complete."
