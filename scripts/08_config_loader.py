"""
08_config_loader.py
アカウント設定を読み込み、認証情報をGitHub Secrets（環境変数）から解決する。

使い方:
  python scripts/08_config_loader.py --account-id account_01
  python scripts/08_config_loader.py --account-id account_01 --output-format github-env
"""

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.utils import load_account_config


def resolve_credentials(account_cfg: dict) -> dict:
    """
    account.yaml の credentials ブロックに記載されたシークレット名を
    実際の環境変数値に解決して返す。
    """
    creds_cfg = account_cfg["credentials"]
    result = {}
    for key, secret_name in creds_cfg.items():
        value = os.environ.get(secret_name)
        if not value:
            raise EnvironmentError(
                f"必須シークレット '{secret_name}' が環境変数に設定されていません。"
                f"GitHub Secrets に追加し、workflow の env: ブロックで渡してください。"
            )
        # キー名からサフィックスを除去してシンプルなキーに
        simple_key = key.removesuffix("_secret")
        result[simple_key] = value
    return result


def write_to_github_env(account_cfg: dict):
    """アカウント設定の主要な値を $GITHUB_ENV に書き出す"""
    github_env = os.environ.get("GITHUB_ENV")
    if not github_env:
        print("WARNING: GITHUB_ENV が設定されていません（GitHub Actions 外で実行中？）")
        return

    account = account_cfg["account"]
    content = account_cfg["content"]
    tts = account_cfg["tts"]
    schedule = account_cfg["schedule"]

    env_vars = {
        "ACCOUNT_ID": account["id"],
        "ACCOUNT_DISPLAY_NAME": account["display_name"],
        "CHANNEL_ID": account["channel_id"],
        "GENRE": content["genre"],
        "TTS_VOICE_ID": tts["voice_id"],
        "TTS_PROVIDER": tts["provider"],
        "SPEAKING_RATE": str(tts.get("speaking_rate", 0.95)),
        "VIDEOS_PER_WEEK": str(schedule["videos_per_week"]),
        "PRIORITY": schedule["priority"],
    }

    with open(github_env, "a", encoding="utf-8") as f:
        for k, v in env_vars.items():
            f.write(f"{k}={v}\n")
    print(f"[08] {len(env_vars)} 個の設定値を GITHUB_ENV に書き込みました")


def main():
    parser = argparse.ArgumentParser(description="アカウント設定を読み込み・検証する")
    parser.add_argument("--account-id", required=True)
    parser.add_argument(
        "--output-format",
        choices=["json", "github-env", "none"],
        default="none",
    )
    args = parser.parse_args()

    cfg = load_account_config(args.account_id)

    if args.output_format == "json":
        # 認証情報の値は出力しない（名前のみ）
        safe_cfg = {k: v for k, v in cfg.items() if k != "credentials"}
        print(json.dumps(safe_cfg, ensure_ascii=False, indent=2))

    elif args.output_format == "github-env":
        write_to_github_env(cfg)

    else:
        print(f"[08] アカウント設定読み込み成功: {args.account_id}")


if __name__ == "__main__":
    main()
