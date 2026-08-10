"""
TEFAS'tan (tefas.gov.tr) gunluk fiyat verisini ceker, data/tefas_veri.json'u
gunceller ve docs/index.html raporunu yeniden uretir.

Playwright (headless Chromium) kullanir cunku TEFAS'in fon-verileri sayfasi
istemci tarafinda (JS ile) render ediliyor ve API'si dogrudan HTTP istegine
kapali/POST-only. Site ayrica bir bot korumasi (WAF) barindiriyor; bulut IP'leri
(GitHub Actions dahil) bazen bu korumaya takilabilir. Bu durumda script hata
verip cikacak, mevcut veri/rapor DEGISTIRILMEYECEK.

Kullanim:
  python scripts/fetch_and_build.py
"""
import asyncio
import json
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import report  # noqa: E402

FUND_CODES = [
    "HLL", "TZL", "ZBJ",              # Ziraat Portföy
    "IOO", "IOP", "IUZ", "TI1",       # İş Portföy
    "ALE", "ANL", "BGP", "SAP",       # Ak Portföy
    "GAL", "GNP", "GPZ", "GTL",       # Garanti BBVA Portföy
    "PPI", "YLB", "YVD",              # Yapı Kredi Portföy
    "DCN", "DL2", "DLY",              # Deniz Portföy
    "ENR", "FI5", "FSK", "OPJ", "YMP",  # QNB Finans Portföy
    "BRG", "IGL", "PTL", "PYB", "SKL", "TKM",  # TEB Portföy
]

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def previous_business_day(d):
    d = d - timedelta(days=1)
    while d.weekday() >= 5:  # 5=Cumartesi, 6=Pazar
        d -= timedelta(days=1)
    return d


def parse_prices(text, wanted_codes):
    """get_page_text tarzı düz metinden fon kodu/fiyat çiftlerini çıkarır.
    Satır düzeni: KOD / AD / TARİH / FİYAT / PAY SAYISI / KİŞİ SAYISI / TOPLAM DEĞER
    """
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    found = {}
    wanted = set(wanted_codes)
    for i, ln in enumerate(lines):
        if ln in wanted and i + 3 < len(lines):
            price_line = lines[i + 3]
            # Fiyat formatı: "3,446530" -> 3.446530
            cleaned = price_line.replace(".", "").replace(",", ".")
            try:
                price = float(cleaned)
            except ValueError:
                continue
            found[ln] = price
    return found


async def fetch_prices_for_date(date_str):
    from playwright.async_api import async_playwright

    url = (
        f"https://www.tefas.gov.tr/tr/fon-verileri?fundType=YAT&sfonTurKod=107"
        f"&startDate={date_str}&endDate={date_str}"
    )
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(user_agent=USER_AGENT, locale="tr-TR")
        page = await context.new_page()
        await page.goto(url, wait_until="networkidle", timeout=45000)
        await page.wait_for_timeout(3000)

        body_text = await page.inner_text("body")
        if "Request Rejected" in body_text:
            await browser.close()
            raise RuntimeError("TEFAS bot korumasi (WAF) istegi reddetti (Request Rejected).")
        if "sonuç bulunamadı" in body_text or "eşleşen fon verisi bulunamadı" in body_text:
            await browser.close()
            return None  # o gun veri yok (tatil vb.)

        found = {}
        for _ in range(6):  # en fazla 6 sayfa gez (81+ fon icin yeterli)
            main_text = await page.inner_text("main")
            found.update(parse_prices(main_text, FUND_CODES))
            if len(found) >= len(FUND_CODES):
                break
            next_btn = page.get_by_role("button", name="Sonraki")
            if await next_btn.count() == 0:
                break
            try:
                is_disabled = await next_btn.get_attribute("disabled")
            except Exception:
                is_disabled = None
            if is_disabled is not None:
                break
            await next_btn.click()
            await page.wait_for_timeout(2000)

        await browser.close()
        return found


async def main():
    target = previous_business_day(datetime.utcnow() + timedelta(hours=3))  # TR saati (UTC+3)

    prices = None
    used_date = None
    for attempt in range(5):
        date_str = target.strftime("%Y-%m-%d")
        print(f"Deneniyor: {date_str}")
        try:
            result = await fetch_prices_for_date(date_str)
        except RuntimeError as e:
            print(f"HATA: {e}")
            print("GitHub Actions IP'si TEFAS tarafindan engellenmis olabilir. "
                  "Iscilik durduruluyor, mevcut veri/rapor degistirilmedi.")
            sys.exit(1)

        if result and len(result) >= len(FUND_CODES) * 0.8:  # en az %80'i bulunduysa yeterli say
            prices = result
            used_date = date_str
            break
        print(f"{date_str} icin yeterli veri bulunamadi ({len(result or {})}/{len(FUND_CODES)}), bir onceki is gunune geciliyor.")
        target = previous_business_day(target)

    if not prices:
        print("5 denemede veri bulunamadi. Cikiliyor (rapor guncellenmedi).")
        sys.exit(1)

    missing = set(FUND_CODES) - set(prices.keys())
    if missing:
        print(f"UYARI: su fonlar icin fiyat bulunamadi: {sorted(missing)}")

    rows = report.build(date_str=used_date, prices=prices)
    print(f"\nRapor guncellendi ({used_date}), {len(rows)} fon:")
    for r in sorted(rows, key=lambda r: (r["sirket"], -(r["gunluk_getiri"] or -999))):
        gr = f"{r['gunluk_getiri']:.4f}%" if r["gunluk_getiri"] is not None else "—"
        print(f"  [{r['sirket']:22s}] {r['kod']:5s} {gr:>10s}  {r['fiyat']:.6f}")


if __name__ == "__main__":
    asyncio.run(main())
