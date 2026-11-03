"""Text length and pagination: word count, page count, pages per hundred words and page-break alignment.

- Word count: words of the outcome's unit (qmd Measures: "a whitespace-delimited token of the text as served that
  contains at least one letter or digit"), from the registered word function. It is the outcome's denominator,
  the length covariate (qmd: "Text length in words [...] enter every model as covariates") and, divided by the
  catalogue median at aggregation, the story unit of Hypothesis 6. The title line is not part of the pages (gap
  G1), so it is not counted.
- Page count: the pages of the delivered text, which the linkage test compares with the page count recorded for
  the session (qmd Sampling plan).
- Pages per hundred words (qmd Sensitivity analyses, sixth family): "Pages per hundred words, computed from the
  delivered text, will enter a tier-1 refit along with its age-band interaction, and how pagination aligns with
  sentence ends will be reported." The alignment is reported as the page breaks that fall inside a sentence.
"""

from __future__ import annotations

from collections.abc import Sequence

NAN = float("nan")


def page_features(n_pages: int, n_words: int, per_words: int) -> dict[str, float]:
    """Word count, page count and pages per `per_words` words (undefined for a text with no word)."""
    return {"word_count": n_words, "page_count": n_pages,
            "pages_per_100_words": per_words * n_pages / n_words if n_words else NAN}


def page_break_alignment(page_spans: Sequence[tuple[int, int]],
                         sentence_spans: Sequence[tuple[int, int]]) -> dict[str, int]:
    """How many page breaks fall inside a sentence: a sentence that holds characters of both pages.

    Pages are [start, end) spans of the joined text, one joining space apart (records.Document.page_spans), and a
    sentence that ends on the joining space ends with its page. Sentences are in order and do not overlap.
    """
    inside, k = 0, 0
    for (_, end), (start_next, _) in zip(page_spans[:-1], page_spans[1:], strict=True):
        while k < len(sentence_spans) and sentence_spans[k][1] <= end:
            k += 1
        if k < len(sentence_spans) and sentence_spans[k][0] < end and sentence_spans[k][1] > start_next:
            inside += 1
    return {"page_breaks": max(len(page_spans) - 1, 0), "page_breaks_inside_sentence": inside}
