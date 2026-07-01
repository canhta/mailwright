import logging

from mailwright.owa.replies import render_link_reply

log = logging.getLogger(__name__)


class Replier:
    def __init__(self, owa_client, thread_repo) -> None:
        self._owa = owa_client
        self._thread_repo = thread_repo

    def reply_link(self, conversation_id, owa_message_id, ticket_key, ticket_url) -> bool:
        if not owa_message_id:
            log.warning("replier: no owa_message_id for conv=%s — skip reply", conversation_id)
            return False
        rec = self._thread_repo.get(conversation_id)
        if rec is not None and rec.link_replied:
            log.debug("replier: already replied for conv=%s — skip", conversation_id)
            return False
        log.info(
            "replier: posting link reply for %s to owa_message_id=%s", ticket_key, owa_message_id
        )
        self._owa.reply_all(owa_message_id, render_link_reply(ticket_key, ticket_url))
        self._thread_repo.mark_link_replied(conversation_id)
        log.info("replier: reply sent for %s", ticket_key)
        return True
