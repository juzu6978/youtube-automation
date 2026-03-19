"""
main.py
YouTube動画生成パイプラインのオーケストレーター。
各スクリプトをサブプロセスで順次実行する。

使い方:
  python scripts/main.py --account-id account_01
  python scripts/main.py --account-id account_01 --dry-run
  python scripts/main.py --account-id account_01 --run-id custom_run_001
  python scripts/main.py --account-id account_01 --use-sample
  python scripts/main.py --account-id account_01 --use-sample --format shorts
"""

import argparse
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.utils import load_settings, load_account_config, get_run_dir


PIPELINE_STEPS = [
    ("01_concept_generator",  "トピック生成"),
    ("02_script_writer",      "原稿生成"),
    ("03_tts_generator",      "TTS音声生成"),
    ("04_media_collector",    "動画素材収集"),
    ("05_video_assembler",    "動画合成"),
    ("06_thumbnail_creator",  "サムネイル生成"),
]

SAMPLE_DIR = Path(__file__).parent.parent / "assets" / "sample"
SCRIPTS_DIR = Path(__file__).parent.parent / "assets" / "scripts"

SHORT_FORMATS = ("shorts", "tiktok")  # 縦型（9:16）フォーマット


def run_step(script_name: str, label: str, account_id: str, run_id: str, extra_args: list = None):
    script_path = Path(f"scripts/{script_name}.py")
    cmd = [
        sys.executable, str(script_path),
        "--account-id", account_id,
        "--run-id", run_id,
    ]
    if extra_args:
        cmd.extend(extra_args)

    print(f"\n[STEP] {label}...")
    result = subprocess.run(cmd, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"{label} に失敗しました（終了コード: {result.returncode}）")


def run_upload(account_id: str, run_id: str, fmt: str, dry_run: bool):
    """YouTube または TikTok へ投稿する"""
    if fmt == "tiktok":
        script_path = Path("scripts/07b_tiktok_uploader.py")
        label = "TikTok投稿"
    else:
        script_path = Path("scripts/07_youtube_uploader.py")
        label = "YouTube投稿"

    cmd = [
        sys.executable, str(script_path),
        "--account-id", account_id,
        "--run-id", run_id,
        "--format", fmt,
    ]
    if dry_run:
        cmd.append("--dry-run")

    print(f"\n[STEP] {label}...")
    result = subprocess.run(cmd, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"{label}に失敗しました（終了コード: {result.returncode}）")


def _resolve_content_files(src_dir: Path, fmt: str) -> dict[str, Path]:
    """
    コンテンツディレクトリから concept.json / script.json の実パスを解決する。
    shorts/tiktok の場合は *_shorts.json を優先し、なければ通常版にフォールバック。
    """
    resolved = {}
    for base in ("concept", "script"):
        if fmt in SHORT_FORMATS:
            path = src_dir / f"{base}_shorts.json"
            if not path.exists():
                path = src_dir / f"{base}.json"   # フォールバック
        else:
            path = src_dir / f"{base}.json"
        resolved[f"{base}.json"] = path
    return resolved


def copy_sample_data(run_dir: Path, fmt: str = "landscape"):
    """assets/sample/ のJSONをrun_dirにコピーしてステップ01・02をスキップできるようにする。"""
    for dst_name, src in _resolve_content_files(SAMPLE_DIR, fmt).items():
        if not src.exists():
            raise FileNotFoundError(f"サンプルファイルが見つかりません: {src}")
        shutil.copy2(src, run_dir / dst_name)
        print(f"[SAMPLE] {src.name} → {run_dir / dst_name}")


def copy_topic_data(run_dir: Path, fmt: str, topic: str):
    """
    assets/scripts/{topic}/ のJSONをrun_dirにコピーしてステップ01・02をスキップする。
    topic にはパス区切りで指定可能（例: long/chatgpt_work, shorts/day01_run1）。
    """
    topic_dir = SCRIPTS_DIR / topic
    if not topic_dir.is_dir():
        available = []
        for d in sorted(SCRIPTS_DIR.iterdir()):
            if not d.is_dir() or d.name.startswith("_"):
                continue
            children = sorted(s.name for s in d.iterdir() if s.is_dir())
            if children:
                available.extend(f"{d.name}/{c}" for c in children)
            else:
                available.append(d.name)
        raise FileNotFoundError(
            f"トピック '{topic}' が見つかりません: {topic_dir}\n"
            f"利用可能なトピック: {available}"
        )
    for dst_name, src in _resolve_content_files(topic_dir, fmt).items():
        if not src.exists():
            raise FileNotFoundError(
                f"コンテンツファイルが見つかりません: {src}\n"
                f"ファイル名は concept.json / script.json （shorts用は concept_shorts.json / script_shorts.json）"
            )
        shutil.copy2(src, run_dir / dst_name)
        print(f"[TOPIC:{topic}] {src.name} → {run_dir / dst_name}")


def run_pipeline(account_id: str, run_id: str, fmt: str,
                 dry_run: bool = False, use_sample: bool = False, topic: str = ""):
    settings = load_settings()
    run_dir = get_run_dir(account_id, run_id, settings)
    run_dir.mkdir(parents=True, exist_ok=True)

    fmt_label = {"landscape": "横型 (16:9)", "shorts": "縦型 Shorts (9:16)", "tiktok": "縦型 TikTok (9:16)"}.get(fmt, fmt)

    # コンテンツ提供モードを決定
    skip_content_gen = bool(topic) or use_sample
    content_mode = f"ライブラリ ({topic})" if topic else ("サンプル" if use_sample else "Claude API")

    print(f"\n{'='*60}")
    print(f"  YouTube Automation Pipeline")
    print(f"  Account    : {account_id}")
    print(f"  Run ID     : {run_id}")
    print(f"  Format     : {fmt_label}")
    print(f"  Dry Run    : {dry_run}")
    print(f"  Content    : {content_mode}")
    print(f"  Work Dir   : {run_dir}")
    print(f"{'='*60}")
    if dry_run:
        print(f"\n  ⚠️  DRY RUN MODE: YouTubeへの投稿は行われません！")
        print(f"  ⚠️  実際に投稿するには dry_run チェックを外して再実行してください。\n")

    # コンテンツJSONをrun_dirにコピー（ステップ01・02をスキップ）
    if topic:
        copy_topic_data(run_dir, fmt, topic)
    elif use_sample:
        copy_sample_data(run_dir, fmt)

    extra_args = ["--format", fmt]

    try:
        for script_name, label in PIPELINE_STEPS:
            # topic または use_sample の場合、ステップ01・02はスキップ
            if skip_content_gen and script_name in ("01_concept_generator", "02_script_writer"):
                print(f"\n[SKIP] {label}（{content_mode}モード）")
                continue
            run_step(script_name, label, account_id, run_id, extra_args=extra_args)

        run_upload(account_id, run_id, fmt, dry_run)

        # 完了サマリー
        result_path = run_dir / "upload_result.json"
        if result_path.exists():
            import json
            with open(result_path) as f:
                result = json.load(f)
            print(f"\n{'='*60}")
            print(f"  完了！ [{fmt_label}]")
            print(f"  タイトル: {result.get('title', '(不明)')}")
            if result.get("dry_run"):
                print(f"  ⚠️  DRY RUN - YouTube投稿はスキップされました")
                print(f"  URL     : (投稿なし)")
            else:
                print(f"  URL     : {result.get('url', '(不明)')}")
            print(f"{'='*60}\n")

    except RuntimeError as e:
        print(f"\n[ERROR] {e}", file=sys.stderr)
        if not settings["pipeline"].get("cleanup_on_failure", False):
            print(f"[INFO] デバッグ用ファイルを保持: {run_dir}")
        else:
            shutil.rmtree(run_dir, ignore_errors=True)
        sys.exit(1)

    # 成功時のクリーンアップ（素材動画クリップを削除）
    if settings["pipeline"].get("cleanup_on_success", True) and not dry_run:
        clips_dir = run_dir / "clips"
        if clips_dir.exists():
            shutil.rmtree(clips_dir)
        (run_dir / "narration_raw.mp3").unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description="YouTube動画生成パイプライン")
    parser.add_argument("--account-id", required=True, help="config/accounts/ 内のアカウントID")
    parser.add_argument("--run-id", default=None, help="実行ID（省略時は自動生成）")
    parser.add_argument("--dry-run", action="store_true", help="YouTube/TikTok投稿をスキップ")
    parser.add_argument("--use-sample", action="store_true",
                        help="assets/sample/ の事前生成JSONを使用（Anthropic API不要）")
    parser.add_argument("--format", default=None,
                        help="フォーマット指定: landscape | shorts | tiktok（省略時はaccount設定に従う）")
    parser.add_argument("--topic", default="",
                        help="assets/scripts/{topic}/ のコンテンツを使用（Claude API不要）")
    args = parser.parse_args()

    run_id_base = args.run_id or datetime.now().strftime("%Y%m%d_%H%M%S")

    # --format 指定があれば1フォーマットのみ、なければアカウント設定の formats リストを使用
    if args.format:
        formats = [args.format]
    else:
        account_cfg = load_account_config(args.account_id)
        formats = account_cfg.get("content", {}).get("formats", ["landscape"])

    for fmt in formats:
        # フォーマットごとに独立した run_id（ディレクトリ）を使う
        run_id = f"{run_id_base}_{fmt}"
        run_pipeline(args.account_id, run_id, fmt,
                     dry_run=args.dry_run, use_sample=args.use_sample, topic=args.topic)


if __name__ == "__main__":
    main()
