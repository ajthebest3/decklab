"""Codespace lifecycle: detach services from the hook process group."""
import os,sys,json,subprocess,time,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if os.environ.get("CODESPACES")!="true":raise SystemExit("Codespace-only lifecycle")
data=ROOT/"data";data.mkdir(exist_ok=True);data.chmod(0o700)
def spawn(args,log):
    with (data/log).open("ab",buffering=0) as out:
        return subprocess.Popen(args,cwd=ROOT,stdin=subprocess.DEVNULL,stdout=out,stderr=subprocess.STDOUT,start_new_session=True)
def healthy():
    try:
        with urllib.request.urlopen("http://127.0.0.1:8790/api/health",timeout=2) as r:
            return json.load(r).get("mode")=="live-observation"
    except Exception:return False
if "--install-clis-only" not in sys.argv and not healthy():
    process=spawn([sys.executable,"-u",str(ROOT/"observer_server.py")],"observer.log")
    (data/"observer.pid").write_text(str(process.pid))
    for _ in range(40):
        if healthy():break
        if process.poll() is not None:raise SystemExit("Observer failed; inspect data/observer.log")
        time.sleep(.25)
    if not healthy():raise SystemExit("Observer is not ready; inspect data/observer.log")
bin_dir=Path.home()/".local/bin"
installed=all((bin_dir/n).exists() for n in ["codex","claude","agy"])
pidfile=data/"cli-install.pid";running=False
try:
    pid=int(pidfile.read_text())
    running=b"install-clis.sh" in (Path("/proc")/str(pid)/"cmdline").read_bytes()
except (OSError,ValueError):pass
if not installed and not running:
    child=spawn(["bash",str(ROOT/".devcontainer/install-clis.sh")],"cli-install.log")
    pidfile.write_text(str(child.pid))
print("Read-only observer prepared; optional CLI installation is separate. No model invoked.")
