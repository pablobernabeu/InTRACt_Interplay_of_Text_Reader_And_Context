# Scopus search record for the InTRACt poster

Run on 14 October 2026 with scopusflow 0.4.0 against the Elsevier Scopus Search API.
Publication years 2010 to 2025. Field tag TITLE-ABS-KEY on every concept.
Document types limited to articles, reviews, conference papers and book chapters.
No language or subject-area limit. Counts are the totals the API reported, not
screened studies: nothing was downloaded, so the counts include false positives.

Reporting follows PRISMA-S (Rethlefsen et al., 2021, doi:10.1186/s13643-020-01542-z)
for the items a count-only search can supply: database, full search strategies,
limits and restrictions, and date of search.

## Concepts

- **Children's reading development**: `TITLE-ABS-KEY(("reading comprehension" OR "reading fluency" OR "reading skill*" OR "reading development" OR "reading achievement" OR "reading ability" OR "reading abilities" OR "learning to read" OR "early literacy" OR "emergent literacy" OR "story comprehension" OR "word reading" OR "beginning reader*" OR "struggling reader*") AND (child* OR pupil* OR "primary school*" OR "elementary school*" OR kindergarten* OR preschool* OR "first grade*" OR "young reader*"))`
- **Digital technology**: `TITLE-ABS-KEY((digital OR "e-book*" OR ebook* OR "electronic book*" OR "electronic storybook*" OR "e-reader*" OR tablet* OR ipad* OR touchscreen* OR "touch screen*" OR smartphone* OR "mobile app*" OR "educational app*" OR "reading app*" OR "storybook app*" OR app OR apps OR "computer-assisted" OR "computer-based" OR "educational technolog*" OR "technology-enhanced" OR multimedia OR "on screen" OR "on-screen" OR "screen time" OR "screen use" OR "screen-based" OR "artificial intelligence" OR chatbot* OR "conversational agent*" OR "text-to-speech" OR "speech synthesis" OR "intelligent tutor*" OR "online reading" OR hypertext))`
- **Document-type limit**: `(DOCTYPE(ar) OR DOCTYPE(re) OR DOCTYPE(cp) OR DOCTYPE(ch))`

## Foci within children's digital reading

| Focus | Records | Query |
|---|---:|---|
| Screen time and media use | 45 | `TITLE-ABS-KEY(("screen time" OR "screen use" OR "screen exposure" OR "media use" OR "media exposure" OR "digital media use" OR "technology use" OR "device use"))` |
| Screen versus paper | 128 | `TITLE-ABS-KEY(("paper-based" OR "on paper" OR "printed book*" OR "print book*" OR "paper book*" OR "printed text*" OR "print-based" OR "print versus" OR "paper versus" OR "versus print" OR "versus paper" OR "reading medium" OR "reading media" OR "medium effect*" OR "mode effect*" OR "screen inferiority"))` |
| Multimedia and games | 264 | `TITLE-ABS-KEY((multimedia OR animat* OR hotspot* OR "interactive feature*" OR "enhanced e-book*" OR "enhanced ebook*" OR "digital enhancement*" OR gamif* OR "game-based" OR "educational game*" OR "video game*"))` |
| Narration and text-to-speech | 42 | `TITLE-ABS-KEY(("text-to-speech" OR "speech synthesis" OR "synthetic speech" OR "audio narration" OR narrated OR "read-aloud tool*" OR "read-aloud feature*" OR "read-aloud function*" OR audiobook* OR "audio book*" OR "reading while listening" OR "reading-while-listening" OR "audio support" OR "audio-assisted"))` |
| AI and chatbots | 115 | `TITLE-ABS-KEY(("artificial intelligence" OR "generative AI" OR "large language model*" OR ChatGPT OR chatbot* OR "conversational agent*" OR "AI-generated" OR "intelligent tutor*" OR "machine-generated"))` |
| Language of the text | 35 | `TITLE-ABS-KEY(("text complexity" OR "text difficulty" OR readability OR "linguistic feature*" OR "linguistic complexity" OR "linguistic characteristic*" OR "syntactic complexity" OR "sentence complexity" OR "word frequency" OR "lexical difficulty" OR "lexical complexity" OR cohesion OR "text characteristic*" OR "text feature*" OR "text propert*" OR "lexical feature*"))` |
| Log data and learning analytics | 24 | `TITLE-ABS-KEY(("log data" OR "log file*" OR logfile* OR "learning analytics" OR "trace data" OR "usage data" OR clickstream* OR "process data" OR telemetry OR "big data" OR "app data" OR "behavioural logs" OR "behavioral logs" OR "data mining"))` |

## Totals

- Children's reading development: 14,193 records
- of which digital technology: 1,536 records
- Digital reading: 1,536 records
- Language of the text: 109,793 records
- Log data: 491,546 records
- Digital reading × Language of the text: 35 records
- Digital reading × Log data: 24 records
- Digital reading × Language of the text × Log data: 0 records
