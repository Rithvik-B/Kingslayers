"""Agent journal: the event timeline shown in the UI. PLAN.md §5."""

from app.db import session
from app.models import Journal


def log(
    campaign_id: str,
    kind: str,
    text: str,
    contact_id: str | None = None,
    data: dict | None = None,
) -> None:
    """Append one journal line. Opens its own session and commits."""
    with session() as db:
        db.add(Journal(campaign_id=campaign_id, kind=kind, text=text, contact_id=contact_id, data=data))
