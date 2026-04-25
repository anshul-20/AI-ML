import os
import stat
import sys

PRE_COMMIT_HOOK = """#!/bin/sh
# This hook captures the staged Git diff and sends it to the local AI Review Agent.

# Extract the staged difference
DIFF=$(git diff --cached)

if [ -z "$DIFF" ]; then
    exit 0
fi

echo "Sending staged difference to AI Code Review Agent..."

# We use python to safely JSON-encode the diff payload
PAYLOAD=$(python -c '
import json
import sys
diff = sys.stdin.read()
data = {
    "repo": "local-repo",
    "pr_id": 0,
    "diff": diff
}
print(json.dumps(data))
' << EOF
$DIFF
EOF
)

# Call the local API
RESPONSE=$(echo "$PAYLOAD" | curl -s -X POST http://127.0.0.1:8001/review \
    -H "Content-Type: application/json" \
    -H "X-API-Token: 0d1ed11b2b8e1e39e00f2a63024713474949194b964dfa3cc54bef2515c3f796" \
    -d @-)

if [ -z "$RESPONSE" ]; then
    echo "AI Code Review Agent is unreachable. Ensure 'uvicorn app.main:app' is running."
    exit 0 # Allow commit if agent is down
fi

SCORE=$(echo "$RESPONSE" | python -c 'import json, sys; print(json.load(sys.stdin).get("score", 0.0))' 2>/dev/null)
SUMMARY=$(echo "$RESPONSE" | python -c 'import json, sys; print(json.load(sys.stdin).get("summary", "Could not parse review"))' 2>/dev/null)

echo ""
echo "=== AI Review Results ==="
echo "Score: $SCORE / 10.0"
echo "Summary: $SUMMARY"
echo "========================="

# Prevent commit if score is worse than 5.0
if python -c "import sys; score = float(sys.argv[1]); sys.exit(0 if score >= 5.0 else 1)" "$SCORE" 2>/dev/null; then
    echo "Code quality looks acceptable."
    exit 0
else
    echo "Review failed! Score $SCORE is below the minimum threshold of 5.0."
    echo "Tip: Address the issues, or bypass this hook via 'git commit --no-verify'."
    exit 1
fi
"""

def main():
    if not os.path.isdir(".git"):
        print("Error: .git directory not found in the current directory.")
        print("Please run this script from the root of a Git repository.")
        sys.exit(1)

    hook_path = os.path.join(".git", "hooks", "pre-commit")
    
    with open(hook_path, "w", encoding="utf-8") as f:
        f.write(PRE_COMMIT_HOOK)

    # make it executable
    st = os.stat(hook_path)
    os.chmod(hook_path, st.st_mode | stat.S_IEXEC)

    print(f"[SUCCESS] Successfully installed Git pre-commit hook at: {hook_path}")
    print("\nNext steps:")
    print("  1. Make sure your local review server is running: `uvicorn app.main:app --reload`")
    print("  2. Perform a `git commit`. The hook will analyze staged files and evaluate your code.")

if __name__ == "__main__":
    main()
