"""
05_video_assembler.py
FFmpeg を使って動画クリップ・音声・字幕を合成し最終動画を生成する。

出力:
  {run_dir}/output.mp4      # 完成動画 (H.264 CRF18, AAC, ASS字幕焼き込み)
  {run_dir}/subtitles.ass   # ASS字幕（フェードインアニメーション付き）
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.utils import load_settings, get_run_dir


# ─────────────────────────────────────────────
# FFmpeg / ffprobe ユーティリティ
# ─────────────────────────────────────────────

def run_ffmpeg(cmd: list, label: str) -> subprocess.CompletedProcess:
    """
    FFmpegを実行し、エラー時はstderrを表示して例外を投げる。
    capture_output=True を避け、エラーの内容を確実に記録する。
    """
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"[05] ❌ FFmpegエラー ({label}):")
        # 最後の50行だけ表示（ログが長い場合）
        lines = result.stderr.strip().splitlines()
        for line in lines[-50:]:
            print(f"       {line}")
        raise subprocess.CalledProcessError(result.returncode, cmd)
    return result


def get_video_duration(path: Path) -> float:
    """ffprobe で動画ファイルの実際の尺（秒）を取得する"""
    cmd = [
        "ffprobe", "-v", "quiet",
        "-show_entries", "format=duration",
        "-of", "csv=p=0",
        str(path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    try:
        return float(result.stdout.strip())
    except (ValueError, AttributeError):
        return 0.0


# ─────────────────────────────────────────────
# 字幕
# ─────────────────────────────────────────────

def ms_to_ass_time(ms: int) -> str:
    """ミリ秒 → ASS タイムコード (H:MM:SS.cc) に変換する"""
    total_cs = ms // 10
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
    \fad() でフェードインアニメーションを付与する。
    """
    font_name    = global_sub.get("font_name", "Noto Sans CJK JP")
    font_size    = sub_cfg.get("font_size", 65)
    primary      = global_sub.get("primary_color", "&H000066FF")
    outline      = global_sub.get("outline_color", "&H00000000")
    border_style = global_sub.get("border_style", 1)
    bold         = -1 if global_sub.get("bold", True) else 0
    outline_size = global_sub.get("outline_size", 3)
    shadow_size  = global_sub.get("shadow_size", 1)
    margin_v     = sub_cfg.get("margin_v", 400)

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
        f"{outline},&H00000000,{bold},0,0,0,100,100,0,0,"
        f"{border_style},{outline_size},{shadow_size},2,10,10,{margin_v},1\n"
        "\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )

    dialogue_lines = []
    for t in timings:
        start = ms_to_ass_time(t["start_ms"])
        end   = ms_to_ass_time(t["end_ms"])
        text  = t["text"].replace("\n", "\\N")
        anim  = f"{{\\fad({reveal_ms},0)}}"
        dialogue_lines.append(
            f"Dialogue: 0,{start},{end},Default,,0,0,0,,{anim}{text}"
        )

    output_path.write_text(header + "\n".join(dialogue_lines) + "\n",
                           encoding="utf-8")


# ─────────────────────────────────────────────
# クリップ選択
# ─────────────────────────────────────────────

def select_clips(clips: list[dict], narration_duration_ms: int,
                 timings: list[dict],
                 transition_buffer_sec: float = 0.0) -> list[dict]:
    """
    ナレーション尺を埋めるクリップリストを返す。
    各要素は {"path": str, "duration": float} の dict。
    transition_buffer_sec: xfadeで失われる尺の補正値（余裕を持って渡す）
    """
    total_sec = narration_duration_ms / 1000 + transition_buffer_sec

    section_clips: dict[str, list] = {}
    for clip in clips:
        sec = clip.get("section", "")
        section_clips.setdefault(sec, []).append(clip)

    section_order: list[str] = []
    seen: set[str] = set()
    for t in timings:
        sec = t.get("section", "")
        if sec and sec not in seen:
            section_order.append(sec)
            seen.add(sec)

    sec_duration = total_sec / len(section_order) if section_order else total_sec

    ordered: list[dict] = []
    accumulated = 0.0

    for sec in section_order:
        available = section_clips.get(sec, []) or list(clips)
        idx = 0
        sec_end = (section_order.index(sec) + 1) * sec_duration
        while accumulated < total_sec and (accumulated < sec_end or sec == section_order[-1]):
            clip = available[idx % len(available)]
            ordered.append({"path": clip["local_path"],
                            "duration": float(clip["duration"])})
            accumulated += clip["duration"]
            idx += 1
            if accumulated >= total_sec:
                break

    return ordered


# ─────────────────────────────────────────────
# ベース動画生成（トランジション対応）
# ─────────────────────────────────────────────

# xfade に渡す最大入力クリップ数（これを超えると concat にフォールバック）
XFADE_MAX_INPUTS = 8


def build_base_video(ordered_clips: list[dict], narration_sec: float,
                     scale_filter: str, video_cfg: dict,
                     run_dir: Path) -> Path:
    """
    クリップリストからベース動画を生成する。
    クリップ数が XFADE_MAX_INPUTS 以下かつ transition 設定がある場合のみ xfade を使用。
    それ以外は concat にフォールバック（安定性優先）。
    """
    output = run_dir / "base_video.mp4"
    transition     = video_cfg.get("transition", "none")
    transition_sec = float(video_cfg.get("transition_sec", 0.5))

    quality_flags = [
        "-c:v", video_cfg["codec"],
        "-profile:v", video_cfg.get("profile", "high"),
        "-preset", video_cfg["preset"],
        "-crf", str(video_cfg["crf"]),
        "-pix_fmt", video_cfg.get("pix_fmt", "yuv420p"),
    ]

    use_xfade = (
        transition and transition != "none"
        and len(ordered_clips) >= 2
        and len(ordered_clips) <= XFADE_MAX_INPUTS   # ← 多すぎると不安定なので制限
        and all(c["duration"] > transition_sec for c in ordered_clips)
    )

    if not use_xfade:
        # ─ シンプル concat ─
        if transition and transition != "none" and len(ordered_clips) > XFADE_MAX_INPUTS:
            print(f"[05] クリップ数 {len(ordered_clips)} > {XFADE_MAX_INPUTS} のため concat を使用")
        concat_path = run_dir / "concat.txt"
        with open(concat_path, "w") as f:
            for c in ordered_clips:
                f.write(f"file '{c['path']}'\n")
        cmd = (
            ["ffmpeg", "-y",
             "-f", "concat", "-safe", "0",
             "-i", str(concat_path),
             "-t", str(narration_sec),
             "-vf", scale_filter,
             "-r", str(video_cfg["fps"])]
            + quality_flags
            + ["-an", str(output)]
        )
        run_ffmpeg(cmd, "concat ベース動画生成")

    else:
        # ─ xfade トランジション ─
        input_args: list[str] = []
        for c in ordered_clips:
            input_args += ["-i", c["path"]]

        n = len(ordered_clips)
        filter_parts: list[str] = []

        for i in range(n):
            filter_parts.append(
                f"[{i}:v]{scale_filter},fps={video_cfg['fps']},format=yuv420p[sv{i}]"
            )

        offset = max(0.0, ordered_clips[0]["duration"] - transition_sec)
        if n == 2:
            filter_parts.append(
                f"[sv0][sv1]xfade=transition={transition}"
                f":duration={transition_sec}:offset={offset:.3f}[vout]"
            )
        else:
            filter_parts.append(
                f"[sv0][sv1]xfade=transition={transition}"
                f":duration={transition_sec}:offset={offset:.3f}[vx1]"
            )
            for i in range(2, n):
                offset += max(0.0, ordered_clips[i - 1]["duration"] - transition_sec)
                prev = f"vx{i - 1}"
                out  = "vout" if i == n - 1 else f"vx{i}"
                filter_parts.append(
                    f"[{prev}][sv{i}]xfade=transition={transition}"
                    f":duration={transition_sec}:offset={offset:.3f}[{out}]"
                )

        filter_complex = ";".join(filter_parts)
        cmd = (
            ["ffmpeg", "-y"]
            + input_args
            + ["-filter_complex", filter_complex,
               "-map", "[vout]",
               "-t", str(narration_sec)]
            + quality_flags
            + ["-an", str(output)]
        )
        run_ffmpeg(cmd, f"xfade ベース動画生成 ({n}クリップ)")
        print(f"[05] xfade 適用: {transition} {transition_sec}s × {n - 1}箇所")

    # ── 生成後の尺を検証 ──
    actual_sec = get_video_duration(output)
    print(f"[05] ベース動画尺: {actual_sec:.2f}s（目標: {narration_sec:.2f}s）")
    if actual_sec < narration_sec - 1.0:
        print(f"[05] ⚠️  ベース動画がナレーションより {narration_sec - actual_sec:.1f}s 短い → tpad で補完")

    return output


# ─────────────────────────────────────────────
# BGM ダッキング
# ─────────────────────────────────────────────

def build_audio_mix(narration_path: Path, bgm_path: Path | None,
                    total_sec: float, audio_cfg: dict,
                    run_dir: Path) -> Path:
    """ナレーション + BGM をミックスする（ダッキング対応）"""
    output = run_dir / "mixed_audio.aac"

    if bgm_path is None or not bgm_path.exists():
        return narration_path

    bgm_vol   = audio_cfg.get("bgm_volume_db", -18.0)
    duck_db   = audio_cfg.get("ducking_db", -10.0)
    attack_ms = audio_cfg.get("ducking_attack_ms", 200)
    release_ms= audio_cfg.get("ducking_release_ms", 500)
    fade_out  = audio_cfg.get("fade_out_sec", 2.0)

    filter_complex = (
        f"[1:a]aloop=loop=-1:size=2e+09,volume={bgm_vol}dB,"
        f"afade=t=out:st={max(0, total_sec - fade_out):.2f}:d={fade_out}[bgm_base];"
        f"[0:a][bgm_base]sidechaincompress="
        f"threshold=0.01:ratio=4:attack={attack_ms}:release={release_ms}:"
        f"makeup={abs(duck_db) * 0.3:.1f}[bgm_duck];"
        f"[0:a][bgm_duck]amix=inputs=2:duration=first[aout]"
    )

    cmd = [
        "ffmpeg", "-y",
        "-i", str(narration_path),
        "-i", str(bgm_path),
        "-filter_complex", filter_complex,
        "-map", "[aout]",
        "-c:a", "aac", "-b:a", "192k",
        "-t", str(total_sec),
        str(output),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print("[05] 警告: BGMダッキングに失敗。ナレーションのみで続行します。")
        print(result.stderr[-300:])
        return narration_path

    print(f"[05] BGMダッキング適用: {bgm_path.name}")
    return output


# ─────────────────────────────────────────────
# メイン合成
# ─────────────────────────────────────────────

SHORT_FORMATS = ("shorts", "tiktok")


def assemble_video(run_dir: Path, settings: dict, fmt: str = "landscape") -> Path:
    narration_path  = run_dir / "narration.mp3"
    clips_meta_path = run_dir / "clips.json"
    timings_path    = run_dir / "timings.json"

    with open(clips_meta_path, encoding="utf-8") as f:
        clips = json.load(f)
    with open(timings_path, encoding="utf-8") as f:
        timings = json.load(f)

    narration_ms = timings[-1]["end_ms"] if timings else 300000

    if fmt in SHORT_FORMATS:
        vid_width, vid_height = 1080, 1920
        video_cfg = settings["shorts"]
    else:
        vid_width, vid_height = 1920, 1080
        video_cfg = settings["video"]

    # Shorts: 上限キャップ
    if fmt in SHORT_FORMATS:
        max_ms = settings["shorts"].get("target_duration_sec", 55) * 1000
        if narration_ms > max_ms:
            print(f"[05] ⚠️ ナレーション {narration_ms/1000:.1f}s → Shorts上限 {max_ms/1000:.0f}s にカット")
            narration_ms = max_ms

    narration_sec = narration_ms / 1000

    # ── 字幕（ASS）生成 ──
    ass_path  = run_dir / "subtitles.ass"
    reveal_ms = settings.get("subtitle", {}).get("reveal_ms", 600)
    sub_cfg   = settings["shorts"]["subtitle"] if fmt in SHORT_FORMATS else settings["subtitle"]
    build_ass(timings, ass_path,
              sub_cfg=sub_cfg,
              global_sub=settings["subtitle"],
              reveal_ms=reveal_ms,
              width=vid_width, height=vid_height)

    # ── クリップ選択（xfade尺ロス分のバッファを確保）──
    transition_sec    = float(video_cfg.get("transition_sec", 0.5))
    transition_buffer = transition_sec * XFADE_MAX_INPUTS
    ordered_clips = select_clips(clips, narration_ms, timings,
                                 transition_buffer_sec=transition_buffer)
    print(f"[05] クリップ選択: {len(ordered_clips)}本 / 合計尺 {sum(c['duration'] for c in ordered_clips):.1f}s")

    # ── スケールフィルタ ──
    if fmt in SHORT_FORMATS:
        scale_filter    = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920"
        resolution_label = "1080x1920 (縦型)"
    else:
        scale_filter    = f"scale={video_cfg['resolution'].replace('x', ':')}"
        resolution_label = video_cfg["resolution"]

    print(f"[05] 解像度: {resolution_label} / ナレーション尺: {narration_sec:.1f}s")

    # ── ベース動画生成 ──
    base_video = build_base_video(
        ordered_clips, narration_sec, scale_filter, video_cfg, run_dir
    )

    # ── 実際のベース動画尺を確認 → 不足分を tpad で補完 ──
    actual_base_sec = get_video_duration(base_video)
    pad_sec = max(0.0, narration_sec - actual_base_sec + 0.5)  # 0.5s の余裕

    # ── BGM ミックス ──
    bgm_dir   = Path("assets/bgm")
    bgm_path  = next(bgm_dir.glob("*.mp3"), None) if bgm_dir.exists() else None
    audio_input = build_audio_mix(
        narration_path, bgm_path, narration_sec,
        settings.get("audio", {}), run_dir
    )

    # ── フォント ──
    font_path = Path("assets/fonts/NotoSansCJK-Regular.ttc")
    if not font_path.exists():
        font_path = Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc")

    # ── vf フィルタ構築 ──
    # tpad: ベース動画が短い場合に最終フレームを静止して尺を延ばす（フリーズ防止）
    tpad = f"tpad=stop_mode=clone:stop_duration={pad_sec:.2f}"

    if font_path.exists():
        subtitle_filter = f"subtitles={ass_path}:fontsdir={font_path.parent}"
        vf_filter = f"{tpad},{subtitle_filter}"
    else:
        print("[05] 警告: 日本語フォントが見つかりません。字幕なしで続行します。")
        vf_filter = tpad

    # ── 最終合成 ──
    output_path = run_dir / "output.mp4"
    quality_flags = [
        "-c:v", video_cfg["codec"],
        "-profile:v", video_cfg.get("profile", "high"),
        "-preset", video_cfg["preset"],
        "-crf", str(video_cfg["crf"]),
        "-pix_fmt", video_cfg.get("pix_fmt", "yuv420p"),
        "-movflags", f"+{video_cfg.get('movflags', 'faststart')}",
        "-r", str(video_cfg["fps"]),
        "-c:a", video_cfg["audio_codec"],
        "-b:a", video_cfg["audio_bitrate"],
    ]

    final_cmd = (
        ["ffmpeg", "-y",
         "-i", str(base_video),
         "-i", str(audio_input),
         "-vf", vf_filter]
        + quality_flags
        + ["-t", str(narration_sec), str(output_path)]
    )

    print("[05] 最終合成中（字幕・音声ミックス）...")
    run_ffmpeg(final_cmd, "最終合成")

    base_video.unlink(missing_ok=True)
    (run_dir / "mixed_audio.aac").unlink(missing_ok=True)

    # 完成動画の尺を最終確認
    final_sec = get_video_duration(output_path)
    size_mb   = output_path.stat().st_size / 1024 / 1024
    print(f"[05] ✅ 動画合成完了: {output_path}")
    print(f"[05]    尺: {final_sec:.2f}s / サイズ: {size_mb:.1f} MB")
    return output_path


# ─────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="動画・音声・字幕を合成する")
    parser.add_argument("--account-id", required=True)
    parser.add_argument("--run-id",     required=True)
    parser.add_argument("--format",     default="landscape",
                        help="フォーマット: landscape | shorts | tiktok")
    args = parser.parse_args()

    settings = load_settings()
    run_dir  = get_run_dir(args.account_id, args.run_id, settings)
    assemble_video(run_dir, settings, fmt=args.format)


if __name__ == "__main__":
    main()
