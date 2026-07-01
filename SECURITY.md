# Security Policy

mailwright is currently a single-deploy personal project, not a published
package with a formal security process. If you find a vulnerability, please
report it privately rather than opening a public issue.

## Reporting a Vulnerability

Email **canhta.w@gmail.com** with:

- A description of the issue and its impact
- Steps to reproduce (or a proof of concept)
- Any suggested fix, if you have one

Please allow a reasonable amount of time to investigate and patch before any
public disclosure.

## Scope

Things especially worth flagging:

- Handling of secrets: `FERNET_KEY` (encrypts the OWA session), Jira API
  token, LLM API key, Telegram bot token — all read from environment
  variables, never logged or persisted in plaintext by design.
- The Telegram allowlist / Jira webhook secret gating who can trigger
  mutating actions (ticket creation/deletion, email sending).
- Any path where untrusted mail content could reach an LLM tool call with
  side effects (Jira writes, email sends) without the owner's confirmation.
