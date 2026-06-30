import json
from typing import Any, Protocol, TypeVar, cast

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class LlmError(RuntimeError):
    pass


def _user_content(user: str, images: list[str] | None) -> str | list[dict]:
    if not images:
        return user
    parts: list[dict[str, Any]] = [{"type": "text", "text": user}]
    parts += [{"type": "image_url", "image_url": {"url": uri}} for uri in images]
    return parts


class StructuredLLM(Protocol):
    def parse(
        self, system: str, user: str, schema: type[T], images: list[str] | None = None
    ) -> T: ...


class OpenAIStructuredLLM:
    """Strict json_schema via chat.completions.parse — OpenAI, recent Ollama."""

    def __init__(self, client, model: str) -> None:
        self._client = client
        self._model = model

    def parse(self, system: str, user: str, schema: type[T], images: list[str] | None = None) -> T:
        completion = self._client.chat.completions.parse(
            model=self._model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": _user_content(user, images)},
            ],
            response_format=schema,
        )
        message = completion.choices[0].message
        if getattr(message, "parsed", None) is None:
            raise LlmError(getattr(message, "refusal", None) or "LLM returned no parse")
        return cast(T, message.parsed)


class JsonObjectLLM:
    """json_object mode + schema-in-prompt + Pydantic validation.

    For providers without strict json_schema support (DeepSeek, older Ollama).
    """

    def __init__(self, client, model: str) -> None:
        self._client = client
        self._model = model

    def parse(self, system: str, user: str, schema: type[T], images: list[str] | None = None) -> T:
        schema_json = json.dumps(schema.model_json_schema())
        sys_prompt = (
            f"{system}\n\nRespond ONLY with a single JSON object (no markdown, no "
            f"prose) that conforms to this JSON Schema:\n{schema_json}"
        )
        completion = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": _user_content(user, images)},
            ],
            response_format={"type": "json_object"},
        )
        content = completion.choices[0].message.content
        if not content:
            raise LlmError("LLM returned empty content")
        return schema.model_validate_json(content)


class OpenAITextLLM:
    def __init__(self, client, model: str) -> None:
        self._client = client
        self._model = model

    def complete(self, system: str, user: str) -> str:
        resp = self._client.chat.completions.create(
            model=self._model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        )
        return resp.choices[0].message.content or ""


def build_structured_llm(client, model: str, mode: str) -> StructuredLLM:
    if mode == "json_object":
        return JsonObjectLLM(client, model)
    return OpenAIStructuredLLM(client, model)
