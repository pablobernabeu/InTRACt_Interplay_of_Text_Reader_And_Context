# Systematic review — verified extraction

This directory holds the verified data table from the InTRACt systematic literature
review, alongside the preregistration it informs. The review itself (preliminary
screening logs, per-paper PDFs, batching and extraction tooling) is maintained in a
separate working repository; only the final verified spreadsheet and the small script
that keeps it consistent with the bibliography are mirrored here. Paper PDFs are not
redistributed.

## Files

- **`verified_extraction.csv`** — one row per included paper. Bibliographic fields
  (`title`, `authors`, `year`, `doi`) are reconciled against Crossref; the remaining
  columns record the coded study characteristics and the effect estimates extracted for
  each text-feature, narration, foreign-language, reading-rate and reading-frequency
  relation. The `citation_key` column gives the BibLaTeX key of the paper in
  `../preregistration/InTRACt references.bib`, so each coded study can be traced to its
  reference.
- **`check_bib_coverage.py`** — verifies that every DOI in the spreadsheet is present
  in the preregistration bibliography and that the `citation_key` column matches the key
  the bibliography assigns by DOI.

## Keeping the spreadsheet and bibliography in step

The `citation_key` column is always derived from the bibliography by DOI, so it is
self-healing: if the (Zotero-managed) `.bib` is re-exported and a key changes, rerunning
the script updates the column without manual edits.

```sh
python systematic_review/check_bib_coverage.py            # check coverage (used in CI)
python systematic_review/check_bib_coverage.py --write    # refresh the citation_key column
```

The check fails if any review DOI is missing from the bibliography, which flags a paper
that still needs adding to the reference library. The spreadsheet is a snapshot of an
ongoing review; to update it, re-export the collated verified extraction from the working
repository over `verified_extraction.csv` and rerun the script with `--write`.
