"""
Ortak veri/rapor mantığı: JSON veri dosyasını okur/günceller ve firma bazlı
HTML raporunu üretir. fetch_and_build.py tarafından kullanılır.
"""
import json
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_FILE = os.path.join(BASE_DIR, "data", "tefas_veri.json")
REPORT_FILE = os.path.join(BASE_DIR, "docs", "index.html")

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
        rows.append({
            "kod": code,
            "ad": fund["ad"],
            "sirket": fund.get("sirket", "Diğer"),
            "risk": fund.get("risk"),
            "tarih": last["tarih"],
            "fiyat": last["fiyat"],
            "gunluk_getiri": daily_return,
            "seri": [h["fiyat"] for h in recent],
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


def render_html(data, rows):
    son_tarih = data.get("son_guncelleme", "")

    by_sirket = {}
    for r in rows:
        by_sirket.setdefault(r["sirket"], []).append(r)

    ordered_sirketler = [s for s in SIRKET_SIRASI if s in by_sirket]
    ordered_sirketler += [s for s in by_sirket if s not in SIRKET_SIRASI]

    sections_html = ""
    for sirket in ordered_sirketler:
        srows = sorted(
            by_sirket[sirket],
            key=lambda r: (r["gunluk_getiri"] is None, -(r["gunluk_getiri"] or 0)),
        )
        table_rows = ""
        for r in srows:
            table_rows += f"""
        <tr>
          <td class="code">{r['kod']}</td>
          <td class="name">{r['ad']}</td>
          <td class="num muted">{r['risk']}/7</td>
          <td class="num">{fmt_price(r['fiyat'])}</td>
          <td class="num">{fmt_pct(r['gunluk_getiri'])}</td>
          <td class="spark"><canvas class="sparkline" data-series='{json.dumps(r["seri"])}' width="120" height="32"></canvas></td>
        </tr>"""
        n = len(srows)
        with_ret = [r["gunluk_getiri"] for r in srows if r["gunluk_getiri"] is not None]
        avg = sum(with_ret) / len(with_ret) if with_ret else None
        avg_str = f"{avg:.4f}%" if avg is not None else "—"
        sections_html += f"""
  <div class="card" id="{sirket.replace(' ', '-')}">
    <h2>{sirket} <span class="muted">· {n} fon · ortalama {avg_str}</span></h2>
    <table>
      <thead>
        <tr>
          <th>Kod</th>
          <th>Fon Adı</th>
          <th style="text-align:right">Risk</th>
          <th style="text-align:right">Fiyat (Birim Pay)</th>
          <th style="text-align:right">Günlük Getiri</th>
          <th style="text-align:right">Son 30 Gün</th>
        </tr>
      </thead>
      <tbody>
        {table_rows}
      </tbody>
    </table>
  </div>"""

    all_with_return = [r["gunluk_getiri"] for r in rows if r["gunluk_getiri"] is not None]
    avg_return = sum(all_with_return) / len(all_with_return) if all_with_return else None
    n_funds = len(rows)
    n_sirket = len(ordered_sirketler)

    rows_sorted_all = sorted(
        rows, key=lambda r: (r["gunluk_getiri"] is None, -(r["gunluk_getiri"] or 0))
    )
    top = rows_sorted_all[0] if rows_sorted_all and rows_sorted_all[0]["gunluk_getiri"] is not None else None

    chart_labels = json.dumps([f'{r["sirket"]} ({r["kod"]})' for r in rows_sorted_all if r["gunluk_getiri"] is not None])
    chart_values = json.dumps([round(r["gunluk_getiri"], 4) for r in rows_sorted_all if r["gunluk_getiri"] is not None])
    chart_risks = json.dumps([r["risk"] for r in rows_sorted_all if r["gunluk_getiri"] is not None])

    html = f"""<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>TEFAS Para Piyasası Fonları (Firma Bazlı) - Günlük Getiri Raporu</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.0/chart.umd.min.js"></script>
<style>
  :root {{
    --bg: #0f1420; --card: #171d2b; --border: #2a3243; --text: #e6e9ef;
    --muted: #8b93a7; --pos: #3ddc84; --neg: #ff5c72; --accent: #4f8cff;
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
    padding: 14px 18px; min-width: 150px;
  }}
  .stat .label {{ color: var(--muted); font-size: 12px; margin-bottom: 6px; }}
  .stat .value {{ font-size: 20px; font-weight: 600; }}
  .card {{
    background: var(--card); border: 1px solid var(--border); border-radius: 12px;
    padding: 20px; margin-bottom: 20px;
  }}
  .card h2 {{ font-size: 15px; margin: 0 0 16px 0; color: var(--text); font-weight: 700; }}
  .card h2 .muted {{ color: var(--muted); font-weight: 500; font-size: 13px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  th {{
    text-align: left; padding: 10px 12px; color: var(--muted); font-weight: 600;
    border-bottom: 1px solid var(--border); font-size: 11px; text-transform: uppercase; letter-spacing: .03em;
  }}
  td {{ padding: 10px 12px; border-bottom: 1px solid var(--border); vertical-align: middle; }}
  tr:hover td {{ background: rgba(255,255,255,0.02); }}
  .code {{ font-weight: 700; color: var(--accent); }}
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
</style>
</head>
<body>
  <h1>TEFAS Para Piyasası Fonları — Firma Bazlı Günlük Getiri Raporu</h1>
  <div class="subtitle">{n_sirket} kurucu firma · {n_funds} fon (risk 1/7 veya 2/7) · Son güncelleme: {son_tarih}</div>

  <div class="toc">
    {''.join(f'<a href="#{s.replace(" ", "-")}">{s}</a>' for s in ordered_sirketler)}
  </div>

  <div class="summary">
    <div class="stat"><div class="label">Firma Sayısı</div><div class="value">{n_sirket}</div></div>
    <div class="stat"><div class="label">Toplam Fon</div><div class="value">{n_funds}</div></div>
    <div class="stat"><div class="label">Ortalama Günlük Getiri</div><div class="value">{('%.4f%%' % avg_return) if avg_return is not None else '—'}</div></div>
    <div class="stat"><div class="label">En Yüksek Getiri</div><div class="value">{(top['kod'] + ' · ' + top['sirket']) if top else '—'}</div></div>
  </div>

  <div class="card">
    <h2>Tüm Fonlar — Günlük Getiri Karşılaştırması</h2>
    <div class="legend">
      <span><span class="swatch" style="background:#4f8cff"></span>Risk 1/7</span>
      <span><span class="swatch" style="background:#f5a623"></span>Risk 2/7</span>
    </div>
    <div class="chart-wrap"><canvas id="returnChart"></canvas></div>
  </div>

  {sections_html}

  <footer>
    Veri kaynağı: <a href="https://www.tefas.gov.tr/tr/fon-verileri" style="color:var(--accent)">TEFAS Fon Verileri</a>.
    Bu rapor bilgilendirme amaçlıdır, yatırım tavsiyesi değildir. Her iş günü otomatik olarak GitHub Actions ile güncellenir.
  </footer>

<script>
  const ctx = document.getElementById('returnChart');
  const chartRisks = {chart_risks};
  const riskColor = {{ 1: 'rgba(79,140,255,0.85)', 2: 'rgba(245,166,35,0.85)' }};
  const riskColorHover = {{ 1: 'rgba(79,140,255,1)', 2: 'rgba(245,166,35,1)' }};
  new Chart(ctx, {{
    type: 'bar',
    data: {{
      labels: {chart_labels},
      datasets: [{{
        label: 'Günlük Getiri (%)',
        data: {chart_values},
        backgroundColor: chartRisks.map(r => riskColor[r] || 'rgba(139,147,167,0.7)'),
        hoverBackgroundColor: chartRisks.map(r => riskColorHover[r] || 'rgba(139,147,167,0.9)'),
        borderRadius: 4,
      }}]
    }},
    options: {{
      responsive: true, maintainAspectRatio: false,
      scales: {{
        x: {{ ticks: {{ color: '#8b93a7', maxRotation: 90, minRotation: 90, autoSkip: false, font: {{ size: 9 }} }}, grid: {{ color: '#2a3243' }} }},
        y: {{ ticks: {{ color: '#8b93a7' }}, grid: {{ color: '#2a3243' }} }}
      }},
      plugins: {{
        legend: {{ display: false }},
        tooltip: {{
          callbacks: {{
            afterLabel: (item) => 'Risk ' + chartRisks[item.dataIndex] + '/7'
          }}
        }}
      }}
    }}
  }});

  document.querySelectorAll('.sparkline').forEach(canvas => {{
    const series = JSON.parse(canvas.dataset.series);
    if (series.length < 2) return;
    const min = Math.min(...series), max = Math.max(...series);
    new Chart(canvas, {{
      type: 'line',
      data: {{
        labels: series.map((_, i) => i),
        datasets: [{{
          data: series, borderColor: '#4f8cff', borderWidth: 1.5,
          pointRadius: 0, tension: 0.3, fill: false,
        }}]
      }},
      options: {{
        responsive: false, maintainAspectRatio: false,
        scales: {{ x: {{ display: false }}, y: {{ display: false, min, max }} }},
        plugins: {{ legend: {{ display: false }}, tooltip: {{ enabled: false }} }},
        elements: {{ point: {{ radius: 0 }} }}
      }}
    }});
  }});
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
    return rows
