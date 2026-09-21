"""Specialist NEXUS agents with real provider integration and ACTUAL data usage.

Every agent reads stored business metrics, delegates its LLM interpretation to
a configured AI provider, and — when no provider is configured or data is
missing — reports deterministically with full transparency (no invented values).
"""

import json
import logging
import time
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session as OrmSession

from ..ai.providers import provider_for_agent
from ..database.session import SessionLocal
from ..models import Agent, AgentConfig, AgentRun
from ..services.business_data import metric_summary

logger = logging.getLogger("nexus.agents")


class BaseAgent(ABC):
    key: str = "base"
    name: str = "Base Agent"
    description: str = ""
    capability: str = ""
    metric_types: list[str] = []
    domain: str = "general"

    @abstractmethod
    def run(self, query: str, context: dict) -> dict:
        ...

    # ---- shared internals -------------------------------------------------
    def _config(self, db: OrmSession) -> AgentConfig:
        cfg = db.get(AgentConfig, self.key)
        return cfg

    def _metrics(self, db: OrmSession) -> tuple[list[dict], list[str]]:
        present = []
        for metric_type in self.metric_types:
            m = metric_summary(db, metric_type)
            if m:
                present.append(m)
        present_types = {m["metric_type"] for m in present}
        missing = [t for t in self.metric_types if t not in present_types]
        return present, missing

    def _interprets(self, query: str, metrics: list[dict], provider) -> str | None:
        """Ask the configured provider for a data-grounded interpretation."""
        if provider is None:
            return None
        payload = [
            {
                "metric_type": m["metric_type"],
                "latest_value": m["latest_value"],
                "previous_value": m["previous_value"],
                "change_pct": m["change_pct"],
                "latest_period": m["latest_period"],
            }
            for m in metrics
        ]
        messages = [
            {
                "role": "system",
                "content": (
                    f"You are the {self.name} within NEXUS. Interpret the question "
                    "strictly using ONLY the supplied business metrics. Never invent "
                    "numbers. Give an executive analysis (2-4 sentences) citing the "
                    "actual figures and the direction of change."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"QUESTION:\n{query}\n\n"
                    f"BUSINESS METRICS (values are real, retrieved from the company "
                    f"dataset):\n{json.dumps(payload, indent=2)}"
                ),
            },
        ]
        try:
            return provider.complete(messages, temperature=0.3, max_tokens=400)
        except Exception as exc:  # pragma: no cover - provider failure path
            logger.warning("Agent %s: provider interpretation failed (%s)", self.key, exc)
            return None

    def _summarize(self, query, present, missing, interpretation, ai_mode, enabled) -> str:
        parts = [f"{self.name}:"]
        for m in present:
            parts.append(
                f"{m['metric_type']} {m['change_pct']:+.2f}% "
                f"({m['metric_type']}: {m['latest_value']:,.4g} vs {m['previous_value']:,.4g})"
            )
        if interpretation:
            summary = interpretation
        elif ai_mode:
            summary = (
                f"{self.name} completed a data-grounded check (no LLM interpretation "
                "returned): " + "; ".join(parts)
            )
        else:
            summary = "; ".join(parts)
        if missing:
            summary += f" | Missing data: {', '.join(missing)}"
        if not enabled:
            summary += " | Agent disabled by admin."
        return summary[:1500]

    def _confidence(self, present, ai_mode) -> float:
        coverage = len(present) / max(len(self.metric_types) or 1, 1)
        confidence = 0.3 + 0.6 * coverage
        if ai_mode:
            confidence += 0.05
        if not present:
            confidence = 0.1
        return round(min(confidence, 0.95), 2)

    def _track(self, db, *, query, task, status, output=None, error=None, duration_ms=0):
        try:
            agent = db.query(Agent).filter(Agent.key == self.key).first()
            if not agent:
                agent = Agent(
                    key=self.key,
                    name=self.name,
                    description=self.description,
                    capability=self.capability,
                    status="IDLE",
                    current_task="",
                    success_rate=0.0,
                    avg_response_ms=0,
                    last_execution=None,
                    executions_total=0,
                    executions_success=0,
                )
                db.add(agent)
                db.flush()
            agent.last_execution = datetime.now(timezone.utc)
            agent.executions_total += 1
            agent.current_task = (task or "")[:500]
            if status == "SUCCESS":
                agent.executions_success += 1
                agent.success_rate = round(
                    agent.executions_success / max(agent.executions_total, 1) * 100, 1
                )
                agent.status = "ONLINE"
                agent.avg_response_ms = round(
                    (agent.avg_response_ms + duration_ms) / 2
                ) if agent.avg_response_ms else duration_ms
            else:
                agent.status = "ERROR"
            db.add(
                AgentRun(
                    agent_id=agent.id,
                    query=query,
                    task=(task or ""),
                    status=status,
                    output_data=json.dumps(output, default=str)[:4000] if output else "",
                    error_message=(error or ""),
                    duration_ms=duration_ms or 0,
                    started_at=datetime.now(timezone.utc)
                    - timedelta(milliseconds=max(duration_ms or 0, 0)),
                    completed_at=datetime.now(timezone.utc),
                )
            )
            db.commit()
        except Exception:
            logger.exception("Agent tracking failed for %s", self.key)
            try:
                db.rollback()
            except Exception:
                pass


class FinanceAgent(BaseAgent):
    key = "finance"
    name = "Finance Agent"
    description = "Revenue, expenses, profit, gross margin, and financial trends."
    capability = "finance"
    metric_types = ["revenue", "profit", "gross_margin", "expenses"]
    domain = "finance"

    def run(self, query, context):
        return self._standard_run(query)


class SalesAgent(BaseAgent):
    key = "sales"
    name = "Sales Agent"
    description = "Sales, new customer acquisition, enterprise deals, retention."
    capability = "sales"
    metric_types = ["sales", "enterprise_sales", "new_customers", "customer_retention"]
    domain = "sales"

    def run(self, query, context):
        return self._standard_run(query)


class MarketingAgent(BaseAgent):
    key = "marketing"
    name = "Marketing Agent"
    description = "Marketing spend efficiency, conversion rates, funnel health."
    capability = "marketing"
    metric_types = ["marketing_spend", "conversion"]
    domain = "marketing"

    def run(self, query, context):
        return self._standard_run(query)


class DevopsAgent(BaseAgent):
    key = "devops"
    name = "Operations Agent"
    description = "Infrastructure performance, cloud costs, latency, and reliability."
    capability = "operations"
    metric_types = ["operations_cost", "cloud_cost"]
    domain = "operations"

    def run(self, query, context):
        db = SessionLocal()
        try:
            present, missing = self._metrics(db)
            present.extend(self._system_metrics(db))
            cfg = self._config(db)
            provider = provider_for_agent(self.key, cfg.provider if cfg else "")
            ai_mode = provider is not None
            interpretation = self._interprets(query, present, provider)
            summary = self._summarize(query, present, missing, interpretation, ai_mode, cfg.enabled if cfg else True)
            confidence = self._confidence(present, ai_mode)
            start = context.get("_started_at", time.time())
            result = self._result(query, present, missing, interpretation, summary, confidence, provider, bool(cfg and not cfg.enabled), int((time.time() - start) * 1000))
            self._track(db, query=query, task=self.name, status="SUCCESS", output=result, duration_ms=result["duration_ms"])
            return result
        finally:
            db.close()

    def _system_metrics(self, db: OrmSession) -> list[dict]:
        from ..models import SystemMetric
        rows = (
            db.query(SystemMetric)
            .order_by(SystemMetric.timestamp.desc())
            .limit(20)
            .all()
        )
        if not rows:
            return []
        lat = [r.api_latency_ms for r in rows if r.api_latency_ms is not None]
        return [
            {
                "metric_type": "avg_api_latency_ms",
                "latest_value": round(sum(lat) / len(lat), 1) if lat else 0.0,
                "previous_value": 0.0,
                "change_pct": 0.0,
                "latest_period": "recent 20 samples",
            }
        ]


class SupportAgent(BaseAgent):
    key = "support"
    name = "Customer/Support Agent"
    description = "Support tickets, high-priority cases, and customer sentiment."
    capability = "support"
    metric_types = ["support_tickets", "support_high_priority", "support_sentiment"]
    domain = "support"

    def run(self, query, context):
        return self._standard_run(query)


class HRAgent(BaseAgent):
    key = "hr"
    name = "HR Agent"
    description = "Headcount, attrition, and workforce metrics."
    capability = "hr"
    metric_types = ["hr_headcount", "hr_attrition"]
    domain = "hr"

    def run(self, query, context):
        return self._standard_run(query)


class RiskAgent(BaseAgent):
    key = "risk"
    name = "Risk Agent"
    description = "Risk posture, security events, and cost exposure."
    capability = "risk"
    metric_types = ["cloud_cost", "support_sentiment"]
    domain = "risk"

    def run(self, query, context):
        db = SessionLocal()
        try:
            present, missing = self._metrics(db)
            risk_evidence = self._security_evidence(db)
            present.extend(risk_evidence)
            cfg = self._config(db)
            provider = provider_for_agent(self.key, cfg.provider if cfg else "")
            ai_mode = provider is not None
            interpretation = self._interprets(query, present, provider)
            parts = [f"{self.name}:"]
            for m in present:
                parts.append(f"{m['metric_type']} {m['change_pct']:+.2f}%" if m["change_pct"] else f"{m['metric_type']} {m['latest_value']}")
            if interpretation:
                summary = interpretation
            elif ai_mode:
                summary = "; ".join(parts)
            else:
                summary = "; ".join(parts)
            confidence = self._confidence(present, ai_mode)
            start = context.get("_started_at", time.time())
            result = self._result(query, present, missing, interpretation, summary, confidence, provider, bool(cfg and not cfg.enabled), int((time.time() - start) * 1000))
            self._track(db, query=query, task=self.name, status="SUCCESS", output=result, duration_ms=result["duration_ms"])
            return result
        finally:
            db.close()

    def _security_evidence(self, db: OrmSession) -> list[dict]:
        from ..models import SecurityEvent
        rows = db.query(SecurityEvent).all()
        counts: dict[str, int] = {}
        for r in rows:
            sev = r.severity or "UNKNOWN"
            counts[sev] = counts.get(sev, 0) + 1
        if not counts:
            return []
        return [
            {
                "metric_type": "security_events",
                "latest_value": sum(counts.values()),
                "previous_value": 0.0,
                "change_pct": 0.0,
                "latest_period": json.dumps(counts),
            }
        ]


class MarketAgent(BaseAgent):
    key = "market"
    name = "Market/External Factors Agent"
    description = "Market conditions, competitors, and external factors."
    capability = "market"
    metric_types = []
    domain = "market"

    def run(self, query, context):
        db = SessionLocal()
        try:
            cfg = self._config(db)
            provider = provider_for_agent(self.key, cfg.provider if cfg else "")
            summary = (
                "Market/External Factors Agent: no external market or competitor data "
                "source is connected, so external factors cannot be assessed from data. "
                "Integrate a market data feed to enable this analysis."
            )
            result = self._result(
                query,
                [],
                ["external_market_data", "competitor_data"],
                None,
                summary,
                0.1,
                provider,
                bool(cfg and not cfg.enabled),
                0,
            )
            self._track(db, query=query, task=self.name, status="SUCCESS", output=result, duration_ms=0)
            return result
        finally:
            db.close()


class ForecastAgent(BaseAgent):
    key = "forecast"
    name = "Forecast Agent"
    description = "Projections and forward-looking estimates from observed trends."
    capability = "forecast"
    metric_types = ["revenue", "conversion"]
    domain = "forecast"

    def run(self, query, context):
        db = SessionLocal()
        try:
            present, missing = self._metrics(db)
            cfg = self._config(db)
            provider = provider_for_agent(self.key, cfg.provider if cfg else "")
            forecast = self._build_forecast(present)
            ai_mode = provider is not None
            interpretation = self._interprets(query, present, provider)
            summary = (
                f"{self.name}: based on observed revenue change "
                f"({forecast['revenue_change_pct']:+.2f}%), the next-period projection is "
                f"≈{forecast['projected_value']:,.0f}. This is an ESTIMATE, not a forecast "
                "of fact."
            )
            if interpretation:
                summary = interpretation + " " + summary
            result = self._result(query, present, missing, interpretation, summary, round(self._confidence(present, False) * 0.85, 2), provider, bool(cfg and not cfg.enabled), 0)
            result["forecast"] = {
                "label": "NEXT PERIOD PROJECTION (estimate)",
                "method": "linear extrapolation of latest observed change",
                **forecast,
            }
            self._track(db, query=query, task=self.name, status="SUCCESS", output=result, duration_ms=0)
            return result
        finally:
            db.close()

    def _build_forecast(self, present: list[dict]) -> dict:
        rev = next((m for m in present if m["metric_type"] == "revenue"), None)
        if not rev:
            return {
                "revenue_change_pct": 0.0,
                "projected_value": 0.0,
                "note": "No revenue data available for projection.",
            }
        projected = rev["latest_value"] * (1 + rev["change_pct"] / 100)
        return {
            "revenue_change_pct": rev["change_pct"],
            "projected_value": round(projected, 2),
            "latest_value": rev["latest_value"],
        }


class SecurityAgent(BaseAgent):
    key = "security"
    name = "Security Agent"
    description = "Authentication logs, suspicious activity, and security events."
    capability = "security"
    metric_types = []
    domain = "security"

    def run(self, query, context):
        db = SessionLocal()
        try:
            counts, critical = self._event_stats(db)
            cfg = self._config(db)
            provider = provider_for_agent(self.key, cfg.provider if cfg else "")
            ai_mode = provider is not None
            evidence = [
                {
                    "metric_type": "security_events",
                    "latest_value": counts["total"],
                    "previous_value": 0.0,
                    "change_pct": 0.0,
                    "latest_period": json.dumps(counts),
                }
            ]
            interpretation = self._interprets(query, evidence, provider)
            summary = (
                f"{self.name}: {counts['total']} security events currently tracked "
                f"(critical={counts.get('CRITICAL', 0)}, high={counts.get('HIGH', 0)})."
            )
            if interpretation:
                summary = interpretation
            result = self._result(query, evidence, [] if counts["total"] else ["security_event_data"], interpretation, summary, 0.8 if counts["total"] else 0.15, provider, bool(cfg and not cfg.enabled), 0)
            self._track(db, query=query, task=self.name, status="SUCCESS", output=result, duration_ms=0)
            return result
        finally:
            db.close()

    def _event_stats(self, db: OrmSession) -> tuple[dict, int]:
        from ..models import SecurityEvent
        rows = db.query(SecurityEvent).all()
        counts: dict[str, int] = {}
        critical = 0
        for r in rows:
            sev = (r.severity or "UNKNOWN").upper()
            counts[sev] = counts.get(sev, 0) + 1
            if sev in ("CRITICAL", "HIGH"):
                critical += 1
        counts["total"] = sum(v for k, v in counts.items() if k != "total")
        return counts, critical


# ---- runner ---------------------------------------------------------------

def _standard_run(agent: BaseAgent, query: str) -> dict:
    db = SessionLocal()
    start = time.time()
    try:
        present, missing = agent._metrics(db)
        cfg = agent._config(db)
        provider = provider_for_agent(agent.key, cfg.provider if cfg else "")
        ai_mode = provider is not None
        interpretation = agent._interprets(query, present, provider)
        summary = agent._summarize(
            query, present, missing, interpretation, ai_mode, bool(cfg and not cfg.enabled)
        )
        confidence = agent._confidence(present, ai_mode)
        duration = int((time.time() - start) * 1000)
        result = agent._result(
            query, present, missing, interpretation, summary,
            confidence, provider, bool(cfg and not cfg.enabled), duration,
        )
        agent._track(db, query=query, task=agent.name, status="SUCCESS", output=result, duration_ms=duration)
        return result
    finally:
        db.close()


def _build_result(agent, query, present, missing, interpretation, summary, confidence, provider, disabled, duration_ms):
    provider_meta = provider.metadata() if provider else {"provider": "unconfigured", "model": "", "configured": False}
    return {
        "agent": agent.key,
        "name": agent.name,
        "domain": agent.domain,
        "provider": provider_meta["provider"],
        "model": provider_meta["model"],
        "mode": "ai" if (provider and interpretation) else "data",
        "enabled": not disabled,
        "status": "SUCCESS",
        "confidence": confidence,
        "summary": summary,
        "observations": [
            {
                "metric": m["metric_type"],
                "latest_value": m["latest_value"],
                "previous_value": m["previous_value"],
                "change_pct": m["change_pct"],
                "latest_period": m.get("latest_period", ""),
            }
            for m in present
        ],
        "details": {
            m["metric_type"]: {
                "value": m["latest_value"],
                "previous": m["previous_value"],
                "change_pct": m["change_pct"],
            }
            for m in present
        },
        "sources": [
            {"type": "business_metric", "metric": m["metric_type"], "period": m.get("latest_period", "")}
            for m in present
        ],
        "missing_data": missing,
        "interpretation": interpretation,
        "duration_ms": duration_ms,
    }


BaseAgent._result = _build_result
BaseAgent._standard_run = _standard_run


AGENT_REGISTRY: dict[str, type[BaseAgent]] = {
    "finance": FinanceAgent,
    "sales": SalesAgent,
    "marketing": MarketingAgent,
    "devops": DevopsAgent,
    "support": SupportAgent,
    "hr": HRAgent,
    "risk": RiskAgent,
    "market": MarketAgent,
    "forecast": ForecastAgent,
    "security": SecurityAgent,
}


def all_agent_classes() -> list[type[BaseAgent]]:
    return list(AGENT_REGISTRY.values())


def build_agent(key: str) -> BaseAgent:
    cls = AGENT_REGISTRY.get(key)
    if not cls:
        raise ValueError(f"Unknown agent: {key}")
    return cls()


def select_agents_for_query(query: str) -> list[BaseAgent]:
    """Select the relevant specialist agents for a user question (never all)."""
    q = query.lower()
    chosen: list[str] = []

    def add(key: str):
        if key not in chosen:
            chosen.append(key)

    # Primary domain triggers
    if any(k in q for k in ["revenue", "profit", "margin", "gross margin", "expense", "cost", "finance", "budget", "spend", "cash"]):
        add("finance")
        add("sales")
        add("marketing")
        add("support")
        add("forecast")
    if any(k in q for k in ["sale", "sales", "pipeline", "deal", "enterprise", "quote", "win rate", "renewal", "acquisition"]):
        add("sales")
    if any(k in q for k in ["marketing", "campaign", "conversion", "lead", "ad spend", "traffic", "funnel", "cac"]):
        add("marketing")
    if any(k in q for k in ["ticket", "support", "customer", "retention", "churn", "sentiment", "csat", "nps", "complaint", "call"]):
        add("support")
    if any(k in q for k in ["hr", "employee", "headcount", "attrition", "hire", "people", "staff", "turnover", "workforce"]):
        add("hr")
    if any(k in q for k in ["security", "auth", "login", "attack", "breach", "phish", "vulnerab", "malware", "ransom"]):
        add("security")
        add("risk")
    if any(k in q for k in ["latency", "api", "server", "infrastructure", "performance", "cloud", "outage", "uptime", "devops", "deploy", "availability"]):
        add("devops")
    if any(k in q for k in ["risk", "compliance", "regulation", "audit", "policy", "exposure", "governance"]):
        add("risk")
    if any(k in q for k in ["market", "competitor", "competition", "external", "industry", "macro", "economy", "survey"]):
        add("market")
    if any(k in q for k in ["forecast", "projection", "predict", "next quarter", "outlook", "future"]):
        add("forecast")

    # Financial/performance questions always benefit from forecast + operations context
    if any(k in q for k in ["revenue", "profit", "sales", "conversion", "growth", "declin", "decreas", "drop", "why", "reason", "trend"]):
        add("forecast")
        add("devops")

    if not chosen:
        chosen = ["finance", "sales", "marketing", "devops", "forecast"]

    if "security" not in chosen and not any(
        k in q for k in ["revenue", "sales", "marketing", "conversion", "customer", "hr", "headcount", "forecast"]
    ):
        pass  # keep security out of pure business questions

    return [build_agent(k) for k in chosen[:7]]