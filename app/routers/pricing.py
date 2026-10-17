from fastapi import APIRouter, HTTPException, status

from app import pricing
from app.config import get_settings
from app.schemas import QuoteOut, QuoteRequest

router = APIRouter(prefix="/pricing", tags=["pricing"])


@router.get("/options")
def options():
    return {
        "currency": get_settings().currency,
        "zones": [{"id": k, "label": v["label"], "description": v["description"]} for k, v in pricing.ZONES.items()],
        "services": [{"id": k, "label": v["label"], "description": v["description"]} for k, v in pricing.SERVICES.items()],
        "limits": {
            "max_weight_kg": str(pricing.MAX_WEIGHT_KG),
            "max_dimension_cm": pricing.MAX_DIMENSION_CM,
            "max_declared_value": str(pricing.MAX_DECLARED_VALUE),
        },
    }


def quote_for(payload: QuoteRequest) -> pricing.Quote:
    try:
        return pricing.calculate_quote(
            payload.zone, payload.service, payload.weight_kg, payload.length_cm, payload.width_cm,
            payload.height_cm, payload.declared_value, payload.fragile,
        )
    except pricing.PricingError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))


@router.post("/quote", response_model=QuoteOut)
def quote(payload: QuoteRequest):
    q = quote_for(payload)
    return QuoteOut(
        currency=get_settings().currency, chargeable_weight_kg=q.chargeable_weight_kg,
        lines=[{"code": l.code, "label": l.label, "amount": l.amount} for l in q.lines],
        total=q.total, eta_min_days=q.eta_min_days, eta_max_days=q.eta_max_days,
    )
