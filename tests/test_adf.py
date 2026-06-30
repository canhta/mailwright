from mailwright.jira.adf import adf_from_text


def test_single_paragraph():
    doc = adf_from_text("Hello world")
    assert doc == {
        "type": "doc",
        "version": 1,
        "content": [{"type": "paragraph", "content": [{"type": "text", "text": "Hello world"}]}],
    }


def test_multiple_paragraphs():
    doc = adf_from_text("First.\n\nSecond.")
    assert len(doc["content"]) == 2
    assert doc["content"][1]["content"][0]["text"] == "Second."


def test_empty_text_yields_empty_paragraph():
    doc = adf_from_text("")
    assert doc["content"] == [{"type": "paragraph", "content": []}]
