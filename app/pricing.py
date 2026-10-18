"""Delivery pricing. Pure Python (no framework imports) so it is trivially testable.

Rules
-----
* Chargeable weight = max(actual, volumetric) where volumetric = L x W x H / 5000,
  rounded up to the next 0.5 kg.
* Each zone has a base fee that covers the first 1 kg, plus a per-kg rate beyond that.
* The service level multiplies base + weight charges.
* Fragile handling is a flat fee; insurance is a percentage of declared value.
All money is Decimal taka (BDT), rounded half-up to 2 places.
"""
from dataclasses import dataclass
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")
INCLUDED_KG = Decimal("1")
VOLUMETRIC_DIVISOR = Decimal("5000")

MAX_WEIGHT_KG = Decimal("30")
MAX_DIMENSION_CM = 150
MAX_DECLARED_VALUE = Decimal("100000")

FRAGILE_FEE = Decimal("20.00")
INSURANCE_RATE = Decimal("0.015")
INSURANCE_MIN = Decimal("10.00")

ZONES = {
    "local": {"label": "Local", "description": "Within the same city", "base": Decimal("80.00"), "per_kg": Decimal("15.00")},
    "regional": {"label": "Regional", "description": "Between nearby cities", "base": Decimal("120.00"), "per_kg": Decimal("20.00")},
    "national": {"label": "National", "description": "Anywhere in the country", "base": Decimal("150.00"), "per_kg": Decimal("25.00")},
}

SERVICES = {
    "standard": {"label": "Standard", "description": "Best value", "multiplier": Decimal("1.0")},
    "express": {"label": "Express", "description": "Priority handling", "multiplier": Decimal("1.5")},
    "same_day": {"label": "Same day", "description": "Local zone only, booked before noon", "multiplier": Decimal("2.2")},
}

# (zone, service) -> (min_days, max_days)
ETA_DAYS = {
    ("local", "standard"): (1, 2), ("local", "express"): (1, 1), ("local", "same_day"): (0, 0),
    ("regional", "standard"): (2, 4), ("regional", "express"): (1, 2),
    ("national", "standard"): (3, 6), ("national", "express"): (2, 3),
}


class PricingError(ValueError):
    """Raised when inputs cannot be priced."""


@dataclass(frozen=True)
class PriceLine:
    code: str
    label: str
    amount: Decimal


@dataclass(frozen=True)
class Quote:
    chargeable_weight_kg: Decimal
    lines: list[PriceLine]
    total: Decimal
    eta_min_days: int
    eta_max_days: int


def _money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def chargeable_weight(weight_kg: Decimal, length_cm=None, width_cm=None, height_cm=None) -> Decimal:
    weight = Decimal(weight_kg)
    dims = (length_cm, width_cm, height_cm)
    if any(d is not None for d in dims):
        if any(d is None for d in dims):
            raise PricingError("Provide all three dimensions or none.")
        volumetric = Decimal(length_cm) * Decimal(width_cm) * Decimal(height_cm) / VOLUMETRIC_DIVISOR
        weight = max(weight, volumetric)
    return (weight * 2).to_integral_value(rounding=ROUND_CEILING) / 2


def calculate_quote(
    zone: str,
    service: str,
    weight_kg,
    length_cm=None,
    width_cm=None,
    height_cm=None,
    declared_value=Decimal("0"),
    fragile: bool = False,
) -> Quote:
    if zone not in ZONES:
        raise PricingError(f"Unknown zone: {zone}")
    if service not in SERVICES:
        raise PricingError(f"Unknown service: {service}")
    if service == "same_day" and zone != "local":
        raise PricingError("Same-day delivery is only available in the local zone.")

    weight = Decimal(weight_kg)
    declared = Decimal(declared_value)
    if weight <= 0 or weight > MAX_WEIGHT_KG:
        raise PricingError(f"Weight must be greater than 0 and at most {MAX_WEIGHT_KG} kg.")
    if declared < 0 or declared > MAX_DECLARED_VALUE:
        raise PricingError(f"Declared value must be between 0 and {MAX_DECLARED_VALUE}.")

    cw = chargeable_weight(weight, length_cm, width_cm, height_cm)
    if cw > MAX_WEIGHT_KG:
        raise PricingError(f"Chargeable weight ({cw} kg) exceeds the {MAX_WEIGHT_KG} kg limit.")

    z, s = ZONES[zone], SERVICES[service]
    mult = s["multiplier"]
    lines = [PriceLine("base", f"{z['label']} delivery, {s['label'].lower()} (first {INCLUDED_KG} kg)", _money(z["base"] * mult))]

    extra_kg = max(Decimal("0"), cw - INCLUDED_KG)
    if extra_kg > 0:
        lines.append(PriceLine("weight", f"Extra weight ({extra_kg} kg)", _money(extra_kg * z["per_kg"] * mult)))
    if fragile:
        lines.append(PriceLine("fragile", "Fragile handling", FRAGILE_FEE))
    if declared > 0:
        lines.append(PriceLine("insurance", "Insurance", max(INSURANCE_MIN, _money(declared * INSURANCE_RATE))))

    eta_min, eta_max = ETA_DAYS[(zone, service)]
    return Quote(cw, lines, sum((l.amount for l in lines), Decimal("0.00")), eta_min, eta_max)
