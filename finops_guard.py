"""
finops_guard.py — lightweight AWS cost anomaly guard.

Pulls the last N days of cost by service from AWS Cost Explorer,
flags services whose week-over-week spend jumped past a threshold,
and can create an AWS Budget alert as a guardrail.

Usage:
    python finops_guard.py --threshold 20 --days 14
    python finops_guard.py --create-budget --budget-limit 5000

Requires: boto3, AWS credentials with ce:GetCostAndUsage and budgets:*
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import date, timedelta


@dataclass
class Anomaly:
    service: str
    last_week: float
    this_week: float
    change_pct: float


class CostGuard:
    def __init__(self, profile: str | None = None, region: str = "us-east-1",
                 threshold_pct: float = 20.0) -> None:
        import boto3  # lazy: import only when actually used

        session = boto3.Session(profile_name=profile) if profile else boto3.Session()
        # Cost Explorer is a global service; us-east-1 is the standard endpoint.
        self.ce = session.client("ce", region_name="us-east-1")
        self.budgets = session.client("budgets", region_name=region)
        self.sts = session.client("sts", region_name=region)
        self.threshold_pct = threshold_pct

    def _daily_cost_by_service(self, start: date, end: date) -> dict[str, list[float]]:
        """Return {service: [daily blended costs]} for the window."""
        resp = self.ce.get_cost_and_usage(
            TimePeriod={"Start": start.isoformat(), "End": end.isoformat()},
            Granularity="DAILY",
            Metrics=["BlendedCost"],
            GroupBy=[{"Type": "DIMENSION", "Key": "SERVICE"}],
        )
        series: dict[str, list[float]] = {}
        for day in resp.get("ResultsByTime", []):
            for g in day.get("Groups", []):
                svc = g["Keys"][0]
                amt = float(g["Metrics"]["BlendedCost"]["Amount"])
                series.setdefault(svc, []).append(amt)
        return series

    def find_anomalies(self, days: int = 14) -> list[Anomaly]:
        """Compare this week vs last week per service; flag big jumps."""
        if days % 2:
            raise ValueError("days must be even so weeks split cleanly")
        end = date.today()
        start = end - timedelta(days=days)
        series = self._daily_cost_by_service(start, end)
        half = days // 2
        out: list[Anomaly] = []
        for svc, daily in series.items():
            if len(daily) < days:
                continue  # partial data — skip rather than mislead
            last_wk, this_wk = sum(daily[:half]), sum(daily[half:])
            if last_wk <= 0:
                change = float("inf") if this_wk > 0 else 0.0
            else:
                change = (this_wk - last_wk) / last_wk * 100
            if change >= self.threshold_pct:
                out.append(Anomaly(svc, last_wk, this_wk, change))
        return sorted(out, key=lambda a: a.change_pct, reverse=True)

    def ensure_budget(self, name: str, limit_usd: float,
                      alert_at_pct: float = 80.0) -> str:
        """Create (or confirm) a monthly cost budget with an actual-spend alert."""
        account_id = self.sts.get_caller_identity()["Account"]
        try:
            self.budgets.create_budget(
                AccountId=account_id,
                Budget={
                    "BudgetName": name,
                    "BudgetLimit": {"Amount": str(limit_usd), "Unit": "USD"},
                    "CostTypes": {"IncludeTax": True, "IncludeSubscription": True,
                                  "UseBlended": False},
                    "TimeUnit": "MONTHLY",
                    "BudgetType": "COST",
                },
                NotificationsWithSubscribers=[{
                    "Notification": {
                        "NotificationType": "ACTUAL",
                        "ComparisonOperator": "GREATER_THAN",
                        "Threshold": alert_at_pct,
                        "ThresholdType": "PERCENTAGE",
                    },
                    "Subscribers": [{"SubscriptionType": "EMAIL",
                                     "Address": "finops@example.com"}],
                }],
            )
            return f"created budget '{name}' (${limit_usd:,.0f}/mo, alert at {alert_at_pct:.0f}%)"
        except Exception as exc:  # noqa: BLE001 — surface AWS errors plainly
            if "already exists" in str(exc).lower() or "Duplicate" in type(exc).__name__:
                return f"budget '{name}' already exists — nothing to do"
            raise


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="AWS cost anomaly guard")
    p.add_argument("--profile", default=None, help="AWS CLI profile name")
    p.add_argument("--threshold", type=float, default=20.0,
                   help="WoW increase %% that counts as an anomaly")
    p.add_argument("--days", type=int, default=14, help="lookback window (even number)")
    p.add_argument("--create-budget", action="store_true",
                   help="create a monthly guardrail budget")
    p.add_argument("--budget-limit", type=float, default=5000.0)
    p.add_argument("--budget-name", default="monthly-guardrail")
    args = p.parse_args(argv)

    guard = CostGuard(profile=args.profile, threshold_pct=args.threshold)
    anomalies = guard.find_anomalies(days=args.days)
    if not anomalies:
        print(f"✅ No service jumped more than {args.threshold:.0f}% week-over-week.")
    else:
        print(f"🚨 {len(anomalies)} anomal{'y' if len(anomalies) == 1 else 'ies'} detected:")
        for a in anomalies:
            print(f"   {a.service}: ${a.last_week:,.2f} → ${a.this_week:,.2f} "
                  f"({a.change_pct:+.1f}%)")

    if args.create_budget:
        print(guard.ensure_budget(args.budget_name, args.budget_limit))

    return 1 if anomalies else 0


if __name__ == "__main__":
    sys.exit(main())
