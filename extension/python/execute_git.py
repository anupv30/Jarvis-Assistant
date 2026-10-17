#!/usr/bin/env python3
"""
Jarvis Git Command Execution Module
Executes validated CLI actions inside the project root directory.
Guarantees execution in the project directory regardless of caller CWD,
auto-injects GitHub CLI path, and skips execution for general QA queries.
"""

import sys
import os
import json
import re
import subprocess
from dotenv import load_dotenv

load_dotenv()

from jarvis_config import JARVIS_CORE_DIR, get_target_repo, get_project_name

PROJECT_ROOT = JARVIS_CORE_DIR

# Ensure GitHub CLI and Git are in PATH
GH_PATH = r"C:\Program Files\GitHub CLI"
if os.path.exists(GH_PATH) and GH_PATH not in os.environ.get("PATH", ""):
    os.environ["PATH"] = GH_PATH + os.pathsep + os.environ.get("PATH", "")

def get_github_auth_token() -> str:
    """Retrieves GitHub token from environment or Git Credential Manager."""
    token = os.getenv("GITHUB_TOKEN", "").strip() or os.getenv("GH_TOKEN", "").strip()
    if token:
        return token

    try:
        proc = subprocess.run(
            ["git", "credential", "fill"],
            input="protocol=https\nhost=github.com\n",
            capture_output=True,
            text=True,
            timeout=5
        )
        if proc.returncode == 0:
            for line in proc.stdout.splitlines():
                if line.startswith("password="):
                    cand = line.split("=", 1)[1].strip()
                    if cand:
                        os.environ["GH_TOKEN"] = cand
                        os.environ["GITHUB_TOKEN"] = cand
                        return cand
    except Exception as e:
        print(f"[execute_git.py] Notice: Could not read git credential helper: {e}", file=sys.stderr)

    return ""

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

def handle_create_repo_and_push(target_repo: str, repo_name: str = None, is_private: bool = False) -> tuple[int, str]:
    """Creates a remote repository on GitHub and pushes all workspace files."""
    if not repo_name or not repo_name.strip():
        repo_name = os.path.basename(target_repo.rstrip("\\/"))
    clean_name = re.sub(r'[^a-zA-Z0-9_\-\.]', '-', repo_name.strip()).strip('-')
    clean_name = re.sub(r'-+', '-', clean_name)
    if not clean_name:
        clean_name = "project-repo"

    print(f"[execute_git.py] Preparing GitHub repo creation for '{clean_name}' in '{target_repo}'...")

    # 1. Get auth credentials
    token = get_github_auth_token()
    username = "RahulSokkalingam"
    if token:
        try:
            import urllib.request
            req = urllib.request.Request(
                "https://api.github.com/user",
                headers={"Authorization": f"token {token}", "User-Agent": "Jarvis-Assistant"}
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                u_data = json.loads(resp.read().decode())
                if "login" in u_data:
                    username = u_data["login"]
        except Exception:
            pass

    # 2. Ensure local git repo is initialized
    git_dir = os.path.join(target_repo, ".git")
    if not os.path.exists(git_dir):
        print(f"[execute_git.py] Initializing local git repository...")
        subprocess.run(["git", "init"], cwd=target_repo, capture_output=True)

    # 3. Stage and commit
    print(f"[execute_git.py] Staging all files in {target_repo}...")
    subprocess.run(["git", "add", "-A"], cwd=target_repo, capture_output=True)

    status_proc = subprocess.run(["git", "status", "--porcelain"], cwd=target_repo, capture_output=True, text=True)
    if status_proc.stdout.strip():
        print(f"[execute_git.py] Creating initial commit...")
        subprocess.run(
            ["git", "commit", "-m", f"Initial commit for {clean_name} via Jarvis"],
            cwd=target_repo,
            capture_output=True
        )

    # Detect current branch
    br_proc = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=target_repo, capture_output=True, text=True)
    curr_branch = br_proc.stdout.strip()
    if not curr_branch or curr_branch == "HEAD":
        curr_branch = "master"
        subprocess.run(["git", "checkout", "-B", "master"], cwd=target_repo, capture_output=True)

    # 4. Create the repository on GitHub
    repo_created = False
    repo_url = f"https://github.com/{username}/{clean_name}.git"

    if token:
        try:
            import urllib.request
            create_payload = json.dumps({
                "name": clean_name,
                "private": is_private,
                "description": f"Automated repository created via Jarvis Voice Assistant"
            }).encode("utf-8")
            req = urllib.request.Request(
                "https://api.github.com/user/repos",
                data=create_payload,
                headers={
                    "Authorization": f"token {token}",
                    "User-Agent": "Jarvis-Assistant",
                    "Content-Type": "application/json"
                }
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                resp_data = json.loads(resp.read().decode())
                repo_url = resp_data.get("clone_url", repo_url)
                print(f"[execute_git.py] Successfully created GitHub repository: {repo_url}")
                repo_created = True
        except urllib.error.HTTPError as e:
            if e.code == 422:
                print(f"[execute_git.py] Repository '{clean_name}' already exists on GitHub under {username}.")
                repo_created = True
            else:
                err_body = e.read().decode("utf-8", errors="ignore")
                print(f"[execute_git.py] GitHub API creation returned HTTP {e.code}: {err_body}")
        except Exception as e:
            print(f"[execute_git.py] GitHub API request notice: {e}")

    # Fallback to GitHub CLI if available and not yet created
    if not repo_created:
        gh_bin = r"C:\Program Files\GitHub CLI\gh.exe"
        gh_cmd = gh_bin if os.path.exists(gh_bin) else "gh"
        gh_env = os.environ.copy()
        if token:
            gh_env["GH_TOKEN"] = token
        vis_flag = "--private" if is_private else "--public"
        print(f"[execute_git.py] Attempting creation via gh CLI ({clean_name})...")
        gh_proc = subprocess.run(
            [gh_cmd, "repo", "create", clean_name, vis_flag, "--source=.", "--remote=origin", "--push"],
            cwd=target_repo,
            env=gh_env,
            capture_output=True,
            text=True
        )
        if gh_proc.returncode == 0:
            return 0, f"Repository '{clean_name}' created on GitHub and files pushed successfully"
        else:
            print(f"[execute_git.py] gh CLI output: {gh_proc.stderr.strip() or gh_proc.stdout.strip()}")

    # 5. Configure remote origin
    rem_check = subprocess.run(["git", "remote", "get-url", "origin"], cwd=target_repo, capture_output=True, text=True)
    if rem_check.returncode == 0:
        subprocess.run(["git", "remote", "set-url", "origin", repo_url], cwd=target_repo, capture_output=True)
    else:
        subprocess.run(["git", "remote", "add", "origin", repo_url], cwd=target_repo, capture_output=True)

    # 6. Push to GitHub origin
    print(f"[execute_git.py] Pushing '{curr_branch}' branch to origin...")
    push_proc = subprocess.run(
        ["git", "push", "-u", "origin", curr_branch],
        cwd=target_repo,
        capture_output=True,
        text=True
    )
    if push_proc.returncode != 0:
        err = push_proc.stderr.strip() or push_proc.stdout.strip()
        return push_proc.returncode, f"Failed to push to GitHub: {err}"

    # Also synchronize main/master if applicable
    if curr_branch == "master":
        subprocess.run(["git", "push", "origin", "master:main"], cwd=target_repo, capture_output=True)
    elif curr_branch == "main":
        subprocess.run(["git", "push", "origin", "main:master"], cwd=target_repo, capture_output=True)

    return 0, f"Repository '{clean_name}' successfully created on GitHub and {curr_branch} pushed"

def handle_delete_branch(target_repo: str, branch_name: str) -> tuple[int, str]:
    """Deletes branch locally and on remote GitHub origin."""
    branch = branch_name.strip(".-/ \t\r\n")
    if not branch:
        return 1, "Branch name is empty"
    if branch in ["main", "master"]:
        return 1, f"Cannot delete protected default branch '{branch}'"

    # 1. If currently on the branch to be deleted, switch to main first
    curr_br = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=target_repo, capture_output=True, text=True).stdout.strip()
    if curr_br == branch:
        print(f"[execute_git.py] Currently on '{branch}'; switching to 'main' first...")
        subprocess.run(["git", "checkout", "main"], cwd=target_repo, capture_output=True)

    # 2. Delete local branch
    print(f"[execute_git.py] Deleting local branch '{branch}'...")
    del_local = subprocess.run(["git", "branch", "-D", branch], cwd=target_repo, capture_output=True, text=True)
    local_msg = del_local.stdout.strip() or del_local.stderr.strip()

    # 3. Delete remote branch on GitHub origin
    print(f"[execute_git.py] Deleting remote branch '{branch}' on origin...")
    del_remote = subprocess.run(["git", "push", "origin", "--delete", branch], cwd=target_repo, capture_output=True, text=True)
    remote_msg = del_remote.stdout.strip() or del_remote.stderr.strip()

    # 4. Prune remote tracking references
    subprocess.run(["git", "fetch", "--prune", "origin"], cwd=target_repo, capture_output=True)

    if del_local.returncode == 0 or del_remote.returncode == 0:
        return 0, f"Branch '{branch}' deleted successfully"
    return 1, f"Failed to delete branch '{branch}': {local_msg} {remote_msg}"

def handle_create_branch(target_repo: str, branch_name: str) -> tuple[int, str]:
    """Robustly checks out/creates a branch and pushes it to GitHub origin."""
    branch = branch_name.strip(".-/ \t\r\n")
    if not branch:
        return 1, "Branch name is empty"
    print(f"[execute_git.py] Creating/switching to branch '{branch}'...")
    res = subprocess.run(["git", "checkout", "-b", branch], cwd=target_repo, capture_output=True, text=True)
    if res.returncode != 0:
        print(f"[execute_git.py] Notice on checkout -b: {res.stderr.strip()}; trying git checkout {branch}...")
        res2 = subprocess.run(["git", "checkout", branch], cwd=target_repo, capture_output=True, text=True)
        if res2.returncode != 0:
            err = res2.stderr.strip() or res.stderr.strip()
            return res2.returncode, f"Failed to checkout branch: {err}"

    print(f"[execute_git.py] Pushing branch '{branch}' to origin...")
    push_res = subprocess.run(["git", "push", "-u", "origin", branch], cwd=target_repo, capture_output=True, text=True)
    if push_res.returncode != 0:
        err = push_res.stderr.strip() or push_res.stdout.strip()
        return push_res.returncode, f"Failed to push branch to GitHub: {err}"

    return 0, f"Successfully created and pushed branch '{branch}' to GitHub"

def handle_commit_and_push(target_repo: str) -> tuple[int, str]:
    """Robustly stages, commits, and pushes to GitHub with accurate branch detection and syncing."""
    # 1. Stage all changes
    print("[execute_git.py] Staging changes: git add -A")
    subprocess.run(["git", "add", "-A"], cwd=target_repo, capture_output=True)

    # 2. Check if changes exist to commit
    status_proc = subprocess.run(["git", "status", "--porcelain"], cwd=target_repo, capture_output=True, text=True)
    if status_proc.stdout.strip():
        print("[execute_git.py] Committing changes...")
        commit_proc = subprocess.run(
            ["git", "commit", "-m", "Automated update via Jarvis"],
            cwd=target_repo,
            capture_output=True,
            text=True
        )
        if commit_proc.returncode != 0:
            err = commit_proc.stderr.strip() or commit_proc.stdout.strip()
            print(f"[execute_git.py] Commit note: {err}")
    else:
        print("[execute_git.py] Working tree clean, nothing new to commit.")

    # 3. Detect current branch
    br_proc = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=target_repo, capture_output=True, text=True)
    curr_branch = br_proc.stdout.strip() or "main"
    print(f"[execute_git.py] Current active branch: {curr_branch}")

    # 4. Check if remote origin exists; if not, automatically create the GitHub repository and push
    rem_check = subprocess.run(["git", "remote", "get-url", "origin"], cwd=target_repo, capture_output=True, text=True)
    if rem_check.returncode != 0:
        print(f"[execute_git.py] Notice: No remote origin found for '{target_repo}'. Auto-creating GitHub repository...")
        return handle_create_repo_and_push(target_repo)

    # 5. Push current branch to origin
    print(f"[execute_git.py] Pushing to origin/{curr_branch}...")
    push_proc = subprocess.run(
        ["git", "push", "-u", "origin", curr_branch],
        cwd=target_repo,
        capture_output=True,
        text=True
    )
    if push_proc.returncode != 0:
        err = push_proc.stderr.strip() or push_proc.stdout.strip()
        return push_proc.returncode, f"Git push error: {err}"

    # 6. Synchronize both main and master so GitHub default branch is always updated
    if curr_branch == "main":
        print("[execute_git.py] Syncing main to master on origin...")
        subprocess.run(["git", "push", "origin", "main:master"], cwd=target_repo, capture_output=True)
    elif curr_branch == "master":
        print("[execute_git.py] Syncing master to main on origin...")
        subprocess.run(["git", "push", "origin", "master:main"], cwd=target_repo, capture_output=True)

    return 0, f"Successfully pushed to GitHub ({curr_branch})"

def main():
    intent_file = sys.argv[1] if len(sys.argv) > 1 else os.path.join(PROJECT_ROOT, "last_intent.json")
    if not os.path.exists(intent_file):
        print(f"[execute_git.py] Error: {intent_file} does not exist.", file=sys.stderr)
        sys.exit(1)

    try:
        with open(intent_file, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"[execute_git.py] Invalid intent JSON: {e}", file=sys.stderr)
        sys.exit(1)

    # Delegate to execute_agent if Antigravity task
    if data.get("type") == "antigravity_task":
        print("[execute_git.py] Antigravity task detected; delegating to execute_agent.py.")
        agent_script = os.path.join(PROJECT_ROOT, "execute_agent.py")
        proc = subprocess.run([sys.executable, agent_script], cwd=PROJECT_ROOT)
        sys.exit(proc.returncode)

    # Bypass if query is General QA, Codebase QA, or Git Query
    if data.get("type") in ["general_qa", "codebase_qa", "git_query"]:
        print("[execute_git.py] QA/Query detected; bypassing Git CLI write actions.")
        sys.exit(0)

    action = str(data.get("action", "")).lower()
    command = data.get("command", "git status").strip()
    task_desc = data.get("task_description", "").lower()
    target_repo = get_target_repo()
    status_file = os.path.join(PROJECT_ROOT, "last_status.txt")

    # 1. Dedicated Handler for Branch Deletion
    if action == "delete_branch" or "branch -d" in command.lower() or ("branch" in task_desc and ("delete" in task_desc or "remove" in task_desc)):
        m = re.search(r'branch\s+-[dD]\s+([^\s&|]+)', command)
        if m:
            bname = m.group(1).strip()
        else:
            m2 = re.search(r'branch\s+(?:called\s+|named\s+)?([a-zA-Z0-9_\-\.\/]+)', task_desc)
            bname = m2.group(1).strip() if m2 else "feature-branch"
        print(f"[Jarvis Executing]: Robust Branch Deletion '{bname}' in '{target_repo}'")
        retcode, out_msg = handle_delete_branch(target_repo, bname)
        print(f"[execute_git.py] {out_msg} (Exit code: {retcode})")
        if retcode != 0:
            with open(status_file, "w", encoding="utf-8") as f:
                f.write(f"[GIT ERROR] {out_msg}")
            sys.exit(retcode)
        else:
            with open(status_file, "w", encoding="utf-8") as f:
                f.write(f"[GIT SUCCESS] {data.get('speaking_response', f'Branch {bname} deleted.')}")
            sys.exit(0)

    # 2. Dedicated Handler for Branch Creation & Push
    elif action == "create_branch" or "checkout -b" in command or ("branch" in task_desc and ("create" in task_desc or "make" in task_desc)):
        m = re.search(r'checkout\s+-b\s+([^\s&|]+)', command)
        if m:
            bname = m.group(1).strip()
        else:
            m2 = re.search(r'branch\s+([a-zA-Z0-9_\-\.\/]+)', task_desc)
            bname = m2.group(1).strip() if m2 else "feature-branch"
        print(f"[Jarvis Executing]: Robust Branch Creation '{bname}' in '{target_repo}'")
        retcode, out_msg = handle_create_branch(target_repo, bname)
        print(f"[execute_git.py] {out_msg} (Exit code: {retcode})")
        if retcode != 0:
            with open(status_file, "w", encoding="utf-8") as f:
                f.write(f"[GIT ERROR] {out_msg}")
            sys.exit(retcode)
        else:
            with open(status_file, "w", encoding="utf-8") as f:
                f.write(f"[GIT SUCCESS] {data.get('speaking_response', f'Branch {bname} created and pushed.')}")
            sys.exit(0)

    # 3. Dedicated Handler for Repository Creation & Push
    elif action in ["create_repo", "new_repo"] or "repo create" in command.lower() or ("repo" in task_desc and any(w in task_desc for w in ["create", "new", "make", "named", "called"])):
        target_name = data.get("target_file") or extract_repo_name(task_desc or command, get_project_name(target_repo))
        print(f"[Jarvis Executing]: Robust GitHub Repository Creation & Push '{target_name}' for '{target_repo}'")
        retcode, out_msg = handle_create_repo_and_push(target_repo, target_name)
        print(f"[execute_git.py] {out_msg} (Exit code: {retcode})")
        if retcode != 0:
            with open(status_file, "w", encoding="utf-8") as f:
                f.write(f"[GIT ERROR] {out_msg}")
            sys.exit(retcode)
        else:
            with open(status_file, "w", encoding="utf-8") as f:
                f.write(f"[GIT SUCCESS] {data.get('speaking_response', f'Repository {target_name} created and files pushed.')}")
            sys.exit(0)

    # 4. Dedicated Handler for Commit & Push
    elif "push" in command or "push" in task_desc or "commit" in task_desc:
        print(f"[Jarvis Executing]: Robust Git Commit & Push in '{target_repo}'")
        retcode, out_msg = handle_commit_and_push(target_repo)
        print(f"[execute_git.py] {out_msg} (Exit code: {retcode})")
        if retcode != 0:
            with open(status_file, "w", encoding="utf-8") as f:
                f.write(f"[GIT ERROR] {out_msg}")
            sys.exit(retcode)
        else:
            with open(status_file, "w", encoding="utf-8") as f:
                f.write(f"[GIT SUCCESS] {data.get('speaking_response', 'Git action completed.')}")
            sys.exit(0)

    print(f"[Jarvis Executing]: '{command}' in '{target_repo}'")

    try:
        proc = subprocess.run(
            command,
            shell=True,
            cwd=target_repo,
            env=os.environ,
            capture_output=True,
            text=True
        )
        print(f"[execute_git.py] Process finished with exit code {proc.returncode}")
        if proc.stdout:
            print(f"[execute_git.py] Output:\n{proc.stdout.strip()}")
        if proc.stderr:
            print(f"[execute_git.py] Notice/Stderr:\n{proc.stderr.strip()}", file=sys.stderr)

        if proc.returncode != 0:
            err_details = proc.stderr.strip() or proc.stdout.strip() or f"Execution failed with code {proc.returncode}"
            print(f"[execute_git.py] Git execution FAILED: {err_details}", file=sys.stderr)
            try:
                with open(status_file, "w", encoding="utf-8") as f:
                    f.write(f"[GIT ERROR] {err_details}")
            except Exception:
                pass
            try:
                if os.path.exists(intent_file):
                    with open(intent_file, "r", encoding="utf-8") as inf:
                        idat = json.load(inf)
                    idat["speaking_error"] = f"Git operation failed, sir: {err_details[:80]}"
                    with open(intent_file, "w", encoding="utf-8") as inf:
                        json.dump(idat, inf, indent=2)
            except Exception:
                pass
            sys.exit(proc.returncode)

        # Execution succeeded
        try:
            with open(status_file, "w", encoding="utf-8") as f:
                f.write(f"[GIT SUCCESS] {data.get('speaking_response', 'Git action completed.')}")
        except Exception:
            pass
        sys.exit(0)
    except Exception as e:
        print(f"[execute_git.py] Execution error: {e}", file=sys.stderr)
        try:
            with open(status_file, "w", encoding="utf-8") as f:
                f.write(f"[GIT ERROR] {e}")
        except Exception:
            pass
        sys.exit(1)

if __name__ == "__main__":
    main()
