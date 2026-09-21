"""Agent selection, execution, and RAG core tests."""

import pytest

from app.agents import (
    build_agent,
    select_agents_for_query,
    FinanceAgent,
)
from app.ai.service import cosine_similarity, generate_embedding
from app.ai.rag import chunk_text
from app.services.orchestrator import Orchestrator


def test_select_agents_for_revenue_query():
    agents = select_agents_for_query("Why is revenue lower this month?")
    keys = [a.key for a in agents]
    assert "finance" in keys


def test_select_agents_for_latency_query():
    keys = [a.key for a in select_agents_for_query("Why is API latency increasing?")]
    assert "devops" in keys


def test_select_agents_for_security_query():
    keys = [a.key for a in select_agents_for_query("Show security events today")]
    assert "security" in keys


def test_select_agents_default():
    agents = select_agents_for_query("Tell me something")
    assert agents  # falls back to a working set


def test_agent_run_returns_findings():
    agent = FinanceAgent()
    result = agent.run("analyze revenue", {"agent_sources": []})
    assert result["agent"] == "finance"
    assert "summary" in result
    assert result["details"]["revenue"]["change_pct"] is not None
    assert result["status"] == "SUCCESS"
    assert any(o["metric"] == "revenue" for o in result["observations"])


def test_unknown_agent_raises():
    with pytest.raises(ValueError):
        build_agent("nonexistent")


def test_chunk_text_basic():
    text = "word " * 5000
    chunks = chunk_text(text)
    assert len(chunks) > 1
    assert all(chunk for chunk in chunks)


def test_fallback_embedding_consistent():
    a1 = generate_embedding("alpha beta gamma")
    a2 = generate_embedding("alpha beta gamma")
    b = generate_embedding("something else entirely")
    assert a1 == a2  # deterministic fallback
    assert len(a1) == 1536
    assert cosine_similarity(a1, a2) == pytest.approx(1.0)
    assert cosine_similarity(a1, b) < 0.95


def test_cosine_similarity_helpers():
    assert cosine_similarity([1, 0], [1, 0]) == 1.0
    assert cosine_similarity([1, 0], [0, 1]) == 0.0
    assert cosine_similarity([], [1]) == 0.0


def test_orchestrator_runs_and_persists():
    orch = Orchestrator(user_id="1", username="tester")
    result = orch.run("Why is revenue down?")
    assert result["status"] == "COMPLETED"
    assert result["agents_activated"]
    assert result["result"]
    assert result["session_id"]