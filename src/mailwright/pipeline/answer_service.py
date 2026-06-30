_SYSTEM = (
    "You answer the owner's questions about their email→Jira activity using "
    "ONLY the provided context. If the context is insufficient, say so. Be concise."
)


class AnswerService:
    def __init__(self, episodic_repo, vector_store, embedder, text_llm, topk: int) -> None:
        self._episodic = episodic_repo
        self._vectors = vector_store
        self._embedder = embedder
        self._llm = text_llm
        self._topk = topk

    def answer(self, question: str) -> str:
        hits = self._episodic.search(question, limit=self._topk)
        qvec = self._embedder.embed([question])[0]
        facts = self._vectors.search("fact", qvec, self._topk)
        ctx_lines = [f"- {h.content}" for h in hits] + [f"- {t}" for t, _ in facts]
        context = "\n".join(ctx_lines) if ctx_lines else "(no relevant memory)"
        user = f"Question: {question}\n\nContext:\n{context}"
        return str(self._llm.complete(_SYSTEM, user))
