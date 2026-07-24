"""Time helpers.

The app stores timestamps in **naive** (tz-less) UTC ``DateTime`` columns — see the
design note in ``app/models/billing.py`` about SQLite ``CURRENT_TIMESTAMP`` truncation,
and the many ``column < utcnow()`` comparisons in the billing/entitlements paths. Mixing
an aware ``datetime.now(timezone.utc)`` into those comparisons would raise
"can't compare offset-naive and offset-aware datetimes".

``utcnow()`` is therefore the drop-in replacement for the deprecated
``datetime.utcnow()``: it returns the **same naive-UTC value** without emitting a
``DeprecationWarning``, so every existing comparison and stored value keeps working
byte-for-byte. Use ``utcnow_aware()`` only in new code that deliberately wants an
aware datetime.
"""
from __future__ import annotations

from datetime import datetime, timezone


def utcnow() -> datetime:
    """Naive UTC ``now`` (tzinfo stripped). Drop-in for the deprecated ``datetime.utcnow()``."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def utcnow_aware() -> datetime:
    """Timezone-aware UTC ``now`` — for new code paths that want aware datetimes."""
    return datetime.now(timezone.utc)
