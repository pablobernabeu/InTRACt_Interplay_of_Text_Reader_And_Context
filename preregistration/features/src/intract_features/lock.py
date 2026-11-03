"""The catalogue lock: no stage reads the Let's Story story texts before in-principle acceptance.

Data provenance, sequestration and outcome blindness (preregistration.qmd): "No linguistic feature
registered here has been computed on the story texts, and none will be before in-principle
acceptance." The lock enforces that commitment in code. A whole-file checksum alone is bypassed by any
decompressed, subset or re-encoded copy, and a flag file that anyone can create is no record of
acceptance (scout critique, item 12), so until it is unlocked the lock refuses:

(a) an input file that lies inside a protected directory (story_texts/data and the git-ignored
    delivery, Oxford-40k-stories), or whose SHA-256, as stored or decompressed, is any checksum that
    a manifest in [lock] manifests records. Only the checksums are read from those files. The list
    covers every publication of the story texts so far, and the next one:
    - story_texts/data/manifest.json and extraction_record.json, which record the current
      publication and will record any later one;
    - config/lock/published_2026-10-18.json, the checksums of the English table published on
      18 October 2026 (commit 03413a4), which holds the 1 October viewer's texts with their page
      markers: the table compressed and uncompressed, the anomalies list, the extraction record and
      the viewer's 83 data files;
    - config/lock/published_2026-10-27.json, the checksums of the 21 tables published on 27 October
      2026 (commit 5227d8b) in the zip delivery's form, with the zip files and the identifier map.
    The frozen records are written from the repository's history by `lock_build checksums`, so the
    lock keeps refusing a publication's files after later manifests replace its own.
(b) any document one of whose readings has a fingerprint listed in a fingerprint file, config/
    catalogue_fingerprints_<label>.txt, which `lock_build fingerprints` writes from published tables:
    one per language from the current tables, and en-us-2026-10-18 from the English table of
    18 October, read from the repository's history. Every such file present is read, whatever the
    run's language, so a table relabelled with another language is refused too. [lock]
    required_fingerprints names the files whose absence stops the run, so that a lost or unsynced
    file cannot switch this check off.

The fingerprint (fingerprint()) is the first 16 hexadecimal digits of the SHA-256 of a text's
White_Space tokens joined by one space, after the registered normalisation of each page. It is
unchanged by re-encoding, re-quoting, changed line endings, extra whitespace or a different page
split at whitespace, and a subset of a table is caught text by text. A document is checked under
several readings of its lines (text_fingerprints()): its pages as split; its title line and pages
together, for a copy that lost its title line; its pages after the first, for a copy that gained a
header line; and, where the build script's page markers occur, the same three with the markers
removed, which turns a text of the viewer's form into the tokens of the zip form. A fingerprint file
lists each text's pages and, for a text with page markers, its marker-free readings
(listed_fingerprints()). A copied fragment of a text, or a subset of its pages, is not caught; the
lock guards against accidents, not against deliberate evasion.

Unlocking needs a record of in-principle acceptance whose SHA-256 equals the value in
config/ipa_record.sha256. Under [lock] ipa_commit_check = "git" that file must also be committed,
tracked by git with no change since HEAD, so an uncommitted local file cannot unlock. The file does
not exist before acceptance, so the lock holds. The record is found at the path in the environment
variable INTRACT_IPA_RECORD or, failing that, at [lock] ipa_record in config/stages/documents.toml.

The lock fails closed: a manifest that cannot be read, a missing required fingerprint file, a
malformed fingerprint file or a malformed committed checksum stops the run instead of letting it
proceed unchecked.
"""

from __future__ import annotations

import hashlib
import json
import lzma
import os
import re
import subprocess
import sys
from array import array
from bisect import bisect_left
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from intract_features.io.catalogue import PAGE_RE
from intract_features.records import sha256_file
from intract_features.text.normalise import normalise
from intract_features.text.words import whitespace_tokens

# The repository's config/ directory, which cli.py also defaults to (src/intract_features/lock.py
# -> features/config). Relative paths in the [lock] settings resolve against the config directory.
DEFAULT_CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"
ENV_IPA_RECORD = "INTRACT_IPA_RECORD"
FINGERPRINT_VERSION = "v1"
FINGERPRINT_HEX_DIGITS = 16
COMMIT_CHECKS = ("git", "none")

# The readings text_fingerprints() returns; a fingerprint file lists LISTED_READINGS of each text.
READINGS = ("pages", "with_title_line", "without_first_page")
UNMARKED = "unmarked_"
LISTED_READINGS = ("pages", UNMARKED + "pages", UNMARKED + "with_title_line")

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_FINGERPRINT_RE = re.compile(rf"^[0-9a-f]{{{FINGERPRINT_HEX_DIGITS}}}$")


class LockError(RuntimeError):
    """The lock cannot be evaluated, so the run stops (the lock fails closed)."""


class CatalogueLocked(LockError):
    """An input or a document from the catalogue was refused before in-principle acceptance."""


def _tokens(line: str) -> list[str]:
    text = normalise(line)
    return [text[s:e] for s, e in whitespace_tokens(text)]


def _digest(tokens: Sequence[str]) -> str:
    return hashlib.sha256(" ".join(tokens).encode("utf-8")).hexdigest()[:FINGERPRINT_HEX_DIGITS]


def fingerprint(pages: Iterable[str]) -> str:
    """The lock's fingerprint of a text given its pages as delivered (version v1).

    Each page is normalised with the registered, configuration-independent rule (text/normalise.py),
    the White_Space tokens of all pages are joined with one space, and the first 16 hexadecimal
    digits of the SHA-256 of that string's UTF-8 bytes are the fingerprint. A text without a token has
    the fingerprint of the empty string, which identifies no story and is never listed or checked.
    """
    return _digest([t for page in pages for t in _tokens(page)])


EMPTY_FINGERPRINT = fingerprint([])


def text_fingerprints(title_line: str, pages: Sequence[str], *, min_tokens: int = 0) -> dict[str, str]:
    """The fingerprints of a text under each reading of its lines, by reading's name.

    "pages" is fingerprint(pages), the text as split into title line and pages. "with_title_line"
    reads the title line as a page too, which is what a copy that lost its title line gives;
    "without_first_page" drops the first page, which is what a copy that gained a header line gives.
    If a line holds a page marker of the data controller's build script (io.catalogue.PAGE_RE), the
    three readings are repeated with every marker removed, under names starting "unmarked_": a text
    in the 1 October viewer's form then gives the tokens of the zip form. A reading without tokens is
    left out, and a reading other than "pages" also when it has fewer than `min_tokens` tokens, so
    that a short remainder cannot match a short catalogue text by chance.
    """
    lines = [title_line, *pages]
    variants = [("", lines)]
    if any(PAGE_RE.search(line) for line in lines):
        variants.append((UNMARKED, [PAGE_RE.sub(" ", line) for line in lines]))
    found: dict[str, str] = {}
    for prefix, variant in variants:
        title_tokens = _tokens(variant[0])
        page_tokens = [_tokens(p) for p in variant[1:]]
        flat = [t for page in page_tokens for t in page]
        readings = {"pages": flat, "with_title_line": title_tokens + flat,
                    "without_first_page": [t for page in page_tokens[1:] for t in page]}
        for name in READINGS:
            tokens = readings[name]
            if not tokens or ((prefix or name != "pages") and len(tokens) < min_tokens):
                continue
            found[prefix + name] = _digest(tokens)
    return found


def listed_fingerprints(title_line: str, pages: Sequence[str]) -> set[str]:
    """The fingerprints a fingerprint file lists for one catalogue text (LISTED_READINGS).

    A text's pages, and, when it carries page markers, its pages and its title line and pages with
    the markers removed, so that a zip-form copy of a text published only in the viewer's form is
    caught as well as a copy in its own form.
    """
    readings = text_fingerprints(title_line, pages)
    return {readings[name] for name in LISTED_READINGS if name in readings}


def recorded_checksum_entries(obj: object) -> list[tuple[str, str]]:
    """Every SHA-256 a JSON value records, with its path (for example "languages/en-us/sha256").

    A checksum is the value of any key ending in "sha256" (case ignored) that holds 64 hexadecimal
    digits. The order is deterministic: a value's own checksums before those nested deeper.
    """
    found: list[tuple[str, str]] = []
    stack: list[tuple[str, object]] = [("", obj)]
    while stack:
        path, item = stack.pop()
        if isinstance(item, Mapping):
            children = [(str(k), v) for k, v in item.items()]
        elif isinstance(item, list):
            children = [(str(i), v) for i, v in enumerate(item)]
        else:
            continue
        deeper = []
        for key, value in children:
            where = f"{path}/{key}" if path else key
            if isinstance(item, Mapping) and isinstance(value, str) and key.lower().endswith("sha256") \
                    and _SHA256_RE.match(value.strip().lower()):
                found.append((where, value.strip().lower()))
            else:
                deeper.append((where, value))
        stack.extend(reversed(deeper))
    return found


def recorded_checksums(obj: object) -> set[str]:
    """Every SHA-256 a JSON value records (recorded_checksum_entries without the paths)."""
    return {value for _, value in recorded_checksum_entries(obj)}


def read_fingerprints(path: Path) -> array:
    """The fingerprints of a fingerprint file as a sorted array of unsigned 64-bit integers.

    Lines starting with "#" and blank lines are skipped. Every other line must be one fingerprint,
    in strictly increasing order, so a damaged or hand-edited file stops the run.
    """
    values = array("Q")
    previous = -1
    with open(path, encoding="utf-8") as fh:
        for n, line in enumerate(fh, 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if not _FINGERPRINT_RE.match(line):
                raise LockError(f"{Path(path).name}, line {n}: {line!r} is not a fingerprint")
            value = int(line, 16)
            if value <= previous:
                raise LockError(f"{Path(path).name}, line {n}: fingerprints must be sorted and unique")
            values.append(value)
            previous = value
    return values


def committed_checksum(path: Path) -> str | None:
    """The SHA-256 in config/ipa_record.sha256, or None while that file does not exist.

    The first line that is neither blank nor a comment must start with the 64 hexadecimal digits
    (sha256sum's format, a file name after them allowed); anything else stops the run.
    """
    path = Path(path)
    if not path.exists():
        return None
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        value = line.split()[0].lower()
        if not _SHA256_RE.match(value):
            raise LockError(f"{path.name}: {value!r} is not a SHA-256")
        return value
    raise LockError(f"{path.name} holds no checksum")


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess | None:
    try:
        return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None


def git_commit_of(path: Path) -> tuple[str | None, str]:
    """(commit, "") if git tracks the file with no change since HEAD, else (None, the reason).

    The commit is the last one that touched the file. Any failure, git missing or the folder outside
    a repository included, gives None, so the caller stays locked.
    """
    path = Path(path).resolve()
    tracked = _git(path.parent, "ls-files", "--error-unmatch", "--", path.name)
    if tracked is None:
        return None, "git cannot be run"
    if tracked.returncode != 0:
        return None, f"git does not track {path.name} (or the folder is not in a repository)"
    clean = _git(path.parent, "diff", "--quiet", "HEAD", "--", path.name)
    if clean is None or clean.returncode != 0:
        return None, f"{path.name} differs from HEAD or HEAD cannot be read"
    log = _git(path.parent, "log", "-1", "--format=%H", "--", path.name)
    commit = log.stdout.strip() if log is not None and log.returncode == 0 else ""
    if not _SHA256_RE.match(commit) and not re.fullmatch(r"[0-9a-f]{40}", commit):
        return None, f"no commit records {path.name}"
    return commit, ""


def content_sha256(path: Path, chunk: int = 1 << 20) -> str:
    """The SHA-256 of a file's content: decompressed for .xz, the bytes themselves otherwise."""
    path = Path(path)
    if path.name.lower().endswith(".xz"):
        h = hashlib.sha256()
        with lzma.open(path, "rb") as fh:
            for block in iter(lambda: fh.read(chunk), b""):
                h.update(block)
        return h.hexdigest()
    return sha256_file(path)


def _resolve(config_dir: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else Path(config_dir) / path


def _inside(path: Path, root: Path) -> bool:
    try:
        return path.resolve().is_relative_to(root.resolve())
    except OSError:
        return False


@dataclass
class CatalogueLock:
    """The lock's state for one run: whether it is unlocked and, if not, what it refuses."""

    unlocked: bool
    checksums: frozenset[str] = frozenset()
    fingerprint_files: list[tuple[str, array]] = field(default_factory=list)
    protected_dirs: tuple[Path, ...] = ()
    min_tokens: int = 20
    record: dict = field(default_factory=dict)

    @classmethod
    def load(cls, config_dir: Path, settings: Mapping, environ: Mapping[str, str] | None = None) -> CatalogueLock:
        """Evaluate the lock from the [lock] settings of config/stages/documents.toml.

        Keys: manifests and protected_dirs (lists of paths), fingerprints (a glob in the config
        directory holding one "*"), required_fingerprints (labels the "*" must take), min_variant_tokens,
        ipa_checksum (the committed file's name), ipa_record (a path, "" for none), ipa_commit_check
        ("git" or "none") and on_missing_manifest ("refuse" or "warn"). Relative paths resolve against
        config_dir. A key left out takes the strict value: no file required, 20 tokens, "git", "refuse".
        """
        environ = os.environ if environ is None else environ
        config_dir = Path(config_dir)
        commit_check = settings.get("ipa_commit_check", "git")
        if commit_check not in COMMIT_CHECKS:
            raise LockError(f"ipa_commit_check must be one of {COMMIT_CHECKS}, not {commit_check!r}")
        checksum_path = _resolve(config_dir, settings["ipa_checksum"])
        committed = committed_checksum(checksum_path)
        record_setting = environ.get(ENV_IPA_RECORD) or settings.get("ipa_record", "")
        record_path = _resolve(config_dir, record_setting) if record_setting else None
        record_sha = sha256_file(record_path) if record_path is not None and record_path.is_file() else None
        matched = committed is not None and record_sha == committed
        commit = None
        if matched and commit_check == "git":
            commit, reason = git_commit_of(checksum_path)
            if commit is None:
                print(f"catalogue lock: the IPA record matches {checksum_path.name}, but {reason}; the checksum "
                      f"counts only once committed ([lock] ipa_commit_check = 'git'), so the lock holds",
                      file=sys.stderr)
        unlocked = matched and (commit_check == "none" or commit is not None)
        record: dict = {"state": "unlocked" if unlocked else "locked",
                        "ipa_checksum_file_present": committed is not None, "ipa_commit_check": commit_check,
                        "ipa_checksum_git_commit": commit, "ipa_record_sha256": record_sha, "manifests": [],
                        "fingerprint_files": [],
                        "required_fingerprints": [str(x) for x in settings.get("required_fingerprints", [])],
                        "protected_dirs": list(settings.get("protected_dirs", []))}
        if committed is not None and record_sha is not None and not matched:
            print(f"catalogue lock: the IPA record's SHA-256 {record_sha} differs from the committed "
                  f"{committed}; the lock holds", file=sys.stderr)
        if unlocked:
            print(f"catalogue lock: unlocked by the IPA record with SHA-256 {record_sha}", file=sys.stderr)
            return cls(unlocked=True, record=record)

        on_missing = settings.get("on_missing_manifest", "refuse")
        if on_missing not in ("refuse", "warn"):
            raise LockError(f"on_missing_manifest must be 'refuse' or 'warn', not {on_missing!r}")
        manifests = list(settings.get("manifests", []))
        if not manifests and on_missing == "refuse":
            raise LockError("the lock names no manifest, so it cannot tell the catalogue's files apart")
        checksums: set[str] = set()
        for value in manifests:
            path = _resolve(config_dir, value)
            try:
                found = recorded_checksums(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, ValueError) as e:
                if on_missing == "refuse":
                    raise LockError(f"cannot read the protected manifest {value}: {e}. Run from the "
                                    f"repository checkout, or point [lock] manifests at it") from e
                print(f"catalogue lock: WARNING, manifest {value} unreadable ({e}); not checked", file=sys.stderr)
                continue
            if not found and on_missing == "refuse":
                raise LockError(f"the protected manifest {value} records no SHA-256")
            checksums |= found
            record["manifests"].append({"file": value, "sha256": sha256_file(path), "checksums": len(found)})

        pattern = settings["fingerprints"]
        required = record["required_fingerprints"]
        if required and pattern.count("*") != 1:
            raise LockError(f"[lock] fingerprints {pattern!r} must hold one '*' to name the required files")
        for label in required:
            expected = config_dir / pattern.replace("*", str(label))
            if not expected.is_file():
                raise LockError(f"the fingerprint file {expected.name} is required ([lock] required_fingerprints) "
                                f"but missing from {config_dir}. Restore it, or rebuild it with lock_build")
        files = []
        for path in sorted(config_dir.glob(pattern)):
            values = read_fingerprints(path)
            files.append((path.name, values))
            record["fingerprint_files"].append({"file": path.name, "sha256": sha256_file(path),
                                                "fingerprints": len(values)})
        dirs = tuple(_resolve(config_dir, d) for d in settings.get("protected_dirs", []))
        min_tokens = int(settings.get("min_variant_tokens", 20))
        if min_tokens < 1:
            raise LockError("min_variant_tokens must be at least 1")
        record["min_variant_tokens"] = min_tokens
        return cls(unlocked=False, checksums=frozenset(checksums), fingerprint_files=files, protected_dirs=dirs,
                   min_tokens=min_tokens, record=record)

    def check_input(self, path: Path) -> dict:
        """Refuse a protected input file; return its name, size and checksums for the run manifest."""
        path = Path(path)
        if not path.is_file():
            raise FileNotFoundError(f"input {path} is not a file")
        if not self.unlocked:
            for root in self.protected_dirs:
                if _inside(path, root):
                    raise CatalogueLocked(f"{path.name} lies inside the protected directory {root.name}; the "
                                          f"story texts are read only after in-principle acceptance")
        stored = sha256_file(path)
        content = content_sha256(path) if path.name.lower().endswith(".xz") else stored
        if not self.unlocked and ({stored, content} & self.checksums):
            raise CatalogueLocked(f"{path.name} has the checksum of a catalogue file; the story texts are read "
                                  f"only after in-principle acceptance")
        return {"name": path.name, "bytes": path.stat().st_size, "sha256": stored, "content_sha256": content}

    def is_listed(self, fp: str) -> bool:
        """True if a fingerprint appears in any fingerprint file."""
        value = int(fp, 16)
        for _, values in self.fingerprint_files:
            i = bisect_left(values, value)
            if i < len(values) and values[i] == value:
                return True
        return False

    def check_document(self, story_id: str, fp: str) -> None:
        """Refuse a document whose fingerprint a fingerprint file lists (nothing is refused once unlocked)."""
        if self.unlocked or fp == EMPTY_FINGERPRINT:
            return
        if self.is_listed(fp):
            raise CatalogueLocked(f"story {story_id!r} has the fingerprint of a catalogue text; the story texts "
                                  f"are read only after in-principle acceptance")

    def check_text(self, story_id: str, title_line: str, pages: Sequence[str]) -> str:
        """Refuse a document any of whose readings (text_fingerprints) is listed; return fingerprint(pages).

        Once unlocked, nothing is refused and only fingerprint(pages) is computed.
        """
        if self.unlocked:
            return fingerprint(pages)
        readings = text_fingerprints(title_line, pages, min_tokens=self.min_tokens)
        for name, fp in readings.items():
            if self.is_listed(fp):
                raise CatalogueLocked(f"story {story_id!r} matches a catalogue text (reading {name!r}); the story "
                                      f"texts are read only after in-principle acceptance")
        return readings.get("pages", EMPTY_FINGERPRINT)
