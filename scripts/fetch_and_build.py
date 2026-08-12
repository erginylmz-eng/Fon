"""
TEFAS'tan (tefas.gov.tr) fiyat verisini ceker, data/tefas_veri.json'u gunceller
ve docs/index.html raporunu yeniden uretir.

BU SCRIPT OTOMATIK/ZAMANLANMIS CALISMAZ — sadece elle tetiklendiginde calisir
(GitHub reposunda Actions sekmesinden "Run workflow" ile, ya da rapor
sayfasindaki "Simdi Cek" butonuyla). Calistirildiginda, sistemde kayitli en
son tarihten bugune en yakin is gunune kadar olan TUM eksik is gunlerini
tek tek (gun gun) ceker ve isler — ornegin sistemde en son 9 Nisan verisi
varken 13 Nisan'da calistirilirsa, 10-11-12-13 Nisan gunlerinin hepsini
sirayla ceker (haftasonlari otomatik atlanir).

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
(GitHub Actions dahil) bazen bu korumaya takilabilir. Bu durumda script o gunu
atlayip diger gunlere devam eder; hicbir gun basarili olmazsa mevcut
veri/rapor DEGISTIRILMEZ.

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
                     wait_until="networkidle", timeout=60000)
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

    NOT: TEFAS'in bot korumasi (WAF) bulut IP'lerini (GitHub Actions dahil)
    bazen yavaslatiyor/engelliyor; bu da sayfanin "main" elementinin zamaninda
    yuklenmemesine (Playwright TimeoutError) yol acabiliyor. Bu fonksiyon bu
    durumu bir kez tekrar deneyip yine de basarisiz olursa anlasilir bir
    RuntimeError'a ceviriyor, boylece main() temiz bir hata mesajiyla cikiyor
    ve mevcut veri/rapor bozulmadan kaliyor.
    """
    from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

    url = (
        f"https://www.tefas.gov.tr/tr/fon-verileri?fundType=YAT&sfonTurKod=107"
        f"&startDate={date_str}&endDate={date_str}"
    )
    async with async_playwright() as p:
        # "Gizli mod": TEFAS'in korumasi, TEFAS.gov.tr'nin normal bir tarayicidan
        # mi yoksa Playwright/Selenium gibi bir otomasyon aracindan mi geldigini
        # ayirt edebiliyor gibi gorunuyor (gercek tarayicidan sorunsuz yukleniyor,
        # Playwright'tan konumdan bagimsiz olarak zaman asimina ugruyor). Bu
        # ayarlar en yaygin otomasyon izlerini (navigator.webdriver bayragi vb.)
        # gizlemeye calisir.
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-features=IsolateOrigins,site-per-process",
            ],
        )
        context = await browser.new_context(
            user_agent=USER_AGENT,
            locale="tr-TR",
            viewport={"width": 1366, "height": 768},
        )
        await context.add_init_script(
            """
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            window.chrome = window.chrome || { runtime: {} };
            Object.defineProperty(navigator, 'languages', { get: () => ['tr-TR', 'tr', 'en-US', 'en'] });
            Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications' ?
                    Promise.resolve({ state: Notification.permission }) :
                    originalQuery(parameters)
            );
            """
        )
        page = await context.new_page()
        page.set_default_timeout(60000)
        try:
            await page.goto(url, wait_until="networkidle", timeout=60000)
            await page.wait_for_timeout(3000)

            body_text = await page.inner_text("body")
            if "Request Rejected" in body_text:
                raise RuntimeError("TEFAS bot korumasi (WAF) istegi reddetti (Request Rejected).")
            if "sonuç bulunamadı" in body_text or "eşleşen fon verisi bulunamadı" in body_text:
                return None  # o gun veri yok (tatil vb.)

            found = {}
            for _ in range(6):  # en fazla 6 sayfa gez (81+ fon icin yeterli)
                try:
                    main_text = await page.inner_text("main", timeout=60000)
                except PlaywrightTimeoutError:
                    # Sayfa gec yuklenmis olabilir, bir kez daha dene
                    await page.wait_for_timeout(3000)
                    main_text = await page.inner_text("main", timeout=60000)
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
                except (RuntimeError, PlaywrightTimeoutError):
                    break  # WAF devreye girdi veya zaman asimi, daha fazla denemeyelim
                if price is not None:
                    found[kod] = (price, name or kod)
                await page.wait_for_timeout(2500)

            return found
        except PlaywrightTimeoutError as e:
            raise RuntimeError(
                "TEFAS sayfasi zaman asimina ugradi (60sn, bir tekrar denemesine ragmen) - "
                "TEFAS'in bot korumasi (WAF) GitHub Actions bulut IP'sini engelliyor olabilir. "
                "Bu genelde gecici bir durumdur, bir sonraki otomatik calistirmada duzelebilir. "
                f"(Teknik detay: {e.__class__.__name__})"
            )
        finally:
            await browser.close()


async def fetch_with_retries(date_str, fund_codes, max_attempts=3, delay_seconds=25):
    """fetch_prices_for_date'i, TEFAS'in bot korumasi/zaman asimi (RuntimeError)
    durumunda, her defasinda TAMAMEN YENI bir tarayici oturumuyla birden fazla
    kez dener. Denemeler arasinda bekleme, gecici WAF engellemelerinin/agir
    yuklerin gecmesine firsat tanir. Tum denemeler basarisiz olursa son hatayi
    yeniden yukseltir.
    """
    last_err = None
    for attempt in range(1, max_attempts + 1):
        try:
            return await fetch_prices_for_date(date_str, fund_codes)
        except RuntimeError as e:
            last_err = e
            print(f"  Deneme {attempt}/{max_attempts} basarisiz: {e}")
            if attempt < max_attempts:
                print(f"  {delay_seconds} saniye beklenip yeni bir tarayici oturumuyla tekrar denenecek...")
                await asyncio.sleep(delay_seconds)
    raise last_err


def business_days_between(start_exclusive, end_inclusive):
    """start_exclusive gununden SONRAKI gunden baslayarak end_inclusive'a kadar
    (o dahil) tum hafta ici gunleri (Pzt-Cuma), artan sirada dondurur."""
    days = []
    d = start_exclusive + timedelta(days=1)
    while d <= end_inclusive:
        if d.weekday() < 5:
            days.append(d)
        d += timedelta(days=1)
    return days


async def main():
    """Sistemde kayitli en son tarihten, bugune en yakin is gunune kadar olan
    TUM eksik is gunlerini tek tek (gun gun) ceker ve isler. Otomatik/zamanlanmis
    calistirma yoktur — bu script sadece elle (Actions sekmesinden "Run workflow"
    ile ya da rapor sayfasindaki "Simdi Cek" butonuyla) tetiklendiginde calisir.
    Bir gun basarisiz olsa bile diger gunlerin denenmesine devam edilir; basarili
    olan gunler her adimda kaydedilir, boylece kismi ilerleme kaybolmaz.
    """
    fon_listesi = load_fon_listesi()
    fund_codes = list(fon_listesi.keys())
    print(f"Takip edilen fon sayisi (data/fon_listesi.csv): {len(fund_codes)}")

    data = report.load_data()
    data.setdefault("fonlar", {})

    # Sistemde en son hangi tarihe kadar veri var?
    last_known = data.get("son_guncelleme") or ""
    if not last_known:
        all_dates = [h["tarih"] for f in data["fonlar"].values() for h in f.get("gecmis", [])]
        last_known = max(all_dates) if all_dates else ""

    end_date = previous_business_day(datetime.utcnow() + timedelta(hours=3)).date()  # TR saati (UTC+3)

    if last_known:
        last_known_date = datetime.strptime(last_known, "%Y-%m-%d").date()
    else:
        # Sistemde hic veri yoksa, sadece en son is gununu cek (baslangic noktasi olsun)
        last_known_date = end_date - timedelta(days=1)

    target_dates = business_days_between(last_known_date, end_date)

    if not target_dates:
        print(f"Veri zaten guncel (son tarih: {last_known or '—'}). Cekilecek yeni is gunu yok.")
        return

    print(
        f"Sistemde en son {last_known or 'hic veri yok'} tarihli veri var. "
        f"{target_dates[0].strftime('%Y-%m-%d')} ile {target_dates[-1].strftime('%Y-%m-%d')} "
        f"arasindaki {len(target_dates)} is gunu tek tek cekilecek."
    )

    succeeded_dates = []
    failed_dates = []

    for d in target_dates:
        date_str = d.strftime("%Y-%m-%d")
        print(f"\nDeneniyor: {date_str}")
        try:
            r = await fetch_with_retries(date_str, fund_codes, max_attempts=3, delay_seconds=25)
        except RuntimeError as e:
            print(f"HATA ({date_str}): {e}")
            failed_dates.append(date_str)
            continue  # bu gunu atla, bir sonraki gune devam et

        if not r:
            print(f"{date_str} icin veri yok (resmi tatil vb. olabilir), atlaniyor.")
            continue

        if len(r) < len(fund_codes) * 0.8:  # en az %80'i bulunduysa yeterli say
            print(f"{date_str} icin yeterli veri bulunamadi ({len(r)}/{len(fund_codes)}), atlaniyor.")
            failed_dates.append(date_str)
            continue

        missing = set(fund_codes) - set(r.keys())
        if missing:
            print(f"UYARI ({date_str}): su fonlar icin fiyat bulunamadi: {sorted(missing)}")

        # data/tefas_veri.json'u guncelle: fiyat + ad (TEFAS'tan) + sirket/risk (CSV'den)
        for kod, (price, name) in r.items():
            meta = fon_listesi.get(kod, {"sirket": "Diğer", "risk": None})
            entry = data["fonlar"].setdefault(kod, {"ad": name, "gecmis": []})
            entry["ad"] = name
            entry["sirket"] = meta["sirket"]
            entry["risk"] = meta["risk"]
            hist = entry["gecmis"]
            hist[:] = [h for h in hist if h["tarih"] != date_str]
            hist.append({"tarih": date_str, "fiyat": price})
            hist.sort(key=lambda h: h["tarih"])
        # CSV'den cikarilmis (artik takip edilmeyen) fonlari raporda gostermemek icin
        # burada silmiyoruz, sadece report.py CSV'de olmayanlari "Diğer" altina koyar.
        data["son_guncelleme"] = date_str
        report.save_data(data)  # her basarili gunden sonra kaydet, kismi ilerleme kaybolmasin
        succeeded_dates.append(date_str)

    if not succeeded_dates:
        print("\nHicbir gun icin veri cekilemedi. Rapor guncellenmedi.")
        sys.exit(1)

    print(f"\nBasariyla cekilen gunler ({len(succeeded_dates)}): {succeeded_dates}")
    if failed_dates:
        print(
            f"Cekilemeyen gunler ({len(failed_dates)}): {failed_dates} — "
            "bir sonraki calistirmada tekrar denenecek."
        )

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

    karsilastir_html = report.render_karsilastir_html(rows)
    with open(report.KARSILASTIR_FILE, "w", encoding="utf-8") as f:
        f.write(karsilastir_html)

    print(f"\nRapor guncellendi (son tarih: {data['son_guncelleme']}), {len(rows)} fon:")
    for r in sorted(rows, key=lambda r: (r["sirket"], -(r["gunluk_getiri"] or -999))):
        gr = f"{r['gunluk_getiri']:.4f}%" if r["gunluk_getiri"] is not None else "—"
        print(f"  [{r['sirket']:22s}] {r['kod']:5s} {gr:>10s}  {r['fiyat']:.6f}")


if __name__ == "__main__":
    asyncio.run(main())
