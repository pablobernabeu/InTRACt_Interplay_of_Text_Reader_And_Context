# Tests of the count script

The count script runs on the data controller's machine, once, on a file nobody at
Oxford has seen. It cannot be checked against the real export, so it is checked
against synthetic exports whose figures are known, and against inputs deliberately
made malformed in the ways an export can be malformed.

```
python test_malformed_inputs.py        # both versions, every malformed input
python test_revised_version.py         # the 2026-09-17 version's own checks
```

Both print JSON and take no arguments by default, using the two scripts in the folder
above. Each scenario writes its synthetic export into its own folder here, which the
root `.gitignore` excludes. No real reading time is used: `synth_export.py` invents
them.

The two scripts describe what each version does with each input and assert nothing.
`check_expected.py` runs both, drops the timing fields and compares every scenario
with the reports recorded in `expected/` on 18 October 2026, exiting 1 if any outcome
has changed. The Check workflow runs it on Python 3.8 and 3.13 on every push.

```
python check_expected.py             # compare with expected/
python check_expected.py --update    # re-record, after a deliberate change
```

To include the two scenarios that need real material, pass the paths:

```
python test_malformed_inputs.py ../lets_story_summary_2026-08-05.py \
    ../lets_story_summary.py <the 35-row sample> <the 7 August summary output>
python test_revised_version.py ../lets_story_summary_2026-08-05.py \
    ../lets_story_summary.py <the 7 August summary output>
```

## What the scenarios establish

Run on 17 September 2026 against version 2026-08-05 (as supplied on 7 August) and
version 2026-09-17.

| Input | 2026-08-05 | 2026-09-17 |
|---|---|---|
| The real 35-row sample | reproduces the 7 August output | every figure identical, 17 rows added, and warns that the identifiers are in scientific notation |
| Clean export, 43,226 sessions, one file | exact | exact |
| The same in three parts, one gzipped | exact | exact |
| Titles with commas, quotes and line breaks, properly quoted | exact | exact, and every physical line accounted for |
| Identifiers as `1.23457E+18`, 50,000 accounts | 48,767 accounts, silently | same count, flagged as unreliable, with a warning naming the cause |
| A second part with no header row | wrote that row's reading time, identifier and timestamp into the deliverable as column names | refuses, names the file, writes nothing |
| A part without `time_spent_reading` | "All 2,161 sessions carry a usable number" for 4,322 sessions | "All 2,161 checked sessions ... a further 2,161 are in files that do not carry the column" |
| One unclosed quote at line 200 | 199 of 4,233 sessions, 1 row reported skipped, exit 0 | stops before writing, reporting the lines swallowed |
| `story_id` empty on 554 rows | 0 rows with no story identifier, 802 texts for 800 | 554 counted, 800 texts |
| Semicolon-separated with decimal commas | every reading time "not a number" | read as numbers, decimal mark recorded |
| Age band written `age 7 - 8` | those 1,641 sessions drop out of Part 2 | included, and the label recorded |
| A folder holding a duplicate copy and a README.txt | counts the export twice and the readme as a session | duplicate detected by checksum, .txt left alone |
| `--manifest-from` | overwrites the manifest it should be compared with | writes a separate file, and rebuilds the 7 August output unchanged |
| 259,280 rows | 27.0 seconds | 25.8 seconds, identical figures |
