"""Thresholds, limits and (from Phase 3) model ids and env switches."""
from __future__ import annotations

# Red-flag fuzzy matching (D-014): a token window must reach this RapidFuzz ratio,
# and tokens shorter than FUZZY_MIN_TOKEN_LEN must match exactly ("can" != "cant").
FUZZY_THRESHOLD = 88
FUZZY_MIN_TOKEN_LEN = 4
