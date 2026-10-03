# Using Kilanvil

Every example below is copy-pasteable and uses the documented invocation
`python3 kilanvil.py <subcommand> ...`. Results go to stdout, diagnostics go to
stderr, and the process exits `0` on success or `2` on a usage/validation error.

## Workflow 1: check a cone before you load the kiln

A glaze firing to cone 6 is a different temperature at a slow ramp than at a
fast one, so read both columns:

```bash
python3 kilanvil.py cone 6
```

```
  heating rate     Celsius   Fahrenheit
  -------------  ---------  -----------
  60 C/hr           1222 C       2232 F
  150 C/hr          1240 C       2264 F
```

If your kiln controller is set in Fahrenheit, ask for the Fahrenheit headline:

```bash
python3 kilanvil.py cone 6 --unit f
```

```
  > Headline: 2232 F (--unit f, 60 C/hr)
```

The `> Headline` line is the single highlighted reading: one unit, one rate, no
guessing which number the answer is.

Bisque firings are usually written in the single digits with a leading zero, and
Kilanvil never strips it - `04` is 1060 C, `4` is 1186 C:

```bash
python3 kilanvil.py cone 04 | head -3
python3 kilanvil.py cone 4  | head -3
```

Do not remember the number? Print the whole table and pick from it:

```bash
python3 kilanvil.py cone --list
python3 kilanvil.py cone --list | grep -E '^  (06|04|6|10) '
```

A cone that is not in the shipped set gets the nearest valid labels instead of a
bare failure:

```bash
$ python3 kilanvil.py cone 99
kilanvil: unknown cone '99' - not in the shipped 022-14 table; nearest shipped
          cones: 14, 13, 12
$ echo $?
2
```

## Workflow 2: write a firing schedule for a glaze firing

A segment is `RATE:TARGET:HOLD`, read as "climb at *rate* degrees per hour to
*target*, then hold for *hold* minutes". Ramps start from the previous segment's
target, and the first one starts at 20 C (68 F) unless you say otherwise.

```bash
python3 kilanvil.py schedule --seg 100:600:0 --seg 80:1100:15 --seg -150:900:0
```

```
Firing schedule - 3 segments, Celsius, starting at 20 C

   #  Direction  Rate        Target    Hold     Ramp min  Elapsed min
  --  ---------  ----------  --------  -------  --------  -----------
   1  heating    +100 C/hr   600 C     0 min       348.0        348.0
   2  heating    +80 C/hr    1100 C    15 min      375.0        738.0
   3  cooling    -150 C/hr   900 C     0 min        80.0        818.0
  --  ---------  ----------  --------  -------  --------  -----------

  Total hold: 15.0 min
  Total firing time: 818.0 min (13 h 38 min)
```

Read it as: five hours and forty-eight minutes to 600 C, six and a quarter hours
to 1100 C with a fifteen minute hold, then an eighty minute controlled cool.
The `Elapsed min` column is cumulative, so the last row *is* the total firing
time and you can tell the operator when the kiln will be done.

A cooling rate is written with a minus sign, and cooling ramps count forward in
elapsed time exactly like heating ramps:

```bash
python3 kilanvil.py schedule --seg 150:1100:20 --seg -100:850:0 --seg -40:200:0
```

Segments that contradict themselves are rejected before any table is printed:

```bash
$ python3 kilanvil.py schedule --seg 100:600:0 --seg 80:500:0
kilanvil: segment 2: target 500 C is below the previous end temperature 600 C
          on a heating ramp of +80 C/hr - use a negative rate for a cooling
          ramp
```

Common slip: a negative rate with a target *above* the previous one. That is a
cooling ramp trying to heat, and it is rejected with the segment number too.

Hand a schedule to a kiln that works in Fahrenheit with one flag:

```bash
python3 kilanvil.py schedule --seg 150:1100:20 --seg -100:850:0 --unit f
python3 kilanvil.py schedule --start 68 --seg 150:1100:20 --unit f
```

Save a schedule in your workshop log by redirecting stdout - the tool itself
writes nothing to disk:

```bash
python3 kilanvil.py schedule --seg 100:600:0 --seg 80:1100:15 > ~/firings/2019-06-14-glaze.txt
```

## Workflow 3: scale a glaze recipe to a batch

Give the recipe in parts and the dry batch weight you want:

```bash
python3 kilanvil.py glaze --line frit:50 --line silica:30 --line kaolin:20 --batch 1000
```

```
Glaze batch - 3 materials, 1000.0 g dry

  Material                  Parts   Grams (g)   % of unity
  --------------------  ---------  ----------  -----------
  frit                       50.0       500.0         50.0
  silica                     30.0       300.0         30.0
  kaolin                     20.0       200.0         20.0
  --------------------  ---------  ----------  -----------
  TOTAL                     100.0      1000.0        100.0
```

Tips that matter on the shop floor:

- **Batch size is the dry weight.** `--batch 1000` is a kilogram of dry
  material; the water is added on top of it.
- **The printed grams always re-add to the batch.** The tenths of a gram are
  allocated by largest remainder, so three equal materials print
  `333.4 / 333.3 / 333.3` for a total of exactly `1000.0`, and the percentages
  print `33.4 / 33.3 / 33.3` for exactly `100.0 %`. Never round the column
  yourself.
- **Parts are relative.** `--line frit:5 --line silica:3 --line kaolin:2` gives
  the same recipe as the 50/30/20 above.
- **Material names are yours.** Nothing is validated against a database, so any
  name without a colon works, including spaces if you quote it:

```bash
python3 kilanvil.py glaze --line "nepheline syenite:45" --line whiting:30 --line kaolin:25 --batch 500
```

Add water as a percentage of the dry batch to get the wet weight:

```bash
python3 kilanvil.py glaze --line frit:50 --line silica:30 --line kaolin:20 --batch 1000 --water 50
```

```
  Water 50.0 %: 500.0 g
  Wet batch weight: 1500.0 g
```

Rejected input names the offending line, every time:

```bash
$ python3 kilanvil.py glaze --line frit:50 --line silica:x --batch 1000
kilanvil: line 2: parts 'x' is not a number
$ python3 kilanvil.py glaze --line frit --batch 1000
kilanvil: line 1: malformed recipe line 'frit' - expected MATERIAL:PARTS (for
          example frit:50, material names cannot contain a colon)
$ python3 kilanvil.py glaze --line frit:50 --batch abc
kilanvil: --batch: size 'abc' is not a number
```

## Workflow 4: scripting and error handling

Every error is on stderr with a non-zero exit status, so shell logic can branch
on the tool without parsing output:

```bash
if python3 kilanvil.py cone "$CONE" > /tmp/cone.txt 2> /tmp/cone.err; then
    grep 'Headline' /tmp/cone.txt
else
    echo "cannot fire to cone $CONE:" >&2
    cat /tmp/cone.err >&2
fi
```

A quick workshop helper that prints a scaled batch only when the recipe is
valid:

```bash
#!/usr/bin/env bash
set -euo pipefail
recipe=(--line frit:50 --line silica:30 --line kaolin:20)
batch="${1:-1000}"
python3 kilanvil.py glaze "${recipe[@]}" --batch "$batch" --water 45
```

Exit statuses are deliberately coarse - `0` success, `2` usage or validation
error - because that is what a shell needs to branch on. Nothing is written to
disk and no state is kept between invocations, so results are reproducible: the
same arguments give byte-identical output every run and on every platform.

Missing input is never a hang and never a bare failure. Each of these prints the
subcommand's usage plus an example you can copy, then exits 2:

```bash
python3 kilanvil.py cone
python3 kilanvil.py schedule
python3 kilanvil.py glaze --batch 1000
```

## What is deliberately not here

- **No colour, no `--json`.** Plain ASCII columns and the exit status are the
  contract; redirected files and non-UTF-8 terminals behave identically.
- **No controller profile or CSV export.** `> schedule.txt` is the save path,
  and per-brand controller formats are a long tail.
- **No oxide analysis, UMF/Seger formula or materials database.** Those need an
  oxide composition database, which the tool deliberately does not ship.
- **No saved schedules or recipes.** Schedules and recipes live for one process;
  the shell is the storage.
- **No login or accounts.** An offline single-file tool has no boundary to
  protect and no store to isolate.
