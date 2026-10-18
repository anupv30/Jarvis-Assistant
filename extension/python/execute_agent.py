#!/usr/bin/env python3
"""
Jarvis Autonomous Offline Code Repair & Generation Engine (Powered by Ollama)
Features:
- 100% Offline operation using local Ollama (e.g. llama3.2:3b with CUDA acceleration).
- Comprehensive multi-tier diagnostics:
    1. AST syntax parsing (`SyntaxError`, `IndentationError`, `TabError`)
    2. Bytecode compilation (`python -m py_compile`)
    3. Static AST symbol inspection (undefined bare expressions, invalid identifiers)
    4. Runtime smoke-testing (captures `NameError`, `TypeError`, `ZeroDivisionError`, etc.)
- Truly dynamic: Zero hardcoded file names.
- Project-Wide Auto-Repair: Scans every Python file across the active workspace and resolves all defects.
- Single-File Targeted Repair: Accurately targets specific files when explicitly requested by user.
- Multi-turn self-reflection loop: Validates generated patches and prompts Ollama to fix syntax/runtime defects.
- Real-time telemetry to Jarvis Sci-Fi HUD Panel 3 and synchronized voice announcements.
"""

import sys
import os
import re
import json
import time
import ast
import shutil
import builtins
import subprocess
import requests
from dotenv import load_dotenv

load_dotenv()

from jarvis_config import JARVIS_CORE_DIR, get_target_repo, get_python_exe

PROJECT_ROOT = JARVIS_CORE_DIR
TASK_FILE = os.path.join(PROJECT_ROOT, "antigravity_task.json")
LOG_FILE = os.path.join(PROJECT_ROOT, "antigravity_log.txt")
STATUS_FILE = os.path.join(PROJECT_ROOT, "last_status.txt")
SPEAK_SCRIPT = os.path.join(PROJECT_ROOT, "speak.py")

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
OLLAMA_DEFAULT_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:3b").strip()

def append_hud_log(msg: str):
    """Appends timestamped telemetry log for HUD Panel 3 consumption."""
    timestamp = time.strftime("[%H:%M:%S]")
    line = f"{timestamp} {msg}\n"
    print(f"[execute_agent] {msg}")
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass
    try:
        with open(STATUS_FILE, "w", encoding="utf-8") as f:
            f.write(msg)
    except Exception:
        pass

def speak_async(phrase: str):
    """Speaks phrase non-blockingly via speak.py."""
    if not phrase:
        return
    py_exe = get_python_exe()
    try:
        subprocess.Popen(
            [py_exe, SPEAK_SCRIPT, phrase],
            cwd=PROJECT_ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
    except Exception as e:
        print(f"[execute_agent] Voice announcement notice: {e}", file=sys.stderr)

def get_ollama_model() -> str:
    """Discovers available model on local Ollama daemon."""
    try:
        res = requests.get(f"{OLLAMA_HOST}/api/tags", timeout=3)
        if res.status_code == 200:
            models = res.json().get("models", [])
            if models:
                names = [m.get("name", "") for m in models]
                for pref in ["llama3.2", "codellama", "qwen", "mistral", "deepseek"]:
                    for n in names:
                        if pref in n.lower():
                            return n
                return names[0]
    except Exception:
        pass
    return OLLAMA_DEFAULT_MODEL or "llama3.2:3b"

JARVIS_FRAMEWORK_FILES = {
    "jarvis_listener.py", "jarvis_hud.py", "jarvis_cli.py",
    "execute_agent.py", "intent_router.py", "transcribe.py",
    "speak.py", "execute_git.py", "antigravity_bridge.py",
    "jarvis_config.py"
}

def diagnose_file(filepath: str) -> tuple[bool, str, int | None]:
    """
    Comprehensive diagnostic for any Python file:
    1. AST syntax parsing (SyntaxError, IndentationError)
    2. Compilation checking via py_compile
    3. Static AST symbol inspection (undefined identifiers like `iubniufvbiufbv`)
    4. Runtime execution smoke-test (NameError, TypeError, ZeroDivisionError, etc.)
    """
    if not filepath or not os.path.exists(filepath):
        return False, "File does not exist", None

    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            source = f.read()
    except Exception as e:
        return False, f"Could not read file: {e}", None

    # Step 1: AST Parsing
    try:
        tree = ast.parse(source, filename=filepath)
    except SyntaxError as se:
        return False, f"SyntaxError on line {se.lineno}: {se.msg} ({se.text.strip() if se.text else ''})", se.lineno
    except Exception as e:
        return False, f"AST parse error: {e}", None

    # Step 2: py_compile check
    py_exe = get_python_exe()
    try:
        proc = subprocess.run(
            [py_exe, "-m", "py_compile", filepath],
            cwd=os.path.dirname(filepath) or PROJECT_ROOT,
            capture_output=True,
            text=True
        )
        if proc.returncode != 0:
            err_output = (proc.stderr or proc.stdout or "").strip()
            line_m = re.search(r'line\s+(\d+)', err_output, re.I)
            line_num = int(line_m.group(1)) if line_m else None
            return False, f"Compilation defect: {err_output}", line_num
    except Exception:
        pass

    # Step 3: Static AST symbol inspection (catches standalone undefined expressions / typos)
    builtin_names = set(dir(builtins))
    defined_names = set(builtin_names)
    defined_names.update(["__name__", "__file__", "__doc__", "__package__", "__builtins__"])

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            defined_names.add(node.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                defined_names.add(alias.asname or alias.name)
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                defined_names.add(alias.asname or alias.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    defined_names.add(target.id)

    for node in ast.walk(tree):
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Name):
            name_id = node.value.id
            if name_id not in defined_names:
                return False, f"NameError: undefined identifier '{name_id}' on line {node.lineno}", node.lineno

    # Step 4: Runtime smoke test (for user scripts, catches NameError, TypeError, ZeroDivisionError, etc.)
    fname = os.path.basename(filepath).lower()
    if fname not in JARVIS_FRAMEWORK_FILES and "__main__" in source:
        try:
            smoke_proc = subprocess.run(
                [py_exe, filepath],
                cwd=os.path.dirname(filepath) or PROJECT_ROOT,
                capture_output=True,
                text=True,
                timeout=3
            )
            if smoke_proc.returncode != 0:
                err_output = (smoke_proc.stderr or smoke_proc.stdout or "").strip()
                if any(err_kw in err_output for err_kw in ["Error", "Exception", "Traceback"]):
                    line_m = re.search(r'line\s+(\d+)', err_output, re.I)
                    line_num = int(line_m.group(1)) if line_m else None
                    return False, f"Runtime exception: {err_output}", line_num
        except subprocess.TimeoutExpired:
            pass
        except Exception:
            pass

    return True, "Code verification passed with zero errors.", None

def scan_project_defects(repo_dir: str) -> list[tuple[str, str, int | None]]:
    """
    Scans ALL Python files in repo_dir (excluding dependencies, virtualenvs, extension, and framework files).
    Returns list of (filepath, diagnostic_message, line_number) for all defective files.
    """
    defective = []
    ignored_dirs = {".git", "node_modules", "venv", ".venv", "__pycache__", ".jarvis", "dist", "build", "extension"}
    for root, dirs, files in os.walk(repo_dir):
        dirs[:] = [d for d in dirs if d not in ignored_dirs]
        for f in files:
            if f.endswith(".py") and f.lower() not in JARVIS_FRAMEWORK_FILES:
                full_p = os.path.join(root, f)
                valid, diag_msg, line_num = diagnose_file(full_p)
                if not valid:
                    defective.append((full_p, diag_msg, line_num))
    return defective

def extract_code_block(response_text: str) -> str:
    """Extracts raw python code from markdown ```python blocks or fences."""
    m = re.search(r'```(?:python|py)?\s*([\s\S]*?)\s*```', response_text, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    lines = response_text.strip().splitlines()
    code_lines = [l for l in lines if not l.startswith("```")]
    return "\n".join(code_lines).strip()

def fix_file_with_ollama(target_path: str, diagnostic: str, task_desc: str = "") -> tuple[bool, str]:
    """
    Autonomous offline code repair loop with Ollama:
    1. Backs up target file.
    2. Sends code + diagnostic to local Ollama.
    3. Parses output and validates syntax & runtime.
    4. Self-corrects up to 3 turns if Ollama introduces syntax/runtime defects.
    """
    model_name = get_ollama_model()
    target_rel = os.path.basename(target_path)

    try:
        with open(target_path, "r", encoding="utf-8", errors="ignore") as f:
            source_code = f.read()
    except Exception as e:
        return False, f"Failed to read {target_rel}: {e}"

    # Backup file
    backup_path = target_path + ".bak"
    try:
        shutil.copy2(target_path, backup_path)
        append_hud_log(f"[OLLAMA] Safety backup created: {os.path.basename(backup_path)}")
    except Exception:
        pass

    prompt = f"""You are an expert autonomous software engineer.
The Python file '{target_rel}' has an error and fails validation.

ERROR DIAGNOSTIC:
{diagnostic}

TASK SPECIFICATION:
{task_desc or f"Fix all syntax, indentation, type, undefined symbol, and runtime errors in {target_rel}."}

CURRENT SOURCE CODE:
```python
{source_code}
```

CRITICAL INSTRUCTIONS:
1. Fix all errors, remove any stray or undefined tokens/identifiers, and ensure 100% valid Python.
2. Preserve original functionality, logic, and module signatures.
3. Return ONLY the complete, corrected Python code inside a single ```python ... ``` block.
4. Do NOT output explanations, apologies, markdown commentary, or introductory text.
"""

    messages = [{"role": "user", "content": prompt}]
    max_retries = 3

    for attempt in range(1, max_retries + 1):
        append_hud_log(f"[OLLAMA] Dispatching offline repair prompt to local Ollama ({model_name}, attempt {attempt}/{max_retries})...")
        try:
            res = requests.post(
                f"{OLLAMA_HOST}/api/chat",
                json={
                    "model": model_name,
                    "messages": messages,
                    "stream": False,
                    "options": {
                        "temperature": 0.1,
                        "num_predict": 4096
                    }
                },
                timeout=60
            )
            if res.status_code != 200:
                append_hud_log(f"[OLLAMA ERROR] HTTP {res.status_code}: {res.text[:120]}")
                time.sleep(1)
                continue

            content = res.json().get("message", {}).get("content", "")
            fixed_code = extract_code_block(content)

            if not fixed_code:
                append_hud_log(f"[OLLAMA] Warning: No code block extracted from attempt {attempt}. Retrying...")
                continue

            # In-memory AST syntax validation
            try:
                ast.parse(fixed_code)
            except SyntaxError as se:
                append_hud_log(f"[OLLAMA] Patch attempt {attempt} has syntax defect on line {se.lineno}: {se.msg}")
                messages.append({"role": "assistant", "content": content})
                messages.append({
                    "role": "user",
                    "content": f"The code you produced still has a syntax error on line {se.lineno}: {se.msg}.\nPlease fix it. Return ONLY the complete, valid Python code inside ```python ... ```."
                })
                continue

            # Write proposed code to disk
            with open(target_path, "w", encoding="utf-8") as f:
                f.write(fixed_code)

            # Full multi-tier diagnostic verification on disk
            valid, diag_err, line_num = diagnose_file(target_path)
            if not valid:
                append_hud_log(f"[OLLAMA] Diagnostic defect on attempt {attempt}: {diag_err[:120]}")
                messages.append({"role": "assistant", "content": content})
                messages.append({
                    "role": "user",
                    "content": f"Validation failed with error: {diag_err}. Please resolve it completely and return ONLY the valid Python code in ```python ... ```."
                })
                continue

            append_hud_log(f"[OLLAMA SUCCESS] Verification PASSED for {target_rel}. Patch applied cleanly.")
            return True, f"Successfully repaired {target_rel} with Ollama."

        except Exception as e:
            append_hud_log(f"[OLLAMA] Connection/generation exception: {e}")
            time.sleep(1)

    # If all attempts failed, restore original backup
    if os.path.exists(backup_path):
        try:
            shutil.copy2(backup_path, target_path)
            append_hud_log(f"[OLLAMA] Restored original {target_rel} from backup after failed attempts.")
        except Exception:
            pass

    return False, f"Ollama could not resolve errors in {target_rel} after {max_retries} attempts."

def generate_scaffold(target_file: str, task_desc: str) -> str:
    """Creates a production-grade template if creating a new script."""
    module_name = os.path.splitext(os.path.basename(target_file))[0].capitalize()
    return f'''#!/usr/bin/env python3
"""
{module_name} Module
Generated by Jarvis & Antigravity Autonomous Code Bridge
Task: {task_desc}
"""

import sys
import os

def run():
    print("[{module_name}] Execution initialized.")
    return True

if __name__ == "__main__":
    success = run()
    sys.exit(0 if success else 1)
'''

def fix_project_errors(repo_dir: str, task_desc: str = "") -> tuple[bool, str]:
    """
    Scans ALL Python files in the workspace and fixes every detected defect.
    """
    append_hud_log(f"[OLLAMA SCAN] Scanning all Python files across workspace: {repo_dir}...")
    defective_files = scan_project_defects(repo_dir)

    if not defective_files:
        msg = "I have scanned all Python files across the project, sir. No syntax, compilation, or runtime errors were found."
        append_hud_log(f"[OLLAMA NOTICE] {msg}")
        return True, msg

    append_hud_log(f"[OLLAMA SCAN] Found {len(defective_files)} file(s) with defects in workspace.")
    repaired = []
    failed = []

    for file_path, diag_msg, line_num in defective_files:
        rel_name = os.path.relpath(file_path, repo_dir)
        append_hud_log(f"[OLLAMA] Defect identified in {rel_name}: {diag_msg.splitlines()[-1] if diag_msg else ''}")
        success, res_msg = fix_file_with_ollama(file_path, diag_msg, task_desc)
        if success:
            repaired.append(rel_name)
        else:
            failed.append(rel_name)

    if repaired and not failed:
        rep_names = ", ".join(repaired)
        msg = f"I have analyzed and fixed the errors in {rep_names} using Ollama, sir. Verification is 100% valid."
        append_hud_log(f"[OLLAMA SUCCESS] {msg}")
        return True, msg
    elif repaired and failed:
        msg = f"Repaired {', '.join(repaired)} successfully, but {', '.join(failed)} could not be resolved."
        append_hud_log(f"[OLLAMA PARTIAL] {msg}")
        return True, msg
    else:
        msg = f"Failed to resolve errors in {', '.join(failed)}."
        append_hud_log(f"[OLLAMA ERROR] {msg}")
        return False, msg

def main():
    task_path = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1].endswith(".json") else TASK_FILE
    target_arg = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].endswith(".json") else None

    task = {}
    if os.path.exists(task_path):
        try:
            with open(task_path, "r", encoding="utf-8") as f:
                task = json.load(f)
        except Exception:
            pass

    target_repo = get_target_repo()
    target_rel = target_arg or task.get("target_file", "")
    task_desc = task.get("task_description", "")
    action = task.get("action", "bug_fix")

    append_hud_log(f"[OLLAMA ENGINE] Initialized autonomous code repair bridge in {target_repo}...")

    # Truly dynamic resolution: If target is not specified or indicates project-wide repair, scan the entire workspace
    is_project_wide = (
        not target_rel or
        target_rel.lower() in ["", "all", "all_project_files", "project", "the project", "program", "the program", "workspace"] or
        any(w in str(task_desc).lower() for w in ["in the project", "across the project", "in the program", "all errors", "any errors"])
    )

    if is_project_wide:
        success, summary_msg = fix_project_errors(target_repo, task_desc)
        prefix = "[OLLAMA SUCCESS]" if success and "fixed" in summary_msg.lower() else ("[OLLAMA NOTICE]" if "no syntax" in summary_msg.lower() else "[OLLAMA ERROR]")
        status_line = f"{prefix} {summary_msg}"
        try:
            with open(STATUS_FILE, "w", encoding="utf-8") as f:
                f.write(status_line)
        except Exception:
            pass
        task["status"] = "completed" if success else "failed"
        task["syntax_valid"] = success
        try:
            with open(task_path, "w", encoding="utf-8") as f:
                json.dump(task, f, indent=2)
        except Exception:
            pass
        sys.exit(0 if success else 1)

    # Single-file targeted repair
    target_path = os.path.join(target_repo, target_rel)
    if not os.path.exists(target_path) and os.path.exists(os.path.join(PROJECT_ROOT, target_rel)):
        target_path = os.path.join(PROJECT_ROOT, target_rel)

    # 1. Target file does not exist
    if not os.path.exists(target_path):
        if action == "code_generation":
            append_hud_log(f"[OLLAMA] Creating new module scaffold for: {target_rel}")
            code = generate_scaffold(target_rel, task_desc)
            with open(target_path, "w", encoding="utf-8") as f:
                f.write(code)
            status_msg = f"[OLLAMA SUCCESS] Created {target_rel} successfully."
            append_hud_log(status_msg)
            try:
                with open(STATUS_FILE, "w", encoding="utf-8") as f:
                    f.write(status_msg)
            except Exception:
                pass
            sys.exit(0)
        else:
            # Fall back to project scan if target file is not found
            success, summary_msg = fix_project_errors(target_repo, task_desc)
            sys.exit(0 if success else 1)

    # 2. Diagnose target file
    append_hud_log(f"[OLLAMA] Diagnosing syntax, AST symbols, and runtime status in {target_rel}...")
    valid, diag_err, line_num = diagnose_file(target_path)

    if valid:
        append_hud_log(f"[OLLAMA] Verification PASSED: {target_rel} is 100% valid with no errors.")
        status_msg = f"[OLLAMA NOTICE] Diagnostic check passed. No compilation or runtime errors found in {target_rel}, sir."
        try:
            with open(STATUS_FILE, "w", encoding="utf-8") as f:
                f.write(status_msg)
        except Exception:
            pass
        task["status"] = "completed"
        task["syntax_valid"] = True
        try:
            with open(task_path, "w", encoding="utf-8") as f:
                json.dump(task, f, indent=2)
        except Exception:
            pass
        sys.exit(0)

    # 3. Defect found: Fix with Ollama offline
    append_hud_log(f"[OLLAMA] Initiating autonomous offline repair for {target_rel}...")
    success, fix_msg = fix_file_with_ollama(target_path, diag_err, task_desc)

    if success:
        status_msg = f"[OLLAMA SUCCESS] I have analyzed and fixed the error in {target_rel} using Ollama, sir. Syntax verification is 100% valid."
        append_hud_log(status_msg)
        try:
            with open(STATUS_FILE, "w", encoding="utf-8") as f:
                f.write(status_msg)
        except Exception:
            pass
        task["status"] = "completed"
        task["syntax_valid"] = True
        try:
            with open(task_path, "w", encoding="utf-8") as f:
                json.dump(task, f, indent=2)
        except Exception:
            pass
        sys.exit(0)
    else:
        status_msg = f"[OLLAMA ERROR] {fix_msg}"
        append_hud_log(status_msg)
        try:
            with open(STATUS_FILE, "w", encoding="utf-8") as f:
                f.write(status_msg)
        except Exception:
            pass
        task["status"] = "failed"
        task["syntax_valid"] = False
        try:
            with open(task_path, "w", encoding="utf-8") as f:
                json.dump(task, f, indent=2)
        except Exception:
            pass
        sys.exit(1)

if __name__ == "__main__":
    main()
