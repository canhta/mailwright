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


class Reflection(BaseModel):
    style_profile: str
    proposed_rules: list[str]
