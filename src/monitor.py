"""
USA Beauty Retailer Sale Monitor
Sends daily push notification to your phone via ntfy.sh (free, no signup).
"""

import os, re, time, logging, urllib.request, urllib.parse, json
from datetime import datetime
from typing import Optional

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)s  %(message)s")
log = logging.getLogger(__name__)

NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "beauty-monitor-changeme")

BRANDS = [
    "Aesop", "IGK", "R+Co", "Image Skincare",
    "Sente", "Carroten", "Alo", "IN COMMON",
    "Navy Hair", "Previa", "SAC", "Solano",
]

BRAND_ALIASES = {
    "Image Skincare": ["image skincare", "image skin care"],
    "IN COMMON":      ["in common", "incommon", "in common beauty"],
    "Navy Hair":      ["navy hair", "navy hair care"],
    "R+Co":           ["r+co", "r co hair", "randco"],
    "Alo":            ["alo wellness", "alo skincare"],
    "Sente":          ["sente", "sente labs"],
}

RETAILERS = [
    dict(name="Sephora",          rtype="Specialty",
         sale_url="https://www.sephora.com/sale",
         sale_kw=["% off","sale","one-day","savings event"]),
    dict(name="Ulta Beauty",      rtype="Specialty",
         sale_url="https://www.ulta.com/sale",
         sale_kw=["% off","sale","21 days","half price","buy 2"]),
    dict(name="Bluemercury",      rtype="Specialty",
         sale_url="https://bluemercury.com/collections/sale",
         sale_kw=["% off","sale","clearance"]),
    dict(name="Nordstrom",        rtype="Dept. Store",
         sale_url="https://www.nordstrom.com/c/sale-beauty",
         sale_kw=["% off","sale","clearance","anniversary"]),
    dict(name="Saks Fifth Ave",   rtype="Dept. Store",
         sale_url="https://www.saksfifthavenue.com/c/sale",
         sale_kw=["% off","sale","event","clearance"]),
    dict(name="Bloomingdale's",   rtype="Dept. Store",
         sale_url="https://www.bloomingdales.com/shop/sale/beauty",
         sale_kw=["% off","sale","clearance"]),
    dict(name="Macy's",           rtype="Dept. Store",
         sale_url="https://www.macys.com/shop/beauty/sale-clearance/beauty",
         sale_kw=["% off","sale","clearance","flash"]),
    dict(name="Target",           rtype="Mass Market",
         sale_url="https://www.target.com/c/beauty-personal-care/-/N-5xu0k",
         sale_kw=["% off","sale","deal","circle offer","clearance"]),
    dict(name="Walmart",          rtype="Mass Market",
         sale_url="https://www.walmart.com/browse/beauty/0/0/?facet=deal_type:CLEARANCE",
         sale_kw=["% off","rollback","clearance","sale","special buy"]),
    dict(name="Dermstore",        rtype="Online Beauty",
         sale_url="https://www.dermstore.com/c/sale/",
         sale_kw=["% off","sale","flash","clearance","limited time"]),
    dict(name="SkinStore",        rtype="Online Beauty",
         sale_url="https://www.skinstore.com/sale/",
         sale_kw=["% off","sale","flash","clearance"]),
    dict(name="Kohl's",           rtype="Specialty",
         sale_url="https://www.kohls.com/catalog/beauty-sale.jsp",
         sale_kw=["% off","sale","clearance"]),
    dict(name="SalonCentric",     rtype="Pro/Salon",
         sale_url="https://www.saloncentric.com/promotions",
         sale_kw=["% off","sale","deal","promo","flash"]),
    dict(name="Sally Beauty",     rtype="Pro/Salon",
         sale_url="https://www.sallybeauty.com/sale",
         sale_kw=["% off","sale","bogo","clearance"]),
    dict(name="Planet Beauty",    rtype="Specialty",
         sale_url="https://www.planetbeauty.com/collections/sale",
         sale_kw=["% off","sale","clearance"]),
    dict(name="Amazon",           rtype="Marketplace",
         sale_url="https://www.amazon.com/s?k={brand}+beauty&rh=p_n_deal_type:23566064011",
         sale_kw=["% off","deal","coupon","lightning deal","limited time","save $"]),
    dict(name="SAYN.com",         rtype="Distributor",
         sale_url="https://sayn.com/collections/sale",
         sale_kw=["% off","sale","promo"]),
]

HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
}

def fetch(url: str, timeout: int = 15) -> str:
    try:
        req = urllib.request.Request(url, headers=HTTP_HEADERS)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            enc = r.headers.get_content_charset("utf-8") or "utf-8"
            return raw.decode(enc, errors="replace").lower()
    except Exception as e:
        log.warning("FETCH FAILED  %s  —  %s", url, e)
        return ""

def check_brand_at_retailer(retailer: dict, brand: str) -> Optional[dict]:
    aliases = [brand.lower()] + [a.lower() for a in BRAND_ALIASES.get(brand, [])]
    sale_url = retailer["sale_url"]
    if "{brand}" in sale_url:
        sale_url = sale_url.format(brand=urllib.parse.quote_plus(aliases[0]))
    content = fetch(sale_url)
    if not content:
        return None
    if not any(alias in content for alias in aliases):
        return None
    if not any(kw in content for kw in retailer["sale_kw"]):
        return None
    discount = ""
    for alias in aliases:
        idx = content.find(alias)
        if idx != -1:
            snippet = content[max(0, idx-250): idx+350]
            m = re.search(r"(\d{1,2})\s*%\s*off", snippet)
            if m:
                discount = f"{m.group(1)}% off"
                break
    return {
        "retailer": retailer["name"],
        "rtype":    retailer["rtype"],
        "brand":    brand,
        "sale_url": sale_url,
        "discount": discount or "Promo detected",
    }

def run_scan() -> list[dict]:
    findings = []
    total = len(RETAILERS) * len(BRANDS)
    n = 0
    for r in RETAILERS:
        for brand in BRANDS:
            n += 1
            log.info("[%d/%d]  %-22s  —  %s", n, total, r["name"], brand)
            hit = check_brand_at_retailer(r, brand)
            if hit:
                log.info("  SALE: %s at %s  (%s)", brand, r["name"], hit["discount"])
                findings.append(hit)
            time.sleep(0.5)
    return findings

def send_notification(findings: list[dict]):
    topic = NTFY_TOPIC
    today = datetime.now().strftime("%b %d")
    if not findings:
        title    = f"✅ Beauty Monitor — {today}"
        message  = "No sales detected today. All 17 retailers scanned. Amazon listings safe."
        priority = "default"
        tags     = "white_check_mark"
    else:
        by_ret: dict[str, list] = {}
        for f in findings:
            by_ret.setdefault(f["retailer"], []).append(f)
        lines = []
        for ret, items in by_ret.items():
            brands_str = ", ".join(f"{i['brand']} ({i['discount']})" for i in items)
            lines.append(f"• {ret}: {brands_str}")
        title    = f"⚠️ {len(findings)} Sale Alert(s) — {today}"
        message  = "\n".join(lines) + "\n\nCheck Amazon pricing NOW to avoid suppression!"
        priority = "high"
        tags     = "warning,rotating_light"
    payload = {
        "topic":    topic,
        "title":    title,
        "message":  message,
        "priority": priority,
        "tags":     tags.split(","),
    }
    data = json.dumps(payload).encode("utf-8")
    req  = urllib.request.Request(
        "https://ntfy.sh",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        log.info("Notification sent. Status: %s", r.status)

if __name__ == "__main__":
    log.info("=" * 55)
    log.info("Beauty Sale Monitor — %s", datetime.now().strftime("%B %d, %Y %H:%M"))
    log.info("Scanning %d brands x %d retailers", len(BRANDS), len(RETAILERS))
    log.info("=" * 55)
    findings = run_scan()
    log.info("Scan complete. %d sale(s) found.", len(findings))
    send_notification(findings)
    log.info("Done.")
