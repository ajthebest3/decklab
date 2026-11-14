"""Fresh advisor homes: no project, previous conversations, or inherited app secrets."""
import json, os, shutil, tomllib
from pathlib import Path

def prepare(bot, command, work):
    if not shutil.which('bwrap'):
        raise ValueError('Private advisor sandbox unavailable; demo decision deferred')
    work=Path(work).resolve();home=work/'advisor-home';home.mkdir(mode=0o700)
    original=Path.home();binary=Path(shutil.which(command[0]) or '').resolve()
    if not binary.is_file():raise ValueError('Advisor executable unavailable')
    executable=work/command[0];executable.touch(mode=0o500)
    if bot=='Codex':
        dest=home/'.codex';dest.mkdir(mode=0o700)
        auth=original/'.codex/auth.json'
        if not auth.is_file():raise ValueError('Private Codex login unavailable')
        shutil.copy2(auth,dest/'auth.json')
        source=original/'.codex/config.toml'
        config=tomllib.loads(source.read_text()) if source.is_file() else {}
        (dest/'config.toml').write_text('\n'.join(k+' = '+json.dumps(config[k]) for k in ('model','model_reasoning_effort') if k in config))
    else:
        dest=home/'.gemini/antigravity-cli';dest.mkdir(parents=True,mode=0o700)
        for name in ('antigravity-oauth-token','installation_id','jetski_state.pbtxt'):
            source=original/'.gemini/antigravity-cli'/name
            if source.is_file():shutil.copy2(source,dest/name)
        # AGY's documented PreToolUse hard-deny contract applies even in auto-approval mode.
        hooks={'decklab-observation-only':{'PreToolUse':[{'matcher':'*','hooks':[{
            'type':'command','command':"printf '%s' '{\"decision\":\"deny\",\"reason\":\"DeckLab advisors use supplied observations only.\"}'"}]}]}}
        for customization in (home/'.agents',work/'.agents'):
            customization.mkdir(mode=0o700)
            (customization/'hooks.json').write_text(json.dumps(hooks))
        (dest/'settings.json').write_text(json.dumps({'permissions':{'deny':['*']}}))
    # Bind a fresh home at the same path, and mount only this executable back in.
    # /proc is a private PID view, so another process's root/fds cannot reveal data.
    sandbox=['bwrap','--die-with-parent','--unshare-pid','--ro-bind','/','/',
             '--proc','/proc','--dev','/dev','--tmpfs','/home','--tmpfs','/tmp',
             '--tmpfs','/run','--ro-bind',str(Path('/etc/resolv.conf').resolve()),str(Path('/etc/resolv.conf').resolve()),
             '--bind',str(work),str(work),
             '--bind',str(home),str(original),
             '--ro-bind',str(binary),str(executable),'--chdir',str(work)]
    # CLI hooks and settings cannot be edited by a proposed tool call.
    if bot=='AGY':
        sandbox+=['--ro-bind',str(dest/'settings.json'),str(original/'.gemini/antigravity-cli/settings.json'),
                  '--ro-bind',str(home/'.agents'),str(original/'.agents'),
                  '--ro-bind',str(work/'.agents'),str(work/'.agents')]
    env={k:v for k,v in os.environ.items() if k in ('PATH','LANG','LC_ALL','TZ','SSL_CERT_FILE','SSL_CERT_DIR')}
    env.update(HOME=str(original),PATH='/usr/local/bin:/usr/bin:/bin')
    sandbox+=['--setenv','HOME',str(original),'--setenv','PATH',env['PATH'],'--',str(executable),*command[1:]]
    return sandbox,env
