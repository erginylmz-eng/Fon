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
            "hist": [[h["tarih"], h["fiyat"]] for h in hist],
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
    son_tarih = data.get("son_guncelleme", "")

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
            "hist": r["hist"],
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
  .addfund-row {{ display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }}
  .addfund-row input {{
    background: var(--bg); border: 1px solid var(--border); color: var(--text);
    border-radius: 8px; padding: 9px 12px; font-size: 13px; font-family: inherit;
  }}
  .addfund-row input#newKod {{ width: 110px; text-transform: uppercase; }}
  .addfund-row input#newSirket {{ flex: 1; min-width: 160px; }}
  .addfund-row input#newRisk {{ width: 90px; }}
  .btn {{
    background: var(--accent); color: #fff; border: none; border-radius: 8px;
    padding: 9px 16px; font-size: 13px; font-weight: 600; cursor: pointer; font-family: inherit;
  }}
  .btn:hover {{ opacity: .9; }}
  .btn.secondary {{ background: transparent; border: 1px solid var(--border); color: var(--text); }}
  .btn-row {{ display: flex; gap: 8px; margin-top: 10px; }}
  .addfund-help {{ font-size: 12px; color: var(--muted); margin-top: 10px; line-height: 1.6; }}
  .addfund-help a {{ color: var(--accent); }}
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
    <h2>Yeni Fon Ekle</h2>
    <div class="addfund-row">
      <input id="newKod" placeholder="Fon Kodu (örn. AAL)" maxlength="10">
      <input id="newSirket" placeholder="Firma Adı (örn. Ata Portföy)">
      <input id="newRisk" placeholder="Risk 1-7 (opsiyonel)" maxlength="1">
      <button class="btn" onclick="addFund()">Listeye Ekle</button>
    </div>
    <div class="btn-row">
      <button class="btn secondary" onclick="runNow()">Raporu Şimdi Güncelle</button>
      <button class="btn secondary" onclick="resetGithubConfig()">GitHub Bağlantısını Sıfırla</button>
    </div>
    <div id="addFundStatus" class="addfund-help"></div>
    <div class="addfund-help">
      Fon eklemek için bir GitHub <b>Personal Access Token</b> gerekir (sadece bu tarayıcınızda saklanır,
      kimseyle paylaşılmaz). Repo → Settings → Developer settings → Personal access tokens →
      Fine-grained tokens → sadece bu repo, izinler: <b>Contents: Read and write</b>,
      <b>Actions: Read and write</b>. İlk "Listeye Ekle" veya "Raporu Şimdi Güncelle" tıklamanızda
      GitHub kullanıcı adı / repo adı / token sorulacak.
    </div>
  </div>

  <div class="card">
    <h2 id="chartTitle">Tüm Fonlar — Günlük Getiri Karşılaştırması</h2>
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
  const REPO_PATH = 'data/fon_listesi.csv';
  const WORKFLOW_FILE = 'daily-update.yml';

  function getGithubConfig(forcePrompt) {{
    let owner = localStorage.getItem('tefas_gh_owner') || '';
    let repo = localStorage.getItem('tefas_gh_repo') || '';
    let token = localStorage.getItem('tefas_gh_token') || '';
    if (forcePrompt || !owner || !repo || !token) {{
      owner = prompt('GitHub kullanıcı adınız:', owner) || owner;
      repo = prompt('Repo adı:', repo) || repo;
      token = prompt('GitHub Personal Access Token (sadece bu tarayıcıda saklanır):', '') || token;
      if (owner) localStorage.setItem('tefas_gh_owner', owner);
      if (repo) localStorage.setItem('tefas_gh_repo', repo);
      if (token) localStorage.setItem('tefas_gh_token', token);
    }}
    return {{ owner, repo, token }};
  }}

  function resetGithubConfig() {{
    localStorage.removeItem('tefas_gh_owner');
    localStorage.removeItem('tefas_gh_repo');
    localStorage.removeItem('tefas_gh_token');
    getGithubConfig(true);
  }}

  function b64EncodeUtf8(str) {{
    return btoa(unescape(encodeURIComponent(str)));
  }}
  function b64DecodeUtf8(str) {{
    return decodeURIComponent(escape(atob(str.replace(/\\n/g, ''))));
  }}

  async function addFund() {{
    const kod = document.getElementById('newKod').value.trim().toUpperCase();
    const sirket = document.getElementById('newSirket').value.trim();
    const risk = document.getElementById('newRisk').value.trim();
    const status = document.getElementById('addFundStatus');
    if (!kod || !sirket) {{
      status.innerHTML = '<span class="neg">Fon kodu ve firma adı zorunlu.</span>';
      return;
    }}
    const {{ owner, repo, token }} = getGithubConfig(false);
    if (!owner || !repo || !token) {{
      status.innerHTML = '<span class="neg">GitHub bilgileri eksik.</span>';
      return;
    }}
    status.textContent = 'Ekleniyor...';
    try {{
      const apiUrl = `https://api.github.com/repos/${{owner}}/${{repo}}/contents/${{REPO_PATH}}`;
      const getRes = await fetch(apiUrl, {{ headers: {{ Authorization: `token ${{token}}` }} }});
      if (!getRes.ok) throw new Error('CSV okunamadı (HTTP ' + getRes.status + ')');
      const getData = await getRes.json();
      let content = b64DecodeUtf8(getData.content);
      if (!content.endsWith('\\n')) content += '\\n';
      content += `${{kod}},${{sirket}},${{risk}}\\n`;
      const putRes = await fetch(apiUrl, {{
        method: 'PUT',
        headers: {{ Authorization: `token ${{token}}`, 'Content-Type': 'application/json' }},
        body: JSON.stringify({{
          message: `Fon eklendi: ${{kod}}`,
          content: b64EncodeUtf8(content),
          sha: getData.sha,
        }}),
      }});
      if (!putRes.ok) throw new Error('Kaydedilemedi (HTTP ' + putRes.status + ')');
      status.innerHTML = `<span class="pos">${{kod}} listeye eklendi.</span> "Raporu Şimdi Güncelle"ye basarak hemen çekebilir ya da bir sonraki otomatik çalıştırmayı bekleyebilirsiniz.`;
      document.getElementById('newKod').value = '';
      document.getElementById('newSirket').value = '';
      document.getElementById('newRisk').value = '';
    }} catch (e) {{
      status.innerHTML = `<span class="neg">Hata: ${{e.message}}</span>`;
    }}
  }}

  async function runNow() {{
    const status = document.getElementById('addFundStatus');
    const {{ owner, repo, token }} = getGithubConfig(false);
    if (!owner || !repo || !token) {{
      status.innerHTML = '<span class="neg">GitHub bilgileri eksik.</span>';
      return;
    }}
    status.textContent = 'Çalıştırma tetikleniyor...';
    try {{
      const res = await fetch(
        `https://api.github.com/repos/${{owner}}/${{repo}}/actions/workflows/${{WORKFLOW_FILE}}/dispatches`,
        {{
          method: 'POST',
          headers: {{ Authorization: `token ${{token}}`, 'Content-Type': 'application/json' }},
          body: JSON.stringify({{ ref: 'main' }}),
        }}
      );
      if (res.status === 204) {{
        status.innerHTML = '<span class="pos">Tetiklendi.</span> Actions sekmesinden takip edebilirsiniz, birkaç dakika sonra bu sayfayı yenileyin.';
      }} else {{
        throw new Error('HTTP ' + res.status);
      }}
    }} catch (e) {{
      status.innerHTML = `<span class="neg">Hata: ${{e.message}}</span>`;
    }}
  }}

  // ---- Dönem bazlı (Günlük/Haftalık/Aylık/Yıllık) dinamik rapor ----
  const FUNDS = {funds_json};
  const SIRKET_ORDER = {sirket_order_json};
  const PERIOD_DAYS = {{ gunluk: 1, haftalik: 7, aylik: 30, yillik: 365 }};
  const PERIOD_LABELS = {{ gunluk: 'Günlük', haftalik: 'Haftalık', aylik: 'Aylık', yillik: 'Yıllık' }};
  const riskColor = {{ 1: 'rgba(79,140,255,0.85)', 2: 'rgba(245,166,35,0.85)' }};
  const riskColorHover = {{ 1: 'rgba(79,140,255,1)', 2: 'rgba(245,166,35,1)' }};
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

  const mainChart = new Chart(document.getElementById('returnChart'), {{
    type: 'bar',
    data: {{ labels: [], datasets: [{{ label: 'Getiri (%)', data: [], backgroundColor: [], hoverBackgroundColor: [], borderRadius: 4 }}] }},
    options: {{
      responsive: true, maintainAspectRatio: false,
      scales: {{
        x: {{ ticks: {{ color: '#8b93a7', maxRotation: 90, minRotation: 90, autoSkip: false, font: {{ size: 9 }} }}, grid: {{ color: '#2a3243' }} }},
        y: {{ ticks: {{ color: '#8b93a7' }}, grid: {{ color: '#2a3243' }} }}
      }},
      plugins: {{
        legend: {{ display: false }},
        tooltip: {{ callbacks: {{ afterLabel: (item) => {{
          const risks = item.chart.__risks || [];
          return risks[item.dataIndex] ? ('Risk ' + risks[item.dataIndex] + '/7') : '';
        }} }} }}
      }}
    }}
  }});

  function buildSparkline(canvas, series) {{
    if (series.length < 2) return;
    const min = Math.min(...series), max = Math.max(...series);
    sparkCharts[canvas.dataset.kod] = new Chart(canvas, {{
      type: 'line',
      data: {{ labels: series.map((_, i) => i), datasets: [{{ data: series, borderColor: '#4f8cff', borderWidth: 1.5, pointRadius: 0, tension: 0.3, fill: false }}] }},
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
      return {{ kod: f.kod, ad: f.ad, sirket: f.sirket, risk: f.risk, ret, fiyat, series }};
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
    mainChart.data.labels = chartFunds.map(f => `${{f.sirket}} (${{f.kod}})`);
    mainChart.data.datasets[0].data = chartFunds.map(f => Math.round(f.ret * 10000) / 10000);
    mainChart.data.datasets[0].label = label + ' Getiri (%)';
    const risks = chartFunds.map(f => f.risk);
    mainChart.data.datasets[0].backgroundColor = risks.map(r => riskColor[r] || 'rgba(139,147,167,0.7)');
    mainChart.data.datasets[0].hoverBackgroundColor = risks.map(r => riskColorHover[r] || 'rgba(139,147,167,0.9)');
    mainChart.__risks = risks;
    mainChart.update();

    const bySirket = {{}};
    computed.forEach(f => {{ (bySirket[f.sirket] = bySirket[f.sirket] || []).push(f); }});

    SIRKET_ORDER.forEach(sirket => {{
      const rows = (bySirket[sirket] || []).slice().sort(sortByRet);
      const tbody = document.getElementById('tbody-' + slug(sirket));
      if (!tbody) return;
      tbody.innerHTML = rows.map(r => `
        <tr>
          <td class="code">${{r.kod}}</td>
          <td class="name">${{r.ad}}</td>
          <td class="num muted">${{r.risk ? r.risk + '/7' : '—'}}</td>
          <td class="num">${{fmtPrice(r.fiyat)}}</td>
          <td class="num">${{fmtPct(r.ret)}}</td>
          <td class="spark"><canvas class="sparkline" data-kod="${{r.kod}}" width="120" height="32"></canvas></td>
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
