from typing import Literal

from pydantic import BaseModel

IssueType = Literal["Bug", "Task", "Story", "Unclear"]
Priority = Literal["Highest", "High", "Medium", "Low", "Lowest", "Unclear"]


class Classification(BaseModel):
    is_request: bool
    needs_ticket: bool
    issue_type: IssueType
    priority: Priority
    confidence: float
    reason: str
    is_urgent: bool


class Draft(BaseModel):
    summary: str
    description: str
    issue_type: IssueType
    priority: Priority
    confidence: float


class ReadDecision(BaseModel):
    read: bool
    attachment_ids: list[str]
    reason: str


class TriageDecision(BaseModel):
    action: Literal["create", "queue_approval", "ignore", "skip_duplicate"]
    reason: str
    is_urgent: bool


class MemoryDecision(BaseModel):
    action: Literal["write", "skip"]
    insight: str  # empty string when action == "skip"


class Reflection(BaseModel):
    style_profile: str
    proposed_rules: list[str]
