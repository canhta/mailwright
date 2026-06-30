import logging

from mailwright.jira.adf import adf_to_text

log = logging.getLogger(__name__)

_SYSTEM = (
    "You are Mailwright, a personal assistant helping the owner stay on top of "
    "their product emails and Jira tickets. "
    "Use the provided tools to look up current information; always prefer live Jira data over assumptions.\n\n"
    "Tone and format rules:\n"
    "- Write like a sharp colleague in a Slack thread: direct, brief, no ceremony.\n"
    "- Give a single reply. Never repeat information you already stated.\n"
    "- Use **bold** to highlight key numbers or ticket keys, e.g. **19 bugs** or **SU-1234**.\n"
    "- Never use em dashes. Use a colon or comma instead.\n"
    "- No filler openers: 'Here is the breakdown', 'The gist is', 'As I mentioned', 'Sure!', etc.\n"
    "- Bullet lists only when there are 3 or more enumerable items. Otherwise use prose.\n"
    "- Short by default. Go deeper only if the question explicitly asks for detail.\n\n"
    "Memory rules:\n"
    "- If the owner asks you to remember a fact, note something for later, or always follow a "
    "rule when drafting tickets, you MUST call store_fact or add_rule first.\n"
    "- Never tell the owner something is saved, remembered, or noted unless the matching tool "
    "call returned stored: true. If the tool call fails, say so plainly instead of pretending "
    "it worked."
)

_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_jira_jql",
            "description": (
                "Search Jira with a JQL query. Use for sprint overviews, project-level queries, "
                "filtering by status/assignee/type/label, or 'tickets created/updated recently' "
                '(e.g. jql="created >= -2h ORDER BY created DESC" — episodic memory does not '
                "store ticket keys, this is the way to find them). Returns matching issues."
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
            "name": "delete_jira_issue",
            "description": (
                "Permanently delete a Jira issue by key. Irreversible. Only call this after the "
                "user has explicitly confirmed the exact issue key; call once per key to delete "
                "more than one issue."
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
    {
        "type": "function",
        "function": {
            "name": "add_rule",
            "description": (
                "Persist a behavioral rule the owner wants you to always follow when drafting "
                "Jira tickets (tone, required fields, when to ask before creating, etc). The rule "
                "takes effect immediately and shows up in /rules. Call this as soon as the owner "
                "asks you to always do something a certain way — never reply that a rule is saved "
                "unless this tool call succeeded."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "rule": {
                        "type": "string",
                        "description": "The rule, written as a clear standalone directive",
                    },
                },
                "required": ["rule"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "store_fact",
            "description": (
                "Persist a standing background fact the owner wants you to remember permanently "
                "(project context, definitions, business facts — not a drafting behavior rule, "
                "use add_rule for those). Call this as soon as the owner asks you to remember or "
                "note something — never reply that something is saved unless this tool call "
                "succeeded."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "fact": {
                        "type": "string",
                        "description": "The fact to remember, written as a standalone statement",
                    },
                },
                "required": ["fact"],
            },
        },
    },
]

_MAX_HISTORY = 10


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
        commands: list[tuple[str, str]] | None = None,
        rulebook_repo=None,
    ) -> None:
        self._episodic = episodic_repo
        self._vectors = vector_store
        self._embedder = embedder
        self._llm = tool_llm
        self._topk = topk
        self._jira = jira
        self._project_key = project_key
        self._commands = commands or []
        self._rules = rulebook_repo
        self._history: list[tuple[str, str]] = []
        self._system = self._build_system_prompt()

    def _build_system_prompt(self) -> str:
        if not self._commands:
            return _SYSTEM
        cmd_lines = "\n".join(f"/{name}: {desc}" for name, desc in self._commands)
        return (
            f"{_SYSTEM}\n\n"
            "Available bot commands (the user can run these directly; tell them to if there's "
            "no matching tool, instead of guessing what the bot can or can't do):\n" + cmd_lines
        )

    def _dispatch(self, name: str, args: dict) -> object:
        log.info("answer: tool=%s args=%s", name, args)
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
            key = args["key"].upper().strip()
            try:
                issue = self._jira.get_issue(key)
                f = issue.get("fields", {})
                desc = adf_to_text(f.get("description"))
                return {
                    "key": key,
                    "summary": f.get("summary", ""),
                    "status": (f.get("status") or {}).get("name", ""),
                    "type": (f.get("issuetype") or {}).get("name", ""),
                    "priority": (f.get("priority") or {}).get("name", ""),
                    "assignee": (f.get("assignee") or {}).get("displayName", "unassigned"),
                    "url": self._jira.issue_url(key),
                    "description": desc,
                }
            except Exception as exc:
                return {"error": f"{key} not found: {exc}"}

        if name == "delete_jira_issue":
            if not self._jira:
                return {"error": "Jira not configured"}
            key = args["key"].upper().strip()
            try:
                self._jira.delete_issue(key)
                self._episodic.delete_by_ref(key)
                self._vectors.delete_by_ref(key)
                return {"key": key, "deleted": True}
            except Exception as exc:
                return {"key": key, "deleted": False, "error": str(exc)}

        if name == "search_memory":
            hits = self._episodic.search(args.get("query", ""), limit=self._topk)
            return [{"ts": e.ts, "content": e.content} for e in hits]

        if name == "get_recent_events":
            n = args.get("n", 5)
            entries = self._episodic.recent(limit=n)
            return [{"ts": e.ts, "content": e.content} for e in entries]

        if name == "add_rule":
            text = args.get("rule", "").strip()
            if not text:
                return {"stored": False, "error": "rule text is empty"}
            if not self._rules:
                return {"stored": False, "error": "rulebook not configured"}
            rule_id = self._rules.add("manual", text, status="active")
            return {"stored": True, "rule_id": rule_id, "rule": text}

        if name == "store_fact":
            text = args.get("fact", "").strip()
            if not text:
                return {"stored": False, "error": "fact text is empty"}
            try:
                vec = self._embedder.embed([text])[0]
                self._vectors.add("fact", text, vec)
                return {"stored": True, "fact": text}
            except Exception as exc:
                return {"stored": False, "error": str(exc)}

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
        log.info("answer: question=%r", question[:120])
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
                if t["function"]["name"]  # type: ignore[index]
                in ("search_memory", "get_recent_events", "store_fact", "add_rule")
            ]
        )

        reply: str = self._llm.run(self._system, history_messages, tools, self._dispatch)
        self._history.append((question, reply))
        log.debug("answer: q=%r → %d chars", question[:60], len(reply))
        return reply
