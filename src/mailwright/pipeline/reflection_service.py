from mailwright.llm.schemas import Reflection

_SYSTEM = (
    "You refine how an assistant writes Jira tickets for one owner, based on "
    "their recent edits and rejections. Produce an updated concise style_profile "
    "(natural language) and any proposed_rules (short, high-signal) worth adding. "
    "Propose rules sparingly; the owner will confirm them."
)


class ReflectionService:
    def __init__(
        self, episodic_repo, style_repo, rulebook_repo, structured_llm, lookback: int
    ) -> None:
        self._episodic = episodic_repo
        self._style = style_repo
        self._rulebook = rulebook_repo
        self._llm = structured_llm
        self._lookback = lookback

    def run(self) -> None:
        entries = [e for e in self._episodic.recent(self._lookback) if e.type in ("edit", "reject")]
        if not entries:
            return
        joined = "\n".join(f"- [{e.type}] {e.content}" for e in entries)
        refl: Reflection = self._llm.parse(_SYSTEM, f"Recent feedback:\n{joined}", Reflection)
        if refl.style_profile:
            self._style.set(refl.style_profile)
        for rule in refl.proposed_rules:
            self._rulebook.add("soft", rule, status="proposed")
