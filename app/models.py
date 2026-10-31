"""Tables. FROZEN contract: PLAN.md §5. Only P1 edits this file."""

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import JSON, Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def new_id() -> str:
    return str(uuid4())


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Campaign(Base):
    __tablename__ = "campaigns"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String)
    product_text: Mapped[str] = mapped_column(Text)
    icp_approved: Mapped[bool] = mapped_column(Boolean, default=False)
    delivery_mode: Mapped[str] = mapped_column(String, default="STAND_IN")  # STAND_IN | LIVE
    status: Mapped[str] = mapped_column(String, default="DRAFT")  # DRAFT|DISCOVERING|READY|RUNNING|DONE|FAILED
    paused: Mapped[bool] = mapped_column(Boolean, default=False)
    discovery_ran_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    credits_used: Mapped[float] = mapped_column(Float, default=0.0)
    consent: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # LIVE only
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    campaign_id: Mapped[str] = mapped_column(String, index=True)
    crustdata_id: Mapped[str] = mapped_column(String)
    name: Mapped[str] = mapped_column(String)
    domain: Mapped[str | None] = mapped_column(String, nullable=True)
    industry: Mapped[str | None] = mapped_column(String, nullable=True)
    country: Mapped[str | None] = mapped_column(String, nullable=True)
    city: Mapped[str | None] = mapped_column(String, nullable=True)
    headcount: Mapped[int | None] = mapped_column(Integer, nullable=True)
    headcount_growth_12m: Mapped[float | None] = mapped_column(Float, nullable=True)
    fit: Mapped[float | None] = mapped_column(Float, nullable=True)
    coverage: Mapped[float] = mapped_column(Float, default=0.0)
    tier: Mapped[str] = mapped_column(String, default="T4")  # T1|T2|T3|T4|NEEDS_EVIDENCE|EXCLUDED
    rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    why_now: Mapped[list] = mapped_column(JSON, default=list)  # [{label, evidence_id}]
    criteria: Mapped[list] = mapped_column(JSON, default=list)  # [{constraint_id, field, type, verdict, observed, evidence_id}]
    raw: Mapped[dict] = mapped_column(JSON, default=dict)


class Contact(Base):
    __tablename__ = "contacts"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    campaign_id: Mapped[str] = mapped_column(String, index=True)
    company_id: Mapped[str] = mapped_column(String, index=True)
    crustdata_person_id: Mapped[str | None] = mapped_column(String, nullable=True)
    name: Mapped[str] = mapped_column(String)
    title: Mapped[str] = mapped_column(String, default="")
    role: Mapped[str] = mapped_column(String, default="OTHER")  # CHAMPION|ECONOMIC_BUYER|OTHER
    linkedin_url: Mapped[str | None] = mapped_column(String, nullable=True)
    verified_email: Mapped[str | None] = mapped_column(String, nullable=True)  # NEVER sent to the UI
    email_status: Mapped[str | None] = mapped_column(String, nullable=True)
    state: Mapped[str] = mapped_column(String, default="READY")  # see PLAN.md §6.12
    featured: Mapped[bool] = mapped_column(Boolean, default=False)
    thread_id: Mapped[str | None] = mapped_column(String, nullable=True)
    delivered_to: Mapped[str | None] = mapped_column(String, nullable=True)
    raw: Mapped[dict] = mapped_column(JSON, default=dict)


class Evidence(Base):
    __tablename__ = "evidence"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    campaign_id: Mapped[str] = mapped_column(String, index=True)
    subject_type: Mapped[str] = mapped_column(String)  # company | contact
    subject_id: Mapped[str] = mapped_column(String, index=True)
    endpoint: Mapped[str] = mapped_column(String)  # e.g. /job/search
    field_path: Mapped[str] = mapped_column(String)
    value: Mapped[str] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(String, nullable=True)  # never invented
    raw_excerpt: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    campaign_id: Mapped[str] = mapped_column(String, index=True)
    contact_id: Mapped[str] = mapped_column(String, index=True)
    direction: Mapped[str] = mapped_column(String)  # out | in
    kind: Mapped[str] = mapped_column(String)  # initial|slot_offer|confirmation|reply
    subject: Mapped[str | None] = mapped_column(String, nullable=True)
    body: Mapped[str] = mapped_column(Text, default="")
    sentences: Mapped[list | None] = mapped_column(JSON, nullable=True)  # drafts only
    gate_status: Mapped[str | None] = mapped_column(String, nullable=True)  # PASS | NEEDS_REVIEW
    gate_notes: Mapped[list | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String, default="DRAFT")  # DRAFT|HELD|PENDING|SENT|FAILED|UNKNOWN|RECEIVED
    idempotency_key: Mapped[str | None] = mapped_column(String, unique=True, nullable=True)
    provider_message_id: Mapped[str | None] = mapped_column(String, nullable=True)
    thread_id: Mapped[str | None] = mapped_column(String, nullable=True)
    send_approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ProcessedMessage(Base):
    __tablename__ = "processed_messages"

    gmail_message_id: Mapped[str] = mapped_column(String, primary_key=True)
    contact_id: Mapped[str | None] = mapped_column(String, nullable=True)
    outcome: Mapped[str] = mapped_column(String, default="")
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Meeting(Base):
    __tablename__ = "meetings"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    campaign_id: Mapped[str] = mapped_column(String, index=True)
    contact_id: Mapped[str] = mapped_column(String, index=True)
    slots_offered: Mapped[list] = mapped_column(JSON, default=list)  # ISO start strings
    start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    event_id: Mapped[str | None] = mapped_column(String, nullable=True)
    meet_link: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, default="OFFERED")  # OFFERED|BOOKED|MEETING_READY_TO_BOOK
    accepted_message_id: Mapped[str | None] = mapped_column(String, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Suppression(Base):
    __tablename__ = "suppressions"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    contact_key: Mapped[str] = mapped_column(String, index=True)  # normalized real email, or contact:<id>
    reason: Mapped[str] = mapped_column(String, default="")
    source_campaign_id: Mapped[str | None] = mapped_column(String, nullable=True)
    source_mode: Mapped[str] = mapped_column(String, default="STAND_IN")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Journal(Base):
    __tablename__ = "journal"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    campaign_id: Mapped[str] = mapped_column(String, index=True)
    contact_id: Mapped[str | None] = mapped_column(String, nullable=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    kind: Mapped[str] = mapped_column(String, default="info")
    text: Mapped[str] = mapped_column(Text)
    data: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class Memory(Base):
    """Seller Memory. PLAN.md §6.13. campaign_id NULL = seller-wide."""

    __tablename__ = "memory"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    campaign_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    key: Mapped[str] = mapped_column(String, index=True)
    kind: Mapped[str] = mapped_column(String)  # profile|icp|voice|rule|decision
    value: Mapped[dict | list | str | int | float | bool | None] = mapped_column(JSON, nullable=True)
    source: Mapped[str] = mapped_column(String)  # agent:<module> | user
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String, default="active")  # active|superseded|proposed
    locked: Mapped[bool] = mapped_column(Boolean, default=False)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
