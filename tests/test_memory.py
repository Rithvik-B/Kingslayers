import os

os.environ["DATABASE_URL"] = "sqlite:///data/test_memory.db"

import pytest  # noqa: E402

from app import memory  # noqa: E402
from app.db import init_db, engine  # noqa: E402
from app.models import Base  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_db():
    init_db()
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield


def test_defaults_do_not_overwrite_existing():
    memory.ensure_defaults()
    memory.edit(None, "reply.prefs", {"interested_min_confidence": 0.9})
    memory.ensure_defaults()
    assert memory.get(None, "reply.prefs")["interested_min_confidence"] == 0.9


def test_agent_put_does_not_overwrite_user_edit():
    memory.put(None, "voice.style", {"tone": "formal"}, kind="voice", source="agent:discovery")
    memory.edit(None, "voice.style", {"tone": "casual"})
    memory.put(None, "voice.style", {"tone": "formal again"}, kind="voice", source="agent:discovery")
    assert memory.get(None, "voice.style") == {"tone": "casual"}
    snap = memory.snapshot(None)
    assert snap["proposed"]["voice.style"]["value"] == {"tone": "formal again"}
    assert snap["knowledge"]["voice"][0]["locked"] is True


def test_campaign_scoped_overrides_seller_wide():
    memory.put(None, "gtm.icp", {"nl_query": "wide"}, kind="icp", source="agent:discovery")
    memory.put("c1", "gtm.icp", {"nl_query": "narrow"}, kind="icp", source="agent:discovery")
    assert memory.get("c1", "gtm.icp")["nl_query"] == "narrow"
    assert memory.get("c2", "gtm.icp")["nl_query"] == "wide"
    assert memory.get(None, "gtm.icp")["nl_query"] == "wide"


def test_record_decision_appends_and_snapshot_lists_newest_first():
    memory.record_decision("c1", "decision.reply_label", {"label": "INTERESTED"}, source="agent:inbox", rationale="r1")
    memory.record_decision("c1", "decision.slot_booked", {"start": "x"}, source="agent:booking", rationale="r2")
    snap = memory.snapshot("c1")
    keys = [d["key"] for d in snap["decisions"]]
    assert keys[0] == "decision.slot_booked" and "decision.reply_label" in keys
    assert memory.get("c1", "decision.reply_label") == {"label": "INTERESTED"}


def test_history_and_revert():
    memory.put(None, "outreach.rules", ["a"], kind="rule", source="agent:x")
    memory.edit(None, "outreach.rules", ["a", "b"])
    hist = memory.history(None, "outreach.rules")
    assert [h["version"] for h in hist] == [2, 1]
    memory.revert(hist[1]["id"])
    assert memory.get(None, "outreach.rules") == ["a"]
