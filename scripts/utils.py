"""
utils.py
パイプライン全体で共通して使うユーティリティ関数群。
"""

import os

import yaml
from pathlib import Path


def load_settings() -> dict:
    """config/settings.yaml を読み込む"""
    with open("config/settings.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_account_config(account_id: str) -> dict:
    """config/accounts/{account_id}.yaml を読み込む"""
    path = Path(f"config/accounts/{account_id}.yaml")
    if not path.exists():
        raise FileNotFoundError(f"アカウント設定が見つかりません: {path}")
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_genre_config(account_id: str) -> dict:
    """アカウント設定からジャンルを解決し、genres.yaml の該当エントリを返す"""
    account_cfg = load_account_config(account_id)
    genre_id = account_cfg["content"]["genre"]

    with open("config/genres.yaml", encoding="utf-8") as f:
        genres_data = yaml.safe_load(f)

    for genre in genres_data["genres"]:
        if genre["id"] == genre_id:
            return genre

    raise ValueError(f"ジャンルが見つかりません: {genre_id}")


def get_run_dir(account_id: str, run_id: str, settings: dict) -> Path:
    """一時作業ディレクトリのパスを返す"""
    base = Path(settings["pipeline"]["temp_dir"])
    return base / account_id / run_id


def load_accounts_registry() -> list[dict]:
    """有効なアカウント一覧を返す"""
    with open("config/accounts/accounts_registry.yaml", encoding="utf-8") as f:
        reg = yaml.safe_load(f)
    return [a for a in reg["accounts"] if a.get("enabled", False)]


def resolve_credentials(account_cfg: dict) -> dict:
    """
    account.yaml の credentials ブロックに記載されたシークレット名を
    実際の環境変数値に解決して返す。

    例: refresh_token_secret → YOUTUBE_REFRESH_TOKEN → 実際のトークン値
    キー名のサフィックス "_secret" を除去してシンプルなキーにマッピングする。
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
        # "_secret" サフィックスを除去（removesuffix で末尾のみ除去）
        # 例: "client_secret_secret" → "client_secret"（replaceだと誤動作する）
        simple_key = key.removesuffix("_secret")
        result[simple_key] = value
    return result
