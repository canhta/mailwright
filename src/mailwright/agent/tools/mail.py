SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "send_email",
            "description": (
                "Send an email. Irreversible once sent. Only call this after the owner has "
                "explicitly confirmed the To/Subject/Body you showed them ('send it', 'yes, "
                "send') — never on vague approval like 'looks good' or 'ok'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "to": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Recipient email address(es)",
                    },
                    "subject": {"type": "string"},
                    "body": {"type": "string"},
                    "cc": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "CC email address(es), if any",
                    },
                    "bcc": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "BCC email address(es), if any",
                    },
                },
                "required": ["to", "subject", "body"],
            },
        },
    },
]


class MailTools:
    def __init__(self, owa, episodic_repo) -> None:
        self._owa = owa
        self._episodic = episodic_repo

    def send_email(self, args: dict) -> object:
        to = [addr.strip() for addr in args.get("to") or [] if addr.strip()]
        cc = [addr.strip() for addr in args.get("cc") or [] if addr.strip()]
        bcc = [addr.strip() for addr in args.get("bcc") or [] if addr.strip()]
        subject = args.get("subject", "").strip()
        body = args.get("body", "").strip()
        if not self._owa:
            return {"sent": False, "error": "mail sending not configured"}
        if not to or not subject or not body:
            return {"sent": False, "error": "to, subject, and body are all required"}
        try:
            self._owa.send_mail(to, subject, body, cc=cc or None, bcc=bcc or None)
            log_line = f"To: {', '.join(to)}\nSubject: {subject}"
            if cc:
                log_line += f"\nCc: {', '.join(cc)}"
            if bcc:
                log_line += f"\nBcc: {', '.join(bcc)}"
            self._episodic.add("sent_email", log_line)
            return {"sent": True, "to": to, "cc": cc, "bcc": bcc, "subject": subject}
        except Exception as exc:
            return {"sent": False, "error": str(exc)}

    def handlers(self) -> dict:
        return {"send_email": self.send_email}
