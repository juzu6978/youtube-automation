"""
00_trend_researcher.py
Claude API でトレンドトピックを調査し、バイラルスコア付き候補を生成する。

出力: assets/trend_cache/scored_topics.json
実行タイミング: 週次（GitHub Actions）または手動

Claude の膨大な学習データを活用し、日本のYouTubeショート動画で
バズりやすいトピックを10件生成・スコアリングする。
"""

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path

import anthropic

sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.utils import load_genre_config, load_settings

TREND_CACHE_DIR = Path(__file__).parent.parent / "assets" / "trend_cache"
TREND_CACHE_FILE = TREND_CACHE_DIR / "scored_topics.json"


# ─────────────────────────────────────────────
# トレンドリサーチ（web_search ツール使用）
# ─────────────────────────────────────────────

def _run_with_websearch(client: anthropic.Anthropic, prompt: str) -> str:
    """
    web_search_20250305 ツールを使って Claude を呼び出す。
    ツールループを処理し、最終テキストを返す。
    """
    messages = [{"role": "user", "content": prompt}]

    for _ in range(15):  # 最大15ターン
        response = client.beta.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            tools=[{"type": "web_search_20250305", "name": "web_search"}],
            messages=messages,
            betas=["web-search-2025-03-05"],
        )

        # tool_use ブロックを探す
        tool_uses = [b for b in response.content if hasattr(b, "type") and b.type == "tool_use"]
        text_blocks = [b for b in response.content if hasattr(b, "type") and b.type == "text"]

        if response.stop_reason == "end_turn" or not tool_uses:
            return " ".join(b.text for b in text_blocks)

        # アシスタントターンを追加してツールループ継続
        messages.append({"role": "assistant", "content": response.content})
        tool_results = [
            {"type": "tool_result", "tool_use_id": tu.id, "content": ""}
            for tu in tool_uses
        ]
        messages.append({"role": "user", "content": tool_results})

    raise RuntimeError("web_search ループが最大反復数に達しました")


def _run_without_websearch(client: anthropic.Anthropic, prompt: str) -> str:
    """web_search なしで Claude を呼び出す（フォールバック）"""
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text.strip()


# ─────────────────────────────────────────────
# メイン調査ロジック
# ─────────────────────────────────────────────

def research_trends(genre_cfg: dict, use_websearch: bool = True) -> dict:
    """
    Claude でトレンドトピックを生成・スコアリングする。

    use_websearch=True の場合は web_search ツールで最新トレンドを調査。
    False の場合は Claude の学習データを活用したナレッジベース生成。
    """
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    today = date.today().strftime("%Y年%m月%d日")
    genre_name = genre_cfg.get("name_jp", "心理学・行動科学")
    keywords_str = "、".join(genre_cfg.get("keywords", []))

    search_instruction = (
        "まずweb_searchツールを使って「YouTube ショート 日本 急上昇 心理学」"
        "「Twitter トレンド 日本 心理学 2025」「日本 バイラル 行動科学」などを検索し、"
        "最新の情報を踏まえた上で回答してください。"
        if use_websearch
        else "あなたの学習データをフル活用して、日本のYouTube視聴者に刺さる最新トレンドを分析してください。"
    )

    prompt = f"""あなたは日本のSNS・YouTube動画トレンドに精通したバイラルコンテンツストラテジストです。
今日の日付: {today}

ジャンル: {genre_name}
関連キーワード: {keywords_str}

{search_instruction}

【調査目的】
日本のYouTubeショート動画（55秒以内）で最もバイラルになりやすい
「{genre_name}」系トピックを10件発掘してください。

【バイラルになる条件】
✓ 視聴者が「え、これ自分のことだ」「知らなかった！」と感じる
✓ 日常生活との強い接点（恋愛・仕事・人間関係・お金など）がある
✓ 「なぜ〜するのか？」という疑問に答える形式
✓ 科学的根拠があると信頼性が上がる
✓ 15〜34歳の日本人が共感・シェアしたくなる

【各トピックで必要な情報】
- タイトル: 25文字以内・検索されやすい・インパクトある
- viral_score: 1〜10（今この瞬間のバイラル可能性）
- 3種類のフック候補:
  * hook_shock: 「え？」「まじで？」と思わせる衝撃型（脳に刺さる事実）
  * hook_curiosity: 「なぜ〜なのか気になる」好奇心型（謎かけ形式）
  * hook_empathy: 「あるある！」「自分もそう！」共感型（日常体験）
- reasons: なぜ今バズるのか（2〜3点）
- trending_angle: 今この瞬間の切り口（他と差別化する視点）
- search_keywords: Pexels動画検索用英語キーワード（3〜4個）

【出力形式】必ず以下のJSONのみを返してください（マークダウン不要、viral_score降順）:
{{
  "generated_at": "{today}",
  "genre": "{genre_name}",
  "topics": [
    {{
      "title": "トピックタイトル（25文字以内）",
      "viral_score": 9.5,
      "hook_shock": "衝撃型フック（20文字以内）",
      "hook_curiosity": "好奇心型フック（25文字以内）",
      "hook_empathy": "共感型フック（20文字以内）",
      "reasons": ["理由1", "理由2"],
      "trending_angle": "差別化する切り口（30文字以内）",
      "search_keywords": ["英語kw1", "英語kw2", "英語kw3"]
    }}
  ]
}}"""

    print(f"[00] {'web_search モード' if use_websearch else 'ナレッジベースモード'} でリサーチ中...")

    if use_websearch:
        try:
            raw = _run_with_websearch(client, prompt)
        except Exception as e:
            print(f"[00] web_search 失敗 ({e})、ナレッジベースにフォールバック")
            raw = _run_without_websearch(client, prompt)
    else:
        raw = _run_without_websearch(client, prompt)

    # JSON 抽出（```json ... ``` ブロックに包まれている場合も対応）
    text = raw.strip()
    if "```" in text:
        start = text.find("{")
        end = text.rfind("}") + 1
        text = text[start:end]

    result = json.loads(text)
    return result


# ─────────────────────────────────────────────
# キャッシュ管理
# ─────────────────────────────────────────────

def load_trend_cache() -> dict | None:
    """キャッシュファイルを読み込む。存在しない場合はNoneを返す。"""
    if not TREND_CACHE_FILE.exists():
        return None
    try:
        return json.loads(TREND_CACHE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return None


def save_trend_cache(data: dict):
    """トレンドデータをキャッシュファイルに保存する"""
    TREND_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    TREND_CACHE_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


# ─────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="トレンドトピックを調査してキャッシュに保存する")
    parser.add_argument("--account-id", default="account_01", help="ジャンル設定の参照先アカウント")
    parser.add_argument("--no-websearch", action="store_true",
                        help="web_search ツールを使わずナレッジベースのみで生成")
    args = parser.parse_args()

    genre_cfg = load_genre_config(args.account_id)
    use_websearch = not args.no_websearch

    print(f"\n[00] トレンドリサーチ開始")
    print(f"[00] ジャンル: {genre_cfg.get('name_jp', '(不明)')}")
    print(f"[00] モード: {'web_search' if use_websearch else 'ナレッジベース'}")

    result = research_trends(genre_cfg, use_websearch=use_websearch)
    topics = result.get("topics", [])

    save_trend_cache(result)

    print(f"\n[00] ✅ トレンドリサーチ完了: {len(topics)}件のトピック候補")
    print(f"[00] 保存先: {TREND_CACHE_FILE}")
    print(f"\n[00] TOP 5 バイラルトピック:")
    for i, t in enumerate(topics[:5], 1):
        score = t.get("viral_score", 0)
        title = t.get("title", "")
        angle = t.get("trending_angle", "")
        print(f"[00]   {i}. [{score:.1f}] {title}")
        print(f"[00]        → {angle}")
    print()


if __name__ == "__main__":
    main()
