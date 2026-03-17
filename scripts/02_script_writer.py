"""
02_script_writer.py
concept.json を元に日本語ナレーション原稿を Claude API で生成する。

出力: {run_dir}/script.json
  {
    "title": "YouTube動画タイトル",
    "description": "動画説明文",
    "tags": ["タグ1", ...],
    "sentences": [
      {"text": "ナレーション文", "section": "セクション名", "index": 0}
    ]
  }
"""

import argparse
import json
import os
import sys
from pathlib import Path

import anthropic

sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.utils import load_genre_config, load_settings, get_run_dir


SHORT_FORMATS = ("shorts", "tiktok")


def generate_script(concept: dict, genre_cfg: dict, duration_sec: int,
                    run_dir: Path, fmt: str = "landscape") -> dict:
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    outline_text = "\n".join(
        [f"{i+1}. {s['title']}" for i, s in enumerate(concept["outline"])]
    )
    tags_str = "、".join(genre_cfg["tags"])

    if fmt in SHORT_FORMATS:
        # ショート動画用: 55秒・約275文字
        duration_sec = 55
        target_chars = 275

        prompt = f"""あなたはYouTubeショート・TikTokで1000万再生を誇るバイラル原稿ライターです。

トピック: {concept['topic']}
フック（最初の一言）: {concept['hook']}

動画構成（合計55秒）:
{outline_text}

目標時間: 55秒（約{target_chars}文字）
ジャンル: {genre_cfg['name_jp']}

【ショート動画の絶対ルール】
1. 最初の文はフックそのままか、それ以上に衝撃的な一言（3秒で視聴者を止める）
2. 1センテンスは15文字以内（テロップに収まる・読みやすい）
3. 句読点少なく、テンポよく、会話口調（です・ます調より話し言葉）
4. 「え？」「まじで？」「知らなかった」と思わせる情報を畳み掛ける
5. 最後はチャンネル登録・いいね・保存への自然な誘導

【出力形式】必ず以下のJSONのみを返してください（マークダウン不要）:
{{
  "title": "ショート動画タイトル（25文字以内・インパクト重視・#Shortsは含めない）",
  "description": "概要文（150〜200文字。動画の内容1〜2文 + ハッシュタグ5〜8個）",
  "tags": ["タグ1", ...(10〜15個)],
  "sentences": [
    {{"text": "フックの一言（15文字以内）", "section": "フック・掴み（10秒）", "index": 0}},
    {{"text": "次の一言", "section": "フック・掴み（10秒）", "index": 1}},
    ...
  ]
}}

注意:
- sentencesの各要素は1文・15文字以内の短い単位（字幕表示のため）
- 合計文字数が約{target_chars}文字になるよう調整
- section名はoutlineのtitleと一致
- indexは0始まりの連番"""

        max_tokens = 2000

    else:
        # 横型動画用: ジャンルの設定通りの尺
        target_chars = int(duration_sec / 60 * 300)

        prompt = f"""あなたはYouTubeで高い視聴維持率を誇るナレーション原稿ライターです。

トピック: {concept['topic']}
冒頭の掴み: {concept['hook']}

動画構成:
{outline_text}

目標時間: {duration_sec}秒（約{target_chars}文字）
ジャンル: {genre_cfg['name_jp']}
関連タグ: {tags_str}

【指示】
1. 上記の構成に沿って、自然な日本語ナレーション原稿を書いてください
2. 各セクションの冒頭で「〇つ目は〜」「次に〜」など視聴者を引き込む言葉を使ってください
3. 具体的な数字・実例・エピソードを豊富に盛り込み、視聴者が飽きないようにしてください
4. 文体は「です・ます調」で、話しかけるような親しみやすいトーンにしてください
5. イントロ（30〜45秒）で「この動画を見ると何が得られるか」を明確に伝えてください
6. アウトロ（30〜45秒）には「高評価・チャンネル登録・コメント」への自然な誘導を入れてください
7. 各セクションの終わりに次セクションへの橋渡しを入れ、視聴維持率を上げてください

【出力形式】必ず以下のJSONのみを返してください（マークダウン不要）:
{{
  "title": "YouTube動画タイトル（40文字以内、数字・感情語・検索キーワードを含む）",
  "description": "動画説明文（500〜800文字。①動画概要2〜3文、②「✅この動画でわかること」箇条書き5点（絵文字付き）、③チャプター（0:00 イントロ の形式で全セクション）、④ハッシュタグ8〜10個 の順で構成）",
  "tags": ["タグ1", "タグ2", ...(15〜20個)],
  "sentences": [
    {{"text": "ナレーション文（1〜2文）", "section": "イントロ・掴み", "index": 0}},
    {{"text": "次のナレーション文", "section": "イントロ・掴み", "index": 1}},
    ...
  ]
}}

注意:
- sentencesの各要素は1〜2文の短い単位にしてください（字幕表示のため）
- section名はoutlineのtitleと一致させてください
- indexは0始まりの連番
- descriptionにはYouTube SEOに効くキーワードを自然に含めること"""

        max_tokens = 8000

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = message.content[0].text.strip()
    script = json.loads(raw)

    # index を正規化
    for i, s in enumerate(script["sentences"]):
        s["index"] = i

    output_path = run_dir / "script.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(script, f, ensure_ascii=False, indent=2)

    total_chars = sum(len(s["text"]) for s in script["sentences"])
    print(f"[02] 原稿生成完了: {len(script['sentences'])}文、合計{total_chars}文字 [{fmt}]")
    print(f"[02] タイトル: {script['title']}")
    return script


def main():
    parser = argparse.ArgumentParser(description="日本語ナレーション原稿を生成する")
    parser.add_argument("--account-id", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--format", default="landscape",
                        help="フォーマット: landscape | shorts | tiktok")
    args = parser.parse_args()

    genre_cfg = load_genre_config(args.account_id)
    settings = load_settings()
    run_dir = get_run_dir(args.account_id, args.run_id, settings)

    concept_path = run_dir / "concept.json"
    with open(concept_path, encoding="utf-8") as f:
        concept = json.load(f)

    generate_script(concept, genre_cfg, genre_cfg["duration_sec"], run_dir, fmt=args.format)


if __name__ == "__main__":
    main()
