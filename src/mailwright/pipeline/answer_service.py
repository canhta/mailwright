from mailwright.brain.key_detector import find_jira_keys
from mailwright.jira.adf import adf_to_text

_SYSTEM = (
    "You are Mailwright, a sharp personal assistant who helps the owner stay on top of "
    "their product emails and Jira tickets. Answer naturally and conversationally — like "
    "a knowledgeable colleague, not a database query. Use the provided context as your "
    "source of truth; if something isn't in the context, say you don't have that info "
    "rather than guessing. Keep replies short and to the point unless the owner asks for "
    "detail. No bullet lists unless there are genuinely multiple items. No robotic "
    "preambles like 'Based on the context' — just answer directly."
)

_SPRINT_KEYWORDS = {"sprint", "current sprint", "this sprint", "active sprint"}
_BACKLOG_KEYWORDS = {
    "backlog",
    "all tickets",
    "all tasks",
    "all issues",
    "open tickets",
    "open tasks",
}

_MAX_HISTORY = 3


class AnswerService:
    def __init__(
        self,
        episodic_repo,
        vector_store,
        embedder,
        text_llm,
        topk: int,
        jira=None,
        project_key: str = "",
    ) -> None:
        self._episodic = episodic_repo
        self._vectors = vector_store
        self._embedder = embedder
        self._llm = text_llm
        self._topk = topk
        self._jira = jira
        self._project_key = project_key
        self._history: list[tuple[str, str]] = []

    def _fetch_jql_context(self, question: str) -> list[str]:
        if not self._jira or not self._project_key:
            return []
        q = question.lower()
        jql = None
        if any(k in q for k in _SPRINT_KEYWORDS):
            jql = f'project = "{self._project_key}" AND sprint in openSprints() ORDER BY status ASC'
        elif any(k in q for k in _BACKLOG_KEYWORDS):
            jql = (
                f'project = "{self._project_key}" AND statusCategory != Done ORDER BY created DESC'
            )
        if not jql:
            return []
        try:
            issues = self._jira.search_jql(jql, max_results=50, extra_fields=["customfield_10020"])
        except Exception:
            return []
        if not issues:
            return [f"- No issues found for project {self._project_key} matching that query."]

        # Extract sprint name from the first issue that has it
        sprint_name = ""
        for i in issues:
            sprints = (i.get("fields") or {}).get("customfield_10020") or []
            active = next(
                (s for s in sprints if isinstance(s, dict) and s.get("state") == "active"), None
            )
            if active:
                sprint_name = active.get("name", "")
                break

        header = f"Sprint: {sprint_name} | " if sprint_name else ""
        lines = [f"- {header}{self._project_key} sprint issues ({len(issues)} total):"]
        for i in issues:
            f = i.get("fields", {})
            key = i["key"]
            summary = f.get("summary", "")
            status = (f.get("status") or {}).get("name", "")
            itype = (f.get("issuetype") or {}).get("name", "")
            assignee = (f.get("assignee") or {}).get("displayName", "unassigned")
            lines.append(f"  • {key} [{itype}/{status}] {summary} — {assignee}")
        return lines

    def _fetch_jira_context(self, question: str) -> list[str]:
        if not self._jira:
            return []
        keys = find_jira_keys(question)
        lines = []
        for key in keys:
            try:
                issue = self._jira.get_issue(key)
                f = issue.get("fields", {})
                summary = f.get("summary", "")
                status = (f.get("status") or {}).get("name", "")
                issue_type = (f.get("issuetype") or {}).get("name", "")
                priority = (f.get("priority") or {}).get("name", "")
                assignee = (f.get("assignee") or {}).get("displayName", "unassigned")
                url = self._jira.issue_url(key)
                description = adf_to_text(f.get("description"))
                lines.append(
                    f"- Jira {key}: {summary} | type={issue_type} status={status} "
                    f"priority={priority} assignee={assignee} url={url}"
                    + (f"\n  Description: {description}" if description else "")
                )
            except Exception:
                lines.append(f"- Jira {key}: not found or inaccessible")
        return lines

    def answer(self, question: str) -> str:
        hits = self._episodic.search(question, limit=self._topk)
        recent = self._episodic.recent(limit=4)
        qvec = self._embedder.embed([question])[0]
        facts = self._vectors.search("fact", qvec, self._topk)
        seen: set[int] = set()
        merged = []
        for e in recent + hits:
            if e.id not in seen:
                seen.add(e.id)
                merged.append(e)
        jira_lines = self._fetch_jql_context(question) or self._fetch_jira_context(question)
        ctx_lines = (
            jira_lines + [f"- [{e.ts}] {e.content}" for e in merged] + [f"- {t}" for t, _ in facts]
        )
        context = "\n".join(ctx_lines) if ctx_lines else "(no relevant memory)"

        history_lines = []
        for q, a in self._history[-_MAX_HISTORY:]:
            history_lines.append(f"User: {q}")
            history_lines.append(f"Assistant: {a}")

        user_parts = []
        if history_lines:
            user_parts.append("Conversation so far:\n" + "\n".join(history_lines))
        user_parts.append(f"Question: {question}\n\nContext:\n{context}")
        user = "\n\n".join(user_parts)

        reply = str(self._llm.complete(_SYSTEM, user))
        self._history.append((question, reply))
        return reply
