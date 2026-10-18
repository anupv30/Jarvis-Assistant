#!/usr/bin/env python3
"""
Jarvis Universal CLI Orchestrator
Provides 'jarvis init', 'jarvis start', 'jarvis hud', 'jarvis n8n', and 'jarvis status'.
Enables Jarvis voice assistant and sci-fi HUD for any repository or project.
"""

import os
import sys
import json
import time
import shutil
import subprocess

# Ensure Jarvis Core is in sys.path
JARVIS_CORE_DIR = os.path.dirname(os.path.abspath(__file__)).replace("/", "\\")
if JARVIS_CORE_DIR not in sys.path:
    sys.path.insert(0, JARVIS_CORE_DIR)

from jarvis_config import (
    get_target_repo,
    set_active_project,
    get_project_name,
    is_n8n_online,
    ensure_n8n_running,
    get_current_git_branch,
    is_hud_running,
    launch_hud as run_hud_window,
    get_python_exe,
)

# Set stdout/stderr to utf-8 safe
try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

def print_banner():
    banner = r"""
  =========================================================================
      JARVIS AUTONOMOUS MULTI-PROJECT VOICE & SCI-FI HUD SYSTEM
  =========================================================================
    """
    print(banner)

def init_project(target_arg: str = None):
    print_banner()
    raw_path = target_arg.strip(' \t\r\n"\'') if (target_arg and target_arg.strip(' \t\r\n"\'')) else os.getcwd()
    target_dir = os.path.abspath(raw_path).rstrip("\\/").replace("/", "\\")
    os.makedirs(target_dir, exist_ok=True)
    project_name = os.path.basename(target_dir)

    print(f">> Initializing Jarvis for project: [{project_name.upper()}]")
    print(f">> Target Workspace: {target_dir}\n")

    # 1. Initialize Git repository if needed
    git_dir = os.path.join(target_dir, ".git")
    if not os.path.exists(git_dir):
        print("  [+] Initializing local Git repository...")
        subprocess.run(["git", "init"], cwd=target_dir, capture_output=True)
    current_branch = get_current_git_branch(target_dir)
    print(f"  [*] Git Repository Verified (Branch: {current_branch})")

    # 2. Scaffold .jarvis directory and config.json
    jarvis_meta_dir = os.path.join(target_dir, ".jarvis")
    os.makedirs(jarvis_meta_dir, exist_ok=True)
    config_file = os.path.join(jarvis_meta_dir, "config.json")
    config_data = {
        "project_name": project_name,
        "project_path": target_dir,
        "jarvis_core_path": JARVIS_CORE_DIR,
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S")
    }
    with open(config_file, "w", encoding="utf-8") as f:
        json.dump(config_data, f, indent=2)
    print("  [+] Scaffolded .jarvis/config.json")

    # 3. Create or update .env in target workspace
    core_env_file = os.path.join(JARVIS_CORE_DIR, ".env")
    target_env_file = os.path.join(target_dir, ".env")
    groq_api_key = ""
    if os.path.exists(core_env_file):
        with open(core_env_file, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                if line.startswith("GROQ_API_KEY="):
                    groq_api_key = line.split("=", 1)[1].strip()
                    break

    if not os.path.exists(target_env_file):
        with open(target_env_file, "w", encoding="utf-8") as f:
            f.write(f"# Jarvis Environment Configuration for {project_name}\n")
            f.write(f"TARGET_REPO_PATH={target_dir}\n")
            f.write(f"GROQ_API_KEY={groq_api_key}\n")
            f.write("N8N_WEBHOOK_URL=http://localhost:5678/webhook/jarvis-git\n")
            f.write("DISPATCH_TO_N8N=true\n")
        print("  [+] Created target .env with shared credentials")

    # 4. Generate local helper batch files in target workspace
    hud_bat = os.path.join(target_dir, "start_hud.bat")
    with open(hud_bat, "w", encoding="utf-8") as f:
        f.write("@echo off\n")
        f.write(f"title JARVIS HUD - [{project_name.upper()}]\n")
        f.write(f"set TARGET_REPO_PATH={target_dir}\n")
        f.write(f'py "{os.path.join(JARVIS_CORE_DIR, "jarvis_hud.py")}" --project "{target_dir}"\n')

    listener_bat = os.path.join(target_dir, "start_jarvis.bat")
    with open(listener_bat, "w", encoding="utf-8") as f:
        f.write("@echo off\n")
        f.write(f"title JARVIS LISTENER - [{project_name.upper()}]\n")
        f.write(f"set TARGET_REPO_PATH={target_dir}\n")
        f.write(f'py "{os.path.join(JARVIS_CORE_DIR, "jarvis_listener.py")}" --project "{target_dir}"\n')

    print("  [+] Generated convenience launchers: start_hud.bat, start_jarvis.bat")

    # 5. Persist target as Active Project
    set_active_project(target_dir)
    print(f"  [+] Active project target registered: {target_dir}")

    # 6. Ensure n8n workflow engine is running in the background
    print("\n>> Checking Background n8n Workflow Server...")
    n8n_status = is_n8n_online()
    if n8n_status:
        print("  [*] n8n Workflow Server: ONLINE (http://localhost:5678)")
    else:
        print("  [!] n8n Server offline. Starting background n8n process...")
        n8n_started = ensure_n8n_running()
        if n8n_started:
            print("  [*] n8n Workflow Server: ONLINE (http://localhost:5678)")
        else:
            print("  [!] Notice: n8n server could not be started automatically. You can launch it with 'jarvis n8n'.")

    # 7. Launch Jarvis HUD Window for this project
    print(f"\n>> Launching Jarvis Sci-Fi HUD for [{project_name.upper()}]...")
    run_hud_window(target_dir)

    print("\n=========================================================================")
    print(f"  JARVIS INITIALIZATION COMPLETE FOR [{project_name.upper()}]")
    print(f"  - Active Workspace : {target_dir}")
    print(f"  - Current Branch   : {current_branch}")
    print(f"  - n8n Automation   : {'ONLINE (http://localhost:5678)' if is_n8n_online() else 'OFFLINE'}")
    print("  - Voice Listener   : Run 'jarvis start' or double-click 'start_jarvis.bat'")
    print("=========================================================================\n")

def start_jarvis(target_arg: str = None):
    print_banner()
    target_dir = get_target_repo(target_arg)
    set_active_project(target_dir)
    project_name = get_project_name(target_dir)

    print(f">> Starting Jarvis Systems for [{project_name.upper()}] ({target_dir})...\n")

    # Ensure n8n is running
    ensure_n8n_running()

    # Launch HUD if not already open
    run_hud_window(target_dir)

    # Launch Voice Listener in foreground
    print("  [*] Launching Zero-Latency Voice Listener (Say 'Hey Jarvis')...\n")
    listener_script = os.path.join(JARVIS_CORE_DIR, "jarvis_listener.py")
    hud_env = os.environ.copy()
    hud_env["TARGET_REPO_PATH"] = target_dir
    python_bin = get_python_exe()
    subprocess.run([python_bin, listener_script, "--project", target_dir], cwd=target_dir, env=hud_env)

def launch_hud(target_arg: str = None):
    target_dir = get_target_repo(target_arg)
    set_active_project(target_dir)
    project_name = get_project_name(target_dir)
    print(f">> Launching Jarvis HUD for [{project_name.upper()}]...")
    run_hud_window(target_dir)
    print(f"  [*] HUD opened for {target_dir}")

def show_status():
    print_banner()
    target_dir = get_target_repo()
    project_name = get_project_name(target_dir)
    branch = get_current_git_branch(target_dir)
    n8n_status = is_n8n_online()

    print(">> CURRENT SYSTEM STATUS:")
    print(f"  - Active Project   : {project_name.upper()}")
    print(f"  - Workspace Path   : {target_dir}")
    print(f"  - Git Branch       : {branch}")
    print(f"  - n8n Server       : {'ONLINE (http://localhost:5678)' if n8n_status else 'OFFLINE'}")
    print(f"  - Core Engine      : {JARVIS_CORE_DIR}")
    print("═════════════════════════════════════════════════════════════════════════\n")

def manage_n8n():
    print(">> Checking n8n server status...")
    if is_n8n_online():
        print("  [*] n8n server is currently ONLINE at http://localhost:5678")
    else:
        print("  [*] Starting background n8n workflow engine...")
        ok = ensure_n8n_running()
        if ok:
            print("  [*] n8n server is now ONLINE at http://localhost:5678")
        else:
            print("  [!] Failed to start n8n server. Run 'start_n8n.bat' manually.")

def uninit_project(target_arg: str = None):
    print_banner()
    raw_path = target_arg.strip(' \t\r\n"\'') if (target_arg and target_arg.strip(' \t\r\n"\'')) else os.getcwd()
    target_dir = os.path.abspath(raw_path).rstrip("\\/").replace("/", "\\")
    project_name = os.path.basename(target_dir)

    print(f">> Uninitializing Jarvis from project: [{project_name.upper()}]")
    print(f">> Target Workspace: {target_dir}\n")

    # 0. Terminate any running HUD process for this workspace
    try:
        import psutil
        for proc in psutil.process_iter(['name', 'cmdline']):
            try:
                cmdline = proc.info.get('cmdline') or []
                if any('jarvis_hud.py' in str(arg).lower() for arg in cmdline):
                    proc.terminate()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
    except Exception:
        pass

    # 1. Remove .jarvis metadata folder
    jarvis_meta_dir = os.path.join(target_dir, ".jarvis")
    if os.path.exists(jarvis_meta_dir):
        shutil.rmtree(jarvis_meta_dir, ignore_errors=True)
        print("  [-] Removed .jarvis configuration directory")

    # 2. Remove batch launchers
    for bat_name in ["start_hud.bat", "start_jarvis.bat"]:
        bat_p = os.path.join(target_dir, bat_name)
        if os.path.exists(bat_p):
            try:
                os.remove(bat_p)
                print(f"  [-] Removed {bat_name}")
            except Exception as e:
                print(f"  [!] Notice: Could not remove {bat_name}: {e}")

    # 3. Clean .env file
    target_env = os.path.join(target_dir, ".env")
    if os.path.exists(target_env):
        try:
            with open(target_env, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()
            jarvis_keys = ["TARGET_REPO_PATH", "GROQ_API_KEY", "N8N_WEBHOOK_URL", "DISPATCH_TO_N8N", "# Jarvis Environment"]
            non_jarvis = [l for l in lines if not any(k in l for k in jarvis_keys)]
            if not "".join(non_jarvis).strip():
                os.remove(target_env)
                print("  [-] Removed Jarvis-generated .env file")
            else:
                with open(target_env, "w", encoding="utf-8") as f:
                    f.writelines(non_jarvis)
                print("  [-] Stripped Jarvis configurations from project .env")
        except Exception as e:
            print(f"  [!] Notice: Could not clean .env: {e}")

    # 4. If target_dir is the current active project, reset active project to Jarvis core
    current_active = get_target_repo()
    if os.path.abspath(current_active).lower() == os.path.abspath(target_dir).lower():
        set_active_project(JARVIS_CORE_DIR)
        print(f"  [*] Active project reset to Jarvis Core: {JARVIS_CORE_DIR}")

    print("\n=========================================================================")
    print(f"  JARVIS UNINITIALIZATION COMPLETE FOR [{project_name.upper()}]")
    print(f"  - Active Workspace : {get_target_repo()}")
    print("=========================================================================\n")

def execute_text_query(query_str: str, play_tts: bool = True):
    from jarvis_listener import process_transcript_pipeline
    print_banner()
    print(f">> Executing Text Query: \"{query_str}\"")
    result = process_transcript_pipeline(query_str, play_tts=play_tts, source="text")
    print(f"\n>> Execution Status: {result.get('status', 'complete')}")
    if "response" in result:
        print(f">> Jarvis Response: {result['response']}")

def run_interactive_text_mode():
    from jarvis_listener import process_transcript_pipeline
    print_banner()
    print("  =========================================================================")
    print("      JARVIS CYBERNETIC COMMAND INTERFACE - INTERACTIVE TEXT MODE")
    print("      Type your command or query (e.g., 'commit and push changes', 'git status')")
    print("      Type 'exit' or 'quit' to return.")
    print("  =========================================================================\n")
    while True:
        try:
            user_input = input("JARVIS [TEXT MODE] > ").strip()
            if not user_input:
                continue
            if user_input.lower() in ["exit", "quit", "q"]:
                print("Exiting interactive text mode. Have a productive session, sir.")
                break
            result = process_transcript_pipeline(user_input, play_tts=True, source="text")
            if "response" in result:
                print(f"\nJARVIS > {result['response']}\n")
        except (KeyboardInterrupt, EOFError):
            print("\nSession terminated.")
            break

def show_help():
    print_banner()
    print("""
Usage:
  jarvis query "query"  Execute a direct text-based command or query.
  jarvis text / chat    Launch interactive cybernetic text console.
  jarvis init [path]    Initialize Jarvis for current or specified project folder.
                        Ensures git, n8n background server, scaffolds launchers,
                        and immediately opens the Jarvis Sci-Fi HUD window.
  jarvis uninit [path]  Uninitialize Jarvis: removes .jarvis, batch launchers,
                        cleans env, and resets active project to core engine.
  jarvis start [path]   Start HUD window and Voice Listener for project.
  jarvis hud [path]     Open the Cybernetic Sci-Fi HUD window for project.
  jarvis n8n            Check or start background n8n workflow server.
  jarvis status         Display active project, git status, and server telemetry.
  jarvis help           Show this command reference.
    """)

def main():
    args = sys.argv[1:]
    if not args:
        show_help()
        sys.exit(0)

    # Detect offline / ollama simulation flags
    if "--ollama" in sys.argv:
        os.environ["FORCE_OLLAMA"] = "true"
        print("[Jarvis CLI] >> Local Ollama mode forced via --ollama flag")
    if "--offline" in sys.argv:
        os.environ["FORCE_OLLAMA"] = "true"
        os.environ["FORCE_OFFLINE"] = "true"
        print("[Jarvis CLI] >> Fully offline mode forced via --offline flag (Ollama + faster-whisper)")

    clean_args = [a for a in args if a not in ["--ollama", "--offline"]]
    if not clean_args:
        show_help()
        sys.exit(0)

    cmd = clean_args[0].lower().strip("-/")
    target = " ".join(clean_args[1:]).strip(' \t\r\n"\'') if len(clean_args) > 1 else None

    if cmd in ["query", "ask", "q", "do", "exec"]:
        if not target:
            print("Error: Please provide a query string. E.g. jarvis query \"commit and push changes\"")
            sys.exit(1)
        execute_text_query(target, play_tts=True)
    elif cmd in ["text", "chat", "repl", "console", "i"]:
        run_interactive_text_mode()
    elif cmd == "init":
        init_project(target)
    elif cmd in ["uninit", "deinit", "remove", "unlink"]:
        uninit_project(target)
    elif cmd == "start":
        start_jarvis(target)
    elif cmd in ["hud", "gui", "window"]:
        launch_hud(target)
    elif cmd == "n8n":
        manage_n8n()
    elif cmd in ["status", "info"]:
        show_status()
    elif cmd in ["help", "h"]:
        show_help()
    else:
        print(f"Unknown command: '{cmd}'. Run 'jarvis help' for available commands.")
        sys.exit(1)

if __name__ == "__main__":
    main()
