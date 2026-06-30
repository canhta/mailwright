import logging

from mailwright.jira.adf import adf_to_text

log = logging.getLogger(__name__)

_SYSTEM = (
    "You are Mailwright, a sharp personal assistant who helps the owner stay on top of "
    "their product emails and Jira tickets. Use the provided tools to look up current "
    "information — always prefer live Jira data over assumptions. "
    "Answer naturally and conversationally, like a knowledgeable colleague. "
    "Keep replies short unless detail is requested. No bullet lists unless there are "
    "genuinely multiple items. No robotic preambles — just answer directly."
)

_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_jira_jql",
            "description": (
                "Search Jira with a JQL query. Use for sprint overviews, project-level queries, "
                "filtering by status/assignee/type/label. Returns a list of matching issues."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "jql": {
                        "type": "string",
                        "description": "JQL query string, e.g. 'project = SU AND sprint in openSprints()'",
                    },
                    "max_results": {"type": "integer", "default": 30},
                },
                "required": ["jql"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_jira_issue",
            "description": (
                "Fetch a single Jira issue by key (e.g. SU-1234). "
                "Returns summary, status, type, priority, assignee, and description."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {"type": "string", "description": "Jira issue key, e.g. SU-1234"},
                },
                "required": ["key"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_memory",
            "description": "Search episodic memory for past events and learned behavioral patterns.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Natural language search query"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_recent_events",
            "description": "Get the most recent episodic memory entries (activity log).",
            "parameters": {
                "type": "object",
                "properties": {
                    "n": {"type": "integer", "default": 5},
                },
            },
        },
    },
]

_MAX_HISTORY = 3


class AnswerService:
    def __init__(
        self,
        episodic_repo,
        vector_store,
        embedder,
        tool_llm,
        topk: int,
        jira=None,
        project_key: str = "",
    ) -> None:
        self._episodic = episodic_repo
        self._vectors = vector_store
        self._embedder = embedder
        self._llm = tool_llm
        self._topk = topk
        self._jira = jira
        self._project_key = project_key
        self._history: list[tuple[str, str]] = []

    def _dispatch(self, name: str, args: dict) -> object:
        if name == "search_jira_jql":
            if not self._jira:
                return {"error": "Jira not configured"}
            try:
                issues = self._jira.search_jql(
                    args["jql"],
                    max_results=args.get("max_results", 30),
                    extra_fields=["customfield_10020"],
                )
                return self._format_jql_results(issues)
            except Exception as exc:
                return {"error": str(exc)}

        if name == "get_jira_issue":
            if not self._jira:
                return {"error": "Jira not configured"}
            try:
                issue = self._jira.get_issue(args["key"])
                f = issue.get("fields", {})
                desc = adf_to_text(f.get("description"))
                return {
                    "key": args["key"],
                    "summary": f.get("summary", ""),
                    "status": (f.get("status") or {}).get("name", ""),
                    "type": (f.get("issuetype") or {}).get("name", ""),
                    "priority": (f.get("priority") or {}).get("name", ""),
                    "assignee": (f.get("assignee") or {}).get("displayName", "unassigned"),
                    "url": self._jira.issue_url(args["key"]),
                    "description": desc,
                }
            except Exception as exc:
                return {"error": f"{args['key']} not found: {exc}"}

        if name == "search_memory":
            hits = self._episodic.search(args.get("query", ""), limit=self._topk)
            return [{"ts": e.ts, "content": e.content} for e in hits]

        if name == "get_recent_events":
            n = args.get("n", 5)
            entries = self._episodic.recent(limit=n)
            return [{"ts": e.ts, "content": e.content} for e in entries]

        return {"error": f"Unknown tool: {name}"}

    def _format_jql_results(self, issues: list[dict]) -> dict:
        sprint_name = ""
        for i in issues:
            sprints = (i.get("fields") or {}).get("customfield_10020") or []
            active = next(
                (s for s in sprints if isinstance(s, dict) and s.get("state") == "active"), None
            )
            if active:
                sprint_name = active.get("name", "")
                break

        items = []
        for i in issues:
            f = i.get("fields", {})
            items.append(
                {
                    "key": i["key"],
                    "summary": f.get("summary", ""),
                    "status": (f.get("status") or {}).get("name", ""),
                    "type": (f.get("issuetype") or {}).get("name", ""),
                    "assignee": (f.get("assignee") or {}).get("displayName", "unassigned"),
                }
            )
        result: dict = {"total": len(issues), "issues": items}
        if sprint_name:
            result["sprint"] = sprint_name
        return result

    def answer(self, question: str) -> str:
        history_messages: list[dict] = []
        for q, a in self._history[-_MAX_HISTORY:]:
            history_messages.append({"role": "user", "content": q})
            history_messages.append({"role": "assistant", "content": a})
        history_messages.append({"role": "user", "content": question})

        tools: list[dict] = (
            _TOOLS
            if self._jira
            else [
                t
                for t in _TOOLS
                if t["function"]["name"] in ("search_memory", "get_recent_events")  # type: ignore[index]
            ]
        )

        reply: str = self._llm.run(_SYSTEM, history_messages, tools, self._dispatch)
        self._history.append((question, reply))
        log.debug("answer: q=%r → %d chars", question[:60], len(reply))
        return reply
