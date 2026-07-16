"""Usage + membership queries for billing/tenancy — Agent P4-A.
Signatures FROZEN (billing + members routers import these).

Self-contained: query the DB directly via ghostpanel.store.db.session_scope +
models (does NOT extend Store), so billing stays decoupled from the core repo.
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import func
from sqlmodel import select

from ghostpanel.store import db
from ghostpanel.store.models import Membership, Project, Role, RunRow, Tier, User


@dataclass
class MemberInfo:
    user_id: str
    email: str
    role: str


def _month_start() -> _dt.datetime:
    """Start of the current UTC calendar month (tz-aware)."""
    now = _dt.datetime.now(_dt.timezone.utc)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


async def runs_this_period(project_id: str, *, since: Optional[_dt.datetime] = None) -> int:
    """Count runs created for a project since `since` (default: start of the
    current UTC month). Used for the monthly run quota."""
    if since is None:
        since = _month_start()
    async with db.session_scope() as session:
        result = await session.exec(
            select(func.count())
            .select_from(RunRow)
            .where(RunRow.project_id == project_id, RunRow.created_at >= since)
        )
        return int(result.one())


async def member_count(project_id: str) -> int:
    """Number of memberships on a project (seat usage)."""
    async with db.session_scope() as session:
        result = await session.exec(
            select(func.count())
            .select_from(Membership)
            .where(Membership.project_id == project_id)
        )
        return int(result.one())


async def list_members(project_id: str) -> list[MemberInfo]:
    """Members of a project with their email + role (joins memberships↔users)."""
    async with db.session_scope() as session:
        result = await session.exec(
            select(Membership, User)
            .join(User, Membership.user_id == User.id)
            .where(Membership.project_id == project_id)
        )
        return [
            MemberInfo(user_id=user.id, email=user.email, role=membership.role.value)
            for membership, user in result.all()
        ]


async def add_member_by_email(project_id: str, email: str, role: str = "member") -> MemberInfo:
    """Add an existing user (looked up by email) to the project. Raise
    LookupError if no such user, ValueError if already a member."""
    async with db.session_scope() as session:
        user = (await session.exec(select(User).where(User.email == email))).first()
        if user is None:
            raise LookupError(f"No user with email {email!r}")

        existing = (
            await session.exec(
                select(Membership).where(
                    Membership.project_id == project_id,
                    Membership.user_id == user.id,
                )
            )
        ).first()
        if existing is not None:
            raise ValueError(f"{email!r} is already a member of this project")

        membership = Membership(
            user_id=user.id, project_id=project_id, role=Role(role)
        )
        session.add(membership)
        return MemberInfo(user_id=user.id, email=user.email, role=membership.role.value)


async def remove_member(project_id: str, user_id: str) -> bool:
    """Remove a membership. Never remove the project owner (return False)."""
    async with db.session_scope() as session:
        project = await session.get(Project, project_id)
        if project is not None and project.owner_id == user_id:
            return False

        membership = (
            await session.exec(
                select(Membership).where(
                    Membership.project_id == project_id,
                    Membership.user_id == user_id,
                )
            )
        ).first()
        if membership is None:
            return False
        if membership.role == Role.OWNER:
            return False

        await session.delete(membership)
        return True


async def set_project_billing(
    project_id: str, *, tier: str, stripe_customer_id: str = "",
    stripe_subscription_id: str = "", private_repos_enabled: Optional[bool] = None,
) -> None:
    """Update a project's tier + Stripe ids + private-repo flag (webhook handler)."""
    async with db.session_scope() as session:
        project = await session.get(Project, project_id)
        if project is None:
            return

        project.tier = Tier(tier)
        # Only overwrite ids when supplied so a downgrade (which omits them)
        # doesn't wipe the customer reference needed for the billing portal.
        if stripe_customer_id:
            project.stripe_customer_id = stripe_customer_id
        if stripe_subscription_id:
            project.stripe_subscription_id = stripe_subscription_id
        if private_repos_enabled is not None:
            project.private_repos_enabled = private_repos_enabled

        session.add(project)


__all__ = [
    "MemberInfo", "runs_this_period", "member_count", "list_members",
    "add_member_by_email", "remove_member", "set_project_billing",
]
