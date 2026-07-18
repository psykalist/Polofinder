"""Tests for the bits that would quietly cost money if they were wrong:
write-off detection, trim/year gating, and tiering."""
import os
import sys

import pytest
import yaml

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from polofinder.matching import (  # noqa: E402
    classify, is_turbo, writeoff_check, infer_trim, infer_power_ps, infer_seller_type,
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
    """Derived from config so changing the budget doesn't break the test."""
    over = cfg["budget"]["max_price"] + 500
    assert over <= cfg["budget"]["stretch_price"], "test price must sit inside stretch"
    l = classify(mk(title="2022 VW Polo 1.0 TSI 95PS Match", price=over), cfg)
    assert l.tier == TIER_STRETCH


def test_at_budget_ceiling_is_exact(cfg):
    l = classify(mk(title="2022 VW Polo 1.0 TSI 95PS Match",
                    price=cfg["budget"]["max_price"]), cfg)
    assert l.tier == TIER_EXACT


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
    l = classify(mk(price=cfg["budget"]["stretch_price"] + 5000), cfg)
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


# --- unknown power: the advert just doesn't say ----------------------------

def test_unstated_power_still_reaches_exact(cfg):
    """Most real adverts say '1.0 TSI Match' with no PS anywhere.
    Those must not be silently demoted."""
    l = classify(mk(title="2022 VW Polo 1.0 TSI Match 5dr",
                    description="One owner, full service history, rear camera"), cfg)
    assert l.tier == TIER_EXACT
    assert l.power_unconfirmed is True
    assert any("Power not stated" in n for n in l.notes)


def test_stated_110ps_never_treated_as_unknown(cfg):
    l = classify(mk(title="2022 VW Polo 1.0 TSI 110 Match"), cfg)
    assert l.power_unconfirmed is False
    assert l.tier != TIER_EXACT


def test_power_from_spec_table():
    assert infer_power_ps(mk(title="VW Polo Match",
                             raw_spec="Engine power: 95 PS  Transmission: Manual")) == 95


def test_litres_from_cc():
    from polofinder.matching import infer_litres
    assert infer_litres(mk(title="VW Polo Match", raw_spec="999 cc petrol")) == 1.0


def test_demote_policy(cfg):
    import copy
    c2 = copy.deepcopy(cfg)
    c2["target"]["power_unknown_policy"] = "demote"
    l = classify(mk(title="2022 VW Polo 1.0 TSI Match 5dr"), c2)
    assert l.tier == TIER_STRETCH


def test_exclude_policy(cfg):
    import copy
    c2 = copy.deepcopy(cfg)
    c2["target"]["power_unknown_policy"] = "exclude"
    l = classify(mk(title="2022 VW Polo 1.0 TSI Match 5dr"), c2)
    assert l.tier != TIER_EXACT


# --- mileage parsing: real strings captured from a live Gumtree run --------
# Gumtree renders attributes with no separator, so the year runs into the
# mileage. Reading 20,174,560 miles instead of 4,560 made every car fail spec.

@pytest.mark.parametrize("raw,year,expected", [
    ("20174,560 milesPrivatePetrol1,197 cc",  2017, 4560),
    ("201197,000 milesTradePetrol1,198 cc",   2011, 97000),
    ("2017130,000 milesPrivatePetrol999 cc",  2017, 130000),
    ("200747,000 milesTradePetrol1,390 cc",   2007, 47000),
    ("201784,414 milesTradePetrol1,197 cc",   2017, 84414),
])
def test_mileage_with_year_glued_on(raw, year, expected):
    assert parse_mileage(raw, year=year) == expected


@pytest.mark.parametrize("raw,expected", [
    ("2017 | 4,560 miles | Private | Petrol | 1,197 cc", 4560),
    ("2011 | 197,000 miles | Trade | Petrol", 197000),
    ("28,450 miles", 28450),
    ("28k miles", 28000),
    ("miles", None),
])
def test_mileage_from_separated_attributes(raw, expected):
    assert parse_mileage(raw) == expected


def test_implausible_mileage_rejected():
    """Better to return None than a confidently wrong number."""
    # Raw numeric input has no year context to strip, so it must be rejected.
    assert parse_mileage(20174560) is None
    assert parse_mileage("999,999,999 miles") is None
    assert parse_mileage(0) is None


def test_glued_year_stripped_without_commas():
    """'20174560 miles' is a 2017 car with 4,560 miles, not 20 million."""
    assert parse_mileage("20174560 miles") == 4560


def test_mileage_no_word_boundary_after_miles():
    """'milesPrivate' has no word boundary - the original regex missed it."""
    assert parse_mileage("4,560 milesPrivatePetrol") == 4560


def test_old_high_mileage_car_still_rejected(cfg):
    """A 2007 1.4 SE with 47k must not sneak in once mileage parses correctly."""
    l = classify(mk(title="VOLKSWAGEN POLO SE 1.4L (2007) low 47,000 miles",
                    price=2350, mileage=47000, year=2007), cfg)
    assert l.tier is None


# --- unnamed trim: Gumtree's structured titles carry no trim ---------------

def test_gumtree_structured_title_reaches_exact(cfg):
    """Real listing that was wrongly buried in WORTH A LOOK:
    'MINT CONDITION - Volkswagen POLO, Hatchback, 2022, Manual, 999 (cc), 5 doors'
    2022, 19k miles, GBP13,750 - no trim or PS named anywhere."""
    l = classify(mk(
        title="MINT CONDITION - Volkswagen POLO, Hatchback, 2022, Manual, 999 (cc), 5 doors",
        price=13750, mileage=19000, year=2022,
        raw_spec="2022 | 19,000 miles | Private | Petrol | 999 cc"), cfg)
    assert l.tier == TIER_EXACT
    assert l.trim_unconfirmed is True
    assert l.power_unconfirmed is True
    assert l.seller_type == "Private"


def test_named_low_trim_still_rejected(cfg):
    """Unknown trim is forgiven; an explicitly low trim is not."""
    l = classify(mk(title="2022 VW Polo 1.0 TSI 95PS Life", year=2022), cfg)
    assert l.trim_unconfirmed is False
    assert l.tier != TIER_EXACT


def test_trim_exclude_policy(cfg):
    import copy
    c2 = copy.deepcopy(cfg)
    c2["target"]["trim_unknown_policy"] = "exclude"
    l = classify(mk(title="Volkswagen, POLO, Hatchback, 2022, Manual, 999 (cc), 5 doors",
                    price=13750, mileage=19000, year=2022), c2)
    assert l.tier != TIER_EXACT


# --- WORTH A LOOK must not fill with old cars ------------------------------

def test_old_gti_not_in_worth_a_look(cfg):
    """A 2012 GTI at 35k miles was cluttering the near-miss bucket."""
    l = classify(mk(title="2012 Volkswagen Polo 1.4 TSI GTI DSG EURO 5 5dr Petrol",
                    price=8500, mileage=35000, year=2012), cfg)
    assert l.tier is None


def test_recent_110ps_still_in_worth_a_look(cfg):
    l = classify(mk(title="2022 VW Polo 1.0 TSI 110PS R-Line", year=2022), cfg)
    assert l.tier == TIER_LOOK


def test_seller_type_from_attribute_strip():
    """Gumtree puts Private/Trade in the attributes, not the description."""
    assert infer_seller_type(mk(
        raw_spec="2022 | 19,000 miles | Private | Petrol | 999 cc")) == "Private"
    assert infer_seller_type(mk(
        raw_spec="2021 | 34,039 miles | Trade | Petrol | 999 cc")) == "Dealer"


# --- the EVO trap ----------------------------------------------------------
# AutoTrader lists "1.0 EVO Match" (80PS naturally aspirated) right alongside
# "1.0 TSI Match" (95PS turbo), a few hundred pounds cheaper. Real listings
# seen 2026-07-18 within budget and mileage - these must NOT be exact matches.

@pytest.mark.parametrize("title,price,miles", [
    ("Volkswagen Polo 1.0 EVO Match Euro 6 (s/s) 5dr", 12595, 29729),
    ("Volkswagen Polo 1.0 EVO Match Euro 6 (s/s) 5dr", 12800, 29560),
    ("Volkswagen Polo 1.0 EVO Match Euro 6 (s/s) 5dr", 12995, 19200),
    ("Volkswagen Polo 1.0 EVO Match Euro 6 (s/s) 5dr", 13150, 22291),
])
def test_evo_is_not_a_tsi_match(cfg, title, price, miles):
    l = classify(mk(title=title, price=price, mileage=miles, year=2021), cfg)
    assert l.tier != TIER_EXACT, f"{title} at GBP{price} wrongly accepted as 95PS TSI"
    assert any("EVO" in n for n in l.notes)


@pytest.mark.parametrize("title,price,miles", [
    ("Volkswagen Polo 1.0 TSI Match Euro 6 (s/s) 5dr", 11995, 28574),
    ("Volkswagen Polo 1.0 TSI Match Euro 6 (s/s) 5dr", 12950, 26455),
    ("Volkswagen Polo 1.0 TSI Match Euro 6 (s/s) 5dr", 13199, 23682),
])
def test_real_tsi_match_cars_are_exact(cfg, title, price, miles):
    """The three genuine 95PS TSI Match cars found on AutoTrader."""
    l = classify(mk(title=title, price=price, mileage=miles, year=2021), cfg)
    assert l.tier == TIER_EXACT


def test_tsi_beats_evo_when_both_present():
    assert is_turbo(mk(title="Polo 1.0 TSI EVO Match")) is True
