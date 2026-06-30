class AttachmentUploader:
    def __init__(self, owa_client, jira_client) -> None:
        self._owa = owa_client
        self._jira = jira_client

    def upload_all(self, owa_message_id: str, has_attachments: bool, issue_key: str) -> int:
        if not has_attachments:
            return 0
        count = 0
        for meta in self._owa.list_attachments(owa_message_id):
            content = self._owa.get_attachment(owa_message_id, meta.id)
            self._jira.add_attachment(issue_key, content.name, content.data, content.content_type)
            count += 1
        return count
