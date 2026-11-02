import asyncio
import json
import sys
import urllib.parse
from playwright.async_api import async_playwright

# (id, quelle, kompletter Suchtext) - gezielt fuer die 9 Gold-Luecken, 1 Bestaetigung und 4 Idschma-Kontrollen
JOBS = [
 ("FIQH_002","ibn_uthaymin","site:binothaimeen.net الترتيب في الوضوء فرض"),
 ("FIQH_003","kuwait_mawsua","site:islamweb.net أكل حيوان البحر الحنفية الحنابلة الجمبري"),
 ("FIQH_003","kuwait_mawsua","site:shamela.ws الموسوعة الفقهية الكويتية حيوان البحري أكل"),
 ("FIQH_004","kuwait_mawsua","site:islamweb.net أكل لحم الخيل الحنفية أبو حنيفة"),
 ("FIQH_004","kuwait_mawsua","site:shamela.ws الموسوعة الفقهية الكويتية لحم الخيل"),
 ("FIQH_004","ibn_uthaymin","site:binothaimeen.net حكم أكل لحم الخيل"),
 ("FIQH_005","ibn_uthaymin","site:binothaimeen.net الجهر بالبسملة في الصلاة"),
 ("FIQH_006","kuwait_mawsua","site:islamweb.net نكاح المرأة بغير ولي الحنفية أبو حنيفة"),
 ("FIQH_006","kuwait_mawsua","site:shamela.ws الموسوعة الفقهية الكويتية ولاية النكاح الحنفية"),
 ("FIQH_007","ibn_uthaymin","site:binothaimeen.net خيار المجلس"),
 ("FIQH_008","kuwait_mawsua","site:islamweb.net قصر الصلاة واجب الحنفية الحنابلة"),
 ("FIQH_008","kuwait_mawsua","site:shamela.ws الموسوعة الفقهية الكويتية صلاة المسافر القصر"),
 ("FIQH_009","ibn_uthaymin","site:binothaimeen.net نجاسة الكلب"),
 ("FIQH_C01","kuwait_mawsua","site:islamweb.net تحريم لحم الخنزير إجماع"),
 ("FIQH_C01","kuwait_mawsua","site:shamela.ws الموسوعة الفقهية الكويتية خنزير"),
 ("FIQH_C02","kuwait_mawsua","site:islamweb.net فرضية الصلوات الخمس إجماع"),
 ("FIQH_C02","kuwait_mawsua","site:shamela.ws الموسوعة الفقهية الكويتية صلاة الصلوات الخمس فرض"),
 ("FIQH_C03","kuwait_mawsua","site:islamweb.net وجوب صوم رمضان إجماع"),
 ("FIQH_C03","kuwait_mawsua","site:shamela.ws الموسوعة الفقهية الكويتية صوم رمضان فرض"),
 ("FIQH_C04","kuwait_mawsua","site:islamweb.net وجوب الحج مرة في العمر إجماع"),
 ("FIQH_C04","kuwait_mawsua","site:shamela.ws الموسوعة الفقهية الكويتية الحج فرض مرة"),
]

TOP_LINKS = 2      # so viele brauchbare Seiten pro Suche
MAX_LINKS = 6      # so viele Treffer werden hoechstens probiert
MAX_CHARS = 10000  # Seitentext pro Treffer
OUT = "fiqh_raw_gaps.json"


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

        for tid, src_name, query in JOBS:
            print(f"[{tid}] {src_name}: {query}", flush=True)
            entry = {"id": tid, "source": src_name, "query": query, "links": [], "pages": []}
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
            except Exception as ex:
                entry["error"] = str(ex)
            print(f"   -> {sum(1 for r in entry['pages'] if 'uebersprungen' not in r)} brauchbare Seiten", flush=True)
            results.append(entry)
            with open(OUT, "w", encoding="utf-8") as f:
                json.dump(results, f, ensure_ascii=False, indent=2)
            await asyncio.sleep(1.5)

        await page.close()
    print(f"\nFertig! Ergebnisse liegen in {OUT}.")


if __name__ == "__main__":
    asyncio.run(main())
