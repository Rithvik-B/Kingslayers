"""Seller Memory: what the agent knows about the seller, and every decision made. PLAN.md §6.13.

Agents call get() at the start of every step (never cache across steps). A user edit locks the key:
later agent writes are stored as "proposed", never applied.
"""

from sqlalchemy import select

from app import journal
from app.db import session
from app.models import Memory

DEFAULTS: dict[str, tuple[str, object]] = {
    # key: (kind, value)
    "outreach.rules": ("rule", []),
    "scheduling.prefs": (
        "rule",
        {
            "working_hours": [9, 18],
            "slot_minutes": 20,
            "buffer_minutes": 10,
            "days_ahead": 7,
            "timezone": "Asia/Kolkata",
        },
    ),
    "reply.prefs": ("rule", {"interested_min_confidence": 0.75}),
}


def _active(db, campaign_id: str | None, key: str) -> Memory | None:
    stmt = (
        select(Memory)
        .where(Memory.key == key, Memory.status == "active")
        .where(Memory.campaign_id.is_(None) if campaign_id is None else Memory.campaign_id == campaign_id)
        .order_by(Memory.version.desc())
    )
    return db.scalars(stmt).first()


def _to_dict(m: Memory) -> dict:
    return {
        "id": m.id,
        "campaign_id": m.campaign_id,
        "key": m.key,
        "kind": m.kind,
        "value": m.value,
        "source": m.source,
        "rationale": m.rationale,
        "status": m.status,
        "locked": m.locked,
        "version": m.version,
        "created_at": m.created_at.isoformat() if m.created_at else None,
    }


def ensure_defaults() -> None:
    """Seed seller-wide keys only if missing. Called at app startup."""
    with session() as db:
        for key, (kind, value) in DEFAULTS.items():
            if _active(db, None, key) is None:
                db.add(Memory(campaign_id=None, key=key, kind=kind, value=value, source="agent:defaults",
                              rationale="Default", status="active", version=1))


def get(campaign_id: str | None, key: str, default=None):
    """Active value: campaign-scoped first, then seller-wide, then default."""
    with session() as db:
        if campaign_id is not None:
            m = _active(db, campaign_id, key)
            if m is not None:
                return m.value
        m = _active(db, None, key)
        return m.value if m is not None else default


def put(campaign_id: str | None, key: str, value, *, kind: str, source: str, rationale: str = "") -> str:
    """Agent or system write. Respects a user lock: then the value is stored as 'proposed'."""
    kept_user_edit = False
    with session() as db:
        cur = _active(db, campaign_id, key)
        if cur is not None and cur.locked and source.startswith("agent:"):
            kept_user_edit = True
            m = Memory(campaign_id=campaign_id, key=key, kind=kind, value=value, source=source,
                       rationale=rationale, status="proposed", locked=False, version=cur.version + 1)
        else:
            version = 1
            if cur is not None:
                cur.status = "superseded"
                version = cur.version + 1
            m = Memory(campaign_id=campaign_id, key=key, kind=kind, value=value, source=source,
                       rationale=rationale, status="active", locked=False, version=version)
        db.add(m)
        db.flush()
        mid = m.id
    if kept_user_edit and campaign_id is not None:
        journal.log(campaign_id, "memory", f"Kept your edit for {key}; the agent's suggestion is saved.")
    return mid


def record_decision(campaign_id: str, key: str, value, *, source: str, rationale: str) -> str:
    """kind='decision'; always appends; never locked. Campaign-scoped."""
    with session() as db:
        prev = _active(db, campaign_id, key)
        version = 1
        if prev is not None:
            prev.status = "superseded"
            version = prev.version + 1
        m = Memory(campaign_id=campaign_id, key=key, kind="decision", value=value, source=source,
                   rationale=rationale, status="active", locked=False, version=version)
        db.add(m)
        db.flush()
        return m.id


def edit(campaign_id: str | None, key: str, value) -> str:
    """A user edit: new active version, source='user', locked=True."""
    with session() as db:
        cur = _active(db, campaign_id, key)
        kind = cur.kind if cur is not None else DEFAULTS.get(key, ("rule", None))[0]
        version = 1
        if cur is not None:
            cur.status = "superseded"
            version = cur.version + 1
        m = Memory(campaign_id=campaign_id, key=key, kind=kind, value=value, source="user",
                   rationale="Edited by the seller", status="active", locked=True, version=version)
        db.add(m)
        db.flush()
        return m.id


def snapshot(campaign_id: str | None) -> dict:
    """Every active item grouped by kind (campaign-scoped overriding seller-wide), plus decisions newest
    first and any proposed agent suggestions."""
    with session() as db:
        rows = db.scalars(
            select(Memory)
            .where(Memory.status.in_(["active", "proposed"]))
            .where((Memory.campaign_id.is_(None)) | (Memory.campaign_id == campaign_id))
            .order_by(Memory.created_at.asc())
        ).all()
        knowledge: dict[str, dict] = {}
        proposed: dict[str, dict] = {}
        decisions: list[dict] = []
        for m in rows:
            d = _to_dict(m)
            if m.kind == "decision":
                if m.status == "active":
                    decisions.append(d)
                continue
            if m.status == "proposed":
                proposed[m.key] = d
                continue
            existing = knowledge.get(m.key)
            # campaign-scoped wins over seller-wide
            if existing is None or (existing["campaign_id"] is None and m.campaign_id is not None):
                knowledge[m.key] = d
        grouped: dict[str, list[dict]] = {}
        for d in knowledge.values():
            grouped.setdefault(d["kind"], []).append(d)
        decisions.sort(key=lambda d: d["created_at"] or "", reverse=True)
        return {"campaign_id": campaign_id, "knowledge": grouped, "proposed": proposed, "decisions": decisions}


def history(campaign_id: str | None, key: str) -> list[dict]:
    """Tier 2: all versions of one key, newest first."""
    with session() as db:
        rows = db.scalars(
            select(Memory)
            .where(Memory.key == key)
            .where(Memory.campaign_id.is_(None) if campaign_id is None else Memory.campaign_id == campaign_id)
            .order_by(Memory.version.desc())
        ).all()
        return [_to_dict(m) for m in rows]


def revert(item_id: str) -> str:
    """Tier 2: copy an old version as a new active one (source='user', locked=True)."""
    with session() as db:
        old = db.get(Memory, item_id)
        if old is None:
            raise KeyError(item_id)
        campaign_id, key, value = old.campaign_id, old.key, old.value
    return edit(campaign_id, key, value)
