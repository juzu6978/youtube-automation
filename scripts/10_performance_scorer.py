"""
10_performance_scorer.py
全アカウントのメトリクスをスコアリングし、投稿頻度を自動リバランスする。

スコア計算式:
  composite = 0.70 * score_7d + 0.30 * score_30d
  score_Nd  = sum(metric_i * weight_i)  [全アカウント間でmin-max正規化]

  重み: subscribersGained_net=40%, views=25%, CTR=20%, avgViewPct=15%

投稿頻度マッピング:
  1位 → 週5本  (priority=high)
  2位 → 週3本  (priority=medium)
  3位以下 → 週1本  (priority=low)

使い方:
  python scripts/10_performance_scorer.py --mode rebalance
  python scripts/10_performance_scorer.py --mode rebalance --dry-run
  python scripts/10_performance_scorer.py --mode generate-workflows
"""

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.utils import load_accounts_registry, load_account_config


METRIC_WEIGHTS = {
    "subscribersGained_net": 0.40,
    "views": 0.25,
    "impressionsClickThroughRate": 0.20,
    "averageViewPercentage": 0.15,
}

RANK_TO_FREQ = {1: 5, 2: 3}   # 3位以下はデフォルト1
RANK_TO_PRIORITY = {1: "high", 2: "medium"}


# ─────────────────────────────────────────────────────────
# メトリクス集計
# ─────────────────────────────────────────────────────────

def load_metrics_for_days(account_id: str, n_days: int) -> dict:
    """過去 n_days 分の日次メトリクスを集計して返す"""
    today = date.today()
    totals: dict[str, float] = {k: 0.0 for k in METRIC_WEIGHTS}
    totals["subscribersGained_net"] = 0.0
    days_found = 0

    for i in range(1, n_days + 1):
        target = today - timedelta(days=i)
        path = Path(f"data/metrics/{account_id}/{target.isoformat()}.json")
        if not path.exists():
            continue
        with open(path) as f:
            data = json.load(f)
        m = data.get("metrics", {})
        totals["views"] += float(m.get("views", 0))
        totals["estimatedMinutesWatched"] = totals.get("estimatedMinutesWatched", 0) + float(m.get("estimatedMinutesWatched", 0))
        gained = float(m.get("subscribersGained", 0))
        lost = float(m.get("subscribersLost", 0))
        totals["subscribersGained_net"] += gained - lost
        totals["impressionsClickThroughRate"] += float(m.get("impressionsClickThroughRate", 0))
        totals["averageViewPercentage"] += float(m.get("averageViewPercentage", 0))
        days_found += 1

    if days_found > 0:
        totals["impressionsClickThroughRate"] /= days_found
        totals["averageViewPercentage"] /= days_found

    return totals


def minmax_normalize(values: list[float]) -> list[float]:
    """min-max 正規化 (0〜1)。全値が同じ場合は 0.5 を返す"""
    mn, mx = min(values), max(values)
    if mx == mn:
        return [0.5] * len(values)
    return [(v - mn) / (mx - mn) for v in values]


def compute_scores(accounts: list[dict]) -> list[dict]:
    """全アカウントのスコアを計算してランキング付きで返す"""
    account_ids = [a["id"] for a in accounts]

    # 7日・30日集計
    data_7 = {aid: load_metrics_for_days(aid, 7) for aid in account_ids}
    data_30 = {aid: load_metrics_for_days(aid, 30) for aid in account_ids}

    def score_from_raw(raw_list: list[dict]) -> list[float]:
        # 各メトリクスを正規化してから重み付け合計
        result = [0.0] * len(raw_list)
        for metric, weight in METRIC_WEIGHTS.items():
            vals = [r.get(metric, 0.0) for r in raw_list]
            normalized = minmax_normalize(vals)
            for i, n in enumerate(normalized):
                result[i] += n * weight
        return result

    raw_7 = [data_7[aid] for aid in account_ids]
    raw_30 = [data_30[aid] for aid in account_ids]
    scores_7 = score_from_raw(raw_7)
    scores_30 = score_from_raw(raw_30)

    composites = [0.70 * s7 + 0.30 * s30 for s7, s30 in zip(scores_7, scores_30)]

    ranked = sorted(
        zip(account_ids, composites),
        key=lambda x: x[1],
        reverse=True,
    )

    results = []
    for rank, (aid, score) in enumerate(ranked, start=1):
        results.append({
            "account_id": aid,
            "score": round(score, 4),
            "rank": rank,
            "videos_per_week": RANK_TO_FREQ.get(rank, 1),
            "priority": RANK_TO_PRIORITY.get(rank, "low"),
        })
    return results


# ─────────────────────────────────────────────────────────
# アカウント設定更新
# ─────────────────────────────────────────────────────────

def update_account_config(account_id: str, score_data: dict, dry_run: bool):
    config_path = Path(f"config/accounts/{account_id}.yaml")
    with open(config_path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    cfg["schedule"]["videos_per_week"] = score_data["videos_per_week"]
    cfg["schedule"]["priority"] = score_data["priority"]
    cfg["performance"]["score"] = score_data["score"]
    cfg["performance"]["score_rank"] = score_data["rank"]
    cfg["performance"]["last_scored_at"] = date.today().isoformat()

    history = cfg["performance"].get("score_history", []) or []
    history.append({"date": date.today().isoformat(), "score": score_data["score"]})
    cfg["performance"]["score_history"] = history[-4:]  # 直近4週のみ保持

    # upload_days を videos_per_week から逆算
    all_days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    vpw = score_data["videos_per_week"]
    step = max(1, len(all_days) // vpw)
    cfg["schedule"]["upload_days"] = all_days[::step][:vpw]

    if not dry_run:
        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(cfg, f, allow_unicode=True, default_flow_style=False)
        print(f"[10] {account_id}: rank={score_data['rank']}, score={score_data['score']:.4f}, {vpw}本/週 → 設定更新完了")
    else:
        print(f"[10] DRY RUN {account_id}: rank={score_data['rank']}, score={score_data['score']:.4f}, {vpw}本/週")


# ─────────────────────────────────────────────────────────
# GitHub Actions ワークフロー自動生成
# ─────────────────────────────────────────────────────────

DAY_TO_CRON_NUM = {
    "monday": 1, "tuesday": 2, "wednesday": 3,
    "thursday": 4, "friday": 5, "saturday": 6, "sunday": 0,
}


def generate_workflow_for_account(account_id: str, dry_run: bool):
    cfg = load_account_config(account_id)
    upload_days = cfg["schedule"]["upload_days"]
    upload_hour = cfg["schedule"]["upload_hour_utc"]
    acct_num = account_id.split("_")[-1]

    cron_lines = "\n".join(
        [f'    - cron: "0 {upload_hour} * * {DAY_TO_CRON_NUM[d]}"  # {d.capitalize()}'
         for d in upload_days]
    )

    # シークレット名のサフィックス（例: account_01 → ACCT01）
    secret_suffix = f"ACCT{acct_num.upper()}"

    workflow_content = f"""# Auto-generated by 10_performance_scorer.py - DO NOT EDIT MANUALLY
# Last updated: {date.today().isoformat()}
name: Upload - {account_id} ({cfg['account']['display_name']})

on:
  schedule:
{cron_lines}
  workflow_dispatch:

jobs:
  upload:
    uses: ./.github/workflows/upload_account.yml
    with:
      account_id: "{account_id}"
    secrets:
      YOUTUBE_REFRESH_TOKEN: ${{{{ secrets.YOUTUBE_REFRESH_TOKEN_{secret_suffix} }}}}
      YOUTUBE_CLIENT_ID: ${{{{ secrets.YOUTUBE_CLIENT_ID_{secret_suffix} }}}}
      YOUTUBE_CLIENT_SECRET: ${{{{ secrets.YOUTUBE_CLIENT_SECRET_{secret_suffix} }}}}
      ANTHROPIC_API_KEY: ${{{{ secrets.ANTHROPIC_API_KEY }}}}
      GCP_CREDENTIALS_JSON: ${{{{ secrets.GCP_CREDENTIALS_JSON }}}}
      PEXELS_API_KEY: ${{{{ secrets.PEXELS_API_KEY }}}}
      PIXABAY_API_KEY: ${{{{ secrets.PIXABAY_API_KEY }}}}
"""

    workflow_path = Path(f".github/workflows/upload_{account_id}.yml")

    if not dry_run:
        workflow_path.write_text(workflow_content, encoding="utf-8")
        print(f"[10] ワークフロー生成: {workflow_path} ({', '.join(upload_days)})")
    else:
        print(f"[10] DRY RUN: {workflow_path} を生成予定 ({', '.join(upload_days)})")


# ─────────────────────────────────────────────────────────
# エントリポイント
# ─────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="パフォーマンスをスコアリングしリバランスする")
    parser.add_argument(
        "--mode",
        choices=["rebalance", "generate-workflows", "score-only"],
        required=True,
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    accounts = load_accounts_registry()
    if not accounts:
        print("[10] 有効なアカウントが見つかりません。")
        sys.exit(0)

    if args.mode in ("rebalance", "score-only"):
        scores = compute_scores(accounts)
        print("\n=== パフォーマンスランキング ===")
        for s in scores:
            print(f"  #{s['rank']} {s['account_id']}: score={s['score']:.4f}, {s['videos_per_week']}本/週, priority={s['priority']}")

        if args.mode == "rebalance":
            print("\n=== 設定を更新します ===")
            score_map = {s["account_id"]: s for s in scores}
            for account in accounts:
                update_account_config(account["id"], score_map[account["id"]], args.dry_run)

    if args.mode == "generate-workflows":
        print("\n=== ワークフローを生成します ===")
        for account in accounts:
            generate_workflow_for_account(account["id"], args.dry_run)


if __name__ == "__main__":
    main()
