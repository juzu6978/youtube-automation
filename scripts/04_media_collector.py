"""
04_media_collector.py
Pexels / Pixabay API から動画素材を検索・ダウンロードする。

出力: {run_dir}/clips/ に動画ファイル群
      {run_dir}/clips.json  # ダウンロードした動画のメタ情報リスト
"""

import argparse
import json
import os
import random
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.utils import load_genre_config, load_settings, get_run_dir


PEXELS_API_BASE = "https://api.pexels.com/videos"
PIXABAY_API_BASE = "https://pixabay.com/api/videos/"


def search_pexels(query: str, per_page: int = 5, min_width: int = 1920) -> list[dict]:
    api_key = os.environ.get("PEXELS_API_KEY", "")
    if not api_key:
        print(f"[04] PEXELS_API_KEY が未設定。Pexels検索をスキップします。")
        return []

    headers = {"Authorization": api_key}
    params = {
        "query": query,
        "per_page": per_page,
        "page": random.randint(1, 3),
        "orientation": "landscape",
        "locale": "ja-JP",
    }
    try:
        resp = requests.get(f"{PEXELS_API_BASE}/search", headers=headers, params=params, timeout=15)
        resp.raise_for_status()
        videos = resp.json().get("videos", [])
        results = []
        for v in videos:
            # 最高解像度のHDファイルを選択
            best_file = None
            for vf in v.get("video_files", []):
                if vf.get("width", 0) >= min_width and vf.get("quality") in ("hd", "uhd"):
                    if best_file is None or vf.get("width", 0) > best_file.get("width", 0):
                        best_file = vf
            if best_file:
                results.append({
                    "id": v["id"],
                    "url": best_file["link"],
                    "duration": v["duration"],
                    "width": best_file["width"],
                    "height": best_file["height"],
                    "source": "pexels",
                    "query": query,
                })
        return results
    except Exception as e:
        print(f"[04] Pexels検索エラー ({query}): {e}")
        return []


def search_pixabay(query: str, per_page: int = 5) -> list[dict]:
    api_key = os.environ.get("PIXABAY_API_KEY", "")
    if not api_key:
        return []

    params = {
        "key": api_key,
        "q": query,
        "video_type": "film",
        "per_page": per_page,
        "page": random.randint(1, 3),
        "min_width": 1280,
        "lang": "en",
    }
    try:
        resp = requests.get(PIXABAY_API_BASE, params=params, timeout=15)
        resp.raise_for_status()
        hits = resp.json().get("hits", [])
        results = []
        for h in hits:
            videos = h.get("videos", {})
            best = videos.get("large") or videos.get("medium") or videos.get("small")
            if best:
                results.append({
                    "id": h["id"],
                    "url": best["url"],
                    "duration": h["duration"],
                    "width": best.get("width", 1280),
                    "height": best.get("height", 720),
                    "source": "pixabay",
                    "query": query,
                })
        return results
    except Exception as e:
        print(f"[04] Pixabay検索エラー ({query}): {e}")
        return []


def download_video(url: str, output_path: Path, timeout: int = 60) -> bool:
    try:
        with requests.get(url, stream=True, timeout=timeout) as resp:
            resp.raise_for_status()
            with open(output_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=1024 * 1024):
                    f.write(chunk)
        return True
    except Exception as e:
        print(f"[04] ダウンロードエラー ({url[:60]}): {e}")
        if output_path.exists():
            output_path.unlink()
        return False


SHORT_FORMATS = ("shorts", "tiktok")


def collect_clips(concept: dict, settings: dict, run_dir: Path, fmt: str = "landscape") -> list[dict]:
    clips_dir = run_dir / "clips"
    clips_dir.mkdir(exist_ok=True)

    # shorts/tiktok 用設定（min_width=1080、短いクリップOK）
    if fmt in SHORT_FORMATS:
        pexels_cfg = settings["shorts"]["pexels"]
    else:
        pexels_cfg = settings["pexels"]

    per_section = pexels_cfg["per_section"]
    min_duration = pexels_cfg["min_duration_sec"]
    max_duration = pexels_cfg["max_duration_sec"]
    min_width = pexels_cfg["min_width"]

    downloaded_clips = []
    used_ids = set()

    for section in concept["outline"]:
        section_title = section["title"]
        keywords = section.get("keywords", [])

        for keyword in keywords:
            if len(downloaded_clips) >= (concept["outline"].index(section) + 1) * per_section:
                break

            # Pexels → Pixabay フォールバック
            candidates = search_pexels(keyword, per_page=10, min_width=min_width)
            if not candidates:
                candidates = search_pixabay(keyword, per_page=10)

            for candidate in candidates:
                vid_id = f"{candidate['source']}_{candidate['id']}"
                if vid_id in used_ids:
                    continue
                if not (min_duration <= candidate["duration"] <= max_duration):
                    continue

                file_ext = "mp4"
                filename = f"clip_{len(downloaded_clips):03d}_{vid_id}.{file_ext}"
                output_path = clips_dir / filename

                print(f"[04] ダウンロード: {keyword} → {filename}")
                if download_video(candidate["url"], output_path):
                    used_ids.add(vid_id)
                    downloaded_clips.append({
                        **candidate,
                        "section": section_title,
                        "filename": filename,
                        "local_path": str(output_path),
                    })
                    time.sleep(0.3)
                    break

    if not downloaded_clips:
        raise RuntimeError("[04] 動画クリップを1本もダウンロードできませんでした。")

    clips_meta_path = run_dir / "clips.json"
    with open(clips_meta_path, "w", encoding="utf-8") as f:
        json.dump(downloaded_clips, f, ensure_ascii=False, indent=2)

    print(f"[04] 動画素材収集完了: {len(downloaded_clips)}本")
    return downloaded_clips


def main():
    parser = argparse.ArgumentParser(description="Pexels/Pixabayから動画素材をダウンロード")
    parser.add_argument("--account-id", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--format", default="landscape",
                        help="フォーマット: landscape | shorts | tiktok")
    args = parser.parse_args()

    settings = load_settings()
    run_dir = get_run_dir(args.account_id, args.run_id, settings)

    concept_path = run_dir / "concept.json"
    with open(concept_path, encoding="utf-8") as f:
        concept = json.load(f)

    collect_clips(concept, settings, run_dir, fmt=args.format)


if __name__ == "__main__":
    main()
