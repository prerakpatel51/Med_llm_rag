"""
trust_scorer.py – computes a trust score (0.0–1.0) for a document at ingestion time.

The score is a weighted average of four sub-scores:
  - Source authority  (35%): who published it?
  - Publication type  (30%): RCT > review > case report
  - Recency           (20%): newer articles score higher
  - Citation count    (15%): more citations = higher credibility

The score is stored on the Document row and copied to each Chunk.
"""
import math
from datetime import datetime, timezone


# ── Source authority scores ───────────────────────────────────────────────────
# These are fixed values for known trusted sources.

SOURCE_AUTHORITY = {
    "cdc": 1.0,
    "who": 1.0,
    "fda": 1.0,
    "nih": 0.95,
    "pubmed": 0.80,
    "pmc": 0.65,
    "preprint": 0.30,
}

# Publication type scores based on evidence hierarchy
PUBLICATION_TYPE_SCORES = {
    "randomized controlled trial": 1.0,
    "meta-analysis": 0.95,
    "systematic review": 0.95,
    "clinical trial": 0.85,
    "review": 0.70,
    "case report": 0.40,
    "unknown": 0.50,
}


def score_source_authority(source: str) -> float:
    """Return authority score for the given source name."""
    return SOURCE_AUTHORITY.get(source.lower(), 0.60)


def score_publication_type(pub_type: str) -> float:
    """Return evidence-hierarchy score for this publication type."""
    pub_type_lower = pub_type.lower()
    # Check for partial matches (e.g. "Randomized Controlled Trial, Phase II")
    for key, score in PUBLICATION_TYPE_SCORES.items():
        if key in pub_type_lower:
            return score
    return 0.50


def score_recency(published_at: datetime | None) -> float:
    """
    Exponential decay: score = exp(-0.139 * years_ago)
    Half-life is 5 years, so an article from 5 years ago scores 0.5.
    """
    if published_at is None:
        return 0.50   # unknown date → neutral
    now = datetime.now(timezone.utc)
    # make published_at timezone-aware if it isn't already
    if published_at.tzinfo is None:
        published_at = published_at.replace(tzinfo=timezone.utc)
    years_ago = (now - published_at).days / 365.25
    years_ago = max(0.0, years_ago)   # clamp negative (future date edge case)
    return math.exp(-0.139 * years_ago)


def score_citations(citation_count: int) -> float:
    """
    Log-normalized citation count.
    10 000 citations → 1.0, 1 citation → 0.25, 0 citations → 0.0
    """
    return min(math.log10(citation_count + 1) / 4.0, 1.0)


def compute_trust_score(
    source: str,
    publication_type: str,
    published_at: datetime | None,
    citation_count: int = 0,
) -> float:
    """
    Compute the composite trust score (0.0–1.0).
    Call this once at ingestion time and store the result.
    """
    authority = score_source_authority(source)
    pub_type = score_publication_type(publication_type)
    recency = score_recency(published_at)

    # CDC/WHO/FDA don't have citation counts in our pipeline; default to 0.8
    if source.lower() in ("cdc", "who", "fda", "nih"):
        citations = 0.80
    else:
        citations = score_citations(citation_count)

    trust = (
        0.35 * authority
        + 0.30 * pub_type
        + 0.20 * recency
        + 0.15 * citations
    )
    # Round to 2 decimal places for clean storage
    return round(min(max(trust, 0.0), 1.0), 2)


def trust_tier(score: float) -> str:
    """Convert a numeric trust score to a tier label shown in the UI."""
    if score >= 0.80:
        return "A"
    elif score >= 0.60:
        return "B"
    else:
        return "C"
