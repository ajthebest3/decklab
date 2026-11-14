#!/usr/bin/env python3
"""Build a personal release APK. Signing secrets stay in the private server data dir."""
import hashlib, json, os, pathlib, secrets, shutil, subprocess
ROOT=pathlib.Path(__file__).resolve().parent
TOOLS=pathlib.Path.home()/'.local/share/market-deck-build'
for asset in ('day-trader.html','day-trader.js','day-trader.css','coverage.js','demo.js','demo.css','ai-settings.js','admin.js','terminal.js','terminal.css'):shutil.copy2(ROOT.parent/'static'/asset,ROOT/'app/src/main/assets'/asset)
shutil.copytree(ROOT.parent/'static/vendor',ROOT/'app/src/main/assets/vendor',dirs_exist_ok=True)
env=dict(os.environ)
env.setdefault('JAVA_HOME',str(TOOLS/'jdk'))
env.setdefault('ANDROID_HOME',str(pathlib.Path.home()/'.local/share/android-sdk'))
env['PATH']=env['JAVA_HOME']+'/bin:'+env.get('PATH','')
private=ROOT.parent/'data';private.mkdir(mode=0o700,exist_ok=True)
config=private/'android-signing.json';keystore=private/'android-release.jks'
if not config.exists():
    with open(os.open(config,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'w') as out:
        json.dump({'password':secrets.token_urlsafe(40)},out)
env['MARKET_DECK_SIGNING_PASSWORD']=json.loads(config.read_text())['password']
env['MARKET_DECK_KEYSTORE']=str(keystore)
if not keystore.exists():
    subprocess.run(['keytool','-genkeypair','-keystore',str(keystore),'-storepass:env','MARKET_DECK_SIGNING_PASSWORD','-keypass:env','MARKET_DECK_SIGNING_PASSWORD','-alias','market-deck','-keyalg','RSA','-keysize','3072','-validity','10000','-dname','CN=Market Deck Personal, OU=Personal Android, O=Market Deck'],env=env,check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    keystore.chmod(0o600)
subprocess.run([str(ROOT/'gradlew'),'--no-daemon',':app:assembleRelease',':app:lintRelease'],cwd=ROOT,env=env,check=True)
dist=ROOT/'dist';dist.mkdir(exist_ok=True)
target=dist/'market-deck.apk'
staged=dist/'market-deck.apk.new'
shutil.copy2(ROOT/'app/build/outputs/apk/release/app-release.apk',staged)
subprocess.run([env['ANDROID_HOME']+'/build-tools/36.0.0/apksigner','verify','--verbose',str(staged)],env=env,check=True)
staged.replace(target)
digest=hashlib.sha256(target.read_bytes()).hexdigest()
(dist/'SHA256SUMS').write_text(digest+'  market-deck.apk\n')
print('Signed APK:',target)
print('SHA-256:',digest)
