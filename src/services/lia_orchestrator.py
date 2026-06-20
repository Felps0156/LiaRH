import json
import logging
import re
from dataclasses import dataclass, field
from threading import RLock

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI

from src.core.config import AGENT_MAX_HISTORY_MESSAGES, MODEL
from src.core.links import (
    LINK_EMPRESA,
    LINK_INVESTIDOR,
    LINK_PARCERIA,
    LINK_PROFISSIONAL_VAGA,
    LINK_PROFISSIONAL_VAGAS,
)
from src.core.prompts import (
    system_prompt_empresa,
    system_prompt_investidor,
    system_prompt_lia,
    system_prompt_parceria,
    system_prompt_profissional,
)
from src.db.repository import save_lead_summary
from src.db.session import is_database_configured

logger = logging.getLogger(__name__)

PROFILE_EMPRESA = "empresa"
PROFILE_PROFISSIONAL = "profissional"
PROFILE_INVESTIDOR = "investidor"
PROFILE_PARCERIA = "parceria"
PROFILE_INDEFINIDO = "indefinido"

VALID_PROFILES = {
    PROFILE_EMPRESA,
    PROFILE_PROFISSIONAL,
    PROFILE_INVESTIDOR,
    PROFILE_PARCERIA,
}

PROFILE_PROMPTS = {
    PROFILE_EMPRESA: system_prompt_empresa,
    PROFILE_PROFISSIONAL: system_prompt_profissional,
    PROFILE_INVESTIDOR: system_prompt_investidor,
    PROFILE_PARCERIA: system_prompt_parceria,
}

RESET_WORDS = {"reiniciar", "resetar", "menu", "voltar", "comecar", "começar"}

_model = None
_sessions: dict[str, "ConversationSession"] = {}
_lock = RLock()


@dataclass
class ConversationSession:
    profile: str | None = None
    history: list[dict[str, str]] = field(default_factory=list)


@dataclass
class AgentResult:
    reply: str
    finalized: bool = False
    summary: str | None = None
    final_link: str | None = None


def process_message(
    *,
    phone_number: str,
    text: str,
    contact_name: str | None = None,
    source: str = "whatsapp",
) -> str:
    clean_text = text.strip()
    if not clean_text:
        return "Pode me enviar sua mensagem em texto para eu te direcionar melhor?"

    with _lock:
        if _is_reset_message(clean_text):
            _sessions.pop(phone_number, None)
            return _initial_menu()

        session = _sessions.setdefault(phone_number, ConversationSession())
        _append_history(session, "user", clean_text)

    if not session.profile:
        profile = classify_profile(clean_text)
        if profile == PROFILE_INDEFINIDO:
            reply = _initial_menu()
            with _lock:
                _append_history(session, "assistant", reply)
            return reply

        with _lock:
            session.profile = profile

    result = run_profile_agent(session.profile, session.history)

    if result.finalized:
        _save_summary_safely(
            phone_number=phone_number,
            contact_name=contact_name,
            profile=session.profile,
            summary=result.summary or _fallback_summary(session.profile, session.history),
            final_link=result.final_link,
            source=source,
            message_count=_count_user_messages(session.history),
        )

        reply = _ensure_final_link(result.reply, result.final_link)
        with _lock:
            _sessions.pop(phone_number, None)
        return reply

    with _lock:
        _append_history(session, "assistant", result.reply)
    return result.reply


def classify_profile(text: str) -> str:
    by_keyword = _classify_by_keyword(text)
    if by_keyword != PROFILE_INDEFINIDO:
        return by_keyword

    prompt = f"""
{system_prompt_lia}

Classifique a mensagem do usuario em apenas uma das opcoes:
- empresa
- profissional
- investidor
- parceria
- indefinido

Responda somente JSON valido neste formato:
{{"profile":"empresa"}}

Mensagem: {text}
"""

    try:
        content = _invoke_model(
            [
                SystemMessage(content=prompt),
                HumanMessage(content="Classifique a mensagem do usuario."),
            ]
        )
        data = _load_json_object(content)
        profile = str(data.get("profile", PROFILE_INDEFINIDO)).strip().lower()
        return profile if profile in VALID_PROFILES else PROFILE_INDEFINIDO
    except Exception:
        logger.exception("Falha ao classificar perfil com LLM.")
        return PROFILE_INDEFINIDO


def run_profile_agent(profile: str, history: list[dict[str, str]]) -> AgentResult:
    user_message_count = _count_user_messages(history)
    prompt = _build_profile_prompt(profile, history, user_message_count)

    try:
        content = _invoke_model(
            [
                SystemMessage(content=prompt),
                HumanMessage(content="Gere a resposta em JSON valido agora."),
            ]
        )
        data = _load_json_object(content)
        reply = str(data.get("reply") or "").strip()
        finalized = bool(data.get("finalized"))
        summary = data.get("summary")
        final_link = _normalize_final_link(profile, data.get("final_link"))

        if not reply:
            raise ValueError("Resposta do agente sem campo reply.")

        return AgentResult(
            reply=reply,
            finalized=finalized,
            summary=str(summary).strip() if summary else None,
            final_link=final_link,
        )
    except Exception:
        logger.exception("Falha ao executar subagente %s.", profile)
        return _fallback_profile_result(profile, history)


def _build_profile_prompt(
    profile: str,
    history: list[dict[str, str]],
    user_message_count: int,
) -> str:
    base_prompt = PROFILE_PROMPTS[profile]
    final_links = _final_links_text(profile)
    history_text = _format_history(history)
    should_finalize = user_message_count >= 2

    return f"""
{base_prompt}

Regras obrigatorias:
- Responda em portugues do Brasil.
- Seja breve, humano e objetivo.
- Faca no maximo uma pergunta por resposta.
- Nao invente precos, prazos, vagas, unidades ou promessas.
- Se ainda faltar informacao essencial, faca uma pergunta curta.
- Se ja tiver informacao suficiente, finalize o atendimento.
- Se o historico ja tiver 2 ou mais mensagens do usuario neste perfil, finalize mesmo com informacoes simples.
- Ao finalizar, gere um resumo final claro para salvar no banco.

Links permitidos:
{final_links}

Contexto tecnico:
- Mensagens do usuario neste perfil: {user_message_count}
- Deve finalizar agora: {"sim" if should_finalize else "nao, exceto se ja houver informacao suficiente"}

Historico temporario da conversa:
{history_text}

Responda SOMENTE JSON valido neste formato:
{{
  "reply": "mensagem que sera enviada ao usuario",
  "finalized": true,
  "summary": "resumo final do atendimento para o banco",
  "final_link": "link final ou null"
}}

Para parceria, final_link deve ser null e a mensagem nao deve conter link.
"""


def _final_links_text(profile: str) -> str:
    if profile == PROFILE_EMPRESA:
        return f"- Empresa: {LINK_EMPRESA}"
    if profile == PROFILE_PROFISSIONAL:
        return (
            f"- Vagas em destaque: {LINK_PROFISSIONAL_VAGAS}\n"
            f"- Vaga especifica: {LINK_PROFISSIONAL_VAGA}"
        )
    if profile == PROFILE_INVESTIDOR:
        return f"- Investidor/empreender: {LINK_INVESTIDOR}"
    return "- Parceria: sem link definido por enquanto."


def _normalize_final_link(profile: str, value) -> str | None:
    if profile == PROFILE_PARCERIA:
        return LINK_PARCERIA

    link = str(value or "").strip()
    if link in {"", "null", "None"}:
        return _default_link_for_profile(profile)

    allowed = {
        LINK_EMPRESA,
        LINK_PROFISSIONAL_VAGAS,
        LINK_PROFISSIONAL_VAGA,
        LINK_INVESTIDOR,
    }
    return link if link in allowed else _default_link_for_profile(profile)


def _default_link_for_profile(profile: str) -> str | None:
    if profile == PROFILE_EMPRESA:
        return LINK_EMPRESA
    if profile == PROFILE_PROFISSIONAL:
        return LINK_PROFISSIONAL_VAGAS
    if profile == PROFILE_INVESTIDOR:
        return LINK_INVESTIDOR
    return LINK_PARCERIA


def _ensure_final_link(reply: str, final_link: str | None) -> str:
    if not final_link or final_link in reply:
        return reply
    return f"{reply}\n\nLink: {final_link}"


def _save_summary_safely(
    *,
    phone_number: str,
    contact_name: str | None,
    profile: str,
    summary: str,
    final_link: str | None,
    source: str,
    message_count: int,
) -> None:
    if not is_database_configured():
        logger.warning("SUPABASE_DATABASE_URL nao configurada. Resumo final nao salvo.")
        return

    try:
        save_lead_summary(
            phone_number=phone_number,
            contact_name=contact_name,
            profile=profile,
            summary=summary,
            final_link=final_link,
            source=source,
            metadata_json={"message_count": message_count},
        )
    except Exception:
        logger.exception("Falha ao salvar resumo final no banco.")


def _fallback_profile_result(profile: str, history: list[dict[str, str]]) -> AgentResult:
    if _count_user_messages(history) < 2:
        return AgentResult(reply=_first_question(profile), finalized=False)

    summary = _fallback_summary(profile, history)
    final_link = _default_link_for_profile(profile)
    reply = _fallback_final_reply(profile, final_link)
    return AgentResult(
        reply=reply,
        finalized=True,
        summary=summary,
        final_link=final_link,
    )


def _first_question(profile: str) -> str:
    if profile == PROFILE_EMPRESA:
        return "Para te direcionar melhor: qual perfil de vaga voce precisa contratar e qual e a urgencia?"
    if profile == PROFILE_PROFISSIONAL:
        return "Voce quer encontrar oportunidades agora ou busca um apoio mais estrategico para sua carreira?"
    if profile == PROFILE_INVESTIDOR:
        return "Voce busca algo mais simples para comecar ou uma operacao mais estruturada na sua cidade?"
    return "Qual instituicao, associacao ou projeto voce representa e em qual regiao atua?"


def _fallback_final_reply(profile: str, final_link: str | None) -> str:
    if profile == PROFILE_PARCERIA:
        return "Perfeito. Registrei suas informacoes e vou encaminhar para um especialista de parcerias avaliar o melhor caminho."
    return f"Perfeito. Com base no que voce me contou, este e o melhor caminho para seguir: {final_link}"


def _fallback_summary(profile: str, history: list[dict[str, str]]) -> str:
    user_messages = [item["content"] for item in history if item["role"] == "user"]
    joined = " | ".join(user_messages[-4:])
    return f"Perfil identificado: {profile}. Informacoes coletadas: {joined}"


def _classify_by_keyword(text: str) -> str:
    normalized = _normalize_text(text)
    compact = normalized.strip()

    if compact in {"1", "oportunidade", "oportunidades", "profissional"}:
        return PROFILE_PROFISSIONAL
    if compact in {"2", "contratar", "empresa"}:
        return PROFILE_EMPRESA
    if compact in {"3", "empreender", "investidor"}:
        return PROFILE_INVESTIDOR
    if compact in {"4", "parceria", "parceiro", "instituicao", "instituicao"}:
        return PROFILE_PARCERIA

    empresa_terms = [
        "contratar",
        "minha empresa",
        "empresa",
        "recrutamento",
        "selecionar candidatos",
        "rh",
        "turnover",
        "colaborador",
        "funcionario",
        "funcionarios",
        "tenho uma vaga",
        "abrir vaga",
    ]
    profissional_terms = [
        "emprego",
        "oportunidade",
        "vagas",
        "vaga",
        "curriculo",
        "candidato",
        "candidatar",
        "trabalho",
        "carreira",
    ]
    investidor_terms = [
        "investir",
        "investidor",
        "empreender",
        "franquia",
        "licenciamento",
        "abrir operacao",
        "operacao estruturada",
    ]
    parceria_terms = [
        "parceria",
        "associacao",
        "instituicao",
        "governo",
        "prefeitura",
        "projeto social",
        "ong",
        "nicho",
    ]

    if _has_any(normalized, empresa_terms):
        return PROFILE_EMPRESA
    if _has_any(normalized, investidor_terms):
        return PROFILE_INVESTIDOR
    if _has_any(normalized, parceria_terms):
        return PROFILE_PARCERIA
    if _has_any(normalized, profissional_terms):
        return PROFILE_PROFISSIONAL
    return PROFILE_INDEFINIDO


def _has_any(text: str, terms: list[str]) -> bool:
    return any(term in text for term in terms)


def _normalize_text(text: str) -> str:
    replacements = {
        "á": "a",
        "à": "a",
        "ã": "a",
        "â": "a",
        "é": "e",
        "ê": "e",
        "í": "i",
        "ó": "o",
        "ô": "o",
        "õ": "o",
        "ú": "u",
        "ç": "c",
    }
    lowered = text.lower()
    for original, replacement in replacements.items():
        lowered = lowered.replace(original, replacement)
    return lowered


def _is_reset_message(text: str) -> bool:
    return _normalize_text(text).strip() in RESET_WORDS


def _initial_menu() -> str:
    return (
        "Ola, tudo bem? Sou a Lia da TalentBank. Vou te ajudar a encontrar o melhor caminho.\n\n"
        "Voce esta buscando:\n"
        "1. Oportunidades ou apoio de carreira\n"
        "2. Contratar profissionais\n"
        "3. Empreender/investir\n"
        "4. Parcerias institucionais"
    )


def _append_history(session: ConversationSession, role: str, content: str) -> None:
    session.history.append({"role": role, "content": content})
    max_messages = max(4, AGENT_MAX_HISTORY_MESSAGES)
    if len(session.history) > max_messages:
        session.history = session.history[-max_messages:]


def _format_history(history: list[dict[str, str]]) -> str:
    if not history:
        return "Sem historico anterior."
    return "\n".join(f"{item['role']}: {item['content']}" for item in history)


def _count_user_messages(history: list[dict[str, str]]) -> int:
    return sum(1 for item in history if item["role"] == "user")


def _invoke_model(messages) -> str:
    response = _get_model().invoke(messages)
    content = response.content

    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and "text" in item:
                parts.append(str(item["text"]))
        return "\n".join(parts)
    return str(content)


def _get_model():
    global _model
    if _model is None:
        _model = ChatGoogleGenerativeAI(model=MODEL, temperature=0.2)
    return _model


def _load_json_object(content: str) -> dict:
    cleaned = content.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise
        return json.loads(cleaned[start : end + 1])
