"""Check that every citation key in the Quarto documents is in their bibliography.

    python tools/check_citations.py

Run from anywhere inside the repository. Quarto renders a citation whose key is not
in the bibliography as a bold "?key" and only warns, so a mistyped or deleted key
can reach a rendered draft unnoticed. This script reads each document listed in
DOCUMENTS, takes the bibliography its YAML header names, and fails on any key the
document cites that the bibliography does not hold. Cross-references (@fig-, @tbl-,
@sec- and the like), e-mail addresses and anything inside code are not citations
and are skipped. The poster's evidence map cites by key from data/evidence.csv, so
those keys are checked against the poster's bibliography too.

Exit status 1 if any key is missing, 0 otherwise. Standard library only.
"""
import csv
import os
import re
import subprocess
import sys

DOCUMENTS = [
    "preregistration/preregistration.qmd",
    "preregistration/supplementary.qmd",
    "poster/poster.qmd",
]
# Keys cited from a data file rather than the document's text.
KEY_FILES = {"poster/poster.qmd": [("poster/data/evidence.csv", "bibkey")]}

CROSSREF = re.compile(r"^(fig|tbl|sec|eq|lst|thm|lem|cor|prp|cnj|def|exm|exr|rem|apx)-")
# Pandoc's citation key: a letter, digit or underscore, then key characters, with
# internal punctuation allowed only when followed by another key character. The
# lookbehind skips e-mail addresses but not "[-@key]", which suppresses the author.
CITE = re.compile(r"(?<![\w.%+])@\{?([A-Za-z0-9_](?:[A-Za-z0-9_]|[:.#$%&+?<>~/-](?=[A-Za-z0-9_]))*)")
FENCE = re.compile(r"^ {0,3}(```|~~~).*?^ {0,3}\1[^\n]*$", re.M | re.S)
CODE_SPAN = re.compile(r"(`+)(?:(?!\1).)+?\1", re.S)
BIB_KEY = re.compile(r"^\s*@[A-Za-z]+\s*\{\s*([^,\s]+)\s*,", re.M)


def front_matter(text):
    m = re.match(r"---\r?\n(.*?)\r?\n---\r?\n", text, re.S)
    return (m.group(1), text[m.end():]) if m else ("", text)


def bibliographies(yaml_text):
    """The bibliography paths named in a YAML header, as a single value or a list."""
    m = re.search(r"^bibliography:[ \t]*(.*)$", yaml_text, re.M)
    if not m:
        return []
    value = m.group(1).strip()
    if value:
        items = [value]
    else:
        rest = yaml_text[m.end():]
        items = re.findall(r"^[ \t]+-[ \t]+(.+)$", rest.split("\n\n")[0], re.M)
    return [i.strip().strip("\"'") for i in items]


def main():
    root = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True,
                          text=True, check=True).stdout.strip()
    os.chdir(root)
    problems = 0
    for doc in DOCUMENTS:
        with open(doc, encoding="utf-8") as fh:
            yaml_text, body = front_matter(fh.read())
        bibs = bibliographies(yaml_text)
        if not bibs:
            print(f"MISSING  {doc}: its YAML header names no bibliography")
            problems += 1
            continue
        keys = set()
        for bib in bibs:
            path = os.path.join(os.path.dirname(doc), bib)
            with open(path, encoding="utf-8") as fh:
                keys |= set(BIB_KEY.findall(fh.read()))
        body = FENCE.sub("", body)
        body = CODE_SPAN.sub("", body)
        cited = {k for k in CITE.findall(body) if not CROSSREF.match(k)}
        # nocite in the YAML header cites without printing a reference in the text.
        cited |= {k for k in CITE.findall(yaml_text) if not CROSSREF.match(k) and k != "*"}
        for data_file, column in KEY_FILES.get(doc, []):
            with open(data_file, encoding="utf-8", newline="") as fh:
                cited |= {row[column] for row in csv.DictReader(fh) if row[column]}
        missing = sorted(cited - keys)
        for k in missing:
            print(f"MISSING  {doc}: @{k} is not in {', '.join(bibs)}")
        problems += len(missing)
        print(f"{doc}: {len(cited)} keys cited, {len(keys)} in the bibliography, "
              f"{len(missing)} missing")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
