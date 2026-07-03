"""
article_generator.py — article_data.json から新規記事パフォーマンス HTML を生成し
                        GitHub にアップロードする
"""

import base64
import datetime
import json
import os
import requests

GITHUB_USERNAME = "tsuyoshi-iwahori-dev"
GITHUB_REPO     = "gsc-report"
GITHUB_API      = "https://api.github.com"


def _get_github_token():
    token = os.environ.get("GITHUB_TOKEN_VALUE", "")
    if not token:
        token_path = os.path.join(os.path.dirname(__file__), '..', 'GitHub_Token.txt')
        if os.path.exists(token_path):
            with open(token_path, encoding='utf-8') as f:
                token = f.read().strip()
    return token


def _github_put(github_path: str, content_bytes: bytes, token: str, message: str):
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
    }
    url = f"{GITHUB_API}/repos/{GITHUB_USERNAME}/{GITHUB_REPO}/contents/{github_path}"
    r = requests.get(url, headers=headers)
    sha = r.json().get("sha") if r.status_code == 200 else None

    body = {
        "message": message,
        "content": base64.b64encode(content_bytes).decode("utf-8"),
    }
    if sha:
        body["sha"] = sha

    resp = requests.put(url, headers=headers, json=body)
    if resp.status_code in [200, 201]:
        pub_url = f"https://{GITHUB_USERNAME}.github.io/{GITHUB_REPO}/{github_path}"
        print(f"  OK {pub_url}")
        return pub_url
    else:
        print(f"  NG {github_path}: {resp.status_code} {resp.text[:120]}")
        return ""


def _esc(s) -> str:
    return str(s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


_COMMON_CSS = """
*{box-sizing:border-box;margin:0;padding:0;}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;font-size:14px;color:#1a1a1a;background:#f5f5f3;}
a{color:#185fa5;text-decoration:none;}
a:hover{text-decoration:underline;}
.wrap{max-width:1800px;margin:0 auto;padding:24px 16px;}
.page-header{background:#fff;border:0.5px solid #e0e0dc;border-radius:10px;padding:14px 20px;margin-bottom:16px;display:flex;align-items:center;justify-content:space-between;}
.page-title{font-size:16px;font-weight:600;}
.back-link{font-size:12px;color:#185fa5;padding:4px 10px;border:0.5px solid #c5d3f0;border-radius:20px;background:#f0f4ff;}
.back-link:hover{background:#dce6ff;}
.tab-bar{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:14px;}
.tab-btn{font-size:12px;padding:5px 12px;border-radius:20px;border:0.5px solid #e0e0dc;background:#fff;cursor:pointer;color:#555;transition:all 0.15s;}
.tab-btn.active{background:#1F3864;color:#fff;border-color:#1F3864;}
.tab-btn:hover:not(.active){background:#f0f4ff;border-color:#c5d3f0;}
.card{background:#fff;border:0.5px solid #e0e0dc;border-radius:10px;padding:16px 20px;margin-bottom:14px;}
.table-card{background:#fff;border:0.5px solid #e0e0dc;border-radius:10px;margin-bottom:14px;overflow-x:auto;}
table{width:max-content;min-width:100%;border-collapse:collapse;font-size:12px;}
th{text-align:left;padding:6px 10px;color:#888;border-bottom:0.5px solid #e0e0dc;font-weight:500;white-space:nowrap;}
td{padding:5px 10px;border-bottom:0.5px solid #e0e0dc;vertical-align:middle;white-space:nowrap;}
tr:last-child td{border-bottom:none;}
tr:hover td{background:#fafaf8;}
.url-cell{color:#185fa5;max-width:200px;overflow:hidden;text-overflow:ellipsis;}
.title-cell{max-width:220px;overflow:hidden;text-overflow:ellipsis;}
.kw-cell{white-space:nowrap;}
.kw-badge{font-size:10px;padding:2px 6px;border-radius:20px;background:#f0f4ff;color:#185fa5;border:0.5px solid #c5d3f0;display:inline-block;margin:1px;white-space:nowrap;}
.num-cell{text-align:right;white-space:nowrap;font-variant-numeric:tabular-nums;}
.footer{text-align:center;font-size:11px;color:#aaa;padding:24px 0;}
.summary-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:12px;margin-bottom:14px;}
.summary-card{background:#fff;border:0.5px solid #e0e0dc;border-radius:10px;padding:14px 16px;text-align:center;}
.summary-val{font-size:22px;font-weight:700;color:#1F3864;}
.summary-lbl{font-size:11px;color:#888;margin-top:4px;}
"""


# ── 一覧ページ ────────────────────────────────────────────────────────────────

def _build_index_html(article_data: dict) -> str:
    generated_at = article_data.get("generated_at", "")
    clients_data = article_data.get("clients", {})

    all_articles = []
    for client_name, client_obj in clients_data.items():
        for art in client_obj.get("articles", []):
            all_articles.append({"client": client_name, **art})

    client_names = list(clients_data.keys())

    tab_btns = '<button class="tab-btn active" data-client="all" onclick="switchTab(\'all\',this)">すべて</button>\n'
    for c in client_names:
        tab_btns += f'<button class="tab-btn" data-client="{_esc(c)}" onclick="switchTab(\'{_esc(c)}\',this)">{_esc(c)}</button>\n'

    def _fmt_int(v):
        if v is None:
            return "-"
        try:
            return f"{int(v):,}"
        except (TypeError, ValueError):
            return "-"

    def _fmt_pos(v):
        if v is None or v == 0:
            return "-"
        try:
            return f"{float(v):.1f}"
        except (TypeError, ValueError):
            return "-"

    today = datetime.date.today()
    rows_html = ""
    for idx, art in enumerate(all_articles):
        pub = art.get("published_at", "")
        try:
            elapsed_weeks = (today - datetime.date.fromisoformat(pub)).days // 7
        except ValueError:
            elapsed_weeks = "-"

        weekly_data = art.get("weekly_data") or []
        latest = weekly_data[-1] if weekly_data else {}
        clicks      = _fmt_int(latest.get("clicks"))
        impressions = _fmt_int(latest.get("impressions"))
        position    = _fmt_pos(latest.get("position"))
        sessions    = _fmt_int(latest.get("sessions"))

        url   = art.get("url", "")
        title = art.get("title", "") or "-"
        url_disp   = (url[:40] + "…")   if len(url)   > 40 else url
        title_disp = (title[:35] + "…") if len(title) > 35 else title

        kws = [k for k in (art.get("top_keywords") or []) if k]
        kw_html = "".join(f'<span class="kw-badge">{_esc(k)}</span>' for k in kws) or "-"

        rows_html += f"""<tr data-client="{_esc(art['client'])}">
  <td style="white-space:nowrap;font-weight:500;">{_esc(art['client'])}</td>
  <td class="url-cell" title="{_esc(url)}"><a href="{_esc(url)}" target="_blank" rel="noopener">{_esc(url_disp)}</a></td>
  <td class="title-cell" title="{_esc(title)}">{_esc(title_disp)}</td>
  <td style="white-space:nowrap;">{_esc(pub or '-')}</td>
  <td style="text-align:center;white-space:nowrap;">{elapsed_weeks}週</td>
  <td class="num-cell">{clicks}</td>
  <td class="num-cell">{impressions}</td>
  <td class="num-cell">{position}</td>
  <td class="num-cell">{sessions}</td>
  <td class="kw-cell">{kw_html}</td>
  <td style="white-space:nowrap;"><a href="./detail_{idx}.html" style="font-size:12px;padding:3px 10px;border:0.5px solid #c5d3f0;border-radius:5px;background:#f0f4ff;">詳細 →</a></td>
</tr>"""

    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<meta name="robots" content="noindex, nofollow">
<title>新規記事パフォーマンス</title>
<style>{_COMMON_CSS}</style>
</head>
<body>
<div class="wrap">
  <div class="page-header">
    <div style="display:flex;align-items:center;gap:14px;">
      <a href="../" class="back-link">← レポート一覧</a>
      <span class="page-title">📝 新規記事パフォーマンス</span>
    </div>
    <span style="font-size:11px;color:#aaa;">更新: {_esc(generated_at)}</span>
  </div>

  <div class="tab-bar" id="tabBar">
    {tab_btns}
  </div>

  <div class="table-card">
    <table>
      <thead><tr>
        <th>クライアント</th><th>URL</th><th>タイトル</th>
        <th>公開日</th><th>経過</th>
        <th style="text-align:right;">クリック</th>
        <th style="text-align:right;">表示回数</th>
        <th style="text-align:right;">平均順位</th>
        <th style="text-align:right;">セッション</th>
        <th>上位KW</th><th></th>
      </tr></thead>
      <tbody id="tableBody">{rows_html}</tbody>
    </table>
  </div>
  <div class="footer">自動生成 — 新規記事パフォーマンス</div>
</div>
<script>
function switchTab(client, btn) {{
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  document.querySelectorAll('#tableBody tr').forEach(tr => {{
    tr.style.display = (client === 'all' || tr.dataset.client === client) ? '' : 'none';
  }});
}}
</script>
</body>
</html>"""


# ── 詳細ページ ────────────────────────────────────────────────────────────────

def _build_summary_html(weekly_data: list) -> str:
    if not weekly_data:
        return ""

    total_clicks      = sum(w.get("clicks", 0) or 0 for w in weekly_data)
    total_impressions = sum(w.get("impressions", 0) or 0 for w in weekly_data)
    latest            = weekly_data[-1]
    latest_pos        = latest.get("position") or 0
    latest_sessions   = latest.get("sessions") or 0

    def fmt(v, decimals=0):
        if v is None:
            return "-"
        if decimals:
            return f"{v:.{decimals}f}"
        return f"{int(v):,}"

    return f"""<div class="summary-grid">
  <div class="summary-card"><div class="summary-val">{fmt(total_clicks)}</div><div class="summary-lbl">累積クリック数</div></div>
  <div class="summary-card"><div class="summary-val">{fmt(total_impressions)}</div><div class="summary-lbl">累積表示回数</div></div>
  <div class="summary-card"><div class="summary-val">{fmt(latest_pos, 1)}</div><div class="summary-lbl">直近平均順位</div></div>
  <div class="summary-card"><div class="summary-val">{fmt(latest_sessions)}</div><div class="summary-lbl">直近週セッション</div></div>
  <div class="summary-card"><div class="summary-val">{len(weekly_data)}</div><div class="summary-lbl">計測週数</div></div>
</div>"""


def _build_detail_html(article: dict, client_name: str, art_index: int, total: int) -> str:
    url          = article.get("url", "")
    title        = article.get("title", "") or url
    published_at = article.get("published_at", "")
    keywords     = [k for k in (article.get("top_keywords") or []) if k][:3]
    weekly_data  = article.get("weekly_data") or []

    summary_html = _build_summary_html(weekly_data)

    kw_badges = " ".join(f'<span class="kw-badge">{_esc(k)}</span>' for k in keywords)

    prev_link = f'<a href="./detail_{art_index-1}.html" style="font-size:12px;color:#185fa5;">← 前の記事</a>' if art_index > 0 else ''
    next_link = f'<a href="./detail_{art_index+1}.html" style="font-size:12px;color:#185fa5;">次の記事 →</a>' if art_index < total - 1 else ''

    weekly_json   = json.dumps(weekly_data, ensure_ascii=False)
    keywords_json = json.dumps(keywords, ensure_ascii=False)

    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<meta name="robots" content="noindex, nofollow">
<title>{_esc(title)} — 新規記事パフォーマンス</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.5.1/dist/chart.umd.min.js"></script>
<style>
{_COMMON_CSS}
.detail-meta{{font-size:12px;color:#666;margin-top:4px;}}
.tab-panel{{display:none;}}
.tab-panel.active{{display:block;}}
canvas{{max-height:320px;}}
</style>
</head>
<body>
<div class="wrap">

  <!-- ヘッダー -->
  <div class="page-header" style="flex-direction:column;align-items:flex-start;gap:8px;">
    <div style="display:flex;align-items:center;gap:12px;width:100%;">
      <a href="./index.html" class="back-link">← 一覧に戻る</a>
      <span style="font-size:11px;color:#aaa;margin-left:auto;">{prev_link}&nbsp;&nbsp;{next_link}</span>
    </div>
    <div>
      <div class="page-title">{_esc(title)}</div>
      <div class="detail-meta">
        <a href="{_esc(url)}" target="_blank" rel="noopener">{_esc(url)}</a>
        &nbsp;|&nbsp; {_esc(client_name)}
        &nbsp;|&nbsp; 公開日: {_esc(published_at)}
      </div>
      {('<div style="margin-top:6px;">' + kw_badges + '</div>') if kw_badges else ''}
    </div>
  </div>

  <!-- サマリー -->
  {summary_html}

  <!-- グラフタブ -->
  <div class="tab-bar" id="chartTabBar">
    <button class="tab-btn active" onclick="showChart('clicks',this)">クリック数</button>
    <button class="tab-btn" onclick="showChart('impressions',this)">表示回数</button>
    <button class="tab-btn" onclick="showChart('ctr',this)">CTR</button>
    <button class="tab-btn" onclick="showChart('position',this)">平均順位</button>
    <button class="tab-btn" onclick="showChart('sessions',this)">セッション数</button>
    <button class="tab-btn" onclick="showChart('kw',this)">KW順位</button>
  </div>

  <div class="card">
    <div id="panel-clicks"      class="tab-panel active"><canvas id="chart-clicks"></canvas></div>
    <div id="panel-impressions" class="tab-panel"><canvas id="chart-impressions"></canvas></div>
    <div id="panel-ctr"         class="tab-panel"><canvas id="chart-ctr"></canvas></div>
    <div id="panel-position"    class="tab-panel"><canvas id="chart-position"></canvas></div>
    <div id="panel-sessions"    class="tab-panel"><canvas id="chart-sessions"></canvas></div>
    <div id="panel-kw"          class="tab-panel"><canvas id="chart-kw"></canvas></div>
  </div>

  <div class="footer">自動生成 — 新規記事パフォーマンス</div>
</div>

<script>
const WEEKLY   = {weekly_json};
const KEYWORDS = {keywords_json};

// X軸ラベル: 「1週目」「2週目」...
const LABELS = WEEKLY.map(w => w.week_number ? w.week_number + '週目' : w.week);

const CHART_OPTS_BASE = {{
  responsive: true,
  interaction: {{ mode: 'index', intersect: false }},
  plugins: {{
    legend: {{ labels: {{ font: {{ size: 11 }} }} }},
    tooltip: {{
      callbacks: {{
        title: (items) => WEEKLY[items[0].dataIndex]?.week + '（' + items[0].label + '）',
      }},
    }},
  }},
  scales: {{
    x: {{ ticks: {{ font: {{ size: 11 }} }} }},
    y: {{ ticks: {{ font: {{ size: 11 }}, precision: 0 }}, beginAtZero: true }},
  }},
}};

function makeLineDS(label, data, color, fill=false) {{
  return {{
    label, data,
    borderColor: color, backgroundColor: color + '33',
    borderWidth: 2, pointRadius: 4, tension: 0.3, fill,
  }};
}}

const charts = {{}};

function buildChart(id, datasets, reverseY=false, yLabel='') {{
  const ctx = document.getElementById('chart-' + id).getContext('2d');
  const opts = JSON.parse(JSON.stringify(CHART_OPTS_BASE));
  opts.scales.y.reverse = reverseY;
  if (yLabel) opts.scales.y.title = {{ display: true, text: yLabel, font: {{ size: 11 }} }};
  if (reverseY) opts.scales.y.beginAtZero = false;
  if (charts[id]) charts[id].destroy();
  charts[id] = new Chart(ctx, {{ type: 'line', data: {{ labels: LABELS, datasets }}, options: opts }});
}}

function initCharts() {{
  buildChart('clicks',
    [makeLineDS('クリック数', WEEKLY.map(w => w.clicks ?? null), '#2563eb', true)]);

  buildChart('impressions',
    [makeLineDS('表示回数', WEEKLY.map(w => w.impressions ?? null), '#059669', true)]);

  buildChart('ctr',
    [makeLineDS('CTR (%)', WEEKLY.map(w => w.ctr ?? null), '#7c3aed', true)], false, '%');

  buildChart('position',
    [makeLineDS('平均順位', WEEKLY.map(w => w.position ?? null), '#d97706')], true, '位');

  buildChart('sessions',
    [makeLineDS('セッション数', WEEKLY.map(w => w.sessions ?? null), '#0891b2', true)]);

  const kwColors = ['#e11d48', '#16a34a', '#7c3aed'];
  const kwDS = KEYWORDS.map((kw, i) => {{
    const data = WEEKLY.map(w => (w.kw_positions && w.kw_positions[kw] != null) ? w.kw_positions[kw] : null);
    return makeLineDS(kw, data, kwColors[i % kwColors.length]);
  }});
  if (kwDS.length > 0) {{
    buildChart('kw', kwDS, true, '位');
  }} else {{
    document.getElementById('panel-kw').innerHTML = '<p style="color:#aaa;padding:20px;text-align:center;">KWデータなし</p>';
  }}
}}

function showChart(name, btn) {{
  document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('#chartTabBar .tab-btn').forEach(b => b.classList.remove('active'));
  document.getElementById('panel-' + name).classList.add('active');
  btn.classList.add('active');
}}

window.addEventListener('load', initCharts);
</script>
</body>
</html>"""


# ── メイン ───────────────────────────────────────────────────────────────────

def generate_article_pages(article_data: dict, output_dir: str, dry_run: bool = False):
    print("\n===== article_generator 開始 =====")

    clients_data = article_data.get("clients", {})
    all_articles = []
    for client_name, client_obj in clients_data.items():
        for art in client_obj.get("articles", []):
            all_articles.append((client_name, art))

    if not all_articles:
        print("  記事が空のためスキップ")
        return

    os.makedirs(output_dir, exist_ok=True)

    token = _get_github_token()
    today = datetime.date.today().isoformat()
    files = []

    # 一覧ページ
    index_html = _build_index_html(article_data)
    index_path = os.path.join(output_dir, "index.html")
    with open(index_path, "w", encoding="utf-8") as f:
        f.write(index_html)
    files.append((index_path, "article/index.html"))
    print(f"  生成: index.html")

    # 詳細ページ
    total = len(all_articles)
    for idx, (client_name, article) in enumerate(all_articles):
        detail_html = _build_detail_html(article, client_name, idx, total)
        fname = f"detail_{idx}.html"
        detail_path = os.path.join(output_dir, fname)
        with open(detail_path, "w", encoding="utf-8") as f:
            f.write(detail_html)
        files.append((detail_path, f"article/{fname}"))
        print(f"  生成: {fname} ({client_name} / {article.get('url','')})")

    # GitHub アップロード
    if not dry_run and token:
        print(f"\n  GitHubアップロード中 ({len(files)}ファイル)...")
        for local_path, github_path in files:
            with open(local_path, "rb") as f:
                content_bytes = f.read()
            _github_put(github_path, content_bytes, token, f"Update article: {today}")
    elif not token:
        print("  ⚠ GitHub Token が未設定のためアップロードをスキップ")
    else:
        print("  dry-run のためアップロードをスキップ")

    pub_url = f"https://{GITHUB_USERNAME}.github.io/{GITHUB_REPO}/article/"
    print(f"\n  記事ページ: {pub_url}")
    print("===== article_generator 完了 =====")
    return pub_url


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', default=os.path.join(os.path.dirname(__file__), 'reports', 'article_data.json'))
    parser.add_argument('--output-dir', default=os.path.join(os.path.dirname(__file__), 'reports', 'article'))
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    with open(args.input, encoding='utf-8') as f:
        data = json.load(f)
    generate_article_pages(data, args.output_dir, dry_run=args.dry_run)
