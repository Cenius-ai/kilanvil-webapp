#!/usr/bin/env python3
"""Kilanvil - a workshop command-line tool for potters.

Three jobs, one prompt:

  * ``cone``     - Orton standard cone 022-14 deformation temperatures (C and F)
  * ``schedule`` - a numbered kiln firing schedule with cumulative elapsed times
  * ``glaze``    - a ratio glaze recipe scaled to a dry batch weight

Design notes: standard library only, a single file, no network, no on-disk
state, deterministic ASCII output on stdout, diagnostics on stderr and a stable
exit status (0 success, 2 usage or validation error).  Results are plain
fixed-width text so ``python3 kilanvil.py ... > firing.txt`` is the save path.

Committed design direction (see DESIGN.md): calm-precise CLI, system monospace,
compact aligned columns, a single accent (oklch(0.58 0.12 268) / #5c76c1) used
as one textual highlight for the primary reading, never as a colour-only signal.
"""

from __future__ import annotations

import argparse
import math
import os
import sys
import textwrap
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

PROGRAM = "kilanvil"
VERSION = "1.0.0"

EXIT_OK = 0
EXIT_ERROR = 2

#: Width used for wrapped diagnostics on stderr.
ERROR_WIDTH = 78

#: Column gap for every fixed-width table (compact density).
COLUMN_GAP = "  "
TABLE_INDENT = "  "

#: Ambient starting temperature of a firing, per working unit.  A schedule's
#: first segment ramps from here unless ``--start`` overrides it.
AMBIENT_START = {"c": 20.0, "f": 68.0}

#: The heating rate whose column is the headline reading for a cone.
HEADLINE_RATE_C_PER_HOUR = 60.0

USAGE_CONE = (
    "kilanvil cone <label> [--unit c|f] [--list]"
)
USAGE_SCHEDULE = (
    "kilanvil schedule --seg RATE:TARGET:HOLD [--seg ...] [--unit c|f] [--start TEMP]"
)
USAGE_GLAZE = (
    "kilanvil glaze --line MATERIAL:PARTS [--line ...] --batch GRAMS [--water PCT]"
)

HINTS_CONE = ("kilanvil cone 6", "kilanvil cone 04", "kilanvil cone --list")
HINTS_SCHEDULE = (
    "kilanvil schedule --seg 100:600:0 --seg 80:1100:15 --seg -150:900:0",
)
HINTS_GLAZE = (
    "kilanvil glaze --line frit:50 --line silica:30 --line kaolin:20 --batch 1000",
)


class UsageError(Exception):
    """A user-facing usage or validation error (reported on stderr, exit 2)."""

    def __init__(
        self,
        message: str,
        usage: Optional[str] = None,
        hints: Sequence[str] = (),
    ) -> None:
        super().__init__(message)
        self.message = message
        self.usage = usage
        self.hints = tuple(hints)


# ---------------------------------------------------------------------------
# Cone table (F1)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Cone:
    """One Orton standard pyrometric cone from the shipped table."""

    label: str
    temp_c_at_60cph: float
    temp_c_at_150cph: float
    sort_rank: int


#: Orton standard cones 022-14, final deformation (end-point) temperature in
#: degrees Celsius at the two heating rates the published chart uses
#: (60 C/hr = 108 F/hr and 150 C/hr = 270 F/hr).  Labels are the keys: "04" and
#: "4" are different cones and leading zeros are never stripped.
_CONE_TABLE: Tuple[Tuple[str, float, float], ...] = (
    ("022", 586.0, 606.0),
    ("021", 600.0, 622.0),
    ("020", 626.0, 651.0),
    ("019", 668.0, 695.0),
    ("018", 698.0, 727.0),
    ("017", 738.0, 769.0),
    ("016", 773.0, 806.0),
    ("015", 800.0, 834.0),
    ("014", 827.0, 864.0),
    ("013", 852.0, 889.0),
    ("012", 875.0, 914.0),
    ("011", 898.0, 938.0),
    ("010", 909.0, 950.0),
    ("09", 945.0, 984.0),
    ("08", 955.0, 997.0),
    ("07", 984.0, 1023.0),
    ("06", 1000.0, 1042.0),
    ("05", 1032.0, 1068.0),
    ("04", 1060.0, 1101.0),
    ("03", 1085.0, 1120.0),
    ("02", 1100.0, 1140.0),
    ("01", 1137.0, 1171.0),
    ("1", 1154.0, 1186.0),
    ("2", 1163.0, 1198.0),
    ("3", 1170.0, 1206.0),
    ("4", 1186.0, 1224.0),
    ("5", 1196.0, 1233.0),
    ("6", 1222.0, 1240.0),
    ("7", 1240.0, 1259.0),
    ("8", 1250.0, 1268.0),
    ("9", 1260.0, 1280.0),
    ("10", 1285.0, 1305.0),
    ("11", 1305.0, 1325.0),
    ("12", 1325.0, 1345.0),
    ("13", 1345.0, 1365.0),
    ("14", 1365.0, 1387.0),
)

CONES: Tuple[Cone, ...] = tuple(
    Cone(label, c60, c150, rank)
    for rank, (label, c60, c150) in enumerate(_CONE_TABLE)
)

CONE_BY_LABEL: Dict[str, Cone] = {cone.label: cone for cone in CONES}

#: Cone labels in Orton order, coolest first (drives --list and suggestions).
CONE_LABEL_ORDER: Tuple[str, ...] = tuple(cone.label for cone in CONES)


def cone_scale_key(label: str) -> Optional[int]:
    """Place a typed cone label on a single numeric Orton axis.

    A leading zero puts the cone below cone 1 (so "04" < "4" and "09" is hotter
    than "010"), which is what makes a nearest-cone suggestion meaningful.
    Returns ``None`` for labels that are not numeric at all.
    """
    if not label.isdigit():
        return None
    value = int(label)
    if label.startswith("0") and len(label) > 1:
        return -value
    return value


def nearest_cone_labels(label: str, limit: int = 3) -> List[str]:
    """Return up to ``limit`` shipped labels closest to ``label`` on the cone axis."""
    key = cone_scale_key(label)
    if key is None:
        return []
    ranked = sorted(
        CONES,
        key=lambda cone: (
            abs(cone_scale_key(cone.label) - key),
            cone_scale_key(cone.label),
        ),
    )
    return [cone.label for cone in ranked[:limit]]


def unknown_cone_message(label: str) -> str:
    """Explain an unknown cone label and name the nearest shipped ones."""
    nearest = nearest_cone_labels(label)
    if nearest:
        return (
            "unknown cone {!r} - not in the shipped 022-14 table; "
            "nearest shipped cones: {}".format(label, ", ".join(nearest))
        )
    return (
        "unknown cone {!r} - the shipped table holds Orton cones 022 to 14 "
        "(for example 06, 04, 6 or 10)".format(label)
    )


# ---------------------------------------------------------------------------
# Number and unit formatting helpers
# ---------------------------------------------------------------------------


def celsius_to_fahrenheit(celsius: float) -> float:
    """Convert degrees Celsius to degrees Fahrenheit."""
    return celsius * 9.0 / 5.0 + 32.0


def format_trim(value: float) -> str:
    """Format a number without a trailing ``.0`` and without float noise."""
    if abs(value - round(value)) < 1e-9:
        return str(int(round(value)))
    return "{:.2f}".format(value).rstrip("0").rstrip(".")


def format_degrees(value: float, unit: str) -> str:
    """Format a whole-degree temperature with its unit, e.g. ``1222 C``."""
    return "{} {}".format(int(round(value)), unit.upper())


def format_rate(rate_per_hour: float, unit: str) -> str:
    """Format a signed ramp rate, e.g. ``+100 C/hr`` or ``-150 C/hr``."""
    sign = "+" if rate_per_hour > 0 else "-"
    return "{}{} {}/hr".format(sign, format_trim(abs(rate_per_hour)), unit.upper())


def unit_name(unit: str) -> str:
    """Human name of a temperature unit: ``c`` -> ``Celsius``."""
    return "Celsius" if unit == "c" else "Fahrenheit"


def parse_float(token: str, what: str, where: str) -> float:
    """Parse a finite float, or raise a UsageError naming the offending token."""
    try:
        value = float(token)
    except (TypeError, ValueError):
        raise UsageError("{}: {} {!r} is not a number".format(where, what, token))
    if not math.isfinite(value):
        raise UsageError(
            "{}: {} {!r} is not a finite number".format(where, what, token)
        )
    return value


# ---------------------------------------------------------------------------
# Fixed-width output helpers
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Column:
    """One fixed-width table column."""

    header: str
    width: int
    right_align: bool = True


def _cell(text: str, column: Column) -> str:
    return text.rjust(column.width) if column.right_align else text.ljust(column.width)


def table_row(columns: Sequence[Column], values: Sequence[str]) -> str:
    """Render one body row of a table."""
    return TABLE_INDENT + COLUMN_GAP.join(
        _cell(value, column) for value, column in zip(values, columns)
    )


def table_rule(columns: Sequence[Column]) -> str:
    """Render the rule line under a table header or above a total row."""
    return TABLE_INDENT + COLUMN_GAP.join("-" * column.width for column in columns)


def render_table(
    columns: Sequence[Column],
    rows: Sequence[Sequence[str]],
) -> List[str]:
    """Render a header, a rule and one line per row."""
    lines = [table_row(columns, [column.header for column in columns])]
    lines.append(table_rule(columns))
    lines.extend(table_row(columns, row) for row in rows)
    return lines


def emit(lines: Sequence[str]) -> None:
    """Write result lines to stdout (never to stderr)."""
    sys.stdout.write("\n".join(lines) + "\n")


# ---------------------------------------------------------------------------
# cone (F1)
# ---------------------------------------------------------------------------


def cone_detail_lines(cone: Cone, unit: str) -> List[str]:
    """Render one cone's temperatures, with ``unit`` as the headline column."""
    celsius = Column("Celsius", 9)
    fahrenheit = Column("Fahrenheit", 11)
    columns = [Column("heating rate", 13, right_align=False)]
    columns += [fahrenheit, celsius] if unit == "f" else [celsius, fahrenheit]

    rows = []
    for rate_c, temp_c in (
        (60.0, cone.temp_c_at_60cph),
        (150.0, cone.temp_c_at_150cph),
    ):
        label = "{} C/hr".format(format_trim(rate_c))
        readings = [
            format_degrees(temp_c, "c"),
            format_degrees(celsius_to_fahrenheit(temp_c), "f"),
        ]
        rows.append([label] + (list(reversed(readings)) if unit == "f" else readings))

    headline_c = cone.temp_c_at_60cph
    if unit == "f":
        headline = "{} (--unit f, 60 C/hr)".format(
            format_degrees(celsius_to_fahrenheit(headline_c), "f")
        )
    else:
        headline = "{} (--unit c, 60 C/hr)".format(format_degrees(headline_c, "c"))

    lines = [
        "Orton cone {} - final deformation temperature".format(cone.label),
        "",
    ]
    lines += render_table(columns, rows)
    lines += [
        "",
        "  Rates are 60 C/hr (108 F/hr) and 150 C/hr (270 F/hr).",
        "  > Headline: {}".format(headline),
    ]
    return lines


def cone_list_lines() -> List[str]:
    """Render the whole shipped cone table in Orton order."""
    columns = [
        Column("cone", 5, right_align=False),
        Column("60 C/hr C", 10),
        Column("60 C/hr F", 10),
        Column("150 C/hr C", 11),
        Column("150 C/hr F", 11),
    ]
    rows = [
        [
            cone.label,
            format_degrees(cone.temp_c_at_60cph, "c"),
            format_degrees(celsius_to_fahrenheit(cone.temp_c_at_60cph), "f"),
            format_degrees(cone.temp_c_at_150cph, "c"),
            format_degrees(celsius_to_fahrenheit(cone.temp_c_at_150cph), "f"),
        ]
        for cone in CONES
    ]
    lines = [
        "Orton standard cone equivalents 022-14 - final deformation temperature",
        "",
    ]
    lines += render_table(columns, rows)
    lines += [
        "",
        "  {} cones in the shipped table. Values are end-point deformation".format(
            len(CONES)
        ),
        "  temperatures at the stated heating rate.",
    ]
    return lines


def run_cone(args: argparse.Namespace) -> int:
    """Handle ``kilanvil cone``."""
    if args.list_cones:
        emit(cone_list_lines())
        return EXIT_OK
    if not args.label:
        raise UsageError(
            "no cone label given - name a cone such as 6 or 04, or use --list",
            usage=USAGE_CONE,
            hints=HINTS_CONE,
        )
    cone = CONE_BY_LABEL.get(args.label)
    if cone is None:
        raise UsageError(unknown_cone_message(args.label), hints=("kilanvil cone --list",))
    emit(cone_detail_lines(cone, args.unit))
    return EXIT_OK


# ---------------------------------------------------------------------------
# schedule (F2)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Segment:
    """One ramp/hold step of a firing schedule."""

    index: int
    rate_per_hour: float
    target_temp: float
    hold_minutes: float
    start_temp: float
    ramp_minutes: float

    @property
    def duration_minutes(self) -> float:
        """Ramp plus hold: the time this segment adds to the firing."""
        return self.ramp_minutes + self.hold_minutes

    @property
    def is_cooling(self) -> bool:
        return self.rate_per_hour < 0


def parse_segments(tokens: Sequence[str]) -> List[Tuple[float, float, float]]:
    """Parse repeated ``RATE:TARGET:HOLD`` tokens, naming the 1-based segment."""
    parsed: List[Tuple[float, float, float]] = []
    for index, token in enumerate(tokens, start=1):
        where = "segment {}".format(index)
        fields = token.split(":")
        if len(fields) != 3:
            raise UsageError(
                "{}: malformed segment {!r} - expected RATE:TARGET:HOLD "
                "(three colon-separated fields, for example 100:600:0)".format(
                    where, token
                )
            )
        rate = parse_float(fields[0], "rate", where)
        target = parse_float(fields[1], "target", where)
        hold = parse_float(fields[2], "hold", where)
        parsed.append((rate, target, hold))
    return parsed


def build_segments(
    rows: Sequence[Tuple[float, float, float]],
    start_temp: float,
    unit: str,
) -> Tuple[Segment, ...]:
    """Turn parsed segments into ramps, validating each 1-based segment."""
    segments: List[Segment] = []
    current = start_temp
    for index, (rate, target, hold) in enumerate(rows, start=1):
        where = "segment {}".format(index)
        if rate == 0:
            raise UsageError(
                "{}: rate 0 is not a ramp - use a positive rate to heat or a "
                "negative rate to cool".format(where)
            )
        if target <= 0:
            raise UsageError(
                "{}: target {} is not a temperature - it must be greater than "
                "zero".format(where, format_degrees(target, unit))
            )
        if hold < 0:
            raise UsageError(
                "{}: hold {} min is negative - hold minutes cannot be "
                "negative".format(where, format_trim(hold))
            )
        if rate > 0 and target < current:
            raise UsageError(
                "{}: target {} is below the previous end temperature {} on a "
                "heating ramp of {} - use a negative rate for a cooling "
                "ramp".format(
                    where,
                    format_degrees(target, unit),
                    format_degrees(current, unit),
                    format_rate(rate, unit),
                )
            )
        if rate < 0 and target > current:
            raise UsageError(
                "{}: target {} is above the previous end temperature {} on a "
                "cooling ramp of {} - use a positive rate for a heating "
                "ramp".format(
                    where,
                    format_degrees(target, unit),
                    format_degrees(current, unit),
                    format_rate(rate, unit),
                )
            )
        ramp_minutes = abs(target - current) / abs(rate) * 60.0
        segments.append(
            Segment(
                index=index,
                rate_per_hour=rate,
                target_temp=target,
                hold_minutes=hold,
                start_temp=current,
                ramp_minutes=ramp_minutes,
            )
        )
        current = target
    return tuple(segments)


def format_hours_minutes(total_minutes: float) -> str:
    """Render elapsed minutes as ``13 h 38 min`` (never wraps at 24 hours)."""
    rounded = round(total_minutes, 1)
    hours = int(rounded // 60)
    minutes = int(round(rounded - hours * 60))
    if minutes == 60:
        hours += 1
        minutes = 0
    return "{} h {} min".format(hours, minutes)


def schedule_lines(
    segments: Sequence[Segment],
    unit: str,
    start_temp: float,
) -> List[str]:
    """Render the numbered firing schedule with cumulative elapsed times."""
    columns = [
        Column("#", 2),
        Column("Direction", 9, right_align=False),
        Column("Rate", 10, right_align=False),
        Column("Target", 8, right_align=False),
        Column("Hold", 7, right_align=False),
        Column("Ramp min", 8),
        Column("Elapsed min", 11),
    ]

    rows: List[List[str]] = []
    elapsed = 0.0
    total_hold = 0.0
    for segment in segments:
        elapsed += segment.duration_minutes
        total_hold += segment.hold_minutes
        rows.append(
            [
                str(segment.index),
                "cooling" if segment.is_cooling else "heating",
                format_rate(segment.rate_per_hour, unit),
                format_degrees(segment.target_temp, unit),
                "{} min".format(format_trim(segment.hold_minutes)),
                "{:.1f}".format(segment.ramp_minutes),
                "{:.1f}".format(elapsed),
            ]
        )

    lines = [
        "Firing schedule - {} segment{}, {}, starting at {}".format(
            len(segments),
            "" if len(segments) == 1 else "s",
            unit_name(unit),
            format_degrees(start_temp, unit),
        ),
        "",
    ]
    lines += render_table(columns, rows)
    lines += [
        table_rule(columns),
        "",
        "  Total hold: {:.1f} min".format(total_hold),
        "  Total firing time: {:.1f} min ({})".format(
            elapsed, format_hours_minutes(elapsed)
        ),
    ]
    return lines


def run_schedule(args: argparse.Namespace) -> int:
    """Handle ``kilanvil schedule``."""
    if not args.segments:
        raise UsageError(
            "no --seg segment given - supply at least one RATE:TARGET:HOLD segment",
            usage=USAGE_SCHEDULE,
            hints=HINTS_SCHEDULE,
        )
    unit = args.unit
    if args.start is not None:
        start_temp = parse_float(args.start, "start temperature", "--start")
        if start_temp <= 0:
            raise UsageError(
                "--start: start temperature {} must be greater than zero".format(
                    format_degrees(start_temp, unit)
                )
            )
    else:
        start_temp = AMBIENT_START[unit]

    segments = build_segments(parse_segments(args.segments), start_temp, unit)
    emit(schedule_lines(segments, unit, start_temp))
    return EXIT_OK


# ---------------------------------------------------------------------------
# glaze (F3)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RecipeLine:
    """One ``MATERIAL:PARTS`` line of a glaze recipe."""

    index: int
    material: str
    parts: float


def parse_recipe_lines(tokens: Sequence[str]) -> List[RecipeLine]:
    """Parse repeated ``MATERIAL:PARTS`` tokens, naming the 1-based line."""
    lines: List[RecipeLine] = []
    for index, token in enumerate(tokens, start=1):
        where = "line {}".format(index)
        material, separator, parts_token = token.partition(":")
        if not separator or not material or not parts_token:
            raise UsageError(
                "{}: malformed recipe line {!r} - expected MATERIAL:PARTS "
                "(for example frit:50, material names cannot contain a "
                "colon)".format(where, token)
            )
        parts = parse_float(parts_token, "parts", where)
        if parts <= 0:
            raise UsageError(
                "{}: parts {} for {!r} must be greater than zero".format(
                    where, format_trim(parts), material
                )
            )
        lines.append(RecipeLine(index=index, material=material, parts=parts))
    return lines


def allocate_tenths(weights: Sequence[float], total_tenths: int) -> List[int]:
    """Split ``total_tenths`` over ``weights`` by largest remainder.

    Rounding the printed tenths this way keeps the printed column summing to the
    requested total exactly (the classic 3 x 33.3 % = 99.9 % slip).  Ties break
    on line order, so the result is deterministic.
    """
    total_weight = sum(weights)
    exact = [weight / total_weight * total_tenths for weight in weights]
    allocated = [int(math.floor(value)) for value in exact]
    remaining = total_tenths - sum(allocated)
    order = sorted(
        range(len(weights)),
        key=lambda i: (-(exact[i] - allocated[i]), i),
    )
    for i in order[:remaining]:
        allocated[i] += 1
    return allocated


def glaze_lines(
    recipe: Sequence[RecipeLine],
    batch_grams: float,
    water_percent: Optional[float],
) -> List[str]:
    """Render the scaled dry batch table, percentages and optional water."""
    parts = [line.parts for line in recipe]
    total_parts = sum(parts)
    gram_tenths = allocate_tenths(parts, int(round(batch_grams * 10)))
    percent_tenths = allocate_tenths(parts, 1000)

    columns = [
        Column("Material", 20, right_align=False),
        Column("Parts", 9),
        Column("Grams (g)", 10),
        Column("% of unity", 11),
    ]

    rows: List[List[str]] = []
    for position, line in enumerate(recipe):
        rows.append(
            [
                line.material,
                "{:.1f}".format(line.parts),
                "{:.1f}".format(gram_tenths[position] / 10.0),
                "{:.1f}".format(percent_tenths[position] / 10.0),
            ]
        )

    printed_total = sum(gram_tenths) / 10.0
    total_row = [
        "TOTAL",
        "{:.1f}".format(total_parts),
        "{:.1f}".format(printed_total),
        "{:.1f}".format(sum(percent_tenths) / 10.0),
    ]

    lines = [
        "Glaze batch - {} material{}, {:.1f} g dry".format(
            len(recipe), "" if len(recipe) == 1 else "s", batch_grams
        ),
        "",
    ]
    lines += render_table(columns, rows)
    lines.append(table_rule(columns))
    lines.append(table_row(columns, total_row))
    lines.append("")

    if water_percent is not None:
        water_grams = batch_grams * water_percent / 100.0
        lines.append(
            "  Water {:.1f} %: {:.1f} g".format(water_percent, water_grams)
        )
        lines.append(
            "  Wet batch weight: {:.1f} g".format(batch_grams + water_grams)
        )
    return lines


def run_glaze(args: argparse.Namespace) -> int:
    """Handle ``kilanvil glaze``."""
    if not args.lines:
        raise UsageError(
            "no --line recipe line given - supply at least one MATERIAL:PARTS line",
            usage=USAGE_GLAZE,
            hints=HINTS_GLAZE,
        )
    recipe = parse_recipe_lines(args.lines)

    if args.batch is None:
        raise UsageError(
            "no batch size given - --batch GRAMS (the dry batch weight) is required",
            usage=USAGE_GLAZE,
            hints=HINTS_GLAZE,
        )
    batch_grams = parse_float(args.batch, "size", "--batch")
    if batch_grams <= 0:
        raise UsageError(
            "--batch: batch size {} g must be greater than zero".format(
                format_trim(batch_grams)
            )
        )

    water_percent: Optional[float] = None
    if args.water is not None:
        water_percent = parse_float(args.water, "percentage", "--water")
        if water_percent < 0:
            raise UsageError(
                "--water: water percentage {} must not be negative".format(
                    format_trim(water_percent)
                )
            )

    emit(glaze_lines(recipe, batch_grams, water_percent))
    return EXIT_OK


# ---------------------------------------------------------------------------
# Argument parser and entry point (F4)
# ---------------------------------------------------------------------------

TOP_LEVEL_EPILOG = textwrap.dedent(
    """\
    examples:
      kilanvil cone 6
      kilanvil cone 04 --unit f
      kilanvil cone --list
      kilanvil schedule --seg 100:600:0 --seg 80:1100:15 --seg -150:900:0
      kilanvil glaze --line frit:50 --line silica:30 --line kaolin:20 --batch 1000 --water 50

    exit status:
      0  success
      2  usage or validation error (diagnostics on stderr, no results on stdout)
    """
)

CONE_EPILOG = textwrap.dedent(
    """\
    examples:
      kilanvil cone 6             cone 6 at the shipped heating rates
      kilanvil cone 04 --unit f   a cooler cone, Fahrenheit as the headline
      kilanvil cone --list        the whole shipped 022-14 table, in cone order

    Cone labels are matched exactly: 4 and 04 are different cones.
    """
)

SCHEDULE_EPILOG = textwrap.dedent(
    """\
    segment syntax:
      RATE:TARGET:HOLD   rate per hour (negative to cool), target temperature,
                         hold in minutes

    examples:
      kilanvil schedule --seg 100:600:0 --seg 80:1100:15 --seg -150:900:0
      kilanvil schedule --seg 150:1100:20 --seg -100:850:0 --unit f

    Each segment ramps from the previous segment's target, starting at 20 C
    (68 F) unless --start is given.
    """
)

GLAZE_EPILOG = textwrap.dedent(
    """\
    line syntax:
      MATERIAL:PARTS     a material name and its parts in the recipe

    examples:
      kilanvil glaze --line frit:50 --line silica:30 --line kaolin:20 --batch 1000
      kilanvil glaze --line frit:50 --line silica:30 --line kaolin:20 --batch 1000 --water 50

    Grams are printed to one decimal place and the printed total re-checks
    against --batch.
    """
)


#: Options whose value may legitimately start with a minus sign (a cooling
#: --seg such as -150:900:0 is the documented invocation).
VALUE_OPTIONS = ("--seg", "--line", "--batch", "--water", "--start", "--unit")

#: Tokens that are never a value, so they must not be folded into one.
RESERVED_TOKENS = (
    "-h",
    "--help",
    "--version",
    "--seg",
    "--line",
    "--batch",
    "--water",
    "--start",
    "--unit",
)


def preprocess_argv(argv: Sequence[str]) -> List[str]:
    """Allow an option value that begins with ``-``.

    argparse rejects ``--seg -150:900:0`` because the value looks like another
    option; rewriting it to the ``--seg=-150:900:0`` form keeps the documented
    cooling-ramp invocation working.
    """
    rewritten: List[str] = []
    index = 0
    while index < len(argv):
        token = argv[index]
        if token in VALUE_OPTIONS and index + 1 < len(argv):
            value = argv[index + 1]
            if value.startswith("-") and value not in RESERVED_TOKENS:
                rewritten.append("{}={}".format(token, value))
                index += 2
                continue
        rewritten.append(token)
        index += 1
    return rewritten


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser with the three subcommands."""
    parser = argparse.ArgumentParser(
        prog=PROGRAM,
        description=(
            "Kiln firing schedules, Orton cone temperatures and glaze batch "
            "maths for the workshop."
        ),
        epilog=TOP_LEVEL_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--version", action="version", version="{} {}".format(PROGRAM, VERSION)
    )

    subparsers = parser.add_subparsers(
        dest="command", metavar="COMMAND", required=True, title="commands"
    )

    cone_parser = subparsers.add_parser(
        "cone",
        help="look up an Orton cone 022-14 deformation temperature",
        description=(
            "Look up the final deformation temperature of an Orton standard "
            "pyrometric cone, in Celsius and Fahrenheit."
        ),
        epilog=CONE_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    cone_parser.add_argument(
        "label",
        nargs="?",
        metavar="LABEL",
        help="cone label, for example 6, 04, 022 or 10",
    )
    cone_parser.add_argument(
        "--unit",
        choices=("c", "f"),
        type=str.lower,
        default="c",
        help="headline temperature unit (default: c)",
    )
    cone_parser.add_argument(
        "--list",
        action="store_true",
        dest="list_cones",
        help="print the whole shipped cone table in cone order",
    )
    cone_parser.set_defaults(handler=run_cone)

    schedule_parser = subparsers.add_parser(
        "schedule",
        help="build a numbered firing schedule with cumulative times",
        description=(
            "Turn repeated --seg RATE:TARGET:HOLD ramps into a numbered firing "
            "schedule with cumulative elapsed times."
        ),
        epilog=SCHEDULE_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    schedule_parser.add_argument(
        "--seg",
        action="append",
        dest="segments",
        metavar="RATE:TARGET:HOLD",
        default=[],
        help="one ramp segment: rate per hour, target temperature, hold minutes "
        "(repeatable; a negative rate cools)",
    )
    schedule_parser.add_argument(
        "--unit",
        choices=("c", "f"),
        type=str.lower,
        default="c",
        help="working temperature unit for rates and targets (default: c)",
    )
    schedule_parser.add_argument(
        "--start",
        metavar="TEMP",
        default=None,
        help="starting temperature of the first ramp (default: 20 C / 68 F)",
    )
    schedule_parser.set_defaults(handler=run_schedule)

    glaze_parser = subparsers.add_parser(
        "glaze",
        help="scale a glaze recipe to a dry batch weight",
        description=(
            "Scale repeated --line MATERIAL:PARTS to a --batch GRAMS dry weight "
            "and print shop-floor gram amounts."
        ),
        epilog=GLAZE_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    glaze_parser.add_argument(
        "--line",
        action="append",
        dest="lines",
        metavar="MATERIAL:PARTS",
        default=[],
        help="one recipe line: material name and its parts (repeatable)",
    )
    glaze_parser.add_argument(
        "--batch",
        metavar="GRAMS",
        default=None,
        help="dry batch weight in grams (required)",
    )
    glaze_parser.add_argument(
        "--water",
        metavar="PCT",
        default=None,
        help="water added as a percentage of the dry batch weight",
    )
    glaze_parser.set_defaults(handler=run_glaze)

    return parser


def wrap_diagnostic(message: str) -> str:
    """Wrap a diagnostic to the terminal width, prefixing the first line."""
    wrapped = textwrap.wrap(message, width=ERROR_WIDTH - len(PROGRAM) - 2)
    if not wrapped:
        return "{}: ".format(PROGRAM)
    lines = ["{}: {}".format(PROGRAM, wrapped[0])]
    lines.extend(" " * (len(PROGRAM) + 2) + line for line in wrapped[1:])
    return "\n".join(lines)


def report_error(error: UsageError) -> None:
    """Write a usage or validation error to stderr (never to stdout)."""
    print(wrap_diagnostic(error.message), file=sys.stderr)
    if error.usage:
        print("usage: {}".format(error.usage), file=sys.stderr)
    for position, hint in enumerate(error.hints):
        prefix = "try:   " if position == 0 else "       "
        print(prefix + hint, file=sys.stderr)


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Run one kilanvil command and return its process exit status."""
    parser = build_parser()
    raw = list(sys.argv[1:] if argv is None else argv)
    try:
        args = parser.parse_args(preprocess_argv(raw))
    except SystemExit as exit_request:
        # argparse already wrote help (stdout, 0) or usage (stderr, 2).
        code = exit_request.code
        if code is None:
            return EXIT_OK
        return code if isinstance(code, int) else EXIT_ERROR

    try:
        return int(args.handler(args))
    except UsageError as error:
        report_error(error)
        return EXIT_ERROR


if __name__ == "__main__":
    try:
        sys.exit(main())
    except BrokenPipeError:
        # A downstream reader (for example `kilanvil cone --list | head`) closed
        # the pipe early; that is a normal shell outcome, not a failure.
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        sys.exit(EXIT_OK)
