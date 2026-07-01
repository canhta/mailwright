import logging

from mailwright.agent.prompts import build_system_prompt
from mailwright.agent.tools import ALL_SCHEMAS, NON_JIRA_SCHEMAS, JiraTools, MailTools, MemoryTools
from mailwright.jira.client import JiraClient
from mailwright.llm.client import ToolCallLLM
from mailwright.memory.embedder import Embedder
from mailwright.memory.vector_store import VectorStore
from mailwright.owa.rest_client import OutlookRestClient
from mailwright.repositories.episodic import EpisodicRepo
from mailwright.repositories.rulebook import RulebookRepo

log = logging.getLogger(__name__)

_MAX_HISTORY = 10


class AnswerService:
    def __init__(
        self,
        episodic_repo: EpisodicRepo,
        vector_store: VectorStore,
        embedder: Embedder,
        tool_llm: ToolCallLLM,
        topk: int,
        jira: JiraClient | None = None,
        project_key: str = "",
        commands: list[tuple[str, str]] | None = None,
        rulebook_repo: RulebookRepo | None = None,
        owa: OutlookRestClient | None = None,
    ) -> None:
        self._episodic = episodic_repo
        self._vectors = vector_store
        self._embedder = embedder
        self._llm = tool_llm
        self._topk = topk
        self._jira = jira
        self._project_key = project_key
        self._commands = commands or []
        self._rules = rulebook_repo
        self._owa = owa
        self._history: list[tuple[str, str]] = []
        self._system = build_system_prompt(self._commands)

        jira_tools = JiraTools(jira, episodic_repo, vector_store)
        memory_tools = MemoryTools(episodic_repo, vector_store, embedder, rulebook_repo, topk)
        mail_tools = MailTools(owa, episodic_repo)
        self._handlers = {
            **jira_tools.handlers(),
            **memory_tools.handlers(),
            **mail_tools.handlers(),
        }

    def _dispatch(self, name: str, args: dict) -> object:
        log.info("answer: tool=%s args=%s", name, args)
        handler = self._handlers.get(name)
        if handler is None:
            return {"error": f"Unknown tool: {name}"}
        return handler(args)

    def reset_history(self) -> None:
        self._history = []

    def answer(self, question: str) -> str:
        log.info("answer: question=%r", question[:120])
        history_messages: list[dict] = []
        for q, a in self._history[-_MAX_HISTORY:]:
            history_messages.append({"role": "user", "content": q})
            history_messages.append({"role": "assistant", "content": a})
        history_messages.append({"role": "user", "content": question})

        tools = ALL_SCHEMAS if self._jira else NON_JIRA_SCHEMAS

        reply: str = self._llm.run(self._system, history_messages, tools, self._dispatch)
        self._history.append((question, reply))
        log.debug("answer: q=%r → %d chars", question[:60], len(reply))
        return reply
