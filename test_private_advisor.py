"""Exercise the actual Linux privacy boundary without invoking paid model calls."""
import json,os,subprocess,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import private_advisor

class PrivateAdvisorTests(unittest.TestCase):
 def test_home_history_environment_and_host_processes_are_hidden(self):
  with tempfile.TemporaryDirectory(prefix='decklab-privacy-') as work:
   with patch.dict(os.environ,{'MARKET_DECK_SECRET':'qa-private','OPENAI_API_KEY':'qa-private'}):
    cmd,env=private_advisor.prepare('Codex',['codex'],work)
   code='''import pathlib,os,json,socket
h=pathlib.Path.home()
print(json.dumps({'project_hidden':not (h/'market-deck').exists(),
'memory_hidden':not (h/'AGENTS.md').exists(),
'history_hidden':not (h/'.codex/history.jsonl').exists(),
'auth_available':(h/'.codex/auth.json').is_file(),
'private_env_hidden':not any(k in os.environ for k in ['MARKET_DECK_SECRET','OPENAI_API_KEY']),
'private_pid_view':len([p for p in pathlib.Path('/proc').iterdir() if p.name.isdigit()])<=3,
'dns_works':bool(socket.getaddrinfo('api.kraken.com',443))}))'''
   cmd=cmd[:cmd.index('--')+1]+['/usr/bin/python3','-c',code]
   proc=subprocess.run(cmd,capture_output=True,text=True,env=env,timeout=15)
   self.assertEqual(proc.returncode,0,proc.stderr)
   self.assertTrue(all(json.loads(proc.stdout).values()),proc.stdout)
 def test_missing_sandbox_fails_closed(self):
  with tempfile.TemporaryDirectory() as work,patch('private_advisor.shutil.which',return_value=None):
   with self.assertRaisesRegex(ValueError,'sandbox unavailable'):private_advisor.prepare('Codex',['codex'],work)
 def test_agy_has_immutable_tool_denial_and_no_past_conversations(self):
  with tempfile.TemporaryDirectory(prefix='decklab-agy-privacy-') as work:
   cmd,env=private_advisor.prepare('AGY',['agy'],work)
   code='''import json,pathlib,subprocess
p=pathlib.Path.home()/'.agents'
h=json.loads((p/'hooks.json').read_text())['decklab-observation-only']['PreToolUse'][0]
result=subprocess.check_output(['/bin/sh','-c',h['hooks'][0]['command']],text=True)
blocked=False
try:(p/'hooks.json').write_text('{}')
except OSError:blocked=True
print(json.dumps({'deny':json.loads(result)['decision']=='deny','matches_all':h['matcher']=='*','immutable':blocked,'history_hidden':not (pathlib.Path.home()/'.gemini/antigravity-cli/history.jsonl').exists()}))'''
   cmd=cmd[:cmd.index('--')+1]+['/usr/bin/python3','-c',code]
   proc=subprocess.run(cmd,capture_output=True,text=True,env=env,timeout=15)
   self.assertEqual(proc.returncode,0,proc.stderr);self.assertTrue(all(json.loads(proc.stdout).values()),proc.stdout)
if __name__=='__main__':unittest.main(verbosity=2)
