"""
05_video_assembler.py
FFmpeg を使って動画クリップ・音声・字幕を合成し最終動画を生成する。

出力:
  {run_dir}/output.mp4      # 完成動画 (1080p, H.264, AAC, ASS字幕焼き込み)
  {run_dir}/subtitles.ass   # ASS字幕（左→右ワイプアニメーション付き）
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.utils import load_settings, get_run_dir


def ms_to_ass_time(ms: int) -> str:
    """ミリ秒 → ASS タイムコード (H:MM:SS.cc) に変換する"""
    total_cs = ms // 10          # センチ秒
    cs = total_cs % 100
    total_sec = total_cs // 100
    h = total_sec // 3600
    m = (total_sec % 3600) // 60
    s = total_sec % 60
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def build_ass(timings: list[dict], output_path: Path,
              sub_cfg: dict, global_sub: dict,
              reveal_ms: int, width: int, height: int):
    """
    timings.json から ASS 字幕ファイルを生成する。
    各行に左→右ワイプアニメーション（\\clip + \\t）を付与する。
    """
    font_name = global_sub.get("font_name", "Noto Sans CJK JP")
    font_size = sub_cfg.get("font_size", 13)
    # ASS カラー形式: &HAABBGGRR
    primary = global_sub.get("primary_color", "&H00FFFFFF")
    outline = global_sub.get("outline_color", "&H00000000")
    border_style = global_sub.get("border_style", 1)
    margin_v = sub_cfg.get("margin_v", 30)

    header = (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        f"PlayResX: {width}\n"
        f"PlayResY: {height}\n"
        "ScaledBorderAndShadow: yes\n"
        "\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
        "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Default,{font_name},{font_size},{primary},&H000000FF,"
        f"{outline},&H00000000,0,0,0,0,100,100,0,0,"
        f"{border_style},2,0,2,10,10,{margin_v},1\n"
        "\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )

    dialogue_lines = []
    for t in timings:
        start = ms_to_ass_time(t["start_ms"])
        end = ms_to_ass_time(t["end_ms"])
        text = t["text"].replace("\n", "\\N")
        # 左→右ワイプ: 0幅クリップ → 全幅クリップに reveal_ms かけてアニメーション
        anim = (
            f"{{\\clip(0,0,0,{height})"
            f"\\t({reveal_ms},\\clip(0,0,{width},{height}))}}"
        )
        dialogue_lines.append(
            f"Dialogue: 0,{start},{end},Default,,0,0,0,,{anim}{text}"
        )

    output_path.write_text(header + "\n".join(dialogue_lines) + "\n",
                           encoding="utf-8")


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


SHORT_FORMATS = ("shorts", "tiktok")


def assemble_video(run_dir: Path, settings: dict, fmt: str = "landscape") -> Path:
    narration_path = run_dir / "narration.mp3"
    clips_meta_path = run_dir / "clips.json"
    timings_path = run_dir / "timings.json"

    with open(clips_meta_path, encoding="utf-8") as f:
        clips = json.load(f)
    with open(timings_path, encoding="utf-8") as f:
        timings = json.load(f)

    # ナレーション尺を取得
    narration_ms = timings[-1]["end_ms"] if timings else 300000

    # フォーマットごとの動画サイズ
    if fmt in SHORT_FORMATS:
        vid_width, vid_height = 1080, 1920
    else:
        vid_width, vid_height = 1920, 1080

    # Shorts/TikTok: target_duration_sec を超えないようにキャップ
    # YouTube Shorts は60秒以下が必須条件
    if fmt in SHORT_FORMATS:
        max_sec = settings["shorts"].get("target_duration_sec", 55)
        max_ms = max_sec * 1000
        if narration_ms > max_ms:
            print(f"[05] ⚠️ ナレーション尺 {narration_ms/1000:.1f}s が Shorts 上限 {max_sec}s を超えています。{max_sec}s にカットします。")
            narration_ms = max_ms

    # 字幕ファイル生成（ASS形式・左→右ワイプアニメーション付き）
    ass_path = run_dir / "subtitles.ass"
    reveal_ms = settings.get("subtitle", {}).get("reveal_ms", 600)
    build_ass(timings, ass_path,
              sub_cfg=settings["shorts"]["subtitle"] if fmt in SHORT_FORMATS else settings["subtitle"],
              global_sub=settings["subtitle"],
              reveal_ms=reveal_ms,
              width=vid_width, height=vid_height)

    # concat リスト生成
    concat_path = build_concat_list(clips, narration_ms, timings, run_dir)

    # フォントファイルのパス
    font_path = Path("assets/fonts/NotoSansCJK-Regular.ttc")
    if not font_path.exists():
        # CI環境では日本語フォントをシステムから探す
        font_path = Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc")

    # フォーマットに応じた設定を選択
    if fmt in SHORT_FORMATS:
        video_cfg = settings["shorts"]
        sub_cfg = settings["shorts"]["subtitle"]
        # 縦型(9:16): 横動画を中央クロップして縦にする
        scale_filter = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920"
        resolution_label = "1080x1920 (縦型)"
    else:
        video_cfg = settings["video"]
        sub_cfg = settings["subtitle"]
        scale_filter = f"scale={video_cfg['resolution'].replace('x', ':')}"
        resolution_label = video_cfg["resolution"]

    print(f"[05] 解像度: {resolution_label}")

    # Step 1: クリップを連結してベース動画を生成
    base_video = run_dir / "base_video.mp4"
    concat_cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", str(concat_path),
        "-t", str(narration_ms / 1000),
        "-vf", scale_filter,
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
        # ASS ファイルにスタイルが埋め込まれているので force_style 不要
        subtitle_filter = (
            f"subtitles={ass_path}:"
            f"fontsdir={font_path.parent}"
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
    parser.add_argument("--format", default="landscape",
                        help="フォーマット: landscape | shorts | tiktok")
    args = parser.parse_args()

    settings = load_settings()
    run_dir = get_run_dir(args.account_id, args.run_id, settings)
    assemble_video(run_dir, settings, fmt=args.format)


if __name__ == "__main__":
    main()
