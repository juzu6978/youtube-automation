"""
01_concept_generator.py
トピック・動画構成を Claude API で生成する。

強化機能:
  - assets/trend_cache/scored_topics.json が存在する場合、トレンドデータを入力として活用
  - hook を3パターン（衝撃型・好奇心型・共感型）生成し、最強フックを自動選択
  - concept.json に hook_alternatives（他の候補）も保存

出力: {run_dir}/concept.json
  {
    "topic": "string",
    "hook": "string（最強フックとして選ばれたもの）",
    "hook_alternatives": {"shock": "...", "curiosity": "...", "empathy": "..."},
    "hook_type": "shock | curiosity | empathy",
    "outline": [{"title": "string", "keywords": ["string"]}],
    "search_keywords": ["string"],
    "viral_score": 9.0,       # トレンドキャッシュが有効な場合のみ
    "trending_angle": "..."   # トレンドキャッシュが有効な場合のみ
  }
"""

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path

import anthropic

sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.utils import load_genre_config, load_settings, get_run_dir


SHORT_FORMATS = ("shorts", "tiktok")

TREND_CACHE_FILE = (
    Path(__file__).parent.parent / "assets" / "trend_cache" / "scored_topics.json"
)


# ─────────────────────────────────────────────
# トレンドキャッシュ読み込み
# ─────────────────────────────────────────────

def load_trend_cache(top_n: int = 5) -> list[dict]:
    """
    トレンドキャッシュから上位N件を読み込む。
    キャッシュが存在しない場合は空リストを返す。
    """
    if not TREND_CACHE_FILE.exists():
        return []
    try:
        data = json.loads(TREND_CACHE_FILE.read_text(encoding="utf-8"))
        topics = data.get("topics", [])
        # viral_score の高い順にソートして上位N件を返す
        return sorted(topics, key=lambda t: t.get("viral_score", 0), reverse=True)[:top_n]
    except Exception as e:
        print(f"[01] トレンドキャッシュの読み込みに失敗: {e}")
        return []


def _build_trend_context(trending_topics: list[dict]) -> str:
    """トレンドデータを Claude プロンプト用のテキストに変換する"""
    if not trending_topics:
        return ""

    lines = ["【今週のバイラルトレンド TOP（このデータを最大限活用すること）】"]
    for i, t in enumerate(trending_topics, 1):
        lines.append(
            f"{i}. [{t.get('viral_score', 0):.1f}点] {t.get('title', '')}"
            f"  → 切り口: {t.get('trending_angle', '')}"
        )
        # フック候補も渡す
        if t.get("hook_shock"):
            lines.append(f"   衝撃型: {t['hook_shock']}")
        if t.get("hook_curiosity"):
            lines.append(f"   好奇心型: {t['hook_curiosity']}")
        if t.get("hook_empathy"):
            lines.append(f"   共感型: {t['hook_empathy']}")
    lines.append("\n上記のトレンドを参考に、今最も刺さるトピックを選んでください。")
    return "\n".join(lines)


# ─────────────────────────────────────────────
# コンセプト生成
# ─────────────────────────────────────────────

def generate_concept(genre_cfg: dict, run_dir: Path,
                     fmt: str = "landscape",
                     trending_topics: list[dict] | None = None) -> dict:
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    today = date.today().strftime("%Y年%m月%d日")
    keywords_str = "、".join(genre_cfg["keywords"])
    context = genre_cfg.get("prompt_context", "")
    trend_section = _build_trend_context(trending_topics or [])
    has_trend = bool(trending_topics)

    if fmt in SHORT_FORMATS:
        # ─ ショート動画用プロンプト ─
        prompt = f"""あなたはYouTubeショート・TikTokで1000万再生を獲得した実績のある
バイラルコンテンツプランナーです。

今日の日付: {today}
ジャンル: {genre_cfg['name_jp']}
関連キーワード: {keywords_str}
ターゲット視聴者: {context}

{trend_section}

【縦型ショート動画（55秒）で爆発的に再生される法則】
✓ 最初3秒で全て決まる：「え、まじ？」「知らなかった...」と言わせる衝撃の一言
✓ テンポが命：1センテンス2〜3秒、テンポよく畳み掛ける
✓ 好奇心ギャップ：「〜って知ってた？」「実は〜なんです」
✓ 25文字以内のタイトル：短く・インパクト重視

良いショートタイトル例:
- 「ChatGPTの使い方、99%が知らない」
- 「スマホ充電、やってはいけない方法」
- 「人を動かす心理学の裏技3選」

【重要】hook は3パターン必ず生成すること:
  - hook_shock    : 「え？」「まじで？」と思わせる衝撃の事実（脳を刺す）
  - hook_curiosity: 「なぜ〜なのか？」「実は〜」謎かけ型（好奇心を刺激）
  - hook_empathy  : 「〜したことありませんか？」「あなたも〜」共感型（自分事化）

【出力形式】必ず以下のJSONのみを返してください（マークダウン不要）:
{{
  "topic": "選択したトピック名（25文字以内・インパクト重視）",
  "hook_shock": "衝撃型フック（20文字以内）",
  "hook_curiosity": "好奇心型フック（25文字以内）",
  "hook_empathy": "共感型フック（20文字以内）",
  "best_hook_type": "shock | curiosity | empathy （最も強力なものを選ぶ）",
  "best_hook_reason": "このフックを選んだ理由（30文字以内）",
  "outline": [
    {{"title": "フック・掴み（10秒）", "keywords": ["英語kw1", "英語kw2"]}},
    {{"title": "本編・核心（35秒）", "keywords": ["英語kw1", "英語kw2"]}},
    {{"title": "CTA・締め（10秒）", "keywords": ["motivation", "success"]}}
  ],
  "search_keywords": ["英語kw1", "英語kw2", "英語kw3"],
  "viral_score": 8.5,
  "trending_angle": "今この瞬間に刺さる切り口（30文字以内）"
}}

注意:
- keywordsはPexels動画検索用なので必ず英語で
- outlineは必ず3セクション（フック/本編/CTA）
- topicは25文字以内の短くてインパクトのあるタイトル
- {f"トレンドデータを最大限に活用し、viral_scoreが高いトピックを選ぶこと" if has_trend else "トレンド性の高いトピックを独自に考案すること"}"""

    else:
        # ─ 横型動画用プロンプト ─
        prompt = f"""あなたはYouTubeで100万再生を獲得した実績のあるコンテンツプランナーです。

今日の日付: {today}
ジャンル: {genre_cfg['name_jp']}
関連キーワード: {keywords_str}
ターゲット視聴者: {context}

{trend_section}

【日本のYouTubeで高クリック率を生む法則】
✓ 数字を使う：「7つの方法」「90%が知らない」「3分でわかる」
✓ 問いかけ：「あなたの〇〇、大丈夫ですか？」
✓ 緊急性：「今すぐ〜しないと」「〇〇前に必ず見て」
✓ 意外性：「実は〜だった」「専門家が教えない〜」
✓ 利得：「〇〇するだけで〜できる」「無料で〜を手に入れる方法」

良いタイトル例:
- 「90%の人が知らない！ChatGPTの使い方で年収が変わる理由」
- 「今すぐやめて！スマホの充電習慣、間違えると半年で壊れる」
- 「【保存版】プロが教えるAI副業で月10万円稼ぐ完全ロードマップ」

【重要】hook は3パターン必ず生成すること:
  - hook_shock    : 衝撃的な事実・数字・逆説
  - hook_curiosity: 謎かけ・問いかけ・「なぜ〜なのか」
  - hook_empathy  : 視聴者が「自分のことだ」と感じる共感型

【出力形式】必ず以下のJSONのみを返してください（マークダウン不要）:
{{
  "topic": "選択したトピック名（30文字以内）",
  "hook_shock": "衝撃型フック（40文字以内）",
  "hook_curiosity": "好奇心型フック（50文字以内）",
  "hook_empathy": "共感型フック（40文字以内）",
  "best_hook_type": "shock | curiosity | empathy",
  "best_hook_reason": "このフックを選んだ理由（30文字以内）",
  "outline": [
    {{"title": "イントロ・掴み", "keywords": ["英語kw1", "英語kw2"]}},
    {{"title": "セクション名2", "keywords": ["英語kw1", "英語kw2"]}},
    {{"title": "セクション名3", "keywords": ["英語kw1", "英語kw2"]}},
    {{"title": "セクション名4", "keywords": ["英語kw1", "英語kw2"]}},
    {{"title": "セクション名5", "keywords": ["英語kw1", "英語kw2"]}},
    {{"title": "セクション名6", "keywords": ["英語kw1", "英語kw2"]}},
    {{"title": "セクション名7", "keywords": ["英語kw1", "英語kw2"]}},
    {{"title": "まとめ・行動促進", "keywords": ["summary", "success", "motivation"]}}
  ],
  "search_keywords": ["英語kw1", "英語kw2", "英語kw3", "英語kw4"],
  "viral_score": 8.0,
  "trending_angle": "今この瞬間に刺さる切り口（30文字以内）"
}}

注意:
- keywordsはPexels動画検索用なので必ず英語で
- outlineは7〜8セクション（8分動画のため）
- {f"トレンドデータを最大限に活用し、viral_scoreが高いトピックを選ぶこと" if has_trend else "トレンド性の高いトピックを独自に考案すること"}"""

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = message.content[0].text.strip()
    if "```" in raw:
        start = raw.find("{")
        end = raw.rfind("}") + 1
        raw = raw[start:end]

    data = json.loads(raw)

    # ── hook を整理 ──
    hook_type = data.get("best_hook_type", "curiosity")
    hook_map = {
        "shock":    data.get("hook_shock", ""),
        "curiosity": data.get("hook_curiosity", ""),
        "empathy":  data.get("hook_empathy", ""),
    }
    selected_hook = hook_map.get(hook_type, hook_map["curiosity"])

    # ── concept.json 用の標準フォーマットに整形 ──
    concept = {
        "topic":    data["topic"],
        "hook":     selected_hook,          # 最強フック（スクリプト生成で使用）
        "hook_alternatives": hook_map,      # 他の候補（参考用）
        "hook_type": hook_type,
        "hook_reason": data.get("best_hook_reason", ""),
        "outline":  data["outline"],
        "search_keywords": data["search_keywords"],
        "viral_score": data.get("viral_score", 0.0),
        "trending_angle": data.get("trending_angle", ""),
    }

    output_path = run_dir / "concept.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(concept, f, ensure_ascii=False, indent=2)

    print(f"[01] トピック生成完了: {concept['topic']} [{fmt}]")
    print(f"[01] バイラルスコア: {concept['viral_score']}")
    print(f"[01] 採用フック ({hook_type}型): {selected_hook}")
    print(f"[01]   衝撃型: {hook_map['shock']}")
    print(f"[01]   好奇心型: {hook_map['curiosity']}")
    print(f"[01]   共感型: {hook_map['empathy']}")
    print(f"[01] 保存先: {output_path}")
    return concept


# ─────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="トピック・構成を生成する")
    parser.add_argument("--account-id", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--format", default="landscape",
                        help="フォーマット: landscape | shorts | tiktok")
    parser.add_argument("--no-trend", action="store_true",
                        help="トレンドキャッシュを使用しない")
    args = parser.parse_args()

    genre_cfg = load_genre_config(args.account_id)
    settings  = load_settings()
    run_dir   = get_run_dir(args.account_id, args.run_id, settings)
    run_dir.mkdir(parents=True, exist_ok=True)

    # トレンドキャッシュを読み込む
    trending_topics = [] if args.no_trend else load_trend_cache(top_n=5)
    if trending_topics:
        print(f"[01] トレンドキャッシュ読み込み: {len(trending_topics)}件のトピック候補を活用")
    else:
        print(f"[01] トレンドキャッシュなし（独自生成モード）")

    generate_concept(genre_cfg, run_dir, fmt=args.format,
                     trending_topics=trending_topics)


if __name__ == "__main__":
    main()
