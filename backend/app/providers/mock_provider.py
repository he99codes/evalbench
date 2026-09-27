"""Deterministic MockLLMProvider.

Produces realistic structured output for every pipeline stage without any network
call. It reads the tagged sections of the stage prompt (<prompt>, <response>,
<criterion>, <requirements>, <scores>, ...) and applies simple, transparent
heuristics. Same input -> same output, always. Evidence quotes are real sentences
taken verbatim from the response, so they pass evidence grounding.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from app.providers.base import LLMResponse
from app.utils.validation import (
    ComplianceCheckOutput,
    CriterionEvaluationOutput,
    ImprovementOutput,
    PairwiseComparisonOutput,
    RequirementExtractionOutput,
)

# ---------------------------------------------------------------------------
# Text helpers
# ---------------------------------------------------------------------------

STOP = set(
    """a an the and or but to of for in on with that this these those be is are was were will would
    must should can could may might reply response write your you it its as at by from keep use do does not
    don't never avoid any all each their them they we our us i me my confirm include make sure also specific
    please so than then there here about into over just very such only both have has had if when which who""".split()
)
SYNONYMS = {"apolo": {"apolo", "sorry"}, "sorry": {"sorry", "apolo"}}
POLITE = ("sorry", "apolog", "thank", "appreciat", "understand", "happy to", "glad", "please", "value")

LENGTH_RE = re.compile(
    r"\b(under|at most|no more than|fewer than|less than|maximum of|up to|within)\s+(\d+)\s+(words|sentences)\b"
)
NEG_RE = re.compile(r"^\s*(do not|don't|never|avoid|no|without)\b")
FORMAT_RE = re.compile(r"\b(bullet|bulleted|numbered|json|markdown|table|heading|format)\b")
TONE_RE = re.compile(r"\b(tone|audience|register|voice)\b")
IMPERATIVE_RE = re.compile(
    r"^\s*(write|reply|respond|explain|summarize|summarise|list|describe|create|draft|give|provide|include|answer|tell)\b"
)
TIMELINE_RE = re.compile(
    r"\b(within|in)\s+\d+\s+(business\s+|working\s+)?(minute|minutes|hour|hours|day|days|week|weeks)\b"
    r"|\bby\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday|tomorrow|tonight|the end of)\b"
    r"|\b\d{1,2}/\d{1,2}(/\d{2,4})?\b",
    re.I,
)
TIME_WORDS = ("timeline", "date", "deadline", "timeframe", "time frame", "when")


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9$#%']+", text.lower())


def _stem(word: str) -> str:
    word = word.strip("'")
    return word if word.startswith("$") or word[:1].isdigit() else word[:5]


def _content(text: str) -> list[str]:
    out: list[str] = []
    for w in _tokens(text):
        if w in STOP or (len(w) < 3 and not w[:1].isdigit() and not w.startswith("$")):
            continue
        stem = _stem(w)
        if stem not in out:
            out.append(stem)
    return out


def _sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+|\n+", text)
    return [p.strip() for p in parts if p.strip()]


def _word_count(text: str) -> int:
    return len(re.findall(r"\S+", text))


def _coverage(words: list[str], text: str) -> float:
    if not words:
        return 1.0
    present = {_stem(w) for w in _tokens(text)}
    hit = sum(1 for w in words if SYNONYMS.get(w, {w}) & present)
    return hit / len(words)


def _best_sentence(text: str, words: list[str]) -> str:
    sents = _sentences(text)
    return max(sents, key=lambda s: (_coverage(words, s), -abs(len(s) - 90))) if sents else text.strip()


def _section(prompt: str, tag: str, **attrs: str) -> str | None:
    for match in re.finditer(rf"<{tag}(?P<attrs>[^>]*)>\n?(?P<body>.*?)\n?</{tag}>", prompt, re.S):
        found = dict(re.findall(r'(\w+)="([^"]*)"', match.group("attrs")))
        if all(found.get(k) == v for k, v in attrs.items()):
            return match.group("body")
    return None


def _section_attrs(prompt: str, tag: str) -> dict[str, str]:
    match = re.search(rf"<{tag}(?P<attrs>[^>]*)>", prompt)
    return dict(re.findall(r'(\w+)="([^"]*)"', match.group("attrs"))) if match else {}


# ---------------------------------------------------------------------------
# Requirement judging (shared by stage 2 and stage 5)
# ---------------------------------------------------------------------------


@dataclass
class Req:
    ref: str
    type: str
    mandatory: bool
    description: str


def _parse_requirements(block: str | None) -> list[Req]:
    reqs = []
    for line in (block or "").splitlines():
        m = re.match(r"^(R\d+) \[(\w+), (mandatory|optional)\] (.+)$", line.strip())
        if m:
            reqs.append(Req(m.group(1), m.group(2), m.group(3) == "mandatory", m.group(4)))
    return reqs


def _judge(req: Req, response: str) -> tuple[bool, str, str]:
    """(satisfied, explanation, verbatim quote or "")."""
    low = req.description.lower()
    sents = _sentences(response)

    length = LENGTH_RE.search(low)
    if req.type == "LENGTH" or length:
        if not length:
            return True, "No measurable length limit was stated.", ""
        limit, unit = int(length.group(2)), length.group(3)
        count = len(sents) if unit == "sentences" else _word_count(response)
        strict = length.group(1) in ("under", "fewer than", "less than")
        ok = count < limit if strict else count <= limit
        return ok, f"The response has {count} {unit} against a limit of {limit}.", ""

    if NEG_RE.match(low):
        if any(w in low for w in TIME_WORDS):
            hits = [s for s in sents if TIMELINE_RE.search(s)]
            if hits:
                return False, "The response commits to a specific timeline.", hits[0]
            return True, "No specific timeline or date is promised.", ""
        words = _content(NEG_RE.sub("", low))
        hits = [s for s in sents if words and _coverage(words, s) >= 0.6]
        if hits:
            return False, "The response includes content the prompt forbids.", hits[0]
        return True, "The forbidden content does not appear.", ""

    if req.type == "AUDIENCE" or TONE_RE.search(low):
        polite = [s for s in sents if any(p in s.lower() for p in POLITE)]
        if polite:
            return True, "The wording is courteous and customer-focused.", polite[0]
        return False, "The response lacks courteous or empathetic wording.", ""

    if req.type == "FORMAT":
        if "bullet" in low or "list" in low:
            bullets = [line for line in response.splitlines() if re.match(r"^\s*([-*•]|\d+[.)])\s+", line)]
            return bool(bullets), "Checked for list formatting.", bullets[0].strip() if bullets else ""
        if "json" in low:
            try:
                json.loads(response)
                return True, "The response is valid JSON.", ""
            except ValueError:
                return False, "The response is not valid JSON.", ""

    words = _content(low)
    coverage = _coverage(words, response)
    quote = _best_sentence(response, words)
    if coverage >= 0.5:
        return True, f"The response addresses this ({coverage:.0%} of key terms present).", quote
    return False, f"The response does not clearly address this ({coverage:.0%} of key terms present).", ""


# ---------------------------------------------------------------------------
# Stage handlers
# ---------------------------------------------------------------------------


def _item(type_: str, text: str, mandatory: bool, description: str | None = None) -> dict[str, Any]:
    return {
        "type": type_,
        "description": (description or text).rstrip(".") + ".",
        "mandatory": mandatory,
        "source_text": text,
    }


def _extract(prompt_text: str) -> dict[str, Any]:
    text = re.sub(r"\"[^\"]*\"|“[^”]*”", " ", prompt_text)  # quoted context is not a requirement
    out: dict[str, list] = {"requests": [], "constraints": [], "format_requirements": [], "ambiguities": []}
    for sent in _sentences(text):
        low = sent.lower()
        if sent.endswith(":") or len(_tokens(sent)) < 2:
            continue
        if LENGTH_RE.search(low):
            out["constraints"].append(_item("LENGTH", sent, True))
        elif NEG_RE.match(low):
            out["constraints"].append(_item("CONSTRAINT", sent, True))
        elif FORMAT_RE.search(low):
            out["format_requirements"].append(_item("FORMAT", sent, True))
        elif TONE_RE.search(low):
            out["constraints"].append(_item("AUDIENCE", sent, False))
            out["ambiguities"].append(
                f"\"{sent.rstrip('.')}\" is subjective; it is judged through the tone-related criteria."
            )
        elif re.search(r"\bmust\b", low):
            body = re.split(r"\bmust\b", sent, maxsplit=1, flags=re.I)[1].strip().rstrip(".")
            for clause in re.split(r",\s*(?:and\s+)?", body):
                if clause.strip():
                    out["requests"].append(_item("REQUEST", sent, True, f"Must {clause.strip()}"))
        elif IMPERATIVE_RE.match(low):
            out["requests"].append(_item("REQUEST", sent, True))
    for vague in ("appropriate", "brief", "short", "some", "etc"):
        if vague in _tokens(prompt_text):
            out["ambiguities"].append(f"The word \"{vague}\" is not precisely defined in the prompt.")
    return out


def _criterion(prompt: str) -> dict[str, Any]:
    attrs = _section_attrs(prompt, "criterion")
    name = attrs.get("name", "Criterion")
    lo, hi = float(attrs.get("scale_min", 1)), float(attrs.get("scale_max", 5))
    description = _section(prompt, "criterion") or ""
    response = _section(prompt, "response") or ""
    reqs = _parse_requirements(_section(prompt, "requirements"))
    judged = [(r, *_judge(r, response)) for r in reqs]
    key = f"{name} {description}".lower()
    sents = _sentences(response) or [response.strip()]
    words = _word_count(response)

    def pool_fraction(pool):
        return sum(1 for _, ok, _, _ in pool if ok) / len(pool) if pool else 1.0

    evidence: list[dict[str, str]] = []
    if "constraint" in key:
        pool = [j for j in judged if j[0].mandatory and j[0].type in ("CONSTRAINT", "LENGTH", "FORMAT")]
        frac = pool_fraction(pool)
        failed = [j for j in pool if not j[1]]
        reasoning = (
            "Violates: " + "; ".join(f"{r.description} ({expl})" for r, _, expl, _ in failed)
            if failed
            else "All hard constraints in the prompt are respected."
        )
        for r, ok, expl, quote in failed:
            if quote:
                evidence.append({"quote": quote, "supports": f"Breaks the constraint: {r.description}"})
        if failed and not evidence:
            longest = max(sents, key=len)
            evidence.append({"quote": longest, "supports": f"Part of an over-limit reply ({failed[0][2]})"})
        if not failed:
            evidence.append({"quote": sents[0], "supports": "Compliant opening; no forbidden content found."})
    elif "instruction" in key or "complete" in key:
        pool = [j for j in judged if j[0].type == "REQUEST" and (j[0].mandatory or "complete" in key)]
        frac = pool_fraction(pool)
        missed = [r.description for r, ok, _, _ in pool if not ok]
        reasoning = (
            f"Addresses {len(pool) - len(missed)} of {len(pool)} requested tasks."
            + (f" Missing: {'; '.join(missed)}." if missed else "")
        )
        for r, ok, _, quote in pool:
            if ok and quote and all(e["quote"] != quote for e in evidence):
                evidence.append({"quote": quote, "supports": f"Fulfils: {r.description}"})
    elif "concise" in key:
        limits = [int(m.group(2)) for r in reqs if (m := LENGTH_RE.search(r.description.lower())) and m.group(3) == "words"]
        target = limits[0] if limits else 80
        frac = max(0.0, min(1.0, 1 - max(0, words - target) / target))
        reasoning = f"{words} words against a target of about {target}."
        evidence.append({"quote": max(sents, key=len), "supports": "Longest sentence in the reply."})
    elif "tone" in key:
        polite = [s for s in sents if any(p in s.lower() for p in POLITE)]
        frac = min(1.0, len(polite) / 3)
        reasoning = f"{len(polite)} sentence(s) use courteous or empathetic wording."
        for s in polite[:2] or sents[:1]:
            evidence.append({"quote": s, "supports": "Shows the tone of the reply."})
    elif "clar" in key:
        avg = words / max(1, len(sents))
        frac = max(0.0, min(1.0, 1 - max(0.0, avg - 15) / 25))
        reasoning = f"Average sentence length is {avg:.1f} words."
        evidence.append({"quote": max(sents, key=len), "supports": "Longest sentence; drives readability."})
    elif "accura" in key:
        broken = [j for j in judged if NEG_RE.match(j[0].description.lower()) and not j[1]]
        frac = 0.4 if broken else 0.9
        reasoning = (
            "Makes commitments or claims the prompt does not support."
            if broken
            else "Statements are consistent with the facts given in the prompt."
        )
        quote = next((q for _, _, _, q in broken if q), None) or sents[0]
        evidence.append({"quote": quote, "supports": reasoning})
    elif "relev" in key:
        prompt_words = set(_content(_section(prompt, "prompt") or ""))
        on_topic = [s for s in sents if set(_content(s)) & prompt_words]
        frac = len(on_topic) / len(sents)
        reasoning = f"{len(on_topic)} of {len(sents)} sentences relate directly to the prompt."
        evidence.append({"quote": on_topic[0] if on_topic else sents[0], "supports": "On-topic content."})
    else:
        pool = [j for j in judged if j[0].mandatory]
        frac = pool_fraction(pool)
        reasoning = f"Satisfies {sum(1 for j in pool if j[1])} of {len(pool)} mandatory requirements."

    if not evidence:
        evidence.append({"quote": _best_sentence(response, _content(description)), "supports": reasoning})
    score = lo + round(frac * (hi - lo))
    return {
        "criterion": name,
        "score": score,
        "passed": (score - lo) / (hi - lo) >= 0.6,
        "reasoning": reasoning,
        "evidence": evidence[:3],
    }


_RESULT_LINE = re.compile(
    r"^- (?P<name>.+?) \(weight (?P<w>[\d.]+)\): (?P<score>-?[\d.]+) on (?P<min>-?\d+)-(?P<max>\d+), "
    r"(?P<passed>passed|failed)\. Reasoning: (?P<reasoning>.*)$"
)


def _parse_results(block: str | None) -> list[dict[str, Any]]:
    rows = []
    for line in (block or "").splitlines():
        m = _RESULT_LINE.match(line.strip())
        if m:
            lo, hi = float(m.group("min")), float(m.group("max"))
            rows.append(
                {
                    "name": m.group("name"),
                    "weight": float(m.group("w")),
                    "norm": (float(m.group("score")) - lo) / (hi - lo),
                    "passed": m.group("passed") == "passed",
                    "reasoning": m.group("reasoning"),
                }
            )
    return rows


def _weighted(rows: list[dict[str, Any]]) -> float:
    total = sum(r["weight"] for r in rows)
    return sum(r["norm"] * r["weight"] for r in rows) / total if total else 0.0


def _hard_failures(rows: list[dict[str, Any]]) -> int:
    return sum(1 for r in rows if not r["passed"] and re.search(r"constraint|instruction", r["name"], re.I))


def _pairwise(prompt: str) -> dict[str, Any]:
    rows = {c: _parse_results(_section(prompt, "scores", candidate=c)) for c in ("1", "2")}
    fails = {c: _hard_failures(rows[c]) for c in rows}
    weighted = {c: _weighted(rows[c]) for c in rows}
    if fails["1"] != fails["2"]:
        winner = "1" if fails["1"] < fails["2"] else "2"
    elif abs(weighted["1"] - weighted["2"]) < 0.02:
        winner = None
    else:
        winner = "1" if weighted["1"] > weighted["2"] else "2"
    if winner is None:
        return {
            "preferred": "TIE",
            "reasoning": "Both candidates fail the same hard requirements and their weighted rubric "
            f"results are within two points ({weighted['1']:.0%} vs {weighted['2']:.0%}).",
            "decisive_criteria": [],
        }
    loser = "2" if winner == "1" else "1"
    by_name = {r["name"]: r for r in rows[loser]}
    diffs = sorted(
        ((r["norm"] - by_name[r["name"]]["norm"], r["name"]) for r in rows[winner] if r["name"] in by_name),
        reverse=True,
    )
    decisive = [name for diff, name in diffs if diff > 0][:3]
    return {
        "preferred": f"CANDIDATE_{winner}",
        "reasoning": (
            f"Candidate {winner} is preferred. It fails {fails[winner]} hard-requirement criteria versus "
            f"{fails[loser]} for Candidate {loser}, and its weighted rubric result is {weighted[winner]:.0%} "
            f"versus {weighted[loser]:.0%}. The largest differences are in "
            f"{', '.join(decisive) if decisive else 'no single criterion'}."
        ),
        "decisive_criteria": decisive,
    }


def _improvement(prompt: str) -> dict[str, Any]:
    rows = {label: _parse_results(_section(prompt, "results", label=label)) for label in ("A", "B")}
    preferred = (_section(prompt, "preferred") or "TIE").strip()
    failed = {label: [r for r in rows[label] if not r["passed"]] for label in rows}
    if preferred in ("A", "B") and failed[preferred]:
        target = preferred
    elif preferred in ("A", "B"):
        target = "B" if preferred == "A" else "A"
    else:
        target = "A" if len(failed["A"]) >= len(failed["B"]) else "B"
    weakest = min(rows[target], key=lambda r: (r["norm"], -r["weight"]), default=None)
    if weakest is None:
        return {"target_response": target, "improvement": f"Review Response {target} against the prompt."}
    return {
        "target_response": target,
        "improvement": (
            f"Improve {weakest['name']} in Response {target}: {weakest['reasoning']} "
            "Revise that part of the reply so it fully meets the prompt."
        ),
    }


def _compliance(prompt: str) -> dict[str, Any]:
    response = _section(prompt, "response") or ""
    checks = []
    for req in _parse_requirements(_section(prompt, "requirements")):
        ok, explanation, quote = _judge(req, response)
        checks.append({"requirement_id": req.ref, "satisfied": ok, "explanation": explanation, "quote": quote})
    return {"checks": checks}


_HANDLERS = {
    RequirementExtractionOutput: lambda p: _extract(_section(p, "prompt") or p),
    CriterionEvaluationOutput: _criterion,
    PairwiseComparisonOutput: _pairwise,
    ImprovementOutput: _improvement,
    ComplianceCheckOutput: _compliance,
}


class MockLLMProvider:
    """Deterministic provider for development and tests. Never touches the network."""

    name = "mock"

    def __init__(self, model: str = "mock") -> None:
        self.model = model

    def generate_structured(
        self, prompt: str, schema: type[BaseModel], *, system: str | None = None
    ) -> LLMResponse:
        handler = _HANDLERS.get(schema)
        if handler is None:
            raise NotImplementedError(f"MockLLMProvider has no handler for {schema.__name__}")
        data = handler(prompt)
        raw = json.dumps(data, ensure_ascii=False)
        return LLMResponse(
            data=data,
            raw_text=raw,
            input_tokens=(len(prompt) + len(system or "")) // 4,
            output_tokens=len(raw) // 4,
            latency_ms=1,
        )
