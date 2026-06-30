import pytest
from mailwright.brain.llm import LlmError, OpenAIStructuredLLM
from mailwright.brain.schemas import Classification


class _Msg:
    def __init__(self, parsed=None, refusal=None):
        self.parsed = parsed
        self.refusal = refusal


class _Choice:
    def __init__(self, message):
        self.message = message


class _Completion:
    def __init__(self, message):
        self.choices = [_Choice(message)]


class _FakeParse:
    def __init__(self, result):
        self._result = result
        self.kwargs = None

    def __call__(self, **kwargs):
        self.kwargs = kwargs
        return _Completion(self._result)


class _FakeClient:
    def __init__(self, result):
        parse = _FakeParse(result)
        self.parse = parse
        self.chat = type("C", (), {"completions": type("D", (), {"parse": parse})()})()


def test_parse_returns_parsed_object_and_passes_model():
    expected = Classification(
        is_request=True,
        needs_ticket=True,
        issue_type="Task",
        priority="Medium",
        confidence=0.9,
        reason="clear ask",
        is_urgent=False,
    )
    client = _FakeClient(_Msg(parsed=expected))
    llm = OpenAIStructuredLLM(client, "gpt-4o-mini")

    got = llm.parse("sys", "user text", Classification)

    assert got is expected
    sent = client.chat.completions.parse.kwargs
    assert sent["model"] == "gpt-4o-mini"
    assert sent["response_format"] is Classification
    assert sent["messages"][0]["role"] == "system"
    assert sent["messages"][1]["content"] == "user text"


def test_parse_raises_on_refusal():
    client = _FakeClient(_Msg(parsed=None, refusal="cannot help"))
    llm = OpenAIStructuredLLM(client, "gpt-4o-mini")
    with pytest.raises(LlmError, match="cannot help"):
        llm.parse("sys", "user", Classification)


class _CreateMsg:
    def __init__(self, content):
        self.content = content


class _FakeCreate:
    def __init__(self, content):
        self._content = content
        self.captured = {}

    def __call__(self, **kwargs):
        self.captured.update(kwargs)
        return _Completion(_CreateMsg(self._content))


class _CreateClient:
    def __init__(self, content):
        create = _FakeCreate(content)
        self.captured = create.captured
        self.chat = type("C", (), {"completions": type("D", (), {"create": create})()})()


def test_json_object_llm_embeds_schema_and_validates():
    from mailwright.brain.llm import JsonObjectLLM

    payload = (
        '{"is_request": true, "needs_ticket": true, "issue_type": "Task", '
        '"priority": "Medium", "confidence": 0.8, "reason": "ok", "is_urgent": false}'
    )
    client = _CreateClient(payload)
    got = JsonObjectLLM(client, "deepseek-chat").parse("sys", "user", Classification)

    assert isinstance(got, Classification)
    assert got.issue_type == "Task"
    sent = client.captured
    assert sent["response_format"] == {"type": "json_object"}
    assert "json" in sent["messages"][0]["content"].lower()  # schema embedded, satisfies json-mode


def test_parse_with_images_builds_content_parts():
    expected = Classification(
        is_request=True,
        needs_ticket=True,
        issue_type="Task",
        priority="Medium",
        confidence=0.9,
        reason="r",
        is_urgent=False,
    )
    client = _FakeClient(_Msg(parsed=expected))
    llm = OpenAIStructuredLLM(client, "gpt-4o")

    llm.parse("sys", "look at this", Classification, images=["data:image/png;base64,AAA"])

    content = client.chat.completions.parse.kwargs["messages"][1]["content"]
    assert isinstance(content, list)
    assert any(p["type"] == "text" for p in content)
    assert any(p["type"] == "image_url" for p in content)


def test_text_llm_calls_create_and_returns_content():
    from mailwright.brain.llm import OpenAITextLLM

    client = _CreateClient("Hello, world!")
    llm = OpenAITextLLM(client, "gpt-4o-mini")
    result = llm.complete("You are helpful.", "Hi!")
    assert result == "Hello, world!"
    assert client.captured["model"] == "gpt-4o-mini"
    assert client.captured["messages"][0]["role"] == "system"
    assert client.captured["messages"][1]["content"] == "Hi!"


def test_build_structured_llm_selects_impl():
    from mailwright.brain.llm import (
        JsonObjectLLM,
        OpenAIStructuredLLM,
        build_structured_llm,
    )

    assert isinstance(build_structured_llm(object(), "m", "json_object"), JsonObjectLLM)
    assert isinstance(build_structured_llm(object(), "m", "json_schema"), OpenAIStructuredLLM)
