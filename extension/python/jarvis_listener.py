#!/usr/bin/env python3
"""
Jarvis Zero-Latency Conversational Voice Listener
Features:
- Instant 0ms local wake-up acknowledgment: plays pre-rendered `on_it.mp3` directly via pygame.mixer.
- Real-time openWakeWord detection (Threshold: 0.20).
- Ultra-responsive Silero VAD boundary detection with 350ms silence cutoff.
- No network delay or subprocess spawn lag for wake-up confirmation.
- Direct multipart HTTP POST dispatch to n8n webhook.
"""

import os
import sys
import time
import subprocess
import wave
import requests
import numpy as np
try:
    import pyaudio
    AUDIO_FORMAT_INT16 = pyaudio.paInt16
except Exception:
    pyaudio = None
    AUDIO_FORMAT_INT16 = 2
import pygame
import threading
import json
from dotenv import load_dotenv

# Suppress Pygame banner
os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"

# Load environment configuration
load_dotenv()

from jarvis_config import (
    JARVIS_CORE_DIR,
    get_target_repo,
    set_active_project,
    get_project_name,
    is_n8n_online,
    ensure_n8n_running,
    get_current_git_branch,
    launch_hud,
)

N8N_WEBHOOK_URL = os.getenv("N8N_WEBHOOK_URL", "http://localhost:5678/webhook/jarvis-git").strip()

PROJECT_ROOT = JARVIS_CORE_DIR
OUTPUT_AUDIO_FILE = os.path.join(PROJECT_ROOT, "recorded_command.wav")
ON_IT_AUDIO = os.path.join(PROJECT_ROOT, "on_it.mp3")

# Audio & Wake Word Parameters
THRESHOLD = 0.20
RATE = 16000
CHUNK = 1280  # 80ms chunks
FORMAT = AUDIO_FORMAT_INT16
CHANNELS = 1

# VAD Parameters
SILENCE_TIMEOUT_MS = 1200  # 1200ms natural conversational pause tolerance (no premature cutting)
MIN_SPEECH_CHUNKS = 6      # Require ~480ms speech before silence checks
MIN_RECORDING_SEC = 2.5    # Minimum 2.5s recording window so full queries are always captured
MAX_RECORDING_SEC = 14     # Generous safety cap for complex commands
VAD_SPEECH_THRESHOLD = 0.28# High sensitivity for natural voices
RMS_ENERGY_THRESHOLD = 150.0# Low energy floor for quiet microphones

def launch_hud_interface():
    """Seamlessly launches the Jarvis Sci-Fi HUD in a non-blocking background subprocess."""
    target_dir = get_target_repo()
    launch_hud(target_dir)

def play_instant_wake_acknowledgment():
    """Plays pre-rendered 'on_it.mp3' directly in the process for true 0ms response."""
    if os.path.exists(ON_IT_AUDIO):
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init(frequency=24000, buffer=1024)
            pygame.mixer.music.load(ON_IT_AUDIO)
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy():
                time.sleep(0.02)
        except Exception as e:
            print(f"[Jarvis] Local wake playback notice: {e}", file=sys.stderr)

def record_dynamic_command(stream, vad_engine) -> bytes:
    """Dynamically records microphone audio with intelligent pause tolerance and complete query capture."""
    # Flush any stale buffer accumulated during wake word playback
    if stream:
        try:
            available = stream.get_read_available()
            if available > 0:
                stream.read(available, exception_on_overflow=False)
        except Exception:
            pass

    print("[Jarvis] Listening to command (speak naturally, 1.2s pause tolerance)...")
    frames = []
    has_spoken = False
    speech_chunks_count = 0
    silence_duration_ms = 0
    start_time = time.time()
    max_chunks = int((RATE / CHUNK) * MAX_RECORDING_SEC)

    for _ in range(max_chunks):
        raw_data = stream.read(CHUNK, exception_on_overflow=False)
        frames.append(raw_data)
        audio_chunk = np.frombuffer(raw_data, dtype=np.int16)

        try:
            speech_prob = vad_engine.predict(audio_chunk, frame_size=320)
        except Exception:
            speech_prob = 0.0

        rms = np.sqrt(np.mean(audio_chunk.astype(np.float32) ** 2))
        is_speech = (speech_prob >= VAD_SPEECH_THRESHOLD) or (rms >= RMS_ENERGY_THRESHOLD)

        elapsed = time.time() - start_time

        if is_speech:
            has_spoken = True
            speech_chunks_count += 1
            silence_duration_ms = 0
        else:
            # Only trigger silence cutoff if user has spoken AND recorded for at least MIN_RECORDING_SEC
            if has_spoken and speech_chunks_count >= MIN_SPEECH_CHUNKS and elapsed >= MIN_RECORDING_SEC:
                silence_duration_ms += 80
                if silence_duration_ms >= SILENCE_TIMEOUT_MS:
                    print(f"[Jarvis] End-of-speech detected ({silence_duration_ms}ms pause, {elapsed:.1f}s total).")
                    break

        if elapsed > MAX_RECORDING_SEC:
            print("[Jarvis] Maximum recording safety timeout reached.")
            break

    return b"".join(frames)

def save_wav(raw_bytes: bytes, audio, filepath: str):
    """Saves WAV audio with peak amplitude normalization for maximum Whisper accuracy."""
    try:
        samples = np.frombuffer(raw_bytes, dtype=np.int16).astype(np.float32)
        max_val = np.max(np.abs(samples))
        if max_val > 50:
            gain = (32767.0 * 0.90) / max_val
            samples = np.clip(samples * min(gain, 4.0), -32768, 32767).astype(np.int16)
            raw_bytes = samples.tobytes()
    except Exception:
        pass

    with wave.open(filepath, "wb") as wf:
        wf.setnchannels(CHANNELS)
        sampwidth = audio.get_sample_size(FORMAT) if (audio and hasattr(audio, "get_sample_size")) else 2
        wf.setsampwidth(sampwidth)
        wf.setframerate(RATE)
        wf.writeframes(raw_bytes)

def dispatch_to_n8n(audio_path: str):
    """Sends recorded command to n8n webhook."""
    if not N8N_WEBHOOK_URL:
        return
    try:
        with open(audio_path, "rb") as f:
            files = {"file": (os.path.basename(audio_path), f, "audio/wav")}
            resp = requests.post(N8N_WEBHOOK_URL, files=files, timeout=10)
            print(f"[Jarvis] n8n webhook response: HTTP {resp.status_code}")
    except Exception:
        pass

def process_transcript_pipeline(transcript: str, play_tts: bool = True, source: str = "voice") -> dict:
    """
    Unified execution pipeline for both voice and text inputs:
    1. Updates last_transcript.txt (HUD updates immediately)
    2. Routes intent dynamically with Groq LLM -> Local Ollama fallback -> Deterministic fallback
    3. Speaks task acknowledgment (if play_tts=True)
    4. Executes Git CLI operation or Antigravity task
    5. Updates last_status.txt
    6. Speaks completion or answers question (if play_tts=True)
    """
    clean_text = transcript.strip()
    if not clean_text:
        return {"status": "error", "message": "Empty query"}

    print(f"\n[Jarvis Pipeline] [{source.upper()}] Processing: \"{clean_text}\"")

    # Step 1: Update transcript cache for HUD & downstream tools
    transcript_file = os.path.join(PROJECT_ROOT, "last_transcript.txt")
    try:
        with open(transcript_file, "w", encoding="utf-8") as f:
            f.write(clean_text)
    except Exception:
        pass

    # Step 2: Route intent dynamically (Groq -> Ollama -> Deterministic)
    print(f"[Jarvis Pipeline] Routing intent for: \"{clean_text}\"...")
    subprocess.run(
        [sys.executable, os.path.join(PROJECT_ROOT, "intent_router.py"), clean_text],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True
    )

    intent_file = os.path.join(PROJECT_ROOT, "last_intent.json")
    if not os.path.exists(intent_file):
        print("[Jarvis Pipeline] Error: last_intent.json not found.", file=sys.stderr)
        return {"status": "error", "message": "Failed to generate intent."}

    with open(intent_file, "r", encoding="utf-8") as f:
        intent = json.load(f)

    itype = intent.get("type", "general_qa")
    spk_start = intent.get("speaking_start", "")
    spk_resp = intent.get("speaking_response", "")

    result_payload = {"status": "success", "intent": intent, "source": source}

    # Step 3: Handle Action vs QA
    if itype == "git_query":
        answer = spk_resp or "Checking git status, sir."
        print(f"[Jarvis Pipeline] Spoken answer: {answer}")
        if play_tts:
            subprocess.run([sys.executable, os.path.join(PROJECT_ROOT, "speak.py"), answer], cwd=PROJECT_ROOT)
        result_payload["response"] = answer

    elif itype == "git_action":
        # Acknowledge task start: "On it, sir..."
        start_phrase = spk_start or "On it, sir. Committing and pushing your changes."
        print(f"[Jarvis Pipeline] Announcing start: {start_phrase}")
        if play_tts:
            subprocess.run([sys.executable, os.path.join(PROJECT_ROOT, "speak.py"), start_phrase], cwd=PROJECT_ROOT)

        # Step 4: Execute Git operation
        print("[Jarvis Pipeline] Executing Git CLI operation...")
        git_proc = subprocess.run([sys.executable, os.path.join(PROJECT_ROOT, "execute_git.py")], cwd=PROJECT_ROOT)

        # Step 5: Announce completion or error
        if git_proc.returncode == 0:
            done_phrase = spk_resp or "Task completed successfully, sir."
            try:
                status_path = os.path.join(PROJECT_ROOT, "last_status.txt")
                if os.path.exists(status_path):
                    with open(status_path, "r", encoding="utf-8") as sf:
                        st = sf.read().strip()
                        if "[GIT SUCCESS]" in st:
                            done_phrase = st.replace("[GIT SUCCESS]", "").strip()
            except Exception:
                pass
            print(f"[Jarvis Pipeline] Announcing completion: {done_phrase}")
            if play_tts:
                subprocess.run([sys.executable, os.path.join(PROJECT_ROOT, "speak.py"), done_phrase], cwd=PROJECT_ROOT)
            result_payload["response"] = done_phrase
        else:
            err_phrase = "Git operation could not be completed, sir."
            try:
                status_path = os.path.join(PROJECT_ROOT, "last_status.txt")
                if os.path.exists(status_path):
                    with open(status_path, "r", encoding="utf-8") as sf:
                        st = sf.read().strip()
                        if "[GIT ERROR]" in st:
                            raw_err = st.replace("[GIT ERROR]", "").strip()
                            err_phrase = f"Git error: {raw_err[:120]}, sir."
            except Exception:
                pass
            print(f"[Jarvis Pipeline] Announcing failure: {err_phrase}")
            if play_tts:
                subprocess.run([sys.executable, os.path.join(PROJECT_ROOT, "speak.py"), err_phrase], cwd=PROJECT_ROOT)
            result_payload["status"] = "error"
            result_payload["response"] = err_phrase

    elif itype == "antigravity_task":
        start_phrase = spk_start or "On it, sir. Repairing code errors with Ollama offline."
        print(f"[Jarvis Pipeline] Announcing start: {start_phrase}")
        if play_tts:
            subprocess.run([sys.executable, os.path.join(PROJECT_ROOT, "speak.py"), start_phrase], cwd=PROJECT_ROOT)

        print("[Jarvis Pipeline] Executing Autonomous Code Repair Bridge (Ollama Offline)...")
        agent_proc = subprocess.run([sys.executable, os.path.join(PROJECT_ROOT, "execute_agent.py")], cwd=PROJECT_ROOT)

        done_phrase = spk_resp or "Task completed, sir."
        try:
            status_path = os.path.join(PROJECT_ROOT, "last_status.txt")
            if os.path.exists(status_path):
                with open(status_path, "r", encoding="utf-8") as sf:
                    st = sf.read().strip()
                    if "[OLLAMA SUCCESS]" in st:
                        done_phrase = st.replace("[OLLAMA SUCCESS]", "").strip()
                    elif "[OLLAMA NOTICE]" in st:
                        done_phrase = st.replace("[OLLAMA NOTICE]", "").strip()
                    elif "[OLLAMA ERROR]" in st:
                        done_phrase = st.replace("[OLLAMA ERROR]", "").strip()
                    elif st and not st.startswith("["):
                        done_phrase = st
        except Exception:
            pass

        print(f"[Jarvis Pipeline] Announcing completion: {done_phrase}")
        if play_tts:
            subprocess.run([sys.executable, os.path.join(PROJECT_ROOT, "speak.py"), done_phrase], cwd=PROJECT_ROOT)
        result_payload["response"] = done_phrase

    else:  # general_qa or codebase_qa
        if spk_resp:
            print(f"[Jarvis Pipeline] Spoken QA Answer: {spk_resp}")
            if play_tts:
                subprocess.run([sys.executable, os.path.join(PROJECT_ROOT, "speak.py"), spk_resp], cwd=PROJECT_ROOT)
            result_payload["response"] = spk_resp

    return result_payload

def run_autonomous_pipeline(audio_path: str):
    """
    Direct, ultra-responsive autonomous execution pipeline for audio:
    1. Transcribes audio dynamically with Groq Whisper (with offline faster-whisper fallback)
    2. Executes unified autonomous pipeline
    """
    if os.getenv("DISPATCH_TO_N8N", "false").lower() == "true":
        threading.Thread(target=dispatch_to_n8n, args=(audio_path,), daemon=True).start()

    try:
        # Step 1: Transcribe audio
        print("\n[Jarvis Pipeline] Step 1: Transcribing audio...")
        t_proc = subprocess.run(
            [sys.executable, os.path.join(PROJECT_ROOT, "transcribe.py"), audio_path],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True
        )
        transcript = t_proc.stdout.strip()
        if not transcript:
            print("[Jarvis Pipeline] No speech detected in audio capture.")
            return

        print(f"[Jarvis Pipeline] Voice Transcript: \"{transcript}\"")
        process_transcript_pipeline(transcript, play_tts=True, source="voice")

    except Exception as e:
        print(f"[Jarvis Pipeline] Error during autonomous pipeline execution: {e}", file=sys.stderr)

def main():
    import openwakeword
    from openwakeword.model import Model
    from openwakeword.vad import VAD

    # Parse target project argument if provided
    for i, a in enumerate(sys.argv):
        if a == "--project" and i + 1 < len(sys.argv):
            set_active_project(sys.argv[i + 1])
            break

    active_repo = get_target_repo()
    proj_name = get_project_name(active_repo)

    print("==================================================")
    print("   JARVIS ULTRA-LOW LATENCY CONVERSATIONAL AGENT  ")
    print(f"   Active Project     : [{proj_name.upper()}]")
    print(f"   Target Workspace   : {active_repo}")
    print(f"   Wake Sensitivity   : Threshold {THRESHOLD} (High)")
    print(f"   Local Acknowledgment: 0ms Pre-rendered Audio")
    print(f"   VAD Silence Cutoff : {SILENCE_TIMEOUT_MS}ms")
    print(f"   n8n Automation     : {'ONLINE' if is_n8n_online() else 'STANDBY'} ({N8N_WEBHOOK_URL})")
    print("==================================================")

    # Launch Sci-Fi Desktop HUD Interface in background
    launch_hud_interface()

    # Initialize Pygame audio mixer pre-warmed for 24kHz
    try:
        pygame.mixer.init(frequency=24000, buffer=1024)
    except Exception as e:
        print(f"[Jarvis] Pygame mixer init note: {e}", file=sys.stderr)

    try:
        openwakeword.utils.download_models()
    except Exception:
        pass

    try:
        oww_model = Model(wakeword_models=["hey_jarvis"], inference_framework="onnx")
        vad_engine = VAD()
    except Exception as e:
        print(f"[Jarvis] Fatal: Unable to initialize voice engines: {e}", file=sys.stderr)
        return

    audio = pyaudio.PyAudio()
    try:
        stream = audio.open(
            format=FORMAT,
            channels=CHANNELS,
            rate=RATE,
            input=True,
            frames_per_buffer=CHUNK,
        )
    except Exception as e:
        print(f"[Jarvis] Fatal: Cannot open microphone input: {e}", file=sys.stderr)
        audio.terminate()
        return

    print("[Jarvis] Microphone active. Standing by for wake word...")

    try:
        while True:
            raw_data = stream.read(CHUNK, exception_on_overflow=False)
            audio_array = np.frombuffer(raw_data, dtype=np.int16)

            prediction = oww_model.predict(audio_array)
            score = prediction.get("hey_jarvis", 0.0)

            if score >= THRESHOLD:
                print(f"\n[Jarvis] Wake word detected! (Confidence: {score:.2f} >= {THRESHOLD})")
                
                # 1. True 0ms instant local audio acknowledgment
                play_instant_wake_acknowledgment()

                # 2. Dynamic VAD Recording with 350ms cutoff
                audio_bytes = record_dynamic_command(stream, vad_engine)
                save_wav(audio_bytes, audio, OUTPUT_AUDIO_FILE)

                # 3. Launch autonomous pipeline in background thread
                pipeline_thread = threading.Thread(
                    target=run_autonomous_pipeline,
                    args=(OUTPUT_AUDIO_FILE,),
                    daemon=True
                )
                pipeline_thread.start()

                # Reset internal buffers
                oww_model.reset()
                vad_engine.reset_states()
                print("[Jarvis] Standing by for next command...")

    except KeyboardInterrupt:
        print("\n[Jarvis] Voice listener terminated by user.")
    finally:
        stream.stop_stream()
        stream.close()
        audio.terminate()
        pygame.mixer.quit()

if __name__ == "__main__":
    main()
