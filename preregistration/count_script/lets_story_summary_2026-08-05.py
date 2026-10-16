"""
Let's Story - an integrity check on the export, for the InTRACt study (Univ. of Oxford)

WHAT IT IS
A sanity check on the exported reading-sessions file, agnostic to the study's
research questions. It asks only whether the export is complete, well formed and
usable: how many rows and accounts it holds, which languages and age bands are
present, how much of each field is missing, whether identifiers and dates parse, and
whether the fields hold the kind of values the data dictionary describes.

It answers none of the study's questions and is not a step in the analysis. Nothing
it reports relates reading time to any property of a text, a child or a session:
reading time enters only as wide groups by size and counts of different values,
for the export as a whole.

WHAT IT DOES
Reads the export, or several files, and writes two small files. Please send both.
  lets_story_summary_data_for_oxford.csv  every figure as data: the counts, and a
                                          record of each input file
  lets_story_manifest_for_oxford.html     the readable page, with the main counts
                                          drawn as charts

Nothing else leaves your machine. The page is there so both teams can check the
export quickly rather than reading down a table of numbers.

HOW IT IS PUT TOGETHER
The work runs in four stages, and the code is laid out in that order:

  1. Find and open the input files       resolve_inputs, build_sources, sniff
  2. Read each row and count it          process_source, tally
  3. Write the summary data file         emit, which fills `rows`
  4. Draw the manifest from those rows   build_manifest, through the Summary class

Stage 4 reads nothing but the output of stage 3. That is deliberate. The manifest
cannot show a figure the summary data file lacks, so the two deliverables cannot
contradict one another, and the summary data file on its own is enough to redraw the
page:

    python lets_story_summary.py --manifest-from lets_story_summary_data_for_oxford.csv

which produces a page identical to the one written beside it.

Every row of the summary data file carries the same five columns: section, group_1,
group_2, metric, value. One row is one labelled number. Sections whose name starts
with the age bands, such as "Age 7-8 and Age 9+ only: overview", repeat the section
of the same name for that subset alone.

WHERE THE LINE IS DRAWN
The study's outcome is reading time, and its protocol is registered before anyone at
Oxford sees it. So time_spent_reading is kept out of KEEP and handled separately. It
is checked for whether it is there, whether it is a number, and roughly how big it is,
in the wide groups listed in TIME_BANDS. It is also counted for how many different
values the column holds and how many sessions share one and the same value, which is
how a timeout cap shows itself, and for nothing else. No reading time is ever stored,
printed, charted, or broken down by language, age, text, child or date. Those checks
cannot tell one child, text or language from another, so they bear on no hypothesis.
They exist so that an unusable field is found now rather than after the protocol is
reviewed. The story rating is likewise reported only as how often it is empty, never
as a value.

HOW TO RUN
    python lets_story_summary.py <path-to-export.csv>

If the export comes as more than one file, pass them all in one run, in any mix of
these forms, so that accounts appearing in more than one file are counted once:
    python lets_story_summary.py part1.csv part2.csv
    python lets_story_summary.py C:/exports/            (a folder: every CSV inside)
    python lets_story_summary.py "C:/exports/*.csv"     (a pattern)
Compressed files (.csv.gz, or a .zip holding CSVs) are read as they are.

Standard library only, so there is nothing to install beyond Python 3.8 or later, and
the charts are plain SVG inside one HTML file that opens in any browser offline.
No preprocessing needed: files can be exactly as exported, comma or semicolon
separated, with any column order and any extra columns present.
"""
import codecs
import csv
import glob
import gzip
import hashlib
import io
import math
import os
import re
import sys
import zipfile
from collections import Counter
from datetime import date, datetime, timezone
from html import escape

SCRIPT_VERSION = "2026-08-05"

# The two outputs, named for their roles. The summary data file holds every figure
# as data; the manifest is the readable page drawn from it. Both go to Oxford.
OUT_CSV = "lets_story_summary_data_for_oxford.csv"
OUT_HTML = "lets_story_manifest_for_oxford.html"

KEEP = ["user_id", "read_language", "user_age_group", "user_reading_level",
        "story_id", "story_title", "is_customized", "is_speech_on",
        "story_rating", "finished_reading_at", "game_version", "user_country",
        "total_page_available", "max_page_reached", "story_location", "story_hero",
        "story_sidekick", "story_plot", "story_theme"]

# Note what is absent from KEEP: time_spent_reading, handled on its own terms below.
# Every value that reaches a count, a chart or the duplicate-row digest comes from
# the nineteen columns above.
ATTRS = ("story_location", "story_hero", "story_sidekick", "story_plot", "story_theme")
NULLABLE = ("user_age_group", "user_reading_level", "story_rating", "is_speech_on")

# ---------------------------------------------------------------------------
# The outcome variable, checked without being seen.
#
# A field can be present and still be unusable: all zeros, milliseconds where the
# dictionary says seconds, a timeout ceiling, text in a numeric column. Every other
# column here gets that check, and the outcome needs it most, because a protocol
# built on an unusable outcome fails only after it has been reviewed.
#
# So each reading time is turned into one of the labels below and discarded. To say
# how many distinct values the column holds, and how many sessions share the most
# common one, a one-way fingerprint of the value is counted in place of the value.
# The number itself is never kept, never printed, never charted, and never broken
# down by language, age band, reading level, text, child, country, version or date.
# Each group is ten times wider than the one before. That is enough to settle whether
# the column is in seconds or milliseconds, and to expose a field that is empty,
# constant or nonsense. It is far too coarse to say anything about how quickly anyone
# read. Because the groups are never crossed with anything, they cannot
# speak to a hypothesis about text difficulty or about reading experience: those are
# claims about differences between rows, and this block draws no distinction between
# rows at all.
TIME_COL = "time_spent_reading"

TIME_BANDS = ((1, 10, "1 to 9"),
              (10, 100, "10 to 99"),
              (100, 1_000, "100 to 999"),
              (1_000, 10_000, "1,000 to 9,999"),
              (10_000, 100_000, "10,000 to 99,999"))
TIME_TOP = "100,000 or more"

# The two families of group the check sorts values into: those no measure could be
# taken from, and those grouped by size. Both outputs read these, so they are named
# once here.
TIME_UNUSABLE = ("empty", "not a number", "negative", "zero")
TIME_SIZES = (("above 0 but below 1",) + tuple(lbl for _, _, lbl in TIME_BANDS)
              + (TIME_TOP,))

# Distinct fingerprints are counted exactly up to this many, then reported as "more
# than", so a fine-grained column cannot grow an unbounded table in memory.
TIME_DISTINCT_CAP = 50_000

# Room for the shared-value check, which must keep working above that cap: a hard
# timeout, or a stand-in code such as 999999, is exactly what a column of finely
# varying values would otherwise hide. The table keeps this many values at a time,
# so a value shared by any appreciable share of sessions survives while one-offs are
# dropped. The count it reports is therefore "at least", and exact whenever the
# column holds no more different values than the table has room for.
TIME_HEAVY_SLOTS = 10_000

# The study analyses these age bands only. Each summary breakdown is therefore
# reported twice, once for the whole export and once for this subset, which is
# also how the charts are split into Part 1 and Part 2. Only the file record, the
# per-file details and the reading-time check describe the whole export alone.
# The sampling plan concerns the sample actually analysed.
ELIGIBLE_AGE_BANDS = ("Age 7-8", "Age 9+")

MISSING = "(missing)"

# Section and metric names shared by the two outputs. The summary data file writes
# them and the manifest looks them up, so they are named once here rather than typed
# out twice; a typo would otherwise leave a chart silently empty.
SCOPE_LABEL = " and ".join(ELIGIBLE_AGE_BANDS)
TIME_SEC = "reading time, checked only for whether it can be used"
TIME_USABLE_METRIC = "sessions with a usable number"
SPAN_SEC = "days between an account's first and last session"

csv.field_size_limit(min(2**31 - 1, sys.maxsize))


# ===================================================================== charting

# Colourblind-safe (Okabe-Ito), dark enough to print
BLUE, ORANGE, GREEN, GREY = "#0072B2", "#E69F00", "#009E73", "#999999"

CSS = """
:root { color-scheme: light dark; }
body { font-family: -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif;
       margin: 0 auto; max-width: 1180px; padding: 28px 20px 60px;
       color: #1a1a1a; background: #fff; line-height: 1.45; }
h1 { font-size: 23px; margin: 0 0 4px; }
h2 { font-size: 21px; margin: 40px 0 14px; padding-bottom: 7px;
     border-bottom: 2px solid #0072B2; color: #0072B2; font-weight: 600; }
h2.part { font-size: 26px; margin: 0 0 6px; padding: 0; border: none;
          color: #0072B2; }
p.sub { margin: 0 0 22px; color: #666; font-size: 13px; }
/* Part 2 repeats Part 1 for the age bands the study analyses, and starts a fresh
   sheet when the page is printed. */
.part-head { margin: 54px 0 4px; padding-top: 26px;
             border-top: 3px solid #0072B2; }
.part-head.first { margin-top: 34px; }
.part-head p { margin: 4px 0 0; color: #555; font-size: 13px; max-width: 78ch; }
@media print { .part-head { break-before: page; page-break-before: always; }
               .part-head.first { break-before: auto; page-break-before: auto; }
               .card { break-inside: avoid; page-break-inside: avoid; } }
nav.toc { border: 1px solid #e3e3e3; border-radius: 7px; padding: 14px 18px;
          margin: 22px 0 8px; font-size: 13px; }
nav.toc h2 { font-size: 13px; margin: 0 0 8px; padding: 0; border: none;
             color: #555; letter-spacing: .04em; text-transform: uppercase; }
nav.toc ol { margin: 0; padding-left: 20px; }
nav.toc > ol > li { margin-bottom: 7px; font-weight: 600; }
nav.toc ol ol { padding-left: 18px; margin: 3px 0 0; font-weight: 400;
                list-style: none; }
nav.toc ol ol li { margin: 1px 0; }
nav.toc a { color: #0072B2; text-decoration: none; }
nav.toc a:hover { text-decoration: underline; }
.grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 18px; }
.grid.full { grid-template-columns: 1fr; }
.card { border: 1px solid #e3e3e3; border-radius: 7px; padding: 12px 14px 8px;
        background: #fff; overflow-x: auto; }
/* every chart carries a viewBox, so a narrow window or a sheet of paper scales it
   down rather than cutting it off */
svg { max-width: 100%; height: auto; }
.card h3 { font-size: 13px; margin: 0 0 8px; font-weight: 600; color: #222; }
table.rec { border-collapse: collapse; font-size: 13px; margin-bottom: 6px; }
table.rec td { padding: 2px 16px 2px 0; vertical-align: top; }
table.rec td.k { color: #666; white-space: nowrap; }
table.rec td.v { font-family: ui-monospace, Consolas, monospace; word-break: break-all; }
.note { font-size: 12px; color: #777; margin-top: 26px; }
table.tab { border-collapse: collapse; font-size: 12.5px; width: 100%;
            max-width: 560px; }
table.tab td { padding: 4px 0; border-bottom: 1px solid #f2f2f2; }
table.tab td.k { padding-left: 16px; text-indent: -16px; }
table.tab td.n { text-align: right; font-variant-numeric: tabular-nums;
                 white-space: nowrap; padding-left: 14px; }
/* each segment sits in the left column with its explanation in the right, as grid
   siblings, so the two always start on the same line */
.segs { display: grid; grid-template-columns: minmax(0, 1.05fr) minmax(0, 1fr);
        column-gap: 34px; row-gap: 20px; align-items: start; }
.segs.cols { grid-template-columns: repeat(auto-fit, minmax(230px, 1fr));
             column-gap: 40px; }
.segs.cols table.tab { max-width: none; }
.seg-n p, .seg-foot p { margin: 0; }
.seg-foot { grid-column: 1 / -1; border-top: 1px solid #eee; padding-top: 12px; }
.grp { font-size: 11px; font-weight: 600; letter-spacing: .05em;
       text-transform: uppercase; color: #8a8a8a; padding-bottom: 4px;
       border-bottom: 1px solid #e0e0e0; }
@media (max-width: 820px) { .segs { grid-template-columns: 1fr; row-gap: 10px; } }
/* a count that means trouble only when it is not zero, so colour follows the value */
table.tab tr.bad td { color: #b3261e; font-weight: 600; }
table.tab tr.bad td.k::before { content: "\\25CF  "; color: #d93025; }
table.tab tr.fine td.k::before { content: "\\25CF  "; color: #d6d6d6; }
table.tab tr.fine td.n { color: #999; }
table.tab tr.band td.k::before { content: "\\25CF  "; color: #0072B2; }
table.tab tr.sum td { font-weight: 600; border-top: 1px solid #dcdcdc;
                      border-bottom: none; padding-top: 7px; }
p.verdict { font-size: 13px; font-weight: 600; margin: 0 0 12px; }
p.verdict.good { color: #0b7a48; }
p.verdict.warn { color: #9a6400; }
p.verdict.bad  { color: #b3261e; }
p.cardnote { font-size: 11.5px; color: #6f6f6f; margin: 2px 0; line-height: 1.55; }
p.lead { font-size: 13px; color: #444; margin: 0 0 18px; max-width: 78ch;
         line-height: 1.5; }
@media (max-width: 820px) { .grid { grid-template-columns: 1fr; } }
"""


AXIS = "#3f3f3f"       # axis titles: darker and bolder than tick labels
AXIS_SIZE = 10.5
TICK_W = 6.0           # approximate width of a tick-label character at size 10


def _txt(x, y, s, size=11, fill="#444", anchor="start", weight="normal"):
    return (f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" fill="{fill}" '
            f'text-anchor="{anchor}" font-weight="{weight}" '
            f'font-family="inherit">{escape(str(s))}</text>')


def _atxt(x, y, s, anchor="middle"):
    """A horizontal axis title."""
    return _txt(x, y, s, size=AXIS_SIZE, fill=AXIS, anchor=anchor, weight="600")


def _vtxt(x, y, s):
    """An axis title turned on its side, to sit against a vertical value axis."""
    return (f'<text x="{x:.1f}" y="{y:.1f}" font-size="{AXIS_SIZE}" fill="{AXIS}" '
            f'text-anchor="middle" font-weight="600" font-family="inherit" '
            f'transform="rotate(-90 {x:.1f} {y:.1f})">{escape(str(s))}</text>')


def _tick_gutter(ticks, y_title):
    """Width for the value axis: the widest tick label, plus room for a title.

    Measured rather than fixed, so a chart whose labels read "12" does not carry the
    same left margin as one reading "2.4M", which is what pushed the axis title far
    away from the numbers it belongs to.
    """
    widest = max(len(_fmt(t)) for t in ticks)
    return int(widest * TICK_W) + 13 + (16 if y_title else 0)


def _nice_ticks(hi, count=4):
    """Whole-number tick values, the top one at or above the data maximum.

    Everything plotted here is a count, and _fmt prints ticks without decimals, so a
    fractional step would label distinct gridlines identically (0, 0, 1, 2, 2).
    """
    if hi <= 0:
        return [0, 1]
    if hi <= count:
        return list(range(int(hi) + 1))
    raw = hi / count
    mag = 10 ** (len(str(int(raw))) - 1)
    for mult in (1, 2, 2.5, 5, 10):
        step = math.ceil(mag * mult)
        if step * count >= hi:
            break
    return [i * step for i in range(count + 1)]


def _fmt(v):
    v = float(v)
    if v >= 1_000_000:
        return f"{v/1_000_000:.1f}M".replace(".0M", "M")
    if v >= 1_000:
        return f"{v/1_000:.1f}k".replace(".0k", "k")
    return f"{v:.0f}"


def hbar(pairs, width=520, row_h=21, pad_left=None, x_title="", y_title=""):
    """Horizontal bars; suits long category names such as languages.

    x_title names the value axis and y_title the category axis, so a reader who
    has not seen the export knows what is being counted and what it is counted by.
    The label gutter is measured from the labels themselves, so short names leave
    the axis title beside them rather than stranded at the edge of the chart.
    """
    pairs = list(pairs)
    if not pairs:
        return '<svg width="10" height="10"></svg>'
    if pad_left is None:
        widest = max(len(str(label)) for label, _ in pairs)
        pad_left = min(190, int(widest * 5.7) + 14) + (16 if y_title else 0)
    hi = max(v for _, v in pairs) or 1
    top, foot = 4, (26 if x_title else 8)
    h = row_h * len(pairs) + top + foot
    inner = width - pad_left - 54
    out = [f'<svg width="{width}" height="{h}" viewBox="0 0 {width} {h}" role="img">']
    if y_title:
        out.append(_vtxt(10, top + row_h * len(pairs) / 2, y_title))
    for i, (label, v) in enumerate(pairs):
        y = i * row_h + top
        bw = max(1.0, inner * (v / hi))
        out.append(_txt(pad_left - 8, y + 14, label, anchor="end"))
        out.append(f'<rect x="{pad_left}" y="{y+3}" width="{bw:.1f}" height="{row_h-9}" '
                   f'rx="2" fill="{BLUE}"/>')
        out.append(_txt(pad_left + bw + 6, y + 14, _fmt(v), fill="#555"))
    if x_title:
        out.append(_atxt(pad_left + inner / 2, h - 8, x_title))
    out.append("</svg>")
    return "".join(out)


def vbar(pairs, width=520, height=210, colour=BLUE, x_title="", y_title=""):
    """Vertical bars. With many categories, labels thin out so they never collide."""
    pairs = list(pairs)
    if not pairs:
        return '<svg width="10" height="10"></svg>'
    n = len(pairs)
    show_values = n <= 12          # value labels would overlap beyond this
    every = 1 if n <= 12 else -(-n // 8)
    hi = max(v for _, v in pairs) or 1
    ticks = _nice_ticks(hi)
    top = max(ticks) or 1
    # a bar can reach the top tick exactly, so when value labels are drawn above
    # the bars, leave them headroom or the tallest bar's label is clipped
    pl = _tick_gutter(ticks, y_title)
    pb = 34 + (16 if x_title else 0)
    pt = 19 if show_values else 10
    height += (16 if x_title else 0)
    iw, ih = width - pl - 14, height - pb - pt
    out = [f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img">']
    for t in ticks:
        y = pt + ih - ih * (t / top)
        out.append(f'<line x1="{pl}" y1="{y:.1f}" x2="{pl+iw}" y2="{y:.1f}" '
                   f'stroke="#ececec" stroke-width="1"/>')
        out.append(_txt(pl - 7, y + 3.5, _fmt(t), size=10, fill="#888", anchor="end"))
    slot = iw / len(pairs)
    bw = min(46, slot * 0.66)
    for i, (label, v) in enumerate(pairs):
        x = pl + slot * i + (slot - bw) / 2
        bh = ih * (v / top)
        out.append(f'<rect x="{x:.1f}" y="{pt+ih-bh:.1f}" width="{bw:.1f}" '
                   f'height="{max(bh,0.6):.1f}" rx="2" fill="{colour}"/>')
        if show_values:
            out.append(_txt(x + bw / 2, pt + ih - bh - 4, _fmt(v), size=10, fill="#555",
                            anchor="middle"))
        if i % every == 0 or i == n - 1:
            out.append(_txt(x + bw / 2, pt + ih + 15, label, size=10, anchor="middle"))
    out.append(f'<line x1="{pl}" y1="{pt+ih}" x2="{pl+iw}" y2="{pt+ih}" stroke="#bbb"/>')
    if x_title:
        out.append(_atxt(pl + iw / 2, pt + ih + 32, x_title))
    if y_title:
        out.append(_vtxt(11, pt + ih / 2, y_title))
    out.append("</svg>")
    return "".join(out)


def timeline(daily, width=1080, height=260, x_title="", y_title=""):
    """Filled area of sessions per day across the whole window."""
    height += 10 if x_title else 0      # room for the axis title below the months
    pts, unplotted = [], 0
    for d, v in sorted(daily.items()):
        try:
            pts.append((date.fromisoformat(d), v))
        except ValueError:      # keep the chart; report the loss below
            unplotted += 1
    if not pts:
        return '<svg width="10" height="10"></svg>'
    xs = [d for d, _ in pts]
    ys = [v for _, v in pts]
    d0, d1 = xs[0], xs[-1]
    span = max((d1 - d0).days, 1)
    hi = max(ys) or 1
    ticks = _nice_ticks(hi)
    top = max(ticks) or 1
    pl = _tick_gutter(ticks, y_title)
    pb, pt, pr = 40 + (10 if x_title else 0), 22, 16
    iw, ih = width - pl - pr, height - pb - pt

    def px(d):
        return pl + iw * ((d - d0).days / span)

    def py(v):
        return pt + ih - ih * (v / top)

    out = [f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img">']
    for t in ticks:
        y = py(t)
        out.append(f'<line x1="{pl}" y1="{y:.1f}" x2="{pl+iw}" y2="{y:.1f}" stroke="#ececec"/>')
        out.append(_txt(pl - 8, y + 3.5, _fmt(t), size=10, fill="#888", anchor="end"))
    path = " ".join(f"{'M' if i == 0 else 'L'} {px(d):.1f} {py(v):.1f}"
                    for i, (d, v) in enumerate(zip(xs, ys)))
    out.append(f'<path d="{path} L {px(d1):.1f} {pt+ih:.1f} L {px(d0):.1f} {pt+ih:.1f} Z" '
               f'fill="{BLUE}" fill-opacity="0.16"/>')
    out.append(f'<path d="{path}" fill="none" stroke="{BLUE}" stroke-width="1.6"/>')
    # month boundaries as x labels, thinned so they never collide
    months, seen = [], set()
    for d in xs:
        key = (d.year, d.month)
        if key not in seen:
            seen.add(key)
            months.append(date(d.year, d.month, 1))
    step = max(1, len(months) // 10)
    for m in months[::step]:
        if m < d0:
            m = d0
        x = px(m)
        out.append(f'<line x1="{x:.1f}" y1="{pt}" x2="{x:.1f}" y2="{pt+ih}" stroke="#f2f2f2"/>')
        out.append(_txt(x, pt + ih + 15, m.strftime("%b %Y"), size=10, anchor="middle"))
    out.append(f'<line x1="{pl}" y1="{pt+ih}" x2="{pl+iw}" y2="{pt+ih}" stroke="#bbb"/>')
    caption = f"{d0.isoformat()} to {d1.isoformat()}  ({span+1} days)"
    if unplotted:
        caption += f"   [{unplotted} day(s) with an unreadable date are not plotted]"
    out.append(_txt(pl + iw, 12, caption, size=10, fill="#888", anchor="end"))
    if x_title:
        out.append(_atxt(pl + iw / 2, pt + ih + 33, x_title))
    if y_title:
        out.append(_vtxt(11, pt + ih / 2, y_title))
    out.append("</svg>")
    return "".join(out)


def card(title, svg):
    """One titled panel on the manifest, holding a chart or a table."""
    return f'<div class="card"><h3>{escape(title)}</h3>{svg}</div>'


def table_block(segments, note="", verdict=None):
    """Counts that should be read rather than plotted, in explained segments.

    segments: [(heading, [(label, value, kind)], explanation)]. Each segment and its
    explanation are siblings in a two-column grid, so every explanation starts level
    with the heading it belongs to however long the segments are.

    The kinds carry meaning rather than decoration: 'bad' is a count that signals
    trouble only when it is not zero, so it is coloured only then; 'band' is an
    ordinary size group; 'sum' a closing total. A verdict of
    (text, "good"|"warn"|"bad") leads, so the answer comes before the numbers.
    """
    out = []
    if verdict:
        out.append(f'<p class="verdict {verdict[1]}">{escape(verdict[0])}</p>')
    # with no explanations to sit beside them, segments read better side by side
    plain = not any(why for _, _, why in segments)
    out.append('<div class="segs cols">' if plain else '<div class="segs">')
    for heading, rows, why in segments:
        out.append('<div class="seg-t">')
        if heading:
            out.append(f'<div class="grp">{escape(heading)}</div>')
        out.append('<table class="tab">')
        for r in rows:
            label, value = r[0], r[1]
            kind = r[2] if len(r) > 2 else ""
            if kind == "bad":
                kind = "bad" if str(value).strip() not in ("0", "") else "fine"
            out.append(f'<tr class="{kind}"><td class="k">{escape(str(label))}</td>'
                       f'<td class="n">{escape(str(value))}</td></tr>')
        out.append("</table></div>")
        if not plain:
            out.append(f'<div class="seg-n"><p class="cardnote">{escape(why)}</p></div>')
    if note:
        out.append(f'<div class="seg-foot"><p class="cardnote">{escape(note)}</p></div>')
    out.append("</div>")
    return "".join(out)


def _slug(s, seen):
    """A stable, unique id for a heading, so the contents list can link to it."""
    base = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-") or "section"
    slug, n = base, 2
    while slug in seen:
        slug, n = f"{base}-{n}", n + 1
    seen.add(slug)
    return slug


def page(title, subtitle, record_rows, parts, lead=""):
    """parts: [(part_title, part_blurb, [(section_heading, [(card, is_full)])])]

    Each part opens a fresh sheet when printed, and every part and section is
    given an id so the contents list at the top can link straight to it.
    """
    seen = set()
    ids = [(p_title, _slug(p_title, seen),
            [(h, _slug(h, seen)) for h, _ in p_sections])
           for p_title, _, p_sections in parts]

    body = [f"<h1>{escape(title)}</h1>", f'<p class="sub">{escape(subtitle)}</p>']
    if lead:
        body.append(f'<p class="lead">{escape(lead)}</p>')
    body.append('<table class="rec">')
    for k, v in record_rows:
        body.append(f'<tr><td class="k">{escape(k)}</td><td class="v">{escape(str(v))}</td></tr>')
    body.append("</table>")

    body.append('<nav class="toc"><h2>Contents</h2><ol>')
    for p_title, p_id, secs in ids:
        body.append(f'<li><a href="#{p_id}">{escape(p_title)}</a><ol>')
        for h, h_id in secs:
            body.append(f'<li><a href="#{h_id}">{escape(h)}</a></li>')
        body.append("</ol></li>")
    body.append("</ol></nav>")

    for i, ((p_title, p_blurb, p_sections), (_, p_id, secs)) in enumerate(
            zip(parts, ids)):
        first = " first" if i == 0 else ""
        body.append(f'<div class="part-head{first}" id="{p_id}">'
                    f'<h2 class="part">{escape(p_title)}</h2>'
                    f"<p>{escape(p_blurb)}</p></div>")
        for (heading, cards), (_, h_id) in zip(p_sections, secs):
            body.append(f'<h2 id="{h_id}">{escape(heading)}</h2>')
            full = [c for c, f in cards if f]
            half = [c for c, f in cards if not f]
            if full:
                body.append('<div class="grid full">' + "".join(full) + "</div>")
            if half:
                body.append('<div class="grid">' + "".join(half) + "</div>")
    body.append('<p class="note">Counts only. Reading times appear solely as the '
                'groups in Part 1, never as values and never broken down by any '
                'other field, and the story rating appears only as how often it '
                'is empty.</p>')
    return ("<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
            f"<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
            f"<title>{escape(title)}</title><style>{CSS}</style></head><body>"
            + "".join(body) + "</body></html>")


# ===================================================================== counting

def blank(v):
    """Is this cell empty? Whitespace, NA and NULL all count as empty."""
    return v is None or v.strip() == "" or v.strip().upper() in ("NA", "NULL")


def clean(v):
    """Collapse any run of whitespace, so no label carries an embedded line break."""
    return " ".join(v.split())


def fill(v):
    """A cell's value, or the label MISSING, so an empty cell is still a category."""
    return MISSING if blank(v) else clean(v)


_TRUE = {"1", "true", "t", "yes", "y", "on"}
_FALSE = {"0", "false", "f", "no", "n", "off"}


def norm_flag(v):
    """Normalise boolean-ish exports (TRUE/False/yes) to '1'/'0'."""
    if v == MISSING:
        return v
    lv = v.lower()
    return "1" if lv in _TRUE else "0" if lv in _FALSE else v


def canon_num(v):
    """'8.0' -> '8', so page counts group correctly whatever wrote the file."""
    if v == MISSING:
        return v
    try:
        f = float(v)
        if f == int(f):
            return str(int(f))
    except (ValueError, OverflowError):
        pass
    return v


def time_class(raw):
    """Reduce one reading time to a validity label and a fingerprint of its value.

    The label is what gets counted. The second element is a one-way fingerprint of
    the value in canonical numeric form, so that distinct values can be counted and a
    shared value spotted without the number itself being kept: '1800', '1800.0' and
    '1.8e3' fingerprint alike, and no fingerprint is ever printed or charted.
    """
    if raw is None or not raw.strip():
        return "empty", None
    v = raw.strip()
    try:
        x = float(v)
    except (ValueError, OverflowError):
        return "not a number", None
    if x != x or x in (float("inf"), float("-inf")):
        return "not a number", None
    if x < 0:
        return "negative", None
    if x == 0:
        return "zero", None
    fp = hashlib.blake2b(repr(x).encode("ascii"), digest_size=16).digest()
    if x < 1:
        return "above 0 but below 1", fp
    for lo, hi, label in TIME_BANDS:
        if lo <= x < hi:
            return label, fp
    return TIME_TOP, fp


def pages_differ(mx, tp):
    """Compare numerically where possible, so '8' vs '8.0' is not a violation."""
    a, b = mx.strip(), tp.strip()
    if a == b:
        return False
    try:
        return float(a) != float(b)
    except ValueError:
        return True


def parse_when(raw):
    """Return (iso_day, hour_or_None, weekday) or (None, None, None).

    Accepted: ISO-style dates with '-' or '/' and an optional time after a space or
    'T'; compact all-digit YYYYMMDD and YYYYMMDDHHMMSS; and Unix epochs in seconds
    (10 digits) or milliseconds (13 digits), read as UTC. Day-first forms such as
    03/01/2026 are deliberately NOT guessed, since day and month cannot be told
    apart; such rows are counted as unreadable instead.
    """
    v = raw.strip()
    try:
        if len(v) >= 10 and v[4] in "-/" and v[7] in "-/":
            d = date(int(v[0:4]), int(v[5:7]), int(v[8:10]))
            hour = None
            if len(v) >= 13 and v[10] in " T":
                hh = v[11:13]
                if hh.isdigit():         # non-throwing: a malformed time must not
                    h = int(hh)          # discard the already-parsed day
                    hour = h if h <= 23 else None
            return d.isoformat(), hour, d.weekday()
        if v.isdigit():
            if len(v) == 8:                     # YYYYMMDD
                d = date(int(v[0:4]), int(v[4:6]), int(v[6:8]))
                return d.isoformat(), None, d.weekday()
            if len(v) == 14:                    # YYYYMMDDHHMMSS
                d = date(int(v[0:4]), int(v[4:6]), int(v[6:8]))
                h = int(v[8:10])
                return d.isoformat(), (h if h <= 23 else None), d.weekday()
            if len(v) in (10, 13):              # epoch seconds / milliseconds, UTC
                ts = int(v) / (1000 if len(v) == 13 else 1)
                if 946684800 <= ts <= 4102444800:       # years 2000 to 2100
                    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
                    return dt.date().isoformat(), dt.hour, dt.date().weekday()
    except ValueError:
        pass
    return None, None, None


def sha256_of(path):
    """The file's SHA-256, read a megabyte at a time so size does not matter."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def new_acc():
    """A fresh set of counters.

    One of these is filled for the whole export and a second for the age bands the
    study analyses, so every breakdown can be reported at both scopes without a
    second pass over the file. Sets hold things that must be counted once however
    often they recur, such as an account or a text; Counters hold running totals.
    """
    return {
        "n_rows": 0, "pair_rows": 0, "no_user_id": 0, "no_text_id": 0,
        "lang_age_user": set(), "text_lang_lvl": set(), "text_user": set(),
        "lang_age_n": Counter(), "text_sessions": Counter(), "user_sessions": Counter(),
        "speech": Counter(), "customized": Counter(),
        "day": Counter(), "month": Counter(), "user_first_month": {},
        "hour": Counter(), "weekday": Counter(),
        "missing": Counter({k: 0 for k in NULLABLE}),
        "date_min": None, "date_max": None,
        "version": Counter(), "missing_by_version": Counter(),
        "pages": Counter(), "pages_by_level": Counter(), "text_pages": {},
        "grain_violations": 0, "country_lang": Counter(),
        "attrs": {k: Counter() for k in ATTRS}, "custom_no_elements": 0,
        "user_span": {}, "user_months": {}, "speech_mask": {},
    }


def tally(a, lang, age, lvl, usr, sid, speech_flag, custom_flag, day, blanks, extra):
    """Add one session to one set of counters.

    Called once per row for the whole export, and again for the same row when the
    age band is one the study analyses. Nothing here reads the reading time: that
    column is handled separately in process_source, for the reasons at the top.
    """
    a["n_rows"] += 1
    # A row with no identifier cannot be attributed. Counting it under one shared
    # "(missing)" key would invent a single enormous account, or a single text read by
    # everyone, so such rows are counted separately and kept out of those tallies.
    has_usr, has_sid = usr != MISSING, sid != MISSING
    if not has_usr:
        a["no_user_id"] += 1
    if not has_sid:
        a["no_text_id"] += 1
    if has_usr:
        a["lang_age_user"].add((lang, age, usr))
        a["user_sessions"][usr] += 1
    if has_sid:
        a["text_lang_lvl"].add((sid, lang, lvl))
        a["text_sessions"][sid] += 1
        a["text_pages"].setdefault(sid, set()).add(extra["pages"])
    if has_usr and has_sid:
        a["pair_rows"] += 1
        a["text_user"].add((sid, usr))
    a["lang_age_n"][(lang, age)] += 1
    # speech is crossed with age band as well as language, so the CSV can show how
    # common narration is within the bands the study analyses
    a["speech"][(lang, age, speech_flag)] += 1
    a["customized"][custom_flag] += 1
    for nm in blanks:
        a["missing"][nm] += 1
        a["missing_by_version"][(extra["version"], nm)] += 1
    if day:
        a["day"][day] += 1
        month = day[:7]
        a["month"][month] += 1
        a["weekday"][extra["weekday"]] += 1
        a["hour"][extra["hour"] if extra["hour"] is not None else -1] += 1
        a["date_min"] = day if a["date_min"] is None or day < a["date_min"] else a["date_min"]
        a["date_max"] = day if a["date_max"] is None or day > a["date_max"] else a["date_max"]
        if has_usr:
            first = a["user_first_month"].get(usr)
            if first is None or month < first:
                a["user_first_month"][usr] = month
            lo, hi = a["user_span"].get(usr, (day, day))
            a["user_span"][usr] = (min(lo, day), max(hi, day))
            a["user_months"].setdefault(usr, set()).add(month)

    a["version"][extra["version"]] += 1
    a["country_lang"][(extra["country"], lang)] += 1
    a["pages"][extra["pages"]] += 1
    a["pages_by_level"][(lvl, extra["pages"])] += 1
    if extra["grain_violation"]:
        a["grain_violations"] += 1
    for k in ATTRS:
        if extra["attrs"][k] != MISSING:
            a["attrs"][k][extra["attrs"][k]] += 1
    if custom_flag == "1" and all(extra["attrs"][k] == MISSING for k in ATTRS):
        a["custom_no_elements"] += 1
    # 1 = seen with speech on, 2 = seen with speech off; 3 means the account varies
    bit = 1 if speech_flag == "1" else 2 if speech_flag == "0" else 0
    if bit and has_usr:
        a["speech_mask"][usr] = a["speech_mask"].get(usr, 0) | bit


_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
           "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
_WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def _age_sort_key(x):
    """Order age bands by the first number in the label, not alphabetically.

    "Age 10-12" sorts before "Age 4-6" as text, which puts the oldest band first.
    Labels with no number, and then the missing band, go last.
    """
    return (x == MISSING, [int(n) for n in re.findall(r"\d+", x)] or [999], x)


def _month_label(m):
    """'2026-03' -> 'Mar 26', which reads better on a crowded axis."""
    try:
        y, mm = m.split("-")
        return f"{_MONTHS[int(mm) - 1]} {y[2:]}"
    except (ValueError, IndexError):
        return m


def _bands(values, edges):
    """edges: [(label, predicate)] applied in order."""
    return [(label, sum(1 for v in values if test(v))) for label, test in edges]


def _span_days(a):
    """Calendar days from the first session to the last, both included."""
    if not a["date_min"] or not a["date_max"]:
        return 0
    try:
        return (date.fromisoformat(a["date_max"])
                - date.fromisoformat(a["date_min"])).days + 1
    except ValueError:
        return 0


def span_bands(a):
    """How many accounts fall in each band of days from first session to last.

    An account seen on one day only says nothing about change over time, so the
    shape of this tells us how much of the export can speak to that at all.
    """
    spans = []
    for lo, hi in a["user_span"].values():
        try:
            spans.append((date.fromisoformat(hi) - date.fromisoformat(lo)).days)
        except ValueError:
            pass
    return _bands(spans, [("same day", lambda d: d == 0),
                          ("1 to 6 days", lambda d: 1 <= d <= 6),
                          ("1 to 4 weeks", lambda d: 7 <= d <= 27),
                          ("1 to 6 months", lambda d: 28 <= d <= 182),
                          ("more than 6 months", lambda d: d > 182)])


def active_month_bands(a):
    """How many accounts were active in one month, two months, and so on."""
    counts = [len(v) for v in a["user_months"].values()]
    return _bands(counts, [("1", lambda n: n == 1), ("2", lambda n: n == 2),
                           ("3 to 5", lambda n: 3 <= n <= 5),
                           ("6 to 11", lambda n: 6 <= n <= 11),
                           ("12 or more", lambda n: n >= 12)])


def speech_consistency(a):
    """Accounts that always had speech on, always off, or varied between sessions."""
    masks = list(a["speech_mask"].values())
    return [("always on", sum(1 for m in masks if m == 1)),
            ("always off", sum(1 for m in masks if m == 2)),
            ("varies within the account", sum(1 for m in masks if m == 3))]


def new_accounts_by_month(a):
    """How many accounts were seen for the first time in each month."""
    c = Counter()
    for m in a["user_first_month"].values():
        c[m] += 1
    return c


def _as_int(v):
    """The integer a summary cell holds, or None if it holds text such as a date."""
    try:
        return int(str(v).replace(",", ""))
    except (TypeError, ValueError):
        return None


class Summary:
    """A read-only view over the rows of the summary data file.

    The manifest is drawn entirely through this class, never from the counters that
    produced the rows. Two things follow, and both are the point of it. The manifest
    cannot display a figure that the summary data file does not contain, so the two
    deliverables cannot disagree. And the summary data file on its own is enough to
    rebuild the manifest, or to build something else from, without the export.
    """

    def __init__(self, rows):
        self.rows = rows
        self._cell = {}          # (section, group_1, group_2, metric) -> value
        self._sec = {}           # section -> [(group_1, group_2, metric, value)]
        for section, g1, g2, metric, value in rows:
            self._cell[(section, g1, g2, metric)] = value
            self._sec.setdefault(section, []).append((g1, g2, metric, value))

    def has_row(self, section, metric, g1="", g2=""):
        return (section, g1, g2, metric) in self._cell

    def text(self, section, metric, g1="", g2="", default=""):
        return self._cell.get((section, g1, g2, metric), default)

    def num(self, section, metric, g1="", g2="", default=0):
        n = _as_int(self.text(section, metric, g1, g2))
        return default if n is None else n

    def series(self, section, metric):
        """[(group_1, count)] for one metric, in the order the summary lists it.

        Rows with no group_1 are summary lines for the section as a whole, such as
        "texts served at more than one page count", so they are left out of what is
        plotted as a series.
        """
        out = []
        for g1, _g2, m, value in self._sec.get(section, ()):
            if m != metric or not g1:
                continue
            n = _as_int(value)
            if n is not None:
                out.append((g1, n))
        return out

    def groups(self, section, metric):
        """The distinct group_1 values carrying a metric, in order."""
        seen, out = set(), []
        for g1, _g2, m, _v in self._sec.get(section, ()):
            if m == metric and g1 not in seen:
                seen.add(g1)
                out.append(g1)
        return out


# ===================================================================== input files

_SEP_WORDS = {",": "comma", ";": "semicolon", "\t": "tab", "|": "pipe"}
_DATA_EXTS = (".csv", ".tsv", ".txt")


def resolve_inputs(args):
    """Expand folders and patterns into a duplicate-free list of file paths."""
    paths = []
    for a in args:
        if os.path.isdir(a):
            found = []
            for ext in _DATA_EXTS + (".csv.gz", ".tsv.gz", ".txt.gz", ".zip"):
                found += glob.glob(os.path.join(a, "*" + ext))
            if not found:
                sys.exit(f"No CSV files found inside the folder {a}")
            # a compressed copy sitting next to its uncompressed twin is the same
            # data twice; reading both would double every session count
            plain = {os.path.normcase(os.path.abspath(f)) for f in found
                     if f.lower().endswith(_DATA_EXTS)}
            for f in sorted(found):
                if (f.lower().endswith(".gz")
                        and os.path.normcase(os.path.abspath(f[:-3])) in plain):
                    print(f"Note: {os.path.basename(f)} skipped - "
                          f"{os.path.basename(f[:-3])} in the same folder appears "
                          "to be the same data.")
                    continue
                paths.append(f)
        elif any(ch in a for ch in "*?"):
            found = sorted(glob.glob(a))
            if not found:
                sys.exit(f"Nothing matched the pattern {a}")
            paths += found
        elif os.path.exists(a):
            paths.append(a)
        else:
            sys.exit(f"Could not find {a}\nPass the export file(s), e.g.\n"
                     "  python lets_story_summary.py C:/data/lets_story_export.csv")
    seen, out = set(), []
    for p in paths:
        # normcase: Windows paths are case-insensitive, so part1.csv and PART1.CSV
        # are the same file and must not be read twice
        ap = os.path.normcase(os.path.abspath(p))
        if ap not in seen:
            seen.add(ap)
            out.append(p)
    return out


def build_sources(paths):
    """One source per logical CSV: a plain file, a .gz file, or a member of a .zip.

    The checksum always covers the file as it would be transferred, so for a zip it
    is the archive's checksum, noted as such.
    """
    srcs, chk_cache = [], {}

    def checksum_for(p):
        if p not in chk_cache:
            print(f"Computing the checksum of {os.path.basename(p)}...")
            chk_cache[p] = sha256_of(p)
        return chk_cache[p]

    for p in paths:
        lp = p.lower()
        if lp.endswith(".zip"):
            try:
                zf = zipfile.ZipFile(p)
            except zipfile.BadZipFile:
                sys.exit(f"{p} is not a valid zip archive. If it is actually a "
                         "plain CSV, rename it to .csv; otherwise please re-export "
                         "or re-copy the file.")
            with zf as z:
                members = [i for i in z.infolist()
                           if not i.is_dir()
                           and not i.filename.startswith("__MACOSX")
                           and i.filename.lower().endswith(_DATA_EXTS)]
            if not members:
                print(f"Note: no CSV found inside {p}, so it was skipped.")
                continue
            chk = checksum_for(p)
            for i in members:
                srcs.append({"kind": "zip", "path": p, "member": i.filename,
                             "label": os.path.basename(p) + " :: " + i.filename,
                             "size": i.file_size,
                             "checksum": chk + " (the whole archive)"})
        elif lp.endswith(".gz"):
            srcs.append({"kind": "gz", "path": p, "label": os.path.basename(p),
                         "size": os.path.getsize(p), "checksum": checksum_for(p)})
        else:
            srcs.append({"kind": "plain", "path": p, "label": os.path.basename(p),
                         "size": os.path.getsize(p), "checksum": checksum_for(p)})
    return srcs


PROBE_N = 4 * 1024 * 1024

# The sniff below sees only the first PROBE_N bytes, so a stray byte later in the
# file could still fail strict decoding. Rather than let one such byte abort a
# multi-million-row run, decoding errors substitute U+FFFD and are counted, and the
# count is reported per file so the record stays honest.
_replaced = {"n": 0}


def _count_replace(exc):
    _replaced["n"] += 1
    return ("�", exc.end)


codecs.register_error("oxford_count_replace", _count_replace)


def probe_bytes(src, n=PROBE_N):
    """The first n bytes, whether the source is plain, gzipped or inside a zip."""
    if src["kind"] == "plain":
        with open(src["path"], "rb") as fh:
            return fh.read(n)
    if src["kind"] == "gz":
        try:
            with gzip.open(src["path"], "rb") as fh:
                return fh.read(n)
        except (gzip.BadGzipFile, EOFError, OSError):
            sys.exit(f"{src['label']} is not a valid gzip file. If it is actually a "
                     "plain CSV, rename it to .csv; otherwise please re-export or "
                     "re-copy the file.")
    with zipfile.ZipFile(src["path"]) as z, z.open(src["member"]) as fh:
        return fh.read(n)


def sniff(src):
    """Record the encoding and delimiter, so the file record can state both."""
    buf = probe_bytes(src)
    if buf[:2] in (b"\xff\xfe", b"\xfe\xff"):
        src["enc"] = "utf-16"        # BOM present; the codec reads and strips it
    else:
        try:
            buf.decode("utf-8")
            src["enc"] = "utf-8-sig"
        except UnicodeDecodeError as e:
            # A probe capped at PROBE_N may cut a multi-byte character at its end;
            # only that is benign. A complete file that fails to decode is not UTF-8.
            if len(buf) == PROBE_N and e.start >= len(buf) - 3:
                src["enc"] = "utf-8-sig"
            else:
                src["enc"] = "latin-1"   # decodes any byte, so never fails
    first = buf.decode(src["enc"], errors="replace").split("\n", 1)[0]
    src["sep"] = max([",", ";", "\t", "|"], key=first.count)


def open_text(src):
    """Open a source as text in the encoding sniff() settled on.

    Decoding errors substitute a replacement character and are counted rather than
    raised, so one stray byte in a large export cannot abort the whole run.
    """
    err = "oxford_count_replace"
    if src["kind"] == "plain":
        return open(src["path"], "r", encoding=src["enc"], errors=err, newline="")
    if src["kind"] == "gz":
        return io.TextIOWrapper(gzip.open(src["path"], "rb"),
                                encoding=src["enc"], errors=err, newline="")
    zf = zipfile.ZipFile(src["path"])
    fh = io.TextIOWrapper(zf.open(src["member"]), encoding=src["enc"], errors=err,
                          newline="")
    fh._keep_zip_open = zf       # closed alongside the wrapper by GC
    return fh


# ===================================================================== main

def process_source(src, allr, elig, G):
    """Read one CSV a row at a time, adding each row to the counters.

    The file is streamed rather than loaded, so memory does not grow with the size
    of the export. `allr` counts every row, `elig` only the age bands the study
    analyses, and `G` holds the figures that describe the run as a whole rather than
    either scope, such as the rows that had to be set aside.
    """
    src.update({"rows": 0, "columns": [], "absent": [],
                "date_min": None, "date_max": None})
    _replaced["n"] = 0
    fh = open_text(src)
    try:
        reader = csv.reader(fh, delimiter=src["sep"], quotechar='"')
        try:
            raw_header = next(reader)
        except StopIteration:
            print(f"Note: {src['label']} is empty.")
            return
        header = [h.lstrip("\ufeff").strip() for h in raw_header]
        src["columns"] = header
        lower = [h.lower() for h in header]
        idx = {n: (lower.index(n.lower()) if n.lower() in lower else None)
               for n in KEEP}
        src["absent"] = [k for k in KEEP if idx[k] is None]
        if src["absent"]:
            print(f"Note: {src['label']} lacks: " + ", ".join(src["absent"]))

        # Positions of the KEEP columns, so the loop below indexes each row directly
        # instead of resolving names 30 times per row. Slot numbers follow KEEP order.
        keep_pos = [idx[n] for n in KEEP]
        slot = {n: j for j, n in enumerate(KEEP)}
        # read separately from the KEEP slots, and only ever passed to time_class
        time_pos = lower.index(TIME_COL) if TIME_COL in lower else None
        src["time_present"] = time_pos is not None
        (S_USR, S_LANG, S_AGE, S_LVL, S_SID, S_TITLE, S_CUST, S_SPEECH,
         S_DT, S_VER, S_CTRY, S_TP, S_MX) = (
            slot[n] for n in ("user_id", "read_language", "user_age_group",
                              "user_reading_level", "story_id", "story_title",
                              "is_customized", "is_speech_on", "finished_reading_at",
                              "game_version", "user_country", "total_page_available",
                              "max_page_reached"))
        attr_slots = [(k, slot[k]) for k in ATTRS]
        nul_slots = [(nm, slot[nm]) for nm in NULLABLE]
        header_key = [h.lower() for h in header]
        h0 = header_key[0]
        n_header = len(header)
        blake2b, intern = hashlib.blake2b, sys.intern
        digests = G["row_digests"]
        eligible = ELIGIBLE_AGE_BANDS
        tcls, tdist, theavy = (G["time_classes"], G["time_distinct"],
                               G["time_heavy"])
        usable = [i for i in keep_pos if i is not None]
        max_pos = max(usable) if usable else -1
        all_present = len(usable) == len(keep_pos)

        # Categorical fields repeat constantly (a language, an age band, a version),
        # so each distinct raw value is normalised once and remembered, rather than
        # re-cleaned on every row. Identifiers stay uncached: they barely repeat.
        _S = object()
        vcache, bcache, fcache, pcache, gcache = {}, {}, {}, {}, {}

        def cfill(v):
            r = vcache.get(v, _S)
            if r is _S:
                r = vcache[v] = intern(fill(v))
            return r

        def cblank(v):
            r = bcache.get(v, _S)
            if r is _S:
                r = bcache[v] = blank(v)
            return r

        def cflag(v):
            r = fcache.get(v, _S)
            if r is _S:
                r = fcache[v] = intern(norm_flag(fill(v)))
            return r

        def cpages(v):
            r = pcache.get(v, _S)
            if r is _S:
                r = pcache[v] = intern(canon_num(fill(v)))
            return r

        def cgrain(mx, tp):
            key = (mx, tp)
            r = gcache.get(key, _S)
            if r is _S:
                r = gcache[key] = (not blank(mx) and not blank(tp)
                                   and pages_differ(mx, tp))
            return r

        for row in reader:
            if not row or not any(row):
                G["empty_rows"] += 1
                continue
            # concatenated exports sometimes carry the header again mid-file; the
            # cheap first-cell test keeps the full comparison off the common path
            if row[0].strip().lower() == h0 and \
                    [c.lstrip("\ufeff").strip().lower() for c in row] == header_key:
                G["repeated_headers"] += 1
                continue
            lr = len(row)
            if lr != n_header:
                # A row with the wrong number of fields is not merely short: an
                # unquoted delimiter shifts every later field left or right, so the
                # reading time can land in a slot that is printed as a label and
                # crossed with age band. Such a row is counted and discarded unread.
                G["misaligned_rows"] += 1
                continue
            if all_present and lr > max_pos:
                vals = [row[i] for i in keep_pos]
            else:
                vals = [(row[i] if i is not None and i < lr else None)
                        for i in keep_pos]

            # The date is parsed once here and reused below, both for the alignment
            # anchor and for the day, hour and weekday counts.
            raw_dt = vals[S_DT]
            dt_blank = blank(raw_dt)
            day = hour = weekday = None
            if not dt_blank:
                day, hour, weekday = parse_when(raw_dt)

            # A shift that gains one field and loses another keeps the field count
            # intact, so check two anchors whose shapes a shift destroys. Both must
            # fail, and neither counts as failed when simply empty, so an ordinary
            # bad date does not discard a row.
            if day is None and not dt_blank:
                _sp = vals[S_SPEECH]
                if not blank(_sp) and norm_flag(clean(_sp)) not in ("0", "1"):
                    G["unshaped_rows"] += 1
                    continue

            # a digest of the nineteen KEEP columns only, deliberately: hashing the
            # whole row would feed the reading times into a computation. repr() of
            # the list is injective for strings and None, so a field containing the
            # separator, or an absent column versus an empty one, cannot collide,
            # and it builds the encoding in one C-level call rather than two Python
            # loops over every field of every row.
            digest = blake2b(repr(vals).encode("utf-8", "replace"),
                             digest_size=8).digest()
            if digest in digests:
                G["duplicate_rows"] += 1
            else:
                digests.add(digest)

            lang = cfill(vals[S_LANG])
            age = cfill(vals[S_AGE])
            lvl = cfill(vals[S_LVL])
            usr = intern(fill(vals[S_USR]))
            sid = vals[S_SID]
            sid = fill(vals[S_TITLE]) if blank(sid) else clean(sid)
            sid = intern(sid)
            speech_flag = cflag(vals[S_SPEECH])
            custom_flag = cflag(vals[S_CUST])

            if dt_blank:
                G["no_date"] += 1
            elif day is None:
                G["bad_dates"] += 1
            else:
                if src["date_min"] is None or day < src["date_min"]:
                    src["date_min"] = day
                if src["date_max"] is None or day > src["date_max"]:
                    src["date_max"] = day

            blanks = [nm for nm, j in nul_slots if cblank(vals[j])]
            mx, tp = vals[S_MX], vals[S_TP]
            extra = {
                "version": cfill(vals[S_VER]),
                "country": cfill(vals[S_CTRY]),
                "pages": cpages(tp),
                "grain_violation": cgrain(mx, tp),
                "attrs": {k: cfill(vals[j]) for k, j in attr_slots},
                "hour": hour, "weekday": weekday,
            }

            args = (lang, age, lvl, usr, sid, speech_flag, custom_flag, day,
                    blanks, extra)
            tally(allr, *args)
            if age in eligible:
                tally(elig, *args)

            # The outcome column, deliberately handled outside args: it is reduced
            # to a validity label here and never passed to tally(), so it cannot
            # reach any breakdown. See the TIME_COL note at the top of the file.
            if time_pos is not None:
                label, fp = time_class(row[time_pos])
                tcls[label] += 1
                if fp is not None:
                    if tdist is not None:
                        tdist.add(fp)
                        if len(tdist) > TIME_DISTINCT_CAP:
                            tdist = G["time_distinct"] = None    # report "more than"
                    # Bounded frequent-value tracking. The table is allowed to grow
                    # to twice its budget and is then pruned back to the most
                    # frequent half, so the cost is amortised rather than paid on
                    # every new value. A value shared by any appreciable share of
                    # rows keeps its count across prunes and survives; a one-off
                    # does not. Retained counts are therefore lower bounds.
                    if fp in theavy:
                        theavy[fp] += 1
                    else:
                        theavy[fp] = 1
                        if len(theavy) > 2 * TIME_HEAVY_SLOTS:
                            G["time_heavy_approx"] = True
                            keep = sorted(theavy.items(), key=lambda kv: -kv[1])
                            theavy = dict(keep[:TIME_HEAVY_SLOTS])
                            G["time_heavy"] = theavy

            src["rows"] += 1
            if allr["n_rows"] % 250000 == 0:
                print(f"  read {allr['n_rows']:,} rows...")
    finally:
        fh.close()
        src["replaced"] = _replaced["n"]


def build_manifest(rows):
    """Draw the manifest from summary rows and nothing else.

    Kept apart from the counting so that it can run on the summary data file on its
    own, which is what --manifest-from does. That separation is also the proof of the
    arrangement: a manifest rebuilt from the file has to match the one written beside
    it, because there is no other source it could have drawn from.
    """
    # ----------------------------------------------------------- the manifest
    # From here on the numbers come out of `summary`, the rows just written to the
    # summary data file, and never out of the counters. So the manifest is a view of
    # that file: it cannot show a figure the file lacks, and the file by itself is
    # enough to rebuild the manifest.
    summary = Summary(rows)

    # Each helper below pulls one series out of the summary. `pre` selects the scope,
    # "" for the whole export and "<age bands> only: " for Part 2, which is exactly
    # the prefix emit() wrote. `top` limits how many bars a chart draws; passing
    # top=None asks for the full series, which is how cut_title finds out whether
    # anything was left out.
    def _cut(pairs, top):
        return pairs if top is None else pairs[:top]

    def lang_pairs(S, pre, top=14):
        return _cut(S.series(pre + "sessions by language", "sessions"), top)

    def age_pairs(S, pre, top=None):
        return _cut(S.series(pre + "sessions by age band", "sessions"), top)

    def per_account_pairs(S, pre, top=None):
        return S.series(pre + "sessions per account", "accounts")

    def reuse_pairs(S, pre, top=None):
        # the summary spells the bands out; the axis has room only for the numbers
        short = {"read by 1 account(s)": "1", "read by 2 to 5 account(s)": "2-5",
                 "read by 6 to 20 account(s)": "6-20",
                 "read by more than 20 account(s)": "20+"}
        return [(short.get(g, g), v)
                for g, v in S.series(pre + "text reuse", "texts")]

    def missing_pairs(S, pre, top=None):
        return [(g.replace("user_", "").replace("_", " "), v)
                for g, v in S.series(pre + "missing values",
                                     "sessions with the field empty")]

    def version_pairs(S, pre, top=10):
        return _cut(S.series(pre + "app version", "sessions"), top)

    def pages_pairs(S, pre, top=14):
        return _cut(S.series(pre + "pages per story", "sessions"), top)

    def month_pairs(S, pre, top=24):
        pairs = S.series(pre + "sessions by month", "sessions")
        return [(_month_label(m), v) for m, v in (pairs[-top:] if top else pairs)]

    def first_seen_pairs(S, pre, top=24):
        pairs = S.series(pre + "new accounts by month", "accounts")
        return [(_month_label(m), v) for m, v in (pairs[-top:] if top else pairs)]

    def weekday_pairs(S, pre, top=None):
        return S.series(pre + "sessions by day of week", "sessions")

    def hour_pairs(S, pre, top=None):
        # the section also holds a "(no time recorded)" row, which is not an hour
        return [(g, v) for g, v in S.series(pre + "sessions by hour of day", "sessions")
                if g.isdigit()]

    def span_pairs(S, pre, top=None):
        return S.series(pre + SPAN_SEC, "accounts")

    def active_pairs(S, pre, top=None):
        return S.series(pre + "months in which an account was active", "accounts")

    def day_counts(S, pre):
        return dict(S.series(pre + "sessions by day", "sessions"))

    def cut_title(title, S, pre, fn, top, how="most common"):
        """A title that owns up to a chart that could not draw every category."""
        total = len(fn(S, pre, top=None))
        return title if total <= top else (
            f"{title} (the {top} {how} of {total}; the summary data lists every one)")

    # ---- the reading-time check, which belongs to Part 1 alone -------------
    def time_segments(S):
        if S.has_row(TIME_SEC, "the column is not in the export"):
            return [("", [("the column is not in the export", "", "bad")],
                     "Without it there is nothing to check, and nothing for the "
                     "study to measure later.")]

        def n(lbl, grp):
            return f"{S.num(TIME_SEC, 'sessions', lbl, grp):,}"

        return [
            ("Cannot be used",
             [(lbl, n(lbl, "cannot be used"), "bad") for lbl in TIME_UNUSABLE],
             "Values no measure could be taken from. These four turn red only when "
             "they are not zero. A large count in any of them means the column "
             "needs looking at before anything else."),
            ("Grouped by size",
             [(lbl, n(lbl, "grouped by size"), "band") for lbl in TIME_SIZES],
             "Only how big each value is, each group ten times wider than the one "
             "before. This is what settles whether the column is in seconds or in "
             "milliseconds. It is far too coarse to say how quickly anyone read, "
             "and it is never split by language, age, text, child or date."),
            ("In total",
             [("sessions with a usable number",
               f"{S.num(TIME_SEC, TIME_USABLE_METRIC, '', 'in total'):,}", "sum"),
              ("different values in the column",
               S.text(TIME_SEC, "different values in the column", "", "in total"),
               "sum"),
              ("sessions sharing one and the same value",
               S.text(TIME_SEC, "sessions sharing one and the same value", "",
                      "in total"), "sum")],
             "A handful of different values would mean the column is rounded or "
             "bucketed. A great many sessions sharing one and the same value is how "
             "a timeout cap shows itself."),
        ]

    def time_verdict_from(S):
        """The answer, stated before the numbers that support it."""
        if S.has_row(TIME_SEC, "the column is not in the export"):
            return ("The reading-time column is not in this export.", "bad")
        usable = S.num(TIME_SEC, TIME_USABLE_METRIC, "", "in total")
        unusable = sum(S.num(TIME_SEC, "sessions", lbl, "cannot be used")
                       for lbl in TIME_UNUSABLE)
        if usable == 0:
            return ("No session carries a usable number.", "bad")
        if unusable:
            return (f"{usable:,} of {usable + unusable:,} sessions carry a usable "
                    f"number. {unusable:,} need checking.", "warn")
        return (f"All {usable:,} sessions carry a usable number.", "good")

    # ---- the cards ---------------------------------------------------------
    def key_figures(S, pre):
        """The handful of numbers a reader wants before any chart."""
        ov = pre + "overview"

        def c(metric):
            return f"{S.num(ov, metric):,}"

        return [
            ("", [("sessions", c("sessions"), "sum"),
                  ("accounts", c("distinct accounts"), "sum"),
                  ("stories", c("distinct texts"), "sum"),
                  ("story, language and reading level together",
                   c("distinct text-language-level combinations"), "sum")], ""),
            ("", [("languages", c("distinct languages"), "sum"),
                  ("countries", c("distinct countries"), "sum"),
                  ("reading levels", c("distinct reading levels"), "sum"),
                  ("app versions", c("distinct app versions"), "sum")], ""),
            ("", [("first session", S.text(ov, "earliest session date"), "sum"),
                  ("last session", S.text(ov, "latest session date"), "sum"),
                  ("days covered", c("days from first session to last"), "sum"),
                  ("months with at least one session",
                   c("months with at least one session"), "sum")], ""),
        ]

    def summary_card(S, pre, scope):
        return (card(f"Key figures, {scope}", table_block(key_figures(S, pre))), True)

    def when_cards(S, pre):
        return [
            (card("Sessions per day across the window",
                  timeline(day_counts(S, pre), y_title="sessions",
                           x_title="date")), True),
            (card(cut_title("Sessions per month", S, pre, month_pairs, 24,
                            "most recent"),
                  vbar(month_pairs(S, pre), y_title="sessions",
                       x_title="month")), False),
            (card(cut_title("Accounts appearing for the first time, per month", S,
                            pre, first_seen_pairs, 24, "most recent"),
                  vbar(first_seen_pairs(S, pre), colour=GREEN, y_title="accounts",
                       x_title="month first seen")), False),
            (card("Sessions by day of the week",
                  vbar(weekday_pairs(S, pre), y_title="sessions",
                       x_title="day of the week")), False),
            (card("Sessions by hour of the day, as logged",
                  vbar(hour_pairs(S, pre), y_title="sessions",
                       x_title="hour (00 to 23)")), False),
        ]

    def divide_cards(S, pre):
        return [
            (card(cut_title("Sessions by language", S, pre, lang_pairs, 14),
                  hbar(lang_pairs(S, pre), x_title="sessions",
                       y_title="language")), False),
            (card("Sessions by age band",
                  vbar(age_pairs(S, pre), y_title="sessions",
                       x_title="age band")), False),
            (card("Sessions per account",
                  vbar(per_account_pairs(S, pre), colour=GREEN, y_title="accounts",
                       x_title="sessions in the account")), False),
            (card("Accounts per story",
                  vbar(reuse_pairs(S, pre), colour=ORANGE, y_title="stories",
                       x_title="accounts that read the story")), False),
            (card("How often each field is empty",
                  vbar(missing_pairs(S, pre), colour=GREY, y_title="sessions",
                       x_title="field")), False),
            (card(cut_title("Sessions by app version", S, pre, version_pairs, 10),
                  hbar(version_pairs(S, pre), x_title="sessions",
                       y_title="app version")), False),
            (card(cut_title("Pages per story", S, pre, pages_pairs, 14, "smallest"),
                  vbar(pages_pairs(S, pre), colour=ORANGE, y_title="sessions",
                       x_title="pages in the story")), False),
        ]

    def account_cards(S, pre):
        return [
            (card(SPAN_SEC[0].upper() + SPAN_SEC[1:],
                  vbar(span_pairs(S, pre), colour=GREEN, y_title="accounts",
                       x_title="days from first to last session")), False),
            (card("Months in which an account was active",
                  vbar(active_pairs(S, pre), colour=GREEN, y_title="accounts",
                       x_title="months with at least one session")), False),
        ]

    # ---- the page ----------------------------------------------------------
    fr = "file record"
    record = [("Files", summary.text(fr, "files read")),
              ("Total rows", f"{summary.num(fr, 'total data rows'):,}"),
              ("Window", f"{summary.text(fr, 'earliest session date')} to "
                         f"{summary.text(fr, 'latest session date')}"),
              ("Produced", f"{summary.text(fr, 'summary produced on')}, "
                           f"script {summary.text(fr, 'script version')}")]
    for label in summary.groups("files", "data rows"):
        record.append(
            (label, f"{summary.num('files', 'data rows', label):,} rows \u00b7 "
                    f"SHA-256 {summary.text('files', 'SHA-256 checksum', label)}"))

    elig_pre = SCOPE_LABEL + " only: "
    parts = [
        ("Part 1. The export as a whole",
         "Everything Gameloft exported, before any restriction.",
         [("Key figures", [summary_card(summary, "", "the whole export")]),
          ("Is the reading-time column usable?", [
              (card("Every reading time sorted into a group, then discarded",
                    table_block(
                        time_segments(summary),
                        "No reading time is stored, plotted, or broken down by any "
                        "other field, so nothing here says how quickly anyone read. "
                        "The point of it is to catch a column that cannot be used "
                        "early rather than late: one that is all zeros, or in "
                        "milliseconds where we expect seconds, or holds text where "
                        "it should hold numbers, or is capped by a timeout. This "
                        "check belongs to Part 1 alone. Repeating it in Part 2 "
                        "would split reading time by age band, which is exactly "
                        "what the study must not see before its protocol is "
                        "reviewed.",
                        verdict=time_verdict_from(summary))),
               True)]),
          ("When the sessions happened", when_cards(summary, "")),
          ("How the sessions divide up", divide_cards(summary, "")),
          ("Each account across the window", account_cards(summary, ""))]),
        (f"Part 2. {SCOPE_LABEL} only",
         "The same figures again, counting only the sessions in the age bands the "
         "study analyses. The reading-time check is not repeated here, because "
         "splitting reading time by age band is precisely what the protocol must "
         "not do before review.",
         [("Key figures", [summary_card(summary, elig_pre, "these age bands")]),
          ("When the sessions happened", when_cards(summary, elig_pre)),
          ("How the sessions divide up", divide_cards(summary, elig_pre)),
          ("Each account across the window", account_cards(summary, elig_pre))]),
    ]

    return page("Let's Story export: integrity check for Oxford",
                "An agnostic sanity check on the export. Counts only.",
                record, parts,
                lead="This page asks one question: is the export complete, well "
                     "formed and usable? It answers none of the study's research "
                     "questions and is not a step in the analysis. No figure here "
                     "relates reading time to any property of a text, a child or a "
                     "session: reading time enters only as wide groups by size and "
                     "counts of different values, for the export as a whole, too "
                     "coarse and too undifferentiated to bear on either hypothesis. "
                     "Every number below is read from the summary data file that "
                     "accompanies this page.")


def rebuild_manifest(summary_path):
    """Redraw the manifest from a summary data file, with no export present.

    This has two uses. It shows that the manifest holds nothing the summary data
    file does not, since a rebuild has to match the page written beside it. And it
    lets either team redraw the page later from the small file rather than the
    large one.
    """
    expected = ["section", "group_1", "group_2", "metric", "value"]
    with open(summary_path, "r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.reader(fh)
        header = next(reader, None)
        if header is None or [h.strip().lower() for h in header[:5]] != expected:
            sys.exit(f"{summary_path} does not look like a summary data file. "
                     "Expected the five columns " + ", ".join(expected) + ".")
        rows = [r[:5] for r in reader if len(r) >= 5]
    if not rows:
        sys.exit(f"{summary_path} holds no rows.")
    with open(OUT_HTML, "w", encoding="utf-8") as fh:
        fh.write(build_manifest(rows))
    print(f"Rebuilt {os.path.abspath(OUT_HTML)} from {summary_path}")
    print(f"{len(rows):,} summary rows read. The export was not needed.")


def main():
    """Read the export, write the summary data file, then draw the manifest."""
    # Redraw the manifest from a summary data file, without the export.
    if len(sys.argv) == 3 and sys.argv[1] == "--manifest-from":
        rebuild_manifest(sys.argv[2])
        return
    if len(sys.argv) < 2:
        sys.exit("Pass the export file(s), e.g.\n"
                 "  python lets_story_summary.py C:/data/lets_story_export.csv\n"
                 "Several files, a folder, or a pattern like exports/*.csv all work.\n"
                 "\nTo redraw the manifest from a summary data file instead:\n"
                 f"  python lets_story_summary.py --manifest-from {OUT_CSV}")
    paths = resolve_inputs(sys.argv[1:])
    srcs = build_sources(paths)
    if not srcs:
        sys.exit("No readable CSV files were found.")

    allr, elig = new_acc(), new_acc()
    G = {"empty_rows": 0, "repeated_headers": 0, "misaligned_rows": 0,
         "unshaped_rows": 0, "duplicate_rows": 0, "bad_dates": 0, "no_date": 0,
         "row_digests": set(), "time_classes": Counter(), "time_distinct": set(),
         "time_heavy": {}, "time_heavy_approx": False}
    for src in srcs:
        sniff(src)
        print(f"Reading {src['label']} ({src['size']/1e6:,.0f} MB)..."
              if src["size"] >= 10e6 else f"Reading {src['label']}...")
        try:
            process_source(src, allr, elig, G)
        except (EOFError, OSError, zipfile.BadZipFile) as e:
            sys.exit(f"{src['label']} could not be read to the end "
                     f"({type(e).__name__}). The file may be truncated or "
                     "corrupted; please re-export or re-copy it.")

    if allr["n_rows"] == 0:
        sys.exit("No data rows were read. Please check the file(s).")

    elig_label = SCOPE_LABEL + " only"

    # The reading-time check, resolved once so the summary and the manifest agree.
    time_absent = (not any(s.get("time_present", True) for s in srcs)
                   and not G["time_classes"])
    time_usable = sum(G["time_classes"].get(k, 0) for k in TIME_SIZES)
    time_unusable = sum(G["time_classes"].get(k, 0) for k in TIME_UNUSABLE)
    _tot = time_usable + time_unusable
    if time_absent:
        time_verdict = ("The reading-time column is not in this export.", "bad")
    elif time_usable == 0:
        time_verdict = ("No session carries a usable number.", "bad")
    elif time_unusable:
        time_verdict = (f"{time_usable:,} of {_tot:,} sessions carry a usable "
                        f"number. {time_unusable:,} need checking.", "warn")
    else:
        time_verdict = (f"All {_tot:,} sessions carry a usable number.", "good")
    time_distinct_txt = (f"more than {TIME_DISTINCT_CAP:,}"
                         if G["time_distinct"] is None
                         else f"{len(G['time_distinct']):,}")
    _shared = max(G["time_heavy"].values()) if G["time_heavy"] else 0
    time_shared_txt = (
        f"at least {_shared:,} (the column holds too many different values to count "
        f"this exactly, but any value shared by more than one session in "
        f"{TIME_HEAVY_SLOTS:,} is found)" if G["time_heavy_approx"]
        else f"{_shared:,}")

    # -------------------------------------------------------------- the CSV
    rows = []

    def add(section, g1, g2, metric, value):
        rows.append([section, g1, g2, metric, str(value)])

    def fmt_date(v):
        # never let a Python None leak into a partner-facing document
        return v if v is not None else "(no readable dates)"

    add("what this file is", "", "", "purpose",
        "An integrity check on the Let's Story export: is it complete, well formed "
        "and usable?")
    add("what this file is", "", "", "relation to the research questions",
        "None. Every figure below is a count of rows, accounts, texts or distinct "
        "values. No figure relates reading time to any property of a text, a child "
        "or a session: reading time enters only as wide groups by size and counts of "
        "different values, for the export as a whole, too coarse and too "
        "undifferentiated to bear on either hypothesis.")
    add("what this file is", "", "", "reading times",
        "Checked only for whether a value is there, whether it is a number, and "
        "roughly how big it is, in groups each ten times wider than the one before, "
        "together with how many different values the column holds and how many "
        "sessions share one and the same value. Never broken down by any other "
        "field. No reading time is stored, reported or charted.")
    add("what this file is", "", "", "story rating",
        "Reported only as how often it is empty, never as a value.")

    add("file record", "", "", "summary produced on", date.today().isoformat())
    add("file record", "", "", "script version", SCRIPT_VERSION)
    add("file record", "", "", "files read", len(srcs))
    add("file record", "", "", "total data rows", allr["n_rows"])
    add("file record", "", "", "earliest session date", fmt_date(allr["date_min"]))
    add("file record", "", "", "latest session date", fmt_date(allr["date_max"]))
    add("file record", "", "", "empty rows skipped", G["empty_rows"])
    add("file record", "", "", "repeated header rows skipped", G["repeated_headers"])
    add("file record", "", "",
        "rows skipped because the field count did not match the header",
        G["misaligned_rows"])
    add("file record", "", "",
        "rows skipped because their fields did not match the shape of the header",
        G["unshaped_rows"])
    add("file record", "", "",
        "rows identical to an earlier row in every column the script reads",
        G["duplicate_rows"])
    add("file record", "", "", "rows with no session date", G["no_date"])
    add("file record", "", "", "rows whose session date could not be read",
        G["bad_dates"])

    for s in srcs:
        add("files", s["label"], "", "file size in bytes", s["size"])
        add("files", s["label"], "", "SHA-256 checksum", s["checksum"])
        add("files", s["label"], "", "text encoding",
            "utf-8" if s["enc"] == "utf-8-sig" else s["enc"])
        add("files", s["label"], "", "delimiter", _SEP_WORDS.get(s["sep"], s["sep"]))
        add("files", s["label"], "", "data rows", s.get("rows", 0))
        add("files", s["label"], "", "earliest session date", fmt_date(s.get("date_min")))
        add("files", s["label"], "", "latest session date", fmt_date(s.get("date_max")))
        add("files", s["label"], "",
            "characters replaced because they did not match the detected encoding",
            s.get("replaced", 0))
        add("files", s["label"], "", "columns", len(s.get("columns", [])))
        if s.get("absent"):
            add("files", s["label"], "", "expected columns not present in this file",
                ", ".join(s["absent"]))
        for i, h in enumerate(s.get("columns", []), 1):
            add("files", s["label"], f"column {i:02d}", "name", h)

    def emit(a, tag):
        """Write one scope's counts into the summary rows.

        Called twice: once with no tag for the whole export, and once tagged with
        the age bands, which prefixes every section name. The manifest looks the
        sections up by those names, so a change here changes both outputs together.
        """
        pre = (tag + ": ") if tag else ""
        add(pre + "overview", "", "", "sessions", a["n_rows"])
        add(pre + "overview", "", "", "distinct accounts", len(a["user_sessions"]))
        add(pre + "overview", "", "", "distinct texts", len(a["text_sessions"]))
        add(pre + "overview", "", "", "sessions with no account identifier",
            a["no_user_id"])
        add(pre + "overview", "", "", "sessions with no story identifier",
            a["no_text_id"])
        add(pre + "overview", "", "", "distinct text-language-level combinations",
            len(a["text_lang_lvl"]))
        add(pre + "overview", "", "", "distinct languages",
            len({k[0] for k in a["lang_age_n"] if k[0] != MISSING}))
        add(pre + "overview", "", "", "distinct countries",
            len({k[0] for k in a["country_lang"] if k[0] != MISSING}))
        add(pre + "overview", "", "", "distinct reading levels",
            len({k[0] for k in a["pages_by_level"] if k[0] != MISSING}))
        add(pre + "overview", "", "", "distinct app versions",
            len({k for k in a["version"] if k != MISSING}))
        add(pre + "overview", "", "", "earliest session date", fmt_date(a["date_min"]))
        add(pre + "overview", "", "", "latest session date", fmt_date(a["date_max"]))
        add(pre + "overview", "", "", "days from first session to last",
            _span_days(a))
        add(pre + "overview", "", "", "months with at least one session",
            len(a["month"]))

        # Marginals for language and age band. The cross-tabulation below carries
        # the same information, but the manifest plots these two directly, and
        # anyone working from the summary data wants them without having to add up
        # a table themselves.
        lang_n, age_n = Counter(), Counter()
        for (lang, age), v in a["lang_age_n"].items():
            lang_n[lang] += v
            age_n[age] += v
        lang_u, age_u = Counter(), Counter()
        for lang, age, usr in a["lang_age_user"]:
            lang_u[(lang, usr)] = 1
            age_u[(age, usr)] = 1
        acc_by_lang, acc_by_age = Counter(), Counter()
        for lang, _u in lang_u:
            acc_by_lang[lang] += 1
        for age, _u in age_u:
            acc_by_age[age] += 1
        for k in sorted(lang_n, key=lambda x: (x == MISSING, -lang_n[x], x)):
            add(pre + "sessions by language", k, "", "sessions", lang_n[k])
            add(pre + "sessions by language", k, "", "distinct accounts",
                acc_by_lang.get(k, 0))
        for k in sorted(age_n, key=_age_sort_key):
            add(pre + "sessions by age band", k, "", "sessions", age_n[k])
            add(pre + "sessions by age band", k, "", "distinct accounts",
                acc_by_age.get(k, 0))

        users_by_la = Counter(k[:2] for k in a["lang_age_user"])
        for k in sorted(set(users_by_la) | set(a["lang_age_n"])):
            add(pre + "by language and age band", k[0], k[1], "sessions",
                a["lang_age_n"].get(k, 0))
            add(pre + "by language and age band", k[0], k[1],
                "distinct accounts", users_by_la.get(k, 0))

        texts_by_ll = Counter(k[1:3] for k in a["text_lang_lvl"])
        for k in sorted(texts_by_ll):
            add(pre + "distinct texts by language and reading level", k[0],
                k[1], "distinct texts", texts_by_ll[k])

        per_text = Counter(k[0] for k in a["text_user"])
        for label, test in [("1", lambda n: n == 1), ("2 to 5", lambda n: 2 <= n <= 5),
                            ("6 to 20", lambda n: 6 <= n <= 20),
                            ("more than 20", lambda n: n > 20)]:
            add(pre + "text reuse", f"read by {label} account(s)", "", "texts",
                sum(1 for n in per_text.values() if test(n)))
        shared = {t for t, n in per_text.items() if n > 1}
        add(pre + "text reuse", "", "",
            "sessions whose text was read by more than one account",
            sum(v for t, v in a["text_sessions"].items() if t in shared))

        for label, test in [("1", lambda n: n == 1), ("2", lambda n: n == 2),
                            ("3 or 4", lambda n: n in (3, 4)),
                            ("5 to 9", lambda n: 5 <= n <= 9),
                            ("10 or more", lambda n: n >= 10)]:
            add(pre + "sessions per account", label, "", "accounts",
                sum(1 for n in a["user_sessions"].values() if test(n)))

        for k in sorted(a["speech"]):
            add(pre + "speech mode by language and age band",
                k[0] + " / " + k[1], k[2], "sessions", a["speech"][k])
        for k in sorted(a["customized"]):
            add(pre + "is_customized", k, "", "sessions", a["customized"][k])
        for nm in NULLABLE:
            add(pre + "missing values", nm, "", "sessions with the field empty",
                a["missing"][nm])
        for m in sorted(a["month"]):
            add(pre + "sessions by month", m, "", "sessions", a["month"][m])
        for m, n in sorted(new_accounts_by_month(a).items()):
            add(pre + "new accounts by month", m, "", "accounts", n)
        for i, w in enumerate(_WEEKDAYS):
            add(pre + "sessions by day of week", w, "", "sessions",
                a["weekday"].get(i, 0))
        for h in range(24):
            add(pre + "sessions by hour of day", f"{h:02d}", "", "sessions",
                a["hour"].get(h, 0))
        if a["hour"].get(-1):
            add(pre + "sessions by hour of day", "(no time recorded)", "", "sessions",
                a["hour"][-1])

        add(pre + "repeat readings", "", "", "distinct account-text pairs",
            len(a["text_user"]))
        # denominator is the rows carrying both identifiers, not every row, or the
        # unattributable rows would masquerade as repeat readings
        add(pre + "repeat readings", "", "", "sessions that repeat a text already read "
            "by that account", a["pair_rows"] - len(a["text_user"]))

        for k in sorted(a["version"], key=lambda x: (-a["version"][x], x)):
            add(pre + "app version", k, "", "sessions", a["version"][k])
        for k in sorted(a["missing_by_version"]):
            add(pre + "empty fields by app version", k[0], k[1],
                "sessions with the field empty", a["missing_by_version"][k])

        for k in sorted(a["pages"], key=lambda x: (len(x), x)):
            add(pre + "pages per story", k, "", "sessions", a["pages"][k])
        for k in sorted(a["pages_by_level"]):
            add(pre + "pages per story by reading level", k[0], k[1],
                "sessions", a["pages_by_level"][k])
        multi = sum(1 for v in a["text_pages"].values() if len(v) > 1)
        add(pre + "pages per story", "", "", "texts served at more than one page count",
            multi)
        add(pre + "data integrity", "", "",
            "sessions where max_page_reached differs from total_page_available",
            a["grain_violations"])

        for k in ATTRS:
            for v in sorted(a["attrs"][k], key=lambda x: (-a["attrs"][k][x], x)):
                add(pre + "story elements", k.replace("story_", ""), v, "sessions",
                    a["attrs"][k][v])
        add(pre + "story elements", "", "",
            "customised sessions with all five element fields empty",
            a["custom_no_elements"])

        for k in sorted(a["country_lang"], key=lambda x: (-a["country_lang"][x], x)):
            add(pre + "country and language", k[0], k[1], "sessions",
                a["country_lang"][k])

        for label, n in span_bands(a):
            add(pre + SPAN_SEC, label, "", "accounts", n)
        for label, n in active_month_bands(a):
            add(pre + "months in which an account was active", label, "", "accounts", n)
        for label, n in speech_consistency(a):
            add(pre + "speech mode within an account", label, "", "accounts", n)

    # Reading-time validity, reported once for the whole export and never crossed
    # with anything. Deliberately outside emit(), which is where the breakdowns live.
    sec = TIME_SEC
    if time_absent:
        add(sec, "", "", "the column is not in the export", "")
    else:
        for lbl in TIME_UNUSABLE:
            add(sec, lbl, "cannot be used", "sessions",
                G["time_classes"].get(lbl, 0))
        for lbl in TIME_SIZES:
            add(sec, lbl, "grouped by size", "sessions",
                G["time_classes"].get(lbl, 0))
        add(sec, "", "in total", TIME_USABLE_METRIC, time_usable)
        add(sec, "", "in total", "different values in the column", time_distinct_txt)
        add(sec, "", "in total", "sessions sharing one and the same value",
            time_shared_txt)

    emit(allr, "")
    emit(elig, elig_label)
    # daily detail, so the spread over time can be replotted exactly, for the whole
    # export and again for the age bands the study analyses
    for d in sorted(allr["day"]):
        add("sessions by day", d, "", "sessions", allr["day"][d])
    for d in sorted(elig["day"]):
        add(elig_label + ": sessions by day", d, "", "sessions", elig["day"][d])

    with open(OUT_CSV, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, quoting=csv.QUOTE_ALL, lineterminator="\r\n")
        w.writerow(["section", "group_1", "group_2", "metric", "value"])
        w.writerows(rows)

    html = build_manifest(rows)

    with open(OUT_HTML, "w", encoding="utf-8") as fh:
        fh.write(html)

    print(f"\nWrote {os.path.abspath(OUT_CSV)}")
    print(f"Wrote {os.path.abspath(OUT_HTML)}")
    if G["duplicate_rows"] * 5 >= allr["n_rows"] and G["duplicate_rows"]:
        print(f"\nWarning: {G['duplicate_rows']:,} of {allr['n_rows']:,} rows were "
              "identical to an earlier row in every column the script reads. If the "
              "same data was supplied in more than one file (for example a CSV "
              "alongside its compressed copy), the session counts are inflated; "
              "please re-run with only one copy.")
    print("Please send both. They contain counts only.")


if __name__ == "__main__":
    main()
