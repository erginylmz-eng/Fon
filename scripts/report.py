"""
Ortak veri/rapor mantığı: JSON veri dosyasını okur/günceller ve firma bazlı
HTML raporunu üretir. fetch_and_build.py tarafından kullanılır.
"""
import json
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_FILE = os.path.join(BASE_DIR, "data", "tefas_veri.json")
REPORT_FILE = os.path.join(BASE_DIR, "docs", "index.html")
KARAR_FILE = os.path.join(BASE_DIR, "docs", "karar.html")
KARSILASTIR_FILE = os.path.join(BASE_DIR, "docs", "karsilastir.html")
FON_DETAY_FILE = os.path.join(BASE_DIR, "docs", "fon.html")
DISAAKTAR_FILE = os.path.join(BASE_DIR, "docs", "disaaktar.html")
VALOR_FILE = os.path.join(BASE_DIR, "data", "fon_valor.csv")


def load_fon_valor():
    """data/fon_valor.csv -> {kod: {platform, alis_valor, satis_valor}}
    TEFAS'ta işlem görüp görmediği ve alış/satış valörü (T0/T1/T2) bilgisi.
    Elle güncellenen bir referans dosyasıdır (fiyat gibi her gün değişmez).
    """
    import csv
    out = {}
    if not os.path.exists(VALOR_FILE):
        return out
    with open(VALOR_FILE, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            kod = (row.get("kod") or "").strip().upper()
            if not kod:
                continue
            out[kod] = {
                "platform": (row.get("platform") or "").strip(),
                "alis_valor": (row.get("alis_valor") or "-").strip(),
                "satis_valor": (row.get("satis_valor") or "-").strip(),
                "kaynak": (row.get("kaynak") or "").strip(),
                "url": (row.get("url") or "").strip(),
            }
    return out

SIRKET_SIRASI = [
    "Ziraat Portföy", "İş Portföy", "Ak Portföy", "Garanti BBVA Portföy",
    "Yapı Kredi Portföy", "Deniz Portföy", "QNB Finans Portföy", "TEB Portföy",
]


def load_data():
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def add_day(data, date_str, prices):
    for code, fund in data["fonlar"].items():
        if code not in prices:
            continue
        hist = fund["gecmis"]
        hist[:] = [h for h in hist if h["tarih"] != date_str]
        hist.append({"tarih": date_str, "fiyat": float(prices[code])})
        hist.sort(key=lambda h: h["tarih"])
    data["son_guncelleme"] = date_str
    return data


def compute_rows(data):
    fon_valor = load_fon_valor()
    rows = []
    for code, fund in sorted(data["fonlar"].items()):
        hist = fund["gecmis"]
        if not hist:
            continue
        last = hist[-1]
        prev = hist[-2] if len(hist) >= 2 else None
        daily_return = None
        if prev and prev["fiyat"] > 0:
            daily_return = (last["fiyat"] - prev["fiyat"]) / prev["fiyat"] * 100
        recent = hist[-30:]
        valor = fon_valor.get(code, {})
        rows.append({
            "kod": code,
            "ad": fund["ad"],
            "sirket": fund.get("sirket", "Diğer"),
            "risk": fund.get("risk"),
            "tarih": last["tarih"],
            "fiyat": last["fiyat"],
            "gunluk_getiri": daily_return,
            "seri": [h["fiyat"] for h in recent],
            "hist": [[h["tarih"], h["fiyat"]] for h in hist],
            "platform": valor.get("platform", ""),
            "alis_valor": valor.get("alis_valor", "-"),
            "satis_valor": valor.get("satis_valor", "-"),
            "valor_kaynak": valor.get("kaynak", ""),
            "valor_url": valor.get("url", ""),
        })
    return rows


def fmt_pct(v):
    if v is None:
        return '<span class="muted">—</span>'
    cls = "pos" if v >= 0 else "neg"
    sign = "+" if v >= 0 else ""
    return f'<span class="{cls}">{sign}{v:.4f}%</span>'


def fmt_price(v):
    return f"{v:,.6f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _slug(s):
    return s.replace(" ", "-")


def render_html(data, rows):
    son_tarih = data.get("son_guncelleme") or ""
    if not son_tarih and rows:
        # Guvenlik agi: ust seviye alan bos/None kalmis olsa bile (ör. gecmis
        # veri birlestirme sirasinda unutulmus olabilir), fonlarin kendi
        # gecmis kayitlarindan en guncel tarihi turet.
        son_tarih = max((r["tarih"] for r in rows if r.get("tarih")), default="")

    by_sirket = {}
    for r in rows:
        by_sirket.setdefault(r["sirket"], []).append(r)

    ordered_sirketler = [s for s in SIRKET_SIRASI if s in by_sirket]
    ordered_sirketler += [s for s in by_sirket if s not in SIRKET_SIRASI]

    sections_html = ""
    for i, sirket in enumerate(ordered_sirketler):
        n = len(by_sirket[sirket])
        open_cls = " open" if i == 0 else ""
        sections_html += f"""
  <div class="card accordion{open_cls}" id="{_slug(sirket)}">
    <div class="acc-header">
      <h2>{sirket} <span class="muted" id="meta-{_slug(sirket)}">· {n} fon</span></h2>
      <span class="acc-arrow">&#9662;</span>
    </div>
    <div class="acc-body">
      <table>
        <thead>
          <tr>
            <th>Kod</th>
            <th>Fon Adı</th>
            <th style="text-align:right">Risk</th>
            <th style="text-align:right">Fiyat (Birim Pay)</th>
            <th style="text-align:right" id="col-{_slug(sirket)}">Günlük Getiri</th>
            <th style="text-align:right">Grafik</th>
            <th style="text-align:right">Valör (Alış/Satış)</th>
          </tr>
        </thead>
        <tbody id="tbody-{_slug(sirket)}"></tbody>
      </table>
    </div>
  </div>"""

    n_funds = len(rows)
    n_sirket = len(ordered_sirketler)

    funds_json = json.dumps([
        {
            "kod": r["kod"], "ad": r["ad"], "sirket": r["sirket"], "risk": r["risk"],
            "hist": r["hist"], "platform": r.get("platform", ""),
            "alisValor": r.get("alis_valor", "-"), "satisValor": r.get("satis_valor", "-"),
            "valorKaynak": r.get("valor_kaynak", ""), "valorUrl": r.get("valor_url", ""),
        }
        for r in rows
    ], ensure_ascii=False)
    sirket_order_json = json.dumps(ordered_sirketler, ensure_ascii=False)

    html = f"""<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>TEFAS Para Piyasası Fonları (Firma Bazlı) - Günlük Getiri Raporu</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.0/chart.umd.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/chartjs-plugin-datalabels/2.2.0/chartjs-plugin-datalabels.min.js"></script>
<style>
  :root {{
    --bg: #f7f5fb; --card: #ffffff; --border: #e3dff2; --text: #443f5e;
    --muted: #8f88a3; --pos: #3f9973; --neg: #c85a72; --accent: #5b7fd1; --warn: #c78f4a;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; padding: 32px; background: var(--bg); color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif;
  }}
  h1 {{ font-size: 22px; margin: 0 0 4px 0; }}
  .subtitle {{ color: var(--muted); font-size: 13px; margin-bottom: 24px; }}
  .summary {{ display: flex; gap: 16px; margin-bottom: 24px; flex-wrap: wrap; }}
  .stat {{
    background: var(--card); border: 1px solid var(--border); border-radius: 10px;
    padding: 14px 18px; min-width: 150px; box-shadow: 0 1px 3px rgba(68,63,94,0.06);
  }}
  .stat .label {{ color: var(--muted); font-size: 12px; margin-bottom: 6px; }}
  .stat .value {{ font-size: 20px; font-weight: 600; }}
  .card {{
    background: var(--card); border: 1px solid var(--border); border-radius: 12px;
    padding: 20px; margin-bottom: 20px; box-shadow: 0 1px 3px rgba(68,63,94,0.06);
  }}
  .card h2 {{ font-size: 15px; margin: 0 0 16px 0; color: var(--text); font-weight: 700; }}
  .card h2 .muted {{ color: var(--muted); font-weight: 500; font-size: 13px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  th {{
    text-align: left; padding: 10px 12px; color: var(--muted); font-weight: 600;
    border-bottom: 1px solid var(--border); font-size: 11px; text-transform: uppercase; letter-spacing: .03em;
  }}
  td {{ padding: 10px 12px; border-bottom: 1px solid var(--border); vertical-align: middle; }}
  tr:hover td {{ background: rgba(91,127,209,0.05); }}
  .code {{ font-weight: 700; color: var(--accent); }}
  .code-link {{ font-weight: 700; color: var(--accent); text-decoration: none; }}
  .code-link:hover {{ text-decoration: underline; }}
  #returnChart {{ cursor: pointer; }}
  .name {{ color: var(--text); }}
  .num {{ text-align: right; font-variant-numeric: tabular-nums; }}
  .pos {{ color: var(--pos); font-weight: 600; }}
  .neg {{ color: var(--neg); font-weight: 600; }}
  .muted {{ color: var(--muted); }}
  .spark {{ text-align: right; }}
  footer {{ color: var(--muted); font-size: 12px; margin-top: 24px; }}
  .chart-wrap {{ height: 360px; }}
  .toc {{ display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 24px; }}
  .toc a {{
    padding: 6px 12px; border-radius: 8px; text-decoration: none; font-size: 12px; font-weight: 600;
    border: 1px solid var(--border); color: var(--muted);
  }}
  .toc a:hover {{ color: var(--text); border-color: var(--accent); }}
  .legend {{ display: flex; gap: 18px; margin-bottom: 12px; font-size: 12px; color: var(--muted); }}
  .legend span {{ display: inline-flex; align-items: center; gap: 6px; }}
  .swatch {{ width: 10px; height: 10px; border-radius: 3px; display: inline-block; }}
  .select-row {{ display: flex; gap: 12px; flex-wrap: wrap; }}
  .select-col {{ flex: 1; min-width: 200px; }}
  .select-col label {{ display: block; font-size: 12px; color: var(--muted); margin-bottom: 6px; }}
  select, input[type="date"] {{
    width: 100%; background: var(--bg); color: var(--text); border: 1px solid var(--border);
    border-radius: 8px; padding: 9px 12px; font-size: 13px; font-family: inherit;
  }}
  select[multiple] {{ height: auto; }}
  .btn {{
    background: var(--accent); color: #fff; border: none; border-radius: 8px;
    padding: 9px 16px; font-size: 13px; font-weight: 600; cursor: pointer; font-family: inherit;
  }}
  .btn:hover {{ opacity: .9; }}
  .btn.secondary {{ background: transparent; border: 1px solid var(--border); color: var(--text); }}
  .btn-row {{ display: flex; gap: 8px; margin-top: 10px; flex-wrap: wrap; }}
  .help-text {{ font-size: 12px; color: var(--muted); margin-top: 10px; line-height: 1.6; }}
  .help-text a {{ color: var(--accent); }}
  .update-status {{
    display: inline-flex; align-items: center; gap: 8px; padding: 9px 16px; border-radius: 8px;
    font-size: 13px; font-weight: 600; margin-bottom: 20px; border: 1px solid var(--border);
  }}
  .update-status .dot {{ width: 8px; height: 8px; border-radius: 50%; background: currentColor; display: inline-block; }}
  .update-status.fresh {{ background: rgba(63,153,115,0.12); border-color: var(--pos); color: var(--pos); }}
  .update-status.stale {{ background: rgba(199,143,74,0.14); border-color: var(--warn); color: var(--warn); }}
  .update-status.old {{ background: rgba(200,90,114,0.12); border-color: var(--neg); color: var(--neg); }}
  .period-row {{ display: flex; gap: 8px; margin-bottom: 20px; flex-wrap: wrap; }}
  .period-btn {{
    padding: 9px 18px; border-radius: 8px; border: 1px solid var(--border); background: transparent;
    color: var(--muted); cursor: pointer; font-size: 13px; font-weight: 600; font-family: inherit;
  }}
  .period-btn.active {{ background: var(--accent); color: #fff; border-color: var(--accent); }}
  .period-btn:hover:not(.active) {{ color: var(--text); border-color: var(--accent); }}
  .acc-header {{ display: flex; align-items: center; justify-content: space-between; cursor: pointer; }}
  .acc-header h2 {{ margin: 0; }}
  .acc-arrow {{ color: var(--muted); font-size: 12px; transition: transform .2s; margin-left: 12px; }}
  .card.accordion .acc-body {{ display: none; margin-top: 16px; }}
  .card.accordion.open .acc-body {{ display: block; }}
  .card.accordion.open .acc-arrow {{ transform: rotate(180deg); color: var(--accent); }}
</style>
</head>
<body>
  <h1>TEFAS Para Piyasası Fonları — Firma Bazlı Günlük Getiri Raporu</h1>
  <div class="subtitle">{n_sirket} kurucu firma · {n_funds} fon (risk 1/7 veya 2/7) · Son güncelleme: {son_tarih}</div>

  <div id="updateStatus" class="update-status"><span class="dot"></span> Veri durumu kontrol ediliyor…</div>

  <div style="margin-bottom:20px; display:flex; gap:10px; flex-wrap:wrap;">
    <a href="karar.html" class="btn" style="text-decoration:none; display:inline-block;">Yatırım Önerisi (AI Analiz)</a>
    <a href="karsilastir.html" class="btn" style="text-decoration:none; display:inline-block; background:transparent; border:1px solid var(--border); color:var(--text);">3 Fon Karşılaştır</a>
    <a href="disaaktar.html" class="btn" style="text-decoration:none; display:inline-block; background:transparent; border:1px solid var(--border); color:var(--text);">Veri Dışa Aktar (Excel)</a>
  </div>

  <div class="toc">
    {''.join(f'<a href="#{s.replace(" ", "-")}">{s}</a>' for s in ordered_sirketler)}
  </div>

  <div class="period-row">
    <button class="period-btn" data-period="gunluk">Günlük</button>
    <button class="period-btn" data-period="haftalik">Haftalık</button>
    <button class="period-btn" data-period="aylik">Aylık</button>
    <button class="period-btn" data-period="yillik">Yıllık</button>
  </div>

  <div class="summary">
    <div class="stat"><div class="label">Firma Sayısı</div><div class="value">{n_sirket}</div></div>
    <div class="stat"><div class="label">Toplam Fon</div><div class="value">{n_funds}</div></div>
    <div class="stat"><div class="label" id="statAvgLabel">Ortalama Günlük Getiri</div><div class="value" id="statAvg">—</div></div>
    <div class="stat"><div class="label">En Yüksek Getiri</div><div class="value" id="statTop">—</div></div>
  </div>

  <div class="card">
    <h2 id="chartTitle">Tüm Fonlar — Günlük Getiri Karşılaştırması</h2>
    <div class="legend">
      <span><span class="swatch" style="background:#5b7fd1"></span>Risk 1/7</span>
      <span><span class="swatch" style="background:#c78f4a"></span>Risk 2/7</span>
    </div>
    <div class="chart-wrap"><canvas id="returnChart"></canvas></div>
  </div>

  {sections_html}

  <footer>
    Veri kaynağı: <a href="https://www.tefas.gov.tr/tr/fon-verileri" style="color:var(--accent)">TEFAS Fon Verileri</a>.
    Bu rapor bilgilendirme amaçlıdır, yatırım tavsiyesi değildir. Veri hafta içi her sabah
    otomatik olarak güncellenir.
  </footer>

<script>
  const SON_TARIH = '{son_tarih}';

  function previousBusinessDay(d) {{
    const dt = new Date(d.getTime());
    dt.setDate(dt.getDate() - 1);
    while (dt.getDay() === 0 || dt.getDay() === 6) dt.setDate(dt.getDate() - 1);
    return dt;
  }}
  function toDateStr(d) {{
    return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
  }}

  (function checkUpdateStatus() {{
    const el = document.getElementById('updateStatus');
    if (!SON_TARIH) {{
      el.className = 'update-status stale';
      el.innerHTML = '<span class="dot"></span> Henüz veri çekilmemiş.';
      return;
    }}
    const now = new Date();
    const expected = previousBusinessDay(now);
    const expectedStr = toDateStr(expected);
    let cls, msg;
    if (SON_TARIH >= expectedStr) {{
      cls = 'fresh';
      msg = `Veri güncel — son güncelleme ${{SON_TARIH}}`;
    }} else {{
      cls = 'stale';
      // Eksik is gunu sayisini, fetch_and_build.py'deki business_days_between
      // ile ayni mantikla say (haftasonlari haric).
      let missing = 0;
      let d = new Date(SON_TARIH + 'T00:00:00');
      d.setDate(d.getDate() + 1);
      const end = new Date(expectedStr + 'T00:00:00');
      while (d <= end) {{
        if (d.getDay() !== 0 && d.getDay() !== 6) missing++;
        d.setDate(d.getDate() + 1);
      }}
      const gunIfadesi = missing === 1 ? '1 iş günü' : `${{missing}} iş günü`;
      msg = `Son güncelleme ${{SON_TARIH}} (${{gunIfadesi}} eksik) — otomatik güncelleme birkaç saat içinde beklenmelidir`;
    }}
    el.className = 'update-status ' + cls;
    el.innerHTML = `<span class="dot"></span> ${{msg}}`;
  }})();

  // ---- Dönem bazlı (Günlük/Haftalık/Aylık/Yıllık) dinamik rapor ----
  const FUNDS = {funds_json};
  const SIRKET_ORDER = {sirket_order_json};

  const PERIOD_DAYS = {{ gunluk: 1, haftalik: 7, aylik: 30, yillik: 365 }};
  const PERIOD_LABELS = {{ gunluk: 'Günlük', haftalik: 'Haftalık', aylik: 'Aylık', yillik: 'Yıllık' }};
  const riskColor = {{ 1: 'rgba(91,127,209,0.85)', 2: 'rgba(199,143,74,0.85)' }};
  const riskColorHover = {{ 1: 'rgba(91,127,209,1)', 2: 'rgba(199,143,74,1)' }};
  let currentPeriod = 'gunluk';
  let sparkCharts = {{}};

  function slug(s) {{ return s.split(' ').join('-'); }}
  function parseDate(s) {{ return new Date(s + 'T00:00:00').getTime(); }}

  function computeForPeriod(hist, days) {{
    if (!hist || hist.length === 0) return {{ ret: null, fiyat: null, series: [] }};
    const last = hist[hist.length - 1];
    if (hist.length === 1) return {{ ret: null, fiyat: last[1], series: [last[1]] }};
    const targetTime = parseDate(last[0]) - days * 86400000;
    let baseline = hist[0];
    for (let i = hist.length - 1; i >= 0; i--) {{
      if (parseDate(hist[i][0]) <= targetTime) {{ baseline = hist[i]; break; }}
    }}
    let ret = null;
    if (baseline[1] > 0 && baseline[0] !== last[0]) {{
      ret = (last[1] - baseline[1]) / baseline[1] * 100;
    }}
    let series = hist.filter(h => parseDate(h[0]) >= parseDate(baseline[0])).map(h => h[1]);
    if (series.length < 2) series = hist.slice(-2).map(h => h[1]);
    return {{ ret, fiyat: last[1], series }};
  }}

  function fmtPct(v) {{
    if (v === null || v === undefined || isNaN(v)) return '<span class="muted">—</span>';
    const cls = v >= 0 ? 'pos' : 'neg';
    const sign = v >= 0 ? '+' : '';
    return `<span class="${{cls}}">${{sign}}${{v.toFixed(4)}}%</span>`;
  }}
  function fmtPrice(v) {{
    return v.toLocaleString('tr-TR', {{ minimumFractionDigits: 6, maximumFractionDigits: 6 }});
  }}
  function sortByRet(a, b) {{
    if (a.ret === null && b.ret === null) return 0;
    if (a.ret === null) return 1;
    if (b.ret === null) return -1;
    return b.ret - a.ret;
  }}

  if (window.ChartDataLabels) Chart.register(window.ChartDataLabels);

  const mainChart = new Chart(document.getElementById('returnChart'), {{
    type: 'bar',
    data: {{ labels: [], datasets: [{{ label: 'Getiri (%)', data: [], backgroundColor: [], hoverBackgroundColor: [], borderRadius: 4, barPercentage: 0.7, categoryPercentage: 0.85 }}] }},
    options: {{
      indexAxis: 'y',
      responsive: true, maintainAspectRatio: false,
      layout: {{ padding: {{ right: 46 }} }},
      scales: {{
        x: {{ ticks: {{ color: '#8f88a3', font: {{ size: 10 }}, callback: (v) => (v >= 0 ? '+' : '') + v.toFixed(3) + '%' }}, grid: {{ color: '#e3dff2' }} }},
        y: {{ ticks: {{ color: '#8f88a3', autoSkip: false, font: {{ size: 10 }} }}, grid: {{ display: false }} }}
      }},
      plugins: {{
        legend: {{ display: false }},
        tooltip: {{ callbacks: {{ afterLabel: (item) => {{
          const risks = item.chart.__risks || [];
          const risk = risks[item.dataIndex] ? ('Risk ' + risks[item.dataIndex] + '/7') : '';
          return [risk, 'Tarihsel grafiği görmek için tıklayın'].filter(Boolean);
        }} }} }},
        datalabels: {{
          anchor: 'end', align: 'end', color: '#443f5e', font: {{ size: 10, weight: '600' }},
          formatter: (v) => (v >= 0 ? '+' : '') + v.toFixed(4) + '%'
        }}
      }},
      onClick: (evt, elements, chart) => {{
        if (!elements.length) return;
        const kod = (chart.__kods || [])[elements[0].index];
        if (kod) window.location.href = 'fon.html?kod=' + encodeURIComponent(kod);
      }},
      onHover: (evt, elements, chart) => {{
        evt.native.target.style.cursor = elements.length ? 'pointer' : 'default';
      }}
    }}
  }});

  function buildSparkline(canvas, series) {{
    if (series.length < 2) return;
    const min = Math.min(...series), max = Math.max(...series);
    sparkCharts[canvas.dataset.kod] = new Chart(canvas, {{
      type: 'line',
      data: {{ labels: series.map((_, i) => i), datasets: [{{ data: series, borderColor: '#5b7fd1', borderWidth: 1.5, pointRadius: 0, tension: 0.3, fill: false }}] }},
      options: {{
        responsive: false, maintainAspectRatio: false,
        scales: {{ x: {{ display: false }}, y: {{ display: false, min, max }} }},
        plugins: {{ legend: {{ display: false }}, tooltip: {{ enabled: false }} }},
        elements: {{ point: {{ radius: 0 }} }}
      }}
    }});
  }}

  function render() {{
    const days = PERIOD_DAYS[currentPeriod];
    const label = PERIOD_LABELS[currentPeriod];

    Object.values(sparkCharts).forEach(c => c.destroy());
    sparkCharts = {{}};

    document.querySelectorAll('.period-btn').forEach(b => b.classList.toggle('active', b.dataset.period === currentPeriod));

    const computed = FUNDS.map(f => {{
      const {{ ret, fiyat, series }} = computeForPeriod(f.hist, days);
      return {{ kod: f.kod, ad: f.ad, sirket: f.sirket, risk: f.risk, ret, fiyat, series, platform: f.platform, alisValor: f.alisValor, satisValor: f.satisValor, valorKaynak: f.valorKaynak, valorUrl: f.valorUrl }};
    }});

    const withRet = computed.filter(f => f.ret !== null);
    const avg = withRet.length ? withRet.reduce((a, b) => a + b.ret, 0) / withRet.length : null;
    const sortedAll = computed.slice().sort(sortByRet);
    const top = sortedAll.length && sortedAll[0].ret !== null ? sortedAll[0] : null;

    document.getElementById('statAvgLabel').textContent = 'Ortalama ' + label + ' Getiri';
    document.getElementById('statAvg').textContent = avg !== null ? (avg >= 0 ? '+' : '') + avg.toFixed(4) + '%' : '—';
    document.getElementById('statTop').textContent = top ? (top.kod + ' · ' + top.sirket) : '—';
    document.getElementById('chartTitle').textContent = 'Tüm Fonlar — ' + label + ' Getiri Karşılaştırması';

    const chartFunds = sortedAll.filter(f => f.ret !== null);
    mainChart.data.labels = chartFunds.map(f => `${{f.kod}} — ${{f.sirket}}`);
    const retData = chartFunds.map(f => Math.round(f.ret * 10000) / 10000);
    mainChart.data.datasets[0].data = retData;
    mainChart.data.datasets[0].label = label + ' Getiri (%)';
    const risks = chartFunds.map(f => f.risk);
    mainChart.data.datasets[0].backgroundColor = risks.map(r => riskColor[r] || 'rgba(143,136,163,0.7)');
    mainChart.data.datasets[0].hoverBackgroundColor = risks.map(r => riskColorHover[r] || 'rgba(143,136,163,0.9)');
    mainChart.__risks = risks;
    mainChart.__kods = chartFunds.map(f => f.kod);

    // Degerler birbirine cok yakin oldugundan (ör. gunluk getiriler), ekseni
    // veri araligina gore yakinlastir ki farklar gozle gorulebilsin.
    if (retData.length) {{
      const minRet = Math.min(...retData), maxRet = Math.max(...retData);
      const pad = Math.max((maxRet - minRet) * 0.18, 0.003);
      mainChart.options.scales.x.min = minRet - pad;
      mainChart.options.scales.x.max = maxRet + pad;
    }}
    // Her fon icin okunabilir bir satir yuksekligi ayir (yatay bar grafik).
    document.getElementById('returnChart').parentElement.style.height =
      Math.max(360, chartFunds.length * 22 + 40) + 'px';
    mainChart.update();

    const bySirket = {{}};
    computed.forEach(f => {{ (bySirket[f.sirket] = bySirket[f.sirket] || []).push(f); }});

    SIRKET_ORDER.forEach(sirket => {{
      const rows = (bySirket[sirket] || []).slice().sort(sortByRet);
      const tbody = document.getElementById('tbody-' + slug(sirket));
      if (!tbody) return;
      tbody.innerHTML = rows.map(r => `
        <tr>
          <td class="code">${{r.valorUrl ? `<a href="${{r.valorUrl}}" target="_blank" rel="noopener" class="code-link" title="Fonun kendi sitesindeki sayfasını aç">${{r.kod}}</a>` : r.kod}}</td>
          <td class="name">${{r.ad}}</td>
          <td class="num muted">${{r.risk ? r.risk + '/7' : '—'}}</td>
          <td class="num">${{fmtPrice(r.fiyat)}}</td>
          <td class="num">${{fmtPct(r.ret)}}</td>
          <td class="spark"><canvas class="sparkline" data-kod="${{r.kod}}" width="120" height="32"></canvas></td>
          <td class="num muted" title="${{(r.platform || '') + (r.valorKaynak ? ' · Kaynak: ' + r.valorKaynak : '')}}">${{r.alisValor === '-' ? '—' : (r.alisValor + ' / ' + r.satisValor)}}</td>
        </tr>`).join('');
      rows.forEach(r => {{
        const canvas = tbody.querySelector(`canvas[data-kod="${{r.kod}}"]`);
        if (canvas) buildSparkline(canvas, r.series);
      }});
      const withRetS = rows.filter(r => r.ret !== null);
      const avgS = withRetS.length ? withRetS.reduce((a, b) => a + b.ret, 0) / withRetS.length : null;
      const meta = document.getElementById('meta-' + slug(sirket));
      if (meta) meta.textContent = `· ${{rows.length}} fon · ortalama ${{avgS !== null ? avgS.toFixed(4) + '%' : '—'}}`;
      const col = document.getElementById('col-' + slug(sirket));
      if (col) col.textContent = label + ' Getiri';
    }});
  }}

  document.querySelectorAll('.period-btn').forEach(btn => {{
    btn.addEventListener('click', () => {{ currentPeriod = btn.dataset.period; render(); }});
  }});

  document.querySelectorAll('.acc-header').forEach(header => {{
    header.addEventListener('click', () => {{
      const card = header.closest('.card');
      const wasOpen = card.classList.contains('open');
      document.querySelectorAll('.card.accordion').forEach(c => c.classList.remove('open'));
      if (!wasOpen) card.classList.add('open');
    }});
  }});

  render();
</script>
</body>
</html>"""
    return html


def render_karar_html(rows):
    funds_json = json.dumps([
        {"kod": r["kod"], "ad": r["ad"], "sirket": r["sirket"], "risk": r["risk"], "hist": r["hist"]}
        for r in rows
    ], ensure_ascii=False)

    html = f"""<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Yatırım Önerisi (AI Analiz) - TEFAS Para Piyasası Fonları</title>
<style>
  :root {{
    --bg: #f7f5fb; --card: #ffffff; --border: #e3dff2; --text: #443f5e;
    --muted: #8f88a3; --pos: #3f9973; --neg: #c85a72; --accent: #5b7fd1; --warn: #c78f4a;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; padding: 32px; background: var(--bg); color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif;
    max-width: 900px;
  }}
  h1 {{ font-size: 22px; margin: 0 0 4px 0; }}
  .subtitle {{ color: var(--muted); font-size: 13px; margin-bottom: 20px; }}
  a.back {{ color: var(--accent); font-size: 13px; text-decoration: none; }}
  a.back:hover {{ text-decoration: underline; }}
  .card {{
    background: var(--card); border: 1px solid var(--border); border-radius: 12px;
    padding: 20px; margin-bottom: 20px; box-shadow: 0 1px 3px rgba(68,63,94,0.06);
  }}
  .card h2 {{ font-size: 15px; margin: 0 0 12px 0; font-weight: 700; }}
  .warn-box {{
    background: rgba(199,143,74,0.14); border: 1px solid var(--warn); border-radius: 10px;
    padding: 14px 18px; margin-bottom: 20px; font-size: 13px; line-height: 1.6; color: var(--text);
  }}
  .warn-box b {{ color: var(--warn); }}
  .btn {{
    background: var(--accent); color: #fff; border: none; border-radius: 8px;
    padding: 11px 20px; font-size: 14px; font-weight: 600; cursor: pointer; font-family: inherit;
  }}
  .btn:hover {{ opacity: .9; }}
  .btn.secondary {{ background: transparent; border: 1px solid var(--border); color: var(--text); padding: 9px 16px; font-size: 13px; }}
  .btn:disabled {{ opacity: .5; cursor: default; }}
  .btn-row {{ display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }}
  .muted {{ color: var(--muted); }}
  .key-status {{ font-size: 12px; color: var(--muted); margin-top: 8px; }}
  #result {{
    margin-top: 16px; white-space: pre-wrap; line-height: 1.7; font-size: 14px;
    display: none;
  }}
  #result.show {{ display: block; }}
  .loading {{ color: var(--muted); font-size: 13px; margin-top: 16px; display: none; }}
  .loading.show {{ display: block; }}
  .err {{ color: var(--neg); font-size: 13px; margin-top: 16px; }}
  .help {{ font-size: 12px; color: var(--muted); margin-top: 14px; line-height: 1.6; }}
</style>
</head>
<body>
  <a class="back" href="index.html">&larr; Rapora Dön</a>
  <h1>Yatırım Önerisi — Yapay Zeka Destekli Bilgilendirme</h1>
  <div class="subtitle">Takip edilen {len(rows)} para piyasası fonu arasından, incelemeye değer bulunan 3 fon ve gerekçeleri.</div>

  <div class="warn-box">
    <b>Bu bir yatırım tavsiyesi değildir.</b> Aşağıdaki analiz, "Karar Ver" butonuna bastığınızda tarayıcınızdan
    doğrudan bir yapay zeka modeline (Google Gemini) gönderilen kamuya açık fon verilerine ve modelin genel
    ekonomik bilgisine dayanır. Kişiselleştirilmiş, profesyonel bir finansal tavsiye değildir; yatırım
    kararlarınızı vermeden önce kendi araştırmanızı yapın ve gerekirse yetkili bir finansal danışmana başvurun.
  </div>

  <div class="card">
    <h2>AI Analizini Başlat</h2>
    <div class="btn-row">
      <button class="btn" id="decideBtn" onclick="decide()">Karar Ver</button>
      <button class="btn secondary" onclick="resetApiKey()">API Anahtarını Sıfırla</button>
    </div>
    <div class="key-status" id="keyStatus"></div>
    <div class="loading" id="loading">Analiz ediliyor, bu birkaç saniye sürebilir…</div>
    <div id="result"></div>
    <div id="errBox"></div>
    <div class="help">
      Bu özellik kendi Google Gemini API anahtarınızı kullanır — anahtar sadece bu tarayıcıda saklanır,
      kimseyle paylaşılmaz, doğrudan Google'ın sunucusuna gönderilir. Anahtarınız yoksa
      <a href="https://aistudio.google.com/apikey" target="_blank" style="color:var(--accent)">aistudio.google.com/apikey</a>
      üzerinden, sadece bir Google hesabıyla, <b>kredi kartı gerekmeden ücretsiz</b> oluşturabilirsiniz. Ücretsiz
      katmanın günlük kotası bu rapor için fazlasıyla yeterlidir.
    </div>
  </div>

<script>
  const FUNDS = {funds_json};
  const PERIOD_DAYS = {{ gunluk: 1, haftalik: 7, aylik: 30, yillik: 365 }};

  function parseDate(s) {{ return new Date(s + 'T00:00:00').getTime(); }}

  function computeForPeriod(hist, days) {{
    if (!hist || hist.length === 0) return null;
    const last = hist[hist.length - 1];
    if (hist.length === 1) return null;
    const targetTime = parseDate(last[0]) - days * 86400000;
    let baseline = hist[0];
    for (let i = hist.length - 1; i >= 0; i--) {{
      if (parseDate(hist[i][0]) <= targetTime) {{ baseline = hist[i]; break; }}
    }}
    if (baseline[1] <= 0 || baseline[0] === last[0]) return null;
    return (last[1] - baseline[1]) / baseline[1] * 100;
  }}

  function getApiKey(forcePrompt) {{
    let key = localStorage.getItem('tefas_gemini_key') || '';
    if (forcePrompt || !key) {{
      key = prompt('Google Gemini API anahtarınız (sadece bu tarayıcıda saklanır):', '') || key;
      if (key) localStorage.setItem('tefas_gemini_key', key);
    }}
    return key;
  }}

  function resetApiKey() {{
    localStorage.removeItem('tefas_gemini_key');
    updateKeyStatus();
    getApiKey(true);
  }}

  function updateKeyStatus() {{
    const key = localStorage.getItem('tefas_gemini_key') || '';
    document.getElementById('keyStatus').textContent = key
      ? 'API anahtarı kayıtlı (...' + key.slice(-4) + ')'
      : 'Henüz bir API anahtarı girilmedi.';
  }}
  updateKeyStatus();

  function buildPrompt() {{
    const today = new Date().toISOString().slice(0, 10);
    const lines = FUNDS.map(f => {{
      const g = computeForPeriod(f.hist, PERIOD_DAYS.gunluk);
      const h = computeForPeriod(f.hist, PERIOD_DAYS.haftalik);
      const a = computeForPeriod(f.hist, PERIOD_DAYS.aylik);
      const y = computeForPeriod(f.hist, PERIOD_DAYS.yillik);
      const fmt = v => v === null ? '—' : v.toFixed(4) + '%';
      return `${{f.kod}} | ${{f.sirket}} | ${{f.ad}} | Risk ${{f.risk}}/7 | Günlük ${{fmt(g)}} | Haftalık ${{fmt(h)}} | Aylık ${{fmt(a)}} | Yıllık ${{fmt(y)}}`;
    }});
    return `Bugünün tarihi: ${{today}}. Sen Türkiye'deki TEFAS para piyasası fonları hakkında bilgilendirme amaçlı analiz yapan bir asistansın.

Aşağıda risk değeri 1/7 veya 2/7 olan, TL bazlı para piyasası fonlarının listesi ve güncel getiri verileri var (kod | kurucu firma | fon adı | risk | günlük getiri | haftalık getiri | aylık getiri | yıllık getiri):

${{lines.join('\\n')}}

Görevin: Genel ekonomik konjonktür hakkındaki bilgini (enflasyon, TCMB politika faizi, TL para piyasası koşulları gibi) ve yukarıdaki getiri/risk verilerini birlikte değerlendirerek, bu listeden incelemeye değer bulduğun 3 fonu seç.

Yanıtını şu şekilde yapılandır:
1) Önce 2-3 cümlelik güncel ekonomik konjonktür özeti (bu değerlendirmeyi nasıl etkiliyor).
2) Seçtiğin 3 fonu, kod ve firma adıyla birlikte sırayla listele; her biri için 2-4 cümlelik somut gerekçe yaz (getiri seviyesi, risk uyumu, tutarlılık gibi noktalara değin).
3) Kısaca "Bu kararı nasıl verdim" başlığıyla metodolojini özetle.
4) Yanıtının başında VE sonunda, bunun kişiselleştirilmiş bir yatırım tavsiyesi olmadığını, kamuya açık verilere dayalı genel bir bilgilendirme olduğunu, yatırım kararlarının kendi araştırması veya yetkili bir finansal danışman desteğiyle verilmesi gerektiğini açıkça belirt.

Düz metin olarak yaz (markdown/yıldız kullanma), paragraflar arasında boş satır bırak.`;
  }}

  async function decide() {{
    const btn = document.getElementById('decideBtn');
    const loading = document.getElementById('loading');
    const result = document.getElementById('result');
    const errBox = document.getElementById('errBox');
    errBox.textContent = '';
    result.classList.remove('show');
    result.textContent = '';

    const apiKey = getApiKey(false);
    if (!apiKey) {{
      errBox.innerHTML = '<div class="err">API anahtarı girilmedi.</div>';
      return;
    }}

    btn.disabled = true;
    loading.classList.add('show');
    try {{
      const model = 'gemini-3.6-flash';
      const url = `https://generativelanguage.googleapis.com/v1beta/models/${{model}}:generateContent?key=${{encodeURIComponent(apiKey)}}`;
      const res = await fetch(url, {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify({{
          contents: [{{ parts: [{{ text: buildPrompt() }}] }}],
          generationConfig: {{ maxOutputTokens: 4000 }},
        }}),
      }});
      if (!res.ok) {{
        const t = await res.text();
        throw new Error('HTTP ' + res.status + ': ' + t.slice(0, 300));
      }}
      const data = await res.json();
      const parts = (data.candidates && data.candidates[0] && data.candidates[0].content && data.candidates[0].content.parts) || [];
      const text = parts.map(p => p.text || '').join('\\n').trim();
      result.textContent = text || 'Yanıt alınamadı.';
      result.classList.add('show');
    }} catch (e) {{
      errBox.innerHTML = '<div class="err">Hata: ' + e.message + '</div>';
    }} finally {{
      btn.disabled = false;
      loading.classList.remove('show');
    }}
  }}
</script>
</body>
</html>"""
    return html


def render_karsilastir_html(rows):
    funds_json = json.dumps([
        {
            "kod": r["kod"], "ad": r["ad"], "sirket": r["sirket"], "risk": r["risk"],
            "hist": r["hist"], "alisValor": r.get("alis_valor", "-"), "satisValor": r.get("satis_valor", "-"),
            "valorKaynak": r.get("valor_kaynak", ""), "valorUrl": r.get("valor_url", ""),
        }
        for r in rows
    ], ensure_ascii=False)

    html = f"""<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Fon Karşılaştırma - TEFAS Para Piyasası Fonları</title>
<style>
  :root {{
    --bg: #f7f5fb; --card: #ffffff; --border: #e3dff2; --text: #443f5e;
    --muted: #8f88a3; --pos: #3f9973; --neg: #c85a72; --accent: #5b7fd1; --warn: #c78f4a;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; padding: 32px; background: var(--bg); color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif;
    max-width: 980px;
  }}
  h1 {{ font-size: 22px; margin: 0 0 4px 0; }}
  .subtitle {{ color: var(--muted); font-size: 13px; margin-bottom: 20px; }}
  a.back {{ color: var(--accent); font-size: 13px; text-decoration: none; }}
  a.back:hover {{ text-decoration: underline; }}
  .card {{
    background: var(--card); border: 1px solid var(--border); border-radius: 12px;
    padding: 20px; margin-bottom: 20px; box-shadow: 0 1px 3px rgba(68,63,94,0.06);
  }}
  .card h2 {{ font-size: 15px; margin: 0 0 14px 0; font-weight: 700; }}
  .select-row {{ display: flex; gap: 12px; flex-wrap: wrap; }}
  .select-col {{ flex: 1; min-width: 220px; }}
  .select-col label {{ display: block; font-size: 12px; color: var(--muted); margin-bottom: 6px; }}
  select {{
    width: 100%; background: var(--bg); color: var(--text); border: 1px solid var(--border);
    border-radius: 8px; padding: 10px 12px; font-size: 13px; font-family: inherit;
  }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  th, td {{ padding: 10px 12px; border-bottom: 1px solid var(--border); text-align: left; vertical-align: middle; }}
  th {{ color: var(--muted); font-weight: 600; font-size: 11px; text-transform: uppercase; letter-spacing: .03em; }}
  .rowlabel {{ color: var(--muted); font-size: 12px; white-space: nowrap; }}
  .num {{ text-align: right; font-variant-numeric: tabular-nums; }}
  .pos {{ color: var(--pos); font-weight: 600; }}
  .neg {{ color: var(--neg); font-weight: 600; }}
  .muted {{ color: var(--muted); }}
  .fund-th {{ text-align: right; }}
  .fund-name {{ font-weight: 700; color: var(--accent); text-decoration: none; display: block; }}
  .fund-name:hover {{ text-decoration: underline; }}
  .fund-sirket {{ color: var(--muted); font-weight: 400; font-size: 11px; text-transform: none; letter-spacing: 0; }}
  .badge-win {{
    display: inline-block; background: var(--accent); color: #fff; font-size: 10px; font-weight: 700;
    padding: 2px 8px; border-radius: 999px; margin-top: 4px; letter-spacing: .03em;
  }}
  td.winner, th.winner {{ background: rgba(91,127,209,0.08); }}
  .empty-msg {{ color: var(--muted); font-size: 13px; padding: 20px 0; text-align: center; }}
  .fon-link {{ color: var(--accent); text-decoration: none; font-size: 12px; }}
  .fon-link:hover {{ text-decoration: underline; }}
</style>
</head>
<body>
  <a class="back" href="index.html">&larr; Rapora Dön</a>
  <h1>Fon Karşılaştırma</h1>
  <div class="subtitle">Aşağıdan 3 fon seçin; son 5 günlük fiyat, günlük/haftalık/aylık getiri, risk ve valör bilgileri karşılaştırılsın. En yüksek getiriye sahip fon otomatik olarak öne çıkarılır.</div>

  <div class="card">
    <h2>Karşılaştırılacak Fonlar</h2>
    <div class="select-row">
      <div class="select-col">
        <label>1. Fon</label>
        <select id="sel0"></select>
      </div>
      <div class="select-col">
        <label>2. Fon</label>
        <select id="sel1"></select>
      </div>
      <div class="select-col">
        <label>3. Fon</label>
        <select id="sel2"></select>
      </div>
    </div>
  </div>

  <div class="card">
    <h2>Karşılaştırma Tablosu</h2>
    <div id="compareResult"></div>
  </div>

<script>
  const FUNDS = {funds_json};
  const PERIOD_DAYS = {{ gunluk: 1, haftalik: 7, aylik: 30 }};

  function parseDate(s) {{ return new Date(s + 'T00:00:00').getTime(); }}

  function computeForPeriod(hist, days) {{
    if (!hist || hist.length === 0) return null;
    const last = hist[hist.length - 1];
    if (hist.length === 1) return null;
    const targetTime = parseDate(last[0]) - days * 86400000;
    let baseline = hist[0];
    for (let i = hist.length - 1; i >= 0; i--) {{
      if (parseDate(hist[i][0]) <= targetTime) {{ baseline = hist[i]; break; }}
    }}
    if (baseline[1] <= 0 || baseline[0] === last[0]) return null;
    return (last[1] - baseline[1]) / baseline[1] * 100;
  }}

  function last5(hist) {{
    if (!hist || hist.length === 0) return [];
    return hist.slice(-5).slice().reverse();
  }}

  function fmtPct(v) {{
    if (v === null || v === undefined || isNaN(v)) return '<span class="muted">—</span>';
    const cls = v >= 0 ? 'pos' : 'neg';
    const sign = v >= 0 ? '+' : '';
    return `<span class="${{cls}}">${{sign}}${{v.toFixed(4)}}%</span>`;
  }}
  function fmtPrice(v) {{
    return v.toLocaleString('tr-TR', {{ minimumFractionDigits: 6, maximumFractionDigits: 6 }});
  }}
  function fmtDate(s) {{
    const [y, m, d] = s.split('-');
    return `${{d}}.${{m}}.${{y}}`;
  }}

  const sortedFunds = FUNDS.slice().sort((a, b) => (a.sirket + a.kod).localeCompare(b.sirket + b.kod, 'tr'));
  const bySirket = {{}};
  sortedFunds.forEach(f => {{ (bySirket[f.sirket] = bySirket[f.sirket] || []).push(f); }});

  function populateSelect(sel, defaultKod) {{
    sel.innerHTML = '';
    Object.keys(bySirket).forEach(sirket => {{
      const grp = document.createElement('optgroup');
      grp.label = sirket;
      bySirket[sirket].forEach(f => {{
        const opt = document.createElement('option');
        opt.value = f.kod;
        opt.textContent = `${{f.kod}} — ${{f.ad}}`;
        if (f.kod === defaultKod) opt.selected = true;
        grp.appendChild(opt);
      }});
      sel.appendChild(grp);
    }});
  }}

  const selects = [document.getElementById('sel0'), document.getElementById('sel1'), document.getElementById('sel2')];
  const defaults = sortedFunds.slice(0, 3).map(f => f.kod);
  selects.forEach((sel, i) => {{
    populateSelect(sel, defaults[i] || sortedFunds[0].kod);
    sel.addEventListener('change', render);
  }});

  function render() {{
    const kods = selects.map(s => s.value);
    const result = document.getElementById('compareResult');

    if (new Set(kods).size < 3) {{
      result.innerHTML = '<div class="empty-msg">Lütfen 3 farklı fon seçin (aynı fon birden fazla kez seçilemez).</div>';
      return;
    }}

    const funds = kods.map(k => FUNDS.find(f => f.kod === k));

    const metrics = funds.map(f => ({{
      gunluk: computeForPeriod(f.hist, PERIOD_DAYS.gunluk),
      haftalik: computeForPeriod(f.hist, PERIOD_DAYS.haftalik),
      aylik: computeForPeriod(f.hist, PERIOD_DAYS.aylik),
    }}));

    // Kazananı belirle: 3 getiri metriğinden (günlük/haftalık/aylık) en çoğunda en yüksek
    // değere sahip olan fon "kazanır". Eşitlik durumunda sırasıyla aylık, haftalık, günlük
    // getirisi en yüksek olan öne çıkar.
    const wins = [0, 0, 0];
    ['gunluk', 'haftalik', 'aylik'].forEach(key => {{
      let bestIdx = -1, bestVal = -Infinity;
      metrics.forEach((m, i) => {{ if (m[key] !== null && m[key] > bestVal) {{ bestVal = m[key]; bestIdx = i; }} }});
      if (bestIdx >= 0) wins[bestIdx]++;
    }});
    let winnerIdx = 0;
    for (let i = 1; i < 3; i++) {{
      if (wins[i] > wins[winnerIdx]) {{ winnerIdx = i; continue; }}
      if (wins[i] === wins[winnerIdx]) {{
        const a = metrics[i], b = metrics[winnerIdx];
        const av = (a.aylik ?? -Infinity), bv = (b.aylik ?? -Infinity);
        if (av > bv) {{ winnerIdx = i; continue; }}
        if (av === bv) {{
          const ah = (a.haftalik ?? -Infinity), bh = (b.haftalik ?? -Infinity);
          if (ah > bh) winnerIdx = i;
        }}
      }}
    }}
    const hasAnyReturn = wins.some(w => w > 0);

    function bestColFor(key) {{
      let bestIdx = -1, bestVal = -Infinity;
      metrics.forEach((m, i) => {{ if (m[key] !== null && m[key] > bestVal) {{ bestVal = m[key]; bestIdx = i; }} }});
      return bestIdx;
    }}

    const rows5 = funds.map(f => last5(f.hist));
    const maxRows = Math.max(0, ...rows5.map(r => r.length));

    let html = '<table><thead><tr><th></th>';
    funds.forEach((f, i) => {{
      const isWinner = hasAnyReturn && i === winnerIdx;
      html += `<th class="fund-th${{isWinner ? ' winner' : ''}}">
        <a class="fund-name" href="${{f.valorUrl || '#'}}" target="_blank" rel="noopener">${{f.kod}}</a>
        <span class="fund-sirket">${{f.sirket}}</span>
        ${{isWinner ? '<span class="badge-win">EN YÜKSEK GETİRİ</span>' : ''}}
      </th>`;
    }});
    html += '</tr></thead><tbody>';

    for (let r = 0; r < maxRows; r++) {{
      html += `<tr><td class="rowlabel">${{r === 0 ? 'Son Fiyat' : 'T-' + r + ' Fiyatı'}}</td>`;
      funds.forEach((f, i) => {{
        const pt = rows5[i][r];
        const isWinner = hasAnyReturn && i === winnerIdx;
        html += `<td class="num${{isWinner ? ' winner' : ''}}">${{pt ? fmtPrice(pt[1]) + '<div class="muted" style="font-size:11px">' + fmtDate(pt[0]) + '</div>' : '<span class="muted">—</span>'}}</td>`;
      }});
      html += '</tr>';
    }}

    const metricRows = [
      ['Günlük Getiri', 'gunluk'],
      ['Haftalık Getiri', 'haftalik'],
      ['Aylık Getiri', 'aylik'],
    ];
    metricRows.forEach(([label, key]) => {{
      const bestIdx = bestColFor(key);
      html += `<tr><td class="rowlabel">${{label}}</td>`;
      funds.forEach((f, i) => {{
        const isWinner = hasAnyReturn && i === winnerIdx;
        const isBest = i === bestIdx;
        html += `<td class="num${{isWinner ? ' winner' : ''}}">${{fmtPct(metrics[i][key])}}${{isBest ? ' ▲' : ''}}</td>`;
      }});
      html += '</tr>';
    }});

    html += `<tr><td class="rowlabel">Risk Seviyesi</td>`;
    funds.forEach((f, i) => {{
      const isWinner = hasAnyReturn && i === winnerIdx;
      html += `<td class="num${{isWinner ? ' winner' : ''}}">${{f.risk ? f.risk + '/7' : '<span class="muted">—</span>'}}</td>`;
    }});
    html += '</tr>';

    html += `<tr><td class="rowlabel">Alış Valörü</td>`;
    funds.forEach((f, i) => {{
      const isWinner = hasAnyReturn && i === winnerIdx;
      html += `<td class="num${{isWinner ? ' winner' : ''}}">${{f.alisValor || '<span class="muted">—</span>'}}</td>`;
    }});
    html += '</tr>';

    html += `<tr><td class="rowlabel">Satış Valörü</td>`;
    funds.forEach((f, i) => {{
      const isWinner = hasAnyReturn && i === winnerIdx;
      html += `<td class="num${{isWinner ? ' winner' : ''}}">${{f.satisValor || '<span class="muted">—</span>'}}</td>`;
    }});
    html += '</tr>';

    html += `<tr><td class="rowlabel">Valör Kaynağı</td>`;
    funds.forEach((f, i) => {{
      const isWinner = hasAnyReturn && i === winnerIdx;
      html += `<td class="num muted${{isWinner ? ' winner' : ''}}" style="font-size:12px">${{f.valorKaynak || '—'}}</td>`;
    }});
    html += '</tr>';

    html += `<tr><td class="rowlabel">Fon Sayfası</td>`;
    funds.forEach((f, i) => {{
      const isWinner = hasAnyReturn && i === winnerIdx;
      html += `<td class="num${{isWinner ? ' winner' : ''}}">${{f.valorUrl ? `<a class="fon-link" href="${{f.valorUrl}}" target="_blank" rel="noopener">Sayfayı Aç →</a>` : '<span class="muted">—</span>'}}</td>`;
    }});
    html += '</tr>';

    html += '</tbody></table>';
    result.innerHTML = html;
  }}

  render();
</script>
</body>
</html>"""
    return html


def render_fon_detay_html(rows):
    funds_json = json.dumps([
        {
            "kod": r["kod"], "ad": r["ad"], "sirket": r["sirket"], "risk": r["risk"],
            "hist": r["hist"], "platform": r.get("platform", ""),
            "alisValor": r.get("alis_valor", "-"), "satisValor": r.get("satis_valor", "-"),
            "valorKaynak": r.get("valor_kaynak", ""), "valorUrl": r.get("valor_url", ""),
        }
        for r in rows
    ], ensure_ascii=False)

    html = f"""<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Fon Grafiği - TEFAS Para Piyasası Fonları</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.0/chart.umd.min.js"></script>
<style>
  :root {{
    --bg: #f7f5fb; --card: #ffffff; --border: #e3dff2; --text: #443f5e;
    --muted: #8f88a3; --pos: #3f9973; --neg: #c85a72; --accent: #5b7fd1; --warn: #c78f4a;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; padding: 32px; background: var(--bg); color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif;
    max-width: 980px;
  }}
  h1 {{ font-size: 22px; margin: 0 0 4px 0; }}
  .subtitle {{ color: var(--muted); font-size: 13px; margin-bottom: 20px; }}
  a.back {{ color: var(--accent); font-size: 13px; text-decoration: none; }}
  a.back:hover {{ text-decoration: underline; }}
  .card {{
    background: var(--card); border: 1px solid var(--border); border-radius: 12px;
    padding: 20px; margin-bottom: 20px; box-shadow: 0 1px 3px rgba(68,63,94,0.06);
  }}
  .card h2 {{ font-size: 15px; margin: 0 0 16px 0; font-weight: 700; }}
  .summary {{ display: flex; gap: 16px; margin-bottom: 20px; flex-wrap: wrap; }}
  .stat {{
    background: var(--card); border: 1px solid var(--border); border-radius: 10px;
    padding: 14px 18px; min-width: 150px; box-shadow: 0 1px 3px rgba(68,63,94,0.06);
  }}
  .stat .label {{ color: var(--muted); font-size: 12px; margin-bottom: 6px; }}
  .stat .value {{ font-size: 20px; font-weight: 600; }}
  .pos {{ color: var(--pos); }}
  .neg {{ color: var(--neg); }}
  .muted {{ color: var(--muted); }}
  .chart-wrap {{ height: 380px; }}
  .risk-badge {{
    display: inline-block; background: rgba(91,127,209,0.12); color: var(--accent);
    font-size: 11px; font-weight: 700; padding: 3px 10px; border-radius: 999px; margin-left: 8px;
  }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  th {{
    text-align: left; padding: 10px 12px; color: var(--muted); font-weight: 600;
    border-bottom: 1px solid var(--border); font-size: 11px; text-transform: uppercase; letter-spacing: .03em;
  }}
  td {{ padding: 10px 12px; border-bottom: 1px solid var(--border); }}
  .num {{ text-align: right; font-variant-numeric: tabular-nums; }}
  .fon-link {{ color: var(--accent); text-decoration: none; font-size: 12px; }}
  .fon-link:hover {{ text-decoration: underline; }}
  .not-found {{ color: var(--muted); font-size: 14px; }}
  footer {{ color: var(--muted); font-size: 12px; margin-top: 24px; }}
</style>
</head>
<body>
  <a class="back" href="index.html">&larr; Rapora Dön</a>
  <div id="content"></div>

  <footer>
    Veri kaynağı: <a href="https://www.tefas.gov.tr/tr/fon-verileri" style="color:var(--accent)">TEFAS Fon Verileri</a>.
    Bu rapor bilgilendirme amaçlıdır, yatırım tavsiyesi değildir.
  </footer>

<script>
  const FUNDS = {funds_json};

  function parseDate(s) {{ return new Date(s + 'T00:00:00').getTime(); }}
  function fmtDate(s) {{
    const [y, m, d] = s.split('-');
    return `${{d}}.${{m}}.${{y}}`;
  }}
  function fmtPrice(v) {{
    return v.toLocaleString('tr-TR', {{ minimumFractionDigits: 6, maximumFractionDigits: 6 }});
  }}
  function fmtPct(v) {{
    if (v === null || v === undefined || isNaN(v)) return '<span class="muted">—</span>';
    const cls = v >= 0 ? 'pos' : 'neg';
    const sign = v >= 0 ? '+' : '';
    return `<span class="${{cls}}">${{sign}}${{v.toFixed(4)}}%</span>`;
  }}
  function computeForPeriod(hist, days) {{
    if (!hist || hist.length < 2) return null;
    const last = hist[hist.length - 1];
    const targetTime = parseDate(last[0]) - days * 86400000;
    let baseline = hist[0];
    for (let i = hist.length - 1; i >= 0; i--) {{
      if (parseDate(hist[i][0]) <= targetTime) {{ baseline = hist[i]; break; }}
    }}
    if (baseline[1] <= 0 || baseline[0] === last[0]) return null;
    return (last[1] - baseline[1]) / baseline[1] * 100;
  }}

  const params = new URLSearchParams(location.search);
  const kod = (params.get('kod') || '').toUpperCase();
  const fund = FUNDS.find(f => f.kod === kod);
  const content = document.getElementById('content');

  if (!fund) {{
    content.innerHTML = '<div class="card"><p class="not-found">Fon bulunamadı. Lütfen rapora dönüp bir fona tıklayın.</p></div>';
  }} else {{
    document.title = `${{fund.kod}} — ${{fund.ad}}`;
    const last = fund.hist[fund.hist.length - 1];
    const gunluk = computeForPeriod(fund.hist, 1);
    const haftalik = computeForPeriod(fund.hist, 7);
    const aylik = computeForPeriod(fund.hist, 30);
    const yillik = computeForPeriod(fund.hist, 365);

    content.innerHTML = `
      <h1>${{fund.kod}} — ${{fund.ad}}<span class="risk-badge">Risk ${{fund.risk || '—'}}/7</span></h1>
      <div class="subtitle">${{fund.sirket}} · Son fiyat tarihi: ${{fmtDate(last[0])}} ${{fund.valorUrl ? `· <a class="fon-link" href="${{fund.valorUrl}}" target="_blank" rel="noopener">Fonun kendi sayfası →</a>` : ''}}</div>

      <div class="summary">
        <div class="stat"><div class="label">Son Fiyat</div><div class="value">${{fmtPrice(last[1])}}</div></div>
        <div class="stat"><div class="label">Günlük Getiri</div><div class="value">${{fmtPct(gunluk)}}</div></div>
        <div class="stat"><div class="label">Haftalık Getiri</div><div class="value">${{fmtPct(haftalik)}}</div></div>
        <div class="stat"><div class="label">Aylık Getiri</div><div class="value">${{fmtPct(aylik)}}</div></div>
        <div class="stat"><div class="label">Yıllık Getiri</div><div class="value">${{fmtPct(yillik)}}</div></div>
      </div>

      <div class="card">
        <h2>Tarihsel Fiyat Grafiği</h2>
        <div class="chart-wrap"><canvas id="histChart"></canvas></div>
      </div>

      <div class="card">
        <h2>Son 20 Kayıt</h2>
        <table>
          <thead><tr><th>Tarih</th><th style="text-align:right">Fiyat</th></tr></thead>
          <tbody>
            ${{fund.hist.slice(-20).slice().reverse().map(h => `<tr><td>${{fmtDate(h[0])}}</td><td class="num">${{fmtPrice(h[1])}}</td></tr>`).join('')}}
          </tbody>
        </table>
      </div>
    `;

    new Chart(document.getElementById('histChart'), {{
      type: 'line',
      data: {{
        labels: fund.hist.map(h => fmtDate(h[0])),
        datasets: [{{
          label: fund.kod, data: fund.hist.map(h => h[1]),
          borderColor: '#5b7fd1', backgroundColor: 'rgba(91,127,209,0.12)',
          borderWidth: 2, pointRadius: 0, tension: 0.25, fill: true,
        }}]
      }},
      options: {{
        responsive: true, maintainAspectRatio: false,
        scales: {{
          x: {{ position: 'bottom', ticks: {{ color: '#8f88a3', maxRotation: 0, autoSkip: true, maxTicksLimit: 10, font: {{ size: 10 }} }}, grid: {{ display: false }} }},
          y: {{ ticks: {{ color: '#8f88a3' }}, grid: {{ color: '#e3dff2' }} }}
        }},
        plugins: {{
          legend: {{ display: false }},
          tooltip: {{ callbacks: {{ title: (items) => items[0] ? items[0].label : '' }} }}
        }}
      }}
    }});
  }}
</script>
</body>
</html>"""
    return html


def render_disaaktar_html(rows):
    funds_json = json.dumps([
        {"kod": r["kod"], "ad": r["ad"], "sirket": r["sirket"], "hist": r["hist"]}
        for r in rows
    ], ensure_ascii=False)

    html = f"""<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Veri Dışa Aktar (Excel) - TEFAS Para Piyasası Fonları</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/xlsx/0.18.5/xlsx.full.min.js"></script>
<style>
  :root {{
    --bg: #f7f5fb; --card: #ffffff; --border: #e3dff2; --text: #443f5e;
    --muted: #8f88a3; --pos: #3f9973; --neg: #c85a72; --accent: #5b7fd1; --warn: #c78f4a;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; padding: 32px; background: var(--bg); color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif;
    max-width: 900px;
  }}
  h1 {{ font-size: 22px; margin: 0 0 4px 0; }}
  .subtitle {{ color: var(--muted); font-size: 13px; margin-bottom: 20px; }}
  a.back {{ color: var(--accent); font-size: 13px; text-decoration: none; }}
  a.back:hover {{ text-decoration: underline; }}
  .card {{
    background: var(--card); border: 1px solid var(--border); border-radius: 12px;
    padding: 20px; margin-bottom: 20px; box-shadow: 0 1px 3px rgba(68,63,94,0.06);
  }}
  .card h2 {{ font-size: 15px; margin: 0 0 16px 0; font-weight: 700; }}
  .select-row {{ display: flex; gap: 12px; flex-wrap: wrap; }}
  .select-col {{ flex: 1; min-width: 200px; }}
  .select-col label {{ display: block; font-size: 12px; color: var(--muted); margin-bottom: 6px; }}
  select, input[type="date"] {{
    width: 100%; background: var(--bg); color: var(--text); border: 1px solid var(--border);
    border-radius: 8px; padding: 9px 12px; font-size: 13px; font-family: inherit;
  }}
  select[multiple] {{ height: auto; }}
  .btn {{
    background: var(--accent); color: #fff; border: none; border-radius: 8px;
    padding: 9px 16px; font-size: 13px; font-weight: 600; cursor: pointer; font-family: inherit;
  }}
  .btn:hover {{ opacity: .9; }}
  .btn.secondary {{ background: transparent; border: 1px solid var(--border); color: var(--text); }}
  .btn-row {{ display: flex; gap: 8px; margin-top: 14px; flex-wrap: wrap; }}
  .help-text {{ font-size: 12px; color: var(--muted); margin-top: 10px; line-height: 1.6; }}
  .pos {{ color: var(--pos); }}
  .neg {{ color: var(--neg); }}
</style>
</head>
<body>
  <a class="back" href="index.html">&larr; Rapora Dön</a>
  <h1>Veri Dışa Aktar (Excel)</h1>
  <div class="subtitle">Fonları ve tarih aralığını seçip Excel dosyası olarak indirin.</div>

  <div class="card">
    <h2>Dışa Aktarma Ayarları</h2>
    <div class="select-row">
      <div class="select-col" style="flex:2">
        <label>Fonlar (Ctrl/Cmd ile birden fazla seçebilirsiniz)</label>
        <select id="exportFunds" multiple size="12"></select>
      </div>
      <div class="select-col">
        <label>Başlangıç Tarihi</label>
        <input type="date" id="exportStart">
      </div>
      <div class="select-col">
        <label>Bitiş Tarihi</label>
        <input type="date" id="exportEnd">
      </div>
    </div>
    <div class="btn-row">
      <button class="btn secondary" onclick="selectAllExportFunds()">Tümünü Seç</button>
      <button class="btn secondary" onclick="clearExportFunds()">Seçimi Temizle</button>
      <button class="btn" onclick="exportExcel()">Excel'e Aktar</button>
    </div>
    <div id="exportStatus" class="help-text"></div>
  </div>

<script>
  const FUNDS = {funds_json};

  const sortedFundsForExport = FUNDS.slice().sort((a, b) => (a.sirket + a.kod).localeCompare(b.sirket + b.kod, 'tr'));
  const exportBySirket = {{}};
  sortedFundsForExport.forEach(f => {{ (exportBySirket[f.sirket] = exportBySirket[f.sirket] || []).push(f); }});

  function populateExportSelect() {{
    const sel = document.getElementById('exportFunds');
    sel.innerHTML = '';
    Object.keys(exportBySirket).forEach(sirket => {{
      const grp = document.createElement('optgroup');
      grp.label = sirket;
      exportBySirket[sirket].forEach(f => {{
        const opt = document.createElement('option');
        opt.value = f.kod;
        opt.textContent = `${{f.kod}} — ${{f.ad}}`;
        grp.appendChild(opt);
      }});
      sel.appendChild(grp);
    }});
  }}
  populateExportSelect();

  function selectAllExportFunds() {{
    document.querySelectorAll('#exportFunds option').forEach(o => o.selected = true);
  }}
  function clearExportFunds() {{
    document.querySelectorAll('#exportFunds option').forEach(o => o.selected = false);
  }}

  (function setDefaultExportDates() {{
    let minD = null, maxD = null;
    FUNDS.forEach(f => f.hist.forEach(([d]) => {{
      if (!minD || d < minD) minD = d;
      if (!maxD || d > maxD) maxD = d;
    }}));
    if (minD && maxD) {{
      const startEl = document.getElementById('exportStart');
      const endEl = document.getElementById('exportEnd');
      startEl.min = minD; startEl.max = maxD; startEl.value = minD;
      endEl.min = minD; endEl.max = maxD; endEl.value = maxD;
    }}
  }})();

  function exportExcel() {{
    const status = document.getElementById('exportStatus');
    const kods = Array.from(document.getElementById('exportFunds').selectedOptions).map(o => o.value);
    const start = document.getElementById('exportStart').value;
    const end = document.getElementById('exportEnd').value;
    if (!kods.length) {{ status.innerHTML = '<span class="neg">En az bir fon seçin.</span>'; return; }}
    if (!start || !end || start > end) {{ status.innerHTML = '<span class="neg">Geçerli bir tarih aralığı seçin.</span>'; return; }}

    const selFunds = FUNDS.filter(f => kods.includes(f.kod));
    const dateSet = new Set();
    selFunds.forEach(f => f.hist.forEach(([d]) => {{ if (d >= start && d <= end) dateSet.add(d); }}));
    const dates = Array.from(dateSet).sort();
    if (!dates.length) {{ status.innerHTML = '<span class="neg">Seçilen aralıkta veri bulunamadı.</span>'; return; }}

    const header = ['Tarih', ...selFunds.map(f => `${{f.kod}} (${{f.sirket}})`)];
    const aoa = [header];
    dates.forEach(d => {{
      const row = [d];
      selFunds.forEach(f => {{
        const entry = f.hist.find(h => h[0] === d);
        row.push(entry ? entry[1] : '');
      }});
      aoa.push(row);
    }});

    const ws = XLSX.utils.aoa_to_sheet(aoa);
    ws['!cols'] = header.map(() => ({{ wch: 18 }}));
    const wb = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(wb, ws, 'Fon Verileri');
    XLSX.writeFile(wb, `tefas_fon_verileri_${{start}}_${{end}}.xlsx`);
    status.innerHTML = `<span class="pos">${{dates.length}} günlük veri, ${{selFunds.length}} fon için indirildi.</span>`;
  }}
</script>
</body>
</html>"""
    return html


def build(date_str=None, prices=None):
    """Load data, optionally add a new day's prices, regenerate the report."""
    data = load_data()
    if prices:
        data = add_day(data, date_str, prices)
        save_data(data)
    rows = compute_rows(data)
    html = render_html(data, rows)
    os.makedirs(os.path.dirname(REPORT_FILE), exist_ok=True)
    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        f.write(html)
    karar_html = render_karar_html(rows)
    with open(KARAR_FILE, "w", encoding="utf-8") as f:
        f.write(karar_html)
    karsilastir_html = render_karsilastir_html(rows)
    with open(KARSILASTIR_FILE, "w", encoding="utf-8") as f:
        f.write(karsilastir_html)
    fon_detay_html = render_fon_detay_html(rows)
    with open(FON_DETAY_FILE, "w", encoding="utf-8") as f:
        f.write(fon_detay_html)
    disaaktar_html = render_disaaktar_html(rows)
    with open(DISAAKTAR_FILE, "w", encoding="utf-8") as f:
        f.write(disaaktar_html)
    return rows
