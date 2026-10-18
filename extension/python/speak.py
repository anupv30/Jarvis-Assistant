#!/usr/bin/env python3
"""
Jarvis Ultra-Low Latency Neural AI Speech Engine
Features:
- Instant playback of pre-rendered static clips: `on_it.mp3` & `listening.mp3`.
- Unique collision-free temporary audio files (`temp_speech_<timestamp>_<uuid>.mp3`).
- Explicit stream release and automatic temp file deletion.
- Background process console logging: `[TTS] Speaking: <text>`.
- Supports CLI flags: --intent-response, --intent-start, --intent-progress, --intent-error, --init, or raw text string.
"""

import sys
import os
import time
import json
import uuid
import asyncio
import re

# Suppress Pygame welcome banner
os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
INTENT_FILE = os.path.join(PROJECT_ROOT, "last_intent.json")

ON_IT_AUDIO = os.path.join(PROJECT_ROOT, "on_it.mp3")
LISTENING_AUDIO = os.path.join(PROJECT_ROOT, "listening.mp3")

NEURAL_VOICE = "en-US-ChristopherNeural"

def cleanup_old_temp_files():
    """Sweeps and deletes old temporary audio files to keep directory clean."""
    try:
        for fname in os.listdir(PROJECT_ROOT):
            if fname.startswith("temp_speech") and fname.endswith(".mp3"):
                fpath = os.path.join(PROJECT_ROOT, fname)
                try:
                    # Remove files older than 20 seconds
                    if time.time() - os.path.getmtime(fpath) > 20:
                        os.remove(fpath)
                except Exception:
                    pass
    except Exception:
        pass

def cleanup_file(filepath: str):
    """Safely removes a specific audio file after playback."""
    if not filepath or filepath in [ON_IT_AUDIO, LISTENING_AUDIO]:
        return
    for _ in range(5):
        try:
            if os.path.exists(filepath):
                os.remove(filepath)
            break
        except Exception:
            time.sleep(0.05)

async def generate_speech_audio(text: str, output_path: str):
    """Renders speech using edge-tts with the Christopher Neural voice."""
    import edge_tts
    communicator = edge_tts.Communicate(
        text=text,
        voice=NEURAL_VOICE,
        rate="+0%",
        pitch="-2Hz",
    )
    await communicator.save(output_path)

def ensure_static_audio():
    """Pre-generates static local audio files for zero-latency instant playback."""
    static_clips = {
        ON_IT_AUDIO: "On it, sir.",
        LISTENING_AUDIO: "Listening, sir.",
    }
    for path, phrase in static_clips.items():
        if not os.path.exists(path) or os.path.getsize(path) == 0:
            try:
                asyncio.run(generate_speech_audio(phrase, path))
                print(f"[speak.py] Pre-rendered static clip: {os.path.basename(path)}")
            except Exception as e:
                print(f"[speak.py] Static clip generation warning ({os.path.basename(path)}): {e}", file=sys.stderr)

def play_audio_file(audio_path: str):
    """Plays audio via pre-warmed 24kHz pygame mixer and releases stream immediately."""
    if not os.path.exists(audio_path) or os.path.getsize(audio_path) == 0:
        return

    import pygame

    try:
        if not pygame.mixer.get_init():
            pygame.mixer.init(frequency=24000, buffer=1024)
        pygame.mixer.music.load(audio_path)
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            time.sleep(0.02)
        pygame.mixer.music.stop()
        if hasattr(pygame.mixer.music, "unload"):
            pygame.mixer.music.unload()
        pygame.mixer.quit()
    except Exception as e:
        print(f"[TTS] Playback notice: {e}", file=sys.stderr)
        try:
            pygame.mixer.quit()
        except Exception:
            pass
    finally:
        cleanup_file(audio_path)

def clean_spoken_text(text: str) -> str:
    """Strips markdown asterisks, backticks, hashes, and formatting for clear TTS."""
    if not text:
        return ""
    t = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
    t = re.sub(r"`([^`]+)`", r"\1", t)
    t = re.sub(r"\*\*([^*]+)\*\*", r"\1", t)
    t = re.sub(r"\*([^*]+)\*", r"\1", t)
    t = re.sub(r"__([^_]+)__", r"\1", t)
    t = re.sub(r"_([^_]+)_", r"\1", t)
    t = re.sub(r"^#+\s*", "", t, flags=re.MULTILINE)
    t = re.sub(r"^>\s*", "", t, flags=re.MULTILINE)
    t = re.sub(r"^[\*\-\+]\s+", "", t, flags=re.MULTILINE)
    t = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", t)
    t = re.sub(r"[\r\n]+", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t

def speak_offline_sapi(text: str) -> bool:
    """Offline Windows Native TTS Fallback via SAPI.SpVoice or System.Speech."""
    # 1. Primary Offline: COM SAPI.SpVoice
    try:
        import win32com.client
        speaker = win32com.client.Dispatch("SAPI.SpVoice")
        speaker.Rate = 1
        speaker.Volume = 100
        speaker.Speak(text)
        return True
    except Exception:
        pass

    # 2. Secondary Offline: PowerShell System.Speech
    try:
        escaped = text.replace("'", "''").replace('"', '`"')
        cmd = f"Add-Type -AssemblyName System.Speech; $s = New-Object System.Speech.Synthesis.SpeechSynthesizer; $s.Speak('{escaped}')"
        subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True, timeout=10)
        return True
    except Exception as e:
        print(f"[TTS] Offline SAPI error: {e}", file=sys.stderr)
        return False

def speak_direct(text: str):
    """Speaks text: plays pre-rendered MP3 if available, otherwise generates dynamic speech with offline SAPI fallback."""
    clean = clean_spoken_text(text.strip())
    if not clean:
        return

    # Logging to console
    print(f"[TTS] Speaking: {clean}", flush=True)

    # Check for direct audio file requests or known phrases
    if clean.lower() in ["on it, sir.", "on it", "on_it.mp3"]:
        if os.path.exists(ON_IT_AUDIO):
            play_audio_file(ON_IT_AUDIO)
            return
    elif clean.lower() in ["listening, sir.", "listening", "listening.mp3"]:
        if os.path.exists(LISTENING_AUDIO):
            play_audio_file(LISTENING_AUDIO)
            return

    # Clean old leftover temp files before synthesizing new audio
    cleanup_old_temp_files()

    # Generate collision-free unique temporary MP3
    unique_tag = f"{int(time.time() * 1000)}_{uuid.uuid4().hex[:6]}"
    temp_audio_file = os.path.join(PROJECT_ROOT, f"temp_speech_{unique_tag}.mp3")

    try:
        asyncio.run(generate_speech_audio(clean, temp_audio_file))
        play_audio_file(temp_audio_file)
    except Exception as e:
        print(f"[TTS] Edge-TTS offline notice ({e}), speaking via offline Windows SAPI...", file=sys.stderr)
        cleanup_file(temp_audio_file)
        speak_offline_sapi(clean)

def resolve_phrase_from_args() -> str:
    """Resolves target phrase from CLI flags, intent files, or string arguments."""
    args = sys.argv[1:]
    if not args:
        return "Neural AI speech engine is online, sir."

    first_arg = args[0].strip()

    # File flag
    if first_arg == "--file" and len(args) > 1:
        path = args[1]
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return f.read().strip()
        return ""

    # Intent flags
    if first_arg == "--intent-start":
        if os.path.exists(INTENT_FILE):
            try:
                with open(INTENT_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return data.get("speaking_start", "")
            except Exception:
                return ""
        return ""

    if first_arg in ["--intent-response", "--intent-success"]:
        if os.path.exists(INTENT_FILE):
            try:
                with open(INTENT_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return data.get("speaking_response", data.get("speaking_success", "Task completed successfully, sir."))
            except Exception:
                return "Task completed successfully, sir."
        return "Task completed successfully, sir."

    if first_arg == "--intent-progress":
        if os.path.exists(INTENT_FILE):
            try:
                with open(INTENT_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return data.get("speaking_progress", "")
            except Exception:
                return ""
        return ""

    if first_arg == "--intent-error":
        if os.path.exists(INTENT_FILE):
            try:
                with open(INTENT_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return data.get("speaking_error", "Task failed, sir.")
            except Exception:
                return "Task failed, sir."
        return "Task failed, sir."

    # Handle unexpanded or literal n8n/powershell expression "$json.speaking_response" / ".speaking_response"
    raw_joined = " ".join(args).strip()
    if raw_joined in [
        "$json.speaking_response",
        '"$json.speaking_response"',
        ".speaking_response",
        '".speaking_response"',
        "$json",
        ""
    ]:
        if os.path.exists(INTENT_FILE):
            try:
                with open(INTENT_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return data.get("speaking_response", "Task completed, sir.")
            except Exception:
                return "Task completed, sir."
        return "Task completed, sir."

    # If argument contains JSON
    if raw_joined.startswith("{") and raw_joined.endswith("}"):
        try:
            parsed = json.loads(raw_joined)
            return parsed.get("speaking_response", parsed.get("text", raw_joined))
        except Exception:
            pass

    return raw_joined

def main():
    if "--init" in sys.argv:
        ensure_static_audio()
        sys.exit(0)

    phrase = resolve_phrase_from_args()
    if phrase:
        speak_direct(phrase)
    sys.exit(0)

if __name__ == "__main__":
    main()

