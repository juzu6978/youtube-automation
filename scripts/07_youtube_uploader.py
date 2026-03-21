"""
07_youtube_uploader.py
YouTube Data API v3 で動画・サムネイルを投稿する。

必要な環境変数（GitHub Secrets から渡す）:
  YOUTUBE_REFRESH_TOKEN
  YOUTUBE_CLIENT_ID
  YOUTUBE_CLIENT_SECRET
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.utils import load_account_config, load_genre_config, load_settings, get_run_dir


def resolve_credentials(account_cfg: dict) -> dict:
    """account_cfg から環境変数経由でOAuth認証情報を解決する"""
    import os
    creds_cfg = account_cfg["credentials"]
    result = {}
    for key, secret_name in creds_cfg.items():
        value = os.environ.get(secret_name)
        if not value:
            raise EnvironmentError(f"必須シークレット '{secret_name}' が未設定です。")
        result[key.removesuffix("_secret")] = value
    return result


YOUTUBE_SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

SHORT_FORMATS = ("shorts", "tiktok")


def build_youtube_client(credentials: dict):
    creds = Credentials(
        token=None,
        refresh_token=credentials["refresh_token"],
        client_id=credentials["client_id"],
        client_secret=credentials["client_secret"],
        token_uri="https://oauth2.googleapis.com/token",
        scopes=YOUTUBE_SCOPES,
    )
    return build("youtube", "v3", credentials=creds)


def upload_video(youtube, video_path: Path, script: dict,
                 account_cfg: dict, genre_cfg: dict, fmt: str = "landscape",
                 dry_run: bool = False) -> str | None:
    content_cfg = account_cfg["content"]

    # Shorts の場合はタイトル末尾に #Shorts を付加し、説明文先頭にも追記
    title = script["title"]
    description = script["description"]
    tags = script.get("tags", []) + genre_cfg.get("tags", [])
    if fmt in SHORT_FORMATS:
        if not title.endswith("#Shorts"):
            title = title + " #Shorts"
        if not description.startswith("#Shorts"):
            description = "#Shorts\n\n" + description
        # YouTube Shorts 認識のためタグにも追加
        if "#Shorts" not in tags and "Shorts" not in tags:
            tags = tags + ["#Shorts", "Shorts"]

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags,
            "categoryId": str(content_cfg.get("category_id", genre_cfg.get("category_id", 22))),
            "defaultLanguage": content_cfg.get("default_language", "ja"),
        },
        "status": {
            "privacyStatus": "public",
            "selfDeclaredMadeForKids": content_cfg.get("made_for_kids", False),
        },
    }

    if dry_run:
        print(f"[07] DRY RUN: 投稿をスキップします [{fmt}]")
        print(f"[07]   タイトル: {body['snippet']['title']}")
        print(f"[07]   タグ: {body['snippet']['tags'][:5]}...")
        return "DRY_RUN_VIDEO_ID"

    print(f"[07] 動画アップロード開始: {video_path.name} ({video_path.stat().st_size / 1024 / 1024:.1f} MB)")

    media = MediaFileUpload(
        str(video_path),
        mimetype="video/mp4",
        resumable=True,
        chunksize=10 * 1024 * 1024,  # 10MB チャンク
    )

    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media,
    )

    response = None
    retry = 0
    while response is None:
        try:
            status, response = request.next_chunk()
            if status:
                pct = int(status.progress() * 100)
                print(f"[07] アップロード中... {pct}%")
        except Exception as e:
            retry += 1
            if retry > 3:
                raise
            print(f"[07] アップロードエラー (リトライ {retry}/3): {e}")
            time.sleep(5 * retry)

    video_id = response["id"]
    print(f"[07] 動画アップロード完了: https://youtu.be/{video_id}")
    return video_id


def upload_thumbnail(youtube, video_id: str, thumbnail_path: Path, dry_run: bool = False):
    if dry_run or video_id == "DRY_RUN_VIDEO_ID":
        print(f"[07] DRY RUN: サムネイルアップロードをスキップします")
        return

    from googleapiclient.errors import HttpError

    media = MediaFileUpload(str(thumbnail_path), mimetype="image/jpeg")

    # 429 レート制限は指数バックオフでリトライ（最大4回）
    wait_times = [30, 60, 120, 240]  # 秒
    for attempt, wait in enumerate(wait_times, 1):
        try:
            youtube.thumbnails().set(videoId=video_id, media_body=media).execute()
            print(f"[07] サムネイルアップロード完了")
            return
        except HttpError as e:
            if e.status_code == 429:
                if attempt <= len(wait_times) - 1:
                    print(f"[07] サムネイルレート制限 (429)。{wait}秒後にリトライ ({attempt}/{len(wait_times)})...")
                    time.sleep(wait)
                    # MediaFileUpload を再生成（ストリームをリセット）
                    media = MediaFileUpload(str(thumbnail_path), mimetype="image/jpeg")
                else:
                    print(f"[07] ⚠️  サムネイルアップロード失敗（レート制限）。動画は投稿済みです。")
                    print(f"[07]    video_id={video_id} に後でサムネイルを手動設定してください。")
                    return   # 例外を投げずに続行（動画投稿自体は成功）
            else:
                print(f"[07] ⚠️  サムネイルアップロードエラー (HTTP {e.status_code}): {e}")
                print(f"[07]    動画は投稿済みです。サムネイルのみ手動設定してください。")
                return   # 非429エラーも動画投稿を失敗扱いにしない
        except Exception as e:
            print(f"[07] ⚠️  サムネイルアップロード予期せぬエラー: {e}")
            print(f"[07]    動画は投稿済みです。サムネイルのみ手動設定してください。")
            return


def upload_pipeline(account_id: str, run_id: str, settings: dict,
                    fmt: str = "landscape", dry_run: bool = False):
    account_cfg = load_account_config(account_id)
    genre_cfg = load_genre_config(account_id)
    run_dir = get_run_dir(account_id, run_id, settings)

    script_path = run_dir / "script.json"
    video_path = run_dir / "output.mp4"
    thumbnail_path = run_dir / "thumbnail.jpg"

    with open(script_path, encoding="utf-8") as f:
        script = json.load(f)

    credentials = resolve_credentials(account_cfg)
    youtube = build_youtube_client(credentials)

    video_id = upload_video(youtube, video_path, script, account_cfg, genre_cfg,
                            fmt=fmt, dry_run=dry_run)

    if thumbnail_path.exists():
        upload_thumbnail(youtube, video_id, thumbnail_path, dry_run=dry_run)

    # 結果を保存
    result = {
        "video_id": video_id,
        "title": script["title"],
        "url": f"https://youtu.be/{video_id}",
        "account_id": account_id,
        "run_id": run_id,
        "format": fmt,
        "dry_run": dry_run,
    }
    result_path = run_dir / "upload_result.json"
    with open(result_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    return result


def main():
    parser = argparse.ArgumentParser(description="YouTube に動画を投稿する")
    parser.add_argument("--account-id", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--format", default="landscape",
                        help="フォーマット: landscape | shorts | tiktok")
    parser.add_argument("--dry-run", action="store_true", help="実際に投稿せずテストする")
    args = parser.parse_args()

    settings = load_settings()
    dry_run = args.dry_run or settings["pipeline"].get("dry_run", False)
    result = upload_pipeline(args.account_id, args.run_id, settings,
                             fmt=args.format, dry_run=dry_run)
    print(f"[07] 投稿完了: {result['url']}")


if __name__ == "__main__":
    main()
