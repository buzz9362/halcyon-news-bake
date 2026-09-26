"""Run the pronunciation rulebook lint on this repo's phonetics tables and bake.py (Sep 26 2026).

The lint itself lives with the apps (App Market Submission/_catalog_state/tools/pronunciation_lint.py)
so the device tables and the baked tables are checked by ONE rule set. This wrapper runs it in
baker-only mode against this checkout. Run it before every push of this repo (a push is a deploy):

    python tools/pronunciation_lint_check.py

Exit codes are the lint's: 0 clean, 1 unexplained hits, 2 broken control / lint not found (fails closed).
Set PRONUNCIATION_LINT to the lint's path if the apps tree is not beside this repo.
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CANDIDATES = [
    os.environ.get("PRONUNCIATION_LINT", ""),
    os.path.join(os.path.dirname(HERE), "App Market Submission", "_catalog_state", "tools", "pronunciation_lint.py"),
]


def main() -> int:
    lint = next((p for p in CANDIDATES if p and os.path.exists(p)), None)
    if not lint:
        print("PRONUNCIATION LINT NOT FOUND (set PRONUNCIATION_LINT): refusing to call the tables clean")
        return 2
    cmd = [sys.executable, lint, "--gate", "--baker-only", "--baker", HERE] + sys.argv[1:]
    return subprocess.call(cmd)


if __name__ == "__main__":
    sys.exit(main())
