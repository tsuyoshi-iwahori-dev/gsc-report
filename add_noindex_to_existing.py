"""
既存の公開済みHTMLファイルに noindex メタタグを一括追加する。
<head> 内に既に noindex があればスキップ（重複防止）。
"""
import pathlib
import re

ROOT = pathlib.Path(__file__).parent
NOINDEX_TAG = '<meta name="robots" content="noindex, nofollow">'

processed = 0
skipped = 0
errors = 0

for html_file in sorted(ROOT.rglob("*.html")):
    try:
        text = html_file.read_text(encoding="utf-8")
    except Exception as e:
        print(f"  [ERROR] 読み込み失敗: {html_file.relative_to(ROOT)} — {e}")
        errors += 1
        continue

    if "noindex" in text:
        print(f"  [SKIP ] {html_file.relative_to(ROOT)}")
        skipped += 1
        continue

    # <head> タグの直後に挿入
    new_text = re.sub(
        r"(<head[^>]*>)",
        r"\1\n" + NOINDEX_TAG,
        text,
        count=1,
        flags=re.IGNORECASE,
    )

    if new_text == text:
        print(f"  [WARN ] <head>タグが見つからなかった: {html_file.relative_to(ROOT)}")
        skipped += 1
        continue

    html_file.write_text(new_text, encoding="utf-8")
    print(f"  [OK   ] {html_file.relative_to(ROOT)}")
    processed += 1

print()
print(f"処理完了: 追加={processed}件 / スキップ={skipped}件 / エラー={errors}件")
