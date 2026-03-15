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

    prompt = f"""あなたはYouTube動画のコンテンツプランナーです。
今日の日付: {today}

ジャンル: {genre_cfg['name_jp']}
関連キーワード: {keywords_str}
ターゲット視聴者・コンテキスト: {context}

以下の条件でYouTube動画のトピックを3つ提案し、最も視聴者に刺さりそうなものを1つ選んで詳細な構成を作成してください。

【出力形式】必ず以下のJSONのみを返してください（マークダウン不要）:
{{
  "topic": "選択したトピック名（30文字以内）",
  "hook": "冒頭の掴み文（視聴者の興味を引く1文、50文字以内）",
  "outline": [
    {{"title": "セクション名", "keywords": ["Pexels検索用英語キーワード1", "英語キーワード2"]}},
    {{"title": "セクション名", "keywords": ["英語キーワード1", "英語キーワード2"]}},
    {{"title": "セクション名", "keywords": ["英語キーワード1", "英語キーワード2"]}},
    {{"title": "セクション名", "keywords": ["英語キーワード1", "英語キーワード2"]}},
    {{"title": "まとめ", "keywords": ["summary", "conclusion"]}}
  ],
  "search_keywords": ["Pexels全体検索用英語キーワード1", "英語キーワード2", "英語キーワード3"]
}}

注意:
- keywordsはPexels動画検索用なので必ず英語で
- outlineは5〜7セクション
- search_keywordsは3〜5個の英語キーワード"""

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
