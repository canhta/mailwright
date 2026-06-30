from dataclasses import dataclass, field

from mailwright.ingest.extract import extract_text, image_data_uri
from mailwright.models import Message


@dataclass
class LoadedAttachments:
    texts: list[str] = field(default_factory=list)
    images: list[str] = field(default_factory=list)


class AttachmentLoader:
    def __init__(self, owa_client, gate, vision_enabled: bool) -> None:
        self._owa = owa_client
        self._gate = gate
        self._vision_enabled = vision_enabled

    def load(self, message: Message) -> LoadedAttachments:
        if not message.has_attachments:
            return LoadedAttachments()
        metas = self._owa.list_attachments(message.id)
        decision = self._gate.decide(message.subject, message.body, metas)
        if not decision.read:
            return LoadedAttachments()

        chosen = set(decision.attachment_ids)
        texts: list[str] = []
        images: list[str] = []
        for meta in metas:
            if meta.id not in chosen:
                continue
            content = self._owa.get_attachment(message.id, meta.id)
            text = extract_text(content)
            if text:
                texts.append(text)
            if self._vision_enabled:
                uri = image_data_uri(content)
                if uri:
                    images.append(uri)
        return LoadedAttachments(texts=texts, images=images)
