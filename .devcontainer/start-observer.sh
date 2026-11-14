#!/usr/bin/env bash
set -euo pipefail
if [[ "${CODESPACES:-}" != true ]]; then
  printf '%s\n' 'Observer autostart is restricted to GitHub Codespaces.'
  exit 1
fi
umask 077
mkdir -p data/observer
chmod 700 data data/observer
if python -c 'import urllib.request; urllib.request.urlopen("http://127.0.0.1:8790/api/health",timeout=2)' >/dev/null 2>&1; then
  exit 0
fi
nohup python observer_server.py >data/observer.log 2>&1 </dev/null &
printf '%s\n' 'Read-only live market observer starting. AI and execution remain disabled.'
