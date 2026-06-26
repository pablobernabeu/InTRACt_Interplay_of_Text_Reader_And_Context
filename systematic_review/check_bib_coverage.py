#!/usr/bin/env python3
"""Keep the systematic review's verified spreadsheet in step with the preregistration bibliography.

Every paper included in the systematic review should also appear in the
preregistration's reference library, and each row of the verified extraction
spreadsheet should carry the BibLaTeX citation key of its paper so the two
artifacts can be cross-referenced.

This tool does both jobs from a single source of truth (the ``.bib`` file):

* ``--check`` (default) verifies that every DOI in the spreadsheet is present in
  the bibliography and that the spreadsheet's ``citation_key`` column matches the
  key the bibliography would assign by DOI. Exits non-zero (for CI) on any gap.
* ``--write`` (re)derives the ``citation_key`` column from the bibliography by DOI
  and writes it back into the spreadsheet, inserted immediately after ``doi``.

Because the key is always derived from the bibliography by DOI, the column is
self-healing: if the Zotero-managed ``.bib`` is re-exported and a key changes,
re-running ``--write`` updates the column without manual edits.

Files (paths relative to the repository root):
    preregistration/InTRACt references.bib     the citation keys (source of truth)
    systematic_review/verified_extraction.csv   the verified review spreadsheet

Run from anywhere:
    python systematic_review/check_bib_coverage.py            # check (CI)
    python systematic_review/check_bib_coverage.py --write    # refresh citation_key
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BIB = REPO_ROOT / "preregistration" / "InTRACt references.bib"
SPREADSHEET = Path(__file__).resolve().parent / "verified_extraction.csv"

_DOI_PREFIXES = (
    "https://doi.org/",
    "http://doi.org/",
    "https://dx.doi.org/",
    "http://dx.doi.org/",
    "doi:",
)
_ENTRY = re.compile(r"@\w+\{([^,]+),(.*?)(?=\n@|\Z)", re.S)
_DOI_FIELD = re.compile(r"\bdoi\s*=\s*[{\"]([^}\"]+)[}\"]", re.I)


def normalize_doi(doi: str) -> str:
    """Bare, lower-cased DOI with any scheme/host prefix stripped."""
    doi = (doi or "").strip()
    for prefix in _DOI_PREFIXES:
        if doi.lower().startswith(prefix):
            doi = doi[len(prefix):]
            break
    return doi.strip().lower()


def load_bib_keys_by_doi(bib_path: Path) -> dict[str, str]:
    """Map every normalised DOI in the bibliography to its citation key."""
    text = bib_path.read_text(encoding="utf-8")
    by_doi: dict[str, str] = {}
    for key, body in _ENTRY.findall(text):
        match = _DOI_FIELD.search(body)
        if match:
            by_doi[normalize_doi(match.group(1))] = key.strip()
    return by_doi


def read_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        header = list(reader.fieldnames or [])
        return header, list(reader)


def header_with_citation_key(header: list[str]) -> list[str]:
    """Return the header with citation_key inserted just after doi (idempotent)."""
    cols = [c for c in header if c != "citation_key"]
    if "doi" in cols:
        cols.insert(cols.index("doi") + 1, "citation_key")
    else:
        cols.append("citation_key")
    return cols


def write_rows(path: Path, header: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=header, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({col: row.get(col, "") for col in header})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Refresh the citation_key column from the bibliography (default is check-only).",
    )
    args = parser.parse_args(argv)

    if not BIB.is_file():
        print(f"Bibliography not found: {BIB}")
        return 1
    if not SPREADSHEET.is_file():
        print(f"Verified spreadsheet not found: {SPREADSHEET}")
        return 1

    keys_by_doi = load_bib_keys_by_doi(BIB)
    header, rows = read_rows(SPREADSHEET)

    missing: list[str] = []   # DOIs absent from the bibliography
    no_doi: list[str] = []    # rows without a DOI (cannot be linked)
    stale: list[str] = []     # citation_key disagrees with the bibliography
    for row in rows:
        rid = (row.get("record_id") or "?").strip()
        doi = normalize_doi(row.get("doi", ""))
        if not doi:
            no_doi.append(rid)
            derived = ""
        else:
            derived = keys_by_doi.get(doi, "")
            if not derived:
                missing.append(f"record {rid}: {doi}")
        if (row.get("citation_key") or "").strip() != derived:
            stale.append(rid)
        row["citation_key"] = derived

    out_header = header_with_citation_key(header)

    if args.write:
        write_rows(SPREADSHEET, out_header, rows)
        linked = sum(1 for r in rows if r.get("citation_key"))
        print(f"Wrote citation_key for {linked}/{len(rows)} row(s) -> {SPREADSHEET.name}")
        if no_doi:
            print(f"  {len(no_doi)} row(s) without a DOI (citation_key left blank): {no_doi}")
        if missing:
            print(f"  WARNING: {len(missing)} DOI(s) not in the bibliography:")
            for m in missing:
                print(f"    - {m}")
            return 1
        return 0

    # check mode
    ok = True
    if missing:
        ok = False
        print(f"FAIL: {len(missing)} review DOI(s) missing from {BIB.name}:")
        for m in missing:
            print(f"  - {m}")
    if "citation_key" not in header:
        ok = False
        print("FAIL: spreadsheet has no citation_key column; run with --write.")
    elif stale:
        ok = False
        print(f"FAIL: citation_key is stale for {len(stale)} row(s): {stale}. Run with --write.")
    if no_doi:
        print(f"NOTE: {len(no_doi)} row(s) without a DOI cannot be linked: {no_doi}")
    if ok:
        linked = sum(1 for r in rows if (r.get("citation_key") or "").strip())
        print(f"OK: all {len(rows) - len(no_doi)} DOI-bearing row(s) present in the bibliography; "
              f"{linked} linked to a citation key.")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
