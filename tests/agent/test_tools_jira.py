from tests.agent.conftest import make_service


class FakeJira:
    def __init__(self, fail_keys=()):
        self.deleted: list[str] = []
        self._fail_keys = set(fail_keys)

    def delete_issue(self, key):
        if key in self._fail_keys:
            raise RuntimeError(f"{key} not found")
        self.deleted.append(key)


def test_delete_jira_issue_tool_deletes_and_cleans_up(tmp_path):
    jira = FakeJira()
    svc, ep, vs = make_service(tmp_path, jira=jira)
    ep.add("insight", "something about SU-1718", ref="SU-1718")
    vec = [1.0, 0.0]
    vs.add("fewshot", "SU-1718 text", vec, ref="SU-1718")

    result = svc._dispatch("delete_jira_issue", {"key": "SU-1718"})

    assert jira.deleted == ["SU-1718"]
    assert result == {"key": "SU-1718", "deleted": True}
    assert ep.search("SU-1718", limit=10) == []


def test_delete_jira_issue_tool_reports_failure_without_raising(tmp_path):
    jira = FakeJira(fail_keys={"SU-9999"})
    svc, _, _ = make_service(tmp_path, jira=jira)

    result = svc._dispatch("delete_jira_issue", {"key": "SU-9999"})

    assert result["key"] == "SU-9999"
    assert result["deleted"] is False
    assert "error" in result
