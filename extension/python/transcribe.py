#!/usr/bin/env python3
"""
Jarvis Speech-to-Text Transcription Module
Primary Engine: Groq Cloud API (whisper-large-v3-turbo) for ultra-fast sub-100ms transcription.
Offline Fallback: Local faster-whisper (tiny.en, int8 quantization).
Saves last transcript to `last_transcript.txt` for rock-solid workflow pipeline safety.
"""

import sys
import os
import re
import warnings
import requests
from dotenv import load_dotenv

# Suppress HuggingFace hub symlink warnings on Windows
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
warnings.filterwarnings("ignore")

load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
TRANSCRIPT_CACHE_FILE = os.path.join(PROJECT_ROOT, "last_transcript.txt")

WHISPER_PROMPT = (
    "Jarvis developer assistant: git commit, git status, git push, git branch, git checkout, "
    "git pull, git revert, git diff, git stash, GitHub, create repository, merge, stage, codebase, "
    "checkout main, switch branch, commit changes."
)

def sanitize_transcript(text: str) -> str:
    """Removes irregular newlines, control characters, filler words, and fixes common phonetic ASR confusions."""
    if not text:
        return ""
    cleaned = re.sub(r"[\r\n\t]+", " ", text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    # Strip accidental leading wake words
    cleaned = re.sub(r"^(?:hey\s+)?jarvis[\s,\.\!:]*", "", cleaned, flags=re.IGNORECASE).strip()
    cleaned = re.sub(r"^(?:please\s+|could\s+you\s+|can\s+you\s+)", "", cleaned, flags=re.IGNORECASE).strip()

    # Correct common ASR misrecognitions for developer and Git terms
    substitutions = [
        (r"\bget\s+(status|commit|push|pull|branch|checkout|diff|log|stash|revert|remote|init|fetch|merge)\b", r"git \1"),
        (r"\b(?:did|kid|good|give)\s+(status|commit|push|pull|branch|checkout|diff)\b", r"git \1"),
        (r"\bchechout\b", "checkout"),
        (r"\bcheck\s+out\b", "checkout"),
        (r"\bcomit\b", "commit"),
        (r"\bcoma\s+message\b", "commit message"),
        (r"\bcoma\b", "commit"),
        (r"\bstash\s+pop\b", "stash pop"),
    ]
    for pattern, replacement in substitutions:
        cleaned = re.sub(pattern, replacement, cleaned, flags=re.IGNORECASE)

    return cleaned.strip()

def transcribe_with_groq(audio_path: str) -> str:
    """Primary ASR: Groq Cloud API whisper-large-v3 with developer vocabulary prompt bias."""
    if not GROQ_API_KEY or GROQ_API_KEY.startswith("your_"):
        raise ValueError("GROQ_API_KEY is not configured.")

    url = "https://api.groq.com/openai/v1/audio/transcriptions"
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
    }

    # Try whisper-large-v3 first (highest accuracy), then turbo
    models_to_try = ["whisper-large-v3", "whisper-large-v3-turbo"]
    last_err = None

    for model_name in models_to_try:
        try:
            with open(audio_path, "rb") as f:
                files = {
                    "file": (os.path.basename(audio_path), f, "audio/wav"),
                }
                data = {
                    "model": model_name,
                    "temperature": "0.0",
                    "language": "en",
                    "prompt": WHISPER_PROMPT,
                    "response_format": "json",
                }
                response = requests.post(url, headers=headers, files=files, data=data, timeout=12)

            if response.status_code == 200:
                result = response.json()
                raw_text = result.get("text", "")
                return sanitize_transcript(raw_text)
            else:
                last_err = f"HTTP {response.status_code}: {response.text}"
        except Exception as e:
            last_err = str(e)

    raise RuntimeError(f"Groq Whisper failed: {last_err}")

os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

def transcribe_with_faster_whisper(audio_path: str) -> str:
    """Offline Fallback ASR: Local faster-whisper tiny.en with direct WAV numpy ingestion."""
    try:
        from faster_whisper import WhisperModel
        import wave
        import numpy as np
    except ImportError:
        raise RuntimeError("faster-whisper or numpy is not installed in local environment.")

    # Convert WAV to float32 numpy array to bypass PyAV container issues
    audio_input = audio_path
    try:
        with wave.open(audio_path, "rb") as wf:
            n_channels = wf.getnchannels()
            sampwidth = wf.getsampwidth()
            frames = wf.readframes(wf.getnframes())
            if sampwidth == 2:
                raw_np = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
            elif sampwidth == 4:
                raw_np = np.frombuffer(frames, dtype=np.int32).astype(np.float32) / 2147483648.0
            else:
                raw_np = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0

            if n_channels > 1:
                raw_np = raw_np.reshape(-1, n_channels).mean(axis=1)
            audio_input = raw_np
    except Exception:
        audio_input = audio_path

    model = WhisperModel("tiny.en", device="cpu", compute_type="int8")
    segments, _ = model.transcribe(
        audio_input,
        beam_size=5,
        vad_filter=True,
        initial_prompt=WHISPER_PROMPT,
        vad_parameters=dict(min_silence_duration_ms=400),
    )
    text_parts = [segment.text.strip() for segment in segments]
    return sanitize_transcript(" ".join(text_parts))

def transcribe(audio_path: str) -> str:
    if not os.path.exists(audio_path):
        print(f"[transcribe.py] Warning: File not found: {audio_path}", file=sys.stderr)
        return ""

    force_offline = (
        os.getenv("FORCE_OFFLINE", "false").lower() in ["true", "1", "yes"]
        or "--offline" in sys.argv
    )

    if not force_offline:
        # 1. Primary: Groq Cloud API (whisper-large-v3 + domain prompt)
        try:
            text = transcribe_with_groq(audio_path)
            if text:
                return text
        except Exception as e:
            print(f"[transcribe.py] Groq Whisper notice ({e}), falling back to offline faster-whisper...", file=sys.stderr)

    # 2. Offline Fallback: Local faster-whisper
    try:
        return transcribe_with_faster_whisper(audio_path)
    except Exception as e:
        print(f"[transcribe.py] Local faster-whisper notice: {e}", file=sys.stderr)
        return ""

def main():
    audio_file = sys.argv[1] if len(sys.argv) > 1 else "recorded_command.wav"
    try:
        transcript = transcribe(audio_file)
    except Exception as e:
        print(f"[transcribe.py] Unexpected error: {e}", file=sys.stderr)
        transcript = ""

    # Cache transcript to file for quote-safe downstream access
    try:
        with open(TRANSCRIPT_CACHE_FILE, "w", encoding="utf-8") as f:
            f.write(transcript)
    except Exception as e:
        print(f"[transcribe.py] Could not cache transcript: {e}", file=sys.stderr)

    # Output to stdout
    print(transcript)
    sys.exit(0)

if __name__ == "__main__":
    main()
