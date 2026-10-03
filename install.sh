#!/usr/bin/env bash
# Kilanvil setup.
#
# Kilanvil is standard library only, so there is nothing to download: this
# script verifies the interpreter, proves the module imports and runs, and runs
# the test suite.  It installs nothing, calls no system package manager, starts
# no server, prompts for nothing, and EXITS.
#
#   bash install.sh
#
set -euo pipefail
cd "$(dirname "$0")"

if [ -n "${PYTHON:-}" ]; then
    PY="$PYTHON"
elif command -v python3 > /dev/null 2>&1; then
    PY=python3
elif command -v python > /dev/null 2>&1; then
    PY=python
else
    printf 'install: python 3.8+ is required but was not found on PATH\n' >&2
    printf 'install: see INSTALL.md for the prerequisite list\n' >&2
    exit 1
fi
printf 'install: using %s (%s)\n' "$PY" "$("$PY" -c 'import sys; print(sys.version.split()[0])')"

printf 'install: checking the interpreter version\n'
"$PY" - <<'PYVERSION'
import sys

if sys.version_info < (3, 8):
    sys.stderr.write(
        "install: kilanvil needs Python 3.8 or newer, found %s\n"
        % sys.version.split()[0]
    )
    raise SystemExit(1)
PYVERSION

printf 'install: no third-party dependencies to install (standard library only)\n'

printf 'install: compiling kilanvil.py\n'
"$PY" -m py_compile kilanvil.py

printf 'install: importing the module (fails loudly on any import-time error)\n'
"$PY" -c 'import kilanvil; print("install: kilanvil %s loaded" % kilanvil.VERSION)'

printf 'install: smoke check of the three subcommands\n'
"$PY" kilanvil.py cone 6 > /dev/null
"$PY" kilanvil.py schedule --seg 100:600:0 --seg -150:400:0 > /dev/null
"$PY" kilanvil.py glaze --line frit:50 --line kaolin:50 --batch 1000 > /dev/null
printf 'install: cone, schedule and glaze all ran with exit status 0\n'

printf 'install: running the test suite\n'
"$PY" -m unittest test_kilanvil

printf '\ninstall: setup complete.\n'
printf 'install: demo      -> bash demo.sh\n'
printf 'install: usage     -> %s kilanvil.py --help\n' "$PY"
printf 'install: tests     -> %s -m unittest test_kilanvil\n' "$PY"
