def render_link_reply(ticket_key: str, ticket_url: str) -> str:
    return (
        f"A Jira ticket has been created for this request: {ticket_key}\n"
        f"{ticket_url}\n\n"
        "(This is an automated message.)"
    )


def render_status_reply(ticket_key: str, ticket_url: str, status: str) -> str:
    return (
        f'Status update for {ticket_key}: now "{status}".\n'
        f"{ticket_url}\n\n"
        "(This is an automated message.)"
    )
