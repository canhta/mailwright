def adf_from_text(text: str) -> dict:
    blocks = text.split("\n\n") if text else [""]
    content = []
    for block in blocks:
        node: dict = {"type": "paragraph", "content": []}
        if block:
            node["content"].append({"type": "text", "text": block})
        content.append(node)
    return {"type": "doc", "version": 1, "content": content}
