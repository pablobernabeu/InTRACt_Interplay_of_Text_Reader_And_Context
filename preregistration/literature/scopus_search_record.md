# Scopus search record for the InTRACt literature counts

Run on 26 August 2026 with scopusflow 0.4.0 against the Elsevier Scopus Search API.
Publication years 2018 to 2026. Field tag TITLE-ABS-KEY throughout. No document type,
language or subject-area limit was applied. Counts are the totals the API reported,
not row counts from a harvest: nothing was downloaded.

Reporting follows PRISMA-S (Rethlefsen et al., 2021, doi:10.1186/s13643-020-01542-z)
for the items a count-only search can supply: database name, full search strategies,
limits and restrictions, and date of search. The remaining items belong to the
systematic review that accompanies this protocol, not to this search.

## Concept sets and their intersections

| Set | Records | Query |
|---|---:|---|
| Children's reading | 3,701 | `TITLE-ABS-KEY("reading comprehension" OR "text comprehension" OR "passage comprehension" OR "reading fluency" OR "reading time") AND TITLE-ABS-KEY(child OR children OR pupils OR "primary school" OR "elementary school")` |
| Computational text features | 6,592 | `TITLE-ABS-KEY("word frequency" OR "lexical diversity" OR "syntactic complexity" OR "dependency distance" OR "text cohesion" OR "text coherence" OR readability OR surprisal OR "age of acquisition" OR concreteness) AND TITLE-ABS-KEY(computational OR corpus OR "natural language processing" OR "language model" OR psycholinguistic)` |
| Platform log data | 133,132 | `TITLE-ABS-KEY("log data" OR logfile OR "log file" OR "trace data" OR "learning analytics" OR "app data" OR "mobile application" OR "digital platform" OR telemetry OR "behavioural logs" OR "behavioral logs")` |
| Reading × Text features | 17 | `(TITLE-ABS-KEY("reading comprehension" OR "text comprehension" OR "passage comprehension" OR "reading fluency" OR "reading time") AND TITLE-ABS-KEY(child OR children OR pupils OR "primary school" OR "elementary school")) AND (TITLE-ABS-KEY("word frequency" OR "lexical diversity" OR "syntactic complexity" OR "dependency distance" OR "text cohesion" OR "text coherence" OR readability OR surprisal OR "age of acquisition" OR concreteness) AND TITLE-ABS-KEY(computational OR corpus OR "natural language processing" OR "language model" OR psycholinguistic))` |
| Reading × Log data | 28 | `(TITLE-ABS-KEY("reading comprehension" OR "text comprehension" OR "passage comprehension" OR "reading fluency" OR "reading time") AND TITLE-ABS-KEY(child OR children OR pupils OR "primary school" OR "elementary school")) AND (TITLE-ABS-KEY("log data" OR logfile OR "log file" OR "trace data" OR "learning analytics" OR "app data" OR "mobile application" OR "digital platform" OR telemetry OR "behavioural logs" OR "behavioral logs"))` |
| Text features × Log data | 45 | `(TITLE-ABS-KEY("word frequency" OR "lexical diversity" OR "syntactic complexity" OR "dependency distance" OR "text cohesion" OR "text coherence" OR readability OR surprisal OR "age of acquisition" OR concreteness) AND TITLE-ABS-KEY(computational OR corpus OR "natural language processing" OR "language model" OR psycholinguistic)) AND (TITLE-ABS-KEY("log data" OR logfile OR "log file" OR "trace data" OR "learning analytics" OR "app data" OR "mobile application" OR "digital platform" OR telemetry OR "behavioural logs" OR "behavioral logs"))` |
| Reading × Text features × Log data | 0 | `(TITLE-ABS-KEY("reading comprehension" OR "text comprehension" OR "passage comprehension" OR "reading fluency" OR "reading time") AND TITLE-ABS-KEY(child OR children OR pupils OR "primary school" OR "elementary school")) AND (TITLE-ABS-KEY("word frequency" OR "lexical diversity" OR "syntactic complexity" OR "dependency distance" OR "text cohesion" OR "text coherence" OR readability OR surprisal OR "age of acquisition" OR concreteness) AND TITLE-ABS-KEY(computational OR corpus OR "natural language processing" OR "language model" OR psycholinguistic)) AND (TITLE-ABS-KEY("log data" OR logfile OR "log file" OR "trace data" OR "learning analytics" OR "app data" OR "mobile application" OR "digital platform" OR telemetry OR "behavioural logs" OR "behavioral logs"))` |

## Publication trend, by year

| Year | Children's reading | with narration | with apps or e-books | with AI-generated text |
|---:|---:|---:|---:|---:|
| 2018 | 348 | 6 | 2 | 0 |
| 2019 | 324 | 5 | 4 | 0 |
| 2020 | 374 | 4 | 5 | 0 |
| 2021 | 375 | 4 | 2 | 0 |
| 2022 | 352 | 7 | 2 | 0 |
| 2023 | 363 | 6 | 3 | 0 |
| 2024 | 400 | 8 | 2 | 2 |
| 2025 | 490 | 16 | 6 | 6 |
| 2026 | 337 | 5 | 1 | 4 |
