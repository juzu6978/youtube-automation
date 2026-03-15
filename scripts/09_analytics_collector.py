"""
09_analytics_collector.py
YouTube Analytics API v2 で前日の指標を収集し
data/metrics/{account_id}/YYYY-MM-DD.json に保存する。

クォータコスト: 1ユニット/呼び出し
使い方:
  python scripts/09_analytics_collector.py --account-id account_01
  python scripts/09_analytics_collector.py --account-id account_01 --date 2026-03-13
"""

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.utils import load_account_config, load_accounts_registry
from scripts.08_config_loader import resolve_credentials


ANALYTICS_METRICS = ",".join([
    "views",
    "estimatedMinutesWatched",
    "subscribersGained",
    "subscribersLost",
    "impressionsClickThroughRate",
    "averageViewPercentage",
])


def build_analytics_client(credentials: dict):
    creds = Credentials(
        token=None,
        refresh_token=credentials["refresh_token"],
        client_id=credentials["client_id"],
        client_secret=credentials["client_secret"],
        token_uri="https://oauth2.googleapis.com/token",
        scopes=["https://www.googleapis.com/auth/yt-analytics.readonly"],
    )
    return build("youtubeAnalytics", "v2", credentials=creds)


def collect_for_account(account_id: str, target_date: date) -> dict:
    account_cfg = load_account_config(account_id)
    credentials = resolve_credentials(account_cfg)
    channel_id = account_cfg["account"]["channel_id"]

    client = build_analytics_client(credentials)
    date_str = target_date.strftime("%Y-%m-%d")

    response = client.reports().query(
        ids=f"channel=={channel_id}",
        startDate=date_str,
        endDate=date_str,
        metrics=ANALYTICS_METRICS,
    ).execute()

    if not response.get("rows"):
        metrics = {m: 0 for m in ANALYTICS_METRICS.split(",")}
    else:
        headers = [h["name"] for h in response["columnHeaders"]]
        metrics = dict(zip(headers, response["rows"][0]))

    payload = {
        "account_id": account_id,
        "date": date_str,
        "collected_at": date.today().isoformat(),
        "metrics": metrics,
    }

    output_dir = Path(f"data/metrics/{account_id}")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{date_str}.json"

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"[09] {account_id} / {date_str}: views={metrics.get('views', 0)}, subs+={metrics.get('subscribersGained', 0)}")
    return payload


def main():
    parser = argparse.ArgumentParser(description="YouTube Analytics を収集する")
    parser.add_argument("--account-id", help="特定アカウントのみ収集（省略時は全有効アカウント）")
    parser.add_argument("--date", help="収集対象日 YYYY-MM-DD（省略時は昨日）")
    args = parser.parse_args()

    target_date = date.fromisoformat(args.date) if args.date else date.today() - timedelta(days=1)

    if args.account_id:
        accounts = [{"id": args.account_id}]
    else:
        accounts = load_accounts_registry()

    for account in accounts:
        try:
            collect_for_account(account["id"], target_date)
        except Exception as e:
            print(f"[09] ERROR {account['id']}: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
