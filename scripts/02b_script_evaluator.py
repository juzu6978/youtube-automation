"""
02b_script_evaluator.py
生成されたナレーション原稿の品質を Claude API で評価し、基準を下回る場合は改善する。

評価軸（各20点・合計100点）:
  1. フック強度   : 最初の1文で「え？」と思わせるか
  2. 好奇心ギャップ: 「続きが気になる」構造になっているか
  3. テンポ       : 1文15文字以内・言い切り形が多いか（Shorts）
  4. 感情トリガー  : 驚き・共感・不安・笑い のいずれかがあるか
  5. 具体性       : 数字・固有名詞・実体験エピソードが含まれるか

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
    sentences_preview = "\n".join(
        f"  [{s['index']}] {s['text']}" for s in script["sentences"][:10]
    )
    all_text = " ".join(s["text"] for s in script["sentences"])
    fmt_label = "ショート動画（55秒）" if fmt in SHORT_FORMATS else "横型動画（5〜8分）"

    prompt = f"""あなたはYouTubeバイラルコンテンツの専門評価者です。
以下のナレーション原稿を厳しく・公正に評価してください。

【動画フォーマット】{fmt_label}
【トピック】{concept.get('topic', '')}
【採用フック】{concept.get('hook', '')}

【原稿（先頭10文）】
{sentences_preview}
...（全{len(script['sentences'])}文）

【全文の流れ】
{all_text[:500]}...

【評価基準（各20点・合計100点）】

1. フック強度（0〜20点）
   - 20点: 最初の1文で「え？まじで？」と思わせる衝撃がある
   - 15点: 興味を引くが衝撃は弱い
   - 10点以下: フックが弱く離脱されやすい

2. 好奇心ギャップ（0〜20点）
   - 20点: 「続きが気になる」「なぜ？」という謎かけ構造がある
   - 15点: 一定の引力はあるが弱い
   - 10点以下: 情報を並べているだけで引力がない

3. テンポ・読みやすさ（0〜20点）
   （Shorts: 1文15文字以内・言い切り形、Long: リズムよく橋渡しがある）
   - 20点: テンポが抜群で引き込まれる
   - 15点: 概ね良いが一部もたつく
   - 10点以下: 長文・回りくどい表現が多い

4. 感情トリガー（0〜20点）
   - 20点: 驚き・共感・不安・笑い のいずれかが強く発動している
   - 15点: 感情への訴えかけは一定あるが弱い
   - 10点以下: 感情的な引っかかりがほぼない

5. 具体性・信頼性（0〜20点）
   - 20点: 数字・研究名・実体験エピソード・固有名詞が豊富
   - 15点: 一部具体的だが抽象表現が多い
   - 10点以下: 具体性がほぼなく「〜が大切です」で終わっている

【出力形式】必ず以下のJSONのみを返してください（マークダウン不要）:
{{
  "total": 75,
  "axes": {{
    "hook": 15,
    "curiosity": 14,
    "tempo": 16,
    "emotion": 15,
    "specificity": 15
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

    prompt = f"""あなたはYouTubeバイラルコンテンツの専門ライターです。
以下の原稿を評価フィードバックを元に改善してください。（改善試行: {attempt}/{MAX_RETRIES}回目）

【動画フォーマット】{fmt_label}
【トピック】{concept.get('topic', '')}
【フック】{concept.get('hook', '')}

【現在のスコア】{eval_result['total']}/100点（合格ライン: {PASS_SCORE}点）
  フック強度: {axes.get('hook', 0)}/20
  好奇心ギャップ: {axes.get('curiosity', 0)}/20
  テンポ: {axes.get('tempo', 0)}/20
  感情トリガー: {axes.get('emotion', 0)}/20
  具体性: {axes.get('specificity', 0)}/20

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
              f"[フック:{axes.get('hook',0)} 好奇心:{axes.get('curiosity',0)} "
              f"テンポ:{axes.get('tempo',0)} 感情:{axes.get('emotion',0)} "
              f"具体性:{axes.get('specificity',0)}]")

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
