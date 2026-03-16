"""
01_concept_generator.py
トピック・動画構成を Claude API で生成する。

出力: {run_dir}/concept.json
  {
    "topic": "string",
    "hook": "string",
    "outline": [
      {"title": "string", "keywords": ["string"]}
    ],
    "search_keywords": ["string"]
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


def generate_concept(genre_cfg: dict, run_dir: Path) -> dict:
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    today = date.today().strftime("%Y年%m月%d日")
    keywords_str = "、".join(genre_cfg["keywords"])
    context = genre_cfg.get("prompt_context", "")

    prompt = f"""あなたはYouTubeで100万再生を獲得した実績のあるコンテンツプランナーです。
今日の日付: {today}

ジャンル: {genre_cfg['name_jp']}
関連キーワード: {keywords_str}
ターゲット視聴者: {context}

【日本のYouTubeで高クリック率を生む法則】
✓ 数字を使う：「7つの方法」「90%が知らない」「3分でわかる」
✓ 問いかけ：「あなたの〇〇、大丈夫ですか？」
✓ 緊急性：「今すぐ〜しないと」「〇〇前に必ず見て」
✓ 意外性：「実は〜だった」「専門家が教えない〜」
✓ 利得：「〇〇するだけで〜できる」「無料で〜を手に入れる方法」

良いタイトル例：
- 「90%の人が知らない！ChatGPTの使い方で年収が変わる理由」
- 「今すぐやめて！スマホの充電習慣、間違えると半年で壊れる」
- 「【保存版】プロが教えるAI副業で月10万円稼ぐ完全ロードマップ」

以下の条件でYouTube動画のトピックを3つ提案し、最もクリックされそうなものを1つ選んで詳細な構成を作成してください。

【出力形式】必ず以下のJSONのみを返してください（マークダウン不要）:
{{
  "topic": "選択したトピック名（30文字以内）",
  "hook": "冒頭の掴み文（視聴者の感情＝不安・好奇心・期待を刺激する1文、50文字以内）",
  "outline": [
    {{"title": "イントロ・掴み", "keywords": ["Pexels検索用英語キーワード1", "英語キーワード2"]}},
    {{"title": "セクション名2（具体的に）", "keywords": ["英語キーワード1", "英語キーワード2"]}},
    {{"title": "セクション名3（具体的に）", "keywords": ["英語キーワード1", "英語キーワード2"]}},
    {{"title": "セクション名4（具体的に）", "keywords": ["英語キーワード1", "英語キーワード2"]}},
    {{"title": "セクション名5（具体的に）", "keywords": ["英語キーワード1", "英語キーワード2"]}},
    {{"title": "セクション名6（具体的に）", "keywords": ["英語キーワード1", "英語キーワード2"]}},
    {{"title": "セクション名7（具体的に）", "keywords": ["英語キーワード1", "英語キーワード2"]}},
    {{"title": "まとめ・行動促進", "keywords": ["summary", "success", "motivation"]}}
  ],
  "search_keywords": ["Pexels全体検索用英語キーワード1", "英語キーワード2", "英語キーワード3", "英語キーワード4"]
}}

注意:
- keywordsはPexels動画検索用なので必ず英語で
- outlineは7〜8セクション（8分動画のため）
- topicはYouTubeサジェスト・検索に引っかかりやすいキーワードを含めること
- hookは視聴者が「もっと見たい」と思わせる強い言葉にすること
- search_keywordsは4〜5個の英語キーワード"""

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = message.content[0].text.strip()
    concept = json.loads(raw)

    output_path = run_dir / "concept.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(concept, f, ensure_ascii=False, indent=2)

    print(f"[01] トピック生成完了: {concept['topic']}")
    print(f"[01] 保存先: {output_path}")
    return concept


def main():
    parser = argparse.ArgumentParser(description="トピック・構成を生成する")
    parser.add_argument("--account-id", required=True)
    parser.add_argument("--run-id", required=True, help="実行ID（タイムスタンプ等）")
    args = parser.parse_args()

    genre_cfg = load_genre_config(args.account_id)
    settings = load_settings()
    run_dir = get_run_dir(args.account_id, args.run_id, settings)
    run_dir.mkdir(parents=True, exist_ok=True)

    generate_concept(genre_cfg, run_dir)


if __name__ == "__main__":
    main()
