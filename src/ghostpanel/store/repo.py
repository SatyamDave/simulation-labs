"""Store — async data-access layer over the SQLModel schema.

Agent P2-A implementation. Signatures are FROZEN (auth, jobs, and the API routers
import them). Each method opens its own ``session_scope``. Returns are detached ORM
instances (the engine uses ``expire_on_commit=False``) or plain values as annotated.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import secrets
from typing import Optional

from sqlmodel import select

from ghostpanel_contracts import RunReport

from . import db
from .models import (
    ApiKey,
    BaselineRow,
    Membership,
    Project,
    Role,
    RunRow,
    RunState,
    Tier,
    User,
    _now,
)

# ---------------------------------------------------------------------------
# API-key helpers.  We delegate to ``ghostpanel.auth.apikeys`` (owned by P2-C).
# While that module is still a stub raising NotImplementedError, fall back to a
# local sha256-based scheme matching the frozen ``sl_live_<prefix8>_<secret>``
# format so this Store is not hard-blocked on a sibling.  Remove the fallbacks
# once P2-C lands (behaviour is identical for high-entropy keys).
# ---------------------------------------------------------------------------
from ghostpanel.auth import apikeys as _apikeys

_KEY_PREFIX = "sl_live_"


def _fallback_generate() -> tuple[str, str, str]:
    prefix = f"{_KEY_PREFIX}{secrets.token_hex(4)}"          # sl_live_<8 hex>
    secret = secrets.token_hex(16)                            # 32 hex chars
    plaintext = f"{prefix}_{secret}"
    key_hash = hashlib.sha256(plaintext.encode()).hexdigest()
    return prefix, plaintext, key_hash


def _fallback_prefix_of(plaintext: str) -> str:
    # Full key is "sl_live_<8>_<secret>"; the indexed prefix is everything up to
    # (and including) the 8-char id — i.e. drop the trailing "_<secret>".
    return plaintext.rsplit("_", 1)[0]


def _fallback_verify(plaintext: str, key_hash: str) -> bool:
    return secrets.compare_digest(
        hashlib.sha256(plaintext.encode()).hexdigest(), key_hash
    )


def _generate_api_key() -> tuple[str, str, str]:
    try:
        return _apikeys.generate_api_key()
    except NotImplementedError:
        return _fallback_generate()


def _prefix_of(plaintext: str) -> str:
    try:
        return _apikeys.prefix_of(plaintext)
    except NotImplementedError:
        return _fallback_prefix_of(plaintext)


def _verify_api_key(plaintext: str, key_hash: str) -> bool:
    try:
        return _apikeys.verify_api_key(plaintext, key_hash)
    except NotImplementedError:
        return _fallback_verify(plaintext, key_hash)


class Store:
    """All persistence operations. Construct once; safe to share (stateless)."""

    # ---- users ----------------------------------------------------------
    async def create_user(self, email: str, password_hash: str) -> User:
        async with db.session_scope() as session:
            user = User(email=email, password_hash=password_hash)
            session.add(user)
            await session.flush()
            return user

    async def get_user(self, user_id: str) -> Optional[User]:
        async with db.session_scope() as session:
            return await session.get(User, user_id)

    async def get_user_by_email(self, email: str) -> Optional[User]:
        async with db.session_scope() as session:
            result = await session.exec(select(User).where(User.email == email))
            return result.first()

    # ---- projects / membership -----------------------------------------
    async def create_project(
        self, *, owner: User, name: str, tier: Tier = Tier.FREE
    ) -> Project:
        """Create the project AND an owner Membership in one transaction."""
        async with db.session_scope() as session:
            project = Project(name=name, owner_id=owner.id, tier=tier)
            session.add(project)
            await session.flush()  # assign project.id before the membership FK
            session.add(
                Membership(
                    user_id=owner.id, project_id=project.id, role=Role.OWNER
                )
            )
            await session.flush()
            return project

    async def get_project(self, project_id: str) -> Optional[Project]:
        async with db.session_scope() as session:
            return await session.get(Project, project_id)

    async def list_projects_for_user(self, user_id: str) -> list[Project]:
        async with db.session_scope() as session:
            result = await session.exec(
                select(Project)
                .join(Membership, Membership.project_id == Project.id)
                .where(Membership.user_id == user_id)
                .order_by(Project.created_at)
            )
            return list(result.all())

    async def member_role(
        self, user_id: str, project_id: str
    ) -> Optional[Role]:
        async with db.session_scope() as session:
            result = await session.exec(
                select(Membership).where(
                    Membership.user_id == user_id,
                    Membership.project_id == project_id,
                )
            )
            membership = result.first()
            return membership.role if membership else None

    async def add_member(
        self, project_id: str, user_id: str, role: Role = Role.MEMBER
    ) -> Membership:
        async with db.session_scope() as session:
            membership = Membership(
                user_id=user_id, project_id=project_id, role=role
            )
            session.add(membership)
            await session.flush()
            return membership

    async def set_project_tier(self, project_id: str, tier: Tier) -> None:
        async with db.session_scope() as session:
            project = await session.get(Project, project_id)
            if project is not None:
                project.tier = tier
                session.add(project)

    # ---- api keys -------------------------------------------------------
    async def create_api_key(
        self, project_id: str, name: str = "default"
    ) -> tuple[ApiKey, str]:
        """Return (row, plaintext). Plaintext is shown ONCE; only the hash is stored.
        Delegates format/hashing to ghostpanel.auth.apikeys (with a local fallback
        while that module is a stub)."""
        prefix, plaintext, key_hash = _generate_api_key()
        async with db.session_scope() as session:
            row = ApiKey(
                project_id=project_id,
                name=name,
                prefix=prefix,
                key_hash=key_hash,
            )
            session.add(row)
            await session.flush()
            return row, plaintext

    async def project_for_api_key(self, plaintext: str) -> Optional[Project]:
        """Look up by prefix, verify the hash, touch last_used_at, return the Project
        (None if unknown/revoked)."""
        prefix = _prefix_of(plaintext)
        async with db.session_scope() as session:
            result = await session.exec(
                select(ApiKey).where(
                    ApiKey.prefix == prefix, ApiKey.revoked_at.is_(None)
                )
            )
            for key in result.all():
                if _verify_api_key(plaintext, key.key_hash):
                    key.last_used_at = _now()
                    session.add(key)
                    return await session.get(Project, key.project_id)
            return None

    async def list_api_keys(self, project_id: str) -> list[ApiKey]:
        async with db.session_scope() as session:
            result = await session.exec(
                select(ApiKey)
                .where(ApiKey.project_id == project_id)
                .order_by(ApiKey.created_at)
            )
            return list(result.all())

    async def revoke_api_key(self, key_id: str, project_id: str) -> bool:
        async with db.session_scope() as session:
            key = await session.get(ApiKey, key_id)
            if key is None or key.project_id != project_id:
                return False
            if key.revoked_at is None:
                key.revoked_at = _now()
                session.add(key)
            return True

    # ---- runs -----------------------------------------------------------
    async def create_run(
        self,
        *,
        run_id: str,
        project_id: str,
        target_url: str,
        task: str,
        persona_ids: list[str],
        flow_name: str = "",
        state: RunState = RunState.QUEUED,
    ) -> RunRow:
        async with db.session_scope() as session:
            row = RunRow(
                id=run_id,
                project_id=project_id,
                target_url=target_url,
                task=task,
                persona_ids=list(persona_ids),
                flow_name=flow_name,
                state=state,
            )
            session.add(row)
            await session.flush()
            return row

    async def set_run_state(
        self, run_id: str, state: RunState, error: str = ""
    ) -> None:
        async with db.session_scope() as session:
            row = await session.get(RunRow, run_id)
            if row is not None:
                row.state = state
                if error:
                    row.error = error
                session.add(row)

    async def set_run_report(self, run_id: str, report: RunReport) -> None:
        """Store the full report_json + promoted completion_rate, mark FINISHED,
        stamp finished_at."""
        async with db.session_scope() as session:
            row = await session.get(RunRow, run_id)
            if row is not None:
                row.report_json = report.model_dump(mode="json")
                row.completion_rate = report.completion_rate
                row.state = RunState.FINISHED
                row.finished_at = _now()
                session.add(row)

    async def get_run(self, run_id: str) -> Optional[RunRow]:
        async with db.session_scope() as session:
            return await session.get(RunRow, run_id)

    async def list_runs(
        self,
        project_id: str,
        *,
        flow_name: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[RunRow]:
        async with db.session_scope() as session:
            stmt = select(RunRow).where(RunRow.project_id == project_id)
            if flow_name is not None:
                stmt = stmt.where(RunRow.flow_name == flow_name)
            stmt = stmt.order_by(RunRow.created_at.desc()).offset(offset).limit(limit)
            result = await session.exec(stmt)
            return list(result.all())

    # ---- baselines / trend ---------------------------------------------
    async def get_baseline(
        self, project_id: str, flow_name: str
    ) -> Optional[BaselineRow]:
        async with db.session_scope() as session:
            result = await session.exec(
                select(BaselineRow).where(
                    BaselineRow.project_id == project_id,
                    BaselineRow.flow_name == flow_name,
                )
            )
            return result.first()

    async def set_baseline(
        self, project_id: str, flow_name: str, run: RunRow
    ) -> BaselineRow:
        """Upsert the (project, flow) baseline from a finished run."""
        async with db.session_scope() as session:
            result = await session.exec(
                select(BaselineRow).where(
                    BaselineRow.project_id == project_id,
                    BaselineRow.flow_name == flow_name,
                )
            )
            row = result.first()
            report_json = run.report_json or {}
            completion_rate = run.completion_rate or 0.0
            if row is None:
                row = BaselineRow(
                    project_id=project_id,
                    flow_name=flow_name,
                    run_id=run.id,
                    completion_rate=completion_rate,
                    report_json=report_json,
                )
            else:
                row.run_id = run.id
                row.completion_rate = completion_rate
                row.report_json = report_json
            session.add(row)
            await session.flush()
            return row

    async def completion_trend(
        self, project_id: str, flow_name: str, *, limit: int = 30
    ) -> list[tuple[_dt.datetime, float]]:
        """(created_at, completion_rate) for finished runs of a flow, oldest→newest —
        the 'did this deploy make it worse' series."""
        async with db.session_scope() as session:
            result = await session.exec(
                select(RunRow)
                .where(
                    RunRow.project_id == project_id,
                    RunRow.flow_name == flow_name,
                    RunRow.state == RunState.FINISHED,
                )
                .order_by(RunRow.created_at)
                .limit(limit)
            )
            return [
                (row.created_at, row.completion_rate or 0.0)
                for row in result.all()
            ]
