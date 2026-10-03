#!/usr/bin/env python3
"""Kilanvil test suite (standard library unittest only).

Run it from the project directory with::

    python3 -m unittest test_kilanvil

The suite drives the tool through its real entry point (``kilanvil.main``) and
through the documented ``python3 kilanvil.py ...`` invocation, so it covers the
stdout/stderr split and the exit-status contract as well as the arithmetic.
"""

from __future__ import annotations

import io
import os
import subprocess
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import kilanvil

REPO_ROOT = Path(__file__).resolve().parent


def run_cli(*argv: str):
    """Run one command in-process; return (exit_code, stdout, stderr)."""
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = kilanvil.main(list(argv))
    return code, out.getvalue(), err.getvalue()


def run_subprocess(*argv: str):
    """Run one command the way a user does; return (exit_code, stdout, stderr)."""
    completed = subprocess.run(
        [sys.executable, "kilanvil.py", *argv],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    return completed.returncode, completed.stdout, completed.stderr


def table_rows(stdout: str, header_first_field: str):
    """Return the body rows of the table whose header starts with a field.

    Stops at the blank line that closes the table, so titles and trailing notes
    never leak into the parsed rows.
    """
    lines = stdout.splitlines()
    start = next(
        index
        for index, line in enumerate(lines)
        if line.strip().startswith(header_first_field)
    )
    rows = []
    for line in lines[start + 1:]:
        stripped = line.strip()
        if not stripped or not line.startswith("  "):
            break
        if set(stripped) <= set("- "):
            continue
        fields = stripped.split()
        if fields[0] == "TOTAL":
            continue
        rows.append(fields)
    return rows


def glaze_rows(stdout: str):
    """Body rows of the glaze batch table (material, parts, grams, percent)."""
    return table_rows(stdout, "Material")


def schedule_rows(stdout: str):
    """Body rows of the firing schedule table."""
    return table_rows(stdout, "#")


class ConeLookupTests(unittest.TestCase):
    """F1 happy path: exact labels, units and the full table."""

    def test_cone_6_prints_celsius_and_fahrenheit(self):
        code, out, err = run_cli("cone", "6")
        self.assertEqual(code, kilanvil.EXIT_OK)
        self.assertEqual(err, "")
        self.assertIn("1222", out)
        self.assertIn("2232", out)

    def test_leading_zero_label_is_a_different_cone(self):
        _, out_04, _ = run_cli("cone", "04")
        _, out_4, _ = run_cli("cone", "4")
        self.assertIn("1060", out_04)
        self.assertIn("1186", out_4)
        self.assertNotEqual(out_04, out_4)

    def test_unit_f_makes_fahrenheit_the_headline(self):
        _, out_c, _ = run_cli("cone", "6")
        _, out_f, _ = run_cli("cone", "6", "--unit", "f")
        self.assertIn("> Headline: 1222 C", out_c)
        self.assertIn("> Headline: 2232 F", out_f)

    def test_unit_choice_is_case_insensitive(self):
        code, out, _ = run_cli("cone", "6", "--unit", "F")
        self.assertEqual(code, kilanvil.EXIT_OK)
        self.assertIn("> Headline: 2232 F", out)

    def test_table_ends_resolve(self):
        for label, celsius in (("022", "586"), ("14", "1365")):
            code, out, err = run_cli("cone", label)
            self.assertEqual(code, kilanvil.EXIT_OK, err)
            self.assertIn(celsius, out)

    def test_list_prints_every_cone_in_order(self):
        code, out, err = run_cli("cone", "--list")
        self.assertEqual(code, kilanvil.EXIT_OK)
        self.assertEqual(err, "")
        labels = [row[0] for row in table_rows(out, "cone")]
        self.assertEqual(labels[0], "022")
        self.assertEqual(labels[-1], "14")
        self.assertEqual(labels, list(kilanvil.CONE_LABEL_ORDER))
        self.assertIn("36 cones", out)

    def test_cone_table_is_monotonic_in_cone_order(self):
        celsius = [cone.temp_c_at_60cph for cone in kilanvil.CONES]
        self.assertEqual(celsius, sorted(celsius))
        self.assertEqual(len(set(celsius)), len(celsius), "duplicate temperatures")

    def test_fahrenheit_conversion_matches_formula(self):
        cone = kilanvil.CONE_BY_LABEL["6"]
        expected = round(kilanvil.celsius_to_fahrenheit(cone.temp_c_at_60cph))
        self.assertEqual(expected, 2232)


class ConeErrorTests(unittest.TestCase):
    """F1 error path: unknown labels and missing input."""

    def test_unknown_cone_reports_nearest_and_no_stdout(self):
        code, out, err = run_cli("cone", "99")
        self.assertNotEqual(code, kilanvil.EXIT_OK)
        self.assertEqual(out, "")
        self.assertIn("99", err)
        self.assertIn("14", err)
        self.assertIn("13", err)

    def test_unknown_cone_out_of_range_low(self):
        code, _, err = run_cli("cone", "999")
        self.assertNotEqual(code, kilanvil.EXIT_OK)
        self.assertIn("999", err)
        self.assertIn("nearest", err)

    def test_non_numeric_cone_label(self):
        code, out, err = run_cli("cone", "pyrometric")
        self.assertNotEqual(code, kilanvil.EXIT_OK)
        self.assertEqual(out, "")
        self.assertIn("pyrometric", err)

    def test_missing_label_prints_usage_to_stderr(self):
        code, out, err = run_cli("cone")
        self.assertNotEqual(code, kilanvil.EXIT_OK)
        self.assertEqual(out, "")
        self.assertIn("usage:", err)
        self.assertIn("kilanvil cone 6", err)
        self.assertIn("kilanvil cone 04", err)


class ScheduleTests(unittest.TestCase):
    """F2 happy path: ramps, holds, cumulative times, cooling and units."""

    SEGMENTS = ("--seg", "100:600:0", "--seg", "80:1100:15", "--seg", "-150:900:0")

    def test_three_segment_schedule_has_cumulative_times(self):
        code, out, err = run_cli("schedule", *self.SEGMENTS)
        self.assertEqual(code, kilanvil.EXIT_OK, err)
        self.assertEqual(err, "")
        self.assertIn("348.0", out)  # 580 C at 100 C/hr from 20 C
        self.assertIn("738.0", out)  # + 375 ramp + 15 hold
        self.assertIn("818.0", out)  # + 80 min cooling
        self.assertIn("Total firing time: 818.0 min (13 h 38 min)", out)

    def test_one_numbered_row_per_segment(self):
        _, out, _ = run_cli("schedule", *self.SEGMENTS)
        rows = schedule_rows(out)
        self.assertEqual(len(rows), 3)
        self.assertEqual([row[0] for row in rows], ["1", "2", "3"])

    def test_cooling_segment_is_labelled_and_time_still_accumulates(self):
        _, out, _ = run_cli("schedule", *self.SEGMENTS)
        cooling = [line for line in out.splitlines() if "cooling" in line]
        self.assertEqual(len(cooling), 1)
        self.assertIn("-150 C/hr", cooling[0])
        self.assertIn("818.0", cooling[0])

    def test_last_row_elapsed_equals_printed_total(self):
        _, out, _ = run_cli("schedule", *self.SEGMENTS)
        last_row = [line for line in out.splitlines() if line.strip().startswith("3")][0]
        total_line = [line for line in out.splitlines() if "Total firing time" in line][0]
        self.assertIn(last_row.split()[-1], total_line)

    def test_hold_minutes_are_added_to_elapsed(self):
        _, out, _ = run_cli("schedule", "--seg", "60:60:0", "--seg", "60:120:30")
        rows = [line.split() for line in out.splitlines() if line.strip()[:1].isdigit()]
        self.assertEqual(rows[0][-1], "40.0")  # 40 min ramp, 0 hold
        self.assertEqual(rows[1][-1], "130.0")  # + 60 min ramp + 30 min hold

    def test_start_temperature_option(self):
        _, out, _ = run_cli("schedule", "--start", "600", "--seg", "100:800:0")
        self.assertIn("starting at 600 C", out)
        self.assertIn("120.0", out)

    def test_unit_f_converts_rate_target_and_header(self):
        code, out, err = run_cli("schedule", "--unit", "f", "--seg", "300:2000:10")
        self.assertEqual(code, kilanvil.EXIT_OK, err)
        self.assertIn("Fahrenheit", out)
        self.assertIn("+300 F/hr", out)
        self.assertIn("2000 F", out)
        self.assertIn("starting at 68 F", out)
        self.assertNotIn(" C/hr", out)
        self.assertNotIn(" C ", out)

    def test_missing_segments_prints_usage_to_stderr(self):
        code, out, err = run_cli("schedule")
        self.assertNotEqual(code, kilanvil.EXIT_OK)
        self.assertEqual(out, "")
        self.assertIn("usage:", err)
        self.assertIn("100:600:0", err)


class ScheduleValidationTests(unittest.TestCase):
    """F2 validation: every message names the offending segment number."""

    def assert_rejected(self, *argv: str, needle: str = ""):
        code, out, err = run_cli("schedule", *argv)
        self.assertNotEqual(code, kilanvil.EXIT_OK)
        self.assertEqual(out, "", "a failing schedule must print no table")
        self.assertIn(needle, err)
        return err

    def test_wrong_field_count_names_segment(self):
        self.assert_rejected("--seg", "100:600", needle="segment 1")

    def test_second_segment_bad_rate_names_segment_2(self):
        self.assert_rejected(
            "--seg", "100:600:0", "--seg", "abc:600:0", needle="segment 2"
        )

    def test_bad_target_names_segment_1(self):
        self.assert_rejected("--seg", "100:abc:0", needle="segment 1")

    def test_bad_hold_names_segment_1(self):
        self.assert_rejected("--seg", "100:600:xyz", needle="segment 1")

    def test_descending_target_on_heating_ramp_is_rejected(self):
        err = self.assert_rejected(
            "--seg", "100:600:0", "--seg", "80:500:0", needle="segment 2"
        )
        self.assertIn("500", err)

    def test_raising_target_on_cooling_ramp_is_rejected(self):
        self.assert_rejected(
            "--seg", "100:600:0", "--seg", "-80:900:0", needle="segment 2"
        )

    def test_zero_rate_is_rejected(self):
        self.assert_rejected("--seg", "0:600:0", needle="segment 1")

    def test_negative_hold_is_rejected(self):
        self.assert_rejected("--seg", "100:600:-5", needle="segment 1")

    def test_non_positive_target_is_rejected(self):
        self.assert_rejected("--seg", "100:0:0", needle="segment 1")

    def test_bad_start_temperature_is_rejected(self):
        code, out, err = run_cli("schedule", "--start", "warm", "--seg", "100:600:0")
        self.assertNotEqual(code, kilanvil.EXIT_OK)
        self.assertEqual(out, "")
        self.assertIn("--start", err)


class GlazeTests(unittest.TestCase):
    """F3 happy path: scaling, percentages, water and the total row."""

    RECIPE = ("--line", "frit:50", "--line", "silica:30", "--line", "kaolin:20")

    def test_batch_scaling_to_one_kg(self):
        code, out, err = run_cli("glaze", *self.RECIPE, "--batch", "1000")
        self.assertEqual(code, kilanvil.EXIT_OK, err)
        self.assertEqual(err, "")
        self.assertIn("500.0", out)
        self.assertIn("300.0", out)
        self.assertIn("200.0", out)
        total = [line for line in out.splitlines() if line.strip().startswith("TOTAL")][0]
        self.assertIn("1000.0", total)

    def test_half_batch_halves_every_gram_figure(self):
        _, full, _ = run_cli("glaze", *self.RECIPE, "--batch", "1000")
        _, half, _ = run_cli("glaze", *self.RECIPE, "--batch", "500")
        full_grams = [row[2] for row in glaze_rows(full)]
        half_grams = [row[2] for row in glaze_rows(half)]
        self.assertEqual(half_grams, ["250.0", "150.0", "100.0"])
        for whole, part in zip(full_grams, half_grams):
            self.assertAlmostEqual(float(whole) / 2, float(part), places=6)

    def test_percent_column_sums_to_one_hundred(self):
        _, out, _ = run_cli("glaze", *self.RECIPE, "--batch", "1000")
        percents = [float(row[3]) for row in glaze_rows(out)]
        self.assertEqual(percents, [50.0, 30.0, 20.0])
        self.assertAlmostEqual(sum(percents), 100.0, places=6)

    def test_percent_column_sums_to_one_hundred_for_thirds(self):
        _, out, _ = run_cli(
            "glaze", "--line", "frit:1", "--line", "silica:1", "--line", "kaolin:1",
            "--batch", "1000",
        )
        percents = [float(row[3]) for row in glaze_rows(out)]
        self.assertAlmostEqual(sum(percents), 100.0, places=6)
        grams = [float(row[2]) for row in glaze_rows(out)]
        self.assertAlmostEqual(sum(grams), 1000.0, places=6)

    def test_water_adds_a_water_line_and_wet_weight(self):
        _, out, _ = run_cli("glaze", *self.RECIPE, "--batch", "1000", "--water", "50")
        self.assertIn("Water 50.0 %: 500.0 g", out)
        self.assertIn("Wet batch weight: 1500.0 g", out)

    def test_grams_always_carry_one_decimal_place(self):
        _, out, _ = run_cli("glaze", *self.RECIPE, "--batch", "1234")
        for row in glaze_rows(out):
            self.assertRegex(row[2], r"^\d+\.\d$")
            self.assertRegex(row[3], r"^\d+\.\d$")

    def test_duplicate_material_names_print_separately(self):
        _, out, _ = run_cli("glaze", "--line", "frit:50", "--line", "frit:20", "--batch", "1000")
        rows = [line for line in out.splitlines() if line.strip().startswith("frit")]
        self.assertEqual(len(rows), 2)
        total = [line for line in out.splitlines() if line.strip().startswith("TOTAL")][0]
        self.assertIn("1000.0", total)

    def test_recipe_with_a_long_material_name_still_totals(self):
        _, out, _ = run_cli(
            "glaze", "--line", "nepheline syenite:45", "--line", "whiting:55", "--batch", "500"
        )
        self.assertIn("500.0", out)


class GlazeValidationTests(unittest.TestCase):
    """F3 validation: usage-on-missing-input and named offending values."""

    def assert_rejected(self, *argv: str, needle: str = ""):
        code, out, err = run_cli("glaze", *argv)
        self.assertNotEqual(code, kilanvil.EXIT_OK)
        self.assertEqual(out, "", "a failing batch must print no table")
        self.assertIn(needle, err)

    def test_missing_lines_prints_usage_to_stderr(self):
        code, out, err = run_cli("glaze", "--batch", "1000")
        self.assertNotEqual(code, kilanvil.EXIT_OK)
        self.assertEqual(out, "")
        self.assertIn("usage:", err)
        self.assertIn("frit:50", err)

    def test_missing_batch_is_reported(self):
        self.assert_rejected(
            "--line", "frit:50", "--line", "silica:30", needle="batch size"
        )

    def test_malformed_batch_names_the_value(self):
        self.assert_rejected("--line", "frit:50", "--batch", "abc", needle="abc")

    def test_non_positive_batch_is_rejected(self):
        self.assert_rejected("--line", "frit:50", "--batch", "0", needle="greater than zero")

    def test_malformed_line_without_colon_names_line_1(self):
        self.assert_rejected("--line", "frit", "--batch", "1000", needle="line 1")

    def test_non_numeric_parts_names_line_1(self):
        self.assert_rejected("--line", "frit:abc", "--batch", "1000", needle="line 1")

    def test_second_bad_line_names_line_2(self):
        self.assert_rejected(
            "--line", "frit:50", "--line", "silica:x", "--batch", "1000", needle="line 2"
        )

    def test_zero_parts_is_rejected(self):
        self.assert_rejected("--line", "frit:0", "--batch", "1000", needle="line 1")

    def test_negative_water_is_rejected(self):
        self.assert_rejected(
            "--line", "frit:50", "--batch", "1000", "--water", "-10", needle="--water"
        )


class EdgeCaseTests(unittest.TestCase):
    """T10 hardening: long firings, long schedules, duplicate and boundary data."""

    def test_firing_longer_than_24_hours_does_not_wrap(self):
        code, out, err = run_cli("schedule", "--seg", "60:1000:600", "--seg", "60:1300:900")
        self.assertEqual(code, kilanvil.EXIT_OK, err)
        self.assertIn("46 h 20 min", out)
        self.assertIn("2780.0 min", out)

    def test_forty_segment_schedule_prints_every_row(self):
        segments = []
        for step in range(1, 41):
            segments += ["--seg", "100:{}:5".format(100 + step * 10)]
        code, out, err = run_cli("schedule", *segments)
        self.assertEqual(code, kilanvil.EXIT_OK, err)
        rows = schedule_rows(out)
        self.assertEqual(len(rows), 40)
        total = [line for line in out.splitlines() if "Total firing time" in line][0]
        self.assertIn(rows[-1][-1], total)

    def test_sub_tenth_batch_rounds_consistently_in_header_and_total(self):
        code, out, err = run_cli("glaze", "--line", "frit:50", "--line", "kaolin:50", "--batch", "1000.06")
        self.assertEqual(code, kilanvil.EXIT_OK, err)
        self.assertIn("1000.1 g dry", out)
        total = [line for line in out.splitlines() if line.strip().startswith("TOTAL")][0]
        self.assertIn("1000.1", total)

    def test_large_batch_scales_linearly(self):
        _, small, _ = run_cli("glaze", "--line", "frit:3", "--line", "silica:7", "--batch", "10")
        _, large, _ = run_cli("glaze", "--line", "frit:3", "--line", "silica:7", "--batch", "1000")
        small_grams = [float(row[2]) for row in glaze_rows(small)]
        large_grams = [float(row[2]) for row in glaze_rows(large)]
        self.assertAlmostEqual(small_grams[0] * 100, large_grams[0], places=3)


class CliContractTests(unittest.TestCase):
    """F4 contract: help, exit status, stream separation, no on-disk state."""

    def test_top_level_help_lists_all_subcommands(self):
        code, out, err = run_cli("--help")
        self.assertEqual(code, kilanvil.EXIT_OK)
        self.assertEqual(err, "")
        for command in ("cone", "schedule", "glaze"):
            self.assertIn(command, out)

    def test_each_subcommand_help_exits_zero(self):
        for command in ("cone", "schedule", "glaze"):
            code, out, err = run_cli(command, "--help")
            self.assertEqual(code, kilanvil.EXIT_OK, command)
            self.assertEqual(err, "")
            self.assertIn("usage:", out)
            self.assertIn("kilanvil {}".format(command), out)

    def test_subcommand_help_documents_the_flags(self):
        _, cone_help, _ = run_cli("cone", "--help")
        self.assertIn("--unit", cone_help)
        self.assertIn("--list", cone_help)
        _, schedule_help, _ = run_cli("schedule", "--help")
        self.assertIn("--seg", schedule_help)
        self.assertIn("--start", schedule_help)
        _, glaze_help, _ = run_cli("glaze", "--help")
        self.assertIn("--line", glaze_help)
        self.assertIn("--batch", glaze_help)
        self.assertIn("--water", glaze_help)

    def test_no_subcommand_is_a_usage_error(self):
        code, out, err = run_cli()
        self.assertNotEqual(code, kilanvil.EXIT_OK)
        self.assertEqual(out, "")
        self.assertIn("usage:", err)

    def test_unknown_subcommand_names_the_token(self):
        code, out, err = run_cli("frobnicate")
        self.assertNotEqual(code, kilanvil.EXIT_OK)
        self.assertEqual(out, "")
        self.assertIn("frobnicate", err)
        self.assertIn("cone", err)

    def test_version_flag(self):
        code, out, err = run_cli("--version")
        self.assertEqual(code, kilanvil.EXIT_OK)
        self.assertIn(kilanvil.VERSION, out)

    def test_results_are_ascii_only(self):
        for argv in (
            ("cone", "6"),
            ("cone", "--list"),
            ("schedule", "--seg", "100:600:0", "--seg", "-150:500:0"),
            ("glaze", "--line", "frit:50", "--line", "kaolin:50", "--batch", "1000", "--water", "45"),
        ):
            code, out, err = run_cli(*argv)
            self.assertEqual(code, kilanvil.EXIT_OK, argv)
            out.encode("ascii")
            err.encode("ascii")

    def test_errors_go_to_stderr_only(self):
        for argv in (("cone", "99"), ("schedule", "--seg", "junk"), ("glaze", "--batch", "10")):
            code, out, err = run_cli(*argv)
            self.assertNotEqual(code, kilanvil.EXIT_OK, argv)
            self.assertEqual(out, "", argv)
            self.assertTrue(err.startswith("kilanvil:"), argv)

    def test_repeated_runs_are_byte_identical(self):
        argv = ("schedule", "--seg", "100:600:0", "--seg", "80:1100:15", "--seg", "-150:900:0")
        first = run_cli(*argv)
        second = run_cli(*argv)
        self.assertEqual(first, second)

    def test_tool_writes_nothing_to_the_working_directory(self):
        # The interpreter's own __pycache__ is not tool state; everything else is.
        visible = lambda: {p for p in os.listdir(REPO_ROOT) if p != "__pycache__"}
        before = visible()
        run_cli("cone", "6")
        run_cli("schedule", "--seg", "100:600:0")
        run_cli("glaze", "--line", "frit:50", "--batch", "1000")
        run_cli("cone", "nope")
        self.assertEqual(visible(), before)


class DocumentedInvocationTests(unittest.TestCase):
    """The README's `python3 kilanvil.py ...` form works end to end."""

    def test_success_exits_zero_and_prints_on_stdout(self):
        code, out, err = run_subprocess("cone", "6")
        self.assertEqual(code, 0)
        self.assertEqual(err, "")
        self.assertIn("1222", out)

    def test_cooling_segment_via_argv_survives_the_leading_minus(self):
        code, out, err = run_subprocess(
            "schedule", "--seg", "100:600:0", "--seg", "-150:400:0"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("cooling", out)

    def test_validation_error_exits_two_with_empty_stdout(self):
        code, out, err = run_subprocess("glaze", "--line", "frit:50", "--batch", "abc")
        self.assertEqual(code, kilanvil.EXIT_ERROR)
        self.assertEqual(out, "")
        self.assertIn("abc", err)

    def test_stdout_can_be_redirected_as_the_save_path(self):
        code, out, _ = run_subprocess("glaze", "--line", "frit:50", "--line", "kaolin:50", "--batch", "1000")
        self.assertEqual(code, 0)
        self.assertTrue(out.endswith("\n"))
        self.assertIn("TOTAL", out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
