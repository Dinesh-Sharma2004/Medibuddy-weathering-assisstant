"""Scan the working tree and the full git history for likely API keys / secrets. Reports; never rewrites history.
    python scripts/audit_secrets.py
Exit code 1 if anything suspicious is found (stop and report; do not rewrite history automatically)."""
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PATTERNS = {
    "OpenAI-style key (sk-...)": r"sk-(?:proj-|svcacct-)?[A-Za-z0-9_\-]{20,}",
    "Groq key (gsk_...)": r"gsk_[A-Za-z0-9]{20,}",
    "Anthropic key (sk-ant-...)": r"sk-ant-[A-Za-z0-9_\-]{20,}",
    "Google API key (AIza...)": r"AIza[0-9A-Za-z_\-]{30,}",
    "GitHub token": r"gh[pousr]_[A-Za-z0-9]{30,}",
    "AWS access key id": r"AKIA[0-9A-Z]{16}",
    "Private key block": r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
    "Slack token": r"xox[baprs]-[A-Za-z0-9\-]{10,}",
    "Assigned secret (KEY/TOKEN/SECRET = long literal)":
        r"(?i)\b[A-Z0-9_]*(?:API_?KEY|SECRET|TOKEN|PASSWORD)[A-Z0-9_]*\s*[:=]\s*['\"]?(?!your-|<|TODO|changeme|\$)[A-Za-z0-9_\-/+=]{24,}",
}
SKIP_DIRS = {"venv", ".venv", ".git", "__pycache__", "node_modules", ".pytest_cache"}


def scan_text(text, where, hits):
    for name, pat in PATTERNS.items():
        for m in re.finditer(pat, text):
            hits.append((name, where, f"<redacted, {len(m.group(0))} chars>"))


def main():
    hits, nfiles = [], 0
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]   # prune: never descend into venv/.git
        for name in filenames:
            f = Path(dirpath) / name
            try:
                text = f.read_text(errors="ignore")
            except OSError:
                continue
            nfiles += 1
            scan_text(text, str(f.relative_to(ROOT)), hits)
    env = ROOT / ".env"
    print(f"working tree: scanned {nfiles} files (skipping {sorted(SKIP_DIRS)}); .env present: {env.exists()} "
          f"(gitignored: {'.env' in (ROOT / '.gitignore').read_text().split()})")
    try:
        n = subprocess.check_output(["git", "-C", str(ROOT), "rev-list", "--all", "--count"], text=True,
                                    stderr=subprocess.DEVNULL).strip()
    except Exception:
        n = "0"
    if n != "0":
        log = subprocess.check_output(["git", "-C", str(ROOT), "log", "--all", "-p", "--no-color"], text=True,
                                      errors="ignore")
        scan_text(log, "git history", hits)
        names = subprocess.check_output(["git", "-C", str(ROOT), "log", "--all", "--name-only", "--pretty=format:"],
                                        text=True, errors="ignore").split()
        if any(Path(x).name == ".env" or x.endswith("secrets.toml") for x in names):
            hits.append(("secret file committed in history", ".env or secrets.toml", ""))
    print(f"git history: {n} commit(s) scanned")
    def ignored(where):
        if where == "git history":
            return False
        r = subprocess.run(["git", "-C", str(ROOT), "check-ignore", "-q", where], capture_output=True)
        return r.returncode == 0
    safe = [h for h in hits if ignored(h[1])]
    bad = [h for h in hits if h not in safe]
    for h in safe:
        print("  info (gitignored, will not be committed):", h)
    if bad:
        print("\nLIKELY SECRETS FOUND IN COMMITTABLE FILES OR HISTORY - STOP AND REPORT (history is NOT rewritten):")
        for h in bad:
            print("  ", h)
        sys.exit(1)
    print("no likely API keys / secrets found")


if __name__ == "__main__":
    main()
