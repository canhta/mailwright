from mailwright.db.connection import get_connection
from mailwright.db.schema import init_db
from mailwright.jira.models import DuplicateCandidate, TicketDraft, TicketResult
from mailwright.llm.schemas import Classification
from mailwright.models import Message
from mailwright.pipeline.attachment_loader import LoadedAttachments
from mailwright.pipeline.service import PipelineService
from mailwright.repositories.approvals import ApprovalRepo
from mailwright.repositories.processed_mails import ProcessedMail, ProcessedMailRepo
from mailwright.tasks.drafter import DraftOutcome


class FakeClassifier:
    def __init__(self, c):
        self.c = c

    def classify(self, m):
        return self.c


class FakeLoader:
    def load(self, m):
        return LoadedAttachments([], [])


class FakeDrafter:
    def __init__(self, o):
        self.o = o

    def draft(self, m, attachment_texts=None, images=None, memory_context=""):
        return self.o


class FakeTicketService:
    def __init__(self, dups=None):
        self.dups = dups or []
        self.created = []

    def find_duplicates(self, draft):
        return self.dups

    def create_or_comment(self, conv, mid, draft):
        self.created.append((conv, mid, draft))
        return TicketResult(key="PROD-9", url="https://x/PROD-9", created=True, commented=False)


class FakeUploader:
    def __init__(self):
        self.calls = []

    def upload_all(self, owa_id, has, key):
        self.calls.append((owa_id, has, key))
        return 1


def _msg(subject="Need export", body="Please add CSV export", has=False):
    return Message(
        id="owa-1",
        internet_message_id="<m>",
        conversation_id="conv-1",
        sender="pm@x.com",
        subject=subject,
        received_at="t",
        body_preview="",
        body=body,
        has_attachments=has,
    )


def _cls(is_req=True, needs=True, is_urgent=False):
    return Classification(
        is_request=is_req,
        needs_ticket=needs,
        issue_type="Story",
        priority="High",
        confidence=0.95,
        reason="r",
        is_urgent=is_urgent,
    )


def _outcome(conf=0.95, clear=True):
    return DraftOutcome(
        draft=TicketDraft("Add CSV export", "desc", "Story", "High"),
        confidence=conf,
        issue_type_clear=clear,
    )


def _svc(tmp_path, classifier, drafter, ticket_service, uploader, threshold=0.8, memory=None):
    conn = get_connection(str(tmp_path / "app.db"))
    init_db(conn)
    proc = ProcessedMailRepo(conn)
    proc.add(ProcessedMail(message_id="<m>", action="pending"))
    appr = ApprovalRepo(conn)
    svc = PipelineService(
        classifier,
        FakeLoader(),
        drafter,
        ticket_service,
        uploader,
        appr,
        proc,
        threshold,
        memory_context=memory,
    )
    return svc, proc, appr


def test_skip_when_has_ticket(tmp_path):
    svc, proc, _ = _svc(
        tmp_path,
        FakeClassifier(_cls()),
        FakeDrafter(_outcome()),
        FakeTicketService(),
        FakeUploader(),
    )
    out = svc.process_message(_msg(subject="Re: PROD-5"))
    assert out == []
    assert proc.get("<m>").action == "skip_has_ticket"


def test_ignore_when_not_request(tmp_path):
    svc, proc, _ = _svc(
        tmp_path,
        FakeClassifier(_cls(is_req=False)),
        FakeDrafter(_outcome()),
        FakeTicketService(),
        FakeUploader(),
    )
    assert svc.process_message(_msg()) == []
    assert proc.get("<m>").action == "ignore"


def test_auto_create_when_confident_no_dups(tmp_path):
    ts = FakeTicketService(dups=[])
    up = FakeUploader()
    svc, proc, _ = _svc(tmp_path, FakeClassifier(_cls()), FakeDrafter(_outcome(0.95)), ts, up)
    out = svc.process_message(_msg(has=True))
    assert len(out) == 1 and "PROD-9" in out[0].text
    assert ts.created and up.calls == [("owa-1", True, "PROD-9")]
    assert proc.get("<m>").action == "created" and proc.get("<m>").ticket_key == "PROD-9"


def test_needs_approval_when_low_confidence(tmp_path):
    svc, proc, appr = _svc(
        tmp_path,
        FakeClassifier(_cls()),
        FakeDrafter(_outcome(0.5)),
        FakeTicketService(),
        FakeUploader(),
    )
    out = svc.process_message(_msg())
    assert len(out) == 1 and out[0].approval_id is not None
    assert out[0].buttons[0][1].startswith("act:approve:")
    rec = appr.get(out[0].approval_id)
    assert rec.payload["draft"]["summary"] == "Add CSV export"
    assert proc.get("<m>").action == "needs_approval"


def test_duplicate_downgrades_to_approval(tmp_path):
    dups = [DuplicateCandidate("PROD-1", "Export CSV", "Open", "u")]
    svc, proc, appr = _svc(
        tmp_path,
        FakeClassifier(_cls()),
        FakeDrafter(_outcome(0.99)),
        FakeTicketService(dups),
        FakeUploader(),
    )
    out = svc.process_message(_msg())
    assert out[0].approval_id is not None  # not auto-created despite high confidence
    assert "PROD-1" in out[0].text


class FakeReplier:
    def __init__(self):
        self.calls = []

    def reply_link(self, conv, owa_id, key, url):
        self.calls.append((conv, owa_id, key, url))
        return True


def test_auto_create_calls_replier(tmp_path):
    ts = FakeTicketService(dups=[])
    up = FakeUploader()
    rep = FakeReplier()
    svc, _, _ = _svc(tmp_path, FakeClassifier(_cls()), FakeDrafter(_outcome(0.95)), ts, up)
    svc._replier = rep
    svc.process_message(_msg())
    assert len(rep.calls) == 1
    assert (
        rep.calls[0][0] == "conv-1" and rep.calls[0][1] == "owa-1" and rep.calls[0][2] == "PROD-9"
    )


class FakeMemory:
    def __init__(self):
        self.queries = []

    def build(self, q):
        self.queries.append(q)
        return "LEARNED CONTEXT"


def test_pipeline_passes_memory_context_to_drafter(tmp_path):
    class RecordingDrafter:
        def __init__(self, o):
            self.o = o
            self.ctx = None

        def draft(self, m, attachment_texts=None, images=None, memory_context=""):
            self.ctx = memory_context
            return self.o

    drafter = RecordingDrafter(_outcome(0.5))
    mem = FakeMemory()
    svc, _, _ = _svc(
        tmp_path, FakeClassifier(_cls()), drafter, FakeTicketService(), FakeUploader(), memory=mem
    )
    svc.process_message(_msg())
    assert drafter.ctx == "LEARNED CONTEXT"
    assert mem.queries


class FakeMemoryManager:
    def __init__(self):
        self.outcomes: list[tuple[str, str]] = []

    def on_outcome(self, event_type, email_summary, draft, result):
        self.outcomes.append((event_type, result))


def test_pipeline_records_memory_on_auto_create(tmp_path):
    ts = FakeTicketService(dups=[])
    up = FakeUploader()
    mgr = FakeMemoryManager()
    conn = get_connection(str(tmp_path / "app.db"))
    init_db(conn)
    proc = ProcessedMailRepo(conn)
    proc.add(ProcessedMail(message_id="<m>", action="pending"))
    appr = ApprovalRepo(conn)
    svc = PipelineService(
        FakeClassifier(_cls()),
        FakeLoader(),
        FakeDrafter(_outcome(0.95)),
        ts,
        up,
        appr,
        proc,
        0.8,
        feedback=mgr,
    )
    svc.process_message(_msg())
    assert any(ev == "created" and res == "PROD-9" for ev, res in mgr.outcomes)


def test_urgent_mail_emits_escalation_notice(tmp_path):
    cls = Classification(
        is_request=True,
        needs_ticket=True,
        issue_type="Story",
        priority="High",
        confidence=0.95,
        reason="r",
        is_urgent=True,
    )
    svc, proc, _ = _svc(
        tmp_path,
        FakeClassifier(cls),
        FakeDrafter(_outcome(0.95)),
        FakeTicketService(),
        FakeUploader(),
    )
    out = svc.process_message(_msg(subject="URGENT prod down"))
    assert "🚨" in out[0].text and "prod down" in out[0].text
