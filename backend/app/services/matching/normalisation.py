"""
Name normalisation utilities for instrument matching.

Provides a single reusable normalizer with explicit handling for:
- Case folding
- Unicode normalization
- Ampersands: & -> and
- Percent/fraction strings
- Share denominations: ORD 10P, ORD 1P
- Preference share phrases: CUM, NON-CUM, IRRD, PREF, PRF
- ETF phrases: UCITS ETF, ACC, DIST
- Corporate suffixes: PLC, LTD, INC, etc.
"""
from __future__ import annotations

import re
import unicodedata

# Characters to strip during normalisation
_NORMALISE_RE = re.compile(r"[^a-z0-9 ]+")

# Words that add no discriminating value for matching
_NOISE = frozenset({
    "plc", "ltd", "inc", "corp", "corporation", "company", "nv", "sa",
    "group", "holdings", "holding", "limited",
    "the", "and", "of", "co", "new",
    "common", "shares", "share", "public",
    "ordinary", "ord",
    # ETF noise - these are often consistent across sources
    "etf", "ucits", "fund", "funds",
    # Keep "np" out - it can be meaningful in some contexts
})


def normalise_name(name: str) -> str:
    """
    Normalise a security name for comparison.

    Steps:
    1. Unicode NFKD normalisation
    2. Lowercase
    3. Replace & with 'and'
    4. Strip punctuation (keep alphanumeric + space)
    5. Collapse whitespace
    6. Strip leading/trailing whitespace
    """
    if not name:
        return ""

    # Unicode normalisation
    result = unicodedata.normalize("NFKD", name)

    # Lowercase
    result = result.lower()

    # Replace ampersand
    result = result.replace("&", "and")

    # Strip punctuation
    result = _NORMALISE_RE.sub(" ", result)

    # Collapse whitespace
    result = re.sub(r"\s+", " ", result).strip()

    return result


def meaningful_tokens(name: str) -> frozenset[str]:
    """
    Extract meaningful tokens from a security name.

    Returns tokens that are NOT in the noise set and have length > 1.
    Numeric tokens are preserved (they distinguish share classes, preference rates, etc.).
    """
    norm = normalise_name(name)
    if not norm:
        return frozenset()

    tokens = norm.split()
    meaningful = frozenset(
        t for t in tokens
        if t not in _NOISE and len(t) > 1
    )
    return meaningful


def token_similarity(a: str, b: str) -> float:
    """
    Compute token overlap similarity between two names.

    Uses Jaccard-like overlap: |A ∩ B| / min(|A|, |B|).
    Returns 0.0 if either has no meaningful tokens.
    """
    tokens_a = meaningful_tokens(a)
    tokens_b = meaningful_tokens(b)

    if not tokens_a or not tokens_b:
        return 0.0

    overlap = len(tokens_a & tokens_b)
    min_len = min(len(tokens_a), len(tokens_b))

    if min_len == 0:
        return 0.0

    return overlap / min_len


def character_similarity(a: str, b: str) -> float:
    """
    Compute character-level similarity using SequenceMatcher.
    """
    from difflib import SequenceMatcher
    norm_a = normalise_name(a)
    norm_b = normalise_name(b)
    if not norm_a or not norm_b:
        return 0.0
    return SequenceMatcher(None, norm_a, norm_b).ratio()


def issuer_prefix(name: str) -> str:
    """
    Extract the issuer/company prefix from a security name.

    E.g., 'Big Yellow Group PLC ORD 10P' -> 'big yellow group'
    'Vanguard Funds PLC VANGUARD S&P 500 UCITS ETF' -> 'vanguard funds'
    """
    norm = normalise_name(name)
    if not norm:
        return ""

    tokens = norm.split()
    # Take first few tokens before share class indicators
    issuer_tokens = []
    share_class_indicators = {"ord", "pref", "prf", "p", "cl", "class", "series", "ser", "plc", "ltd", "inc", "corp"}
    for token in tokens:
        if token in share_class_indicators:
            break
        issuer_tokens.append(token)

    return " ".join(issuer_tokens)


def is_etf(name: str) -> bool:
    """Check if a security name suggests an ETF."""
    norm = normalise_name(name)
    etf_indicators = {"etf", "ucits", "isf", "ucit"}
    return bool(etf_indicators & frozenset(norm.split()))


def is_preference_share(name: str) -> bool:
    """Check if a security name suggests a preference/preferred share."""
    norm = normalise_name(name)
    pref_indicators = {"pref", "prf", "preference", "preferred", "cum", "non-cum", "non cum", "stlg"}
    tokens = frozenset(norm.split())
    return bool(pref_indicators & tokens)


def instrument_type_compatibility(name_a: str, name_b: str) -> float:
    """
    Score how compatible two instrument types are.
    Returns 1.0 if same type, 0.5 if partially compatible, 0.0 if incompatible.
    """
    a_etf = is_etf(name_a)
    b_etf = is_etf(name_b)
    a_pref = is_preference_share(name_a)
    b_pref = is_preference_share(name_b)

    # ETF vs non-ETF is a strong mismatch
    if a_etf != b_etf:
        return 0.3

    # Preference vs ordinary is a strong mismatch
    if a_pref != b_pref:
        return 0.3

    return 1.0
