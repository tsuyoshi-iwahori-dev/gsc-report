# ai_analyzer.py — Claude APIを使ったRAGベースのSEO分析

import json
import requests
import os


CLAUDE_API_URL = "https://api.anthropic.com/v1/messages"
CLAUDE_MODEL = "claude-sonnet-4-6"

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
if not ANTHROPIC_API_KEY:
    key_path = os.path.join(os.path.dirname(__file__), '..', 'Anthropic APIキー.txt')
    if os.path.exists(key_path):
        with open(key_path, encoding='utf-8') as f:
            ANTHROPIC_API_KEY = f.read().strip()


# RAGナレッジ（検索アルゴリズムの主要シグナル）
SEO_KNOWLEDGE = """
## SEOランキングシグナルの優先度分類

### 【A】順位に直接影響（最優先）
- ユーザーエンゲージメント（CTR・滞在時間・直帰率）: 特許US8762373B1, WO2013192101A1
  - CTR低下が継続すると順位評価にも悪影響（ポゴスティッキング検出）
  - 1位の平均CTR 27.6%、6〜10位は4〜8%が目安（Backlinko 2025）
- クエリ意図マッチング: 特許US8868548B2, US8612432B2
  - 意図マッチング高で+6.1ポジション、不一致で-11.3ポジション
  - 表示急増×CTR急落は意図ミスマッチの典型パターン
- セマンティック関連性・トピッククラスター: 特許US8402018B2
  - クラスター構造ありで+4.3ポジション、孤立ページで-5.8ポジション
- 被リンク（質・量）: 特許US7516123B2
  - 被リンクドメイン数 相関0.28（SEMrush 2024）
- コンテンツ鮮度: 特許US8832088B1
  - 2年以上更新なしで-3.2ポジション

### 【B】間接的に影響
- E-E-A-T（著者情報・信頼性・専門性・一次情報）
- コンテンツの深さ・網羅性（Information Gain Score: 特許US20200349181A1）
- パッセージランキング（MUVERA技術）: ページ内セクション単位で独立評価

### 【C】直接影響なし
- デザイン・UI/UX（滞在時間経由で間接的）
- 文章の読みやすさ（間接的）

## AI Overviews / AI Modeの影響
- AI Overview表示時、上位ページのCTRが低下する可能性（Ahrefs研究）
- 表示回数が増加しているのにCTRが低い場合、AI Overviewsがクリックを吸収している可能性がある
- AI Overviewsに引用されるには: retrievable・verifiable・grounded なコンテンツ構造が重要

## アルゴリズムアップデート履歴（2025-2026）
- December 2025 Core Update（12/11-12/29）
- August 2025 Spam Update（8/26-）
- June 2025 Core Update
- March 2025 Core Update

## 判断の原則
- 「インデックス要件」と「順位要因」を混同しない
- page-level / site-wide / entity-levelを分けて考える
- 従来SEOの順位とAI Overviewsでの引用は同じではない
- 特許は実装の方向性を示すが、現行仕様の断定はしない
"""


def build_prompt(site_name, week_label, summary_rows, current_queries, previous_queries, pages):
    """Claude APIに渡すプロンプトを生成"""

    current = summary_rows[0]
    previous = summary_rows[1] if len(summary_rows) > 1 else {}

    # 週次サマリー
    summary_text = f"""
【サイト名】{site_name}
【対象期間】{week_label}

■ 全体指標（先週比）
- クリック数: {current['clicks']:,} （前週: {previous.get('clicks', 'N/A'):,}）
- 表示回数: {current['impressions']:,} （前週: {previous.get('impressions', 'N/A'):,}）
- CTR: {current['ctr']}% （前週: {previous.get('ctr', 'N/A')}%）
- 平均順位: {current['position']}位 （前週: {previous.get('position', 'N/A')}位）
"""

    # ページ上位20件
    pages_text = "\n■ クリック上位ページ（先週 top20）\n"
    for p in pages[:20]:
        url = p['page'].replace('https://www.', '').replace('https://', '')
        pages_text += f"- {url} | CL:{p['clicks']} IMP:{p['impressions']:,} CTR:{p['ctr']}% 順位:{p['position']}位\n"

    # クエリ比較
    queries_text = "\n■ クエリ比較（今週 vs 前週 上位20件）\n"
    all_q = sorted(
        set(list(current_queries.keys()) + list(previous_queries.keys())),
        key=lambda q: current_queries.get(q, {}).get("clicks", 0),
        reverse=True
    )[:20]

    for q in all_q:
        curr = current_queries.get(q, {})
        prev = previous_queries.get(q, {})
        curr_cl = curr.get('clicks', '-')
        prev_cl = prev.get('clicks', '-')
        curr_pos = curr.get('position', '-')
        prev_pos = prev.get('position', '-')
        curr_ctr = f"{curr.get('ctr', '-')}%"

        if q not in previous_queries:
            status = "🆕新出現"
        elif q not in current_queries:
            status = "❌消滅"
        elif isinstance(curr_cl, int) and isinstance(prev_cl, int):
            if curr_cl > prev_cl:
                status = "✅増加"
            elif curr_cl < prev_cl:
                status = "🔴減少"
            else:
                status = "－横ばい"
        else:
            status = "－"

        queries_text += f"- {q} | 今週CL:{curr_cl} 前週CL:{prev_cl} | 今週順位:{curr_pos} 前週順位:{prev_pos} | CTR:{curr_ctr} | {status}\n"

    return summary_text + pages_text + queries_text


def analyze_with_ai(site_name, week_label, summary_rows, current_queries, previous_queries, pages):
    """
    Claude APIを使ってSEO分析コメントを生成する
    戻り値: insights リスト
    """

    prompt_data = build_prompt(
        site_name, week_label, summary_rows,
        current_queries, previous_queries, pages
    )

    system_prompt = f"""あなたは検索アルゴリズムに精通したSEOスペシャリストです。
以下のSEOナレッジを参照しながら、GSCデータを分析してください。

{SEO_KNOWLEDGE}

## 分析の指示

以下の3つの観点で分析し、JSON形式で返してください。

1. **全体サマリー**: 先週比でクリック・表示・CTR・順位がどう変わったか、その要因仮説
2. **ページ単位の分析**: 注目すべきページの変化と要因（機会損失・順位変動・意図ミスマッチ等）
3. **クエリ単位の分析**: 注目すべきクエリの変化と要因（新出現・消滅・順位変動・CTR変化等）

各分析には以下を含めてください：
- 何が起きたか（事実）
- なぜ起きたか（SEOナレッジに基づく要因仮説）
- 何をすべきか（具体的アクション）

## 出力形式（JSON）

以下の形式で出力してください。JSON以外のテキストは含めないでください。

{{
  "insights": [
    {{
      "level": "📊 全体",
      "title": "先週比のサマリータイトル",
      "detail": "詳細な要因分析（SEOナレッジに基づく根拠を含む）",
      "action": "具体的なアクション"
    }},
    {{
      "level": "📄 ページ",
      "title": "ページ単位の分析タイトル",
      "detail": "詳細",
      "action": "アクション"
    }},
    {{
      "level": "🔍 クエリ",
      "title": "クエリ単位の分析タイトル",
      "detail": "詳細",
      "action": "アクション"
    }}
  ]
}}
"""

    headers = {
        "Content-Type": "application/json",
        "x-api-key": ANTHROPIC_API_KEY,
    "anthropic-version": "2023-06-01",
}

    body = {
        "model": CLAUDE_MODEL,
        "max_tokens": 1000,
        "system": system_prompt,
        "messages": [
            {
                "role": "user",
                "content": f"以下のGSCデータを分析してください。\n\n{prompt_data}"
            }
        ]
    }

    try:
        response = requests.post(CLAUDE_API_URL, headers=headers, json=body)
        response.raise_for_status()
        data = response.json()

        text = ""
        for block in data.get("content", []):
            if block.get("type") == "text":
                text += block.get("text", "")

        # JSON部分を抽出
        text = text.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        text = text.strip()

        parsed = json.loads(text)
        return parsed.get("insights", [])

    except Exception as e:
        print(f"  ⚠ AI分析エラー: {e}")
        try:
            print(f"  ⚠ レスポンス詳細: {response.text}")
        except:
            pass
        return []