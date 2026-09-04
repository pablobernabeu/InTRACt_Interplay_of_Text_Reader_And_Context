# An integrity check on the export: how to run it and what comes back

`lets_story_summary.py` is a sanity check on the export, agnostic to our research
questions. It asks one thing: is the file complete, well formed and usable? It
answers none of the study's questions and is not a step in the analysis.

It uses only what comes with Python, so there is nothing to install beyond Python 3.8
or later, which most systems already have.

There is nothing to prepare either. Run it on the export exactly as it comes out, with
all its columns, unfiltered and uncleaned. We will do any further processing at our
end. Files may be comma or semicolon separated, in any column order, and may contain
columns the script does not use. Compressed files (`.csv.gz`, or a `.zip` holding
CSVs) are read as they are.

## Running it

```
python lets_story_summary.py "C:/path/to/lets_story_export.csv"
```

If the export comes as more than one file, pass them all in one run, in any of these
forms:

```
python lets_story_summary.py part1.csv part2.csv part3.csv.gz
python lets_story_summary.py "C:/path/to/export_folder"
python lets_story_summary.py "C:/path/to/exports/*.csv"
```

One run matters: a child who appears in two files is then counted as one account, not
two. If a compressed copy sits in a folder next to its uncompressed twin, the copy is
skipped with a note, so the same data is not counted twice.

On our machine, half a million rows took about forty seconds and 2.4 million rows
between three and four minutes, a little longer again when split across compressed
files. It used around 1.5 to 2.5 GB of memory at that size. Both figures grow with the
number of distinct accounts and texts rather than with rows alone, so treat them as a
guide rather than a promise. Any ordinary workstation is comfortable either way.

## What to send back

Please send us both files the script writes. They are the deliverable, and neither is
useful without the other.

| File | What it is |
| --- | --- |
| `lets_story_summary_data_for_oxford.csv` | The summary data set. Every figure, as data. |
| `lets_story_manifest_for_oxford.html` | The manifest: the readable page, drawn from that data. |

Both are small, a few tens of kilobytes even for a very large export.

The manifest is drawn from the summary data set and from nothing else, so the page
cannot show a figure the data file does not contain, and the data file on its own is
enough to redraw the page. You can see that for yourself:

```
python lets_story_summary.py --manifest-from lets_story_summary_data_for_oxford.csv
```

which rebuilds the page without reading the export at all. We mention it because it is
why we ask for both: the data set is what we can work from and cite, and the page is
what makes it readable.

### The summary data set

Every row has the same five columns, so one row is one labelled number: `section`,
`group_1`, `group_2`, `metric`, `value`.

It opens by stating what it is and what it is not. Then comes a record of the run and
of each input file: name, size, how many rows it holds, the dates it covers, its
column names, its text encoding and separator, and a checksum. A checksum is a short
code worked out from the file's contents, and any change to the file changes the code,
so it lets us show later that the files we receive are the ones you built. For a
`.zip`, the checksum covers the archive itself.

The rest is counts. Some describe who read what: sessions and accounts by language and
age band, distinct texts by language and reading level, and sessions by app version,
by country against language, and by the number of pages in the story. Others describe
how the reading is spread, covering how often a text is read by more than one account,
how many sessions each account has, how often an account reads the same text again,
how long each account spans, and whether its speech setting changes. For four fields
it also counts how often they are empty, and how that varies by app version.

All of those are reported twice, once for the whole export and once for Age 7-8 and
Age 9+ only, so nothing needs filtering at your end. A section whose name begins with
those age bands is the restricted twin of the section of the same name above it.
Sessions and new accounts per month, by day of the week and by hour of the day are
reported the same way, and the file closes with a day-by-day session count for each of
the two.

A few integrity counts report oddities rather than quietly folding them in. Two sit
with the counts for each scope: the check your data dictionary itself suggests,
counting rows where `max_page_reached` differs from `total_page_available`, and a
count of rows with no account or no story identifier. The rest sit in the opening
record, covering rows whose session date is missing or cannot be read, repeated header
lines, and rows identical to an earlier row in every column the script reads.

Two further counts record rows the script sets aside rather than reads. If a row does
not have the same number of fields as the header, or if its fields plainly do not fit
the shape the header describes, it is skipped and counted rather than used. A stray
unquoted comma in a story title shifts every later field along by one, and a shifted
row would otherwise put one column's contents under another column's name. If either
count comes back large, something in the export needs quoting and we should look at it
together.

### The manifest

Open it in any browser. It needs no internet connection and nothing installed. After
the file record it gives a contents list, and is then in two parts. Part 1 covers the
export as a whole. Part 2 repeats the same figures for Age 7-8 and Age 9+ only, and
starts a fresh sheet if you print it. Each part opens with a table of key figures, so
the size and shape of the export can be read off in one place.

Both example files, produced from the 35-row sample you sent, are attached, so you can
see exactly what comes back.

## Reading times: checked, not read

`time_spent_reading` is the measure our study will eventually analyse, and the journal
reviews our protocol before we see it. That makes it all the more important to know
now whether the field is usable at all, because a protocol built on an unusable field
fails only after it has been reviewed.

So the script checks that column the same way it checks every other one, and no
further. Each value is sorted into a group and then discarded. Four groups are for
values that cannot be used at all: empty, not a number, negative and zero. The rest
sort by size, each group ten times wider than the one before: below 1, then 1 to 9, 10
to 99, 100 to 999, and so on up to 100,000 and above.

It also reports how many different values the column holds, and how many sessions
share one and the same value, which is how a timeout cap shows itself. Those two
counts work from a fingerprint of each value rather than the value, so that 1800 and
1800.0 count as the same value and the number itself is never held.

That is the whole of it. No reading time is stored, printed or charted, and none of
these counts is ever broken down by language, age band, reading level, text, child,
country, app version or date, so none of them relates reading time to anything else.
This is also why the check appears in Part 1 alone: repeating it in Part 2 would split
reading time by age band, which is the one thing the protocol must not do before it is
reviewed. What the groups do tell us is whether the field is in seconds or
milliseconds, whether it is largely empty or zero, and whether it is capped, all of
which we would rather learn now than later.

## What the script never uses

It takes values from the nineteen columns listed at the top of the file, plus
`time_spent_reading` for the groups just described and nothing else. The story rating
is reported only as how often it is empty, never as a value. The script performs no
analysis of any kind.

If anything fails, send us the error message and we will adjust it.
