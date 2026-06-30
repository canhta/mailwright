def adf_to_text(node: dict | None, max_chars: int = 600) -> str:
    """Extract plain text from an ADF document node, depth-first."""
    if not node:
        return ""
    parts: list[str] = []

    def _walk(n: dict) -> None:
        if n.get("type") == "text":
            parts.append(n.get("text", ""))
        elif n.get("type") in ("hardBreak", "rule"):
            parts.append("\n")
        for child in n.get("content") or []:
            _walk(child)
        if n.get("type") in ("paragraph", "heading", "listItem", "bulletList", "orderedList"):
            parts.append("\n")

    _walk(node)
    text = "".join(parts).strip()
    return text[:max_chars] + ("…" if len(text) > max_chars else "")


def adf_from_text(text: str) -> dict:
    blocks = text.split("\n\n") if text else [""]
    content = []
    for block in blocks:
        node: dict = {"type": "paragraph", "content": []}
        if block:
            node["content"].append({"type": "text", "text": block})
        content.append(node)
    return {"type": "doc", "version": 1, "content": content}
