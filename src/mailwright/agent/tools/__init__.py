from mailwright.agent.tools.jira import SCHEMAS as JIRA_SCHEMAS
from mailwright.agent.tools.jira import JiraTools
from mailwright.agent.tools.mail import SCHEMAS as MAIL_SCHEMAS
from mailwright.agent.tools.mail import MailTools
from mailwright.agent.tools.memory import SCHEMAS as MEMORY_SCHEMAS
from mailwright.agent.tools.memory import MemoryTools

ALL_SCHEMAS = [*JIRA_SCHEMAS, *MEMORY_SCHEMAS, *MAIL_SCHEMAS]
NON_JIRA_SCHEMAS = [*MEMORY_SCHEMAS, *MAIL_SCHEMAS]

__all__ = [
    "ALL_SCHEMAS",
    "NON_JIRA_SCHEMAS",
    "JiraTools",
    "MemoryTools",
    "MailTools",
]
