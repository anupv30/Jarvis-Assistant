#!/usr/bin/env python3
"""
Jarvis Universal Configuration & Target Project Resolver
Handles workspace targeting across all Jarvis subsystems,
manages active_project.txt pointer, and tracks background n8n status.
"""

import os
import sys
import json
import socket
import time
import subprocess
from dotenv import load_dotenv

JARVIS_CORE_DIR = os.path.dirname(os.path.abspath(__file__)).replace("/", "\\")
ACTIVE_PROJECT_FILE = os.path.join(JARVIS_CORE_DIR, "active_project.txt")

# Load core .env if available
core_env = os.path.join(JARVIS_CORE_DIR, ".env")
if os.path.exists(core_env):
    load_dotenv(core_env)

def get_target_repo(cli_arg: str = None) -> str:
    """Resolves active project repository directory with rigorous fallbacks."""
    # 1. Direct CLI argument
    if cli_arg:
        cleaned = str(cli_arg).strip(' \t\r\n"\'').rstrip("\\/")
        cand = os.path.abspath(cleaned).replace("/", "\\")
        if os.path.exists(cand):
            return cand

    # 2. Check ACTIVE_PROJECT_FILE (the active project pointer)
    if os.path.exists(ACTIVE_PROJECT_FILE):
        try:
            with open(ACTIVE_PROJECT_FILE, "r", encoding="utf-8") as f:
                path = f.read().strip(' \t\r\n"\'').rstrip("\\/")
                if path and path != "." and os.path.exists(path):
                    return os.path.abspath(path).replace("/", "\\")
        except Exception:
            pass

    # 3. Explicit non-dot environment variable
    env_target = os.getenv("TARGET_REPO_PATH", "").strip(' \t\r\n"\'').rstrip("\\/")
    if env_target and env_target != "." and os.path.exists(env_target):
        return os.path.abspath(env_target).replace("/", "\\")

    # 4. Fallback to core directory
    return JARVIS_CORE_DIR

def set_active_project(target_dir: str) -> str:
    """Sets active project target directory and persists to active_project.txt."""
    cleaned = str(target_dir).strip(' \t\r\n"\'').rstrip("\\/")
    abs_path = os.path.abspath(cleaned).replace("/", "\\")
    os.environ["TARGET_REPO_PATH"] = abs_path
    try:
        with open(ACTIVE_PROJECT_FILE, "w", encoding="utf-8") as f:
            f.write(abs_path)
    except Exception as e:
        print(f"[Jarvis Config] Notice: Could not write active_project.txt: {e}", file=sys.stderr)
    return abs_path

def get_project_name(target_dir: str = None) -> str:
    """Extracts friendly display name for target project."""
    repo = get_target_repo(target_dir)
    name = os.path.basename(repo.rstrip("\\/"))
    return name if name else "Jarvis-Core"

def is_n8n_online(host: str = "localhost", port: int = 5678, timeout: float = 0.8) -> bool:
    """Checks whether n8n workflow engine is responding on the local port."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (OSError, socket.timeout):
        return False

def ensure_n8n_running() -> bool:
    """Verifies n8n is running; if not, spins up background server automatically."""
    if is_n8n_online():
        return True

    print("[Jarvis n8n] n8n workflow engine is offline. Initializing background server...")
    bat_file = os.path.join(JARVIS_CORE_DIR, "start_n8n.bat")
    if not os.path.exists(bat_file):
        print(f"[Jarvis n8n] Error: {bat_file} not found.", file=sys.stderr)
        return False

    DETACHED_FLAGS = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    try:
        subprocess.Popen(
            ["cmd.exe", "/c", bat_file],
            cwd=JARVIS_CORE_DIR,
            creationflags=DETACHED_FLAGS,
            close_fds=True
        )
        # Give n8n a few seconds to bind port
        for _ in range(8):
            time.sleep(1.0)
            if is_n8n_online():
                print("[Jarvis n8n] Background n8n server successfully online at http://localhost:5678")
                return True
    except Exception as e:
        print(f"[Jarvis n8n] Could not launch background n8n: {e}", file=sys.stderr)
        return False

    return is_n8n_online()

def get_current_git_branch(repo_path: str = None) -> str:
    """Returns active git branch name for the project."""
    repo = repo_path or get_target_repo()
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=repo,
            capture_output=True,
            text=True,
            timeout=3
        )
        if proc.returncode == 0:
            br = proc.stdout.strip()
            if br:
                return br
    except Exception:
        pass
    return "main"

def is_hud_running() -> bool:
    """Checks whether jarvis_hud.py process is already running on this machine."""
    try:
        import psutil
        curr_pid = os.getpid()
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                if proc.info.get('pid') == curr_pid:
                    continue
                cmdline = proc.info.get('cmdline') or []
                if any('jarvis_hud.py' in str(arg).lower() for arg in cmdline):
                    return True
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
    except Exception:
        pass
    return False

def get_python_exe() -> str:
    """Finds the Python interpreter that has all required Jarvis packages installed."""
    user_py = r"C:\Users\Anup\AppData\Local\Programs\Python\Python312\python.exe"
    if os.path.exists(user_py):
        return user_py
    py_cmd = shutil.which("py")
    if py_cmd:
        return py_cmd
    return sys.executable

def launch_hud(target_dir: str = None) -> bool:
    """Reliably launches the Jarvis HUD desktop GUI window directly."""
    raw = target_dir or get_target_repo()
    target = os.path.abspath(str(raw).strip(' \t\r\n"\'')).rstrip("\\/").replace("/", "\\")
    if is_hud_running():
        return True

    hud_script = os.path.join(JARVIS_CORE_DIR, "jarvis_hud.py").replace("/", "\\")
    if not os.path.exists(hud_script):
        return False

    hud_env = os.environ.copy()
    hud_env["TARGET_REPO_PATH"] = target

    try:
        CREATE_NEW_CONSOLE = 0x00000010
        subprocess.Popen(
            [get_python_exe(), hud_script, "--project", target],
            cwd=target,
            env=hud_env,
            creationflags=CREATE_NEW_CONSOLE
        )
        time.sleep(0.5)
        return True
    except Exception as e:
        print(f"[Jarvis HUD Launch Error]: {e}", file=sys.stderr)
        return False
