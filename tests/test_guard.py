"""Recipient guard and send gates (PLAN.md §9, P3)."""
import pathlib
import sys

_HERE = pathlib.Path(__file__).resolve().parent
sys.path[:0] = [str(_HERE.parent), str(_HERE)]

from contextlib import contextmanager  # noqa: E402
from uuid import uuid4  # noqa: E402

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from datetime import date, timedelta  # noqa: E402
import pytest  # noqa: E402
from app import gates, mail  # noqa: E402
from app.config import S  # noqa: E402
from app.mail import RecipientGuardError, check_recipient  # noqa: E402


@pytest.fixture
def tdb(monkeypatch, tmp_path):
    from app import db, journal, models
    from app.config import S

    eng = create_engine(f"sqlite:///{tmp_path}/test.db", connect_args={"check_same_thread": False})
    models.Base.metadata.create_all(eng)
    SL = sessionmaker(bind=eng, expire_on_commit=False)

    @contextmanager
    def session():
        s = SL()
        try:
            yield s
            s.commit()
        except Exception:
            s.rollback()
            raise
        finally:
            s.close()

    monkeypatch.setattr(db, "engine", eng, raising=False)
    monkeypatch.setattr(db, "SessionLocal", SL, raising=False)
    monkeypatch.setattr(db, "session", session)
    monkeypatch.setattr(journal, "log", lambda *a, **k: None)
    monkeypatch.setattr(S, "STAND_IN_EMAIL", "standin@example.com")
    monkeypatch.setattr(S, "SELLER_EMAIL", "seller@example.com")
    monkeypatch.setattr(S, "ACCEPTED_EMAIL_STATUSES", ["verified", "valid"])
    return session


def make_campaign(session, *, mode="STAND_IN", consent=None):
    from app import mail
    from app import models as m

    cid = str(uuid4())
    with session() as s:
        s.add(m.Campaign(id=cid, name="t", product_text="p", icp_approved=True, delivery_mode=mode,
                         status="READY", paused=False, credits_used=0, consent=consent,
                         created_at=mail.utcnow()))
    return cid


def make_contact(session, campaign_id, *, email="prospect@realco.in", state="READY", delivered_to=None,
                 thread_id=None):
    from app import models as m

    coid, ctid = str(uuid4()), str(uuid4())
    with session() as s:
        s.add(m.Company(id=coid, campaign_id=campaign_id, crustdata_id=coid, name="RealCo", coverage=100,
                        tier="T1", why_now=[], criteria=[], raw={}))
        s.add(m.Contact(id=ctid, campaign_id=campaign_id, company_id=coid, name="Asha Rao",
                        title="Head of Talent", role="CHAMPION", verified_email=email,
                        email_status="verified", state=state, featured=False, delivered_to=delivered_to,
                        thread_id=thread_id, raw={}))
    return ctid


def load(session, model_name, id_):
    from app import models as m

    with session() as s:
        obj = s.get(getattr(m, model_name), id_)
        s.expunge(obj)
        return obj


def _consent(max_sends=5):
    return {"sender_name": "A", "company": "B", "postal_address": "C", "max_sends": max_sends,
            "end_date": (date.today() + timedelta(days=7)).isoformat(), "authorized": True}


@pytest.fixture
def live_on(monkeypatch):
    # LIVE flags are properties re-read from the environment at call time (app/config.py).
    monkeypatch.setenv("OUTBOUND_ENABLED", "true")
    monkeypatch.setenv("DEMO_MODE", "false")


def test_stand_in_rejects_real_address(tdb):
    camp = load(tdb, "Campaign", make_campaign(tdb))
    c = load(tdb, "Contact", make_contact(tdb, camp.id))
    with pytest.raises(RecipientGuardError):
        check_recipient(camp, c, "prospect@realco.in", initial=True)
    check_recipient(camp, c, "StandIn@Example.com", initial=True)  # the stand-in passes
    assert mail.delivered_recipient(camp, c) == "standin@example.com"


def test_stand_in_unset_fails_closed(tdb, monkeypatch):
    monkeypatch.setattr(S, "STAND_IN_EMAIL", "")
    camp = load(tdb, "Campaign", make_campaign(tdb))
    c = load(tdb, "Contact", make_contact(tdb, camp.id))
    with pytest.raises(RecipientGuardError):
        check_recipient(camp, c, "", initial=True)
    with pytest.raises(RecipientGuardError):
        mail.delivered_recipient(camp, c)


def test_live_without_consent_raises(tdb, live_on):
    camp = load(tdb, "Campaign", make_campaign(tdb, mode="LIVE", consent=None))
    c = load(tdb, "Contact", make_contact(tdb, camp.id))
    with pytest.raises(RecipientGuardError):
        check_recipient(camp, c, "prospect@realco.in", initial=True)


def test_outbound_disabled_blocks_consented_live(tdb, live_on, monkeypatch):
    camp = load(tdb, "Campaign", make_campaign(tdb, mode="LIVE", consent=_consent()))
    c = load(tdb, "Contact", make_contact(tdb, camp.id))
    check_recipient(camp, c, "prospect@realco.in", initial=True)  # allowed while enabled
    monkeypatch.setenv("OUTBOUND_ENABLED", "false")
    with pytest.raises(RecipientGuardError):
        check_recipient(camp, c, "prospect@realco.in", initial=True)


def test_live_demo_mode_and_wrong_recipient_block(tdb, live_on, monkeypatch):
    camp = load(tdb, "Campaign", make_campaign(tdb, mode="LIVE", consent=_consent()))
    c = load(tdb, "Contact", make_contact(tdb, camp.id))
    with pytest.raises(RecipientGuardError):
        check_recipient(camp, c, "someone.else@realco.in", initial=True)
    monkeypatch.setenv("DEMO_MODE", "true")
    with pytest.raises(RecipientGuardError):
        check_recipient(camp, c, "prospect@realco.in", initial=True)


def test_live_cap_allows_followups_to_delivered_only(tdb, live_on):
    cid = make_campaign(tdb, mode="LIVE", consent=_consent(max_sends=1))
    camp = load(tdb, "Campaign", cid)
    a = load(tdb, "Contact", make_contact(tdb, cid, email="a@realco.in", state="WAITING",
                                          delivered_to="a@realco.in"))
    b = load(tdb, "Contact", make_contact(tdb, cid, email="b@other.in"))
    check_recipient(camp, a, "a@realco.in", initial=False)  # slot offer to the delivered contact
    with pytest.raises(RecipientGuardError):
        check_recipient(camp, b, "b@other.in", initial=True)  # second initial is over the cap
    with pytest.raises(RecipientGuardError):
        check_recipient(camp, b, "b@other.in", initial=False)  # never delivered


def test_gates_stand_in_delivers_one_contact(tdb):
    cid = make_campaign(tdb)
    camp = load(tdb, "Campaign", cid)
    a = load(tdb, "Contact", make_contact(tdb, cid))
    assert gates.can_send(camp, a, "initial") == (True, "ok")
    make_contact(tdb, cid, email="x@y.in", state="WAITING", delivered_to="standin@example.com")
    ok, reason = gates.can_send(camp, a, "initial")
    assert not ok and "1 contact" in reason


def test_gates_pause_and_suppression(tdb):
    from app import inbox

    cid = make_campaign(tdb)
    ct = make_contact(tdb, cid)
    camp, c = load(tdb, "Campaign", cid), load(tdb, "Contact", ct)
    camp.paused = True
    assert gates.can_send(camp, c, "initial")[0] is False
    camp.paused = False
    inbox.suppress_contact(ct, "test")
    c = load(tdb, "Contact", ct)
    assert c.state == "SUPPRESSED"
    c.state = "READY"
    ok, reason = gates.can_send(camp, c, "initial")
    assert not ok and "suppressed" in reason.lower()
