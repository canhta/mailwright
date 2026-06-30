from mailwright.webhook.parse import WebhookEvent, parse_jira_webhook, verify_secret


def test_parse_custom_shape():
    assert parse_jira_webhook({"issue": "PROD-7", "status": "Done"}) == WebhookEvent(
        "PROD-7", "Done"
    )


def test_parse_native_shape():
    payload = {"issue": {"key": "PROD-7", "fields": {"status": {"name": "In Prod"}}}}
    assert parse_jira_webhook(payload) == WebhookEvent("PROD-7", "In Prod")


def test_parse_returns_none_when_incomplete():
    assert parse_jira_webhook({"issue": "PROD-7"}) is None
    assert parse_jira_webhook({}) is None


def test_verify_secret():
    assert verify_secret("abc", "abc") is True
    assert verify_secret("abc", "xyz") is False
    assert verify_secret("abc", "") is False
