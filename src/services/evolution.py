import logging
import re
from dataclasses import dataclass
from typing import Any

import requests

from src.core.config import (
    EVOLUTION_API_KEY,
    EVOLUTION_API_URL,
    EVOLUTION_INSTANCE,
    REQUEST_TIMEOUT_SECONDS,
)

logger = logging.getLogger(__name__)


@dataclass
class IncomingMessage:
    instance: str | None
    remote_jid: str | None
    phone_number: str
    contact_name: str | None
    text: str
    from_me: bool = False
    is_group: bool = False
    message_id: str | None = None


def parse_incoming_message(payload: dict[str, Any]) -> IncomingMessage | None:
    data = payload.get("data") or payload
    key = data.get("key") or {}
    message = data.get("message") or payload.get("message") or {}

    remote_jid = (
        key.get("remoteJid")
        or data.get("remoteJid")
        or data.get("chatId")
        or payload.get("remoteJid")
    )
    from_me = bool(key.get("fromMe") or data.get("fromMe"))
    text = _extract_text(message) or data.get("text") or payload.get("text")

    if not remote_jid or not text:
        return None

    is_group = str(remote_jid).endswith("@g.us")
    phone_number = _normalize_phone_number(remote_jid)
    if not phone_number:
        return None

    return IncomingMessage(
        instance=payload.get("instance") or data.get("instance") or EVOLUTION_INSTANCE,
        remote_jid=remote_jid,
        phone_number=phone_number,
        contact_name=data.get("pushName") or payload.get("pushName") or data.get("senderName"),
        text=str(text).strip(),
        from_me=from_me,
        is_group=is_group,
        message_id=key.get("id") or data.get("messageId"),
    )


def send_text(
    *,
    number: str,
    text: str,
    instance: str | None = None,
) -> bool:
    if not EVOLUTION_API_URL or not EVOLUTION_API_KEY:
        logger.warning("Evolution API nao configurada. Resposta nao enviada.")
        return False

    instance_name = instance or EVOLUTION_INSTANCE
    if not instance_name:
        logger.warning("EVOLUTION_INSTANCE nao configurada. Resposta nao enviada.")
        return False

    endpoint = f"{EVOLUTION_API_URL}/message/sendText/{instance_name}"
    headers = {
        "apikey": EVOLUTION_API_KEY,
        "Content-Type": "application/json",
    }
    body = {
        "number": number,
        "text": text,
    }

    response = requests.post(
        endpoint,
        headers=headers,
        json=body,
        timeout=REQUEST_TIMEOUT_SECONDS,
    )

    if response.status_code >= 400:
        logger.error(
            "Falha ao enviar mensagem pela Evolution API: %s %s",
            response.status_code,
            response.text,
        )
        return False

    return True


def _extract_text(message: dict[str, Any]) -> str | None:
    if not isinstance(message, dict):
        return None

    candidates = [
        message.get("conversation"),
        (message.get("extendedTextMessage") or {}).get("text"),
        (message.get("imageMessage") or {}).get("caption"),
        (message.get("videoMessage") or {}).get("caption"),
        (message.get("documentMessage") or {}).get("caption"),
        (message.get("buttonsResponseMessage") or {}).get("selectedDisplayText"),
        (message.get("buttonsResponseMessage") or {}).get("selectedButtonId"),
        (message.get("listResponseMessage") or {}).get("title"),
        (message.get("templateButtonReplyMessage") or {}).get("selectedDisplayText"),
    ]

    for candidate in candidates:
        if candidate:
            return str(candidate)
    return None


def _normalize_phone_number(remote_jid: str) -> str:
    number = str(remote_jid).split("@", 1)[0]
    return re.sub(r"\D", "", number)
