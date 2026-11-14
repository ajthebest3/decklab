"""Compatibility boundary for historical imports. This public distribution is CLI-only."""
import re

def model_id(value):
    if not isinstance(value,str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/:+@-]{0,199}",value):raise ValueError("Invalid model ID")
    return value

def redact(value):
    return re.sub(r"\bsk-[A-Za-z0-9_-]{8,}","[redacted credential]",str(value))

class MiraiClient:
    def __init__(self,data):self.last_error="External AI API connections are disabled; use Codex, Claude or AGY CLI manually."
    def config(self):return {}
    def status(self):return dict(enabled=False,key_configured=False,backup_configured=False,model="",base_url="",catalog_error=self.last_error)
    def checks(self):return {}
    def models(self,refresh=False):return dict(models=[],fetched=None,source="disabled",stale=False,error=self.last_error,access_verified=False,access_error=self.last_error)
    def safe_text(self,value,cfg=None):return redact(value)
    def request(self,*a,**k):raise ValueError(self.last_error)
    def save(self,*a,**k):raise ValueError(self.last_error)
    def validate_model(self,*a,**k):raise ValueError(self.last_error)
    def test_model(self,*a,**k):raise ValueError(self.last_error)
    def complete(self,*a,**k):raise ValueError(self.last_error)
    def complete_details(self,*a,**k):raise ValueError(self.last_error)
