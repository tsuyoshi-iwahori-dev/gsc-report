# github_uploader.py

import base64
import datetime
import json
import requests
import os

GITHUB_USERNAME = "tsuyoshi-iwahori-dev"
GITHUB_REPO = "gsc-report"
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN_VALUE", "")
if not GITHUB_TOKEN:
    token_path = os.path.join(os.path.dirname(__file__), '..', 'GitHub_Token.txt')
    if os.path.exists(token_path):
        with open(token_path, encoding='utf-8') as f:
            GITHUB_TOKEN = f.read().strip()
GITHUB_API = "https://api.github.com"


def upload_to_github(filepath, site_name):
    import os
    filename = os.path.basename(filepath)
    github_path = f"{site_name}/{filename}"

    with open(filepath, "rb") as f:
        content = base64.b64encode(f.read()).decode("utf-8")

    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
    }

    url = f"{GITHUB_API}/repos/{GITHUB_USERNAME}/{GITHUB_REPO}/contents/{github_path}"
    response = requests.get(url, headers=headers)
    sha = response.json().get("sha") if response.status_code == 200 else None

    body = {
        "message": f"Add report: {site_name} {datetime.date.today()}",
        "content": content,
    }
    if sha:
        body["sha"] = sha

    response = requests.put(url, headers=headers, json=body)

    if response.status_code in [200, 201]:
        pages_url = f"https://{GITHUB_USERNAME}.github.io/{GITHUB_REPO}/{site_name}/{filename}"
        print(f"  OK GitHub: {pages_url}")
        return pages_url
    else:
        print(f"  NG GitHub: {response.status_code}")
        return ""


def update_index(site_reports):
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
    }

    index_url = f"{GITHUB_API}/repos/{GITHUB_USERNAME}/{GITHUB_REPO}/contents/index.html"
    json_url = f"{GITHUB_API}/repos/{GITHUB_USERNAME}/{GITHUB_REPO}/contents/report_data.json"

    # 既存index.htmlのSHA取得
    r = requests.get(index_url, headers=headers)
    existing_sha = r.json().get("sha") if r.status_code == 200 else None

    # 既存JSONデータ取得
    rj = requests.get(json_url, headers=headers)
    if rj.status_code == 200:
        json_sha = rj.json().get("sha")
        existing_json = json.loads(base64.b64decode(rj.json()["content"]).decode("utf-8"))
    else:
        json_sha = None
        existing_json = {}

    # 今週データを追加
    week_label = site_reports[0]["week"] if site_reports else ""
    existing_json[week_label] = [
        {"name": r["name"], "url": r["url"]} for r in site_reports
    ]

    # JSONをGitHubに保存
    json_content = base64.b64encode(json.dumps(existing_json, ensure_ascii=False, indent=2).encode("utf-8")).decode("utf-8")
    json_body = {"message": f"Update data: {datetime.date.today()}", "content": json_content}
    if json_sha:
        json_body["sha"] = json_sha
    requests.put(json_url, headers=headers, json=json_body)

    # 週を新しい順にソート
    sorted_weeks = sorted(existing_json.keys(), reverse=True)

    # アコーディオンHTML生成
    weeks_html = ""
    for i, week in enumerate(sorted_weeks):
        clients = existing_json[week]
        is_latest = i == 0
        body_style = "" if is_latest else 'style="display:none;"'
        chev_class = "chevron open" if is_latest else "chevron"
        badge = '<span class="badge-new">最新</span>' if is_latest else ""

        client_rows = ""
        for c in clients:
            domain = c["url"].replace("https://", "").split("/")[0] if "http" in c["url"] else c["url"]
            client_rows += f'''
      <div class="client-row">
        <div>
          <div class="client-name">{c['name']}</div>
          <div class="client-url">{domain}</div>
        </div>
        <a class="open-btn" href="{c['url']}" target="_blank">レポートを開く ↗</a>
      </div>'''

        weeks_html += f'''
  <div class="week-section" id="w{i}">
    <div class="week-header" onclick="toggle('w{i}')">
      <div>
        <div class="week-label">{week} {badge}</div>
        <div class="week-meta">{len(clients)}クライアント</div>
      </div>
      <span class="{chev_class}" id="chev-w{i}">&#8964;</span>
    </div>
    <div class="week-body" id="body-w{i}" {body_style}>{client_rows}
    </div>
  </div>'''

    generated_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

    html = f'''<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="robots" content="noindex, nofollow">
<title>週次レポート一覧</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0;}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#f5f5f3;color:#1a1a1a;font-size:14px;}}
.wrap{{max-width:800px;margin:0 auto;padding:28px 16px;}}
.top{{display:flex;justify-content:space-between;align-items:center;margin-bottom:24px;}}
.top h1{{font-size:17px;font-weight:500;}}
.top p{{font-size:12px;color:#888;margin-top:3px;}}
.week-section{{margin-bottom:12px;}}
.week-header{{display:flex;align-items:center;justify-content:space-between;background:#fff;border:0.5px solid #e0e0dc;border-radius:10px;padding:12px 16px;cursor:pointer;user-select:none;}}
.week-header:hover{{background:#fafaf8;}}
.week-body{{border:0.5px solid #e0e0dc;border-top:none;border-radius:0 0 10px 10px;background:#fff;overflow:hidden;}}
.week-label{{font-size:13px;font-weight:500;}}
.week-meta{{font-size:11px;color:#888;margin-top:2px;}}
.chevron{{font-size:16px;color:#888;transition:transform 0.2s;}}
.chevron.open{{transform:rotate(180deg);}}
.client-row{{display:flex;align-items:center;justify-content:space-between;padding:11px 16px;border-bottom:0.5px solid #f0f0ec;}}
.client-row:last-child{{border-bottom:none;}}
.client-name{{font-size:13px;font-weight:500;}}
.client-url{{font-size:11px;color:#888;margin-top:1px;}}
.open-btn{{font-size:12px;color:#185fa5;text-decoration:none;display:flex;align-items:center;gap:4px;flex-shrink:0;}}
.open-btn:hover{{text-decoration:underline;}}
.badge-new{{font-size:10px;background:#e1f5ee;color:#0f6e56;padding:2px 7px;border-radius:20px;margin-left:8px;}}
.footer{{text-align:center;font-size:11px;color:#aaa;padding:24px 0;}}
</style>
</head>
<body>
<div class="wrap">
  <div class="top">
    <div>
      <h1>週次レポート一覧</h1>
      <p>最終更新：{generated_at}</p>
      <div style="display:flex;gap:8px;margin-top:12px;flex-wrap:wrap;">
        <a href="https://tsuyoshi-iwahori-dev.github.io/gsc-report/dashboard/"
           target="_blank"
           style="display:inline-flex;align-items:center;gap:6px;font-size:13px;color:#185fa5;background:#f0f4f8;border:0.5px solid #c0d0e0;border-radius:6px;padding:7px 14px;text-decoration:none;">
          📋 施策ダッシュボード →
        </a>
        <a href="https://tsuyoshi-iwahori-dev.github.io/gsc-report/article/"
           target="_blank"
           style="display:inline-flex;align-items:center;gap:6px;font-size:13px;color:#185fa5;background:#f0f4f8;border:0.5px solid #c0d0e0;border-radius:6px;padding:7px 14px;text-decoration:none;">
          📝 新規記事パフォーマンス →
        </a>
      </div>
    </div>
  </div>
  {weeks_html}
  <div class="footer">自動生成レポート — GSC Weekly Report</div>
</div>
<script>
function toggle(id) {{
  const body = document.getElementById('body-' + id);
  const chev = document.getElementById('chev-' + id);
  if (body.style.display === 'none') {{
    body.style.display = 'block';
    chev.classList.add('open');
  }} else {{
    body.style.display = 'none';
    chev.classList.remove('open');
  }}
}}
</script>
</body>
</html>'''

    content = base64.b64encode(html.encode("utf-8")).decode("utf-8")
    body = {"message": f"Update index: {datetime.date.today()}", "content": content}
    if existing_sha:
        body["sha"] = existing_sha

    response = requests.put(index_url, headers=headers, json=body)
    if response.status_code in [200, 201]:
        result_url = f"https://{GITHUB_USERNAME}.github.io/{GITHUB_REPO}/"
        print(f"\n  OK 一覧ページ更新完了: {result_url}")
        return result_url
    else:
        print(f"\n  NG 一覧ページ更新失敗: {response.status_code}")
        return ""