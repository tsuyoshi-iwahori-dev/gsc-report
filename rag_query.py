"""
rag_query.py — RAG索引を使ってクライアント資料を横断検索し、AI回答を生成する

使い方:
  py rag_query.py --client 田所商店 --q "直近の議事録で決まったToDoは？"
"""

import argparse
import json
import logging
import math
import os
import sys
from pathlib import Path

# HuggingFace / transformers / tqdm のログ・プログレスバーを stderr に抑制
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
logging.getLogger("transformers").setLevel(logging.ERROR)
logging.getLogger("sentence_transformers").setLevel(logging.ERROR)
logging.getLogger("huggingface_hub").setLevel(logging.ERROR)

BASE_DIR = Path(__file__).parent.parent  # Documents/gijiroku/

CLAUDE_API_URL = "https://api.anthropic.com/v1/messages"
CLAUDE_MODEL   = "claude-sonnet-4-6"
TOP_K          = 5


# ─── Anthropic API キー ───────────────────────────────────────

def load_api_key():
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        key_path = Path(__file__).parent.parent / "Anthropic APIキー.txt"
        if key_path.exists():
            key = key_path.read_text(encoding="utf-8").strip()
    return key


# ─── 埋め込み ─────────────────────────────────────────────────

_model = None

def get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer("intfloat/multilingual-e5-small")
    return _model


def embed_query(text: str) -> list[float]:
    model = get_model()
    vec = model.encode(["query: " + text], normalize_embeddings=True)[0]
    return vec.tolist()


# ─── コサイン類似度 ───────────────────────────────────────────

def cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


# ─── 索引読み込み ─────────────────────────────────────────────

def load_index(client_name: str) -> dict:
    index_path = BASE_DIR / f"rag_index_{client_name}.json"
    if not index_path.exists():
        raise FileNotFoundError(f"索引ファイルが見つかりません: {index_path}")
    with open(index_path, encoding="utf-8") as f:
        return json.load(f)


# ─── 検索 ─────────────────────────────────────────────────────

def search(index: dict, query_vec: list[float], top_k=TOP_K) -> list[dict]:
    scored = []
    for chunk in index["chunks"]:
        score = cosine_similarity(query_vec, chunk["embedding"])
        scored.append({**chunk, "score": score})
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:top_k]


# ─── Anthropic API 呼び出し ───────────────────────────────────

def call_claude(query: str, contexts: list[dict], api_key: str) -> str:
    import requests

    context_text = "\n\n---\n\n".join(
        f"【出典: {c['file_name']} ({c['source_type']}) チャンク{c['chunk_index']+1}】\n{c['text']}"
        for c in contexts
    )

    system_prompt = (
        "あなたはクライアント担当者のアシスタントです。"
        "以下の参考資料（過去の議事録や提案書等）を踏まえて、質問に対して正確・簡潔に日本語で回答してください。"
        "参考資料に根拠がない場合はその旨を伝えてください。"
    )
    user_prompt = f"## 参考資料\n\n{context_text}\n\n## 質問\n\n{query}"

    headers = {
        "Content-Type": "application/json",
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
    }
    body = {
        "model":      CLAUDE_MODEL,
        "max_tokens": 1500,
        "system":     system_prompt,
        "messages":   [{"role": "user", "content": user_prompt}],
    }

    resp = requests.post(CLAUDE_API_URL, headers=headers, json=body, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    return data["content"][0]["text"]


# ─── メイン ───────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--client", required=True)
    parser.add_argument("--q",      required=True, help="質問文")
    args = parser.parse_args()

    api_key = load_api_key()
    if not api_key:
        print(json.dumps({"error": "Anthropic APIキーが設定されていません"}, ensure_ascii=False))
        sys.exit(1)

    try:
        index = load_index(args.client)
    except FileNotFoundError as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False))
        sys.exit(1)

    query_vec = embed_query(args.q)
    top_chunks = search(index, query_vec)

    ai_available = True
    answer = None
    try:
        answer = call_claude(args.q, top_chunks, api_key)
    except Exception as e:
        ai_available = False
        answer = None

    sources = []
    seen = set()
    for c in top_chunks:
        key = c["file_name"]
        if key not in seen:
            seen.add(key)
            sources.append({"file_name": c["file_name"], "source_type": c["source_type"], "score": round(c["score"], 3)})

    result = {
        "answer":       answer,
        "ai_available": ai_available,
        "chunks":       [
            {
                "file_name":   c["file_name"],
                "source_type": c["source_type"],
                "score":       round(c["score"], 3),
                "text":        c["text"],
                "chunk_index": c["chunk_index"],
            }
            for c in top_chunks
        ],
        "sources": sources,
        "query":   args.q,
        "client":  args.client,
    }
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
