"""
05_video_assembler.py
FFmpeg を使って動画クリップ・音声・字幕を合成し最終動画を生成する。

出力:
  {run_dir}/output.mp4   # 完成動画 (1080p, H.264, AAC, SRT字幕焼き込み)
  {run_dir}/subtitles.srt
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.utils import load_settings, get_run_dir


def build_srt(timings: list[dict], output_path: Path):
    """timings.json から SRT 字幕ファイルを生成する"""
    lines = []
    for i, t in enumerate(timings):
        start = ms_to_srt_time(t["start_ms"])
        end = ms_to_srt_time(t["end_ms"])
        lines.append(f"{i+1}\n{start} --> {end}\n{t['text']}\n")
    output_path.write_text("\n".join(lines), encoding="utf-8")


def ms_to_srt_time(ms: int) -> str:
    total_sec = ms // 1000
    ms_part = ms % 1000
    h = total_sec // 3600
    m = (total_sec % 3600) // 60
    s = total_sec % 60
    return f"{h:02d}:{m:02d}:{s:02d},{ms_part:03d}"


def build_concat_list(clips: list[dict], narration_duration_ms: int,
                      timings: list[dict], run_dir: Path) -> Path:
    """
    ナレーション尺に合わせてクリップを並べた concat リストを作成する。
    各セクションの字幕タイミングに合わせてクリップを割り振る。
    """
    total_duration_sec = narration_duration_ms / 1000

    # セクションごとのクリップをマッピング
    section_clips: dict[str, list] = {}
    for clip in clips:
        sec = clip.get("section", "")
        section_clips.setdefault(sec, []).append(clip)

    # タイミングからセクション境界を計算
    section_order = []
    seen = set()
    for t in timings:
        sec = t.get("section", "")
        if sec and sec not in seen:
            section_order.append(sec)
            seen.add(sec)

    # セクションごとの継続時間を均等割り
    if section_order:
        sec_duration = total_duration_sec / len(section_order)
    else:
        sec_duration = total_duration_sec

    concat_path = run_dir / "concat.txt"
    clip_entries = []
    accumulated = 0.0

    for sec in section_order:
        available = section_clips.get(sec, []) or list(clips)
        # ラウンドロビンでクリップを選択
        idx = 0
        while accumulated < total_duration_sec and (accumulated < (section_order.index(sec) + 1) * sec_duration or sec == section_order[-1]):
            clip = available[idx % len(available)]
            clip_duration = clip["duration"]
            clip_entries.append(clip["local_path"])
            accumulated += clip_duration
            idx += 1
            if accumulated >= total_duration_sec:
                break

    with open(concat_path, "w") as f:
        for path in clip_entries:
            f.write(f"file '{path}'\n")

    return concat_path


def assemble_video(run_dir: Path, settings: dict) -> Path:
    narration_path = run_dir / "narration.mp3"
    clips_meta_path = run_dir / "clips.json"
    timings_path = run_dir / "timings.json"

    with open(clips_meta_path, encoding="utf-8") as f:
        clips = json.load(f)
    with open(timings_path, encoding="utf-8") as f:
        timings = json.load(f)

    # 字幕ファイル生成
    srt_path = run_dir / "subtitles.srt"
    build_srt(timings, srt_path)

    # ナレーション尺を取得
    narration_ms = timings[-1]["end_ms"] if timings else 300000

    # concat リスト生成
    concat_path = build_concat_list(clips, narration_ms, timings, run_dir)

    # フォントファイルのパス
    font_path = Path("assets/fonts/NotoSansCJK-Regular.ttc")
    if not font_path.exists():
        # CI環境では日本語フォントをシステムから探す
        font_path = Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc")

    sub_cfg = settings["subtitle"]
    video_cfg = settings["video"]

    # Step 1: クリップを連結してベース動画を生成
    base_video = run_dir / "base_video.mp4"
    concat_cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", str(concat_path),
        "-t", str(narration_ms / 1000),
        "-vf", f"scale={video_cfg['resolution'].replace('x', ':')}",
        "-r", str(video_cfg["fps"]),
        "-c:v", video_cfg["codec"],
        "-preset", video_cfg["preset"],
        "-crf", str(video_cfg["crf"]),
        "-an",  # 音声なし（後でミックス）
        str(base_video),
    ]
    print(f"[05] ベース動画生成中...")
    subprocess.run(concat_cmd, check=True, capture_output=True)

    # Step 2: 字幕焼き込み + 音声ミックス → 最終動画
    output_path = run_dir / "output.mp4"

    if font_path.exists():
        subtitle_filter = (
            f"subtitles={srt_path}:"
            f"fontsdir={font_path.parent}:"
            f"force_style='"
            f"Fontname={sub_cfg['font_name']},"
            f"FontSize={sub_cfg['font_size']},"
            f"PrimaryColour={sub_cfg['primary_color']},"
            f"OutlineColour={sub_cfg['outline_color']},"
            f"BorderStyle={sub_cfg['border_style']},"
            f"MarginV={sub_cfg['margin_v']}'"
        )
    else:
        # フォントなし（字幕なし）でフォールバック
        print("[05] 警告: 日本語フォントが見つかりません。字幕なしで続行します。")
        subtitle_filter = None

    vf_filter = subtitle_filter if subtitle_filter else "null"

    final_cmd = [
        "ffmpeg", "-y",
        "-i", str(base_video),
        "-i", str(narration_path),
        "-vf", vf_filter,
        "-c:v", video_cfg["codec"],
        "-preset", video_cfg["preset"],
        "-crf", str(video_cfg["crf"]),
        "-r", str(video_cfg["fps"]),
        "-c:a", video_cfg["audio_codec"],
        "-b:a", video_cfg["audio_bitrate"],
        "-shortest",
        str(output_path),
    ]
    print(f"[05] 字幕・音声ミックス中...")
    subprocess.run(final_cmd, check=True, capture_output=True)

    # ベース動画を削除
    base_video.unlink(missing_ok=True)

    size_mb = output_path.stat().st_size / 1024 / 1024
    print(f"[05] 動画合成完了: {output_path} ({size_mb:.1f} MB)")
    return output_path


def main():
    parser = argparse.ArgumentParser(description="動画・音声・字幕を合成する")
    parser.add_argument("--account-id", required=True)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()

    settings = load_settings()
    run_dir = get_run_dir(args.account_id, args.run_id, settings)
    assemble_video(run_dir, settings)


if __name__ == "__main__":
    main()
