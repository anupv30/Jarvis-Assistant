#!/usr/bin/env python3
"""
Jarvis Low-Latency Codebase & Conversational AI Router
Features:
- Fast cached repository file crawler: `get_project_context()` with 120s TTL cache.
- Concise architectural digest keeps Groq prompt under 800 tokens for sub-200ms responses.
- Tri-mode routing: `codebase_qa` | `git_action` | `general_qa`.
- Output Schema:
  {
    "type": "codebase_qa" | "git_action" | "general_qa",
    "command": "<cli_command_if_git>",
    "speaking_start": "<task_description_if_git>",
    "speaking_response": "<direct_concise_spoken_answer_for_qa_or_completion>"
  }
"""

import sys
import os
import json
import re
import time
import subprocess
import requests
from dotenv import load_dotenv

# Load configuration
load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "").strip()

from jarvis_config import (
    JARVIS_CORE_DIR,
    get_target_repo,
    get_project_name,
    get_current_git_branch,
    is_n8n_online,
)

PROJECT_ROOT = JARVIS_CORE_DIR
TRANSCRIPT_CACHE_FILE = os.path.join(JARVIS_CORE_DIR, "last_transcript.txt")
INTENT_CACHE_FILE = os.path.join(JARVIS_CORE_DIR, "last_intent.json")
STATUS_CACHE_FILE = os.path.join(JARVIS_CORE_DIR, "last_status.txt")
CODEBASE_CACHE_FILE = os.path.join(JARVIS_CORE_DIR, "codebase_cache.json")
ANTIGRAVITY_TASK_FILE = os.path.join(JARVIS_CORE_DIR, "antigravity_task.json")
ANTIGRAVITY_PROMPT_FILE = os.path.join(JARVIS_CORE_DIR, "antigravity_prompt.txt")
PENDING_ACTION_FILE = os.path.join(JARVIS_CORE_DIR, "pending_action.json")

def get_project_context(force_refresh: bool = False) -> str:
    """Scans and caches key project source files to answer codebase questions with zero delay."""
    target_repo = get_target_repo()
    cache_file = os.path.join(target_repo, ".jarvis", "codebase_cache.json") if target_repo != JARVIS_CORE_DIR else CODEBASE_CACHE_FILE

    if not force_refresh and os.path.exists(cache_file):
        try:
            mtime = os.path.getmtime(cache_file)
            if time.time() - mtime < 120:
                with open(cache_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    cached_text = data.get("context", "")
                    if cached_text:
                        return cached_text
        except Exception:
            pass

    context_parts = []
    if target_repo != JARVIS_CORE_DIR:
        candidate_files = []
        for root, dirs, files in os.walk(target_repo):
            dirs[:] = [d for d in dirs if d not in [".git", "node_modules", "venv", ".venv", "__pycache__", ".jarvis"]]
            for file in files:
                ext = os.path.splitext(file)[1].lower()
                if ext in [".py", ".js", ".ts", ".jsx", ".tsx", ".html", ".css", ".json", ".md", ".txt", ".go", ".rs"]:
                    full_p = os.path.join(root, file)
                    rel_p = os.path.relpath(full_p, target_repo)
                    candidate_files.append((rel_p, full_p))
                    if len(candidate_files) >= 12:
                        break
            if len(candidate_files) >= 12:
                break

        for relpath, filepath in candidate_files:
            try:
                with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                    lines = f.readlines()
                snippet = "".join(lines[:25]).strip()
                context_parts.append(f"[{relpath}]\n{snippet}\n")
            except Exception:
                continue
    else:
        core_files = [
            "jarvis_listener.py",
            "speak.py",
            "transcribe.py",
            "intent_router.py",
            "execute_git.py",
            "workflows/jarvis_workflow.json",
            "README.md",
        ]
        for relpath in core_files:
            filepath = os.path.join(JARVIS_CORE_DIR, relpath)
            if os.path.exists(filepath):
                try:
                    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                        lines = f.readlines()
                    snippet = "".join(lines[:25]).strip()
                    context_parts.append(f"[{relpath}]\n{snippet}\n")
                except Exception:
                    continue

    summary = "\n".join(context_parts)
    try:
        os.makedirs(os.path.dirname(cache_file), exist_ok=True)
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump({"context": summary, "timestamp": time.time()}, f)
    except Exception:
        pass

    return summary

ANTIGRAVITY_TRIGGER_KEYWORDS = [
    "bug fix", "fix bug", "code changes", "create app", "modify hud", "theme", "antigravity",
    "solve", "bug", "fix", "error", "repair", "broken", "issue", "crash",
    "generate", "create script", "write script", "make script", "build script",
    "refactor", "patch", "modify code", "edit code", "new feature", "add feature", "implement",
    "ui change", "dark mode"
]

def sync_to_clipboard(text: str) -> bool:
    """Syncs formatted text to Windows clipboard using pyperclip and clip.exe."""
    try:
        from antigravity_bridge import sync_to_clipboard as bridge_sync
        return bridge_sync(text)
    except Exception:
        try:
            proc = subprocess.Popen(["clip"], stdin=subprocess.PIPE, shell=True)
            proc.communicate(input=text.encode("utf-8"))
            print("[intent_router.py] Formatted prompt synchronized to Windows clipboard.", file=sys.stderr)
            return True
        except Exception as e:
            print(f"[intent_router.py] Clipboard sync error: {e}", file=sys.stderr)
            return False

def is_antigravity_intent(transcript: str) -> bool:
    """Detects whether transcript requires Antigravity code generation, bug fixing, or HUD styling."""
    t = transcript.lower()
    # Explicit exclusions: Git queries, branch operations, commits, pushes are NEVER Antigravity
    if is_git_query(transcript) or is_branch_creation(transcript) or is_branch_deletion(transcript):
        return False
    if any(w in t for w in ["branch", "commit", "push", "git status", "git log", "git remote", "repo"]):
        if "antigravity" not in t:
            return False

    # Explicit regex patterns for critical trigger phrases
    patterns = [
        r'\bbug\s*fix\b',
        r'\bfix\s*bug\b',
        r'\bcode\s*changes?\b',
        r'\bcreate\s*app\b',
        r'\bmodify\s*hud\b',
        r'\btheme\b',
        r'\bantigravity\b',
    ]
    for p in patterns:
        if re.search(p, t):
            return True
    return any(w in t for w in ANTIGRAVITY_TRIGGER_KEYWORDS)

def load_pending_action() -> dict | None:
    """Reads pending confirmation action if not expired (45s TTL)."""
    if not os.path.exists(PENDING_ACTION_FILE):
        return None
    try:
        with open(PENDING_ACTION_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if time.time() <= data.get("expires_at", 0):
            return data
        os.remove(PENDING_ACTION_FILE)
    except Exception:
        pass
    return None

def save_pending_action(action_data: dict):
    """Saves a pending action requiring confirmation with 45s expiration."""
    action_data["created_at"] = time.time()
    action_data["expires_at"] = time.time() + 45
    try:
        with open(PENDING_ACTION_FILE, "w", encoding="utf-8") as f:
            json.dump(action_data, f, indent=2)
    except Exception as e:
        print(f"[intent_router.py] Warning: Could not save pending action: {e}", file=sys.stderr)

def clear_pending_action():
    """Clears any pending confirmation action."""
    if os.path.exists(PENDING_ACTION_FILE):
        try:
            os.remove(PENDING_ACTION_FILE)
        except Exception:
            pass

def is_confirmation_yes(transcript: str) -> bool:
    """Detects affirmative confirmation to proceed with pending destructive action."""
    t = transcript.lower().strip().rstrip(".!?,")
    yes_exact = [
        "yes", "yeah", "yep", "sure", "confirm", "proceed", "go ahead",
        "do it", "authorize", "approved", "affirmative", "yes please",
        "yes confirm", "yes do it", "yes delete it", "yes proceed", "i confirm"
    ]
    if t in yes_exact:
        return True
    return any(t.startswith(w) for w in ["yes", "confirm", "proceed", "authorize", "go ahead"])

def is_confirmation_no(transcript: str) -> bool:
    """Detects negative response or cancellation of pending action."""
    t = transcript.lower().strip().rstrip(".!?,")
    no_exact = [
        "no", "nope", "cancel", "stop", "abort", "nevermind",
        "negative", "don't", "dont", "do not", "no cancel", "no don't"
    ]
    if t in no_exact:
        return True
    return any(t.startswith(w) for w in ["no", "cancel", "stop", "abort", "nevermind", "don't", "dont"])

def create_branch_safety_snapshot(target_repo: str, branch_name: str) -> str:
    """Creates a safety backup git tag for a branch before deletion."""
    clean_b = branch_name.strip(".-/ \t\r\n")
    tag_name = f"safety_backup_{clean_b.replace('/', '_')}"
    try:
        subprocess.run(["git", "tag", "-f", tag_name, clean_b], cwd=target_repo, capture_output=True)
        return tag_name
    except Exception:
        return ""

def is_restore_backup_intent(transcript: str) -> bool:
    """Detects intent to restore a branch from safety snapshot."""
    t = transcript.lower()
    return any(k in t for k in [
        "restore deleted branch", "recover deleted branch", "undo branch deletion",
        "restore branch", "recover branch", "restore from safety backup", "restore from backup",
        "undo deletion", "restore the branch"
    ])

def handle_safety_restore_intent(transcript: str) -> dict:
    """Restores a branch from the latest or specified safety snapshot."""
    target_repo = get_target_repo()
    cd_prefix = f'cd "{target_repo}"'
    tags_proc = subprocess.run(["git", "tag", "-l", "safety_backup_*"], cwd=target_repo, capture_output=True, text=True)
    tags = [t.strip() for t in tags_proc.stdout.splitlines() if t.strip()]
    if not tags:
        return {
            "type": "git_query",
            "action": "",
            "target_file": "",
            "task_description": "Safety backup restore check",
            "command": "git status --short",
            "speaking_start": "",
            "speaking_progress": "",
            "speaking_response": "No safety backup snapshots found in this repository, sir.",
        }
    t_lower = transcript.lower()
    selected_tag = None
    target_bname = None
    for tag in reversed(tags):
        b_cand = tag.replace("safety_backup_", "")
        if b_cand in t_lower:
            selected_tag = tag
            target_bname = b_cand
            break
    if not selected_tag:
        selected_tag = tags[-1]
        target_bname = selected_tag.replace("safety_backup_", "")

    cmd = f'{cd_prefix} && (git checkout -b {target_bname} {selected_tag} 2>nul || git checkout {target_bname}) && git push -u origin {target_bname}'
    return {
        "type": "git_action",
        "action": "restore_safety_backup",
        "target_file": "",
        "task_description": f"Restore branch {target_bname} from safety snapshot {selected_tag}",
        "command": cmd,
        "speaking_start": f"Restoring branch {target_bname} from safety backup snapshot, sir.",
        "speaking_progress": "",
        "speaking_response": f"Branch {target_bname} has been successfully restored from your safety snapshot and synced to GitHub, sir.",
    }

def is_revert_action(transcript: str) -> bool:
    """Detects command to execute git revert (action), not a question about history."""
    t = transcript.lower().strip()
    if any(q in t for q in ["what was", "what is", "tell me", "show me", "which was", "how many", "did we", "who reverted"]):
        return False
    return any(k in t for k in [
        "revert the last commit", "revert last commit", "revert the commit", "revert commit",
        "revert the committed changes", "revert committed changes", "revert changes",
        "undo the last commit", "undo last commit", "undo the commit", "undo commit",
        "rollback the last commit", "rollback last commit", "rollback commit"
    ]) or bool(re.search(r'^(?:please\s+|jarvis\s+)?(?:revert|undo|rollback)\b', t))

def is_discard_intent(transcript: str) -> bool:
    """Detects command to discard uncommitted working tree changes."""
    t = transcript.lower()
    return any(k in t for k in [
        "discard uncommitted", "discard changes", "discard local changes",
        "undo uncommitted", "reset uncommitted", "wipe uncommitted",
        "clean working tree", "revert uncommitted", "restore modified files",
        "discard my changes"
    ])

def is_git_query(transcript: str) -> bool:
    """Detects informational git questions (NOT action commands).
    Examples: 'what branch am I on?', 'which branch am I in?', 'show me git status'
    """
    if (is_revert_action(transcript) or is_discard_intent(transcript) or
        is_confirmation_yes(transcript) or is_confirmation_no(transcript) or
        is_restore_backup_intent(transcript)):
        return False
    t = transcript.lower()
    # Question patterns about git state
    query_patterns = [
        r'\b(?:what|which|show|tell|current|check|display)\b.*\bbranch\b',
        r'\bbranch\b.*\b(?:am i|are we|currently|right now|on|in)\b',
        r'\b(?:what|which|show)\b.*\b(?:status|log|remote|diff|changes)\b',
        r'\b(?:am i on|are we on)\b.*\bbranch\b',
        r'\b(?:show|list|display)\b.*\b(?:branches|remotes|tags)\b',
        r'\b(?:what|which|show|tell|check|who)\b.*\b(?:commit|committed|revert|reverted)\b',
        r'\b(?:last|latest|recent|previous)\b.*\b(?:commit|committed|revert|reverted|change|changes|one)\b',
        r'\bwhat\s+(?:did\s+i|was)\s+(?:commit|revert|changed)\b',
        r'\b(?:what was the last|what is the last|tell me the last|show the last)\b',
    ]
    for p in query_patterns:
        if re.search(p, t):
            return True
    return False

def is_branch_deletion(transcript: str) -> bool:
    """Detects git branch deletion requests."""
    t = transcript.lower()
    if is_git_query(transcript):
        return False
    patterns = [
        r'\b(?:delete|remove|drop|destroy)\s+.*?\bbranch\b',
        r'\bbranch\s+.*?\b(?:delete|deletion|remove|removal|drop|destroy)\b',
    ]
    return any(bool(re.search(p, t)) for p in patterns)

def is_branch_creation(transcript: str) -> bool:
    """Detects git branch creation requests. Excludes query/question and deletion patterns."""
    t = transcript.lower()
    # First, exclude any question or deletion patterns
    if is_git_query(transcript) or is_branch_deletion(transcript):
        return False
    patterns = [
        r'\b(?:create|make|checkout\s+-b|new)\s+.*?\bbranch\b',
        r'\bbranch\s+.*?\b(?:create|creation|make|new)\b',
        r'\bbranch\s+(?:called|named)\b',
    ]
    return any(bool(re.search(p, t)) for p in patterns)

def extract_branch_name(transcript: str) -> str:
    """Extracts and sanitizes git branch name from user speech.
    e.g. 'create a branch called jarvis test' -> 'jarvis-test'
         'delete branch jarvis-test' -> 'jarvis-test'
         'can you delete test branch' -> 'test'
         'create branch feature' -> 'feature'
    """
    t = transcript.strip()
    raw = ""
    # Check deletion commands first: 'delete branch <name>' or 'delete <name> branch'
    m_del = re.search(r'(?:delete|remove|drop|destroy)\s+(?:the\s+)?(?:a\s+)?branch\s+(?:called\s+|named\s+)?([a-zA-Z0-9_\-\.\/\s]+)', t, re.IGNORECASE)
    if m_del:
        raw = m_del.group(1).strip()
    if not raw:
        m_del_rev = re.search(r'(?:delete|remove|drop|destroy)\s+(?:the\s+)?(?:a\s+)?([a-zA-Z0-9_\-\.\/]+)\s+branch', t, re.IGNORECASE)
        if m_del_rev:
            cand = m_del_rev.group(1).strip()
            if cand.lower() not in ["the", "a", "this", "that"]:
                raw = cand
    if not raw:
        m = re.search(r'branch\s+(?:called|named|as)\s+([a-zA-Z0-9_\-\.\/\s]+)', t, re.IGNORECASE)
        if m:
            raw = m.group(1).strip()
    if not raw:
        m2 = re.search(r'(?:create|make|checkout|switch to|new)\s+(?:a\s+)?branch\s+([a-zA-Z0-9_\-\.\/\s]+)', t, re.IGNORECASE)
        if m2:
            raw = m2.group(1).strip()
    if not raw:
        m_create_rev = re.search(r'(?:create|make|checkout|new)\s+(?:the\s+)?(?:a\s+)?([a-zA-Z0-9_\-\.\/]+)\s+branch', t, re.IGNORECASE)
        if m_create_rev:
            cand = m_create_rev.group(1).strip()
            if cand.lower() not in ["the", "a", "this", "that", "new"]:
                raw = cand
    if not raw:
        m3 = re.search(r'(?:called|named)\s+([a-zA-Z0-9_\-\.\/\s]+)', t, re.IGNORECASE)
        if m3:
            raw = m3.group(1).strip()
    if not raw:
        raw = "feature-branch"

    # Clean trailing conversational filler words
    raw = re.sub(r'\b(?:please|sir|in|and|push|to github|now|for me|from github)\b.*$', '', raw, flags=re.IGNORECASE).strip()
    # Strip trailing punctuation (e.g. Whisper sentence-ending periods)
    raw = raw.rstrip('.!?,;: ')
    # Replace spaces with hyphens (valid git branch naming)
    sanitized = re.sub(r'\s+', '-', raw)
    # Remove any characters illegal in git branch names
    sanitized = re.sub(r'[^a-zA-Z0-9_\-\.\/]', '', sanitized).lower()
    # Strip leading/trailing dots, slashes, and hyphens (strictly illegal in Git ref format)
    sanitized = sanitized.strip('.-/')
    sanitized = re.sub(r'\.{2,}', '.', sanitized)
    sanitized = re.sub(r'/{2,}', '/', sanitized)
    return sanitized if sanitized else "feature-branch"

def check_python_syntax(filepath: str) -> tuple[bool, str, int | None, str]:
    """Runs comprehensive AST, compilation, and runtime diagnostics."""
    if not filepath or not os.path.exists(filepath):
        return True, "File does not exist yet", None, ""

    try:
        from execute_agent import diagnose_file
        valid, diag_msg, line_num = diagnose_file(filepath)
        return valid, diag_msg, line_num, diag_msg
    except Exception:
        pass

    try:
        proc = subprocess.run(
            [sys.executable, "-m", "py_compile", filepath],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True
        )
        if proc.returncode == 0:
            return True, "Syntax check passed. No compilation errors found.", None, ""

        err_output = (proc.stderr or proc.stdout or "").strip()
        line_num = None
        m = re.search(r'line\s+(\d+)', err_output, re.IGNORECASE)
        if m:
            line_num = int(m.group(1))

        lines = [l.strip() for l in err_output.splitlines() if l.strip()]
        error_line = lines[-1] if lines else "SyntaxError: compilation failure"
        return False, err_output, line_num, error_line
    except Exception as e:
        return False, str(e), None, str(e)

def extract_target_file(transcript: str) -> str:
    """Extracts target python filename from transcript or returns empty string for project-wide repair."""
    t = transcript.lower()

    # If transcript is generic (e.g. "in the project", "in the program", "all errors", "any errors"), return empty string for full project scan
    if any(phrase in t for phrase in ["in the project", "in the program", "in project", "in program", "across the project", "all errors", "any errors", "the project", "the program", "in the code"]):
        return ""

    # 1. Direct regex for filename.py
    m = re.search(r'([a-zA-Z0-9_\-]+\.py)', transcript, re.IGNORECASE)
    if m:
        return m.group(1).lower()

    # 2. Phonetic "filename dot py" or "filename pi"
    m_phonetic = re.search(r'([a-zA-Z0-9_\-]+)\s+(?:dot|\.)\s*(?:py|pi)\b', transcript, re.IGNORECASE)
    if m_phonetic:
        return f"{m_phonetic.group(1).lower()}.py"

    target_repo = get_target_repo()

    # 3. Match any existing .py file in target_repo if its base name specifically appears in speech (e.g. "fix multiply")
    try:
        if os.path.exists(target_repo):
            for f in os.listdir(target_repo):
                if f.endswith(".py"):
                    base = os.path.splitext(f)[0].lower()
                    if len(base) > 2 and re.search(r'\b' + re.escape(base) + r'\b', t):
                        return f
    except Exception:
        pass

    known_files = [
        "jarvis_listener", "speak", "transcribe", "intent_router",
        "jarvis_hud", "execute_git", "execute_agent", "start_hud", "start_jarvis"
    ]
    for kf in known_files:
        if re.search(r'\b' + re.escape(kf) + r'\b', t):
            return f"{kf}.py"

    if any(w in t for w in ["hud", "gui", "theme", "dashboard"]):
        return "jarvis_hud.py"

    if any(w in t for w in ["generate", "create", "write", "build", "new script", "create app"]):
        return "custom_tool.py"

    return ""

def build_system_prompt() -> str:
    target_repo = get_target_repo()
    codebase_context = get_project_context()
    proj_name = get_project_name(target_repo)
    return f"""You are Jarvis, a brilliant AI systems assistant and autonomous coding engineer.
You automate Git commands, dispatch code generation and bug fixes to Antigravity, and answer questions about this codebase or general topics.

=== CODEBASE DIGEST ({proj_name.upper()} @ {target_repo}) ===
{codebase_context}
========================================

Classify the user's input into one of five types:
1. "antigravity_task": Instruction to fix a bug, solve an error, write a new script, generate code, create an app, modify the HUD, change themes, or refactor code.
   - Any transcript mentioning "bug fix", "fix bug", "code changes", "create app", "modify HUD", "theme", or "antigravity" MUST be classified as "antigravity_task".
   - action: "bug_fix" | "code_generation" | "refactor"
   - target_file: specific file mentioned or implied (e.g. "speak.py", "jarvis_hud.py", "custom_tool.py")
   - task_description: detailed actionable instructions for the code fix or generation.
   - speaking_start: "Delegating task to Antigravity Agent, sir."
   - speaking_progress: "Antigravity is reading <filename> and applying code patches..."
   - speaking_response: "Task completed, sir. Antigravity has resolved the issue in <filename>."
2. "codebase_qa": Question about this project, its code, files, architecture, or behavior (no code change requested).
3. "git_query": An INFORMATIONAL QUESTION about git state — e.g. "what branch am I on?", "which branch am I in?", "show me git status", "what's the last commit?", "list all branches".
   - CRITICAL: If the user asks a QUESTION about git (what/which/show/tell/current branch, status, log, etc.), this is a git_query, NOT a git_action.
   - "What branch am I currently in?" is a git_query, NOT a branch creation.
   - command: the git CLI command to run (e.g. "git branch --show-current", "git status", "git log --oneline -5")
   - speaking_response: A direct spoken answer describing what was found.
4. "git_action": An INSTRUCTION to perform a Git/GitHub WRITE operation (push, commit, create branch, pr, merge, delete).
   - CRITICAL: Only classify as git_action when the user is COMMANDING an action, not asking a question.
   - If user asks to create or make a branch: command MUST be: cd "{target_repo}" && (git checkout -b <branch> 2>nul || git checkout <branch>) && git push -u origin <branch>
5. "general_qa": General knowledge question, reasoning, conversation, or math.

CRITICAL DISAMBIGUATION RULES:
- "What branch am I on?" / "Which branch am I currently in?" = git_query (NOT git_action, NOT branch creation)
- "Create branch feature" / "Make a new branch called dev" = git_action
- "Push all code to GitHub" = git_action
- "Show me the git status" / "What are my uncommitted changes?" = git_query

You must respond with ONLY a valid, raw JSON object matching the exact schema below.
DO NOT include markdown code blocks (```json), explanations, or preamble.

Strict Output Schema:
{{
  "type": "antigravity_task" | "codebase_qa" | "git_query" | "git_action" | "general_qa",
  "action": "bug_fix" | "code_generation" | "refactor" | "",
  "target_file": "<filename_if_antigravity_task>",
  "task_description": "<detailed_prompt_for_code_fix_if_antigravity>",
  "command": "<cli_command_if_git>",
  "speaking_start": "<short_task_start_announcement>",
  "speaking_progress": "<spoken_progress_announcement_if_antigravity>",
  "speaking_response": "<direct_spoken_answer_2_to_3_sentences_max>"
}}

Rules:
- For "antigravity_task":
  - command: "cd \"{target_repo}\" && python execute_agent.py antigravity_task.json"
  - speaking_start: "Delegating task to Antigravity Agent, sir."
- For "codebase_qa":
  - Use the codebase digest above to give an accurate, crisp, 2-sentence conversational answer.
  - command: "", action: "", target_file: "", speaking_start: "", speaking_progress: ""
- For "git_query":
  - command: the exact git command to answer the question (e.g. "git branch --show-current", "git status --short", "git log --oneline -5")
  - speaking_start: ""
  - speaking_response: will be filled dynamically with the command output
- For "git_action":
  - For branch creation (e.g. "create branch feature"):
    command: cd "{target_repo}" && (git checkout -b <branch> 2>nul || git checkout <branch>) && git push -u origin <branch>
    speaking_start: "Creating and pushing branch <branch> to GitHub, sir."
    speaking_response: "Branch <branch> has been created and pushed to GitHub, sir."
  - For commit and push:
    command: cd "{target_repo}" && git init && git add . && (git commit -m "<msg>" || echo "No changes to commit") && (git push || gh repo create "{proj_name}" --public --source=. --remote=origin --push)
    speaking_start: "Executing task: committing and pushing your changes, sir."
    speaking_response: "Task completed successfully, sir."
- For "general_qa":
  - Provide a concise spoken answer (1-2 sentences maximum).
  - command: "", action: "", target_file: "", speaking_start: "", speaking_progress: ""

Examples:
1. "Jarvis, create branch feature" ->
{{
  "type": "git_action",
  "action": "create_branch",
  "target_file": "",
  "task_description": "Create and push branch feature",
  "command": "cd \\"{target_repo}\\" && (git checkout -b feature 2>nul || git checkout feature) && git push -u origin feature",
  "speaking_start": "Creating and pushing branch feature to GitHub, sir.",
  "speaking_progress": "",
  "speaking_response": "Branch feature has been created and pushed to GitHub, sir."
}}

2. "Jarvis, solve the bug in speak.py" ->
{{
  "type": "antigravity_task",
  "action": "bug_fix",
  "target_file": "speak.py",
  "task_description": "Diagnose and resolve audio playback and edge-tts synthesis locking bug in speak.py",
  "command": "cd \\"{target_repo}\\" && python execute_agent.py antigravity_task.json",
  "speaking_start": "Delegating task to Antigravity Agent, sir.",
  "speaking_progress": "Antigravity is reading speak.py and applying code patches...",
  "speaking_response": "Task completed, sir. Antigravity has resolved the issue in speak.py."
}}
"""

def resolve_git_query_command(transcript: str) -> str:
    """Maps informational git questions to the correct git CLI command."""
    t = transcript.lower()
    # Check current branch specific queries first
    if any(w in t for w in ["which branch am", "what branch am", "current branch", "am i on", "are we on", "which branch are"]):
        return "git branch --show-current"
    # General branch listing queries
    if any(w in t for w in ["all branch", "list branch", "show branch", "what branch", "branches in", "how many branch", "available branch", "the branch", "branches", "branch list"]):
        return "git branch -a"
    if any(w in t for w in ["status", "changes", "uncommitted", "modified"]):
        return "git status --short"
    if any(w in t for w in [
        "log", "commit history", "last commit", "recent commit", "last committed",
        "committed one", "reverted one", "last revert", "latest revert", "reverted",
        "what was the last", "previous commit", "what did i commit", "what was committed"
    ]):
        return "git log -n 8 --format=%h|||%s|||%cr"
    if any(w in t for w in ["remote", "origin", "url"]):
        return "git remote -v"
    if any(w in t for w in ["diff", "difference"]):
        return "git diff --stat"
    if any(w in t for w in ["tag", "tags"]):
        return "git tag"
    return "git status"

def execute_git_query(git_cmd: str, transcript: str) -> str:
    """Executes a git query command and formats a concise spoken answer."""
    try:
        target_repo = get_target_repo()

        res = subprocess.run(git_cmd.split(), cwd=target_repo, capture_output=True, text=True)
        out = (res.stdout.strip() or res.stderr.strip() or "")

        if "show-current" in git_cmd:
            if not out:
                return "You are currently not on any branch, sir."
            return f"You are currently on the {out} branch, sir."
        elif "branch" in git_cmd:
            # 1. Prune deleted remote branches from origin
            subprocess.run(["git", "fetch", "--prune", "origin"], cwd=target_repo, capture_output=True)

            # 2. Automatically delete dead local branches whose upstream was deleted on GitHub (marked [gone])
            vv_proc = subprocess.run(["git", "branch", "-vv"], cwd=target_repo, capture_output=True, text=True)
            for vv_line in vv_proc.stdout.splitlines():
                if ": gone]" in vv_line:
                    gone_b = vv_line.strip().lstrip("*").split()[0]
                    if gone_b not in ["main", "master"]:
                        if vv_line.strip().startswith("*"):
                            subprocess.run(["git", "checkout", "main"], cwd=target_repo, capture_output=True)
                        subprocess.run(["git", "branch", "-D", gone_b], cwd=target_repo, capture_output=True)

            # 3. Query remote branches from origin (true repository branches on GitHub)
            r_proc = subprocess.run(["git", "branch", "-r"], cwd=target_repo, capture_output=True, text=True)
            branches = set()
            for line in r_proc.stdout.splitlines():
                clean = line.strip()
                if not clean or "->" in clean:
                    continue
                if clean.startswith("origin/"):
                    clean = clean.replace("origin/", "")
                branches.add(clean)

            # If no remote branches found (offline repo), fallback to local active branches
            if not branches:
                l_proc = subprocess.run(["git", "branch"], cwd=target_repo, capture_output=True, text=True)
                for line in l_proc.stdout.splitlines():
                    clean = line.strip().lstrip("*").strip()
                    if clean:
                        branches.add(clean)

            branch_list = sorted(branches)
            if not branch_list:
                return "No branches found in repository, sir."
            if len(branch_list) == 1:
                return f"There is 1 branch: {branch_list[0]}, sir."
            return f"The branches in your repository are: {', '.join(branch_list)}, sir."
        elif "status" in git_cmd:
            if not out:
                return "Your working tree is clean with no uncommitted changes, sir."
            return "Your working tree has uncommitted modifications, sir."
        elif "log" in git_cmd:
            if not out:
                return "No commit history found in this repository, sir."
            lines = [l.strip() for l in out.splitlines() if l.strip()]
            if not lines:
                return "No commits found in git log, sir."

            # Parse top commit
            top_parts = lines[0].split("|||")
            top_subj = top_parts[1].replace('"', '').replace("'", "") if len(top_parts) > 1 else lines[0]
            top_time = top_parts[2] if len(top_parts) > 2 else "recently"
            is_top_revert = top_subj.lower().startswith("revert")

            # Check for any revert commit in recent history
            revert_line = next((l for l in lines if "|||" in l and l.split("|||")[1].lower().startswith("revert")), None)
            revert_subj = None
            revert_time = None
            if revert_line:
                r_parts = revert_line.split("|||")
                revert_subj = r_parts[1].replace('"', '').replace("'", "")
                revert_time = r_parts[2] if len(r_parts) > 2 else "recently"

            t_lower = transcript.lower()

            # Case A: User explicitly asks for "last committed or reverted" or "commit or revert"
            if any(w in t_lower for w in ["revert", "reverted"]) and any(w in t_lower for w in ["commit", "committed"]):
                if is_top_revert:
                    non_rev = next((l for l in lines[1:] if "|||" in l and not l.split("|||")[1].lower().startswith("revert")), None)
                    prev_subj = non_rev.split("|||")[1].replace('"', '').replace("'", "") if non_rev else None
                    if prev_subj:
                        return f"The latest action was a revert: {top_subj}, {top_time}. The commit prior to it was: {prev_subj}, sir."
                    return f"The latest action was a revert: {top_subj}, {top_time}, sir."
                else:
                    if revert_subj:
                        return f"The last committed change was: {top_subj}, {top_time}. And the last reverted one was: {revert_subj}, {revert_time}, sir."
                    return f"The last committed change was: {top_subj}, {top_time}, and there are no recent reverts, sir."

            # Case B: User specifically asks only for the last revert
            elif any(w in t_lower for w in ["revert", "reverted"]):
                if revert_subj:
                    return f"The last reverted change was: {revert_subj}, made {revert_time}, sir."
                return "There are no revert commits found in recent history, sir."

            # Case C: General last commit question
            else:
                if is_top_revert:
                    return f"The latest commit is a revert: {top_subj}, made {top_time}, sir."
                return f"The latest commit is: {top_subj}, made {top_time}, sir."
        elif "remote" in git_cmd:
            if not out:
                return "No remote repositories configured, sir."
            return f"Your repository remotes are configured, sir."
        else:
            return f"Git reports: {out[:80]}, sir."
    except Exception as e:
        return f"Unable to check git status: {e}"

def is_repo_creation(transcript: str) -> bool:
    """Detects intent to create a new GitHub repository."""
    t = transcript.lower()
    return any(k in t for k in [
        "new repo", "create repo", "make a repo", "make repo",
        "new repository", "create repository", "make a repository", "make repository"
    ])

def extract_repo_name(t: str, default: str = "project-repo") -> str:
    """Extracts desired repository name from transcript or command string."""
    if not t:
        return default
    m = re.search(r'(?:named|called)\s+([a-zA-Z0-9_\-\s]+?)(?:\s+(?:and|to|files|file|repo|repository|please)|\.|$)', t, re.IGNORECASE)
    if m:
        cand = m.group(1).strip()
        clean = re.sub(r'[^a-zA-Z0-9_\-\.]', '-', cand).strip('-')
        clean = re.sub(r'-+', '-', clean)
        clean = re.sub(r'-(?:and|push|to|files)$', '', clean, flags=re.IGNORECASE).strip('-')
        if clean and clean.lower() not in ['new', 'a', 'the', 'my', 'and', 'push']:
            return clean

    m2 = re.search(r'(?:new\s+)?(?:repo|repository)\s+(?:to\s+push\s+)?([a-zA-Z0-9_\-\s]+?)(?:\s+(?:files|file|and|to|please)|\.|$)', t, re.IGNORECASE)
    if m2:
        cand = m2.group(1).strip()
        clean = re.sub(r'[^a-zA-Z0-9_\-\.]', '-', cand).strip('-')
        clean = re.sub(r'-+', '-', clean)
        clean = re.sub(r'-(?:and|push|to|files)$', '', clean, flags=re.IGNORECASE).strip('-')
        if clean and clean.lower() not in ['new', 'a', 'the', 'my', 'and', 'push', 'and-push']:
            return clean

    return default

def is_revert_intent(transcript: str) -> bool:
    """Detects intent to revert or undo a git commit."""
    t = transcript.lower()
    return any(k in t for k in [
        "revert", "undo commit", "undo the commit", "undo last commit",
        "rollback commit", "roll back commit", "revert changes", "revert commit"
    ])

def build_default_intent(transcript: str) -> dict:
    target_repo = get_target_repo()
    proj_name = get_project_name(target_repo)
    cd_prefix = f'cd "{target_repo}"'
    t = transcript.lower()

    # 1. Revert Action Intent (IMMEDIATE TOP PRIORITY: Action command to undo/revert commit)
    if is_revert_action(transcript):
        return {
            "type": "git_action",
            "action": "revert_commit",
            "target_file": "",
            "task_description": "Revert last commit",
            "command": f'{cd_prefix} && git revert HEAD --no-edit && git push origin',
            "speaking_start": "Reverting the last commit and syncing with GitHub, sir.",
            "speaking_progress": "Reverting commit...",
            "speaking_response": "The last committed changes have been reverted and synced with GitHub, sir.",
        }

    # 2. Discard Uncommitted Changes Intent (Protected by Two-Turn Voice Confirmation)
    if is_discard_intent(transcript):
        save_pending_action({
            "action_name": "discarding uncommitted local changes",
            "target": "uncommitted_changes",
            "confirmed_intent": {
                "type": "git_action",
                "action": "discard_uncommitted",
                "target_file": "",
                "task_description": "Discard uncommitted local changes",
                "command": f'{cd_prefix} && git restore . && git clean -fd',
                "speaking_start": "Confirmation received. Discarding all uncommitted local modifications, sir.",
                "speaking_progress": "Resetting working tree...",
                "speaking_response": "All uncommitted local changes have been discarded, sir.",
            }
        })
        return {
            "type": "git_query",
            "action": "awaiting_confirmation",
            "target_file": "",
            "task_description": "Security guard awaiting voice confirmation to discard changes",
            "command": "git status --short",
            "speaking_start": "",
            "speaking_progress": "",
            "speaking_response": "Security warning: This will permanently wipe all your uncommitted local modifications. Are you sure you wish to proceed, sir?",
        }

    # 3. Antigravity Coding, Bug Fixing, App Creation, HUD & Theme Intent
    if is_antigravity_intent(transcript):
        target_file = extract_target_file(transcript)

        if not target_file:
            # Dynamic Project-Wide Scan and Repair
            return {
                "type": "antigravity_task",
                "action": "bug_fix",
                "target_file": "",
                "task_description": transcript,
                "command": f'{cd_prefix} && python execute_agent.py antigravity_task.json',
                "speaking_start": "Scanning all Python files across the project for errors with Ollama offline, sir.",
                "speaking_progress": "Ollama is scanning and repairing project files offline...",
                "speaking_response": "Project scan complete. All identified errors have been resolved with Ollama, sir.",
            }

        target_path = os.path.join(target_repo, target_file)
        valid, diag_err, line_num, _ = check_python_syntax(target_path)
        if not valid:
            action = "bug_fix"
            if line_num:
                speaking_start = f"Error detected on line {line_num} in {target_file}. Repairing with Ollama offline, sir."
                task_desc = f"@{target_file} Fix the error on line {line_num}: {diag_err}. Resolve this issue now."
            else:
                speaking_start = f"Error detected in {target_file}. Repairing with Ollama offline, sir."
                task_desc = f"@{target_file} Fix the error: {diag_err}. Resolve this issue now."
            speaking_progress = f"Ollama is analyzing and repairing {target_file}..."
            speaking_response = f"I have repaired the error in {target_file} using Ollama, sir. Verification is valid."
        else:
            if "refactor" in t:
                action = "refactor"
                speaking_start = f"Refactoring {target_file} with Ollama, sir."
                speaking_progress = f"Ollama is refactoring {target_file}..."
                speaking_response = f"Refactoring completed for {target_file}, sir."
            elif any(w in t for w in ["generate", "create", "write", "make", "build", "create app"]):
                action = "code_generation"
                speaking_start = f"Synthesizing new module {target_file} with Ollama, sir."
                speaking_progress = f"Ollama is generating code for {target_file}..."
                speaking_response = f"Module {target_file} generated successfully, sir."
            else:
                action = "bug_fix"
                speaking_start = f"Inspecting {target_file} with Ollama offline, sir."
                speaking_progress = f"Ollama is checking {target_file}..."
                speaking_response = f"Diagnostic check passed. No compilation or runtime errors found in {target_file}, sir."
            task_desc = transcript

        return {
            "type": "antigravity_task",
            "action": action,
            "target_file": target_file,
            "task_description": task_desc,
            "command": f'{cd_prefix} && python execute_agent.py antigravity_task.json',
            "speaking_start": speaking_start,
            "speaking_progress": speaking_progress,
            "speaking_response": speaking_response,
        }

    # 2. Git QUERY Intent — informational questions about git state (MUST come before branch creation check)
    if is_git_query(transcript):
        git_cmd = resolve_git_query_command(transcript)
        speaking_resp = execute_git_query(git_cmd, transcript)
        return {
            "type": "git_query",
            "action": "",
            "target_file": "",
            "task_description": f"Answering git query: {transcript}",
            "command": git_cmd,
            "speaking_start": "",
            "speaking_progress": "",
            "speaking_response": speaking_resp,
        }

    # 3. Branch Deletion Intent (Protected by Two-Turn Voice Confirmation & Auto-Safety Tag)
    if is_branch_deletion(transcript):
        bname = extract_branch_name(transcript)
        # Pre-check: Verify if branch exists locally or remotely before prompting for confirmation
        loc_check = subprocess.run(["git", "show-ref", "--verify", f"refs/heads/{bname}"], cwd=target_repo, capture_output=True)
        rem_check = subprocess.run(["git", "ls-remote", "--heads", "origin", bname], cwd=target_repo, capture_output=True, text=True)
        if loc_check.returncode != 0 and not rem_check.stdout.strip():
            return {
                "type": "git_query",
                "action": "branch_not_found",
                "target_file": "",
                "task_description": f"Branch {bname} not found",
                "command": "git branch -a",
                "speaking_start": "",
                "speaking_progress": "",
                "speaking_response": f"Branch '{bname}' does not exist in this repository, sir.",
            }

        safety_tag = create_branch_safety_snapshot(target_repo, bname)
        save_pending_action({
            "action_name": f"deletion of branch {bname}",
            "target": bname,
            "safety_tag": safety_tag,
            "confirmed_intent": {
                "type": "git_action",
                "action": "delete_branch",
                "target_file": "",
                "task_description": f"Delete branch {bname}",
                "command": (
                    f'{cd_prefix} && git branch -D {bname} && git push origin --delete {bname}'
                ),
                "speaking_start": f"Confirmation received. Deleting branch {bname} locally and from GitHub, sir.",
                "speaking_progress": "",
                "speaking_response": f"Branch {bname} has been deleted successfully, sir.",
            }
        })
        return {
            "type": "git_query",
            "action": "awaiting_confirmation",
            "target_file": "",
            "task_description": f"Security guard awaiting voice confirmation to delete branch {bname}",
            "command": "git status --short",
            "speaking_start": "",
            "speaking_progress": "",
            "speaking_response": f"Security warning: This will permanently delete branch '{bname}' locally and from GitHub. A safety backup snapshot has been created. Are you sure you wish to proceed, sir?",
        }

    # 4. Branch Creation & Push Intent (Strict command: git checkout -b <branch> && git push -u origin <branch>)
    if is_branch_creation(transcript):
        bname = extract_branch_name(transcript)
        return {
            "type": "git_action",
            "action": "create_branch",
            "target_file": "",
            "task_description": f"Create and push branch {bname}",
            "command": (
                f'{cd_prefix} && git checkout -b {bname} && git push -u origin {bname}'
            ),
            "speaking_start": f"Creating and pushing branch {bname} to GitHub, sir.",
            "speaking_progress": "",
            "speaking_response": f"Branch {bname} has been created and pushed to GitHub, sir.",
        }

    # 5. Repository Creation & Push Intent (Dedicated Handler)
    if is_repo_creation(transcript):
        repo_name = extract_repo_name(transcript, default=proj_name)
        return {
            "type": "git_action",
            "action": "create_repo",
            "target_file": repo_name,
            "task_description": f"Create GitHub repository {repo_name} and push all files",
            "command": f'{cd_prefix} && gh repo create {repo_name} --public --source=. --remote=origin --push',
            "speaking_start": f"Creating new GitHub repository {repo_name} and pushing workspace files, sir.",
            "speaking_progress": "",
            "speaking_response": f"Repository {repo_name} has been created on GitHub and files pushed successfully, sir.",
        }

    # 6. Revert / Undo Commit Intent (MUST precede standard commit & push check)
    if is_revert_intent(transcript):
        return {
            "type": "git_action",
            "action": "revert_commit",
            "target_file": "",
            "task_description": "Revert last commit",
            "command": f'{cd_prefix} && git revert HEAD --no-edit && git push origin',
            "speaking_start": "Reverting the last commit and syncing with GitHub, sir.",
            "speaking_progress": "Reverting commit...",
            "speaking_response": "The last committed changes have been reverted and synced with GitHub, sir.",
        }

    # 7. Standard Git Commit & Push Intent
    if any(w in t for w in ["push", "commit", "repo", "github"]):
        return {
            "type": "git_action",
            "action": "",
            "target_file": "",
            "task_description": "Git commit and push",
            "command": (
                f'{cd_prefix} && git init && git add . && '
                f'(git commit -m "Automated update via Jarvis" || echo "No changes to commit") && '
                f'(git push || gh repo create "{proj_name}" --public --source=. --remote=origin --push)'
            ),
            "speaking_start": "Executing task: committing and pushing changes, sir.",
            "speaking_progress": "",
            "speaking_response": "Task completed successfully, sir.",
        }
    elif any(w in t for w in ["status", "changes"]):
        return {
            "type": "git_query",
            "action": "",
            "target_file": "",
            "task_description": "Git status check",
            "command": "git status --short",
            "speaking_start": "",
            "speaking_progress": "",
            "speaking_response": "",
        }
    else:
        return {
            "type": "general_qa",
            "action": "",
            "target_file": "",
            "task_description": "",
            "command": "",
            "speaking_start": "",
            "speaking_progress": "",
            "speaking_response": "I am standing by, sir. How may I assist you?",
        }

def clean_spoken_text(text: str) -> str:
    """Strips markdown asterisks, backticks, hashes, and formatting for clear TTS."""
    if not text:
        return ""
    # Strip markdown code blocks
    t = re.sub(r"```(?:[a-zA-Z0-9_\-]+)?\s*.*?\s*```", "", text, flags=re.DOTALL)
    # Strip inline code formatting `code`
    t = re.sub(r"`([^`]+)`", r"\1", t)
    # Strip markdown bold / italics
    t = re.sub(r"\*\*([^*]+)\*\*", r"\1", t)
    t = re.sub(r"\*([^*]+)\*", r"\1", t)
    t = re.sub(r"__([^_]+)__", r"\1", t)
    t = re.sub(r"_([^_]+)_", r"\1", t)
    # Strip markdown headers, blockquotes, bullets
    t = re.sub(r"^#+\s*", "", t, flags=re.MULTILINE)
    t = re.sub(r"^>\s*", "", t, flags=re.MULTILINE)
    t = re.sub(r"^[\*\-\+]\s+", "", t, flags=re.MULTILINE)
    # Strip markdown links [text](url) -> text
    t = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", t)
    # Clean whitespace and newlines
    t = re.sub(r"[\r\n]+", " ", t)
    t = re.sub(r"\s+", " ", t).strip()

    # Limit to 2 concise sentences max for optimal voice delivery
    sentences = re.split(r'(?<=[.!?])\s+', t)
    if len(sentences) > 2:
        t = " ".join(sentences[:2]).strip()

    return t

def sanitize_json(raw_text: str, transcript: str) -> dict:
    clean = raw_text.strip()
    clean = re.sub(r"^```(?:json)?\s*", "", clean, flags=re.MULTILINE)
    clean = re.sub(r"\s*```$", "", clean, flags=re.MULTILINE)
    clean = clean.replace("```json", "").replace("```", "").strip()

    start = clean.find("{")
    end = clean.rfind("}")
    if start != -1 and end != -1 and end > start:
        clean = clean[start : end + 1].strip()

    try:
        data = json.loads(clean)
    except Exception:
        return build_default_intent(transcript)

    req_type = str(data.get("type", "general_qa")).strip()
    cmd = str(data.get("command", "")).strip()

    # STRICT OVERRIDE: Force git_query if the transcript is an informational git question
    if is_git_query(transcript):
        req_type = "git_query"
        cmd = resolve_git_query_command(transcript)
    cd_prefix = f'cd "{PROJECT_ROOT}"'

    # STRICT OVERRIDE: Force antigravity_task if any trigger keywords are in the transcript
    if is_antigravity_intent(transcript):
        req_type = "antigravity_task"

    target_file = str(data.get("target_file", "")).strip()
    if req_type == "antigravity_task" and not target_file:
        target_file = extract_target_file(transcript)

    raw_resp = str(data.get("speaking_response", ""))
    speaking_resp = clean_spoken_text(raw_resp)
    if not speaking_resp:
        if req_type == "codebase_qa":
            speaking_resp = "Codebase analysis complete, sir. Standing by for instructions."
        elif req_type == "git_action":
            speaking_resp = "Git task completed successfully, sir."
        elif req_type == "antigravity_task":
            speaking_resp = f"Task completed, sir. Antigravity has resolved the issue in {target_file}."
        else:
            speaking_resp = "I am standing by, sir. How may I assist you?"

    if req_type == "antigravity_task":
        action = str(data.get("action", "bug_fix")).strip() or "bug_fix"
        target_path = os.path.join(get_target_repo(), target_file)
        valid, full_tb, line_num, err_details = check_python_syntax(target_path)
        if not valid:
            action = "bug_fix"
            if line_num:
                start = f"Syntax error detected on line {line_num} in {target_file}. Repairing with Ollama offline, sir."
                task_desc = f"@{target_file} Fix the compilation error on line {line_num}: {err_details}. Resolve this issue now."
            else:
                start = f"Syntax error detected in {target_file}. Repairing with Ollama offline, sir."
                task_desc = f"@{target_file} Fix the compilation error: {err_details}. Resolve this issue now."
            prog = f"Ollama is repairing {target_file} offline..."
            speaking_resp = f"I have repaired the error in {target_file} using Ollama, sir. Syntax is valid."
        elif not speaking_resp or speaking_resp.startswith("Task completed"):
            start = f"Checking syntax for {target_file}, sir."
            prog = f"Ollama is checking {target_file}..."
            speaking_resp = f"Syntax check passed. No compilation errors found in {target_file}, sir."
            task_desc = str(data.get("task_description", transcript)).strip()
        else:
            start = f"Analyzing {target_file} with Ollama offline, sir."
            prog = clean_spoken_text(str(data.get("speaking_progress", f"Ollama is checking {target_file}...")))
            task_desc = str(data.get("task_description", transcript)).strip()

        if not cmd:
            cmd = f'{cd_prefix} && python execute_agent.py antigravity_task.json'
        elif not cmd.startswith("cd "):
            cmd = f'{cd_prefix} && {cmd}'

        return {
            "type": "antigravity_task",
            "action": action,
            "target_file": target_file,
            "task_description": task_desc,
            "command": cmd,
            "speaking_start": start,
            "speaking_progress": prog,
            "speaking_response": speaking_resp,
        }

    if req_type == "git_query":
        if not cmd:
            cmd = resolve_git_query_command(transcript)
        speaking_resp = execute_git_query(cmd, transcript)
        return {
            "type": "git_query",
            "action": "",
            "target_file": "",
            "task_description": f"Answering git query: {transcript}",
            "command": cmd,
            "speaking_start": "",
            "speaking_progress": "",
            "speaking_response": speaking_resp,
        }

    if req_type == "git_action":
        if is_revert_intent(transcript):
            cmd = f'{cd_prefix} && git revert HEAD --no-edit && git push origin'
            start = "Reverting the last commit and syncing with GitHub, sir."
            speaking_resp = "The last committed changes have been reverted and synced with GitHub, sir."
        elif is_branch_creation(transcript):
            bname = extract_branch_name(transcript)
            cmd = f'{cd_prefix} && git checkout -b {bname} && git push -u origin {bname}'
            start = f"Creating and pushing branch {bname} to GitHub, sir."
            speaking_resp = f"Branch {bname} has been created and pushed to GitHub, sir."
        elif not cmd.startswith("cd "):
            cmd = f'{cd_prefix} && {cmd}' if cmd else f'{cd_prefix} && git status'

    start = clean_spoken_text(str(data.get("speaking_start", "")))
    prog = clean_spoken_text(str(data.get("speaking_progress", "")))

    return {
        "type": req_type,
        "action": str(data.get("action", "")),
        "target_file": str(data.get("target_file", "")),
        "task_description": str(data.get("task_description", "")),
        "command": cmd,
        "speaking_start": start,
        "speaking_progress": prog,
        "speaking_response": speaking_resp,
    }

def call_groq(transcript: str) -> dict:
    if not GROQ_API_KEY or GROQ_API_KEY.startswith("your_"):
        raise ValueError("GROQ_API_KEY not configured.")

    models = [
        "qwen/qwen3.8-27b",
        "llama-3.3-70b-versatile",
        "qwen-2.5-32b",
        "openai/gpt-oss-120b",
    ]

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }

    system_prompt = build_system_prompt()
    last_err = None

    for m in models:
        try:
            resp = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers=headers,
                json={
                    "model": m,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": f"User: {transcript}"},
                    ],
                    "temperature": 0.2,
                    "max_tokens": 150,
                },
                timeout=10,
            )
            if resp.status_code == 200:
                content = resp.json()["choices"][0]["message"]["content"]
                return sanitize_json(content, transcript)
            elif resp.status_code == 404:
                continue
            else:
                last_err = f"HTTP {resp.status_code}"
        except Exception as e:
            last_err = str(e)
            break

    raise RuntimeError(f"Groq API error: {last_err}")

def get_available_ollama_model() -> str:
    """Detects available models in local Ollama instance or returns preferred default."""
    preferred = os.getenv("OLLAMA_MODEL", "").strip()
    if preferred:
        return preferred
    try:
        r = requests.get(f"{OLLAMA_HOST}/api/tags", timeout=(1.5, 3.0))
        if r.status_code == 200:
            data = r.json()
            models = [m.get("name", "") for m in data.get("models", []) if m.get("name")]
            if models:
                for priority in ["llama3.2", "llama3.1", "llama3", "llama3:8b", "qwen2.5-coder", "qwen2.5", "mistral", "phi3", "gemma"]:
                    for m in models:
                        if priority in m.lower():
                            return m
                return models[0]
    except Exception:
        pass
    return "llama3:8b"

def call_ollama(transcript: str) -> dict:
    """Offline Fallback: Local Ollama chat inference with auto model discovery and strict JSON schema."""
    model = get_available_ollama_model()
    system_prompt = build_system_prompt()
    resp = requests.post(
        f"{OLLAMA_HOST}/api/chat",
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"User: {transcript}"},
            ],
            "options": {"temperature": 0.2, "num_predict": 180},
            "format": "json",
            "stream": False,
        },
        timeout=(2.0, 25.0),
    )
    if resp.status_code == 200:
        content = resp.json().get("message", {}).get("content", "")
        return sanitize_json(content, transcript)
    raise RuntimeError(f"Ollama HTTP {resp.status_code} (model: {model})")

def route_intent(transcript: str) -> dict:
    cleaned = transcript.strip()
    if not cleaned or len(cleaned) < 2:
        return build_default_intent(cleaned)

    # 0. TWO-TURN VOICE CONFIRMATION GUARD (Pending destructive action check)
    pending = load_pending_action()
    if pending:
        if is_confirmation_yes(cleaned):
            clear_pending_action()
            return pending.get("confirmed_intent", build_default_intent(cleaned))
        elif is_confirmation_no(cleaned):
            clear_pending_action()
            return {
                "type": "git_query",
                "action": "action_cancelled",
                "target_file": "",
                "task_description": "User cancelled pending destructive action",
                "command": "git status --short",
                "speaking_start": "",
                "speaking_progress": "",
                "speaking_response": "Action cancelled, sir. Your branches and code remain completely safe.",
            }
        else:
            clear_pending_action()

    # RESTORE SAFETY BACKUP SNAPSHOT (Idea 4 Recovery)
    if is_restore_backup_intent(cleaned):
        return handle_safety_restore_intent(cleaned)

    # 1. IMMEDIATE ROUTING: Git commit revert action
    if is_revert_action(cleaned):
        return build_default_intent(cleaned)

    # 2. IMMEDIATE ROUTING: Discard uncommitted changes action
    if is_discard_intent(cleaned):
        return build_default_intent(cleaned)

    # 3. IMMEDIATE ROUTING: Git informational queries
    if is_git_query(cleaned):
        return build_default_intent(cleaned)

    # 2. IMMEDIATE ROUTING: Git branch deletion
    if is_branch_deletion(cleaned):
        return build_default_intent(cleaned)

    # 3. IMMEDIATE ROUTING: Git branch creation & remote push
    if is_branch_creation(cleaned):
        return build_default_intent(cleaned)

    # 4. IMMEDIATE ROUTING: Git repository creation & push
    if is_repo_creation(cleaned):
        return build_default_intent(cleaned)

    # 5. IMMEDIATE ROUTING: Git commit revert
    if is_revert_intent(cleaned):
        return build_default_intent(cleaned)

    # 6. IMMEDIATE ROUTING: Antigravity task regex/classifier match
    if is_antigravity_intent(cleaned):
        return build_default_intent(cleaned)

    # Check if Ollama / offline mode is explicitly requested
    force_ollama = (
        os.getenv("FORCE_OLLAMA", "false").lower() in ["true", "1", "yes"]
        or os.getenv("FORCE_OFFLINE", "false").lower() in ["true", "1", "yes"]
        or "--ollama" in sys.argv
        or "--offline" in sys.argv
    )

    if not force_ollama:
        # 1. Primary: Groq Cloud API
        try:
            return call_groq(cleaned)
        except Exception as e:
            print(f"[intent_router.py] Groq fallback notice: {e}", file=sys.stderr)

    # 2. Offline Fallback: Local Ollama
    try:
        return call_ollama(cleaned)
    except Exception as e:
        print(f"[intent_router.py] Ollama fallback notice: {e}", file=sys.stderr)

    # 3. Deterministic Fallback
    return build_default_intent(cleaned)

def main():
    transcript = ""
    if len(sys.argv) > 1:
        transcript = " ".join(sys.argv[1:]).strip()

    if not transcript and os.path.exists(TRANSCRIPT_CACHE_FILE):
        try:
            with open(TRANSCRIPT_CACHE_FILE, "r", encoding="utf-8") as f:
                transcript = f.read().strip()
        except Exception:
            transcript = ""

    result = route_intent(transcript)

    # Save to status & intent cache
    try:
        with open(STATUS_CACHE_FILE, "w", encoding="utf-8") as f:
            status_text = result.get("speaking_start") or f"Jarvis routing: {result.get('type')}"
            f.write(status_text)
    except Exception as e:
        print(f"[intent_router.py] Status caching notice: {e}", file=sys.stderr)

    # Save structured payload to antigravity_task.json and antigravity_prompt.txt
    if result.get("type") == "antigravity_task":
        action = result.get("action", "bug_fix")
        target_f = result.get("target_file", "")
        task_desc = result.get("task_description", transcript)
        target_path = os.path.join(get_target_repo(), target_f) if target_f else ""

        if not target_f:
            formatted_prompt = f"Scan all files across workspace {get_target_repo()} and fix any code errors with Ollama."
            hud_status = "[OLLAMA] Scanning workspace for code defects..."
        else:
            valid, diag_err, line_num, _ = check_python_syntax(target_path)
            if not valid:
                formatted_prompt = f"@{target_f} Fix the error on line {line_num or '?'}: {diag_err}. Resolve this issue now."
                hud_status = f"[DEFECT DETECTED] Line {line_num or '?'} in {target_f}: {diag_err[:80]}"
            else:
                formatted_prompt = f"@{target_f} {task_desc}"
                hud_status = f"[DIAGNOSTIC OK] No errors found in {target_f}."

        try:
            with open(ANTIGRAVITY_PROMPT_FILE, "w", encoding="utf-8") as f:
                f.write(formatted_prompt)
            print(f"[intent_router.py] Wrote formatted prompt to {ANTIGRAVITY_PROMPT_FILE}", file=sys.stderr)
        except Exception as e:
            print(f"[intent_router.py] Antigravity prompt caching notice: {e}", file=sys.stderr)

        dispatched_ok = True

        # Stream update to last_status.txt for HUD Panel 3
        try:
            with open(STATUS_CACHE_FILE, "w", encoding="utf-8") as f:
                f.write(hud_status)
        except Exception:
            pass

        try:
            task_payload = {
                "type": "antigravity_task",
                "action": action,
                "target_file": target_f,
                "task_description": task_desc,
                "prompt": formatted_prompt,
                "speaking_start": result.get("speaking_start", ""),
                "speaking_progress": result.get("speaking_progress", ""),
                "speaking_response": result.get("speaking_response", ""),
                "status": "dispatched" if dispatched_ok else "pending",
                "dispatched": dispatched_ok,
                "created_at": time.time()
            }
            with open(ANTIGRAVITY_TASK_FILE, "w", encoding="utf-8") as f:
                json.dump(task_payload, f, indent=2)
            print(f"[intent_router.py] Wrote structured task to {ANTIGRAVITY_TASK_FILE}", file=sys.stderr)
        except Exception as e:
            print(f"[intent_router.py] Antigravity task caching notice: {e}", file=sys.stderr)

    try:
        with open(INTENT_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)
    except Exception as e:
        print(f"[intent_router.py] Intent caching notice: {e}", file=sys.stderr)

    # Output strict JSON
    print(json.dumps(result, indent=2))
    sys.exit(0)

if __name__ == "__main__":
    main()
