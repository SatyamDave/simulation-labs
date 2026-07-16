"""SQLModel schema — the hosted product's persistence contract. FROZEN.

Every Phase 2 agent imports these. Do not change a column name/type without
updating PHASE2_SPEC.md and every owner. The full ``RunReport`` is stored as a
JSON column (``report_json``) with a few promoted columns for cheap querying
(state, completion_rate, created_at, flow_name).
"""

from __future__ import annotations

import datetime as _dt
import enum
import uuid
from typing import Any, Optional

from sqlalchemy import JSON, Column, UniqueConstraint
from sqlmodel import Field, SQLModel


def _uuid() -> str:
    return uuid.uuid4().hex


def _now() -> _dt.datetime:
    return _dt.datetime.now(_dt.timezone.utc)


class Tier(str, enum.Enum):
    FREE = "free"
    TEAM = "team"
    AUDIT = "audit"


class Role(str, enum.Enum):
    OWNER = "owner"
    MEMBER = "member"


class RunState(str, enum.Enum):
    QUEUED = "queued"
    RUNNING = "running"
    FINISHED = "finished"
    ERROR = "error"


class JobState(str, enum.Enum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    CANCELED = "canceled"


class User(SQLModel, table=True):
    __tablename__ = "users"
    id: str = Field(default_factory=_uuid, primary_key=True)
    email: str = Field(index=True, unique=True)
    password_hash: str
    created_at: _dt.datetime = Field(default_factory=_now)


class Project(SQLModel, table=True):
    __tablename__ = "projects"
    id: str = Field(default_factory=_uuid, primary_key=True)
    name: str
    owner_id: str = Field(foreign_key="users.id", index=True)
    tier: Tier = Field(default=Tier.FREE)
    private_repos_enabled: bool = False           # gated by tier (Phase 4)
    stripe_customer_id: str = ""                  # Phase 4
    stripe_subscription_id: str = ""              # Phase 4
    created_at: _dt.datetime = Field(default_factory=_now)


class Membership(SQLModel, table=True):
    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("user_id", "project_id", name="uq_member"),)
    id: str = Field(default_factory=_uuid, primary_key=True)
    user_id: str = Field(foreign_key="users.id", index=True)
    project_id: str = Field(foreign_key="projects.id", index=True)
    role: Role = Field(default=Role.MEMBER)
    created_at: _dt.datetime = Field(default_factory=_now)


class ApiKey(SQLModel, table=True):
    __tablename__ = "api_keys"
    id: str = Field(default_factory=_uuid, primary_key=True)
    project_id: str = Field(foreign_key="projects.id", index=True)
    name: str = "default"
    prefix: str = Field(index=True)               # visible id, e.g. "sl_live_ab12cd34"
    key_hash: str                                 # bcrypt/sha256 of the full secret
    created_at: _dt.datetime = Field(default_factory=_now)
    last_used_at: Optional[_dt.datetime] = None
    revoked_at: Optional[_dt.datetime] = None


class RunRow(SQLModel, table=True):
    __tablename__ = "runs"
    id: str = Field(primary_key=True)             # == RunReport.run_id
    project_id: str = Field(foreign_key="projects.id", index=True)
    state: RunState = Field(default=RunState.QUEUED, index=True)
    target_url: str = ""
    task: str = ""
    flow_name: str = Field(default="", index=True)
    persona_ids: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    completion_rate: Optional[float] = None
    report_json: Optional[dict[str, Any]] = Field(default=None, sa_column=Column(JSON))
    error: str = ""
    created_at: _dt.datetime = Field(default_factory=_now, index=True)
    finished_at: Optional[_dt.datetime] = None


class BaselineRow(SQLModel, table=True):
    __tablename__ = "baselines"
    __table_args__ = (
        UniqueConstraint("project_id", "flow_name", name="uq_baseline_flow"),
    )
    id: str = Field(default_factory=_uuid, primary_key=True)
    project_id: str = Field(foreign_key="projects.id", index=True)
    flow_name: str = Field(default="", index=True)
    run_id: str = Field(foreign_key="runs.id")
    completion_rate: float = 0.0
    report_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: _dt.datetime = Field(default_factory=_now)


class JobRow(SQLModel, table=True):
    __tablename__ = "jobs"
    id: str = Field(default_factory=_uuid, primary_key=True)
    project_id: str = Field(foreign_key="projects.id", index=True)
    run_id: Optional[str] = Field(default=None, foreign_key="runs.id")
    state: JobState = Field(default=JobState.QUEUED, index=True)
    # Swarm spec: {url, task, persona_ids, flow_name, fixture, rpm}.
    spec: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    attempts: int = 0
    max_attempts: int = 3
    error: str = ""
    locked_by: str = ""                           # worker id holding the claim
    locked_at: Optional[_dt.datetime] = None
    created_at: _dt.datetime = Field(default_factory=_now, index=True)
    started_at: Optional[_dt.datetime] = None
    finished_at: Optional[_dt.datetime] = None


__all__ = [
    "Tier", "Role", "RunState", "JobState",
    "User", "Project", "Membership", "ApiKey", "RunRow", "BaselineRow", "JobRow",
    "_uuid", "_now",
]
