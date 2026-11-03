"""Predicted spoken duration per word, the quantity behind the Hypothesis 4 duration adjustment.

S3, predicted spoken duration row: "Predicted seconds, the rate per unit times the text's spoken units plus 0.55 s
per sentence end and 0.20 s per clause mark, divided by the words and log-transformed. The units are eSpeak NG
1.52.0 phones, through phonemizer 3.4.0, at 0.08 s each in the 13 languages written in Latin, Greek or Cyrillic
script." Materials: "One further text quantity serves Hypothesis 4 alone, a predicted spoken duration per word on a
log scale."

eSpeak NG and phonemizer are GPL-3.0. They are never imported into this package or vendored: `Phonemizer` runs
phonemizer's own command-line program (phonemizer.main) as a separate process and reads its output file.

Promoted from verify-narrdur/scripts/dur_constants_ts.py (the phonemizer settings, the phone count, the formula),
affect-narrativity-duration/scripts/fleurs_duration_benchmark.py (ipa_counts) and test_espeak.py (the version
check). Two rules are defaults pending the Feature Specification, each behind a switch: what counts as a clause mark
(gap G5; the default is comma, semicolon, colon and dash with their full-width forms) and what counts as a sentence
end (default: one per sentence of the registered segmentation; the benchmark counted runs of terminal marks).
"""

from __future__ import annotations

import math
import os
import re
import subprocess
import sys
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def count_phones(phonemized: str, word_separator: str) -> tuple[int, int]:
    """(phones, phonemized words) in one line of phonemizer output.

    dur_constants_ts.py: phones = [x for w in p.split("|") for x in w.split() if x], with phones separated by a
    space and words by " | ".
    """
    sep = word_separator.strip() or word_separator
    words = [w.split() for w in phonemized.split(sep)]
    return sum(len(w) for w in words), sum(1 for w in words if w)


def _between_digits(text: str, i: int) -> bool:
    return 0 < i < len(text) - 1 and text[i - 1].isdigit() and text[i + 1].isdigit()


@dataclass(frozen=True)
class PauseRules:
    """Which characters count as clause marks and sentence ends (gap G5 and the sentence-end switch)."""

    clause_marks: frozenset[str]
    clause_dashes: frozenset[str]
    ascii_double_hyphen: bool
    spaced_hyphen: bool
    skip_between_digits: bool
    terminal_marks: frozenset[str]

    @classmethod
    def from_config(cls, cfg: Mapping[str, Any]) -> PauseRules:
        """Build the rules from the [duration] table of config/stages/features_discourse.toml."""
        return cls(clause_marks=frozenset(cfg["clause_marks"]), clause_dashes=frozenset(cfg["clause_dashes"]),
                   ascii_double_hyphen=bool(cfg["ascii_double_hyphen_is_dash"]),
                   spaced_hyphen=bool(cfg["spaced_hyphen_is_dash"]),
                   skip_between_digits=bool(cfg["skip_between_digits"]),
                   terminal_marks=frozenset(cfg["terminal_marks"]))

    def clause_mark_count(self, text: str) -> int:
        """Clause marks in a text (PENDING gap G5).

        Each comma, semicolon or colon (or full-width form) counts once, except between two digits ("1,000",
        "10:30"). A run of dash characters counts once, as does a run of two or more ASCII hyphens or a hyphen
        standing alone between spaces; a hyphen inside a word ("well-known") is not a pause.
        """
        n = 0
        i = 0
        while i < len(text):
            c = text[i]
            if c in self.clause_marks:
                if not (self.skip_between_digits and _between_digits(text, i)):
                    n += 1
                i += 1
            elif c in self.clause_dashes:
                n += 1
                while i < len(text) and text[i] in self.clause_dashes:
                    i += 1
            elif c == "-":
                j = i
                while j < len(text) and text[j] == "-":
                    j += 1
                run = j - i
                before = text[i - 1] if i > 0 else " "
                after = text[j] if j < len(text) else " "
                if (run >= 2 and self.ascii_double_hyphen) or (
                        run == 1 and self.spaced_hyphen and before.isspace() and after.isspace()):
                    n += 1
                i = j
            else:
                i += 1
        return n

    def terminal_run_count(self, text: str) -> int:
        """Runs of terminal marks, each counted once (dur_constants_ts.py: re.findall(r"[.!?…]+", t))."""
        n = 0
        prev = False
        for c in text:
            cur = c in self.terminal_marks
            if cur and not prev:
                n += 1
            prev = cur
        return n


@dataclass(frozen=True)
class DurationConstants:
    """The registered constants (S3): seconds per phone, per sentence end and per clause mark."""

    seconds_per_unit: float
    seconds_per_sentence_end: float
    seconds_per_clause_mark: float

    def seconds(self, units: int, sentence_ends: int, clause_marks: int) -> float:
        """Predicted seconds of a text."""
        return (self.seconds_per_unit * units + self.seconds_per_sentence_end * sentence_ends
                + self.seconds_per_clause_mark * clause_marks)


def log_seconds_per_word(seconds: float, n_words: int) -> float | None:
    """log(seconds / words), the registered scale; None for a text without words or speech (undefined)."""
    if n_words <= 0 or seconds <= 0:
        return None
    return math.log(seconds / n_words)


class PhonemizerError(RuntimeError):
    """The external phonemizer program failed, or its versions differ from the registered pins."""


_PHONEMIZER_RE = re.compile(r"phonemizer-(\d+(?:\.\d+)*)")
_ESPEAK_RE = re.compile(r"espeak-ng-(\d+(?:\.\d+)*)")


def parse_versions(version_text: str) -> tuple[str | None, str | None]:
    """(phonemizer version, eSpeak NG version) from `phonemize --version` (phonemizer/version.py's format)."""
    p = _PHONEMIZER_RE.search(version_text)
    e = _ESPEAK_RE.search(version_text)
    return (p.group(1) if p else None), (e.group(1) if e else None)


def one_line(text: str) -> str:
    """The text with every whitespace run, line breaks included, collapsed to one space.

    phonemizer reads one utterance per line, so a text must occupy exactly one line of its input file.
    dur_constants_ts.py joined each story the same way (" ".join(s.split())).
    """
    return " ".join(text.split())


class Phonemizer:
    """phonemizer 3.4.0 with the eSpeak NG backend, run as a separate program.

    Settings follow dur_constants_ts.py, the benchmark that tested the registered constants' sensitivity: phones
    separated by a space, words by " | ", stripped, no stress marks, punctuation removed and language-switch flags
    removed.
    """

    def __init__(self, cfg: Mapping[str, Any], voice: str):
        self.cfg = cfg
        self.voice = voice
        cmd = list(cfg.get("command") or [])
        self.command = cmd if cmd else [sys.executable, "-I", "-m", "phonemizer.main"]
        self.timeout = float(cfg.get("timeout_seconds", 3600))

    def _env(self) -> dict[str, str]:
        env = dict(os.environ)
        data = self.cfg.get("espeak_data_path") or ""
        if data:
            env["ESPEAK_DATA_PATH"] = str(data)
        env.setdefault("PYTHONIOENCODING", "utf-8")
        return env

    def _library_args(self) -> list[str]:
        lib = self.cfg.get("espeak_library") or ""
        return ["--espeak-library", str(lib)] if lib else []

    def versions(self) -> tuple[str | None, str | None]:
        """Ask the program for its phonemizer and eSpeak NG versions."""
        proc = subprocess.run([*self.command, *self._library_args(), "--version"], capture_output=True,
                              text=True, encoding="utf-8", env=self._env(), timeout=self.timeout, check=False)
        if proc.returncode != 0:
            raise PhonemizerError(f"phonemizer --version failed ({proc.returncode}): {proc.stderr.strip()[:500]}")
        return parse_versions(proc.stdout)

    def check_pins(self) -> tuple[str, str]:
        """Verify the registered versions before any text is phonemized (DESIGN: a pin is verified before use)."""
        p, e = self.versions()
        want_p, want_e = str(self.cfg["phonemizer_version"]), str(self.cfg["espeak_ng_version"])
        if (p, e) != (want_p, want_e):
            msg = f"phonemizer {p} with eSpeak NG {e}, but the registered pins are {want_p} and {want_e}"
            if not self.cfg.get("allow_version_mismatch", False):
                raise PhonemizerError(msg)
        return p or "", e or ""

    def arguments(self, input_path: Path, output_path: Path) -> list[str]:
        """The command line for one batch."""
        c = self.cfg
        args = [*self.command, *self._library_args(), "-b", str(c["backend"]), "-l", self.voice,
                "-p", str(c["phone_separator"]), "-w", str(c["word_separator"]),
                "--language-switch", str(c["language_switch"]), "--preserve-empty-lines", "-j", "1", "-q"]
        if c["strip"]:
            args.append("--strip")
        if c["with_stress"]:
            args.append("--with-stress")
        if c["preserve_punctuation"]:
            args.append("--preserve-punctuation")
        return [*args, "-o", str(output_path), str(input_path)]

    def phonemize(self, texts: Sequence[str]) -> list[str]:
        """One phonemized line per text, in order."""
        if not texts:
            return []
        with tempfile.TemporaryDirectory(prefix="intract-phonemize-") as tmp:
            src, dst = Path(tmp) / "input.txt", Path(tmp) / "output.txt"
            with open(src, "w", encoding="utf-8", newline="\n") as fh:
                for t in texts:
                    fh.write(one_line(t) + "\n")
            proc = subprocess.run(self.arguments(src, dst), capture_output=True, text=True, encoding="utf-8",
                                  env=self._env(), timeout=self.timeout, check=False)
            if proc.returncode != 0:
                raise PhonemizerError(f"phonemizer failed ({proc.returncode}): {proc.stderr.strip()[:500]}")
            raw = dst.read_bytes().decode("utf-8")
        # phonemizer joins its lines with os.linesep through a text-mode file, which on Windows writes "\r\r\n";
        # phones never contain a carriage return, so dropping every one restores the lines on any platform.
        lines = raw.replace("\r", "").split("\n")
        if lines and lines[-1] == "":
            lines.pop()
        if len(lines) != len(texts):
            raise PhonemizerError(f"phonemizer returned {len(lines)} lines for {len(texts)} texts")
        return lines
