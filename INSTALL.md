# Installing and running Kilanvil

Kilanvil is a single Python file that uses only the standard library.
**There is no package manager step** - no `pip install`, no lockfile, no
`node_modules`, no system package. `install.sh` verifies the interpreter,
smoke-checks the three subcommands, runs the test suite and exits.

## 1. Prerequisites

| Requirement | Detail |
| --- | --- |
| Python | 3.8 or newer, available as `python3` (or `python`) on `PATH` |
| Everything else | None. No third-party packages, no compiler, no database, no network |
| Disk | The project directory only; Kilanvil writes no state |

Check the interpreter:

```bash
python3 --version     # expect Python 3.8.x or newer
```

Nothing is installed system-wide, and `install.sh` never uses `sudo`, `apt`,
`brew` or any other system package manager.

## 2. Set up (verifies, checks, exits)

```bash
cd kilanvil
bash install.sh
```

It is safe to re-run and prints, in order:

1. the interpreter it selected and its version,
2. a Python-version check (fails with a clear message below 3.8),
3. `python3 -m py_compile kilanvil.py` - syntax check,
4. `python3 -c "import kilanvil"` - import-time check (this catches any
   module-level error before you ever run a command),
5. a smoke run of `cone`, `schedule` and `glaze`,
6. `python3 -m unittest test_kilanvil` - the full test suite,
7. how to run the demo and the tool.

The script exits with status 0 on success and non-zero on failure. It does not
start a server and it does not leave a process running - Kilanvil is a
foreground command-line tool, so there is nothing to serve.

There is no separate migrate or seed step: the tool has no database and no
stored state, and the cone table is a constant inside `kilanvil.py`.

## 3. Run in dev

```bash
bash demo.sh                        # recorded end-to-end demonstration
python3 kilanvil.py --help          # the three subcommands and their flags
python3 kilanvil.py cone 6
python3 kilanvil.py schedule --seg 100:600:0 --seg 80:1100:15 --seg -150:900:0
python3 kilanvil.py glaze --line frit:50 --line silica:30 --line kaolin:20 --batch 1000
```

If `python3` is not on your `PATH`, substitute `python` (Windows) or call the
interpreter by absolute path. `demo.sh` and `install.sh` both pick `python3`
first and fall back to `python`; override with `PYTHON=/path/to/python bash install.sh`.

## 4. Test

```bash
python3 -m unittest test_kilanvil          # 65 tests
python3 -m unittest test_kilanvil -v       # one line per test
```

The suite needs no network, no fixtures on disk and no interactive input.

## 5. Environment variables

None. Kilanvil reads no environment variables, so there is no `.env` file and
no `.env.example` - on a fresh copy the documented commands above are all you
need. (`PYTHON` is honoured by the two shell scripts as a convenience only; it
is not read by the tool itself.)

## Troubleshooting

| Symptom | Cause and fix |
| --- | --- |
| `python3: command not found` | Python is not on `PATH`; install Python 3.8+ or use `PYTHON=/path/to/python bash install.sh` |
| `install: kilanvil needs Python 3.8 or newer` | The interpreter on `PATH` is older; put a 3.8+ interpreter first on `PATH` |
| `kilanvil: no cone label given ...` | Missing input, not a crash: the message includes the exact command to copy. Every diagnostic goes to stderr and exits 2 |
| A schedule is rejected as a descending target | A positive rate cannot target a lower temperature. Use a negative rate for the cooling ramp |
