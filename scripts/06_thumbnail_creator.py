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


def split_title_lines(text: str) -> list:
    """タイトルを最大16文字×2行に分割する"""
    if len(text) <= 16:
        return [text]
    # 自然な区切り点（句読点・記号）を探す
    split_pos = 16
    for i in range(15, max(8, 15 - 5), -1):
        if i < len(text) and text[i] in "、。！？！？・ ":
            split_pos = i + 1
            break
    line1 = text[:split_pos]
    remaining = text[split_pos:]
    line2 = remaining[:16] + ("…" if len(remaining) > 16 else "")
    return [line1, line2] if line2 else [line1]


def overlay_title(frame_path: Path, title: str, output_path: Path, settings: dict):
    """YouTube向け 2行タイトル＋カラーバナー サムネイルを生成する"""
    thumb_cfg = settings["thumbnail"]
    font_size = thumb_cfg.get("font_size", 56)

    font_path = Path("assets/fonts/NotoSansCJK-Regular.ttc")
    if not font_path.exists():
        font_path = Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc")

    if not font_path.exists():
        print("[06] 警告: フォントが見つかりません。テキストなしサムネイルを生成します。")
        import shutil
        shutil.copy(frame_path, output_path)
        return

    lines = split_title_lines(title)
    has_two_lines = len(lines) == 2

    # gravity=South からの縦オフセット（px）
    if has_two_lines:
        offset1 = "+0+105"   # 1行目（大・上）
        offset2 = "+0+38"    # 2行目（小・下）
    else:
        offset1 = "+0+60"    # 1行のみ（中央下部）

    convert_cmd = [
        "convert",
        str(frame_path),
        # 全体を少し暗くして視認性を上げる
        "-brightness-contrast", "-12x0",
        # 下部グラデーション（暗め・幅広）
        "(",
        "-size", "1280x340",
        "gradient:rgba(0,0,0,0.0)-rgba(0,0,0,0.92)",
        ")",
        "-gravity", "South",
        "-composite",
        # テキスト背景の矩形（深い紺色・半透明）
        "-fill", "rgba(8,18,75,0.82)",
        "-draw", "roundrectangle 22,545 1258,710 16,16",
        # ゴールドのアクセントライン（矩形上端）
        "-fill", "rgba(255,185,0,1.0)",
        "-draw", "rectangle 22,545 1258,556",
        # 1行目テキスト（ゴールド・大）
        "-font", str(font_path),
        "-pointsize", str(font_size),
        "-fill", "#FFD700",
        "-stroke", "#000000",
        "-strokewidth", "3",
        "-gravity", "South",
        "-annotate", offset1,
        lines[0],
    ]

    # 2行目テキスト（白・小）
    if has_two_lines:
        second_size = int(font_size * 0.74)
        convert_cmd += [
            "-pointsize", str(second_size),
            "-fill", "#FFFFFF",
            "-stroke", "#000000",
            "-strokewidth", "2",
            "-gravity", "South",
            "-annotate", offset2,
            lines[1],
        ]

    convert_cmd.append(str(output_path))

    try:
        subprocess.run(convert_cmd, check=True, capture_output=True)
        label = lines[0] + (" / " + lines[1] if has_two_lines else "")
        print(f"[06] サムネイル生成: {label}")
    except subprocess.CalledProcessError as e:
        print("[06] 警告: ImageMagick エラー。シンプルサムネイルを使用します。")
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
