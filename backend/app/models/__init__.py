from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    Float,
)
from sqlalchemy.orm import relationship

from ..database.session import Base


def utcnow():
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    username = Column(String(120), unique=True, index=True, nullable=False)
    full_name = Column(String(255), nullable=False, default="")
    hashed_password = Column(String(512), nullable=False)
    role = Column(String(32), nullable=False, default="VIEWER")
    is_active = Column(Boolean, default=True)
    demo_account = Column(Boolean, default=False)
    organization = Column(String(255), default="")
    must_change_password = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=utcnow)
    last_login = Column(DateTime(timezone=True), nullable=True)

    audit_logs = relationship("AuditLog", back_populates="user")
    approvals = relationship("ApprovalRequest", back_populates="user")
    notifications = relationship("Notification", back_populates="user")
    sessions = relationship("Session", back_populates="user", cascade="all, delete-orphan")


class Agent(Base):
    __tablename__ = "agents"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(64), unique=True, index=True, nullable=False)
    name = Column(String(120), nullable=False)
    description = Column(Text, default="")
    capability = Column(String(255), default="")
    status = Column(String(32), default="IDLE")
    current_task = Column(String(500), default="")
    success_rate = Column(Float, default=0.0)
    avg_response_ms = Column(Integer, default=0)
    last_execution = Column(DateTime(timezone=True), nullable=True)
    executions_total = Column(Integer, default=0)
    executions_success = Column(Integer, default=0)

    runs = relationship("AgentRun", back_populates="agent")


class AgentRun(Base):
    __tablename__ = "agent_runs"

    id = Column(Integer, primary_key=True, index=True)
    agent_id = Column(Integer, ForeignKey("agents.id"), index=True)
    query = Column(Text, default="")
    task = Column(Text, default="")
    status = Column(String(32), default="RUNNING")
    input_data = Column(Text, default="")
    output_data = Column(Text, default="")
    error_message = Column(Text, default="")
    duration_ms = Column(Integer, default=0)
    started_at = Column(DateTime(timezone=True), default=utcnow)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    agent = relationship("Agent", back_populates="runs")


class BusinessMetric(Base):
    __tablename__ = "business_metrics"

    id = Column(Integer, primary_key=True, index=True)
    metric_date = Column(DateTime(timezone=True), index=True)
    metric_type = Column(String(64), index=True)
    value = Column(Float, default=0.0)
    previous_value = Column(Float, default=0.0)
    change_pct = Column(Float, default=0.0)
    department = Column(String(64), default="All")
    region = Column(String(64), default="All")
    product = Column(String(64), default="All")
    segment = Column(String(64), default="All")
    created_at = Column(DateTime(timezone=True), default=utcnow)


class SecurityEvent(Base):
    __tablename__ = "security_events"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime(timezone=True), index=True, default=utcnow)
    event_type = Column(String(128), index=True)
    source = Column(String(255), default="")
    severity = Column(String(16), default="LOW")
    status = Column(String(32), default="OPEN")
    description = Column(Text, default="")
    username = Column(String(120), default="")
    ip_address = Column(String(64), default="")
    is_synthetic = Column(Boolean, default=False)


class SystemMetric(Base):
    __tablename__ = "system_metrics"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime(timezone=True), index=True, default=utcnow)
    service = Column(String(64), default="api")
    cpu_usage = Column(Float, default=0.0)
    memory_usage = Column(Float, default=0.0)
    disk_usage = Column(Float, default=0.0)
    api_latency_ms = Column(Float, default=0.0)
    request_rate = Column(Float, default=0.0)
    error_rate = Column(Float, default=0.0)
    db_health = Column(String(16), default="HEALTHY")
    is_synthetic = Column(Boolean, default=False)


class Incident(Base):
    __tablename__ = "incidents"

    id = Column(Integer, primary_key=True, index=True)
    incident_id = Column(String(32), unique=True, index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, default="")
    severity = Column(String(16), default="LOW")
    status = Column(String(32), default="Detected")
    assigned_agent = Column(String(120), default="")
    assignee = Column(String(255), default="")
    root_cause = Column(Text, default="")
    resolution = Column(Text, default="")
    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    events = relationship(
        "IncidentEvent", back_populates="incident", cascade="all, delete-orphan"
    )


class IncidentEvent(Base):
    __tablename__ = "incident_events"

    id = Column(Integer, primary_key=True, index=True)
    incident_id_fk = Column(Integer, ForeignKey("incidents.id"), index=True)
    timestamp = Column(DateTime(timezone=True), default=utcnow)
    event_type = Column(String(64), default="note")
    message = Column(Text, default="")
    actor = Column(String(120), default="system")

    incident = relationship("Incident", back_populates="events")


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    user_id_fk = Column(Integer, ForeignKey("users.id"), index=True, nullable=True)
    title = Column(String(255), nullable=False)
    message = Column(Text, default="")
    category = Column(String(64), default="general")
    severity = Column(String(16), default="INFO")
    read = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=utcnow)

    user = relationship("User", back_populates="notifications")


class KnowledgeDocument(Base):
    __tablename__ = "knowledge_documents"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False)
    filename = Column(String(255), default="")
    doc_type = Column(String(32), default="txt")
    size_bytes = Column(Integer, default=0)
    status = Column(String(32), default="PROCESSING")
    chunk_count = Column(Integer, default=0)
    uploaded_by = Column(String(120), default="")
    created_at = Column(DateTime(timezone=True), default=utcnow)

    chunks = relationship(
        "KnowledgeChunk", back_populates="document", cascade="all, delete-orphan"
    )


class KnowledgeChunk(Base):
    __tablename__ = "knowledge_chunks"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("knowledge_documents.id"), index=True)
    chunk_index = Column(Integer, default=0)
    text = Column(Text, default="")
    embedding_id = Column(String(128), default="")

    document = relationship("KnowledgeDocument", back_populates="chunks")


class Report(Base):
    __tablename__ = "reports"

    id = Column(Integer, primary_key=True, index=True)
    report_type = Column(String(64), index=True)
    title = Column(String(255), default="")
    summary = Column(Text, default="")
    content = Column(Text, default="")
    status = Column(String(32), default="GENERATED")
    created_by = Column(String(120), default="")
    created_at = Column(DateTime(timezone=True), default=utcnow)


class AIConversation(Base):
    __tablename__ = "ai_conversations"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String(64), index=True)
    user_id = Column(String(64), default="")
    title = Column(String(255), default="")
    query = Column(Text, default="")
    agents_used = Column(Text, default="[]")
    result = Column(Text, default="")
    status = Column(String(32), default="COMPLETED")
    created_at = Column(DateTime(timezone=True), default=utcnow)

    messages = relationship("AIMessage", back_populates="conversation")


class AIMessage(Base):
    __tablename__ = "ai_messages"

    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(Integer, ForeignKey("ai_conversations.id"), index=True)
    role = Column(String(16), default="user")
    content = Column(Text, default="")
    created_at = Column(DateTime(timezone=True), default=utcnow)

    conversation = relationship("AIConversation", back_populates="messages")


class ApprovalRequest(Base):
    __tablename__ = "approval_requests"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    title = Column(String(255), nullable=False)
    action = Column(String(255), nullable=False)
    reason = Column(Text, default="")
    expected_result = Column(Text, default="")
    risk_level = Column(String(16), default="LOW")
    affected_service = Column(String(128), default="")
    system_response = Column(Text, default="")
    status = Column(String(32), default="PENDING")
    requested_by = Column(String(120), default="")
    decided_by = Column(String(120), default="")
    decision_note = Column(Text, default="")
    created_at = Column(DateTime(timezone=True), default=utcnow)
    decided_at = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User", back_populates="approvals")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    username = Column(String(120), default="")
    action = Column(String(128), index=True)
    resource = Column(String(128), default="")
    details = Column(Text, default="")
    ip_address = Column(String(64), default="")
    request_id = Column(String(64), default="")
    result = Column(String(32), default="SUCCESS")
    created_at = Column(DateTime(timezone=True), default=utcnow)

    user = relationship("User", back_populates="audit_logs")


class Session(Base):
    """Server-side token session (enables revocation, remember-me, logout)."""

    __tablename__ = "sessions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    token_id = Column(String(64), unique=True, index=True)
    token_hash = Column(String(128), index=True)
    remember = Column(Boolean, default=False)
    revoked = Column(Boolean, default=False)
    ip_address = Column(String(64), default="")
    user_agent = Column(String(255), default="")
    created_at = Column(DateTime(timezone=True), default=utcnow)
    expires_at = Column(DateTime(timezone=True))
    last_seen = Column(DateTime(timezone=True), default=utcnow)

    user = relationship("User", back_populates="sessions")


class SystemSetting(Base):
    """Key/value admin settings."""

    __tablename__ = "system_settings"

    key = Column(String(128), primary_key=True)
    value = Column(Text, default="")


class AgentConfig(Base):
    """Per-agent runtime configuration (admin-managed)."""

    __tablename__ = "agent_configs"

    agent_key = Column(String(64), primary_key=True)
    name = Column(String(120), default="")
    description = Column(Text, default="")
    capability = Column(String(255), default="")
    enabled = Column(Boolean, default=True)
    provider = Column(String(32), default="")
    model = Column(String(128), default="")
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)