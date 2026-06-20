import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from src.core.config import EVOLUTION_WEBHOOK_TOKEN
from src.db.session import init_database, is_database_configured
from src.services.evolution import parse_incoming_message, send_text
from src.services.lia_orchestrator import process_message

logger = logging.getLogger(__name__)


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    phone_number: str = "local"
    contact_name: str | None = None


class ChatResponse(BaseModel):
    reply: str


@asynccontextmanager
async def lifespan(app: FastAPI):
    if is_database_configured():
        await run_in_threadpool(init_database)
    else:
        logger.warning("SUPABASE_DATABASE_URL nao configurada. Resumos finais nao serao salvos.")
    yield


app = FastAPI(
    title="Lia RH Agent",
    description="Agente multi-agent da TalentBank/MySkills integrado a Evolution API.",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    reply = await run_in_threadpool(
        process_message,
        phone_number=request.phone_number,
        contact_name=request.contact_name,
        text=request.message,
        source="local",
    )
    return ChatResponse(reply=reply)


@app.post("/webhook/evolution")
async def evolution_webhook(request: Request):
    _validate_webhook_token(request)

    payload = await request.json()
    incoming = parse_incoming_message(payload)
    if not incoming:
        return {"status": "ignored", "reason": "message_not_supported"}
    if incoming.from_me:
        return {"status": "ignored", "reason": "from_me"}
    if incoming.is_group:
        return {"status": "ignored", "reason": "group_message"}

    reply = await run_in_threadpool(
        process_message,
        phone_number=incoming.phone_number,
        contact_name=incoming.contact_name,
        text=incoming.text,
        source="whatsapp",
    )
    sent = await run_in_threadpool(
        send_text,
        number=incoming.phone_number,
        text=reply,
        instance=incoming.instance,
    )

    return {
        "status": "processed",
        "sent": sent,
        "phone_number": incoming.phone_number,
        "reply": reply,
    }


def _validate_webhook_token(request: Request) -> None:
    if not EVOLUTION_WEBHOOK_TOKEN:
        return

    token = (
        request.headers.get("x-webhook-token")
        or request.headers.get("x-evolution-token")
        or request.query_params.get("token")
    )
    if token != EVOLUTION_WEBHOOK_TOKEN:
        raise HTTPException(status_code=401, detail="Token do webhook invalido.")
