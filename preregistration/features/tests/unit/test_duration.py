"""Predicted spoken duration (features.duration): the formula, the pause counts and the external phonemizer call."""

import math
import os
import sys
import tomllib
from pathlib import Path

import pytest

from intract_features.features import duration as dur

CONFIG = Path(__file__).resolve().parents[2] / "config" / "stages" / "features_discourse.toml"

# A stand-in for phonemizer's command-line program: one output line per input line, each letter a "phone", words
# joined by " | ". It writes through a text-mode file joined with os.linesep, as phonemizer/main.py does.
FAKE = r'''
import os, sys
args = sys.argv[1:]
if "--version" in args:
    print("phonemizer-" + os.environ.get("FAKE_PHONEMIZER", "3.4.0"))
    print("available backends: espeak-ng-" + os.environ.get("FAKE_ESPEAK", "1.52.0") + ", espeak-mbrola")
    sys.exit(0)
if os.environ.get("FAKE_FAIL"):
    sys.exit(3)
out, src = args[args.index("-o") + 1], args[-1]
lines = []
for line in open(src, encoding="utf8").readlines():
    words = [" ".join(ch for ch in w if ch.isalpha()) for w in line.split()]
    lines.append(" | ".join(x for x in words if x))
if os.environ.get("FAKE_DROP"):
    lines = lines[:-1]
with open(out, "w", encoding="utf8") as fh:
    fh.write(os.linesep.join(lines) + os.linesep)
'''


@pytest.fixture(scope="module")
def cfg():
    return tomllib.loads(CONFIG.read_text(encoding="utf-8"))["duration"]


@pytest.fixture
def fake(tmp_path, cfg, monkeypatch):
    script = tmp_path / "fake_phonemize.py"
    script.write_text(FAKE, encoding="utf-8")
    for var in ("FAKE_PHONEMIZER", "FAKE_ESPEAK", "FAKE_FAIL", "FAKE_DROP"):
        monkeypatch.delenv(var, raising=False)
    return dur.Phonemizer({**cfg, "command": [sys.executable, str(script)]}, "en-us")


def test_registered_constants(cfg):
    # S3: "0.55 s per sentence end and 0.20 s per clause mark ... eSpeak NG 1.52.0 phones, through phonemizer 3.4.0,
    # at 0.08 s each"
    assert (cfg["seconds_per_unit"], cfg["seconds_per_sentence_end"], cfg["seconds_per_clause_mark"]) == \
        (0.08, 0.55, 0.20)
    assert (cfg["espeak_ng_version"], cfg["phonemizer_version"]) == ("1.52.0", "3.4.0")


def test_phone_count_of_the_benchmark_sentence():
    # eSpeak NG 1.52.0, en-us, for "The little dragon quickly flew through the beautiful sky."
    # (affect-narrativity-duration/espeak_test.txt)
    line = "ð ə | l ɪ ɾ əl | d ɹ æ ɡ ə n | k w ɪ k l i | f l uː | θ ɹ uː | ð ə | b j uː ɾ i f əl | s k aɪ"
    assert dur.count_phones(line, " | ") == (36, 9)
    assert dur.count_phones("", " | ") == (0, 0)


def test_seconds_and_log_per_word():
    c = dur.DurationConstants(0.08, 0.55, 0.20)
    assert c.seconds(100, 5, 3) == pytest.approx(8.0 + 2.75 + 0.6)
    assert dur.log_seconds_per_word(11.35, 25) == pytest.approx(math.log(11.35 / 25))
    assert dur.log_seconds_per_word(11.35, 0) is None
    assert dur.log_seconds_per_word(0.0, 10) is None


def test_clause_marks_default_rule(cfg):
    rules = dur.PauseRules.from_config(cfg)
    assert rules.clause_mark_count("Yes, I know; it is: here — now.") == 4
    assert rules.clause_mark_count("Full-width，marks；too：") == 3
    assert rules.clause_mark_count("It cost 1,000 coins at 10:30.") == 0  # not between digits
    assert rules.clause_mark_count("A well-known fox.") == 0  # a hyphen inside a word is no pause
    assert rules.clause_mark_count("Wait - go.") == 1  # a hyphen between spaces is a dash
    assert rules.clause_mark_count("Wait--go.") == 1  # a run of hyphens is one dash
    assert rules.clause_mark_count("He went——then stopped.") == 1  # a run of dashes is one mark


def test_clause_mark_switches(cfg):
    rules = dur.PauseRules.from_config({**cfg, "skip_between_digits": False, "spaced_hyphen_is_dash": False})
    assert rules.clause_mark_count("1,000 - 2,000") == 2


def test_terminal_mark_runs(cfg):
    rules = dur.PauseRules.from_config(cfg)
    assert rules.terminal_run_count("Hi!! Really?! Yes... ok.") == 4
    assert rules.terminal_run_count("No marks here") == 0


def test_one_line_collapses_line_breaks():
    assert dur.one_line(" Tom ran.\nHe hid. End ") == "Tom ran. He hid. End"


def test_parse_versions():
    text = "phonemizer-3.4.0\navailable backends: espeak-ng-1.52.0, espeak-mbrola, festival-2.5.0"
    assert dur.parse_versions(text) == ("3.4.0", "1.52.0")
    assert dur.parse_versions("nothing") == (None, None)


def test_arguments_follow_the_benchmark_settings(cfg, tmp_path):
    ph = dur.Phonemizer({**cfg, "command": ["phonemize"]}, "en-us")
    args = ph.arguments(tmp_path / "in.txt", tmp_path / "out.txt")
    assert args[:1] == ["phonemize"]
    joined = " ".join(args)
    for part in ("-b espeak", "-l en-us", "--language-switch remove-flags", "--preserve-empty-lines", "--strip"):
        assert part in joined
    assert args[args.index("-p") + 1] == " " and args[args.index("-w") + 1] == " | "
    assert "--with-stress" not in args and "--preserve-punctuation" not in args
    assert args[-3:] == ["-o", str(tmp_path / "out.txt"), str(tmp_path / "in.txt")]


def test_default_command_runs_phonemizer_in_a_separate_python(cfg):
    ph = dur.Phonemizer({**cfg, "command": []}, "en-us")
    assert ph.command == [sys.executable, "-I", "-m", "phonemizer.main"]


def test_phonemize_through_an_external_program(fake):
    texts = ["Tom ran.\nHe hid.", "Mia sang", "!!!"]
    lines = fake.phonemize(texts)
    assert len(lines) == 3
    assert dur.count_phones(lines[0], " | ") == (len("TomranHehid"), 4)
    assert dur.count_phones(lines[1], " | ") == (7, 2)
    assert lines[2] == ""  # a text without letters keeps its line
    assert fake.phonemize([]) == []


def test_version_pins_are_checked(fake, monkeypatch):
    assert fake.check_pins() == ("3.4.0", "1.52.0")
    monkeypatch.setenv("FAKE_ESPEAK", "1.51")
    with pytest.raises(dur.PhonemizerError, match="registered pins"):
        fake.check_pins()
    loose = dur.Phonemizer({**fake.cfg, "allow_version_mismatch": True}, "en-us")
    assert loose.check_pins() == ("3.4.0", "1.51")


def test_a_failing_or_misaligned_program_raises(fake, monkeypatch):
    monkeypatch.setenv("FAKE_DROP", "1")
    with pytest.raises(dur.PhonemizerError, match="lines"):
        fake.phonemize(["a b", "c d"])
    monkeypatch.delenv("FAKE_DROP")
    monkeypatch.setenv("FAKE_FAIL", "1")
    with pytest.raises(dur.PhonemizerError, match="failed"):
        fake.phonemize(["a b"])


@pytest.mark.models
def test_real_phonemizer_reproduces_the_benchmark_count(cfg):
    """Runs the pinned phonemizer and eSpeak NG when INTRACT_PHONEMIZE_PYTHON names a Python that has them.

    INTRACT_ESPEAK_LIBRARY and INTRACT_ESPEAK_DATA may point at the library and its data, as espeakng_loader
    provides them.
    """
    python = os.environ.get("INTRACT_PHONEMIZE_PYTHON")
    if not python:
        pytest.skip("INTRACT_PHONEMIZE_PYTHON is not set")
    ph = dur.Phonemizer({**cfg, "command": [python, "-I", "-m", "phonemizer.main"],
                         "espeak_library": os.environ.get("INTRACT_ESPEAK_LIBRARY", ""),
                         "espeak_data_path": os.environ.get("INTRACT_ESPEAK_DATA", "")}, "en-us")
    ph.check_pins()
    [line] = ph.phonemize(["The little dragon quickly flew through the beautiful sky."])
    assert dur.count_phones(line, cfg["word_separator"]) == (36, 9)
