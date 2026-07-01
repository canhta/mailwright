SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "search_memory",
            "description": (
                "Search the episodic activity log for past events and learned behavioral patterns "
                "around a topic. Does not cover stored facts or rules — use list_memory for those."
            ),
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
            "description": (
                "Get the most recent episodic activity log entries. Does not cover stored facts "
                "or rules — use list_memory for those."
            ),
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
                "Persist a NEW behavioral rule the owner wants you to always follow when drafting "
                "Jira tickets (tone, required fields, when to ask before creating, etc). The rule "
                "takes effect immediately and shows up in /rules. Call this as soon as the owner "
                "asks you to always do something a certain way — never reply that a rule is saved "
                "unless this tool call succeeded. To edit or retire an EXISTING rule, use "
                "update_rule instead of adding a duplicate."
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
                "Persist a NEW standing background fact the owner wants you to remember permanently "
                "(project context, definitions, business facts — not a drafting behavior rule, "
                "use add_rule for those). Call this as soon as the owner asks you to remember or "
                "note something — never reply that something is saved unless this tool call "
                "succeeded. If the owner is correcting or replacing an EXISTING fact, use "
                "forget_fact on the old one (then store_fact the correction) instead of storing a "
                "duplicate."
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
    {
        "type": "function",
        "function": {
            "name": "list_memory",
            "description": (
                "List every stored rule and fact, with their IDs. Call this before update_rule "
                "or forget_fact so you know the exact id to target — never guess an id."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_rule",
            "description": (
                "Edit a rule's text and/or set its status. Use status='retired' when the owner "
                "says a rule no longer applies (this is reversible — set status='active' again "
                "to reinstate it later). Call list_memory first to get the exact rule_id."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "rule_id": {"type": "integer", "description": "id from list_memory"},
                    "text": {"type": "string", "description": "New rule text, if changing it"},
                    "status": {
                        "type": "string",
                        "enum": ["active", "retired"],
                        "description": "New status, if changing it",
                    },
                },
                "required": ["rule_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "forget_fact",
            "description": (
                "Permanently delete a stored fact by id. Irreversible — the fact is gone, not just "
                "hidden (re-add it with store_fact if it turns out you need it again). Call "
                "list_memory first to confirm the exact fact_id; if it's ambiguous which fact the "
                "owner means, ask instead of guessing."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "fact_id": {"type": "integer", "description": "id from list_memory"},
                },
                "required": ["fact_id"],
            },
        },
    },
]


class MemoryTools:
    def __init__(self, episodic_repo, vector_store, embedder, rulebook_repo, topk: int) -> None:
        self._episodic = episodic_repo
        self._vectors = vector_store
        self._embedder = embedder
        self._rules = rulebook_repo
        self._topk = topk

    def search_memory(self, args: dict) -> object:
        hits = self._episodic.search(args.get("query", ""), limit=self._topk)
        return [{"ts": e.ts, "content": e.content} for e in hits]

    def get_recent_events(self, args: dict) -> object:
        n = args.get("n", 5)
        entries = self._episodic.recent(limit=n)
        return [{"ts": e.ts, "content": e.content} for e in entries]

    def add_rule(self, args: dict) -> object:
        text = args.get("rule", "").strip()
        if not text:
            return {"stored": False, "error": "rule text is empty"}
        if not self._rules:
            return {"stored": False, "error": "rulebook not configured"}
        rule_id = self._rules.add("manual", text, status="active")
        return {"stored": True, "rule_id": rule_id, "rule": text}

    def store_fact(self, args: dict) -> object:
        text = args.get("fact", "").strip()
        if not text:
            return {"stored": False, "error": "fact text is empty"}
        try:
            vec = self._embedder.embed([text])[0]
            self._vectors.add("fact", text, vec)
            return {"stored": True, "fact": text}
        except Exception as exc:
            return {"stored": False, "error": str(exc)}

    def list_memory(self, args: dict) -> object:
        rules = (
            [{"id": r.id, "text": r.text, "status": r.status} for r in self._rules.list_all()]
            if self._rules
            else []
        )
        facts = [
            {"id": fid, "text": text, "created_at": created_at}
            for fid, text, created_at in self._vectors.list_by_kind("fact")
        ]
        return {"rules": rules, "facts": facts}

    def update_rule(self, args: dict) -> object:
        if not self._rules:
            return {"updated": False, "error": "rulebook not configured"}
        rule_id = args["rule_id"]
        text = args.get("text")
        status = args.get("status")
        if text is None and status is None:
            return {"updated": False, "error": "must provide text and/or status"}
        if status is not None and status not in ("active", "retired"):
            return {"updated": False, "error": "status must be 'active' or 'retired'"}
        updated = self._rules.update(rule_id, text=text, status=status)
        if not updated:
            return {"updated": False, "error": f"no rule with id {rule_id}"}
        return {"updated": True, "rule_id": rule_id}

    def forget_fact(self, args: dict) -> object:
        fact_id = args["fact_id"]
        deleted = self._vectors.delete(fact_id)
        if not deleted:
            return {"deleted": False, "error": f"no fact with id {fact_id}"}
        return {"deleted": True, "fact_id": fact_id}

    def handlers(self) -> dict:
        return {
            "search_memory": self.search_memory,
            "get_recent_events": self.get_recent_events,
            "add_rule": self.add_rule,
            "store_fact": self.store_fact,
            "list_memory": self.list_memory,
            "update_rule": self.update_rule,
            "forget_fact": self.forget_fact,
        }
