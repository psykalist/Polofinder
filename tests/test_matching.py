"""Tests for the bits that would quietly cost money if they were wrong:
write-off detection, trim/year gating, and tiering."""
import os
import sys

import pytest
import yaml

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from polofinder.matching import (  # noqa: E402
    classify, writeoff_check, infer_trim, infer_power_ps, infer_seller_type,
    TIER_EXACT, TIER_STRETCH, TIER_LOOK,
)
from polofinder.models import Listing, parse_price, parse_mileage, extract_plate  # noqa: E402


@pytest.fixture(scope="module")
def cfg():
    with open(os.path.join(os.path.dirname(__file__), "..", "config.yaml")) as f:
        return yaml.safe_load(f)


def mk(**kw):
    base = dict(source="test", url="http://x", title="VW Polo 1.0 TSI Match",
                price=11500, mileage=22000, year=2022, make="Volkswagen",
                model="Polo")
    base.update(kw)
    return Listing(**base)


# --- write-off detection ---------------------------------------------------

@pytest.mark.parametrize("text", [
    "VW Polo Cat S repaired", "Polo category C damaged", "cat-n recorded",
    "Polo 1.0 TSI insurance write off", "salvage vehicle", "Cat D light damage",
])
def test_writeoff_detected(text, cfg):
    l = mk(title=text)
    assert writeoff_check(l, cfg["exclusions"]["write_off_categories"])


@pytest.mark.parametrize("text", [
    "VW Polo Match, HPI clear, not a cat S",
    "Unrecorded, no accident history",
    "Never been in an accident, clear HPI",
    "Polo Match 1.0 TSI, non cat S or C",
])
def test_clean_cars_not_flagged(text, cfg):
    """The classic false positive: sellers advertising that it's NOT a write-off."""
    l = mk(title=text)
    assert writeoff_check(l, cfg["exclusions"]["write_off_categories"]) is None


def test_writeoff_rejected_end_to_end(cfg):
    l = classify(mk(title="VW Polo 1.0 TSI 95PS Match Cat S"), cfg)
    assert l.tier is None
    assert "Cat S" in l.reject_reason


# --- trim + year gating ----------------------------------------------------

@pytest.mark.parametrize("title,expected", [
    ("Polo 1.0 TSI R-Line", "r-line"),
    ("Polo 1.0 TSI Match 95", "match"),
    ("Polo Style 1.0 TSI", "style"),
    ("Polo 1.0 TSI Life", "life"),
    ("Polo 1.0 TSI SEL", "sel"),
])
def test_trim_parsing(title, expected):
    assert infer_trim(mk(title=title)) == expected


def test_life_trim_below_match_rejected(cfg):
    """Post-2021 Life sits below Match, so it must not reach EXACT."""
    l = classify(mk(title="VW Polo 1.0 TSI 95PS Life", year=2022), cfg)
    assert l.tier != TIER_EXACT


def test_pre_2021_rejected_from_exact(cfg):
    l = classify(mk(title="VW Polo 1.0 TSI 95PS Match", year=2019), cfg)
    assert l.tier != TIER_EXACT


def test_perfect_car_is_exact(cfg):
    l = classify(mk(
        title="2022 VW Polo 1.0 TSI 95PS Match",
        description="Rear camera, parking sensors, Apple CarPlay, sat nav, climate control",
        price=11995, mileage=18500, year=2022), cfg)
    assert l.tier == TIER_EXACT
    assert "Rear Camera" in l.extras_found
    assert l.score > 20


# --- tiering ---------------------------------------------------------------

def test_over_budget_goes_to_stretch(cfg):
    l = classify(mk(title="2022 VW Polo 1.0 TSI 95PS Match", price=13400), cfg)
    assert l.tier == TIER_STRETCH


def test_high_mileage_goes_to_stretch(cfg):
    l = classify(mk(title="2022 VW Polo 1.0 TSI 95PS Style", mileage=33000), cfg)
    assert l.tier == TIER_STRETCH


def test_110ps_polo_is_worth_a_look(cfg):
    l = classify(mk(title="2022 VW Polo 1.0 TSI 110PS R-Line"), cfg)
    assert l.tier == TIER_LOOK


def test_sibling_car_is_worth_a_look(cfg):
    l = classify(mk(title="2022 SEAT Ibiza 1.0 TSI FR", make="SEAT", model="Ibiza"), cfg)
    assert l.tier == TIER_LOOK


def test_way_over_budget_rejected(cfg):
    l = classify(mk(price=19000), cfg)
    assert l.tier is None


def test_non_turbo_mpi_not_exact(cfg):
    l = classify(mk(title="2022 VW Polo 1.0 MPI 80PS Match"), cfg)
    assert l.tier != TIER_EXACT


# --- seller type -----------------------------------------------------------

def test_private_seller_detected():
    assert infer_seller_type(mk(description="Private sale, selling my car")) == "Private"


def test_dealer_detected():
    assert infer_seller_type(mk(seller="Bristol Car Sales Ltd")) == "Dealer"


def test_dealer_site_implies_trade():
    assert infer_seller_type(mk(source="arnoldclark")) == "Dealer"


# --- parsers ---------------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    ("£12,495", 12495), ("12495", 12495), (12495, 12495), ("POA", None),
])
def test_parse_price(raw, expected):
    assert parse_price(raw) == expected


@pytest.mark.parametrize("raw,expected", [
    ("28,450 miles", 28450), ("28k miles", 28000), (28450, 28450),
])
def test_parse_mileage(raw, expected):
    assert parse_mileage(raw) == expected


def test_power_snapping():
    assert infer_power_ps(mk(title="Polo 1.0 TSI 94bhp")) == 95


def test_plate_extraction():
    assert extract_plate("vw polo gl21 xyz match") == "GL21XYZ"


def test_dedupe_by_plate():
    a, b = mk(title="Polo AB21 CDE", url="http://a"), mk(title="polo ab21cde", url="http://b")
    assert a.fingerprint == b.fingerprint


# --- power parsing without a PS suffix -------------------------------------

@pytest.mark.parametrize("title", [
    "VW Polo Match 1.0 TSI 95 2021",
    "Polo 1.0 TSI 95PS Match",
    "Polo 1.0 TSI 94bhp Match",
])
def test_power_found_with_or_without_suffix(title):
    assert infer_power_ps(mk(title=title)) == 95


def test_bare_tsi_95_reaches_exact(cfg):
    """Real-world title style: '1.0 TSI 95' with no PS suffix."""
    l = classify(mk(title="VW Polo Match 1.0 TSI 95 2021", price=12250,
                    mileage=26800, year=2021), cfg)
    assert l.tier == TIER_EXACT


def test_bare_number_not_mistaken_for_power(cfg):
    """'TSI 150' isn't a Polo output we care about, shouldn't snap to 95."""
    assert infer_power_ps(mk(title="Polo 1.0 TSI 150")) != 95
