class FeedbackRecorder:
    def __init__(self, embedder, vector_store, episodic_repo) -> None:
        self._embedder = embedder
        self._vectors = vector_store
        self._episodic = episodic_repo

    def _add_fewshot(self, context_text: str, summary: str, description: str) -> None:
        text = f"Context: {context_text}\nTicket: {summary}\n{description}"
        vec = self._embedder.embed([text])[0]
        self._vectors.add("fewshot", text, vec)

    def record_created(self, context_text: str, draft, ticket_key: str) -> None:
        self._add_fewshot(context_text, draft.summary, draft.description)
        # Extract just From:/Subject: header lines — drop the body to avoid
        # email signatures being mistaken for the sender by the LLM.
        header = "\n".join(
            line
            for line in context_text.splitlines()
            if line.startswith("From:") or line.startswith("Subject:")
        )
        self._episodic.add(
            "ticket_created",
            f"Ticket: {ticket_key}\nSummary: {draft.summary}\nType: {draft.issue_type}\n{header}",
            ref=ticket_key,
        )

    def record_edit(self, context_text: str, old_desc: str, new_desc: str) -> None:
        self._add_fewshot(context_text, "(edited)", new_desc)
        self._episodic.add("edit", f"Edited draft. before='{old_desc}' after='{new_desc}'")

    def record_reject(self, context_text: str, reason: str) -> None:
        self._episodic.add("reject", f"Rejected: {reason}. Context: {context_text}")
