"""The initial send (PLAN.md §6.9)."""
from __future__ import annotations

from app import db, gates, journal, mail
from app import models as m


def _load(contact_id: str):
    with db.session() as s:
        contact = s.get(m.Contact, contact_id)
        if contact is None:
            raise gates.GateError("Contact not found")
        campaign = s.get(m.Campaign, contact.campaign_id)
        company = s.get(m.Company, contact.company_id) if contact.company_id else None
        draft = (
            s.query(m.Message)
            .filter(m.Message.contact_id == contact_id, m.Message.direction == "out",
                    m.Message.kind == "initial", m.Message.status == "DRAFT")
            .order_by(m.Message.created_at.desc())
            .first()
        )
        s.expunge_all()
    return campaign, contact, company, draft


async def send_initial(contact_id: str) -> None:
    """Send the approved, gate-passing draft. Raises GateError / RecipientGuardError / MailError."""
    campaign, contact, company, draft = _load(contact_id)
    if draft is None:
        raise gates.GateError("No draft to send for this contact")
    if draft.gate_status != "PASS":
        raise gates.GateError("Draft did not pass the claim gate")
    if not draft.send_approved_at:
        raise gates.GateError("Send was not approved by the seller")
    gates.require(campaign, contact, "initial")

    res = await mail.send_email(campaign, contact, kind="initial", subject=draft.subject or "",
                                body=draft.body, thread_id=None,
                                idempotency_key=f"{contact_id}:initial:1")
    delivered = mail.delivered_recipient(campaign, contact)

    with db.session() as s:
        c = s.get(m.Contact, contact_id)
        c.thread_id = res["thread_id"]
        c.delivered_to = delivered
        c.state = "CONTACTED"
        c.state = "WAITING"
        # The sent row carries the draft's receipts, so the latest initial message is complete.
        sent = s.query(m.Message).filter(m.Message.idempotency_key == f"{contact_id}:initial:1").first()
        if sent is not None:
            sent.sentences = draft.sentences
            sent.gate_status = draft.gate_status
            sent.gate_notes = draft.gate_notes
            sent.send_approved_at = draft.send_approved_at

    why = ""
    if company is not None and company.why_now:
        first = company.why_now[0]
        why = first.get("label", "") if isinstance(first, dict) else str(first)
    where = "rerouted to stand-in" if campaign.delivery_mode == "STAND_IN" else "delivered to prospect"
    text = f"Sent to {contact.name} → {where}."
    if why:
        text += f" Cited: {why}"
    journal.log(campaign.id, "send", text, contact_id=contact_id,
                data={"thread_id": res["thread_id"], "message_id": res["message_id"]})
