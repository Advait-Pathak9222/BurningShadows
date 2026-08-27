#!/usr/bin/env bash
#
# Clone-and-run entrypoint for reviewers.
#
# Runs the offline evidence path only: no API key, no network call, no GPU. It creates a
# virtualenv, installs the package, runs the quality gate, and regenerates the demo and the
# report so you can see the committed numbers being produced rather than taking them on
# trust.
#
# It is idempotent and does not leave the working tree dirty: the artifacts it regenerates
# are byte-identical to the committed ones, and the script checks that and tells you if they
# are not.
#
# The external-benchmark path (`make benchmarks`, `make toxicchat`) is NOT run here, because
# it downloads several GB from Hugging Face. Run it explicitly if you want to reproduce the
# public-corpus results.

set -euo pipefail

cd "$(dirname "$0")"

PYTHON="${PYTHON:-python3}"
VENV="${VENV:-.venv-submission}"

say() { printf '\n\033[1m==> %s\033[0m\n' "$1"; }
fail() { printf '\n\033[31mFAILED: %s\033[0m\n' "$1" >&2; exit 1; }

command -v "$PYTHON" >/dev/null 2>&1 || fail "no '$PYTHON' on PATH; set PYTHON=/path/to/python3"

version=$("$PYTHON" -c 'import sys; print("%d.%d" % sys.version_info[:2])')
case "$version" in
  3.1[1-9]|3.[2-9][0-9]) ;;
  *) fail "Python 3.11 or newer required, found $version" ;;
esac
say "Python $version"

say "Creating virtualenv in $VENV"
"$PYTHON" -m venv "$VENV"
# shellcheck disable=SC1091
if [ -f "$VENV/bin/activate" ]; then . "$VENV/bin/activate"; else . "$VENV/Scripts/activate"; fi

say "Installing (offline extras only)"
python -m pip install --quiet --upgrade pip
python -m pip install --quiet -e ".[dev]"

say "Quality gate: ruff, mypy --strict, pytest"
make check

say "Offline demo (no key, no network, no GPU)"
make demo

say "Regenerating the committed report"
make report

say "Checking the regenerated artifacts match what is committed"
if command -v git >/dev/null 2>&1 && git rev-parse --git-dir >/dev/null 2>&1; then
  dirty=$(git status --porcelain -- reports docs/results data/*.jsonl)
  if [ -n "$dirty" ]; then
    printf '\n\033[33mThese committed artifacts changed when regenerated:\033[0m\n%s\n' "$dirty"
    printf 'That means a number in the repository does not reproduce here. Please report it.\n'
    exit 2
  fi
  printf 'All regenerated artifacts are byte-identical to the committed ones.\n'
else
  printf 'Not a git checkout; skipping the byte-identity check.\n'
fi

say "Done"
cat <<'EOF'
What you just ran:
  make check    ruff, mypy --strict, and the full test suite
  make demo     builds the corpus, calibrates, runs scenarios, verifies the hash chain
  make report   regenerates reports/ and docs/results/summary.md

To reproduce the public-benchmark results (downloads several GB):
  make toxicchat     ToxicChat
  make benchmarks    Aegis, OR-Bench, BeaverTails, RAGTruth, and docs/results/benchmarks.md

To open the inspection console:
  make console       http://localhost:8501
EOF
