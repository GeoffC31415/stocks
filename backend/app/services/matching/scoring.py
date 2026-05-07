"""
Scoring engine for instrument matching.

Scores each candidate instrument against an order using multiple dimensions:
- Account match
- Exact normalized name match
- Token similarity
- Character similarity
- Issuer/prefix similarity
- Instrument type compatibility
- Date/closed status compatibility

Returns a score from 0.0 to 1.0 plus detailed evidence.
"""
from __future__ import annotations

import datetime as dt

from app.models import Instrument
from app.services.matching.normalisation import (
    normalise_name,
    token_similarity,
    character_similarity,
    issuer_prefix,
    instrument_type_compatibility,
)

# Score weights
_WEIGHT_ACCOUNT = 0.20
_WEIGHT_EXACT_NAME = 0.25
_WEIGHT_TOKEN = 0.20
_WEIGHT_CHARACTER = 0.10
_WEIGHT_ISSUER = 0.10
_WEIGHT_TYPE_COMPAT = 0.05
_WEIGHT_DATE_COMPAT = 0.05
_WEIGHT_CLOSED_PENALTY = 0.05

# Thresholds
CONFIDENCE_HIGH = 0.92
CONFIDENCE_REVIEW = 0.75


def score_candidate(
    instrument: Instrument,
    order_security_name: str,
    order_account_name: str,
    canonical_account_name: str,
    order_date: dt.datetime | None = None,
) -> tuple[float, dict]:
    """
    Score a candidate instrument against an order.

    Returns (score, evidence_dict) where score is 0.0-1.0.
    """
    evidence: dict = {
        "instrument_id": instrument.id,
        "instrument_name": instrument.security_name,
        "instrument_account": instrument.account_name,
        "order_name": order_security_name,
        "order_account": order_account_name,
        "canonical_account": canonical_account_name,
        "scores": {},
    }

    norm_order = normalise_name(order_security_name)
    norm_inst = normalise_name(instrument.security_name)

    # 1. Account match (does instrument account match canonical order account?)
    account_score = 1.0 if instrument.account_name == canonical_account_name else 0.0
    evidence["scores"]["account"] = account_score

    # 2. Exact normalized name match
    exact_score = 1.0 if norm_order == norm_inst else 0.0
    evidence["scores"]["name_exact"] = exact_score

    # 3. Token similarity
    tok_score = token_similarity(order_security_name, instrument.security_name)
    evidence["scores"]["token_similarity"] = round(tok_score, 4)

    # 4. Character similarity
    char_score = character_similarity(order_security_name, instrument.security_name)
    evidence["scores"]["character_similarity"] = round(char_score, 4)

    # 5. Issuer/prefix similarity
    order_prefix = issuer_prefix(order_security_name)
    inst_prefix = issuer_prefix(instrument.security_name)
    if order_prefix and inst_prefix:
        issuer_score = character_similarity(order_prefix, inst_prefix)
    else:
        issuer_score = 0.0
    evidence["scores"]["issuer_similarity"] = round(issuer_score, 4)

    # 6. Instrument type compatibility (ETF vs ordinary, pref vs ordinary)
    type_score = instrument_type_compatibility(order_security_name, instrument.security_name)
    evidence["scores"]["type_compatibility"] = type_score

    # 7. Date/closed status compatibility
    date_score = 1.0
    if instrument.closed_at is not None:
        if order_date is not None and order_date > instrument.closed_at:
            date_score = 0.0
        else:
            date_score = 0.7  # Partial credit for closed instruments
    evidence["scores"]["date_compatible"] = date_score

    # Weighted combination
    raw_score = (
        account_score * _WEIGHT_ACCOUNT
        + exact_score * _WEIGHT_EXACT_NAME
        + tok_score * _WEIGHT_TOKEN
        + char_score * _WEIGHT_CHARACTER
        + issuer_score * _WEIGHT_ISSUER
        + type_score * _WEIGHT_TYPE_COMPAT
        + date_score * _WEIGHT_DATE_COMPAT
    )

    # Penalize closed instruments (less aggressively so they can still surface as
    # viable matches for historical/order-only securities)
    if instrument.closed_at is not None:
        raw_score = max(0.0, raw_score - _WEIGHT_CLOSED_PENALTY)

    # Boost: exact name match is a strong signal even for closed instruments,
    # since many unmatched orders are for securities no longer in the portfolio
    if exact_score == 1.0 and instrument.closed_at is not None:
        raw_score = max(raw_score, 0.95)

    # Boost for exact matches with same account
    if exact_score == 1.0 and account_score == 1.0:
        raw_score = max(raw_score, 0.95)

    # Boost for exact name match even with different account
    if exact_score == 1.0:
        raw_score = max(raw_score, 0.85)

    score = min(1.0, max(0.0, raw_score))
    evidence["final_score"] = round(score, 4)

    return score, evidence


def classify_score(score: float) -> str:
    """Classify a score into a match status."""
    if score >= CONFIDENCE_HIGH:
        return "auto_high"
    if score >= CONFIDENCE_REVIEW:
        return "auto_review"
    return "unmatched"


def determine_method(score: float, evidence: dict) -> str:
    """Determine the matching method label based on what drove the score."""
    scores = evidence.get("scores", {})
    exact = scores.get("name_exact", 0)
    account = scores.get("account", 0)
    token = scores.get("token_similarity", 0)

    if exact == 1.0 and account == 1.0:
        return "exact_account"
    if exact == 1.0:
        return "exact_cross_account"
    if account == 1.0 and token >= 0.8:
        return "token_account"
    if token >= 0.8:
        return "token_cross_account"
    if account == 1.0 and token >= 0.5:
        return "partial_token_account"
    return "fuzzy"
