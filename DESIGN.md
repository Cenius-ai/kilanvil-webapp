# Kilanvil design direction (source of truth)

Kilanvil is a terminal product, so its design system is committed here as
tokens and output rules rather than as a stylesheet. Every screen the tool
prints consumes the rules below; there is no second palette and no second type
ramp anywhere in the project.

## Committed tokens

| Token | Value | Used for |
| --- | --- | --- |
| `--accent` | `oklch(0.58 0.12 268)` | the single accent: the primary reading of a screen |
| `--accent-hex` | `#5c76c1` | the same accent for any non-CSS context (chart libraries, `<canvas>`, editor themes, a future docs page) - never pass the `oklch()` string to a charting API |
| `--surface` | terminal dark | the only honest surface for a CLI; no light theme, no theme picker |
| `--ink` | terminal default foreground | body text and table cells |
| `--ink-muted` | terminal dim (via wording, not colour) | notes under a table |
| `--rule` | `-` (ASCII) | table separators, header rules, section rules |
| `--type-family` | system monospace | every character the tool prints, including prose |
| `--density` | compact | one blank line between blocks, no box padding |
| `--column-gap` | 2 spaces | the only gutter in any table |
| `--transition` | none | a CLI renders once; there is nothing to animate |

Neutral ramp: the accent is the only chromatic value in the product. Every other
distinction is carried by position, capitalisation, a `-` rule, or an explicit
word (`heating` / `cooling`, `TOTAL`, `> Headline`), never by hue alone - so the
output stays readable with 16-colour, monochrome and non-UTF-8 terminals.

## The accent, applied honestly

The plan's non-goals exclude colourised output (`--json` and colour are both out
of scope) and the shipped text must be pure ASCII so redirected files behave
identically everywhere. The accent is therefore applied **textually**, as the one
highlight that marks a screen's primary reading:

```
  > Headline: 1222 C (--unit c, 60 C/hr)
```

One `>` marker, one headline per screen. `#5c76c1` / `oklch(0.58 0.12 268)`
remains the project's committed accent for any future renderer (a docs site, an
editor or syntax theme, a kiln-controller export viewer), so the direction is
recorded in the source of truth instead of being re-invented later.

## Layout skeleton

Aligned terminal columns, help-first output - not a top-nav plus card grid:

```
<one line: what this screen is, and its unit>

  <header row, one column per field>
  <rule of dashes matching each column width>
  <body row per record, right-aligned numbers, left-aligned labels>
  <rule>
  <total row>            (glaze only)

  <notes: units, rates, caveats>
  > Headline: ...        (cone only)
```

Shape language: monospace, no chrome, `-` box-drawing-separator rules in ASCII.
The same rule character, the same two-space gutter and the same right-aligned
numerics appear on every surface (cone detail, cone list, schedule, glaze), so
the three calculators read as one product.

## Type and density

- System monospace throughout; the tool never assumes a specific installed font.
- One type ramp: `Title` (sentence case, no trailing punctuation), `Body`
  (columns), `Note` (two-space indent), `Error` (`kilanvil:` prefix, wrapped to
  78 columns, stderr only).
- Compact: no blank line inside a table, exactly one blank line between blocks.

## Verification

- Every table renders with aligned columns and only ASCII bytes
  (`test_kilanvil.CliContractTests.test_results_are_ascii_only`).
- Numbers are right-aligned and carry a fixed decimal count so a column lines up
  vertically (`test_grams_always_carry_one_decimal_place`).
- Errors never touch stdout and never colour-code their meaning
  (`test_errors_go_to_stderr_only`).
