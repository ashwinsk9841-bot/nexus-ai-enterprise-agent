"""Deterministic business scenario dataset used by demo/tests.

These are the ACTUAL values NEXUS agents analyze. Every metric is stored in
the `business_metrics` table with two period dates so agents compute exactly
the change shown here — no fabricated numbers, no unrelated demo metrics.
"""

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..models import BusinessMetric

PERIOD_1 = datetime(2026, 5, 1, tzinfo=timezone.utc)  # Q2
PERIOD_2 = datetime(2026, 8, 1, tzinfo=timezone.utc)  # Q3

# metric_type: (previous_period_value, latest_period_value)
SCENARIO: dict[str, tuple[float, float]] = {
    "revenue": (5_000_000, 4_900_000),          # -2.0%
    "profit": (1_500_000, 1_250_000),           # -16.67%
    "gross_margin": (45.0, 42.2),               # -2.8 pts
    "expenses": (3_500_000, 3_650_000),         # +4.29%
    "sales": (2_900_000, 2_750_000),            # -5.17%
    "enterprise_sales": (2_400_000, 2_280_000), # -5.0%
    "new_customers": (850, 782),                # -8.0%
    "customer_retention": (87.0, 85.5),         # -1.5 pts
    "marketing_spend": (450_000, 504_000),      # +12.0%
    "conversion": (4.5, 3.7),                   # -17.78%
    "operations_cost": (620_000, 657_200),      # +6.0%
    "cloud_cost": (120_000, 132_000),           # +10.0%
    "support_tickets": (188, 199),              # +5.85%
    "support_high_priority": (27, 31),          # +14.81%
    "support_sentiment": (66.0, 61.4),          # -4.6 pts
    "hr_headcount": (240, 245),                 # +2.08%
    "hr_attrition": (5.2, 5.0),                 # -0.2 pts
}


def apply_scenario(db: Session) -> int:
    """Replace business metrics with the deterministic scenario rows."""
    db.query(BusinessMetric).delete()
    count = 0
    for metric_type, (prev, latest) in SCENARIO.items():
        change = ((latest - prev) / prev * 100) if prev else 0.0
        db.add(
            BusinessMetric(
                metric_date=PERIOD_1,
                metric_type=metric_type,
                value=prev,
                previous_value=prev,
                change_pct=0.0,
                department="All",
            )
        )
        db.add(
            BusinessMetric(
                metric_date=PERIOD_2,
                metric_type=metric_type,
                value=latest,
                previous_value=prev,
                change_pct=round(change, 2),
                department="All",
            )
        )
        count += 2
    db.commit()
    return count


def describe_scenario() -> dict:
    """Metadata describing the loaded scenario (no sensitive data)."""
    return {
        "period_1": PERIOD_1.date().isoformat(),
        "period_2": PERIOD_2.date().isoformat(),
        "metrics": list(SCENARIO.keys()),
        "count": len(SCENARIO),
    }