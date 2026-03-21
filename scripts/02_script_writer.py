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
        # ─── ショート動画用 ───────────────────────────────────
        # 研究データ: 最適尺は25〜45秒、バイラル動画の平均は30.8秒
        # 1.5x速度で約5文字/秒 → 38秒ターゲット = 190文字
        target_sec = 38
        target_chars = 190

        hook_alternatives = concept.get("hook_alternatives", {})
        hook_shock     = hook_alternatives.get("shock", "")
        hook_curiosity = hook_alternatives.get("curiosity", "")
        hook_empathy   = hook_alternatives.get("empathy", "")
        trending_angle = concept.get("trending_angle", "")
        loop_cta_hint  = concept.get("loop_cta_hint", "末尾で冒頭フックに戻る言葉を入れてください")

        prompt = f"""あなたはYouTube Shortsで累計1億再生を達成した、データドリブンなバイラル原稿ライターです。

【動画情報】
トピック: {concept['topic']}
採用フック: {concept['hook']}
フック候補（参考）:
  衝撃型: {hook_shock}
  好奇心型: {hook_curiosity}
  共感型: {hook_empathy}
今の切り口: {trending_angle}
ループCTAヒント: {loop_cta_hint}

【動画構成（3セクション）】
{outline_text}

ジャンル: {genre_cfg['name_jp']}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【科学的に証明された伸びる原稿の5原則】
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

① 最適尺は38秒（190文字）
   バイラル動画の平均は30.8秒。長いより短い方が完了率が上がる。
   完了率70%超 → インプレッション+30%のアルゴリズム優遇が発動する。

② 遅延ペイオフ構造（Zeigarnik効果）
   フックで「謎」を提示 → 本編で焦らす → 最後に答え → CTA
   答えを最初に全部言わない。「〇〇の理由は後で話します」で引き伸ばす。

③ ループ構造（リプレイ率向上の最強技術）
   【重要】最後の文を、冒頭のフックに自然に繋がる形にすること。
   ループすると1ループ=1再生カウント。リプレイが増えるほどアルゴリズムが押す。
   例: 冒頭「なぜ人は損をするとわかってもやめられないのか」
       末尾「この答えが気になった人、もう一度最初から見てみてください」

④ 1文1メッセージ・12文字以内
   テロップ表示の鉄則。長い文は読まれずにスワイプされる。
   話しかけ口調・言い切り形・語尾の変化で単調さを防ぐ。

⑤ コミュニティ型CTA（「登録してください」は最悪）
   NG: 「チャンネル登録お願いします」（受動的）
   OK: 「〇〇派？それとも△△派？コメントで教えて」（二択で参加しやすい）
   最強: 「これ知らなかった人、コメントで教えて！毎週〇曜日に心理学の話してます」

━━━━━━━━━━━━━━━━━━━━━━━
【タイトル・ハッシュタグのルール】
━━━━━━━━━━━━━━━━━━━━━━━
- タイトル: 20〜30文字・4〜6語・絵文字1個（先頭か末尾）
  例: 「😮 試食したら買ってしまう心理の正体」
- ハッシュタグ: 3〜5個のみ（多すぎるとスパム判定）
  必須: #shorts  ニッチ: 2〜3個
- description: 60〜100文字（要約1文＋ハッシュタグ）

【出力形式】必ず以下のJSONのみを返してください（マークダウン不要）:
{{
  "title": "絵文字入りタイトル（20〜30文字・#Shortsは含めない）",
  "description": "要約1文（50字以内）\\n\\n#shorts #心理学 #豆知識（計3〜5個）",
  "tags": ["タグ1", "タグ2", ...(8〜12個)],
  "sentences": [
    {{"text": "冒頭フック（12文字以内・衝撃または謎かけ）", "section": "フック・掴み（10秒）", "index": 0}},
    {{"text": "謎の補強（12文字以内）", "section": "フック・掴み（10秒）", "index": 1}},
    {{"text": "本編（12文字以内）", "section": "本編・核心（25秒）", "index": 2}},
    ...,
    {{"text": "ループCTA（冒頭フックに戻る導線）", "section": "CTA・締め（3秒）", "index": N}}
  ]
}}

【品質チェックリスト（出力前に自分で確認）】
□ 合計文字数が約{target_chars}文字（{target_sec}秒）になっているか
□ 全文が12文字以内か
□ 最後の文が冒頭に戻るループ構造になっているか
□ CTAは二択コメント誘導か「また見てね」かループ誘導か
□ 答え（ペイオフ）が本編後半まで引き伸ばされているか
□ ハッシュタグが3〜5個以内か"""

        max_tokens = 2000

    else:
        # 横型動画用: ジャンルの設定通りの尺
        target_chars = int(duration_sec / 60 * 300)

        trending_angle = concept.get("trending_angle", "")
        hook_alternatives = concept.get("hook_alternatives", {})

        prompt = f"""あなたはYouTubeで視聴維持率80%超を安定的に達成する、データドリブンなナレーション原稿ライターです。

【動画情報】
トピック: {concept['topic']}
冒頭の掴み: {concept['hook']}
今の切り口: {trending_angle}

【動画構成（{len(concept['outline'])}セクション）】
{outline_text}

目標時間: {duration_sec}秒（約{target_chars}文字）
ジャンル: {genre_cfg['name_jp']}

━━━━━━━━━━━━━━━━━━━━━━━
【視聴維持率を最大化する7原則】
━━━━━━━━━━━━━━━━━━━━━━━

① 冒頭30秒以内に「何が得られるか」を明示
   「この動画を見ると〇〇がわかります」で離脱を防ぐ。

② 遅延ペイオフ構造（Zeigarnik効果）
   各セクションの冒頭で「謎・問い」を立て、末尾で解決する。
   「実はその理由が〇〇で、次のセクションで詳しく解説します」で橋渡し。

③ パターン中断で飽きを防ぐ
   長い説明の後に「ここで面白い研究があります」「驚くことに〜」などを挟む。
   統計 → エピソード → 実生活への応用 のサイクルで変化をつける。

④ 感情スパイクを意図的に配置
   驚き・共感・笑い・怒り のいずれかを各セクションに1回以上含める。
   純粋に「有益なだけ」の動画は視聴維持率が上がらない。

⑤ 具体的な数字・実名・エピソード
   「多くの人が〜」→ NG。「アメリカの心理学者チャルディーニが〜」→ OK。
   数字・人名・場所・実体験で信頼性と面白さを両立させる。

⑥ コミュニティ型CTA
   NG: 「チャンネル登録お願いします」
   OK: 「あなたはどっちだと思いますか？コメントで教えてください」
   最強: 「今日から試してみた人は、結果をコメントで報告してください。一緒に実験しましょう」

⑦ 1文1メッセージ（字幕表示のため）
   各sentenceは1〜2文の短い単位。30文字を超えたら分割する。

━━━━━━━━━━━━━━━━━━━━━━━
【SEO・メタデータのルール】
━━━━━━━━━━━━━━━━━━━━━━━
- タイトル: 30〜40文字・数字か絵文字1個・検索キーワードを自然に含む
- ハッシュタグ: 5〜8個のみ（多すぎるとスパム判定。10個超は禁止）
- description: 500〜700文字（概要→学べること箇条書き→チャプター→ハッシュタグ）

【出力形式】必ず以下のJSONのみを返してください（マークダウン不要）:
{{
  "title": "YouTube動画タイトル（30〜40文字・数字か絵文字1個含む）",
  "description": "動画説明文（①概要2文、②✅この動画でわかること（5点・絵文字付き）、③⏱チャプター（全セクション）、④ハッシュタグ5〜8個）",
  "tags": ["タグ1", "タグ2", ...(10〜15個)],
  "sentences": [
    {{"text": "ナレーション文（1〜2文・30文字以内推奨）", "section": "イントロ・掴み", "index": 0}},
    {{"text": "次のナレーション文", "section": "イントロ・掴み", "index": 1}},
    ...
  ]
}}

注意:
- sentencesの各要素は1〜2文の短い単位（字幕表示のため）
- section名はoutlineのtitleと一致させること
- indexは0始まりの連番
- ハッシュタグは5〜8個以内を厳守
- descriptionにYouTube SEOキーワードを自然に含める"""

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
