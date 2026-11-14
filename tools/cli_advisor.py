#!/usr/bin/env python3
"""Optional manual CLI launcher. Never imported or invoked by the public observer."""
import argparse,shutil,subprocess,sys
PROVIDERS={"codex":"codex","claude":"claude","agy":"agy"}
def command(provider,prompt):
    if provider=="codex":return ["codex","exec","--skip-git-repo-check","--ephemeral","-s","read-only",prompt]
    if provider=="claude":return ["claude","-p",prompt,"--no-session-persistence"]
    if provider=="agy":return ["agy","--dangerously-skip-permissions","--mode","plan","--sandbox","--disable-slash-commands","--print-timeout","180s","-p",prompt]
    raise ValueError("Unknown CLI provider")
def main():
    p=argparse.ArgumentParser(description="Manual developer CLI access; public website remains AI-free")
    p.add_argument("--provider",choices=PROVIDERS);p.add_argument("--status",action="store_true");p.add_argument("prompt",nargs="?");a=p.parse_args()
    if a.status:
        for name,exe in PROVIDERS.items():print(name+": "+(shutil.which(exe) or "not installed"))
        return
    if not a.provider:p.error("Choose --provider or --status")
    prompt=a.prompt or sys.stdin.read()
    if not prompt.strip():p.error("A prompt is required")
    if not shutil.which(PROVIDERS[a.provider]):p.error("CLI not installed")
    try:raise SystemExit(subprocess.run(command(a.provider,prompt),timeout=240).returncode)
    except subprocess.TimeoutExpired:p.exit(1,"CLI timed out; no automatic retry.\n")
if __name__=="__main__":main()
