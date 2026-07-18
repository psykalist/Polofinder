"""Builds the daily HTML email. Inline CSS only - Gmail strips <style> blocks."""
from __future__ import annotations

import html
from datetime import datetime

from .matching import TIER_EXACT, TIER_STRETCH, TIER_LOOK, TIER_ORDER, sort_key

TIER_META = {
    TIER_EXACT:   ("#1a7f37", "Your exact spec, in budget, under 30k miles."),
    TIER_STRETCH: ("#bf8700", "Right car, slightly over on price or mileage."),
    TIER_LOOK:    ("#0969da", "Not a 95PS Polo, but close enough to consider."),
}

STATUS_META = {
    "OK":             ("#1a7f37", "Scraped"),
    "DEEPLINK_ONLY":  ("#8250df", "Deep link"),
    "BLOCKED_ROBOTS": ("#bf8700", "Robots-blocked"),
    "ERROR":          ("#cf222e", "Error"),
    "DISABLED":       ("#6e7781", "Off"),
}


def _esc(s):
    return html.escape(str(s)) if s is not None else ""


def _money(n):
    return f"£{n:,}" if n else "POA"


def _seller_badge(listing):
    st = listing.seller_type or "Unknown"
    colour = {"Private": "#0969da", "Dealer": "#6e7781"}.get(st, "#8c959f")
    label = {"Private": "PRIVATE SELLER", "Dealer": "TRADE / DEALER"}.get(st, "SELLER UNKNOWN")
    return (f'<span style="background:{colour};color:#fff;font-size:10px;font-weight:700;'
            f'padding:2px 7px;border-radius:3px;letter-spacing:.4px;">{label}</span>')


def _card(listing):
    badges = [_seller_badge(listing)]
    if listing.is_new:
        badges.append('<span style="background:#1a7f37;color:#fff;font-size:10px;'
                      'font-weight:700;padding:2px 7px;border-radius:3px;">NEW TODAY</span>')
    if listing.price_drop:
        badges.append(f'<span style="background:#cf222e;color:#fff;font-size:10px;'
                      f'font-weight:700;padding:2px 7px;border-radius:3px;">'
                      f'-£{listing.price_drop:,}</span>')

    facts = []
    if listing.mileage:
        facts.append(f"{listing.mileage:,} miles")
    if listing.year:
        facts.append(str(listing.year))
    if listing.trim:
        facts.append(listing.trim.title())
    if listing.power_ps:
        facts.append(f"{listing.power_ps}PS")
    if listing.distance_miles is not None:
        facts.append(f"~{listing.distance_miles} mi away")
    if listing.location:
        facts.append(_esc(listing.location))

    extras = ""
    if listing.extras_found:
        chips = "".join(
            f'<span style="display:inline-block;background:#eef3f8;color:#24292f;'
            f'font-size:11px;padding:2px 8px;border-radius:10px;margin:2px 3px 0 0;">'
            f'{_esc(e)}</span>'
            for e in listing.extras_found
        )
        extras = f'<div style="margin-top:8px;">{chips}</div>'

    notes = ""
    if listing.notes:
        notes = ('<div style="margin-top:6px;font-size:12px;color:#8250df;">'
                 + " &middot; ".join(_esc(n) for n in listing.notes if n) + "</div>")

    also = ""
    if getattr(listing, "also_on", None):
        links = ", ".join(f'<a href="{_esc(u)}" style="color:#57606a;">{_esc(s)}</a>'
                          for s, u in listing.also_on)
        also = (f'<div style="margin-top:6px;font-size:11px;color:#57606a;">'
                f'Also listed on: {links}</div>')

    img = ""
    if listing.image:
        img = (f'<img src="{_esc(listing.image)}" width="150" '
               f'style="border-radius:6px;object-fit:cover;" alt="">')

    return f"""
    <table width="100%" cellpadding="0" cellspacing="0" style="border:1px solid #d0d7de;
           border-radius:8px;margin-bottom:12px;background:#fff;">
      <tr>
        <td width="160" valign="top" style="padding:14px 0 14px 14px;">{img}</td>
        <td valign="top" style="padding:14px;">
          <div style="margin-bottom:6px;">{" ".join(badges)}</div>
          <a href="{_esc(listing.url)}" style="font-size:16px;font-weight:600;
             color:#0969da;text-decoration:none;">{_esc(listing.title)}</a>
          <div style="font-size:22px;font-weight:700;color:#24292f;margin:6px 0 4px;">
            {_money(listing.price)}
          </div>
          <div style="font-size:13px;color:#57606a;">{" &middot; ".join(facts)}</div>
          {extras}{notes}{also}
          <div style="margin-top:10px;font-size:11px;color:#8c959f;
               text-transform:uppercase;letter-spacing:.5px;">
            {_esc(listing.source)} &middot; fit score {listing.score}
          </div>
        </td>
      </tr>
    </table>"""


def _sources_table(results):
    rows = []
    for r in sorted(results, key=lambda x: (x.status != "OK", x.name)):
        colour, label = STATUS_META.get(r.status, ("#6e7781", r.status))
        link = (f'<a href="{_esc(r.search_url)}" style="color:#0969da;">open search &rarr;</a>'
                if r.search_url else "")
        detail = _esc(r.detail)[:150]
        rows.append(f"""
        <tr>
          <td style="padding:7px 10px;border-bottom:1px solid #eaeef2;font-size:13px;">
            <a href="{_esc(r.homepage)}" style="color:#24292f;text-decoration:none;
               font-weight:600;">{_esc(r.name)}</a></td>
          <td style="padding:7px 10px;border-bottom:1px solid #eaeef2;">
            <span style="color:{colour};font-size:11px;font-weight:700;">{label}</span></td>
          <td style="padding:7px 10px;border-bottom:1px solid #eaeef2;font-size:13px;
              text-align:center;">{r.count or "&ndash;"}</td>
          <td style="padding:7px 10px;border-bottom:1px solid #eaeef2;font-size:11px;
              color:#57606a;">{detail}</td>
          <td style="padding:7px 10px;border-bottom:1px solid #eaeef2;font-size:12px;">{link}</td>
        </tr>""")
    return f"""
    <h2 style="font-size:15px;color:#24292f;margin:26px 0 10px;">
      Every site checked ({len(results)})</h2>
    <table width="100%" cellpadding="0" cellspacing="0"
           style="border:1px solid #d0d7de;border-radius:8px;background:#fff;">
      <tr style="background:#f6f8fa;">
        <th align="left" style="padding:8px 10px;font-size:11px;color:#57606a;">SITE</th>
        <th align="left" style="padding:8px 10px;font-size:11px;color:#57606a;">STATUS</th>
        <th style="padding:8px 10px;font-size:11px;color:#57606a;">HITS</th>
        <th align="left" style="padding:8px 10px;font-size:11px;color:#57606a;">NOTE</th>
        <th align="left" style="padding:8px 10px;font-size:11px;color:#57606a;">LINK</th>
      </tr>
      {"".join(rows)}
    </table>"""


def build_html(listings, results, cfg, rejected=None) -> str:
    matched = sorted([l for l in listings if l.tier], key=sort_key)
    counts = {t: len([l for l in matched if l.tier == t]) for t in TIER_ORDER}
    limit = cfg["report"].get("max_per_tier", 25)
    new_count = len([l for l in matched if l.is_new])

    sections = []
    for tier in TIER_ORDER:
        group = [l for l in matched if l.tier == tier][:limit]
        colour, blurb = TIER_META[tier]
        if not group:
            sections.append(
                f'<h2 style="font-size:15px;color:{colour};margin:26px 0 4px;">{tier} '
                f'<span style="color:#8c959f;font-weight:400;">(0)</span></h2>'
                f'<p style="font-size:13px;color:#8c959f;margin:0 0 14px;">'
                f'Nothing today. {blurb}</p>')
            continue
        sections.append(
            f'<h2 style="font-size:15px;color:{colour};margin:26px 0 4px;">{tier} '
            f'<span style="color:#8c959f;font-weight:400;">({counts[tier]})</span></h2>'
            f'<p style="font-size:12px;color:#8c959f;margin:0 0 12px;">{blurb}</p>'
            + "".join(_card(l) for l in group))

    b, t = cfg["budget"], cfg["target"]
    excluded_note = ""
    if rejected:
        cats = [r for r in rejected if r.reject_reason
                and "write-off" in r.reject_reason.lower()]
        if cats:
            excluded_note = (
                f'<p style="font-size:12px;color:#cf222e;margin:8px 0 0;">'
                f'Filtered out {len(cats)} insurance write-off '
                f'{"car" if len(cats) == 1 else "cars"} (Cat S/C/N/D).</p>')

    return f"""<!DOCTYPE html>
<html><body style="margin:0;padding:0;background:#f6f8fa;
  font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f6f8fa;padding:20px 0;">
<tr><td align="center">
<table width="680" cellpadding="0" cellspacing="0" style="max-width:680px;">
  <tr><td style="padding:0 0 16px;">
    <div style="font-size:22px;font-weight:700;color:#24292f;">PoloFinder</div>
    <div style="font-size:13px;color:#57606a;margin-top:4px;">
      {datetime.now().strftime('%A %d %B %Y')} &middot;
      VW Polo {t.get('min_trim','Match')}+ &middot; {t['engine_litres']}L TSI
      {t['power_ps']}PS &middot; {t.get('min_year','')}+ &middot;
      under {_money(b['max_price'])} &middot; under {b['max_mileage']:,} miles
    </div>
    <div style="font-size:13px;color:#57606a;margin-top:8px;">
      <strong style="color:#24292f;">{len(matched)}</strong> matches
      &middot; <strong style="color:#1a7f37;">{new_count}</strong> new today
      &middot; searched from {_esc(cfg['location'].get('postcode','UK'))}
    </div>
    {excluded_note}
  </td></tr>
  <tr><td>{"".join(sections)}</td></tr>
  <tr><td>{_sources_table(results)}</td></tr>
  <tr><td style="padding:22px 0;font-size:11px;color:#8c959f;line-height:1.6;">
    Sites marked <strong>Deep link</strong> disallow automated search in their
    robots.txt, so PoloFinder builds you a pre-filtered URL to click instead of
    scraping them. Write-off status is inferred from listing text and is not a
    substitute for a proper HPI check before you hand over money.
  </td></tr>
</table></td></tr></table></body></html>"""


def build_markdown(listings, results, cfg) -> str:
    matched = sorted([l for l in listings if l.tier], key=sort_key)
    lines = [f"# PoloFinder - {datetime.now().strftime('%Y-%m-%d')}", "",
             f"**{len(matched)}** matches from {len(results)} sites.", ""]
    for tier in TIER_ORDER:
        group = [l for l in matched if l.tier == tier]
        lines.append(f"## {tier} ({len(group)})")
        if not group:
            lines.append("_Nothing today._")
        for l in group:
            bits = [f"{l.mileage:,} mi" if l.mileage else "", str(l.year or ""),
                    l.seller_type or "", f"~{l.distance_miles} mi away"
                    if l.distance_miles is not None else ""]
            lines.append(f"- [{l.title}]({l.url}) - **{_money(l.price)}** - "
                         f"{' | '.join(b for b in bits if b)} - score {l.score}")
        lines.append("")
    lines += ["## Sites checked", "", "| Site | Status | Hits | Note |", "|---|---|---|---|"]
    for r in results:
        lines.append(f"| [{r.name}]({r.search_url or r.homepage}) | {r.status} | "
                     f"{r.count} | {r.detail[:80]} |")
    return "\n".join(lines)
