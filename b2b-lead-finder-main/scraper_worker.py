"""
Scraper worker — runs independently, writes results to a JSON file.
Called by app.py via subprocess. Also works standalone:
  python scraper_worker.py "interior designers" "Kuala Lumpur" JOB_ID
"""

import re
import sys
import json
import time
import subprocess
from pathlib import Path
from playwright.sync_api import sync_playwright

# ─── Location metadata ────────────────────────────────────────────────────────
LOCATION_META = {
    # ── Singapore ──
    "Singapore":          {"coords": "@1.3521,103.8198,12z", "label": "Singapore"},
    "Central Region":     {"coords": "@1.2966,103.8498,13z", "label": "Central Singapore"},
    "East Region":        {"coords": "@1.3236,103.9273,13z", "label": "East Singapore"},
    "North Region":       {"coords": "@1.4184,103.8068,13z", "label": "North Singapore"},
    "North-East Region":  {"coords": "@1.3765,103.8882,13z", "label": "North-East Singapore"},
    "West Region":        {"coords": "@1.3203,103.7478,13z", "label": "West Singapore"},
    "Orchard":            {"coords": "@1.3048,103.8318,15z", "label": "Orchard Singapore"},
    "Marina Bay":         {"coords": "@1.2802,103.8586,15z", "label": "Marina Bay Singapore"},
    "Tanjong Pagar":      {"coords": "@1.2762,103.8436,15z", "label": "Tanjong Pagar Singapore"},
    "Bugis":              {"coords": "@1.3008,103.8559,15z", "label": "Bugis Singapore"},
    "Jurong":             {"coords": "@1.3329,103.7436,14z", "label": "Jurong Singapore"},
    "Tampines":           {"coords": "@1.3540,103.9437,14z", "label": "Tampines Singapore"},
    "Woodlands":          {"coords": "@1.4370,103.7862,14z", "label": "Woodlands Singapore"},
    "Ang Mo Kio":         {"coords": "@1.3691,103.8454,14z", "label": "Ang Mo Kio Singapore"},
    "Bishan":             {"coords": "@1.3520,103.8492,15z", "label": "Bishan Singapore"},
    "Clementi":           {"coords": "@1.3153,103.7653,15z", "label": "Clementi Singapore"},
    "Bedok":              {"coords": "@1.3236,103.9273,14z", "label": "Bedok Singapore"},
    "Pasir Ris":          {"coords": "@1.3720,103.9494,14z", "label": "Pasir Ris Singapore"},
    "Punggol":            {"coords": "@1.4043,103.9022,14z", "label": "Punggol Singapore"},
    "Sengkang":           {"coords": "@1.3911,103.8954,14z", "label": "Sengkang Singapore"},
    "Hougang":            {"coords": "@1.3719,103.8930,14z", "label": "Hougang Singapore"},
    "Serangoon":          {"coords": "@1.3554,103.8679,14z", "label": "Serangoon Singapore"},
    "Buona Vista":        {"coords": "@1.3072,103.7904,15z", "label": "Buona Vista Singapore"},
    "Novena":             {"coords": "@1.3204,103.8437,15z", "label": "Novena Singapore"},
    "Toa Payoh":          {"coords": "@1.3343,103.8563,15z", "label": "Toa Payoh Singapore"},
    # ── Malaysia ──
    "Malaysia":           {"coords": "@3.1390,101.6869,7z",  "label": "Malaysia"},
    "Kuala Lumpur":       {"coords": "@3.1390,101.6869,13z", "label": "Kuala Lumpur Malaysia"},
    "Selangor":           {"coords": "@3.0738,101.5183,11z", "label": "Selangor Malaysia"},
    "Johor":              {"coords": "@1.9344,103.3587,10z", "label": "Johor Malaysia"},
    "Penang":             {"coords": "@5.4141,100.3288,12z", "label": "Penang Malaysia"},
    "Perak":              {"coords": "@4.5921,101.0901,10z", "label": "Perak Malaysia"},
    "Sabah":              {"coords": "@5.9788,116.0753,9z",  "label": "Sabah Malaysia"},
    "Sarawak":            {"coords": "@1.5533,110.3592,8z",  "label": "Sarawak Malaysia"},
    "Pahang":             {"coords": "@3.8126,103.3256,9z",  "label": "Pahang Malaysia"},
    "Negeri Sembilan":    {"coords": "@2.7258,101.9424,11z", "label": "Negeri Sembilan Malaysia"},
    "Melaka":             {"coords": "@2.1896,102.2501,12z", "label": "Melaka Malaysia"},
    "Kedah":              {"coords": "@6.1184,100.3685,11z", "label": "Kedah Malaysia"},
    "Kelantan":           {"coords": "@5.7414,102.1701,10z", "label": "Kelantan Malaysia"},
    "Terengganu":         {"coords": "@5.3117,103.1324,10z", "label": "Terengganu Malaysia"},
    "Perlis":             {"coords": "@6.4449,100.2053,12z", "label": "Perlis Malaysia"},
    "Putrajaya":          {"coords": "@2.9264,101.6964,14z", "label": "Putrajaya Malaysia"},
    "Labuan":             {"coords": "@5.2831,115.2308,13z", "label": "Labuan Malaysia"},
}


def update_file(job_file: Path, leads, message, status="running", total=0):
    try:
        job_file.write_text(json.dumps({
            "status" : status,
            "message": message,
            "leads"  : leads,
            "total"  : total,
        }, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def main(query, location, job_id):
    results_dir = Path(__file__).parent / "results"
    results_dir.mkdir(exist_ok=True)
    job_file = results_dir / f"{job_id}.json"

    update_file(job_file, [], "🌐 Opening Google Maps …")

    # Ensure Playwright Chromium binary is downloaded (system libs come from packages.txt)
    update_file(job_file, [], "🔧 Checking browser installation …")
    try:
        subprocess.run(
            [sys.executable, "-m", "playwright", "install", "chromium"],
            capture_output=True, timeout=180
        )
    except Exception as e:
        update_file(job_file, [], f"⚠️ Browser install warning: {e} — trying anyway …")

    # Build search label and URL
    meta        = LOCATION_META.get(location, {})
    label       = meta.get("label", location)
    coords      = meta.get("coords", "")
    search_term = f"{query} {label}"
    seen        = set()
    leads       = []

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--disable-blink-features=AutomationControlled",
                    "--window-size=1280,900",
                ],
            )
            context = browser.new_context(
                viewport={"width": 1280, "height": 900},
                locale="en-US",
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
            )

            # Block images/fonts/media — Streamlit Cloud's free tier has ~1GB RAM,
            # and Google Maps pages are image-heavy. Without this, headless
            # Chromium gets OOM-killed partway through the detail-page loop,
            # which shows up as a silent "0 leads" with no error in the UI.
            context.route(
                "**/*",
                lambda route: route.abort()
                if route.request.resource_type in ("image", "font", "media")
                else route.continue_(),
            )

            # Bypass Google consent wall
            context.add_cookies([
                {"name": "CONSENT", "value": "YES+cb.20231002-17-p0.en+FX+410",
                 "domain": ".google.com", "path": "/"},
                {"name": "SOCS",    "value": "CAESEwgDEgk0NTc4MDU1NzIaAmVuIAEaBgiAv5SmBg",
                 "domain": ".google.com", "path": "/"},
            ])

            page = context.new_page()

            # Coordinate-biased URL — pins the search to the right area
            encoded = search_term.replace(" ", "+")
            url = (f"https://www.google.com/maps/search/{encoded}/{coords}"
                   if coords else
                   f"https://www.google.com/maps/search/{encoded}/")

            update_file(job_file, leads, "🌐 Opening Google Maps …")
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            time.sleep(3)

            # Dismiss any remaining consent dialogs
            for sel in ["button:has-text('Accept all')", "button:has-text('Reject all')",
                        "#L2AGLb", "button:has-text('Agree')"]:
                try:
                    page.click(sel, timeout=2000)
                    time.sleep(1)
                    break
                except Exception:
                    pass

            # Wait for feed
            update_file(job_file, leads, "⏳ Waiting for results feed …")
            try:
                page.wait_for_selector("div[role='feed']", timeout=20000)
            except Exception:
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
                time.sleep(3)
                try:
                    page.wait_for_selector("div[role='feed']", timeout=15000)
                except Exception:
                    page_title = page.title()
                    page_url   = page.url
                    # Grab first 300 chars of page text for diagnosis
                    try:
                        page_text = page.evaluate("() => document.body.innerText").strip()[:300]
                    except Exception:
                        page_text = "(could not read page)"
                    update_file(job_file, leads,
                                f"❌ Feed not found. Title: '{page_title}' | URL: {page_url} | Page text: {page_text}",
                                status="done")
                    browser.close()
                    return

            # Scroll to load listings — stop early if end-of-list detected
            update_file(job_file, leads, "📜 Scrolling to load listings …")
            no_new_count = 0
            prev_count   = 0
            for scroll_i in range(60):
                page.evaluate("""() => {
                    const f = document.querySelector("div[role='feed']");
                    if (f) f.scrollTop += 700;
                }""")
                time.sleep(0.6)

                end_reached = page.evaluate("""() => {
                    const spans = document.querySelectorAll("span");
                    for (const s of spans) {
                        if (s.innerText && s.innerText.includes("reached the end")) return true;
                    }
                    return false;
                }""")
                if end_reached:
                    break

                if scroll_i % 8 == 7:
                    cur = len(page.query_selector_all("a[href*='/maps/place/']"))
                    if cur == prev_count:
                        no_new_count += 1
                        if no_new_count >= 2:
                            break
                    else:
                        no_new_count = 0
                    prev_count = cur

            time.sleep(1)

            # Collect unique place URLs
            cards = page.query_selector_all("a[href*='/maps/place/']")
            seen_hrefs, place_urls = set(), []
            for c in cards:
                href  = c.get_attribute("href") or ""
                clean = href.split("?")[0]
                if clean and "/maps/place/" in clean and clean not in seen_hrefs:
                    seen_hrefs.add(clean)
                    place_urls.append(href)

            total = len(place_urls)
            update_file(job_file, leads, f"📌 Found {total} listings. Extracting …", total=total)

            if total == 0:
                page_title = page.title()
                page_url   = page.url
                try:
                    page_text = page.evaluate("() => document.body.innerText").strip()[:300]
                except Exception:
                    page_text = "(could not read)"
                update_file(job_file, leads,
                            f"❌ 0 listings. Title: '{page_title}' | URL: {page_url} | Text: {page_text}",
                            status="done")
                browser.close()
                return

            skipped_reasons = []

            MAX_DETAIL_PAGES = 60  # keeps memory bounded on Streamlit Cloud's free tier
            for place_url in place_urls[:MAX_DETAIL_PAGES]:
                try:
                    page.goto(place_url, wait_until="domcontentloaded", timeout=30000)

                    try:
                        page.wait_for_selector("h1", timeout=8000)
                    except Exception:
                        if len(skipped_reasons) < 3:
                            try:
                                snippet = page.evaluate("() => document.body.innerText").strip()[:200]
                            except Exception:
                                snippet = "(could not read page)"
                            skipped_reasons.append(f"title='{page.title()}' text='{snippet}'")
                        continue

                    # Name
                    name = ""
                    for sel in ["h1.DUwDvf", "h1[class*='fontHeadline']", "h1"]:
                        el = page.query_selector(sel)
                        if el:
                            name = (el.inner_text() or "").strip()
                            if name:
                                break
                    if not name:
                        if len(skipped_reasons) < 3:
                            try:
                                snippet = page.evaluate("() => document.body.innerText").strip()[:200]
                            except Exception:
                                snippet = "(could not read page)"
                            skipped_reasons.append(f"empty-name title='{page.title()}' text='{snippet}'")
                        continue
                    if name in seen:
                        continue
                    seen.add(name)

                    # Rating
                    rating = ""
                    for sel in ["div.F7nice span[aria-hidden='true']",
                                "span.ceNzKf[aria-hidden='true']",
                                "span[aria-hidden='true']"]:
                        el = page.query_selector(sel)
                        if el:
                            t = (el.inner_text() or "").strip()
                            if re.match(r"^\d[\d.]*$", t):
                                rating = t
                                break

                    # Reviews
                    reviews = 0
                    for sel in ["span[aria-label*='review']", "button[aria-label*='review']",
                                "span[aria-label*='Rating']"]:
                        el = page.query_selector(sel)
                        if el:
                            m = re.search(r"([\d,]+)", el.get_attribute("aria-label") or "")
                            if m:
                                reviews = int(m.group(1).replace(",", ""))
                                break

                    # Category, address, phone, website
                    def get_text(sels):
                        for s in sels:
                            el = page.query_selector(s)
                            if el:
                                t = (el.inner_text() or "").strip()
                                if t:
                                    return t
                        return ""

                    category = get_text(["button.DkEaL", "span.mgr77e", "button[jsaction*='category']"])
                    address  = get_text(["button[data-item-id='address'] .rogA2c",
                                         "button[data-item-id='address']",
                                         "[data-tooltip='Copy address']"])
                    phone    = get_text(["button[data-item-id*='phone'] .rogA2c",
                                         "button[data-item-id*='phone']",
                                         "[data-tooltip='Copy phone number']"])

                    website = ""
                    for sel in ["a[data-item-id='authority']", "a[aria-label*='ebsite']",
                                "a[data-tooltip='Open website']"]:
                        el = page.query_selector(sel)
                        if el:
                            w = re.sub(r"\?.*", "", el.get_attribute("href") or "")
                            if w and "google" not in w:
                                website = w
                                break

                    leads.append({
                        "Name"       : name,
                        "Rating"     : rating,
                        "Reviews"    : reviews,
                        "Category"   : category,
                        "Phone"      : phone,
                        "Website"    : website,
                        "Address"    : address,
                        "Google Maps": place_url.split("?")[0],
                    })

                    update_file(job_file, leads,
                                f"⚡ Found {len(leads)} leads so far …",
                                total=total)

                except Exception as loop_exc:
                    if len(skipped_reasons) < 3:
                        skipped_reasons.append(f"exception: {type(loop_exc).__name__}: {loop_exc}")
                    # If the browser/page itself died (e.g. OOM kill), retrying
                    # the remaining URLs against a dead page is pointless —
                    # stop here and keep whatever leads we already collected.
                    if type(loop_exc).__name__ == "TargetClosedError":
                        break
                    continue

            browser.close()

    except Exception as e:
        # Write the actual error to the job file so we can see it in the UI
        update_file(job_file, leads,
                    f"❌ Scraper error: {e}",
                    status="done", total=len(leads))
        return

    if leads:
        final_msg = f"✅ Done! Found {len(leads)} leads."
    elif skipped_reasons:
        final_msg = f"❌ Done. Found 0 leads. Sample failures: {' || '.join(skipped_reasons)}"
    else:
        final_msg = "✅ Done! Found 0 leads."

    update_file(job_file, leads, final_msg, status="done", total=total)


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Usage: scraper_worker.py <query> <location> <job_id>")
        sys.exit(1)
    main(sys.argv[1], sys.argv[2], sys.argv[3])
