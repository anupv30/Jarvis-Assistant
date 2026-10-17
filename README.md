# Jarvis - Real-Time Codebase Assistant & Voice Git Automation

Zero-cost, local, zero-latency voice assistant that handles **Codebase Q&A, Git/GitHub CLI operations, and general conversational AI queries** using **openWakeWord** (Sensitivity: 0.20), **0ms Local Wake Acknowledgment**, **Silero VAD** (350ms silence cutoff), **Groq Whisper (`whisper-large-v3-turbo`)**, **Groq LLM (`llama-3.3-70b-versatile` with cached codebase context)**, **Neural AI TTS (`edge-tts` with `en-US-ChristopherNeural`)**, and **n8n**.

---

## Conversational Voice Architecture

```mermaid
sequenceDiagram
    autonumber
    actor User
    participant Mic as Microphone
    participant Listener as jarvis_listener.py (Silero VAD)
    participant LocalAudio as on_it.mp3 (0ms Local Playback)
    participant n8n as n8n Webhook Pipeline
    participant ASR as transcribe.py (Groq Whisper)
    participant Router as intent_router.py (Groq / Ollama + Codebase Cache)
    participant Speak as speak.py (Neural AI TTS)
    participant Exec as execute_git.py (Git / gh CLI)

    User->>Mic: "Hey Jarvis"
    Mic->>Listener: Audio Stream (16kHz PCM)
    Listener->>LocalAudio: Direct pygame.mixer play (0ms, no network delay)
    LocalAudio-->>User: Spoken Response: "On it, sir."
    User->>Mic: Speaks query (e.g., "Explain how speak.py works", "Check git status", "What is standard deviation?")
    Note over Listener: Silero VAD monitors speech.<br/>Stops immediately after >=350ms silence.
    Listener->>n8n: POST multipart/form-data to /webhook/jarvis-git
    n8n->>ASR: cd "..." && python transcribe.py recorded_command.wav
    ASR-->>n8n: Sub-100ms Transcript
    n8n->>Router: cd "..." && python intent_router.py
    Note over Router: Injects cached codebase digest.<br/>Routes: codebase_qa | general_qa | git_action
    alt Codebase or General Q&A (e.g., "Explain how speak.py works")
        Router-->>n8n: type: codebase_qa / general_qa, speaking_response: "<concise answer>"
        n8n->>Speak: cd "..." && python speak.py --intent-response
        Speak-->>User: Neural Spoken Answer: "<2-3 sentence answer based on codebase>"
    else Git Action (e.g., "Push all my changes")
        Router-->>n8n: type: git_action, speaking_start, command, speaking_response
        n8n->>Speak: cd "..." && python speak.py --intent-start
        Speak-->>User: Neural Announcement: "Executing task: committing and pushing changes, sir."
        n8n->>Exec: cd "..." && python execute_git.py
        n8n->>Speak: cd "..." && python speak.py --intent-response
        Speak-->>User: Neural Response: "Task completed successfully, sir."
    end
```

---

## Component Architecture

1. [`jarvis_listener.py`](jarvis_listener.py):
   - **0ms Instant Wake Acknowledgment**: Plays pre-rendered `on_it.mp3` directly via `pygame.mixer` inside the listener process.
   - **Dynamic Silero VAD**: Automatically stops recording within 350ms of trailing silence.
   - **Multipart Webhook Dispatch**: Posts to `http://localhost:5678/webhook/jarvis-git`.
2. [`intent_router.py`](intent_router.py):
   - **Codebase Context Scanner**: Crawls and caches key files (`.py`, `.bat`, `.json`, `.md`) with a 120s TTL cache.
   - **Tri-Mode Classifier**: Distinguishes `codebase_qa` vs `git_action` vs `general_qa`.
   - **Fast Voice Responses**: Enforces `max_tokens: 150` for crisp, natural 2–3 sentence spoken answers.
3. [`speak.py`](speak.py):
   - Pre-rendered static clips: `on_it.mp3` and `listening.mp3`.
   - Pre-warmed 24kHz `pygame.mixer` player for sub-50ms dynamic playback.
   - Reuses single `temp_speech.mp3` cache file.
4. [`execute_git.py`](execute_git.py):
   - Injects GitHub CLI into PATH.
   - Automatically bypasses Git execution for Q&A queries.
5. [`workflows/jarvis_workflow.json`](workflows/jarvis_workflow.json):
   - 9-node workflow with conditional IF node branching Git actions vs direct Q&A speech routing.

---

## Global CLI & Multi-Project Support

Jarvis can be initialized and run in **any project folder or workspace** inside Antigravity IDE:

```powershell
# Initialize Jarvis in the current folder (or pass a target directory):
# - Verifies/initializes Git repository
# - Scaffolds .jarvis/config.json and local batch shortcuts
# - Verifies background n8n server (starts it automatically if stopped)
# - Opens the Cybernetic Sci-Fi HUD desktop window for that project
jarvis init [project_path]

# Start both HUD and Voice Listener for the active project
jarvis start [project_path]

# Open just the Cybernetic Sci-Fi HUD window
jarvis hud [project_path]

# Check background n8n automation status
jarvis n8n

# Check current active project, Git branch, and pipeline telemetry
jarvis status
```

### Running Locally inside Core Repository

```powershell
# 1. Start n8n Workflow Server in background
.\start_n8n.bat

# 2. Launch Cybernetic HUD Window
.\start_hud.bat

# 3. Start Zero-Latency Voice Listener
.\start_jarvis.bat
```
