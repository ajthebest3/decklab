#!/usr/bin/env bash
set -euo pipefail
umask 077
mkdir -p data
chmod 700 data
if [[ ! -e data/owner-research-paused-until-asked ]]; then
  printf '%s\n' 'Development workspace: owner pause retained. No automatic research or simulation activation.' > data/owner-research-paused-until-asked
fi
chmod 600 data/owner-research-paused-until-asked
printf '%s\n' 'DeckLab source is ready. Research, simulation and HTTP workers were not started.'
printf '%s\n' 'Read README.md and docs/DEVELOPMENT.md before running isolated tests.'

if [[ "$(printenv CODESPACES)" == true ]]; then
  python .devcontainer/start-services.py --install-clis-only
fi
