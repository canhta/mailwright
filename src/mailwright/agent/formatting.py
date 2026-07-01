def format_jql_results(issues: list[dict]) -> dict:
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
