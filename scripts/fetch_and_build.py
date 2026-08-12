"""
TEFAS'tan (tefas.gov.tr) fiyat verisini ceker, data/tefas_veri.json'u gunceller
ve docs/index.html raporunu yeniden uretir.

TEFAS'in yeni (2026, Next.js tabanli) sitesi, kendi ön yüzünün kullandığı
dogrudan bir JSON API sunuyor (yetkilendirme/API anahtari gerektirmez):

    POST https://www.tefas.gov.tr/api/funds/fonGnlBlgSiraliGetir

Bu script bu API'yi düz bir HTTP istegiyle (requests) çağırır — tarayıcı ya
da Playwright GEREKMEZ. Eski sürüm, TEFAS'in HTML sayfasını (fon-verileri)
Playwright ile taklit ederek kazıyordu ve bulut ortamlarında (GitHub Actions
dahil) bot korumasına (WAF) takılıp sürekli zaman aşımına uğruyordu. Bu API
o korumaya tabi değil gibi görünüyor (birden fazla bağımsız kaynakla ve canlı
testle doğrulandı — bkz. proje notları).

Otomatik/zamanlanmış çalışabilir (GitHub Actions cron) ya da elle
(Actions sekmesinden "Run workflow" ile) tetiklenebilir. Çalıştırıldığında,
sistemde kayıtlı en son tarihten bugüne en yakın iş gününe kadar olan TÜM
eksik iş günlerini tek istekte (gerekirse birkaç ~1 aylık parçaya bölünerek)
çeker ve işler.

Takip edilen fon listesi data/fon_listesi.csv dosyasından okunur — YENİ FON
EKLEMEK İÇİN sadece bu CSV'ye bir satır eklemeniz yeterlidir, kod
değiştirmenize gerek yoktur. Format:

    kod,sirket,risk
    HLL,Ziraat Portföy,1
    ...

- kod: TEFAS fon kodu (büyük harf)
- sirket: rapor sayfasında hangi başlığın altında görüneceği (serbest metin)
- risk: TEFAS'taki "Fonun Risk Değeri" (1-7), sadece bilgi amaçlı, boş bırakılabilir

Fon adı (ad) TEFAS'tan otomatik çekilir, elle girmenize gerek yoktur.

Kullanım:
  python scripts/fetch_and_build.py
"""
import csv
import os
import sys
import time
from datetime import datetime, timedelta

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import report  # noqa: E402

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FON_LISTESI_FILE = os.path.join(BASE_DIR, "data", "fon_listesi.csv")

INFO_URL = "https://www.tefas.gov.tr/api/funds/fonGnlBlgSiraliGetir"
API_HEADERS = {
    "Accept": "*/*",
    "Content-Type": "application/json",
    "Origin": "https://www.tefas.gov.tr",
    "Referer": "https://www.tefas.gov.tr/tr/fon-verileri",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36"
    ),
}
# TEFAS API'si tek istekte ~1 ay (30 gun) sinirlar; 28 gun koruyucu esik.
MAX_DAYS_PER_REQUEST = 28
# API dakikada 6 istek sinirlar; istekler arasi bu kadar bekleyerek asiliyoruz.
REQUEST_INTERVAL_SECONDS = 11


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


class TefasAPIError(RuntimeError):
    pass


def _post_with_retry(body, max_retry=5, timeout=60):
    session = requests.Session()
    last_err = None
    for attempt in range(max_retry):
        try:
            r = session.post(INFO_URL, headers=API_HEADERS, json=body, timeout=timeout)
        except (requests.ConnectionError, requests.Timeout) as e:
            last_err = e
            print(f"  Ag hatasi (deneme {attempt + 1}/{max_retry}): {e}")
            time.sleep(min(2 ** attempt, 30))
            continue

        if r.status_code == 429:
            reset = r.headers.get("ratelimit-reset")
            wait = int(reset) + 1 if (reset and reset.isdigit()) else 30
            print(f"  Rate limit asildi, {wait}sn bekleniyor...")
            time.sleep(wait)
            continue

        if r.status_code == 200 and not r.text.strip():
            print("  Bos yanit alindi, tekrar deneniyor...")
            time.sleep(15)
            continue

        r.raise_for_status()
        try:
            return r.json()
        except ValueError:
            print("  JSON parse hatasi, tekrar deneniyor...")
            time.sleep(15)
            continue

    raise TefasAPIError(f"TEFAS API {max_retry} denemeden sonra basarisiz: {last_err}")


def fetch_range(start_date, end_date):
    """start_date..end_date (dahil) araligindaki TUM YAT fonlarinin gunluk
    fiyat/ad bilgisini ceker. {fon_kodu: {tarih_str: (fiyat, ad)}} seklinde
    dondurur. Tek istekte tum fonlar (fonKodu filtresi yok) cekilir; bu hem
    daha az istek hem de "Serbest Fon" gibi ozel kategorilerdeki fonlar icin
    (ör. DCB, YPT) ayri bir yedek sorguya gerek birakmiyor.
    """
    out = {}
    cur = start_date
    first_request = True
    while cur <= end_date:
        chunk_end = min(cur + timedelta(days=MAX_DAYS_PER_REQUEST - 1), end_date)
        if not first_request:
            time.sleep(REQUEST_INTERVAL_SECONDS)
        first_request = False

        body = {
            "fonTipi": "YAT", "fonKodu": None, "aramaMetni": None, "fonTurKod": None,
            "fonGrubu": None, "sfonTurKod": None, "fonTurAciklama": None, "kurucuKod": None,
            "basTarih": cur.strftime("%Y%m%d"), "bitTarih": chunk_end.strftime("%Y%m%d"),
            "basSira": 1, "bitSira": 100000, "dil": "TR",
            "sFonTurKod": "", "fonKod": "", "fonGrup": "", "fonUnvanTip": "",
        }
        print(f"  API istegi: {cur} - {chunk_end}")
        data = _post_with_retry(body)

        err = data.get("errorMessage")
        empty_markers = ("out of bounds", "bulunamadı", "bulunamadi")
        is_empty = err and any(m in err.lower() for m in empty_markers)
        if err and not is_empty:
            raise TefasAPIError(f"TEFAS API hatasi: {err}")

        rows = data.get("resultList") or []
        print(f"    {len(rows)} kayit alindi.")
        for row in rows:
            kod = row.get("fonKodu")
            tarih = row.get("tarih")
            fiyat = row.get("fiyat")
            ad = row.get("fonUnvan")
            if kod and tarih and fiyat is not None:
                out.setdefault(kod, {})[tarih] = (float(fiyat), ad)

        cur = chunk_end + timedelta(days=1)
    return out


def main():
    """Sistemde kayıtlı en son tarihten, bugüne en yakın iş gününe kadar olan
    TÜM eksik iş günlerini TEFAS API'sinden çeker ve işler. Elle (Actions
    sekmesinden "Run workflow" ile) ya da otomatik (cron) tetiklenebilir.
    """
    fon_listesi = load_fon_listesi()
    fund_codes = set(fon_listesi.keys())
    print(f"Takip edilen fon sayisi (data/fon_listesi.csv): {len(fund_codes)}")

    data = report.load_data()
    data.setdefault("fonlar", {})

    last_known = data.get("son_guncelleme") or ""
    if not last_known:
        all_dates = [h["tarih"] for f in data["fonlar"].values() for h in f.get("gecmis", [])]
        last_known = max(all_dates) if all_dates else ""

    end_date = previous_business_day(datetime.utcnow() + timedelta(hours=3)).date()  # TR saati (UTC+3)

    if last_known:
        last_known_date = datetime.strptime(last_known, "%Y-%m-%d").date()
    else:
        last_known_date = end_date - timedelta(days=1)

    target_dates = business_days_between(last_known_date, end_date)

    if not target_dates:
        print(f"Veri zaten guncel (son tarih: {last_known or '—'}). Cekilecek yeni is gunu yok.")
        return

    print(
        f"Sistemde en son {last_known or 'hic veri yok'} tarihli veri var. "
        f"{target_dates[0].strftime('%Y-%m-%d')} ile {target_dates[-1].strftime('%Y-%m-%d')} "
        f"arasindaki {len(target_dates)} is gunu cekilecek."
    )

    try:
        fetched = fetch_range(target_dates[0], target_dates[-1])
    except TefasAPIError as e:
        print(f"\nHATA: {e}")
        print("Rapor guncellenmedi.")
        sys.exit(1)

    target_date_strs = [d.strftime("%Y-%m-%d") for d in target_dates]
    succeeded_dates = []
    empty_dates = []

    for date_str in target_date_strs:
        prices_today = {}
        for kod in fund_codes:
            entry = fetched.get(kod, {})
            if date_str in entry:
                prices_today[kod] = entry[date_str]

        if not prices_today:
            print(f"{date_str} icin veri yok (resmi tatil vb. olabilir), atlaniyor.")
            empty_dates.append(date_str)
            continue

        missing = fund_codes - set(prices_today.keys())
        if missing:
            print(f"UYARI ({date_str}): su fonlar icin fiyat bulunamadi: {sorted(missing)}")

        for kod, (price, ad) in prices_today.items():
            meta = fon_listesi.get(kod, {"sirket": "Diğer", "risk": None})
            fentry = data["fonlar"].setdefault(kod, {"ad": ad or kod, "gecmis": []})
            fentry["ad"] = ad or fentry.get("ad") or kod
            fentry["sirket"] = meta["sirket"]
            fentry["risk"] = meta["risk"]
            hist = fentry["gecmis"]
            hist[:] = [h for h in hist if h["tarih"] != date_str]
            hist.append({"tarih": date_str, "fiyat": price})
            hist.sort(key=lambda h: h["tarih"])

        data["son_guncelleme"] = date_str
        report.save_data(data)  # her basarili gunden sonra kaydet, kismi ilerleme kaybolmasin
        succeeded_dates.append(date_str)

    if not succeeded_dates:
        print("\nHicbir gun icin veri bulunamadi (hepsi tatil olabilir, ya da bir sorun var). Rapor guncellenmedi.")
        return

    print(f"\nBasariyla islenen gunler ({len(succeeded_dates)}): {succeeded_dates}")
    if empty_dates:
        print(f"Veri bulunamayan gunler (muhtemelen tatil) ({len(empty_dates)}): {empty_dates}")

    rows = report.compute_rows(data)
    rows = [r for r in rows if r["kod"] in fund_codes]
    report.build()

    print(f"\nRapor guncellendi (son tarih: {data['son_guncelleme']}), {len(rows)} fon:")
    for r in sorted(rows, key=lambda r: (r["sirket"], -(r["gunluk_getiri"] or -999))):
        gr = f"{r['gunluk_getiri']:.4f}%" if r["gunluk_getiri"] is not None else "—"
        print(f"  [{r['sirket']:22s}] {r['kod']:5s} {gr:>10s}  {r['fiyat']:.6f}")


if __name__ == "__main__":
    main()
