"""
TEFAS'tan (tefas.gov.tr) gunluk fiyat verisini ceker, data/tefas_veri.json'u
gunceller ve docs/index.html raporunu yeniden uretir.

Takip edilen fon listesi data/fon_listesi.csv dosyasindan okunur — YENI FON
EKLEMEK ICIN sadece bu CSV'ye bir satir eklemeniz yeterlidir, kod
degistirmenize gerek yoktur. Format:

    kod,sirket,risk
    HLL,Ziraat Portföy,1
    ...

- kod: TEFAS fon kodu (buyuk harf)
- sirket: rapor sayfasinda hangi basligin altinda gorunecegi (serbest metin)
- risk: TEFAS'taki "Fonun Risk Degeri" (1-7), sadece bilgi amacli, bos birakilabilir

Fon adi (ad) TEFAS'tan otomatik cekilir, elle girmenize gerek yoktur.

Playwright (headless Chromium) kullanir cunku TEFAS'in fon-verileri sayfasi
istemci tarafinda (JS ile) render ediliyor ve API'si dogrudan HTTP istegine
kapali/POST-only. Site ayrica bir bot korumasi (WAF) barindiriyor; bulut IP'leri
(GitHub Actions dahil) bazen bu korumaya takilabilir. Bu durumda script hata
verip cikacak, mevcut veri/rapor DEGISTIRILMEYECEK.

Kullanim:
  python scripts/fetch_and_build.py
"""
import asyncio
import csv
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import report  # noqa: E402

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FON_LISTESI_FILE = os.path.join(BASE_DIR, "data", "fon_listesi.csv")

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def load_fon_listesi():
    """data/fon_listesi.csv dosyasini okur -> {kod: {sirket, risk}}"""
    fonlar = {}
    with open(FON_LISTESI_FILE, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            kod = row["kod"].strip().upper()
            if not kod or kod.startswith("#"):
                continue
            risk_raw = (row.get("risk") or "").strip()
            fonlar[kod] = {
                "sirket": (row.get("sirket") or "Diğer").strip(),
                "risk": int(risk_raw) if risk_raw.isdigit() else None,
            }
    return fonlar


def previous_business_day(d):
    d = d - timedelta(days=1)
    while d.weekday() >= 5:  # 5=Cumartesi, 6=Pazar
        d -= timedelta(days=1)
    return d


def parse_rows(text, wanted_codes):
    """get_page_text tarzı düz metinden fon kodu -> (fiyat, ad) çıkarır.
    Satır düzeni: KOD / AD / TARİH / FİYAT / PAY SAYISI / KİŞİ SAYISI / TOPLAM DEĞER
    """
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    found = {}
    wanted = set(wanted_codes)
    for i, ln in enumerate(lines):
        if ln in wanted and i + 3 < len(lines):
            name = lines[i + 1]
            price_line = lines[i + 3]
            cleaned = price_line.replace(".", "").replace(",", ".")
            try:
                price = float(cleaned)
            except ValueError:
                continue
            found[ln] = (price, name)
    return found


def parse_detail_page(text):
    """fon-detayli-analiz/{KOD} sayfasının düz metninden (fiyat, ad) çıkarır.
    Bu sayfa, Para Piyasası dışındaki şemsiye fon türlerinde (ör. Serbest Fon)
    olup sfonTurKod=107 sorgusunda görünmeyen fonlar için yedek kaynaktır.
    """
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    name = None
    for ln in lines:
        if ln.isupper() and "PORTFÖY" in ln:
            name = ln
            break
    price = None
    for i, ln in enumerate(lines):
        if ln.startswith("Son Fiyat") and i + 1 < len(lines):
            cleaned = lines[i + 1].replace(".", "").replace(",", ".")
            try:
                price = float(cleaned)
            except ValueError:
                pass
            break
    return price, name


async def fetch_single_fund_detail(page, kod):
    """Tek bir fon için fon-detayli-analiz sayfasından fiyat/ad çeker (yedek yol)."""
    await page.goto(f"https://www.tefas.gov.tr/tr/fon-detayli-analiz/{kod}",
                     wait_until="networkidle", timeout=45000)
    await page.wait_for_timeout(2500)
    body_text = await page.inner_text("body")
    if "Request Rejected" in body_text:
        raise RuntimeError("TEFAS bot korumasi (WAF) istegi reddetti (Request Rejected).")
    return parse_detail_page(body_text)


async def fetch_prices_for_date(date_str, fund_codes):
    """Ana kaynak: sfonTurKod=107 (Para Piyasası Şemsiye Fonu) sorgusu, tek
    tarih, tüm sayfalar gezilir. Bu sorguda görünmeyen fonlar (ör. Serbest
    Şemsiye Fonu altındaki para piyasası benzeri fonlar) için main() içinde
    fon-detayli-analiz sayfası yedek olarak kullanılır.
    """
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
            found.update(parse_rows(main_text, fund_codes))
            if len(found) >= len(fund_codes):
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

        # Yedek yol: ana sorguda bulunamayan (farkli semsiye fon turundeki)
        # fonlar icin tek tek fon-detayli-analiz sayfasina bak (yavas ve
        # nazik: en fazla 15 fon, aralarinda bekleme).
        missing = [c for c in fund_codes if c not in found]
        for kod in missing[:15]:
            try:
                price, name = await fetch_single_fund_detail(page, kod)
            except RuntimeError:
                break  # WAF devreye girdi, daha fazla denemeyelim
            if price is not None:
                found[kod] = (price, name or kod)
            await page.wait_for_timeout(2500)

        await browser.close()
        return found


async def main():
    fon_listesi = load_fon_listesi()
    fund_codes = list(fon_listesi.keys())
    print(f"Takip edilen fon sayisi (data/fon_listesi.csv): {len(fund_codes)}")

    target = previous_business_day(datetime.utcnow() + timedelta(hours=3))  # TR saati (UTC+3)

    result = None
    used_date = None
    for attempt in range(5):
        date_str = target.strftime("%Y-%m-%d")
        print(f"Deneniyor: {date_str}")
        try:
            r = await fetch_prices_for_date(date_str, fund_codes)
        except RuntimeError as e:
            print(f"HATA: {e}")
            print("GitHub Actions IP'si TEFAS tarafindan engellenmis olabilir. "
                  "Iscilik durduruluyor, mevcut veri/rapor degistirilmedi.")
            sys.exit(1)

        if r and len(r) >= len(fund_codes) * 0.8:  # en az %80'i bulunduysa yeterli say
            result = r
            used_date = date_str
            break
        print(f"{date_str} icin yeterli veri bulunamadi ({len(r or {})}/{len(fund_codes)}), bir onceki is gunune geciliyor.")
        target = previous_business_day(target)

    if not result:
        print("5 denemede veri bulunamadi. Cikiliyor (rapor guncellenmedi).")
        sys.exit(1)

    missing = set(fund_codes) - set(result.keys())
    if missing:
        print(f"UYARI: su fonlar icin fiyat bulunamadi: {sorted(missing)}")

    # data/tefas_veri.json'u guncelle: fiyat + ad (TEFAS'tan) + sirket/risk (CSV'den)
    data = report.load_data()
    data.setdefault("fonlar", {})
    for kod, (price, name) in result.items():
        meta = fon_listesi.get(kod, {"sirket": "Diğer", "risk": None})
        entry = data["fonlar"].setdefault(kod, {"ad": name, "gecmis": []})
        entry["ad"] = name
        entry["sirket"] = meta["sirket"]
        entry["risk"] = meta["risk"]
        hist = entry["gecmis"]
        hist[:] = [h for h in hist if h["tarih"] != used_date]
        hist.append({"tarih": used_date, "fiyat": price})
        hist.sort(key=lambda h: h["tarih"])
    # CSV'den cikarilmis (artik takip edilmeyen) fonlari raporda gostermemek icin
    # burada silmiyoruz, sadece report.py CSV'de olmayanlari "Diğer" altina koyar.
    data["son_guncelleme"] = used_date
    report.save_data(data)

    rows = report.compute_rows(data)
    # Sadece CSV'deki fonlari rapora dahil et
    rows = [r for r in rows if r["kod"] in fon_listesi]
    html = report.render_html(data, rows)
    os.makedirs(os.path.dirname(report.REPORT_FILE), exist_ok=True)
    with open(report.REPORT_FILE, "w", encoding="utf-8") as f:
        f.write(html)

    karar_html = report.render_karar_html(rows)
    with open(report.KARAR_FILE, "w", encoding="utf-8") as f:
        f.write(karar_html)

    print(f"\nRapor guncellendi ({used_date}), {len(rows)} fon:")
    for r in sorted(rows, key=lambda r: (r["sirket"], -(r["gunluk_getiri"] or -999))):
        gr = f"{r['gunluk_getiri']:.4f}%" if r["gunluk_getiri"] is not None else "—"
        print(f"  [{r['sirket']:22s}] {r['kod']:5s} {gr:>10s}  {r['fiyat']:.6f}")


if __name__ == "__main__":
    asyncio.run(main())
