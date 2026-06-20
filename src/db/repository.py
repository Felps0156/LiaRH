from src.db.models import LeadSummary
from src.db.session import get_session


def save_lead_summary(
    *,
    phone_number: str,
    contact_name: str | None,
    profile: str,
    summary: str,
    final_link: str | None,
    source: str = "whatsapp",
    metadata_json: dict | None = None,
) -> LeadSummary:
    with get_session() as db:
        lead = LeadSummary(
            phone_number=phone_number,
            contact_name=contact_name,
            profile=profile,
            summary=summary,
            final_link=final_link or None,
            source=source,
            metadata_json=metadata_json,
        )
        db.add(lead)
        db.commit()
        db.refresh(lead)
        return lead
