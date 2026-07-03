def _rate(current, previous):
    if previous == 0:
        return 0
    return round((current - previous) / previous * 100, 1)


def analyze(summary_rows, queries, pages):
    insights = []

    if not pages:
        return insights

    # CTR改善余地: 5〜20位・表示500以上・CTR3%未満
    low_ctr_pages = [
        p for p in pages
        if p.get('impressions', 0) >= 500
        and 5.0 <= p.get('position', 0) <= 20.0
        and p.get('ctr', 0) < 3.0
    ]
    if low_ctr_pages:
        top = sorted(low_ctr_pages, key=lambda p: p.get('impressions', 0), reverse=True)
        detail = '5〜20位で表示回数500以上・CTR3%未満のページ（上位5件）：\n'
        detail += '\n'.join(
            f"  - {p['page']}（順位{p['position']}位・表示{p['impressions']:,}回・CTR{p['ctr']}%）"
            for p in top[:5]
        )
        insights.append({
            'level': '⚠ 注意',
            'title': f'タイトル改善でCTRを伸ばせるページが{len(low_ctr_pages)}件あります',
            'detail': detail,
            'action': 'タイトルタグをクリック訴求力の高いものに見直してください',
        })

    # 圏外ページ: 表示200以上・20位超
    deep_pages = [
        p for p in pages
        if p.get('impressions', 0) >= 200
        and p.get('position', 0) > 20.0
    ]
    if deep_pages:
        top = sorted(deep_pages, key=lambda p: p.get('impressions', 0), reverse=True)
        detail = '表示回数200以上・20位以下のページ（上位5件）：\n'
        detail += '\n'.join(
            f"  - {p['page']}（順位{p['position']}位・表示{p['impressions']:,}回）"
            for p in top[:5]
        )
        insights.append({
            'level': '⚠ 注意',
            'title': f'20位以下で表示されている重要ページが{len(deep_pages)}件',
            'detail': detail,
            'action': '内部リンク強化・コンテンツの質改善で上位表示を目指してください',
        })

    # 意図ミスマッチ: 表示1万超・CTR0.1%未満
    mismatch_pages = [
        p for p in pages
        if p.get('impressions', 0) >= 10000
        and p.get('ctr', 0) < 0.1
    ]
    if mismatch_pages:
        top = sorted(mismatch_pages, key=lambda p: p.get('impressions', 0), reverse=True)
        detail = '表示回数1万超・CTR0.1%未満のページ：\n'
        detail += '\n'.join(
            f"  - {p['page']}（表示{p['impressions']:,}回・CTR{p['ctr']}%）"
            for p in top[:5]
        )
        insights.append({
            'level': '🔴 最優先',
            'title': f'クエリ意図ミスマッチの疑い：表示回数+{len(mismatch_pages)}件を検出',
            'detail': detail,
            'action': f'意図ミスマッチ候補ページ {len(mismatch_pages)}件を検出。検索意図を再確認してください',
        })

    return insights


def format_insights(insights):
    if not insights:
        return '今週は特筆すべき異常値はありませんでした。'

    lines = []
    for i, ins in enumerate(insights, 1):
        lines.append('=' * 50)
        lines.append(f'【{ins.get("level", "")}】{ins.get("title", "")}')
        if ins.get('detail'):
            lines.append(f'詳細：{ins["detail"]}')
        if ins.get('action'):
            lines.append(f'アクション：{ins["action"]}')
    return '\n'.join(lines)


def analyze_queries(current_queries, previous_queries):
    """
    クエリ比較からSEO観点の分析コメントを生成する
    current_queries / previous_queries: fetch_queries_for_comparison()の戻り値
    """
    insights = []

    new_queries = [q for q in current_queries if q not in previous_queries]
    lost_queries = [q for q in previous_queries if q not in current_queries]
    improved_queries = []
    declining_queries = []

    for q in current_queries:
        if q not in previous_queries:
            continue
        curr_cl = current_queries[q].get('clicks', 0)
        prev_cl = previous_queries[q].get('clicks', 0)
        if prev_cl > 0:
            rate = round((curr_cl - prev_cl) / prev_cl * 100, 1)
            if rate >= 50:
                improved_queries.append((q, curr_cl, prev_cl, rate))
            elif rate <= -30:
                declining_queries.append((q, curr_cl, prev_cl, rate))

    improved_queries.sort(key=lambda x: x[1], reverse=True)
    declining_queries.sort(key=lambda x: x[1], reverse=True)

    if new_queries:
        top = sorted(new_queries, key=lambda q: current_queries[q].get('clicks', 0), reverse=True)
        sample = '、'.join(top[:5]) + 'など' if len(top) > 5 else '、'.join(top)
        insights.append({
            'level': '🆕 新出現',
            'title': f'今週新たに上位20位以内に入ったクエリが{len(new_queries)}件',
            'detail': sample,
            'action': '',
        })

    if lost_queries:
        top = sorted(lost_queries, key=lambda q: previous_queries[q].get('clicks', 0), reverse=True)
        sample = '、'.join(top[:5]) + 'など' if len(top) > 5 else '、'.join(top)
        insights.append({
            'level': '❌ 消滅',
            'title': f'先週上位20位以内にいたクエリが{len(lost_queries)}件圏外に',
            'detail': sample,
            'action': '',
        })

    if improved_queries:
        detail_lines = [
            f'  - {q}（{prev_cl}→{curr_cl}CL, +{rate}%）'
            for q, curr_cl, prev_cl, rate in improved_queries[:5]
        ]
        insights.append({
            'level': '✅ 改善',
            'title': f'クリック数が50%以上増加したクエリが{len(improved_queries)}件',
            'detail': '\n'.join(detail_lines),
            'action': '',
        })

    if declining_queries:
        detail_lines = [
            f'  - {q}（{prev_cl}→{curr_cl}CL, {rate}%）'
            for q, curr_cl, prev_cl, rate in declining_queries[:5]
        ]
        insights.append({
            'level': '🔴 要注意',
            'title': f'クリック数が30%以上減少したクエリが{len(declining_queries)}件',
            'detail': '\n'.join(detail_lines),
            'action': '',
        })

    return insights
