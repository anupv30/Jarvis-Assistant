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
import pyaudio
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
FORMAT = pyaudio.paInt16
CHANNELS = 1

# VAD Parameters
SILENCE_TIMEOUT_MS = 350  # 350ms silence cutoff
MIN_SPEECH_CHUNKS = 3     # ~240ms minimum speech
MAX_RECORDING_SEC = 10    # Safety cap
VAD_SPEECH_THRESHOLD = 0.35
RMS_ENERGY_THRESHOLD = 250.0

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

def record_dynamic_command(stream: pyaudio.Stream, vad_engine) -> bytes:
    """Dynamically records microphone audio until 350ms of trailing silence."""
    print("[Jarvis] Streaming audio: dynamic VAD active (350ms silence cutoff)...")
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

        if is_speech:
            has_spoken = True
            speech_chunks_count += 1
            silence_duration_ms = 0
        else:
            if has_spoken and speech_chunks_count >= MIN_SPEECH_CHUNKS:
                silence_duration_ms += 80
                if silence_duration_ms >= SILENCE_TIMEOUT_MS:
                    print(f"[Jarvis] End-of-speech detected ({silence_duration_ms}ms silence). Stopping capture.")
                    break

        if time.time() - start_time > MAX_RECORDING_SEC:
            print("[Jarvis] Maximum recording safety timeout reached.")
            break

    return b"".join(frames)

def save_wav(raw_bytes: bytes, audio: pyaudio.PyAudio, filepath: str):
    with wave.open(filepath, "wb") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(audio.get_sample_size(FORMAT))
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

def run_autonomous_pipeline(audio_path: str):
    """
    Direct, ultra-responsive autonomous execution pipeline:
    1. Transcribes audio dynamically with Groq Whisper -> writes to last_transcript.txt (HUD updates immediately!)
    2. Routes intent dynamically with Groq LLM -> writes to last_intent.json
    3. Speaks task acknowledgment (e.g. "On it, sir. Committing and pushing changes...")
    4. Executes validated action (Git command / Antigravity task)
    5. Speaks completion announcement (e.g. "Task completed successfully, sir." / direct spoken answer)
    """
    # Avoid duplicate execution: the local autonomous pipeline handles the entire lifecycle
    if os.getenv("DISPATCH_TO_N8N", "false").lower() == "true":
        threading.Thread(target=dispatch_to_n8n, args=(audio_path,), daemon=True).start()

    try:
        # Step 1: Transcribe audio
        print("\n[Jarvis Pipeline] Step 1: Transcribing audio with Groq Whisper...")
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
        transcript_file = os.path.join(PROJECT_ROOT, "last_transcript.txt")
        try:
            with open(transcript_file, "w", encoding="utf-8") as f:
                f.write(transcript)
        except Exception:
            pass

        # Step 2: Route intent dynamically with Groq LLM
        print("[Jarvis Pipeline] Step 2: Routing intent with Groq LLM...")
        subprocess.run(
            [sys.executable, os.path.join(PROJECT_ROOT, "intent_router.py")],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True
        )

        intent_file = os.path.join(PROJECT_ROOT, "last_intent.json")
        if not os.path.exists(intent_file):
            print("[Jarvis Pipeline] Error: last_intent.json not found.", file=sys.stderr)
            return

        with open(intent_file, "r", encoding="utf-8") as f:
            intent = json.load(f)

        itype = intent.get("type", "general_qa")
        spk_start = intent.get("speaking_start", "")
        spk_resp = intent.get("speaking_response", "")

        # Step 3: Handle Action vs QA
        if itype == "git_query":
            answer = spk_resp or "Checking git status, sir."
            print(f"[Jarvis Pipeline] Speaking answer: {answer}")
            subprocess.run([sys.executable, os.path.join(PROJECT_ROOT, "speak.py"), answer], cwd=PROJECT_ROOT)

        elif itype == "git_action":
            # Acknowledge task start: "On it, sir..."
            start_phrase = spk_start or "On it, sir. Committing and pushing your changes."
            print(f"[Jarvis Pipeline] Announcing start: {start_phrase}")
            subprocess.run([sys.executable, os.path.join(PROJECT_ROOT, "speak.py"), start_phrase], cwd=PROJECT_ROOT)

            # Step 4: Execute Git operation
            print("[Jarvis Pipeline] Step 3: Executing Git CLI operation...")
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
                subprocess.run([sys.executable, os.path.join(PROJECT_ROOT, "speak.py"), done_phrase], cwd=PROJECT_ROOT)
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
                subprocess.run([sys.executable, os.path.join(PROJECT_ROOT, "speak.py"), err_phrase], cwd=PROJECT_ROOT)

        elif itype == "antigravity_task":
            start_phrase = spk_start or "On it, sir. Delegating task to Antigravity Agent."
            print(f"[Jarvis Pipeline] Announcing start: {start_phrase}")
            subprocess.run([sys.executable, os.path.join(PROJECT_ROOT, "speak.py"), start_phrase], cwd=PROJECT_ROOT)

            print("[Jarvis Pipeline] Step 3: Executing Antigravity Agent Bridge...")
            subprocess.run([sys.executable, os.path.join(PROJECT_ROOT, "execute_agent.py")], cwd=PROJECT_ROOT)

            done_phrase = spk_resp or "Task completed, sir."
            print(f"[Jarvis Pipeline] Announcing completion: {done_phrase}")
            subprocess.run([sys.executable, os.path.join(PROJECT_ROOT, "speak.py"), done_phrase], cwd=PROJECT_ROOT)

        else:  # general_qa or codebase_qa
            if spk_resp:
                print(f"[Jarvis Pipeline] Spoken QA Answer: {spk_resp}")
                subprocess.run([sys.executable, os.path.join(PROJECT_ROOT, "speak.py"), spk_resp], cwd=PROJECT_ROOT)

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
