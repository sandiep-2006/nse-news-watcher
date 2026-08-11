"""Keyword-based bullish/bearish scorer for a news headline+summary.

Deliberately simple and free (no per-article API call, no model to run): a
weighted phrase lexicon, scored and normalized. This is a heuristic screen,
NOT a validated statistical edge - unlike every strategy in this project
(see SESSION_STATUS.md), it has not been backtested against actual forward
returns. Treat its "confidence" as a rough read-the-headline signal to
prioritize what to look at, not a probability in the project's usual sense.
Swapping this module for an LLM-based reader later is a drop-in upgrade -
callers only depend on `score_text()`'s return shape.
"""
from __future__ import annotations

NEUTRAL_BAND = 0.15  # |net| below this -> "neutral", no alert fires

POSITIVE_PHRASES: dict[str, int] = {
    "beats estimates": 3,
    "beats street": 3,
    "record profit": 3,
    "record revenue": 2,
    "profit jumps": 2,
    "profit rises": 2,
    "profit soars": 3,
    "revenue growth": 1,
    "strong growth": 2,
    "raises guidance": 3,
    "upgraded": 2,
    "upgrade": 2,
    "buy rating": 2,
    "outperform": 2,
    "target price raised": 3,
    "target price hiked": 3,
    "wins order": 2,
    "wins contract": 2,
    "bags order": 2,
    "bags contract": 2,
    "new order": 1,
    "signs deal": 1,
    "expansion plan": 1,
    "expands capacity": 1,
    "buyback": 2,
    "bonus issue": 2,
    "special dividend": 2,
    "interim dividend": 1,
    "stake acquisition": 1,
    "surge": 2,  # substring match also covers surges/surged/surging
    "rally": 2,
    "rallies": 2,  # "rally" doesn't cover this irregular plural, list separately
    "jump": 1,  # covers jumps/jumped/jumping
    "hits 52-week high": 3,
    "all-time high": 3,
    "strong demand": 1,
    "capacity expansion": 1,
    "approval granted": 1,
    "fda approval": 2,
    "block deal": 1,
}

NEGATIVE_PHRASES: dict[str, int] = {
    "misses estimates": 3,
    "profit falls": 2,
    "profit drops": 2,
    "profit plunges": 3,
    "loss widens": 3,
    "reports loss": 2,
    "downgraded": 2,
    "downgrade": 2,
    "sell rating": 2,
    "underperform": 2,
    "target price cut": 3,
    "guidance cut": 3,
    "weak guidance": 2,
    "sebi probe": 3,
    "sebi action": 2,
    "fraud": 3,
    "scam": 3,
    "raid": 2,
    "raided": 2,
    "resigns": 2,
    "resignation": 1,
    "steps down": 1,
    "default": 3,
    "debt concerns": 2,
    "rating downgrade": 3,
    "credit rating cut": 3,
    "plunge": 2,  # substring match also covers plunges/plunged/plunging
    "slump": 2,
    "crash": 3,
    "tumble": 2,
    "hits 52-week low": 3,
    "strike": 1,
    "lawsuit": 1,
    "penalty": 2,
    "fine imposed": 2,
    "regulatory action": 2,
    "production halt": 2,
    "plant shutdown": 2,
    "recall": 2,
    "job cuts": 1,
    "layoffs": 1,
    "profit warning": 3,
    "shares fall": 1,
    "shares fell": 1,
    "shares decline": 1,
    "insider selling": 1,
    "probe launched": 2,
}


def score_text(title: str, summary: str = "") -> dict:
    """Returns {"direction": "bullish"|"bearish"|"neutral", "confidence": 0..1,
    "reason": str, "engine": "keyword", "matched_positive": [...],
    "matched_negative": [...]}.

    Title counts double weight - headlines carry more signal than boilerplate
    summary text, and this keeps a strong headline word from getting diluted
    by a long, mostly-neutral summary paragraph.
    """
    title_lower = (title or "").lower()
    summary_lower = (summary or "").lower()

    pos_score = 0
    neg_score = 0
    matched_pos: list[str] = []
    matched_neg: list[str] = []

    for phrase, weight in POSITIVE_PHRASES.items():
        hits = (2 if phrase in title_lower else 0) + (1 if phrase in summary_lower else 0)
        if hits:
            pos_score += weight * hits
            matched_pos.append(phrase)

    for phrase, weight in NEGATIVE_PHRASES.items():
        hits = (2 if phrase in title_lower else 0) + (1 if phrase in summary_lower else 0)
        if hits:
            neg_score += weight * hits
            matched_neg.append(phrase)

    total = pos_score + neg_score
    if total == 0:
        return {
            "direction": "neutral",
            "confidence": 0.0,
            "reason": "",
            "engine": "keyword",
            "matched_positive": [],
            "matched_negative": [],
        }

    net = (pos_score - neg_score) / total  # -1..1
    if net > NEUTRAL_BAND:
        direction = "bullish"
    elif net < -NEUTRAL_BAND:
        direction = "bearish"
    else:
        direction = "neutral"

    # Confidence blends (a) how one-sided the matched phrases are and (b) how
    # much evidence there is, capped well short of 1.0 - this is a keyword
    # heuristic, not a calibrated probability, and should never claim
    # near-certainty.
    confidence = min(0.85, 0.30 + 0.05 * total + 0.25 * abs(net))
    reason = ", ".join((matched_pos if direction == "bullish" else matched_neg)[:3])

    return {
        "direction": direction,
        "confidence": round(confidence, 3),
        "reason": reason,
        "engine": "keyword",
        "matched_positive": matched_pos,
        "matched_negative": matched_neg,
    }
