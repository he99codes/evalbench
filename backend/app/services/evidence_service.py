"""Evidence grounding: every stored quote is a verbatim substring of the response.

Matching is tolerant of how models transcribe (markdown emphasis, smart quotes,
truncated tails, minor typos) — but what we persist is always the exact span of the
original response text, never the model's version of it.
"""

from __future__ import annotations

import difflib
import re
import unicodedata

from app.models import ResponseLabel
from app.schemas.evaluation import EvidenceItemCreate
from app.utils.validation import EvidenceQuote

_WRAPPING = "\"'“”‘’`"
# Markdown emphasis/formatting characters ignored during matching.
_MD_CHARS = "*_`~"
# Minimum similarity for the best-sentence fallback (token-level transcription drift).
_FUZZY_THRESHOLD = 0.85


def _clean_quote(quote: str) -> str:
    quote = quote.strip()
    # Models often wrap quotes in quotation marks or trail with ellipses.
    quote = quote.strip(_WRAPPING).strip()
    quote = re.sub(r"^(\.\.\.|…)\s*|\s*(\.\.\.|…)$", "", quote)
    return quote.strip(_WRAPPING).strip()


def _norm_char(ch: str) -> str:
    """Per-character normalization for matching: NFKC, unified quotes/dashes, lower."""
    ch = unicodedata.normalize("NFKC", ch)
    if ch in "“”": ch = '"'
    if ch in "‘’": ch = "'"
    if ch in "—–": ch = "-"
    if ch in _MD_CHARS: return ""
    return ch.lower()


def _normalize_with_map(text: str) -> tuple[str, list[int]]:
    """Normalized text plus, for each normalized char, its index in the original."""
    out: list[str] = []
    index: list[int] = []
    for i, ch in enumerate(text):
        for c in _norm_char(ch):
            if c.isspace():
                c = " "
                if out and out[-1] == " ":
                    continue  # collapse whitespace runs
            out.append(c)
            index.append(i)
    return "".join(out), index


def _normalize(text: str) -> str:
    return _normalize_with_map(text)[0]


def _map_span(text: str, index: list[int], start: int, end: int) -> tuple[int, int]:
    """Map a normalized [start, end) span back to original offsets, then widen to
    include adjacent markdown emphasis characters (the model may drop leading `**`)."""
    s, e = index[start], index[end - 1] + 1
    while s > 0 and text[s - 1] in _MD_CHARS:
        s -= 1
    while e < len(text) and text[e] in _MD_CHARS:
        e += 1
    return s, e


def _partial_ratio(needle: str, haystack: str) -> float:
    """Best similarity of `needle` to any same-length window inside `haystack`."""
    if not needle:
        return 0.0
    if len(needle) > len(haystack):
        needle, haystack = haystack, needle
    best = 0.0
    for i in range(len(haystack) - len(needle) + 1):
        ratio = difflib.SequenceMatcher(None, needle, haystack[i : i + len(needle)]).ratio()
        if ratio > best:
            best = ratio
    return best


def _best_sentence_span(text: str, quote_norm: str) -> tuple[int, int] | None:
    """Fuzzy fallback: the response sentence most similar to the intended quote.

    A quote that is a truncated/mistyped substring still scores high via partial
    ratio, while a true paraphrase does not. The returned span is the full sentence.
    """
    best_ratio, best = _FUZZY_THRESHOLD, None
    for match in re.finditer(r"[^.!?\n]+(?:[.!?]|$)", text):
        cand = match.group()
        stripped = cand.strip()
        if not stripped:
            continue
        ratio = _partial_ratio(quote_norm, _normalize(cand))
        if ratio > best_ratio:
            start = match.start() + (len(cand) - len(cand.lstrip()))
            best_ratio, best = ratio, (start, match.end())
    return best


def locate_quote(text: str, quote: str) -> tuple[int, int] | None:
    """Return the (start, end) span of `quote` in `text`, tolerating model sloppiness.

    Order: exact match → markdown/quote/whitespace-normalized match → tail-truncated
    match (models cut quotes mid-word) → best-sentence fuzzy match (minor typos).
    """
    cleaned = _clean_quote(quote)
    if not cleaned:
        return None
    index = text.find(cleaned)
    if index >= 0:
        return index, index + len(cleaned)

    norm_text, index_map = _normalize_with_map(text)
    quote_norm = _normalize(cleaned).strip()
    if not quote_norm:
        return None
    pos = norm_text.find(quote_norm)
    if pos >= 0:
        return _map_span(text, index_map, pos, pos + len(quote_norm))

    # Fuzzy alignment first: resolves mid-quote typos to the full intended sentence.
    if len(quote_norm.split()) >= 4:
        span = _best_sentence_span(text, quote_norm)
        if span is not None:
            return span

    # Tail-truncation: drop trailing words until a prefix matches at a word boundary
    # (a mid-word hit like "emits a" inside "emits an" is not a real truncation point).
    words = quote_norm.split(" ")
    while len(words) >= 4:
        words.pop()
        prefix = " ".join(words)
        pos = 0
        while True:
            pos = norm_text.find(prefix, pos)
            if pos < 0:
                break
            end = pos + len(prefix)
            if end >= len(norm_text) or norm_text[end] == " ":
                return _map_span(text, index_map, pos, end)
            pos += 1

    return None


def ground_evidence(
    response_text: str, label: ResponseLabel, evidence: list[EvidenceQuote]
) -> list[EvidenceItemCreate]:
    """Keep only quotes that resolve to a real span of the response, de-duplicated by span.

    The stored quote is the exact substring of the response (so offsets are reliable),
    and `location` records the character span. Raises ValueError if nothing survives,
    because a criterion score must never be stored without evidence.
    """
    items: list[EvidenceItemCreate] = []
    seen_spans: list[tuple[int, int]] = []
    for item in evidence:
        span = locate_quote(response_text, item.quote)
        if span is None:
            continue
        # Duplicate or contained within an existing quote -> skip.
        if any(s <= span[0] and span[1] <= e for s, e in seen_spans):
            continue
        # A longer quote containing earlier ones replaces them.
        contained = [i for i, (s, e) in enumerate(seen_spans) if span[0] <= s and e <= span[1]]
        for i in reversed(contained):
            seen_spans.pop(i)
            items.pop(i)
        supports = item.supports.strip() or "Cited by the evaluator"
        seen_spans.append(span)
        items.append(
            EvidenceItemCreate(
                response=label,
                quote=response_text[span[0] : span[1]],
                supports=supports[:2000],
                location=f"chars {span[0]}-{span[1]}",
            )
        )
    if not items:
        raise ValueError("no evidence quote was found verbatim in the response")
    return items
