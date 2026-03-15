"""
03_tts_generator.py
script.json のナレーション文を Google Cloud TTS で音声合成し、
BGM とミックスした最終音声ファイルを生成する。

出力:
  {run_dir}/narration_raw.mp3    # ナレーション原音
  {run_dir}/narration.mp3        # BGMミックス済み最終音声
  {run_dir}/timings.json         # 各文の開始時刻・終了時刻リスト（字幕用）
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

from google.cloud import texttospeech
from pydub import AudioSegment

sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.utils import load_account_config, load_settings, get_run_dir


def synthesize_sentence(client: texttospeech.TextToSpeechClient,
                         text: str,
                         voice_id: str,
                         speaking_rate: float,
                         pitch: float) -> bytes:
    synthesis_input = texttospeech.SynthesisInput(text=text)
    voice = texttospeech.VoiceSelectionParams(
        language_code="ja-JP",
        name=voice_id,
    )
    audio_config = texttospeech.AudioConfig(
        audio_encoding=texttospeech.AudioEncoding.MP3,
        speaking_rate=speaking_rate,
        pitch=pitch,
        effects_profile_id=["headphone-class-device"],
    )
    response = client.synthesize_speech(
        input=synthesis_input,
        voice=voice,
        audio_config=audio_config,
    )
    return response.audio_content


def build_narration_with_timings(script: dict, account_cfg: dict, run_dir: Path):
    tts_cfg = account_cfg["tts"]
    voice_id = tts_cfg["voice_id"]
    speaking_rate = tts_cfg.get("speaking_rate", 0.95)
    pitch = tts_cfg.get("pitch", 0.0)

    client = texttospeech.TextToSpeechClient()

    segments = []
    timings = []
    current_time_ms = 0
    pause_between_sentences_ms = 400  # 文間のポーズ

    sentences = script["sentences"]
    total = len(sentences)

    for i, sentence in enumerate(sentences):
        text = sentence["text"].strip()
        if not text:
            continue

        print(f"[03] TTS {i+1}/{total}: {text[:30]}...")
        audio_bytes = synthesize_sentence(client, text, voice_id, speaking_rate, pitch)

        # バイトをAudioSegmentに変換
        tmp_path = run_dir / f"_sent_{i:04d}.mp3"
        tmp_path.write_bytes(audio_bytes)
        segment = AudioSegment.from_mp3(tmp_path)

        start_ms = current_time_ms
        end_ms = current_time_ms + len(segment)

        timings.append({
            "index": sentence["index"],
            "text": text,
            "section": sentence.get("section", ""),
            "start_ms": start_ms,
            "end_ms": end_ms,
        })

        segments.append(segment)
        current_time_ms = end_ms + pause_between_sentences_ms

        # API制限対策（無料枠は特に問題ないが念のため）
        time.sleep(0.05)

    # 連結
    narration = segments[0]
    for seg in segments[1:]:
        narration = narration + AudioSegment.silent(duration=pause_between_sentences_ms) + seg

    narration_path = run_dir / "narration_raw.mp3"
    narration.export(narration_path, format="mp3", bitrate="192k")

    # 一時ファイル削除
    for i in range(len(sentences)):
        tmp = run_dir / f"_sent_{i:04d}.mp3"
        if tmp.exists():
            tmp.unlink()

    timings_path = run_dir / "timings.json"
    with open(timings_path, "w", encoding="utf-8") as f:
        json.dump(timings, f, ensure_ascii=False, indent=2)

    print(f"[03] ナレーション生成完了: {len(narration)/1000:.1f}秒")
    return narration, timings


def mix_with_bgm(narration: AudioSegment, settings: dict, run_dir: Path) -> Path:
    bgm_volume_db = settings["audio"]["bgm_volume_db"]
    fade_in_sec = int(settings["audio"]["fade_in_sec"] * 1000)
    fade_out_sec = int(settings["audio"]["fade_out_sec"] * 1000)

    bgm_dir = Path("assets/bgm")
    bgm_files = list(bgm_dir.glob("*.mp3")) + list(bgm_dir.glob("*.wav"))

    if bgm_files:
        bgm = AudioSegment.from_file(bgm_files[0])
        # ナレーションの長さに合わせてループ
        while len(bgm) < len(narration):
            bgm = bgm + bgm
        bgm = bgm[:len(narration)]
        bgm = bgm.apply_gain(bgm_volume_db)
        bgm = bgm.fade_in(fade_in_sec).fade_out(fade_out_sec)
        mixed = narration.overlay(bgm)
    else:
        print("[03] BGMファイルが見つかりません。ナレーションのみで続行します。")
        mixed = narration

    output_path = run_dir / "narration.mp3"
    mixed.export(output_path, format="mp3", bitrate="192k")
    print(f"[03] BGMミックス完了: {output_path}")
    return output_path


def main():
    parser = argparse.ArgumentParser(description="TTS音声を生成しBGMとミックスする")
    parser.add_argument("--account-id", required=True)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()

    account_cfg = load_account_config(args.account_id)
    settings = load_settings()
    run_dir = get_run_dir(args.account_id, args.run_id, settings)

    script_path = run_dir / "script.json"
    with open(script_path, encoding="utf-8") as f:
        script = json.load(f)

    narration, _ = build_narration_with_timings(script, account_cfg, run_dir)
    mix_with_bgm(narration, settings, run_dir)


if __name__ == "__main__":
    main()
