from mailwright.agent.formatting import format_jql_results
from mailwright.jira.adf import adf_to_text
from mailwright.pipeline.deletion_service import DeletionService

SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "search_jira_jql",
            "description": (
                "Search Jira with a JQL query. Use for sprint overviews, project-level queries, "
                "filtering by status/assignee/type/label, or 'tickets created/updated recently' "
                '(e.g. jql="created >= -2h ORDER BY created DESC" — episodic memory does not '
                "store ticket keys, this is the way to find them). Returns matching issues. "
                "For a single already-known issue key, use get_jira_issue instead."
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
                "Returns summary, status, type, priority, assignee, and description. "
                "For searching by criteria instead of a known key, use search_jira_jql."
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
]


class JiraTools:
    def __init__(self, jira, episodic_repo, vector_store) -> None:
        self._jira = jira
        self._deletion = DeletionService(jira, episodic_repo, vector_store)

    def search_jira_jql(self, args: dict) -> object:
        if not self._jira:
            return {"error": "Jira not configured"}
        try:
            issues = self._jira.search_jql(
                args["jql"],
                max_results=args.get("max_results", 30),
                extra_fields=["customfield_10020"],
            )
            return format_jql_results(issues)
        except Exception as exc:
            return {"error": str(exc)}

    def get_jira_issue(self, args: dict) -> object:
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

    def delete_jira_issue(self, args: dict) -> object:
        if not self._jira:
            return {"error": "Jira not configured"}
        outcome = self._deletion.delete(args["key"])
        if outcome.deleted:
            return {"key": outcome.key, "deleted": True}
        return {"key": outcome.key, "deleted": False, "error": outcome.error}

    def handlers(self) -> dict:
        return {
            "search_jira_jql": self.search_jira_jql,
            "get_jira_issue": self.get_jira_issue,
            "delete_jira_issue": self.delete_jira_issue,
        }
