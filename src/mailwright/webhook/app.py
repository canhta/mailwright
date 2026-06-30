import inspect

from fastapi import FastAPI, Header, HTTPException, Request

from mailwright.webhook.parse import parse_jira_webhook, verify_secret


def build_webhook_app(
    secret, status_service, send_notice, owa_secret="", save_owa_state=None
) -> FastAPI:
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

    @app.post("/owa/session")
    async def owa_session(request: Request, x_owa_upload_secret: str | None = Header(default=None)):
        provided = x_owa_upload_secret or request.query_params.get("secret") or ""
        if not verify_secret(provided, owa_secret):
            raise HTTPException(status_code=401, detail="bad secret")
        payload = await request.json()
        if save_owa_state is not None:
            save_owa_state(payload)
        return {"ok": True}

    return app
