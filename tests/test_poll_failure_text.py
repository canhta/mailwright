from mailwright.owa.session import OwaLoginRequired
from mailwright.telegram.handlers import _poll_failure_text


def test_owa_login_required_gets_actionable_nudge():
    text = _poll_failure_text(OwaLoginRequired("no token captured"))

    assert "login" in text.lower()
    assert "session" in text.lower()
    assert "no token captured" not in text  # actionable message, not the raw exception
    assert "`" not in text  # sent with ParseMode.HTML, not Markdown — no bare backticks
    assert "<code>mailwright login</code>" in text


def test_generic_exception_gets_generic_failure_message():
    text = _poll_failure_text(ValueError("boom"))

    assert "Poll failed" in text
    assert "boom" in text
