"""Renders a sample report with representative listings so you can see the
email format before any live data exists."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import yaml
from polofinder import dedupe, report
from polofinder.matching import classify
from polofinder.robots import RobotsCache
from polofinder.models import Listing
from polofinder.sources import ALL_SOURCES
from polofinder.sources.base import SourceResult

cfg = yaml.safe_load(open(os.path.join(os.path.dirname(__file__), "..", "config.yaml")))

SAMPLES = [
    Listing(source="ebay", url="https://www.ebay.co.uk/itm/1", make="Volkswagen", model="Polo",
            title="2022 VW Polo 1.0 TSI 95PS Match 5dr", price=11995, mileage=18400, year=2022,
            location="Gloucester", seller="Cotswold Motor Company Ltd",
            description="Rear camera, front and rear parking sensors, Apple CarPlay, sat nav, "
                        "climate control, adaptive cruise, LED headlights, alloy wheels, DAB. HPI clear."),
    Listing(source="gumtree", url="https://www.gumtree.com/p/2", make="Volkswagen", model="Polo",
            title="VW Polo Match 1.0 TSI 95 2021 AB21 XYZ", price=12250, mileage=26800, year=2021,
            location="Bristol", description="Private sale, selling my car. Reversing camera, "
            "heated seats, climate control, keyless, alloys. Not a cat S or C, unrecorded."),
    Listing(source="ebay", url="https://www.ebay.co.uk/itm/3", make="Volkswagen", model="Polo",
            title="2022 VW Polo 1.0 TSI 95PS Style", price=13400, mileage=21000, year=2022,
            location="Birmingham", seller="Midlands Car Sales Ltd",
            description="Rear camera, digital cockpit, sat nav, CarPlay, blind spot, LED"),
    Listing(source="pistonheads", url="https://www.pistonheads.com/4", make="Volkswagen", model="Polo",
            title="2023 VW Polo 1.0 TSI 95PS R-Line", price=12400, mileage=33500, year=2023,
            location="Cardiff", seller="PH Trade", description="Panoramic roof, camera, nav, ACC"),
    Listing(source="ebay", url="https://www.ebay.co.uk/itm/5", make="Volkswagen", model="Polo",
            title="2022 VW Polo 1.0 TSI 110PS R-Line DSG", price=13750, mileage=24000, year=2022,
            location="Oxford", seller="Oxford Motors Ltd",
            description="Rear camera, digital cockpit, adaptive cruise, CarPlay, keyless, LED"),
    Listing(source="gumtree", url="https://www.gumtree.com/p/6", make="SEAT", model="Ibiza",
            title="2022 SEAT Ibiza 1.0 TSI FR 95PS", price=11200, mileage=19500, year=2022,
            location="Swindon", description="Private seller. Rear camera, sensors, CarPlay, nav"),
    # should be filtered out
    Listing(source="ebay", url="https://www.ebay.co.uk/itm/7", make="Volkswagen", model="Polo",
            title="2022 VW Polo 1.0 TSI 95PS Match CAT S", price=8995, mileage=15000, year=2022,
            location="Leeds", description="Cat S recorded, repaired, drives well"),
    Listing(source="ebay", url="https://www.ebay.co.uk/itm/8", make="Volkswagen", model="Polo",
            title="2019 VW Polo 1.0 TSI 95PS Match", price=9995, mileage=28000, year=2019,
            location="Manchester", description="Pre-facelift, sensors, DAB"),
    Listing(source="ebay", url="https://www.ebay.co.uk/itm/9", make="Volkswagen", model="Polo",
            title="2022 VW Polo 1.0 TSI 95PS Life", price=11500, mileage=20000, year=2022,
            location="Reading", description="Life trim, air con, DAB"),
]

for l in SAMPLES:
    classify(l, cfg)

matched = [l for l in SAMPLES if l.tier]
rejected = [l for l in SAMPLES if l.reject_reason]
matched = dedupe.cross_site_dupes(matched)
for l in matched:
    l.is_new = True

print("=== CLASSIFICATION ===")
for l in SAMPLES:
    print(f"  {(l.tier or 'REJECTED'):16} score={l.score:3}  {l.seller_type:8} "
          f"{l.title[:46]:48} {l.reject_reason or ''}")

robots = RobotsCache(cfg["sources"]["user_agent"], True)
results = []
for cls in ALL_SOURCES:
    src = cls(cfg, robots, None)
    try:
        url = src.search_url()
    except Exception:
        url = None
    if cls.deeplink_only:
        results.append(SourceResult(cls.key, cls.name, cls.homepage, "DEEPLINK_ONLY",
                                    search_url=url, detail=cls.robots_note))
    else:
        got = [l for l in matched if l.source == cls.key]
        results.append(SourceResult(cls.key, cls.name, cls.homepage, "OK",
                                    listings=got, search_url=url,
                                    detail="sample data" if got else "no listings"))

os.makedirs("reports", exist_ok=True)
open("reports/sample-report.html", "w").write(report.build_html(matched, results, cfg, rejected))
open("reports/sample-report.md", "w").write(report.build_markdown(matched, results, cfg))
print("\n=== DEEP LINKS GENERATED ===")
for r in results:
    if r.status == "DEEPLINK_ONLY":
        print(f"  {r.name:22} {(r.search_url or '')[:95]}")
print("\nWrote reports/sample-report.html")
