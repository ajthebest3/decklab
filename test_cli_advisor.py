import unittest
from tools.cli_advisor import command
from mirai_client import MiraiClient
class CLITests(unittest.TestCase):
 def test_codex(self):self.assertIn("read-only",command("codex","x"))
 def test_claude(self):self.assertEqual(command("claude","x")[0],"claude")
 def test_agy(self):self.assertIn("--dangerously-skip-permissions",command("agy","x"))
 def test_api_disabled(self):
  c=MiraiClient(".");self.assertFalse(c.status()["enabled"])
  with self.assertRaises(ValueError):c.request("/chat/completions",{})
if __name__=="__main__":unittest.main()
