"""
03_tts_generator.py
script.json のナレーション文を TTS で音声合成し、BGM とミックスした最終音声を生成する。

対応プロバイダー:
  - edge_tts   : Microsoft Edge TTS（無料・APIキー不要・高品質）← 推奨
  - google_tts : Google Cloud TTS WaveNet（有料 or 無料枠500万字/月）

出力:
  {run_dir}/narration_raw.mp3    # ナレーション原音
  {run_dir}/narration.mp3        # BGMミックス済み最終音声
  {run_dir}/timings.json         # 各文の開始・終了時刻（字幕用）
"""

import argparse
import asyncio
import io
import json
import os
import sys
import time
from pathlib import Path

from pydub import AudioSegment

sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.utils import load_account_config, load_settings, get_run_dir


# ─────────────────────────────────────────────
# Edge TTS（Microsoft・無料）
# ─────────────────────────────────────────────

async def _edge_synthesize_async(text: str, voice: str,
                                  rate_str: str, pitch_str: str) -> bytes:
    """edge-tts で非同期合成し MP3 バイト列を返す"""
    import edge_tts  # 遅延インポート（google_tts 使用時に import エラーを避ける）
    communicate = edge_tts.Communicate(
        text=text,
        voice=voice,
        rate=rate_str,
        pitch=pitch_str,
    )
    chunks = []
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            chunks.append(chunk["data"])
    if not chunks:
        raise RuntimeError(f"Edge TTS: 音声データなし（text='{text[:20]}'）")
    return b"".join(chunks)


def synthesize_edge(text: str, voice_id: str,
                    speaking_rate: float, pitch: float) -> bytes:
    """
    Edge TTS で合成し MP3 バイト列を返す。
    speaking_rate: 1.5 → "+50%", 0.8 → "-20%"
    pitch: semitone 値 → Hz 換算（例: 0.0 → "+0Hz"）
    """
    rate_pct = int((speaking_rate - 1.0) * 100)
    rate_str = f"+{rate_pct}%" if rate_pct >= 0 else f"{rate_pct}%"
    pitch_hz = int(pitch * 10)  # 簡易換算（1 semitone ≒ 10Hz）
    pitch_str = f"+{pitch_hz}Hz" if pitch_hz >= 0 else f"{pitch_hz}Hz"

    return asyncio.run(
        _edge_synthesize_async(text, voice_id, rate_str, pitch_str)
    )


# ─────────────────────────────────────────────
# Google Cloud TTS（フォールバック）
# ─────────────────────────────────────────────

def synthesize_google(text: str, voice_id: str,
                      speaking_rate: float, pitch: float) -> bytes:
    """Google Cloud TTS で合成し MP3 バイト列を返す"""
    from google.cloud import texttospeech  # 遅延インポート
    client = texttospeech.TextToSpeechClient()
    response = client.synthesize_speech(
        input=texttospeech.SynthesisInput(text=text),
        voice=texttospeech.VoiceSelectionParams(
            language_code="ja-JP",
            name=voice_id,
        ),
        audio_config=texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.MP3,
            speaking_rate=speaking_rate,
            pitch=pitch,
            effects_profile_id=["headphone-class-device"],
        ),
    )
    return response.audio_content


# ─────────────────────────────────────────────
# プロバイダー振り分け
# ─────────────────────────────────────────────

def synthesize_sentence(text: str, provider: str, voice_id: str,
                         speaking_rate: float, pitch: float) -> bytes:
    """プロバイダーに応じてTTSを呼び分ける"""
    if provider == "edge_tts":
        return synthesize_edge(text, voice_id, speaking_rate, pitch)
    elif provider == "google_tts":
        return synthesize_google(text, voice_id, speaking_rate, pitch)
    else:
        raise ValueError(f"未対応のTTSプロバイダー: {provider}（edge_tts / google_tts）")


# ─────────────────────────────────────────────
# ナレーション生成
# ─────────────────────────────────────────────

def build_narration_with_timings(script: dict, account_cfg: dict,
                                  settings: dict, run_dir: Path):
    tts_cfg      = account_cfg["tts"]
    # アカウント設定 → グローバル設定 の順に fallback
    provider     = tts_cfg.get("provider") or settings.get("tts", {}).get("provider", "edge_tts")
    voice_id     = tts_cfg["voice_id"]
    speaking_rate = tts_cfg.get("speaking_rate", 1.0)
    pitch        = tts_cfg.get("pitch", 0.0)
    pause_ms     = 400  # 文間のポーズ（ms）

    print(f"[03] TTS プロバイダー: {provider} / ボイス: {voice_id} / 速度: {speaking_rate}x")

    sentences = script["sentences"]
    total = len(sentences)
    segments = []
    timings  = []
    current_ms = 0

    for i, sentence in enumerate(sentences):
        text = sentence["text"].strip()
        if not text:
            continue

        print(f"[03] {i+1}/{total}: {text[:35]}...")
        audio_bytes = synthesize_sentence(text, provider, voice_id, speaking_rate, pitch)

        # MP3バイト → AudioSegment
        segment = AudioSegment.from_mp3(io.BytesIO(audio_bytes))

        start_ms = current_ms
        end_ms   = current_ms + len(segment)

        timings.append({
            "index":   sentence["index"],
            "text":    text,
            "section": sentence.get("section", ""),
            "start_ms": start_ms,
            "end_ms":   end_ms,
        })
        segments.append(segment)
        current_ms = end_ms + pause_ms

        # Edge TTS は非同期だが念のため少し間隔を空ける
        time.sleep(0.03)

    # 全文を連結（文間にポーズを挿入）
    silence = AudioSegment.silent(duration=pause_ms)
    narration = segments[0]
    for seg in segments[1:]:
        narration = narration + silence + seg

    narration_path = run_dir / "narration_raw.mp3"
    narration.export(narration_path, format="mp3", bitrate="192k")

    timings_path = run_dir / "timings.json"
    with open(timings_path, "w", encoding="utf-8") as f:
        json.dump(timings, f, ensure_ascii=False, indent=2)

    # pydub の実測値を別ファイルに保存。
    # MP3 を ffprobe で読んだときの VBR ヘッダー誤差を避けるため、
    # 05_video_assembler.py はこちらの値を「正確な出力尺」として使用する。
    duration_ms = len(narration)
    meta_path = run_dir / "narration_meta.json"
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump({
            "duration_ms": duration_ms,
            "duration_sec": duration_ms / 1000,
            "sentence_count": total,
        }, f, ensure_ascii=False, indent=2)

    duration_sec = duration_ms / 1000
    print(f"[03] ナレーション生成完了: {duration_sec:.1f}秒 / {total}文")
    return narration, timings


# ─────────────────────────────────────────────
# BGM ミックス
# ─────────────────────────────────────────────

def mix_with_bgm(narration: AudioSegment, settings: dict, run_dir: Path) -> Path:
    bgm_volume_db = settings["audio"]["bgm_volume_db"]
    fade_in_ms    = int(settings["audio"]["fade_in_sec"] * 1000)
    fade_out_ms   = int(settings["audio"]["fade_out_sec"] * 1000)

    bgm_files = list(Path("assets/bgm").glob("*.mp3")) + \
                list(Path("assets/bgm").glob("*.wav"))

    if bgm_files:
        bgm = AudioSegment.from_file(bgm_files[0])
        # ナレーション尺に合わせてループ
        while len(bgm) < len(narration):
            bgm = bgm + bgm
        bgm = bgm[:len(narration)]
        bgm = bgm.apply_gain(bgm_volume_db).fade_in(fade_in_ms).fade_out(fade_out_ms)
        mixed = narration.overlay(bgm)
        print(f"[03] BGMミックス: {bgm_files[0].name} ({bgm_volume_db}dB)")
    else:
        print("[03] BGMファイルなし。ナレーションのみで続行します。")
        mixed = narration

    output_path = run_dir / "narration.mp3"
    mixed.export(output_path, format="mp3", bitrate="192k")
    print(f"[03] 最終音声: {output_path}")
    return output_path


# ─────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="TTS音声を生成しBGMとミックスする")
    parser.add_argument("--account-id", required=True)
    parser.add_argument("--run-id",     required=True)
    parser.add_argument("--format",     default="landscape")
    args = parser.parse_args()

    account_cfg = load_account_config(args.account_id)
    settings    = load_settings()
    run_dir     = get_run_dir(args.account_id, args.run_id, settings)

    with open(run_dir / "script.json", encoding="utf-8") as f:
        script = json.load(f)

    narration, _ = build_narration_with_timings(script, account_cfg, settings, run_dir)
    mix_with_bgm(narration, settings, run_dir)


if __name__ == "__main__":
    main()
