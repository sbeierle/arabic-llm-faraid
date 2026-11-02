import asyncio
import json
import sys
import urllib.parse
from playwright.async_api import async_playwright

# Pro Frage ein kurzer Suchbegriff (kurze Begriffe finden mehr als ganze Saetze)
TOPICS = [
    ("FIQH_001", "لمس المرأة ينقض الوضوء"),
    ("FIQH_002", "الترتيب في الوضوء فرض"),
    ("FIQH_003", "حكم أكل الجمبري حيوان البحر"),
    ("FIQH_004", "حكم أكل لحم الخيل"),
    ("FIQH_005", "الجهر بالبسملة في الصلاة"),
    ("FIQH_006", "النكاح بلا ولي"),
    ("FIQH_007", "خيار المجلس"),
    ("FIQH_008", "قصر الصلاة في السفر واجب أم سنة"),
    ("FIQH_009", "طهارة الكلب لعاب شعر"),
    ("FIQH_010", "قراءة الفاتحة خلف الإمام"),
]

# Quelle -> Such-Praefixe (DuckDuckGo site:-Suche, damit wir keine Seiten-Suchen raten muessen)
SOURCES = {
    "kuwait_mawsua": [
        "site:islamweb.net الموسوعة الفقهية الكويتية",
        "site:shamela.ws الموسوعة الفقهية الكويتية",
    ],
    "ibn_baz": ["site:binbaz.org.sa"],
    "ibn_uthaymin": ["site:binothaimeen.net"],
    "lajna_daima": ["site:alifta.gov.sa -site:sunna.alifta.gov.sa"],
}

TOP_LINKS = 2      # so viele brauchbare Seiten pro Suche
MAX_LINKS = 6      # so viele Treffer werden hoechstens probiert
MAX_CHARS = 10000  # Seitentext pro Treffer
ONLY = sys.argv[1:]   # z.B.: python fiqh_cdp_scrape.py lajna_daima
if ONLY:
    SOURCES = {k: v for k, v in SOURCES.items() if k in ONLY}
OUT = "fiqh_raw_sources.json" if not ONLY else "fiqh_raw_sources_" + "_".join(ONLY) + ".json"


def bad_page(r):
    if "error" in r:
        return "Fehler"
    head = r.get("text", "")[:400].lower()
    if "service unavailable" in head or "http error 503" in head or "just a moment" in head:
        return "503/Sperre"
    if len(r.get("text", "")) < 400:
        return "fast leer"
    return None


async def wait_if_blocked(page, what):
    title = await page.title()
    body = (await page.inner_text("body"))[:600].lower()
    if "just a moment" in title.lower() or "captcha" in body or "unusual traffic" in body or "anomaly" in body:
        input(f"[{what}] Sperre/Captcha im Browser loesen, dann hier ENTER druecken... ")


async def ddg_links(page, query):
    url = "https://html.duckduckgo.com/html/?q=" + urllib.parse.quote(query)
    await page.goto(url, wait_until="domcontentloaded")
    await asyncio.sleep(2)
    await wait_if_blocked(page, "Suche")
    links = []
    for a in await page.query_selector_all("a.result__a"):
        href = await a.get_attribute("href") or ""
        title = (await a.inner_text()).strip()
        if "uddg=" in href:
            href = urllib.parse.unquote(href.split("uddg=")[1].split("&")[0])
        elif href.startswith("//"):
            href = "https:" + href
        if not href.startswith("http") or href.lower().endswith(".pdf"):
            continue
        links.append({"url": href, "title": title})
        if len(links) >= MAX_LINKS:
            break
    return links


async def grab(page, url):
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=45000)
        await asyncio.sleep(2.5)
        await wait_if_blocked(page, "Seite")
        title = await page.title()
        text = await page.inner_text("body")
        return {"url": url, "title": title, "text": text[:MAX_CHARS]}
    except Exception as e:
        return {"url": url, "error": str(e)}


async def main():
    results = []
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp("http://localhost:9222")
        context = browser.contexts[0]
        page = await context.new_page()   # eigener Tab, deine offenen Tabs bleiben unberuehrt

        for tid, kw in TOPICS:
            for src, prefixes in SOURCES.items():
                for prefix in prefixes:
                    query = f"{prefix} {kw}"
                    print(f"[{tid}] {src}: {query}", flush=True)
                    entry = {"id": tid, "source": src, "query": query, "links": [], "pages": []}
                    try:
                        entry["links"] = await ddg_links(page, query)
                        good = 0
                        for l in entry["links"]:
                            r = await grab(page, l["url"])
                            why = bad_page(r)
                            if why:
                                r["uebersprungen"] = why
                            else:
                                good += 1
                            entry["pages"].append(r)
                            await asyncio.sleep(1.5)
                            if good >= TOP_LINKS:
                                break
                    except Exception as e:
                        entry["error"] = str(e)
                    print(f"   -> {sum(1 for r in entry['pages'] if 'uebersprungen' not in r)} brauchbare Seiten, {sum(1 for r in entry['pages'] if 'uebersprungen' in r)} uebersprungen", flush=True)
                    results.append(entry)
                    await asyncio.sleep(1.5)
            with open(OUT, "w", encoding="utf-8") as f:   # nach jeder Frage sichern
                json.dump(results, f, ensure_ascii=False, indent=2)

        await page.close()
    print(f"\nFertig! Ergebnisse liegen in {OUT}.")


if __name__ == "__main__":
    asyncio.run(main())
