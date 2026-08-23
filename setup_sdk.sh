#!/usr/bin/env bash
# WebToApp Forge — (re)instalacija minimalnog Android SDK-a (platforma + build-tools)
set -e
SDK="${ANDROID_SDK_ROOT:-$HOME/android-sdk}"
mkdir -p "$SDK/platforms" "$SDK/build-tools" /tmp/sdkz
cd /tmp/sdkz

python3 - <<'EOF'
import re, urllib.request
xml = urllib.request.urlopen("https://dl.google.com/android/repository/repository2-3.xml", timeout=90).read().decode("utf-8","ignore")
plats = sorted(set(re.findall(r'platform-\d+(?:-ext\d+)?_r\d+[\d.]*\.zip', xml)))
bts   = sorted(set(re.findall(r'build-tools_r\d+(?:\.\d+)?-linux\.zip', xml)))
open("/tmp/sdkz/urls.txt","w").write(plats[-1]+"\n"+bts[-1]+"\n")
print("platform:", plats[-1], "| build-tools:", bts[-1])
EOF

PLAT=$(sed -n 1p /tmp/sdkz/urls.txt); BT=$(sed -n 2p /tmp/sdkz/urls.txt)
curl -fSL --retry 3 -sS -o platform.zip "https://dl.google.com/android/repository/$PLAT"
curl -fSL --retry 3 -sS -o bt.zip "https://dl.google.com/android/repository/$BT"
rm -rf pf bt && mkdir -p pf bt
unzip -q -o platform.zip -d pf
unzip -q -o bt.zip -d bt
PF_DIR=$(ls pf | head -1); BT_DIR=$(ls bt | head -1)
API=$(echo "$PLAT" | grep -oP 'platform-\K\d+')
VER=$(echo "$BT" | grep -oP 'build-tools_r\K[0-9.]+(?=-linux)')
rm -rf "$SDK/platforms/android-$API" "$SDK/build-tools/$VER"
mv "pf/$PF_DIR" "$SDK/platforms/android-$API"
mv "bt/$BT_DIR" "$SDK/build-tools/$VER"
chmod -R +x "$SDK/build-tools/$VER"
echo "✅ SDK spreman: platforms/android-$API, build-tools/$VER"
