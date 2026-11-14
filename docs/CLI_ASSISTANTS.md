# Codex, Claude and AGY CLI

The live website never invokes AI. These CLIs are optional **manual developer tools in the Codespace terminal**.

The development bootstrap installs CLI binaries from their official distributions in the new Codespace. It does not copy or create provider credentials and does not send a prompt. Installation may take longer than the observer startup; see data/cli-install.log.

## Check availability

~~~bash
python tools/cli_advisor.py --status
~~~

Sign in through each CLI's own interactive/browser login before asking it to work. A new Codespace is not logged in merely because another machine is logged in.

## Deliberate use

~~~bash
python tools/cli_advisor.py --provider codex "Review the observer isolation tests"
python tools/cli_advisor.py --provider claude "Explain the read-only architecture"
python tools/cli_advisor.py --provider agy "Review the public market source labels"
~~~

The launcher uses the installed executable, enforces a process timeout and never retries automatically. AGY uses plan mode, sandbox and the owner's requested permission flag. CLI execution is deliberate and separate from public visitors; prompts can consume the chosen provider's subscription or usage.

## Official sources

- Codex: https://github.com/openai/codex
- Claude Code: https://github.com/anthropics/claude-code
- Antigravity CLI: https://github.com/google-antigravity/antigravity-cli

There is no configured AI API gateway or API-key form in the public profile. The historical compatibility class returns disabled status and rejects requests/configuration. Private credentials and original machine logins are not part of Git or Codespace setup.

This does not claim Claude is already integrated into every historical bot/privacy boundary. The supported three-provider entry point here is the explicit manual CLI launcher; automated full-backend advisor workflows need their own provider/privacy validation.
