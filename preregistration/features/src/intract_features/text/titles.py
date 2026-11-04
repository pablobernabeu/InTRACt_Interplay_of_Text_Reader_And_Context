"""Titles: the catalogue's title line (gap G1a) and S3's rule for page-initial titles (gap G1b).

The catalogue's title is its own first line. In the zip delivery of 26 October 2026, "The first line
of a file is the story's title and each further line is one page" (story_texts/extract_story_texts.py),
and io.catalogue.split_lines() separates it exactly as the extraction does. The title line is kept in
Document.title and read by no feature, and the extraction's `words` column already leaves it out.
That is the planning review's recommended default for the title line (SPECIFICATION.md, gap G1a), PENDING the
Feature Specification. The planning review's recommendation covered the title line only, not the page titles
below (gap G1b), whose default is the PI's to decide.

S3 also registers a rule for titles inside a text: "A title is the first line of a text or page if it
has at most eight words and no sentence-final mark. Titles are identified on the English source and
carried to each translation by line index if line structure survives." A page holds more than one line
where the delivery wrote an in-page line break: the zip files escape it as a backslash followed by n,
and split_lines() decodes the escape into a line feed, text.words.LINE_BREAK, the only line break a
page can hold (the extraction's docstring; gap G9 asks only how often this occurs).
find_page_titles() applies the rule to the first line of each English page, and carry_page_titles()
carries the decisions to a translation.

The rule leaves four choices open. Each is a named switch in config/stages/documents.toml [titles],
PENDING the Feature Specification (gaps G1b and G9):

- page_rule. "multiline" (the default) tests a page's first line only when an in-page line break
  follows it, so a page that is one short line, such as a sentence continued across a page break or
  "The End", is never taken for a title. "every_page" tests single-line pages too, the literal
  reading. "off" applies no page rule.
- action. "exclude" (the default) moves a page title out of the page into Document.meta["page_titles"],
  so its words leave the text as served; "mark" records it there and leaves the page as served. Which
  of the two applies changes a registered quantity, the outcome's denominator, so it is the PI's
  decision (gap G1b); the planning review's recommendation covered only the title line.
- final_mark_test. "anywhere" (the default, the literal reading of "no sentence-final mark") refuses a
  line holding any sentence-final mark. "line_end" refuses only a line that ends with one, closing
  quotation marks and brackets skipped.
- carry_rule, what "if line structure survives" means. "page_lines" (the default) carries a title when
  the translation has as many pages as its English source and the title's page holds as many lines
  as the English page did. "text_lines" also requires every other page to keep its number of lines.

What the defaults do to the outcome. The rule reads only the shape of a line, so under the defaults
a short first line without a sentence-final mark that an in-page line break follows is taken for a
title even when it is dialogue or verse: '“Wait,”' above 'said Tom.', 'Tom shouted:' above '“Run!”',
'Twinkle, twinkle, little star,' above the next line of the rhyme. With action = "exclude", its words
leave every feature and the text's registered word count, the processing outcome's denominator. The
documents stage counts the titles and their words (page_titles, page_title_words) and the pages that
hold a line break (pages_with_line_breaks), so that G1b and G9 can be settled on those counts.

Words are counted with the registered word function. A title needs at least one word, so a blank
first line is never a title.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Collection, Sequence
from dataclasses import dataclass

from intract_features.text.words import LINE_BREAK, WHITE_SPACE, count_words

PAGE_RULES = ("multiline", "every_page", "off")
ACTIONS = ("exclude", "mark")
FINAL_MARK_TESTS = ("anywhere", "line_end")
CARRY_RULES = ("page_lines", "text_lines")

# Skipped before the line-end test, as S3 skips "Closing quotation marks after a terminal mark".
# Straight quotation marks are ambiguous in direction, so both are skipped too.
_STRAIGHT_QUOTES = frozenset("\"'")


@dataclass(frozen=True)
class PageTitle:
    """A page-initial title: the page's index, the title line and the lines the page held as served."""

    page: int
    text: str
    lines: int

    def to_json(self) -> dict:
        """The form kept in Document.meta["page_titles"]."""
        return {"page": self.page, "text": self.text, "lines": self.lines}

    @classmethod
    def from_json(cls, obj: dict) -> PageTitle:
        """Inverse of to_json."""
        return cls(page=int(obj["page"]), text=str(obj["text"]), lines=int(obj["lines"]))


def _closing(ch: str) -> bool:
    return ch in _STRAIGHT_QUOTES or unicodedata.category(ch) in ("Pe", "Pf")


def is_title_line(line: str, *, max_words: int, terminal_marks: Collection[str], final_mark_test: str) -> bool:
    """S3: a line is a title if it has at most `max_words` words and no sentence-final mark."""
    if final_mark_test not in FINAL_MARK_TESTS:
        raise ValueError(f"final_mark_test must be one of {FINAL_MARK_TESTS}, not {final_mark_test!r}")
    n = count_words(line)
    if n == 0 or n > max_words:
        return False
    if final_mark_test == "anywhere":
        return not any(ch in terminal_marks for ch in line)
    end = len(line)
    while end and (line[end - 1] in WHITE_SPACE or _closing(line[end - 1])):
        end -= 1
    return not (end and line[end - 1] in terminal_marks)


def find_page_titles(pages: Sequence[str], *, page_rule: str, max_words: int, terminal_marks: Collection[str],
                     final_mark_test: str) -> list[PageTitle]:
    """The page-initial titles of a text's pages under S3's rule and the `page_rule` switch."""
    if page_rule not in PAGE_RULES:
        raise ValueError(f"page_rule must be one of {PAGE_RULES}, not {page_rule!r}")
    if page_rule == "off":
        return []
    found = []
    for i, page in enumerate(pages):
        lines = page.split(LINE_BREAK)
        if page_rule == "multiline" and len(lines) < 2:
            continue
        if is_title_line(lines[0], max_words=max_words, terminal_marks=terminal_marks,
                         final_mark_test=final_mark_test):
            found.append(PageTitle(page=i, text=lines[0], lines=len(lines)))
    return found


def line_count(page: str) -> int:
    """The number of lines a page holds: one more than its in-page line breaks."""
    return page.count(LINE_BREAK) + 1


def carry_page_titles(english: Sequence[PageTitle], english_pages: int, pages: Sequence[str], *,
                      rule: str = "page_lines",
                      english_lines: Sequence[int] | None = None) -> tuple[list[PageTitle], int]:
    """Carry English page titles to a translation by line index, where line structure survives (S3).

    Under either rule the translation must have as many pages as its English source. Under
    "page_lines" a title is carried when its page holds as many lines as the English page did as
    served. Under "text_lines" every page must hold as many lines as its English page did
    (`english_lines`, one count per English page as served), or no title is carried. Returns the
    carried titles, whose text is the translation's own first line, and the number not carried.
    """
    if rule not in CARRY_RULES:
        raise ValueError(f"carry_rule must be one of {CARRY_RULES}, not {rule!r}")
    if len(pages) != english_pages:
        return [], len(english)
    if rule == "text_lines":
        if english_lines is None or len(english_lines) != english_pages:
            raise ValueError("carry_rule 'text_lines' needs the English page's line counts, one per page")
        if [line_count(p) for p in pages] != list(english_lines):
            return [], len(english)
    carried, lost = [], 0
    for title in english:
        lines = pages[title.page].split(LINE_BREAK)
        if len(lines) == title.lines:
            carried.append(PageTitle(page=title.page, text=lines[0], lines=len(lines)))
        else:
            lost += 1
    return carried, lost


def served_line_counts(pages: Sequence[str], found: Sequence[PageTitle]) -> list[int]:
    """Each page's number of lines as served, from pages that may have had their titles excluded."""
    counts = [line_count(p) for p in pages]
    for title in found:
        counts[title.page] = title.lines
    return counts


def exclude_page_titles(pages: Sequence[str], titles: Sequence[PageTitle]) -> tuple[str, ...]:
    """The pages with each title line removed, together with the line break after it.

    A page that held only its title becomes empty, and stays in place so that page indices keep
    matching the pages served.
    """
    out = list(pages)
    for title in titles:
        page = out[title.page]
        if not page.startswith(title.text):
            raise ValueError(f"page {title.page} does not start with its title {title.text!r}")
        rest = page[len(title.text):]
        out[title.page] = rest[len(LINE_BREAK):] if rest.startswith(LINE_BREAK) else rest
    return tuple(out)
