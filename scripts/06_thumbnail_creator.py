"""
06_thumbnail_creator.py
FFmpeg でフレーム抽出 → ImageMagick でタイトル文字を合成してサムネイルを生成する。

出力: {run_dir}/thumbnail.jpg  (1280x720)
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.utils import load_settings, get_run_dir


def extract_frame(video_path: Path, output_path: Path, time_pct: float = 0.10):
    """動画の指定タイムコード（全体のtime_pct%地点）からフレームを抽出する"""
    # まず動画の長さを取得
    probe_cmd = [
        "ffprobe", "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        str(video_path),
    ]
    result = subprocess.run(probe_cmd, capture_output=True, text=True, check=True)
    info = json.loads(result.stdout)
    duration = float(info["format"]["duration"])

    seek_time = duration * time_pct

    extract_cmd = [
        "ffmpeg", "-y",
        "-ss", str(seek_time),
        "-i", str(video_path),
        "-vframes", "1",
        "-vf", "scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720",
        "-q:v", "2",
        str(output_path),
    ]
    subprocess.run(extract_cmd, check=True, capture_output=True)


def overlay_title(frame_path: Path, title: str, output_path: Path, settings: dict):
    """ImageMagick を使ってタイトルテキストをフレームにオーバーレイする"""
    thumb_cfg = settings["thumbnail"]
    font_size = thumb_cfg["font_size"]
    text_color = thumb_cfg["text_color"]
    shadow_color = thumb_cfg["shadow_color"]

    # タイトルを短縮（サムネイルは20文字程度が見やすい）
    display_title = title if len(title) <= 20 else title[:19] + "…"

    font_path = Path("assets/fonts/NotoSansCJK-Regular.ttc")
    if not font_path.exists():
        font_path = Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc")

    if not font_path.exists():
        # フォントなし: フレームをそのままサムネイルとして使用
        print("[06] 警告: フォントが見つかりません。テキストなしサムネイルを生成します。")
        import shutil
        shutil.copy(frame_path, output_path)
        return

    # 半透明オーバーレイ + テキスト
    convert_cmd = [
        "convert",
        str(frame_path),
        # 下部に暗いグラデーション
        "(",
        "-size", "1280x200",
        "gradient:rgba(0,0,0,0.8)-transparent",
        "-flip",
        ")",
        "-gravity", "South",
        "-composite",
        # タイトルテキスト（影付き）
        "-font", str(font_path),
        "-pointsize", str(font_size),
        "-fill", shadow_color,
        "-annotate", "+4+4",
        display_title,
        "-fill", text_color,
        "-annotate", "+0+0",
        display_title,
        "-gravity", "South",
        "-geometry", "+0+40",
        str(output_path),
    ]

    try:
        subprocess.run(convert_cmd, check=True, capture_output=True)
    except subprocess.CalledProcessError:
        # ImageMagick が利用できない場合はフレームをそのまま使用
        print("[06] 警告: ImageMagick エラー。テキストなしサムネイルを使用します。")
        import shutil
        shutil.copy(frame_path, output_path)


def create_thumbnail(run_dir: Path, settings: dict) -> Path:
    video_path = run_dir / "output.mp4"
    script_path = run_dir / "script.json"

    with open(script_path, encoding="utf-8") as f:
        script = json.load(f)

    title = script["title"]
    time_pct = settings["thumbnail"]["extract_time_pct"]

    frame_path = run_dir / "_frame_raw.jpg"
    thumbnail_path = run_dir / "thumbnail.jpg"

    print(f"[06] フレーム抽出中 ({time_pct*100:.0f}%地点)...")
    extract_frame(video_path, frame_path, time_pct)

    print(f"[06] タイトルオーバーレイ中: {title[:20]}...")
    overlay_title(frame_path, title, thumbnail_path, settings)

    frame_path.unlink(missing_ok=True)

    size_kb = thumbnail_path.stat().st_size / 1024
    print(f"[06] サムネイル生成完了: {thumbnail_path} ({size_kb:.0f} KB)")
    return thumbnail_path


def main():
    parser = argparse.ArgumentParser(description="サムネイルを生成する")
    parser.add_argument("--account-id", required=True)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()

    settings = load_settings()
    run_dir = get_run_dir(args.account_id, args.run_id, settings)
    create_thumbnail(run_dir, settings)


if __name__ == "__main__":
    main()
