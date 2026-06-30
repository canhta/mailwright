from mailwright.brain.schemas import Reflection
from mailwright.db.connection import get_connection
from mailwright.db.schema import init_db
from mailwright.pipeline.reflection_service import ReflectionService
from mailwright.repositories.episodic import EpisodicRepo
from mailwright.repositories.rulebook import RulebookRepo
from mailwright.repositories.style import StyleRepo


class FakeLLM:
    def __init__(self, result):
        self.result = result
        self.called = False

    def parse(self, system, user, schema, images=None):
        self.called = True
        return self.result


def _svc(tmp_path, llm):
    conn = get_connection(str(tmp_path / "app.db"))
    init_db(conn)
    ep, st, rb = EpisodicRepo(conn), StyleRepo(conn), RulebookRepo(conn)
    return ReflectionService(ep, st, rb, llm, lookback=50), ep, st, rb


def test_reflection_updates_style_and_proposes_rules(tmp_path):
    refl = Reflection(
        style_profile="Terse, no hedging.", proposed_rules=["Always include acceptance criteria."]
    )
    svc, ep, st, rb = _svc(tmp_path, FakeLLM(refl))
    ep.add("edit", "before='x' after='shorter'")
    svc.run()
    assert st.get() == "Terse, no hedging."
    assert [r.text for r in rb.list_proposed()] == ["Always include acceptance criteria."]


def test_reflection_noop_without_edits(tmp_path):
    svc, _, st, _ = _svc(tmp_path, FakeLLM(None))
    svc.run()
    assert st.get() == ""  # nothing to learn from
