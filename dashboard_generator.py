"""
dashboard_generator.py — dashboard_data.json からダッシュボード HTML を生成し GitHub にアップロードする
"""

import base64
import datetime
import json
import os
import requests

# ── GitHub 設定（github_uploader.py と同じ） ──────────────────────────────
GITHUB_USERNAME = "tsuyoshi-iwahori-dev"
GITHUB_REPO = "gsc-report"
GITHUB_API = "https://api.github.com"

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


# ── CSS 共通 ─────────────────────────────────────────────────────────────────
_COMMON_CSS = """
*{box-sizing:border-box;margin:0;padding:0;}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;font-size:14px;color:#1a1a1a;background:#f5f5f3;}
a{color:#185fa5;text-decoration:none;}
a:hover{text-decoration:underline;}
.wrap{max-width:1000px;margin:0 auto;padding:24px 16px;}
.page-header{background:#fff;border:0.5px solid #e0e0dc;border-radius:10px;padding:14px 20px;margin-bottom:16px;display:flex;align-items:center;justify-content:space-between;}
.page-title{font-size:16px;font-weight:600;}
.back-link{font-size:12px;color:#185fa5;padding:4px 10px;border:0.5px solid #c5d3f0;border-radius:20px;background:#f0f4ff;}
.back-link:hover{background:#dce6ff;}
.tab-bar{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:14px;}
.tab-btn{font-size:12px;padding:5px 12px;border-radius:20px;border:0.5px solid #e0e0dc;background:#fff;cursor:pointer;color:#555;transition:all 0.15s;}
.tab-btn.active{background:#1F3864;color:#fff;border-color:#1F3864;}
.tab-btn:hover:not(.active){background:#f0f4ff;border-color:#c5d3f0;}
.card{background:#fff;border:0.5px solid #e0e0dc;border-radius:10px;padding:16px 20px;margin-bottom:14px;}
table{width:100%;border-collapse:collapse;font-size:12px;}
th{text-align:left;padding:8px 10px;color:#888;border-bottom:0.5px solid #e0e0dc;font-weight:500;white-space:nowrap;}
td{padding:8px 10px;border-bottom:0.5px solid #e0e0dc;vertical-align:top;}
tr:last-child td{border-bottom:none;}
tr:hover td{background:#fafaf8;}
.badge{display:inline-block;font-size:10px;padding:2px 7px;border-radius:20px;background:#e1f5ee;color:#0f6e56;border:0.5px solid #b2dfdb;margin:2px 2px 2px 0;}
.url-cell{color:#185fa5;max-width:220px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}
.footer{text-align:center;font-size:11px;color:#aaa;padding:24px 0;}
"""


# ── 一覧ページ生成 ────────────────────────────────────────────────────────────
def _build_index_html(dashboard_data: dict) -> str:
    generated_at = dashboard_data.get("generated_at", "")
    clients_data = dashboard_data.get("clients", {})

    # 全施策をリスト化（連番付き）
    all_pages = []
    for client_name, client_obj in clients_data.items():
        for page in client_obj.get("pages", []):
            all_pages.append({"client": client_name, **page})

    client_names = list(clients_data.keys())

    # タブ HTML
    tab_btns = '<button class="tab-btn active" data-client="all" onclick="switchTab(\'all\',this)">すべて</button>\n'
    for c in client_names:
        tab_btns += f'<button class="tab-btn" data-client="{_esc(c)}" onclick="switchTab(\'{_esc(c)}\',this)">{_esc(c)}</button>\n'

    # 行 HTML
    rows_html = ""
    for idx, p in enumerate(all_pages):
        actions_html = " ".join(
            f'<span class="badge">{_esc(a.get("date",""))}{(" " + _esc(a.get("label",""))) if a.get("label") else ""}</span>'
            for a in (p.get("actions") or [])
        )
        kws = [k for k in (p.get("keywords") or []) if k]
        kw_html = " ".join(f'<span style="font-size:10px;padding:2px 6px;border-radius:20px;background:#f0f4ff;color:#185fa5;border:0.5px solid #c5d3f0;">{_esc(k)}</span>' for k in kws)
        rows_html += f"""<tr data-client="{_esc(p['client'])}">
  <td style="white-space:nowrap;font-weight:500;">{_esc(p['client'])}</td>
  <td class="url-cell" title="{_esc(p.get('url',''))}"><a href="{_esc(p.get('url',''))}" target="_blank" rel="noopener">{_esc(p.get('url',''))}</a></td>
  <td>{_esc(p.get('title','') or '-')}</td>
  <td>{kw_html or '-'}</td>
  <td>{actions_html or '-'}</td>
  <td style="white-space:nowrap;"><a href="./detail_{idx}.html" style="font-size:12px;padding:3px 10px;border:0.5px solid #c5d3f0;border-radius:5px;background:#f0f4ff;">詳細 →</a></td>
</tr>"""

    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<meta name="robots" content="noindex, nofollow">
<title>施策ダッシュボード</title>
<style>{_COMMON_CSS}</style>
</head>
<body>
<div class="wrap">
  <div class="page-header">
    <div style="display:flex;align-items:center;gap:14px;">
      <a href="../" class="back-link">← レポート一覧</a>
      <span class="page-title">📋 施策ダッシュボード</span>
    </div>
    <span style="font-size:11px;color:#aaa;">更新: {_esc(generated_at)}</span>
  </div>

  <div class="tab-bar" id="tabBar">
    {tab_btns}
  </div>

  <div class="card" style="padding:0 20px;">
    <table>
      <thead><tr>
        <th>クライアント</th><th>URL</th><th>タイトル</th>
        <th>主要KW</th><th>施策実行日</th><th></th>
      </tr></thead>
      <tbody id="tableBody">{rows_html}</tbody>
    </table>
  </div>
  <div class="footer">自動生成 — 施策ダッシュボード</div>
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


# ── 詳細ページ生成 ────────────────────────────────────────────────────────────
def _build_detail_html(page: dict, client_name: str, page_index: int, total: int) -> str:
    url = page.get("url", "")
    title = page.get("title", "") or url
    keywords = [k for k in (page.get("keywords") or []) if k][:3]
    actions = [a for a in (page.get("actions") or []) if a.get("date")]
    weekly_data = page.get("weekly_data") or []

    # 変化率テーブル計算
    change_table_html = _build_change_table(weekly_data, actions, keywords)

    # action バッジ
    action_badges = " ".join(
        f'<span class="badge">{_esc(a["date"])}{(" " + _esc(a.get("label",""))) if a.get("label") else ""}</span>'
        for a in actions
    )

    # prev / next ナビ
    prev_link = f'<a href="./detail_{page_index-1}.html" style="font-size:12px;color:#185fa5;">← 前の施策</a>' if page_index > 0 else ''
    next_link = f'<a href="./detail_{page_index+1}.html" style="font-size:12px;color:#185fa5;">次の施策 →</a>' if page_index < total - 1 else ''

    # データを JS に埋め込む
    weekly_json = json.dumps(weekly_data, ensure_ascii=False)
    actions_json = json.dumps([a["date"] for a in actions], ensure_ascii=False)
    keywords_json = json.dumps(keywords, ensure_ascii=False)

    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<meta name="robots" content="noindex, nofollow">
<title>{_esc(title)} — 施策ダッシュボード</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.5.1/dist/chart.umd.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chartjs-plugin-annotation@3.1.0/dist/chartjs-plugin-annotation.min.js"></script>
<style>
{_COMMON_CSS}
.detail-meta{{font-size:12px;color:#666;margin-top:4px;}}
.tab-panel{{display:none;}}
.tab-panel.active{{display:block;}}
canvas{{max-height:320px;}}
.change-table th,.change-table td{{text-align:right;}}
.change-table th:first-child,.change-table td:first-child{{text-align:left;}}
.up{{color:#0f6e56;font-weight:600;}}
.down{{color:#a32d2d;font-weight:600;}}
.neutral{{color:#888;}}
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
      </div>
      {('<div style="margin-top:6px;">' + action_badges + '</div>') if action_badges else ''}
    </div>
  </div>

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
    <div id="panel-clicks" class="tab-panel active"><canvas id="chart-clicks"></canvas></div>
    <div id="panel-impressions" class="tab-panel"><canvas id="chart-impressions"></canvas></div>
    <div id="panel-ctr" class="tab-panel"><canvas id="chart-ctr"></canvas></div>
    <div id="panel-position" class="tab-panel"><canvas id="chart-position"></canvas></div>
    <div id="panel-sessions" class="tab-panel"><canvas id="chart-sessions"></canvas></div>
    <div id="panel-kw" class="tab-panel"><canvas id="chart-kw"></canvas></div>
  </div>

  <!-- 変化率テーブル -->
  {change_table_html}

  <div class="footer">自動生成 — 施策ダッシュボード</div>
</div>

<script>
const WEEKLY = {weekly_json};
const ACTION_DATES = {actions_json};
const KEYWORDS = {keywords_json};
const LABELS = WEEKLY.map(w => w.week);

// 施策実行日をx軸ラベルに対応させる
function buildAnnotations() {{
  const annotations = {{}};
  ACTION_DATES.forEach((date, i) => {{
    // 最も近い週ラベルを探す
    let nearest = LABELS[0];
    let minDiff = Infinity;
    LABELS.forEach(lbl => {{
      const diff = Math.abs(new Date(lbl) - new Date(date));
      if (diff < minDiff) {{ minDiff = diff; nearest = lbl; }}
    }});
    annotations['action' + i] = {{
      type: 'line',
      scaleID: 'x',
      value: nearest,
      borderColor: '#e05c2a',
      borderWidth: 2,
      borderDash: [5, 4],
      label: {{
        display: true,
        content: date,
        position: 'start',
        backgroundColor: 'rgba(224,92,42,0.85)',
        color: '#fff',
        font: {{ size: 10 }},
        padding: {{ x: 4, y: 2 }},
        yAdjust: i * 22,
      }},
    }};
  }});
  return annotations;
}}

const CHART_OPTS_BASE = {{
  responsive: true,
  interaction: {{ mode: 'index', intersect: false }},
  plugins: {{
    legend: {{ labels: {{ font: {{ size: 11 }} }} }},
    annotation: {{ annotations: buildAnnotations() }},
  }},
  scales: {{
    x: {{ ticks: {{ font: {{ size: 10 }}, maxRotation: 45, minRotation: 30 }} }},
    y: {{ ticks: {{ font: {{ size: 11 }}, precision: 0 }}, beginAtZero: true }},
  }},
}};

function makeLineDS(label, data, color, fill=false) {{
  return {{
    label, data,
    borderColor: color, backgroundColor: color + '33',
    borderWidth: 2, pointRadius: 3, tension: 0.3, fill,
  }};
}}

// チャートインスタンス管理
const charts = {{}};

function buildChart(id, datasets, reverseY=false, yLabel='') {{
  const ctx = document.getElementById('chart-' + id).getContext('2d');
  const opts = JSON.parse(JSON.stringify(CHART_OPTS_BASE));
  opts.plugins.annotation.annotations = buildAnnotations();
  opts.scales.y.reverse = reverseY;
  if (yLabel) opts.scales.y.title = {{ display: true, text: yLabel, font: {{ size: 11 }} }};
  if (reverseY) opts.scales.y.beginAtZero = false;
  if (charts[id]) charts[id].destroy();
  charts[id] = new Chart(ctx, {{ type: 'line', data: {{ labels: LABELS, datasets }}, options: opts }});
}}

function initCharts() {{
  if (typeof ChartjsPluginAnnotation !== 'undefined') {{
    Chart.register(ChartjsPluginAnnotation);
  }}

  buildChart('clicks',
    [makeLineDS('クリック数', WEEKLY.map(w=>w.clicks), '#2563eb', true)]);

  buildChart('impressions',
    [makeLineDS('表示回数', WEEKLY.map(w=>w.impressions), '#059669', true)]);

  buildChart('ctr',
    [makeLineDS('CTR (%)', WEEKLY.map(w=>w.ctr), '#7c3aed', true)], false, '%');

  buildChart('position',
    [makeLineDS('平均順位', WEEKLY.map(w=>w.position??null), '#d97706')], true, '位');

  buildChart('sessions',
    [makeLineDS('セッション数', WEEKLY.map(w=>w.sessions??null), '#0891b2', true)]);

  // KW順位（複数系列）
  const kwColors = ['#e11d48','#16a34a','#7c3aed'];
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


# ── 変化率テーブル ────────────────────────────────────────────────────────────
def _build_change_table(weekly_data: list, actions: list, keywords: list) -> str:
    if not weekly_data or len(weekly_data) < 2:
        return ""

    # 施策前の週（最古のアクション日より前の最新週）
    oldest_action = min((a["date"] for a in actions if a.get("date")), default=None)
    before_w = None
    if oldest_action:
        for w in weekly_data:
            if w["week"] < oldest_action:
                before_w = w
    if before_w is None:
        before_w = weekly_data[0]

    after_w = weekly_data[-1]

    def pct(before_val, after_val, lower_is_better=False):
        try:
            b, a = float(before_val or 0), float(after_val or 0)
            if b == 0:
                return "-", "neutral"
            diff = (a - b) / b * 100
            arrow = "▲" if diff > 0 else "▼"
            if lower_is_better:
                # 平均順位・KW順位: 数値が下がる（▼）ほど改善 → 緑
                css = "up" if diff < 0 else "down"
            else:
                # クリック数・表示回数・CTR・セッション数: 数値が上がる（▲）ほど改善 → 緑
                css = "up" if diff > 0 else "down"
            return f"{arrow}{abs(diff):.1f}%", css
        except Exception:
            return "-", "neutral"

    def fmt(v):
        if v is None:
            return "-"
        if isinstance(v, float):
            return f"{v:.1f}"
        return str(v)

    metrics = [
        ("クリック数", "clicks", False),
        ("表示回数", "impressions", False),
        ("CTR (%)", "ctr", False),
        ("平均順位", "position", True),
        ("セッション数", "sessions", False),
    ]
    for kw in keywords:
        metrics.append((f"KW: {kw}", f"__kw__{kw}", True))

    def get_val(w, key):
        if key.startswith("__kw__"):
            kw = key[6:]
            return (w.get("kw_positions") or {}).get(kw)
        return w.get(key)

    rows = ""
    for label, key, lower_is_better in metrics:
        b_val = get_val(before_w, key)
        a_val = get_val(after_w, key)
        change, css = pct(b_val, a_val, lower_is_better)
        rows += f"""<tr>
  <td>{_esc(label)}</td>
  <td>{fmt(b_val)}</td>
  <td>{fmt(a_val)}</td>
  <td class="{css}">{change}</td>
</tr>"""

    before_label = before_w.get("week", "-")
    after_label = after_w.get("week", "-")

    return f"""<div class="card">
  <div style="font-size:13px;font-weight:600;color:#1F3864;margin-bottom:12px;">📊 施策前後の変化</div>
  <table class="change-table">
    <thead><tr>
      <th>指標</th>
      <th>施策前（{_esc(before_label)}週）</th>
      <th>最新（{_esc(after_label)}週）</th>
      <th>変化率</th>
    </tr></thead>
    <tbody>{rows}</tbody>
  </table>
  <p style="font-size:10px;color:#aaa;margin-top:8px;">※ 施策前: 施策実行日より前の直近週</p>
</div>"""


# ── ユーティリティ ────────────────────────────────────────────────────────────
def _esc(s) -> str:
    return str(s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


# ── メイン ────────────────────────────────────────────────────────────────────
def generate_dashboard(dashboard_data: dict, output_dir: str, dry_run: bool = False):
    """
    dashboard_data.json の内容からダッシュボード HTML を生成して output_dir に保存し、
    GitHub の dashboard/ フォルダにアップロードする。
    """
    print("\n===== dashboard_generator 開始 =====")

    clients_data = dashboard_data.get("clients", {})
    all_pages = []
    for client_name, client_obj in clients_data.items():
        for page in client_obj.get("pages", []):
            all_pages.append((client_name, page))

    if not all_pages:
        print("  施策ページが空のためスキップ")
        return

    os.makedirs(output_dir, exist_ok=True)

    token = _get_github_token()
    today = datetime.date.today().isoformat()
    files = []  # (local_path, github_path)

    # 一覧ページ
    index_html = _build_index_html(dashboard_data)
    index_path = os.path.join(output_dir, "index.html")
    with open(index_path, "w", encoding="utf-8") as f:
        f.write(index_html)
    files.append((index_path, "dashboard/index.html"))
    print(f"  生成: index.html")

    # 詳細ページ
    total = len(all_pages)
    for idx, (client_name, page) in enumerate(all_pages):
        detail_html = _build_detail_html(page, client_name, idx, total)
        fname = f"detail_{idx}.html"
        detail_path = os.path.join(output_dir, fname)
        with open(detail_path, "w", encoding="utf-8") as f:
            f.write(detail_html)
        files.append((detail_path, f"dashboard/{fname}"))
        print(f"  生成: {fname} ({client_name} / {page.get('url','')})")

    # GitHub アップロード
    if not dry_run and token:
        print(f"\n  GitHubアップロード中 ({len(files)}ファイル)...")
        for local_path, github_path in files:
            with open(local_path, "rb") as f:
                content_bytes = f.read()
            _github_put(github_path, content_bytes, token, f"Update dashboard: {today}")
    elif not token:
        print("  ⚠ GitHub Token が未設定のためアップロードをスキップ")
    else:
        print("  dry-run のためアップロードをスキップ")

    pub_url = f"https://{GITHUB_USERNAME}.github.io/{GITHUB_REPO}/dashboard/"
    print(f"\n  ダッシュボード: {pub_url}")
    print("===== dashboard_generator 完了 =====")
    return pub_url


# ── 単体実行 ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="reports/dashboard_data.json")
    parser.add_argument("--output-dir", default="reports/dashboard")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not os.path.exists(args.input):
        print(f"❌ {args.input} が見つかりません")
        raise SystemExit(1)

    with open(args.input, encoding="utf-8") as f:
        data = json.load(f)

    generate_dashboard(data, args.output_dir, dry_run=args.dry_run)
