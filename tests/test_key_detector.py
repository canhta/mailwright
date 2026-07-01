from mailwright.tasks.key_detector import find_jira_keys, mail_references_ticket


def test_finds_keys_in_order_unique():
    text = "See PROD-12 and SU-3, also PROD-12 again."
    assert find_jira_keys(text) == ["PROD-12", "SU-3"]


def test_ignores_non_keys():
    assert (
        find_jira_keys("no keys here, A-1 lowercase ab-1") == ["A-1"]
        or find_jira_keys("call me at 555-1234") == []
    )


def test_no_keys_returns_empty():
    assert find_jira_keys("just a plain sentence") == []


def test_mail_references_ticket_checks_subject_and_body():
    assert mail_references_ticket("Re: PROD-9 fix", "body") is True
    assert mail_references_ticket("New request", "tracked as SU-77") is True
    assert mail_references_ticket("New request", "no ticket yet") is False
