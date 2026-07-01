from mailwright.config import Settings
from mailwright.db.connection import get_connection
from mailwright.db.schema import init_db
from mailwright.models import Message
from mailwright.poller.mail_poller import MailPoller
from mailwright.repositories.processed_mails import ProcessedMailRepo


class FakeClient:
    def __init__(self, messages):
        self._messages = messages
        self.calls = []

    def list_messages(self, folder, since=None, top=50):
        self.calls.append((folder, since))
        return self._messages


def _msg(mid, sender):
    return Message(
        id="g-" + mid,
        internet_message_id=mid,
        conversation_id="c-" + mid,
        sender=sender,
        subject="Subj",
        received_at="2026-06-30T01:00:00Z",
        body_preview="p",
        body="b",
    )


def _settings(**over):
    base = dict(
        company_domain="example.com",
        fernet_key="k" * 44,
        mail_folder="Inbox",
        sender_allowlist=["product@example.com", "partner.com"],
    )
    base.update(over)
    return Settings(**base)


def _poller(tmp_path, messages, **over):
    conn = get_connection(str(tmp_path / "app.db"))
    init_db(conn)
    repo = ProcessedMailRepo(conn)
    return MailPoller(FakeClient(messages), repo, _settings(**over)), repo


def test_poll_keeps_only_allowlisted_senders(tmp_path):
    msgs = [
        _msg("<a>", "product@example.com"),  # exact email -> keep
        _msg("<b>", "someone@partner.com"),  # domain -> keep
        _msg("<c>", "spam@other.com"),  # not allowed -> drop
    ]
    poller, repo = _poller(tmp_path, msgs)

    new = poller.poll()

    assert {m.internet_message_id for m in new} == {"<a>", "<b>"}
    assert repo.exists("<a>") and repo.exists("<b>")
    assert repo.exists("<c>") is False


def test_poll_dedups_already_processed(tmp_path):
    msgs = [_msg("<a>", "product@example.com")]
    poller, repo = _poller(tmp_path, msgs)

    first = poller.poll()
    second = poller.poll()

    assert len(first) == 1
    assert second == []  # already stored, not returned again


def test_poll_persists_body_and_attachments(tmp_path):
    m = Message(
        id="g",
        internet_message_id="<x>",
        conversation_id="c",
        sender="product@example.com",
        subject="S",
        received_at="t",
        body_preview="p",
        body="BODY",
        has_attachments=True,
    )
    poller, repo = _poller(tmp_path, [m])
    poller.poll()
    got = repo.get("<x>")
    assert got.body == "BODY"
    assert got.has_attachments is True


class FakeRuntimeConfig:
    def __init__(self, sender_allowlist):
        self.sender_allowlist = sender_allowlist


class FakeRuntimeConfigRepo:
    def __init__(self, cfg):
        self._cfg = cfg

    def get(self):
        return self._cfg


def test_poll_uses_runtime_config_sender_allowlist_when_provided(tmp_path):
    conn = get_connection(str(tmp_path / "app.db"))
    init_db(conn)
    repo = ProcessedMailRepo(conn)
    settings = _settings(sender_allowlist=["should-not-be-used@example.com"])
    client = FakeClient([_msg("m1", "runtime@example.com"), _msg("m2", "blocked@example.com")])
    runtime_config = FakeRuntimeConfigRepo(FakeRuntimeConfig(["runtime@example.com"]))
    poller = MailPoller(client, repo, settings, runtime_config=runtime_config)

    new = poller.poll()

    assert [m.sender for m in new] == ["runtime@example.com"]
