from decimal import Decimal

import pytest

from app.pricing import PricingError, calculate_quote, chargeable_weight


def test_base_price_for_one_kg():
    q = calculate_quote("local", "standard", "1")
    assert q.total == Decimal("80.00")
    assert [l.code for l in q.lines] == ["base"]


def test_extra_weight_is_rounded_up_to_half_kg():
    # 2.1 kg -> 2.5 kg chargeable -> 1.5 kg extra x 20/kg regional
    q = calculate_quote("regional", "standard", "2.1")
    assert q.chargeable_weight_kg == Decimal("2.5")
    assert q.total == Decimal("120.00") + Decimal("30.00")


def test_volumetric_weight_wins_when_larger():
    # 50x40x30 = 60000 / 5000 = 12 kg
    assert chargeable_weight(Decimal("1"), 50, 40, 30) == Decimal("12.0")


def test_express_multiplier_and_extras():
    q = calculate_quote("national", "express", "1", declared_value="200", fragile=True)
    # base 150 * 1.5 = 225.00, fragile 20.00, insurance 1.5% of 200 = 3.00 -> raised to the 10.00 minimum
    assert q.total == Decimal("255.00")
    assert {l.code for l in q.lines} == {"base", "fragile", "insurance"}


def test_insurance_has_minimum():
    q = calculate_quote("local", "standard", "1", declared_value="100")
    assert [l for l in q.lines if l.code == "insurance"][0].amount == Decimal("10.00")


def test_same_day_only_local():
    assert calculate_quote("local", "same_day", "1").total == Decimal("176.00")
    with pytest.raises(PricingError):
        calculate_quote("regional", "same_day", "1")


@pytest.mark.parametrize("weight", ["0", "-1", "30.01"])
def test_weight_limits(weight):
    with pytest.raises(PricingError):
        calculate_quote("local", "standard", weight)


def test_partial_dimensions_rejected():
    with pytest.raises(PricingError):
        calculate_quote("local", "standard", "1", length_cm=10)


def test_total_equals_sum_of_lines():
    q = calculate_quote("regional", "express", "7.3", 30, 30, 30, "333.33", True)
    assert q.total == sum(l.amount for l in q.lines)
