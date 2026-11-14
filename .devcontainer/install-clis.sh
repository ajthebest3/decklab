#!/usr/bin/env bash
set -euo pipefail
if [[ "$CODESPACES" != true ]]; then exit 1; fi
mkdir -p "$HOME/.local/bin"
export PATH="$HOME/.local/bin:$PATH"
npm install --global --prefix "$HOME/.local" @openai/codex
curl --fail --silent --show-error --location https://claude.ai/install.sh --output /tmp/decklab-claude-install.sh
bash /tmp/decklab-claude-install.sh
curl --fail --silent --show-error --location https://antigravity.google/cli/install.sh --output /tmp/decklab-agy-install.sh
bash /tmp/decklab-agy-install.sh
printf '%s\n' 'CLI binaries installed. Sign in to each separately if desired. No model was invoked; no credentials were copied.'
