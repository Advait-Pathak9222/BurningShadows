#!/usr/bin/env bash
#
# Clone-and-run entrypoint for reviewers.
#
#   git clone https://github.com/Advait-Pathak9222/BurningShadows.git
#   cd BurningShadows
#   bash run_submission.sh
#
# Runs the offline evidence path only: no API key, no network call after the install, no
# GPU, no local model. It creates a virtualenv, installs the package, runs the quality
# gate, then regenerates the demo and the report so you can watch the committed numbers
# being produced rather than taking them on trust.
#
# It is idempotent and does not leave the working tree dirty. The artifacts it regenerates
# are byte-identical to the committed ones, and the last step checks exactly that and tells
# you if they are not.
#
# The only hard requirements are Python 3.11 or newer and git. GNU make is NOT required:
# every step below is the same command the equivalent Makefile target runs, spelled out, so
# the script works on a machine without a build toolchain. The make target is named beside
# each step for anyone who has make and prefers it.
#
# The external-benchmark path is deliberately NOT run here, because it downloads several GB
# from Hugging Face. See the closing note for how to run it.

set -euo pipefail

cd "$(dirname "$0")"

VENV="${VENV:-.venv-submission}"

say()  { printf '\n\033[1m==> %s\033[0m\n' "$1"; }
note() { printf '    %s\n' "$1"; }
fail() { printf '\n\033[31mFAILED: %s\033[0m\n' "$1" >&2; exit 1; }

# --------------------------------------------------------------------------------------
# Find an interpreter that actually runs
# --------------------------------------------------------------------------------------
#
# `command -v python3` is not enough to know Python exists. A default Windows install ships
# an App Execution Alias at that exact path which resolves, runs, prints "Python was not
# found" and exits 0, so a naive check sails past it and the failure surfaces later as
# something incomprehensible. The only reliable test is to run the interpreter and see
# whether it returns the version string we asked for.

usable_python() {
  local candidate="$1" reported
  command -v "$candidate" >/dev/null 2>&1 || return 1
  reported=$("$candidate" -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null) || return 1
  case "$reported" in
    3.1[1-9]|3.[2-9][0-9]) PYTHON_VERSION="$reported"; return 0 ;;
    *) return 1 ;;
  esac
}

REQUESTED="${PYTHON:-}"
PYTHON=""
PYTHON_VERSION=""

# An explicit PYTHON= is an instruction, not a hint. If it does not work, say so about that
# interpreter rather than quietly succeeding with a different one the caller did not choose.
if [ -n "$REQUESTED" ]; then
  usable_python "$REQUESTED"     || fail "PYTHON=$REQUESTED is not a working Python 3.11 or newer.
    Check the path, or unset PYTHON to let this script search for one."
  PYTHON="$REQUESTED"
else
  for candidate in python3 python py; do
    if usable_python "$candidate"; then PYTHON="$candidate"; break; fi
  done
fi

if [ -z "$PYTHON" ]; then
  fail "no working Python 3.11+ found.
    Tried: python3, python, py.
    Install Python 3.11 or newer, or point at one directly:
        PYTHON=/full/path/to/python3 bash run_submission.sh
    On Windows, note that the 'python3' shim in WindowsApps is a Microsoft Store
    placeholder, not an interpreter. This script skips it on purpose."
fi

command -v git >/dev/null 2>&1 || note "git not found; the byte-identity check will be skipped."

say "Python $PYTHON_VERSION ($PYTHON)"

# --------------------------------------------------------------------------------------
# Environment
# --------------------------------------------------------------------------------------

say "Creating virtualenv in $VENV"
"$PYTHON" -m venv "$VENV" || fail "could not create a virtualenv in $VENV.
    On Debian and Ubuntu this usually means the venv module is packaged separately:
        sudo apt install python3-venv"

# Layout differs between POSIX and Windows, so resolve the interpreter rather than relying
# on `activate` having put the right one first on PATH.
if [ -x "$VENV/bin/python" ]; then
  VPY="$VENV/bin/python"
elif [ -x "$VENV/Scripts/python.exe" ]; then
  VPY="$VENV/Scripts/python.exe"
else
  fail "virtualenv created but no interpreter found under $VENV"
fi

say "Installing the package and its test dependencies"
note "make install"
"$VPY" -m pip install --quiet --upgrade pip setuptools wheel \
  || fail "could not upgrade pip inside the virtualenv"
"$VPY" -m pip install --quiet -e ".[dev]" \
  || fail "install failed. If this is a network error, retry; nothing after this step
    needs the network."

# Everything below runs inside the virtualenv, so a stray global install cannot be what
# gets exercised. Import the package once before spending time on the gate, because a
# broken install is far cheaper to diagnose here than three steps later.
"$VPY" -c 'import controlplane, sys; print("    controlplane imports cleanly on", sys.version.split()[0])' \
  || fail "the package installed but does not import"

# --------------------------------------------------------------------------------------
# The gate
# --------------------------------------------------------------------------------------

say "Quality gate: ruff, mypy --strict, pytest"
note "make check"
"$VPY" -m ruff check controlplane tests console || fail "ruff found lint errors"
"$VPY" -m mypy --strict controlplane            || fail "mypy --strict found type errors"
"$VPY" -m pytest -q                             || fail "the test suite did not pass"

# --------------------------------------------------------------------------------------
# The evidence
# --------------------------------------------------------------------------------------

say "Building the corpus"
note "make data"
"$VPY" -m controlplane.cli data || fail "corpus generation failed"

say "Offline demo: calibrate, run scenarios, verify the hash chain"
note "make demo"
"$VPY" -m controlplane.cli demo || fail "the demo did not complete, or the audit chain did not verify"

say "Regenerating the committed report"
note "make report"
"$VPY" -m controlplane.cli report || fail "report generation failed"

# --------------------------------------------------------------------------------------
# Did the numbers reproduce?
# --------------------------------------------------------------------------------------

say "Checking the regenerated artifacts match what is committed"
if command -v git >/dev/null 2>&1 && git rev-parse --git-dir >/dev/null 2>&1; then
  dirty=$(git status --porcelain -- reports docs/results data/*.jsonl || true)
  if [ -n "$dirty" ]; then
    printf '\n\033[33mThese committed artifacts changed when regenerated:\033[0m\n%s\n' "$dirty"
    printf 'That means a number in the repository does not reproduce here. Please report it.\n'
    exit 2
  fi
  printf '    All regenerated artifacts are byte-identical to the committed ones.\n'
else
  printf '    Not a git checkout, or git is unavailable; skipping the byte-identity check.\n'
fi

say "Done"
cat <<EOF
What you just ran, and the make target for each:

  make check     ruff, mypy --strict, and the full test suite
  make data      regenerates the 3000-row corpus from its seed
  make demo      calibrates, runs the scenarios, verifies the hash chain
  make report    regenerates reports/ and docs/results/

Everything above ran inside $VENV, offline, with no API key and no model.

To open the inspection console and the live prototype (seven views, one app):

  $VPY -m streamlit run console/streamlit_app.py      # make console

To reproduce the public-benchmark results (downloads several GB from Hugging Face):

  $VPY -m controlplane.cli toxicchat                  # make toxicchat
  $VPY -m controlplane.cli benchmarks                 # make benchmarks

To refit the calibration maps from reviewer labels in the audit chain, which needs
the report above to have written reviews into it:

  $VPY -m controlplane.cli relearn                    # make relearn
EOF
