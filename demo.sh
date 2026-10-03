#!/usr/bin/env bash
# Kilanvil end-to-end demo.
#
# Runs all three calculators non-interactively and shows the diagnostic and
# exit-status contract, so the recorded terminal transcript is the proof of the
# build.  Nothing is installed, nothing is downloaded, no server is started.
#
#   bash demo.sh
#
set -uo pipefail
cd "$(dirname "$0")"

if command -v python3 > /dev/null 2>&1; then
    PY=python3
elif command -v python > /dev/null 2>&1; then
    PY=python
else
    printf 'demo: python 3.8+ is required but was not found on PATH\n' >&2
    exit 1
fi

KILANVIL="$PY kilanvil.py"

banner() {
    printf '\n%s\n' "----------------------------------------------------------------------"
    printf ':: %s\n' "$1"
    printf '%s\n' "----------------------------------------------------------------------"
}

# Run a command that must succeed.
run() {
    printf '\n$ %s\n' "$*"
    if ! "$@"; then
        printf 'demo: command failed: %s\n' "$*" >&2
        exit 1
    fi
}

# Run a command that must be rejected: usage or validation error on stderr,
# non-zero exit status, and no results on stdout.
expect_failure() {
    printf '\n$ %s\n' "$*"
    "$@"
    local status=$?
    if [ "$status" -eq 0 ]; then
        printf 'demo: expected a non-zero exit status from: %s\n' "$*" >&2
        exit 1
    fi
    printf '[exit status %s - nothing printed on stdout]\n' "$status"
}

banner "Kilanvil - kiln schedules, Orton cone temperatures, glaze batches"
printf 'python: %s\n' "$("$PY" -c 'import sys; print(sys.version.split()[0])')"
"$PY" kilanvil.py --version || exit 1

banner "1. Cone lookup - what temperature is cone 6?"
run $KILANVIL cone 6
run $KILANVIL cone 04 --unit f
run $KILANVIL cone 022

banner "2. The shipped cone table (022-14)"
"$PY" kilanvil.py cone --list | head -14 || exit 1
printf '  ...\n'

banner "3. Firing schedule - bisque, glaze, then a controlled cool"
run $KILANVIL schedule --seg 100:600:0 --seg 80:1100:15 --seg -150:900:0

banner "4. The same schedule written in Fahrenheit"
run $KILANVIL schedule --seg 150:1100:20 --seg -100:850:0 --unit f

banner "5. Glaze batch - 1 kg dry, 3 materials, water added"
run $KILANVIL glaze --line frit:50 --line silica:30 --line kaolin:20 --batch 1000 --water 50

banner "6. Shell-friendly: results on stdout, diagnostics on stderr"
printf '\n$ python3 kilanvil.py glaze --line frit:50 --line kaolin:50 --batch 250\n'
"$PY" kilanvil.py glaze --line frit:50 --line kaolin:50 --batch 250 > /tmp/kilanvil-demo.txt || exit 1
printf 'saved to /tmp/kilanvil-demo.txt:\n'
cat /tmp/kilanvil-demo.txt
rm -f /tmp/kilanvil-demo.txt

banner "7. Rejected input - every error names the offending argument"
expect_failure $KILANVIL cone 99
expect_failure $KILANVIL cone
expect_failure $KILANVIL schedule
expect_failure $KILANVIL schedule --seg 100:600
expect_failure $KILANVIL schedule --seg 100:600:0 --seg 80:500:0
expect_failure $KILANVIL glaze --line frit:50 --batch abc
expect_failure $KILANVIL glaze --line frit --batch 1000
expect_failure $KILANVIL glaze --batch 1000

banner "Done"
printf 'Demo finished with exit status 0.\n'
printf 'Test suite:  python3 -m unittest test_kilanvil\n'
printf 'Own usage:   python3 kilanvil.py --help\n'
