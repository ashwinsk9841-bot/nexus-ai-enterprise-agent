"""Business data access for specialist agents (reads ACTUAL stored metrics)."""

from collections import OrderedDict
from typing import Optional

from sqlalchemy.orm import Session

from ..models import BusinessMetric


def metric_summary(
    db: Session,
    metric_type: str,
    *,
    department: str = "All",
) -> Optional[dict]:
    """Compute the latest vs previous period change for a metric from stored rows.

    Rows are grouped by date; the change is calculated between the mean value
    of the two most recent date groups present in the database. Returns None
    when fewer than two periods exist or the metric is unknown — agents then
    report "missing data" instead of inventing values.
    """
    rows = (
        db.query(BusinessMetric)
        .filter(
            BusinessMetric.metric_type == metric_type,
            BusinessMetric.department == department,
        )
        .order_by(BusinessMetric.metric_date.asc())
        .all()
    )
    if not rows:
        return None

    groups: "OrderedDict[str, list[float]]" = OrderedDict()
    for row in rows:
        key = row.metric_date.date().isoformat()
        groups.setdefault(key, []).append(row.value)

    dates = list(groups.keys())
    if len(dates) < 2:
        return None

    prev_label, last_label = dates[-2], dates[-1]
    prev = sum(groups[prev_label]) / len(groups[prev_label])
    last = sum(groups[last_label]) / len(groups[last_label])
    change = ((last - prev) / prev * 100) if prev else 0.0

    return {
        "metric_type": metric_type,
        "latest_value": round(last, 4),
        "previous_value": round(prev, 4),
        "change_pct": round(change, 2),
        "latest_period": last_label,
        "previous_period": prev_label,
        "sample_count": len(rows),
    }


def compute_period_change(
    db: Session, last_value: float, previous_value: float
) -> float:
    if not previous_value:
        return 0.0
    return round((last_value - previous_value) / previous_value * 100, 2)


def available_metric_types(db: Session) -> list[str]:
    rows = (
        db.query(BusinessMetric.metric_type)
        .distinct()
        .all()
    )
    return [r[0] for r in rows]