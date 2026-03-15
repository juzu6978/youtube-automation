"""
11_dashboard_builder.py
全アカウントの日次メトリクスを集計し、
ダッシュボード用の summary.json を生成する。

出力: data/metrics/summary.json
使い方:
  python scripts/11_dashboard_builder.py
"""

import json
import sys
from datetime import date, timedelta
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.utils import load_accounts_registry, load_account_config


def load_recent_metrics(account_id: str, n_days: int = 30) -> list[dict]:
    """過去 n_days 日分の日次データを日付昇順で返す"""
    today = date.today()
    records = []
    for i in range(n_days, 0, -1):
        target = today - timedelta(days=i)
        path = Path(f"data/metrics/{account_id}/{target.isoformat()}.json")
        if not path.exists():
            continue
        with open(path) as f:
            records.append(json.load(f))
    return records


def summarize_account(account_id: str) -> dict:
    account_cfg = load_account_config(account_id)
    records_30 = load_recent_metrics(account_id, 30)
    records_7 = records_30[-7:] if len(records_30) >= 7 else records_30

    def aggregate(records: list[dict]) -> dict:
        totals = {
            "views": 0,
            "estimatedMinutesWatched": 0.0,
            "subscribersGained": 0,
            "subscribersLost": 0,
            "subscribersNet": 0,
            "impressionsClickThroughRate": 0.0,
            "averageViewPercentage": 0.0,
        }
        days = 0
        for r in records:
            m = r.get("metrics", {})
            totals["views"] += int(m.get("views", 0))
            totals["estimatedMinutesWatched"] += float(m.get("estimatedMinutesWatched", 0))
            gained = int(m.get("subscribersGained", 0))
            lost = int(m.get("subscribersLost", 0))
            totals["subscribersGained"] += gained
            totals["subscribersLost"] += lost
            totals["subscribersNet"] += gained - lost
            totals["impressionsClickThroughRate"] += float(m.get("impressionsClickThroughRate", 0))
            totals["averageViewPercentage"] += float(m.get("averageViewPercentage", 0))
            days += 1
        if days > 0:
            totals["impressionsClickThroughRate"] = round(totals["impressionsClickThroughRate"] / days, 4)
            totals["averageViewPercentage"] = round(totals["averageViewPercentage"] / days, 2)
        return totals

    # 日次トレンド用データ（折れ線グラフ）
    daily_trend = []
    for r in records_30:
        m = r.get("metrics", {})
        daily_trend.append({
            "date": r["date"],
            "views": int(m.get("views", 0)),
            "subscribersNet": int(m.get("subscribersGained", 0)) - int(m.get("subscribersLost", 0)),
        })

    perf = account_cfg.get("performance", {})

    return {
        "account_id": account_id,
        "display_name": account_cfg["account"]["display_name"],
        "genre": account_cfg["content"]["genre"],
        "priority": account_cfg["schedule"]["priority"],
        "videos_per_week": account_cfg["schedule"]["videos_per_week"],
        "score": perf.get("score", 0.0),
        "score_rank": perf.get("score_rank"),
        "last_scored_at": perf.get("last_scored_at"),
        "metrics_7d": aggregate(records_7),
        "metrics_30d": aggregate(records_30),
        "daily_trend": daily_trend,
    }


def build_summary():
    accounts = load_accounts_registry()
    summaries = []

    for account in accounts:
        try:
            summary = summarize_account(account["id"])
            summaries.append(summary)
            print(f"[11] {account['id']}: 集計完了")
        except Exception as e:
            print(f"[11] ERROR {account['id']}: {e}", file=sys.stderr)

    # スコア順にソート
    summaries.sort(key=lambda x: x.get("score", 0), reverse=True)

    output = {
        "generated_at": date.today().isoformat(),
        "accounts": summaries,
    }

    output_path = Path("data/metrics/summary.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"[11] summary.json 生成完了: {output_path} ({len(summaries)}アカウント)")
    return output


if __name__ == "__main__":
    build_summary()
