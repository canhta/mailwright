from mailwright.telegram.commands.base import Action, Domain, find_action, usage_text


def _noop_handler(update, context, args):
    pass


def _domain():
    return Domain(
        name="mail",
        description="Mail polling and pipeline settings",
        actions=[
            Action("poll", "Manually trigger a mail poll right now", _noop_handler),
            Action("pause", "Pause automatic polling", _noop_handler),
        ],
    )


def test_find_action_matches_case_insensitively():
    domain = _domain()
    action = find_action(domain, "PAUSE")
    assert action is not None and action.name == "pause"


def test_find_action_returns_none_when_missing():
    assert find_action(_domain(), "bogus") is None


def test_usage_text_lists_all_action_names():
    text = usage_text(_domain())
    assert text == "Usage: /mail &lt;poll|pause&gt;"


def test_usage_text_is_html_safe():
    # Telegram's HTML parse mode raises BadRequest on a literal, unescaped
    # "<...>" it can't recognize as a real tag — usage_text() must return
    # text that's already safe to send with parse_mode=ParseMode.HTML.
    text = usage_text(_domain())
    assert "<" not in text
    assert ">" not in text
