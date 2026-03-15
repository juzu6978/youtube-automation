"""
utils.py
パイプライン全体で共通して使うユーティリティ関数群。
"""

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
