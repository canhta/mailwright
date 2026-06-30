import inspect

from fastapi import FastAPI, Header, HTTPException, Request

from mailwright.webhook.parse import parse_jira_webhook, verify_secret


def build_webhook_app(secret, status_service, send_notice) -> FastAPI:
    app = FastAPI()

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.post("/jira/webhook")
    async def jira_webhook(request: Request, x_webhook_secret: str | None = Header(default=None)):
        provided = x_webhook_secret or request.query_params.get("secret") or ""
        if not verify_secret(provided, secret):
            raise HTTPException(status_code=401, detail="bad secret")
        payload = await request.json()
        event = parse_jira_webhook(payload)
        if event is not None:
            message = status_service.handle(event)
            if message is not None:
                if inspect.iscoroutinefunction(send_notice):
                    await send_notice(message)
                else:
                    send_notice(message)
        return {"ok": True}

    return app
