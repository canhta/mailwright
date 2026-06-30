from dataclasses import dataclass


@dataclass
class Message:
    id: str
    internet_message_id: str
    conversation_id: str
    sender: str
    subject: str
    received_at: str
    body_preview: str
    body: str
    has_attachments: bool = False


@dataclass
class AttachmentMeta:
    id: str
    name: str
    content_type: str
    size: int
    is_inline: bool


@dataclass
class AttachmentContent:
    name: str
    content_type: str
    data: bytes
