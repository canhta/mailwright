class MemoryContext:
    def __init__(self, rulebook_repo, style_repo, vector_store, embedder, topk: int) -> None:
        self._rules = rulebook_repo
        self._style = style_repo
        self._vectors = vector_store
        self._embedder = embedder
        self._topk = topk

    def build(self, query_text: str) -> str:
        sections: list[str] = []

        rules = self._rules.render()
        if rules:
            sections.append("Rules (always follow):\n" + rules)

        style = self._style.get()
        if style:
            sections.append("Your writing style:\n" + style)

        qvec = self._embedder.embed([query_text])[0]
        examples = self._vectors.search("fewshot", qvec, self._topk)
        if examples:
            sections.append("Similar past tickets:\n" + "\n".join(f"- {t}" for t, _ in examples))

        facts = self._vectors.search("fact", qvec, self._topk)
        if facts:
            sections.append("Known facts:\n" + "\n".join(f"- {t}" for t, _ in facts))

        return "\n\n".join(sections)
