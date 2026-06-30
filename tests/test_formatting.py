from mailwright.telegram.formatting import h, md_to_html


def test_h_escapes_html_special_chars():
    assert h("AT&T <Corp>") == "AT&amp;T &lt;Corp&gt;"


def test_h_coerces_non_string():
    assert h(None) == "None"
    assert h(42) == "42"


def test_md_to_html_bold():
    assert md_to_html("We have **19 bugs**") == "We have <b>19 bugs</b>"


def test_md_to_html_italic():
    assert md_to_html("this is *important*") == "this is <i>important</i>"


def test_md_to_html_escapes_before_converting():
    result = md_to_html("AT&T **bold** <nil>")
    assert "AT&amp;T" in result
    assert "<b>bold</b>" in result
    assert "&lt;nil&gt;" in result


def test_md_to_html_inline_bold_in_list():
    result = md_to_html("- **Status:** In Progress\n- **Priority:** High")
    assert "<b>Status:</b>" in result
    assert "<b>Priority:</b>" in result


def test_md_to_html_bullet_asterisks_not_treated_as_italic():
    text = "* Bug one\n* Bug two"
    result = md_to_html(text)
    assert "<i>" not in result


def test_md_to_html_plain_text_unchanged():
    assert md_to_html("hello world") == "hello world"


def test_md_to_html_jira_angle_brackets_escaped():
    result = md_to_html("error: <nil> value")
    assert "<nil>" not in result
    assert "&lt;nil&gt;" in result
