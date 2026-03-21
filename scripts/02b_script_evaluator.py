"""
02b_script_evaluator.py
生成されたナレーション原稿の品質を Claude API で評価し、基準を下回る場合は改善する。

評価軸（各20点・合計100点）:
  1. フック強度      : 最初1〜2文で「え？まじで？」と思わせるか（3要素フック）
  2. 遅延ペイオフ構造 : 謎かけ→焦らし→回収 の構造があるか（Zeigarnik効果）
  3. ループ・テンポ   : ループ構造があり1文12〜15文字以内か
  4. 感情トリガー     : 驚き・共感・不安・笑い のいずれかが発動しているか
  5. CTA・具体性     : コミュニティ型CTA + 数字・固有名詞・エピソードの豊富さ

75点未満の場合は詳細フィードバック付きで原稿を再生成する（最大3回）。

出力:
  {run_dir}/script.json          # 最終確定原稿（改善済み）
  {run_dir}/script_eval.json     # 評価履歴ログ
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

# 合格ライン（100点満点）
PASS_SCORE = 75
MAX_RETRIES = 3


# ─────────────────────────────────────────────
# 評価ロジック
# ─────────────────────────────────────────────

def evaluate_script(script: dict, concept: dict, fmt: str,
                    client: anthropic.Anthropic) -> dict:
    """
    スクリプトを5軸で評価し、スコアとフィードバックを返す。

    Returns:
        {
          "total": 82,
          "axes": {"hook": 18, "curiosity": 16, "tempo": 17, "emotion": 16, "specificity": 15},
          "feedback": "改善すべき点のリスト",
          "pass": True
        }
    """
    is_shorts = fmt in SHORT_FORMATS
    sentences_preview = "\n".join(
        f"  [{s['index']}] {s['text']}" for s in script["sentences"][:12]
    )
    last_sentences = "\n".join(
        f"  [{s['index']}] {s['text']}" for s in script["sentences"][-3:]
    )
    all_text = " ".join(s["text"] for s in script["sentences"])
    total_chars = sum(len(s["text"]) for s in script["sentences"])
    fmt_label = f"ショート動画（目標38秒≒190文字 / 現在{total_chars}文字）" if is_shorts else "横型動画（5〜8分）"

    loop_check = (
        "【ループ確認】冒頭フックと末尾CTAを見比べて、末尾が冒頭に自然に繋がるか判定してください。"
        if is_shorts else ""
    )

    prompt = f"""あなたはYouTube Shortsバイラルコンテンツの専門評価者です。
最新の研究データ（完了率・ループ率・コメント率がアルゴリズムの主要シグナル）に基づき、
以下の原稿を厳しく・公正に評価してください。

【動画フォーマット】{fmt_label}
【トピック】{concept.get('topic', '')}
【採用フック】{concept.get('hook', '')}

【冒頭12文】
{sentences_preview}

【末尾3文（ループ確認用）】
{last_sentences}

{loop_check}

【全文テキスト（参考）】
{all_text[:600]}...

━━━━━━━━━━━━━━━━━━━━━━━
【評価基準（各20点・合計100点）】
━━━━━━━━━━━━━━━━━━━━━━━

1. フック強度（0〜20点）
   視聴者がスクロールを止める「3秒の壁」を越えられるか。
   - 20点: 冒頭1〜2文に「衝撃の事実」「矛盾」「損失回避」の心理トリガーがある
   - 15点: 興味は引くが衝撃・矛盾感が弱い
   - 10点以下: 「こんにちは」「今日は〜について話します」型の致命的な出だし

2. 遅延ペイオフ構造（0〜20点）
   答えを最後まで引き伸ばし、Zeigarnik効果（未完への執着）を発動させているか。
   - 20点: フックで謎を提示→本編で焦らす→末尾で回収 の構造が明確
   - 15点: 焦らしはあるが弱い（すぐに答えを言っている）
   - 10点以下: 冒頭から情報を全部与えてしまっている

3. ループ・テンポ（0〜20点）
   {'ループ構造（末尾→冒頭への接続）と文の短さ・テンポを評価。' if is_shorts else '視聴維持のリズム・橋渡し表現・パターン中断を評価。'}
   - 20点: {'末尾が冒頭フックに自然に戻る構造。全文12〜15文字以内。' if is_shorts else 'セクション間の橋渡し・パターン中断が効いて飽きない。'}
   - 15点: {'ループ構造が弱い、または長文が混在。' if is_shorts else '橋渡しはあるが機械的で自然でない。'}
   - 10点以下: {'ループ構造なし、長文が多い。' if is_shorts else '単調な情報羅列。'}

4. 感情トリガー（0〜20点）
   驚き・共感・不安・笑い のいずれかが意図的に配置されているか。
   「役立つだけ」の動画はアルゴリズムに押されない。
   - 20点: 明確な感情スパイクが1箇所以上ある（「えっ！」と声が出るレベル）
   - 15点: 感情への訴えかけはあるが弱い
   - 10点以下: 終始フラットで感情的引っかかりがない

5. CTA・具体性（0〜20点）
   コミュニティ型CTAと具体的な数字・固有名詞・エピソードの組み合わせ。
   - 20点: 「〇〇か△△か、コメントで教えて」型の参加型CTA + 数字・研究名が豊富
   - 15点: CTAはあるが受動的「登録お願いします」。具体性は一定あり。
   - 10点以下: CTAなし or 抽象的「大切にしましょう」ばかり

【出力形式】必ず以下のJSONのみを返してください（マークダウン不要）:
{{
  "total": 75,
  "axes": {{
    "hook": 15,
    "payoff": 14,
    "loop_tempo": 16,
    "emotion": 15,
    "cta_specificity": 15
  }},
  "strengths": ["良い点1", "良い点2"],
  "feedback": [
    "改善点1: 具体的にどう直すか",
    "改善点2: 具体的にどう直すか",
    "改善点3: 具体的にどう直すか"
  ],
  "pass": false
}}

注意: total が 75 以上の場合のみ pass を true にしてください。"""

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.content[0].text.strip()
    if "```" in raw:
        start = raw.find("{")
        end = raw.rfind("}") + 1
        raw = raw[start:end]

    result = json.loads(raw)
    result["pass"] = result["total"] >= PASS_SCORE
    return result


# ─────────────────────────────────────────────
# 改善ロジック
# ─────────────────────────────────────────────

def improve_script(script: dict, concept: dict, genre_cfg: dict, fmt: str,
                   eval_result: dict, attempt: int,
                   client: anthropic.Anthropic) -> dict:
    """
    評価フィードバックを元に原稿を改善・再生成する。
    """
    feedback_str = "\n".join(f"  - {f}" for f in eval_result.get("feedback", []))
    strengths_str = "\n".join(f"  - {s}" for s in eval_result.get("strengths", []))
    axes = eval_result.get("axes", {})
    current_text = "\n".join(
        f"[{s['index']}] ({s['section']}) {s['text']}"
        for s in script["sentences"]
    )

    is_shorts = fmt in SHORT_FORMATS
    fmt_label = "ショート動画（55秒）" if is_shorts else "横型動画（5〜8分）"
    length_rule = "1文15文字以内・テンポよく・会話口調" if is_shorts else "1〜2文の短い単位・セクション橋渡しあり"

    prompt = f"""あなたはYouTube Shortsバイラルコンテンツの専門ライターです。
以下の原稿を評価フィードバックを元に改善してください。（改善試行: {attempt}/{MAX_RETRIES}回目）

【動画フォーマット】{fmt_label}
【トピック】{concept.get('topic', '')}
【フック】{concept.get('hook', '')}

【現在のスコア】{eval_result['total']}/100点（合格ライン: {PASS_SCORE}点）
  フック強度: {axes.get('hook', 0)}/20
  遅延ペイオフ構造: {axes.get('payoff', 0)}/20
  ループ・テンポ: {axes.get('loop_tempo', 0)}/20
  感情トリガー: {axes.get('emotion', 0)}/20
  CTA・具体性: {axes.get('cta_specificity', 0)}/20

【良い点（維持すること）】
{strengths_str}

【改善すべき点（必ず対処すること）】
{feedback_str}

【現在の原稿】
{current_text}

【改善指示】
- 上記フィードバックをすべて反映してください
- 良い点は維持してください
- 文の長さルール: {length_rule}
- section名・index番号はそのまま維持してください
- title・description・tagsも必要に応じて改善してください

【出力形式】必ず以下のJSONのみを返してください（マークダウン不要）:
{{
  "title": "改善後タイトル",
  "description": "改善後の説明文",
  "tags": ["タグ1", "タグ2"],
  "sentences": [
    {{"text": "改善後の文", "section": "セクション名", "index": 0}},
    ...
  ]
}}"""

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=6000 if not is_shorts else 2000,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.content[0].text.strip()
    if "```" in raw:
        start = raw.find("{")
        end = raw.rfind("}") + 1
        raw = raw[start:end]

    improved = json.loads(raw)

    # index を正規化
    for i, s in enumerate(improved["sentences"]):
        s["index"] = i

    return improved


# ─────────────────────────────────────────────
# メインフロー
# ─────────────────────────────────────────────

def evaluate_and_improve(run_dir: Path, genre_cfg: dict,
                         settings: dict, fmt: str) -> dict:
    """
    スクリプトを評価し、必要に応じて改善する。
    最終スクリプトを script.json に上書き保存し、評価ログを script_eval.json に保存する。
    """
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    script_path  = run_dir / "script.json"
    concept_path = run_dir / "concept.json"

    with open(script_path,  encoding="utf-8") as f:
        script = json.load(f)
    with open(concept_path, encoding="utf-8") as f:
        concept = json.load(f)

    eval_log = []
    best_script = script
    best_score  = 0

    print(f"\n[02b] スクリプト品質評価開始（合格ライン: {PASS_SCORE}点）")

    for attempt in range(MAX_RETRIES + 1):
        # ── 評価 ──
        label = "初回評価" if attempt == 0 else f"改善後評価 ({attempt}回目)"
        print(f"[02b] {label}...")

        eval_result = evaluate_script(script, concept, fmt, client)
        total = eval_result["total"]
        axes  = eval_result.get("axes", {})

        eval_log.append({"attempt": attempt, "score": total, "eval": eval_result})

        print(f"[02b] スコア: {total}/100点  "
              f"[フック:{axes.get('hook',0)} "
              f"遅延ペイオフ:{axes.get('payoff',0)} "
              f"ループ/テンポ:{axes.get('loop_tempo',0)} "
              f"感情:{axes.get('emotion',0)} "
              f"CTA/具体性:{axes.get('cta_specificity',0)}]")

        # ベストスコアを記録
        if total > best_score:
            best_score  = total
            best_script = script

        if eval_result["pass"]:
            print(f"[02b] ✅ 品質基準クリア！（{total}点）")
            break

        if attempt >= MAX_RETRIES:
            print(f"[02b] ⚠️  {MAX_RETRIES}回改善しましたが {PASS_SCORE}点未達。"
                  f"ベストスコア ({best_score}点) の原稿を採用します。")
            script = best_script
            break

        # ── 改善 ──
        feedback = eval_result.get("feedback", [])
        for fb in feedback:
            print(f"[02b]   💬 {fb}")
        print(f"[02b] 原稿を改善中（{attempt + 1}/{MAX_RETRIES}回目）...")

        script = improve_script(script, concept, genre_cfg, fmt, eval_result,
                                attempt + 1, client)

    # ── 最終スクリプトを保存 ──
    with open(script_path, "w", encoding="utf-8") as f:
        json.dump(script, f, ensure_ascii=False, indent=2)

    # ── 評価ログを保存 ──
    eval_log_path = run_dir / "script_eval.json"
    with open(eval_log_path, "w", encoding="utf-8") as f:
        json.dump({
            "fmt": fmt,
            "topic": concept.get("topic", ""),
            "final_score": best_score,
            "passed": best_score >= PASS_SCORE,
            "attempts": len(eval_log),
            "history": eval_log,
        }, f, ensure_ascii=False, indent=2)

    print(f"[02b] 評価ログ保存: {eval_log_path}")
    return script


# ─────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="スクリプトを評価し品質を保証する")
    parser.add_argument("--account-id", required=True)
    parser.add_argument("--run-id",     required=True)
    parser.add_argument("--format",     default="landscape")
    args = parser.parse_args()

    genre_cfg = load_genre_config(args.account_id)
    settings  = load_settings()
    run_dir   = get_run_dir(args.account_id, args.run_id, settings)

    evaluate_and_improve(run_dir, genre_cfg, settings, args.format)


if __name__ == "__main__":
    main()
