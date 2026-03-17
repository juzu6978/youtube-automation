"""
07b_tiktok_uploader.py
TikTok Content Posting API v2 で動画を自動投稿する。

必要な環境変数（GitHub Secrets から渡す）:
  TIKTOK_ACCESS_TOKEN          # TikTok OAuth2 アクセストークン
  TIKTOK_CLIENT_KEY            # TikTok アプリの Client Key（任意: ログ出力用）
  TIKTOK_CLIENT_SECRET         # TikTok アプリの Client Secret（任意）

TikTok Content Posting API フロー:
  1. POST /v2/video/init/        → upload_url, publish_id を取得
  2. PUT  {upload_url}           → 動画ファイルをアップロード（チャンク転送）
  3. POST /v2/video/publish/     → 投稿確定（タイトル・プライバシー設定）

注意:
  - TikTok Developer Account が必要
  - video.publish スコープの承認が必要（申請〜承認に数日〜数週間かかる場合あり）
  - アクセストークンの有効期限は発行から24時間（リフレッシュが必要）
  - 動画は 9:16 縦型 (1080x1920) のみ対応
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.utils import load_settings, get_run_dir


TIKTOK_API_BASE = "https://open.tiktokapis.com/v2"
CHUNK_SIZE = 10 * 1024 * 1024  # 10MB チャンク


def get_access_token() -> str:
    """環境変数から TikTok アクセストークンを取得する"""
    token = os.environ.get("TIKTOK_ACCESS_TOKEN", "")
    if not token:
        raise EnvironmentError(
            "TIKTOK_ACCESS_TOKEN が未設定です。\n"
            "TikTok Developer Portal で OAuth2 フローを実行し、"
            "GitHub Secrets に登録してください。"
        )
    return token


def init_video_upload(access_token: str, video_size: int, title: str) -> dict:
    """
    動画アップロードを初期化し、upload_url と publish_id を取得する。

    Returns:
        {"upload_url": str, "publish_id": str}
    """
    url = f"{TIKTOK_API_BASE}/video/init/"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json; charset=UTF-8",
    }
    body = {
        "post_info": {
            "title": title[:2200],  # TikTok タイトルは最大2200文字
            "privacy_level": "PUBLIC_TO_EVERYONE",
            "disable_duet": False,
            "disable_comment": False,
            "disable_stitch": False,
        },
        "source_info": {
            "source": "FILE_UPLOAD",
            "video_size": video_size,
            "chunk_size": CHUNK_SIZE,
            "total_chunk_count": max(1, (video_size + CHUNK_SIZE - 1) // CHUNK_SIZE),
        },
    }

    resp = requests.post(url, headers=headers, json=body, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    if data.get("error", {}).get("code", "ok") != "ok":
        raise RuntimeError(f"TikTok init エラー: {data['error']}")

    upload_info = data["data"]
    return {
        "upload_url": upload_info["upload_url"],
        "publish_id": upload_info["publish_id"],
    }


def upload_video_chunks(upload_url: str, video_path: Path) -> None:
    """
    動画ファイルをチャンクに分割してアップロードする（PUT リクエスト）。
    TikTok の Content-Range ヘッダー仕様に準拠。
    """
    video_size = video_path.stat().st_size
    total_chunks = max(1, (video_size + CHUNK_SIZE - 1) // CHUNK_SIZE)

    print(f"[07b] 動画アップロード開始: {video_path.name} ({video_size / 1024 / 1024:.1f} MB, "
          f"{total_chunks}チャンク)")

    with open(video_path, "rb") as f:
        for chunk_idx in range(total_chunks):
            start = chunk_idx * CHUNK_SIZE
            end = min(start + CHUNK_SIZE, video_size) - 1
            chunk_data = f.read(CHUNK_SIZE)

            headers = {
                "Content-Type": "video/mp4",
                "Content-Range": f"bytes {start}-{end}/{video_size}",
                "Content-Length": str(len(chunk_data)),
            }

            retry = 0
            while True:
                try:
                    resp = requests.put(
                        upload_url,
                        headers=headers,
                        data=chunk_data,
                        timeout=120,
                    )
                    resp.raise_for_status()
                    pct = int((chunk_idx + 1) / total_chunks * 100)
                    print(f"[07b] アップロード中... {pct}% (chunk {chunk_idx + 1}/{total_chunks})")
                    break
                except Exception as e:
                    retry += 1
                    if retry > 3:
                        raise RuntimeError(f"チャンクアップロード失敗 (chunk {chunk_idx}): {e}")
                    print(f"[07b] リトライ {retry}/3: {e}")
                    time.sleep(5 * retry)


def publish_video(access_token: str, publish_id: str) -> str:
    """
    アップロード完了後、動画を公開する。

    Returns:
        TikTok 動画 ID
    """
    url = f"{TIKTOK_API_BASE}/video/publish/"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json; charset=UTF-8",
    }
    body = {"publish_id": publish_id}

    resp = requests.post(url, headers=headers, json=body, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    if data.get("error", {}).get("code", "ok") != "ok":
        raise RuntimeError(f"TikTok publish エラー: {data['error']}")

    video_id = data["data"]["video_id"]
    return str(video_id)


def upload_tiktok(account_id: str, run_id: str, settings: dict,
                  dry_run: bool = False) -> dict:
    """TikTok への動画投稿パイプライン"""
    run_dir = get_run_dir(account_id, run_id, settings)

    script_path = run_dir / "script.json"
    video_path = run_dir / "output.mp4"

    with open(script_path, encoding="utf-8") as f:
        script = json.load(f)

    # タイトル（TikTok 用: ハッシュタグ付き）
    title = script["title"]
    tags_str = " ".join(f"#{t}" for t in script.get("tags", [])[:5])
    if tags_str:
        title = f"{title} {tags_str}"

    if dry_run:
        print(f"[07b] DRY RUN: TikTok 投稿をスキップします")
        print(f"[07b]   タイトル: {title}")
        result = {
            "video_id": "DRY_RUN_TIKTOK_ID",
            "title": title,
            "url": "https://www.tiktok.com/@user/video/DRY_RUN_TIKTOK_ID",
            "account_id": account_id,
            "run_id": run_id,
            "format": "tiktok",
            "dry_run": True,
        }
        result_path = run_dir / "tiktok_result.json"
        with open(result_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        return result

    access_token = get_access_token()
    video_size = video_path.stat().st_size

    # Step 1: アップロード初期化
    print(f"[07b] TikTok アップロード初期化中...")
    upload_info = init_video_upload(access_token, video_size, title)
    upload_url = upload_info["upload_url"]
    publish_id = upload_info["publish_id"]
    print(f"[07b] publish_id: {publish_id}")

    # Step 2: 動画チャンクアップロード
    upload_video_chunks(upload_url, video_path)

    # Step 3: 公開確定
    print(f"[07b] 動画を公開中...")
    video_id = publish_video(access_token, publish_id)
    video_url = f"https://www.tiktok.com/@user/video/{video_id}"
    print(f"[07b] TikTok 投稿完了: {video_url}")

    result = {
        "video_id": video_id,
        "title": title,
        "url": video_url,
        "account_id": account_id,
        "run_id": run_id,
        "format": "tiktok",
        "dry_run": False,
    }
    result_path = run_dir / "tiktok_result.json"
    with open(result_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    return result


def main():
    parser = argparse.ArgumentParser(description="TikTok に動画を投稿する")
    parser.add_argument("--account-id", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--dry-run", action="store_true", help="実際に投稿せずテストする")
    args = parser.parse_args()

    settings = load_settings()
    dry_run = args.dry_run or settings["pipeline"].get("dry_run", False)
    result = upload_tiktok(args.account_id, args.run_id, settings, dry_run=dry_run)
    print(f"[07b] 完了: {result['url']}")


if __name__ == "__main__":
    main()
