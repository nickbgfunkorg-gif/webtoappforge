#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WebToApp Forge — engine koji od URL-a sajta pravi pravi, potpisan Android APK.
Koraci: aapt2 (resurse) -> javac -> d8 (dex) -> zip -> zipalign -> apksigner.
"""
import base64
import glob
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
from xml.sax.saxutils import escape

BASE = os.path.dirname(os.path.abspath(__file__))
HOME = os.path.expanduser("~")
SDK_HOME = os.environ.get("ANDROID_SDK_ROOT", os.path.join(HOME, "android-sdk"))
KEYS_DIR = os.environ.get("FORGE_KEYS_DIR", os.path.join(BASE, "keys"))
KEY_PK8 = os.path.join(KEYS_DIR, "forge-key.pk8")
KEY_CERT = os.path.join(KEYS_DIR, "forge-cert.pem")
DEFAULT_ICON = os.path.join(BASE, "default-icon.png")


class ForgeError(Exception):
    pass


def _pick(pattern, what):
    items = sorted(glob.glob(pattern), reverse=True)
    if not items:
        raise ForgeError(f"Nije pronađen {what} ({pattern}). Pokreni setup_sdk.sh!")
    return items[0]


def sdk_tools():
    jar = _pick(os.path.join(SDK_HOME, "platforms", "*", "android.jar"), "android.jar")
    bt = _pick(os.path.join(SDK_HOME, "build-tools", "*"), "build-tools")
    tools = {t: os.path.join(bt, t) for t in ("aapt2", "d8", "zipalign", "apksigner")}
    for t, p in tools.items():
        if not os.path.exists(p):
            raise ForgeError(f"Nedostaje alat: {p}")
    return jar, tools


def sdk_ready():
    try:
        sdk_tools()
        return True
    except ForgeError:
        return False


def ensure_keys(log=lambda *a: None):
    """Generiše self-signed sertifikat (RSA 2048) za potpis APK-ova ako ne postoji."""
    if os.path.exists(KEY_PK8) and os.path.exists(KEY_CERT):
        return
    os.makedirs(KEYS_DIR, exist_ok=True)
    raw = os.path.join(KEYS_DIR, "forge-raw.pem")
    log("🔑 Pravim novi potpisni ključ (self-signed)...")
    subprocess.run(
        ["openssl", "req", "-x509", "-newkey", "rsa:2048", "-keyout", raw,
         "-out", KEY_CERT, "-days", "10000", "-nodes",
         "-subj", "/CN=WebToApp Forge/O=WebToApp Forge/C=MT"],
        check=True, capture_output=True)
    subprocess.run(
        ["openssl", "pkcs8", "-topk8", "-outform", "DER", "-inform", "PEM",
         "-in", raw, "-out", KEY_PK8, "-nocrypt"],
        check=True, capture_output=True)
    os.remove(raw)


def run(cmd, log, cwd=None):
    log("$ " + " ".join(os.path.basename(c) if i == 0 else c for i, c in enumerate(cmd))[:700])
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                       text=True, cwd=cwd)
    lines = (p.stdout or "").strip().splitlines()
    for l in lines[:40]:
        log("  " + l)
    if len(lines) > 40:
        log(f"  ... ({len(lines) - 40} linija skraćeno)")
    if p.returncode != 0:
        raise ForgeError(f"Korak '{os.path.basename(cmd[0])}' pao (exit {p.returncode}). Vidi log iznad.")
    return "\n".join(lines)


# ---------------------------------------------------------------- templejti

MANIFEST = """<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android"
    package="%PKG%" android:versionCode="%VCODE%" android:versionName="%VNAME%">
    <uses-sdk android:minSdkVersion="21" android:targetSdkVersion="36" />
    <uses-permission android:name="android.permission.INTERNET" />
    <uses-permission android:name="android.permission.ACCESS_NETWORK_STATE" />
    <application
        android:label="@string/app_name"
        android:icon="@drawable/ic_launcher"
        android:allowBackup="true"
        android:usesCleartextTraffic="true"
        android:hardwareAccelerated="true"
        android:theme="@android:style/Theme.Material.NoActionBar">
        <activity android:name=".MainActivity" android:exported="true"
            android:launchMode="singleTask"
            android:configChanges="orientation|screenSize|screenLayout|smallestScreenSize|keyboardHidden|uiMode|density|fontScale">
            <intent-filter>
                <action android:name="android.intent.action.MAIN" />
                <category android:name="android.intent.category.LAUNCHER" />
            </intent-filter>
        </activity>
    </application>
</manifest>
"""

STRINGS = """<?xml version="1.0" encoding="utf-8"?>
<resources>
    <string name="app_name">%APPNAME%</string>
    <string name="start_url">%URL%</string>
</resources>
"""

ACTIVITY = """package %PKG%;

import android.app.Activity;
import android.os.Bundle;
import android.view.View;
import android.webkit.WebChromeClient;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.LinearLayout;
import android.widget.ProgressBar;

public class MainActivity extends Activity {
    private WebView web;
    private ProgressBar bar;

    @Override
    protected void onCreate(Bundle saved) {
        super.onCreate(saved);
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        bar = new ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal);
        bar.setMax(100);
        bar.setVisibility(View.GONE);
        root.addView(bar, new LinearLayout.LayoutParams(-1, 6));
        web = new WebView(this);
        root.addView(web, new LinearLayout.LayoutParams(-1, 0, 1f));
        setContentView(root);

        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setDatabaseEnabled(true);
        s.setLoadWithOverviewMode(true);
        s.setUseWideViewPort(true);
        // Zakljucaj prikaz na 100% — sprecava "zumiran" prikaz na telefonima
        // gde je u podesavanjima uvecan sistemski font/display size.
        s.setTextZoom(100);
%ZOOM%
        s.setMediaPlaybackRequiresUserGesture(false);
        s.setMixedContentMode(WebSettings.MIXED_CONTENT_COMPATIBILITY_MODE);
        s.setAllowFileAccess(true);
        s.setJavaScriptCanOpenWindowsAutomatically(true);

        web.setWebViewClient(new WebViewClient() {
            @Override
            public void onPageFinished(WebView view, String url) {
                super.onPageFinished(view, url);
                // Ako stranica nema viewport meta tag, ubaci ga — bez njega se
                // sajt na nekim telefonima prikazuje uvecan/odsecen.
                view.evaluateJavascript(
                    "(function(){var m=document.querySelector('meta[name=viewport]');"
                    + "if(!m){m=document.createElement('meta');m.name='viewport';"
                    + "m.content='width=device-width, initial-scale=1.0';"
                    + "document.head.appendChild(m);}})();", null);
            }
        });
        web.setWebChromeClient(new WebChromeClient() {
            @Override
            public void onProgressChanged(WebView v, int p) {
                bar.setVisibility(p < 100 ? View.VISIBLE : View.GONE);
                bar.setProgress(p);
            }
        });

        if (saved != null) {
            web.restoreState(saved);
        } else {
            web.loadUrl(getString(R.string.start_url));
        }
    }

    @Override
    protected void onSaveInstanceState(Bundle out) {
        super.onSaveInstanceState(out);
        if (web != null) web.saveState(out);
    }

    @Override
    public void onBackPressed() {
        if (web != null && web.canGoBack()) {
            web.goBack();
        } else {
            super.onBackPressed();
        }
    }
}
"""

# ---------------------------------------------------------------- pomoćne

PKG_RE = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$")


def slugify(s, default="app"):
    s = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
    return s or default


def normalize_url(url):
    url = (url or "").strip()
    if not url:
        raise ForgeError("URL sajta je prazan.")
    if not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", url):
        url = "https://" + url
    m = re.match(r"^https?://[^\s/]+", url)
    if not m:
        raise ForgeError(f"Neispravan URL: {url}")
    return url


def normalize_pkg(pkg, fallback_name):
    pkg = (pkg or "").strip().lower()
    if not pkg:
        pkg = "com.webtoapp." + re.sub(r"[^a-z0-9]+", "", fallback_name.lower())[:20]
    if not PKG_RE.match(pkg):
        raise ForgeError(f"Neispravan package name: '{pkg}' (primer: com.mojafirma.app)")
    return pkg


def version_parts(vname):
    parts = [int(p) for p in re.findall(r"\d+", vname or "1.0")[:3]] or [1, 0]
    while len(parts) < 3:
        parts.append(0)
    return parts[0] * 10000 + parts[1] * 100 + parts[2]


def make_icon(png_bytes, dest):
    try:
        from PIL import Image
        im = Image.open(io.BytesIO(png_bytes)).convert("RGBA")
        im.thumbnail((192, 192), Image.LANCZOS)
        canvas = Image.new("RGBA", (192, 192), (0, 0, 0, 0))
        canvas.paste(im, ((192 - im.width) // 2, (192 - im.height) // 2))
        canvas.save(dest, "PNG")
    except Exception:
        with open(dest, "wb") as f:
            f.write(png_bytes)


# ---------------------------------------------------------------- glavna funkcija

def forge(url, app_name, package="", version_name="1.0", icon_bytes=None,
          allow_zoom=False, log=print):
    """Kompletan build. Vraća putanju do potpisanog APK-a."""
    url = normalize_url(url)
    app_name = (app_name or "").strip() or "Web Aplikacija"
    if len(app_name) > 40:
        raise ForgeError("Ime aplikacije je predugačko (max 40 karaktera).")
    package = normalize_pkg(package, app_name)
    version_name = (version_name or "1.0").strip()
    version_code = version_parts(version_name)
    ensure_keys(log)
    jar, tools = sdk_tools()

    log(f"🔥 FORGE start: «{app_name}» → {url}")
    log(f"   paket={package}  verzija={version_name} ({version_code})  "
        f"zumiranje={'UKLJUČENO' if allow_zoom else 'isključeno'}")
    log("📌 Prikaz fiksiran na 100% (textZoom) + auto viewport meta tag.")

    work = tempfile.mkdtemp(prefix="forge_")
    try:
        # --- struktura projekta
        res = os.path.join(work, "res")
        os.makedirs(os.path.join(res, "values"))
        os.makedirs(os.path.join(res, "drawable"))
        srcdir = os.path.join(work, "src", *package.split("."))
        os.makedirs(srcdir)

        if allow_zoom:
            zoom_settings = ("        s.setSupportZoom(true);\n"
                             "        s.setBuiltInZoomControls(true);\n"
                             "        s.setDisplayZoomControls(false);")
        else:
            zoom_settings = ("        s.setSupportZoom(false);\n"
                             "        s.setBuiltInZoomControls(false);")

        def W(path, text):
            with open(os.path.join(work, path), "w", encoding="utf-8") as f:
                f.write(text)

        W("AndroidManifest.xml",
          MANIFEST.replace("%PKG%", package)
                  .replace("%VCODE%", str(version_code))
                  .replace("%VNAME%", escape(version_name)))
        W("res/values/strings.xml",
          STRINGS.replace("%APPNAME%", escape(app_name))
                 .replace("%URL%", escape(url)))
        W(os.path.join("src", *package.split("."), "MainActivity.java"),
          ACTIVITY.replace("%PKG%", package)
                  .replace("%ZOOM%", zoom_settings))

        if icon_bytes is None and os.path.exists(DEFAULT_ICON):
            with open(DEFAULT_ICON, "rb") as f:
                icon_bytes = f.read()
        if icon_bytes is None:
            raise ForgeError("Nema ikonice (default-icon.png nedostaje).")
        make_icon(icon_bytes, os.path.join(res, "drawable", "ic_launcher.png"))
        log("🎨 Ikonica spremna (192x192).")

        # --- 1) aapt2 compile + link
        log("📦 [1/6] aapt2 compile resursa…")
        run([tools["aapt2"], "compile", "--dir", "res", "-o", "res.zip"], log, cwd=work)
        run([tools["aapt2"], "link", "-o", "unsigned.apk", "-I", jar,
             "--manifest", "AndroidManifest.xml", "--java", "gen", "res.zip"], log, cwd=work)

        # --- 2) javac
        log("☕ [2/6] javac kompajliranje…")
        sources = []
        for base in ("gen", "src"):
            for r, _d, files in os.walk(os.path.join(work, base)):
                sources += [os.path.relpath(os.path.join(r, f), work)
                            for f in files if f.endswith(".java")]
        run(["javac", "--release", "8", "-encoding", "UTF-8",
             "-cp", jar, "-d", "classes"] + sources, log, cwd=work)

        # --- 3) d8 dex
        log("🤖 [3/6] d8 DEX konverzija…")
        os.makedirs(os.path.join(work, "dex"), exist_ok=True)
        classes = []
        for r, _d, files in os.walk(os.path.join(work, "classes")):
            classes += [os.path.relpath(os.path.join(r, f), work)
                        for f in files if f.endswith(".class")]
        run([tools["d8"], "--min-api", "21", "--lib", jar,
             "--output", "dex"] + classes, log, cwd=work)

        # --- 4) upakuj classes.dex u APK
        log("🗜️  [4/6] Pakovanje classes.dex…")
        run(["zip", "-qj9", "unsigned.apk", "dex/classes.dex"], log, cwd=work)

        # --- 5) zipalign
        log("📐 [5/6] zipalign…")
        run([tools["zipalign"], "-f", "-p", "4", "unsigned.apk", "aligned.apk"], log, cwd=work)

        # --- 6) potpis
        log("✍️  [6/6] apksigner potpisivanje…")
        out_apk = os.path.join(work, "final.apk")
        run([tools["apksigner"], "sign", "--key", KEY_PK8, "--cert", KEY_CERT,
             "--out", out_apk, "aligned.apk"], log, cwd=work)

        # --- verifikacija
        log("🔍 Verifikacija potpisa i paketa…")
        run([tools["apksigner"], "verify", out_apk], log, cwd=work)
        badging = run([tools["aapt2"], "dump", "badging", out_apk], log, cwd=work)
        for line in badging.splitlines():
            if line.startswith(("package:", "application-label:", "launchable-activity:")):
                log("  ✓ " + line)

        import uuid
        dest_dir = os.environ.get("FORGE_OUT_DIR", os.path.join(BASE, "out"))
        os.makedirs(dest_dir, exist_ok=True)
        final = os.path.join(dest_dir,
                             f"{slugify(app_name)}-{version_name}-{uuid.uuid4().hex[:6]}.apk")
        shutil.copy(out_apk, final)
        size = os.path.getsize(final) / (1024 * 1024)
        log(f"✅ GOTOVO! APK: {os.path.basename(final)} ({size:.1f} MB)")
        return final
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="WebToApp Forge — CLI")
    ap.add_argument("url", help="URL sajta, npr. https://example.com")
    ap.add_argument("name", help="Ime aplikacije")
    ap.add_argument("--package", default="")
    ap.add_argument("--version", default="1.0")
    ap.add_argument("--icon", default=None, help="Putanja do PNG ikonice")
    ap.add_argument("--zoom", action="store_true",
                    help="Dozvoli pinch-to-zoom (po defaultu isključeno, prikaz fiksan na 100%%)")
    args = ap.parse_args()
    icon = open(args.icon, "rb").read() if args.icon else None
    try:
        apk = forge(args.url, args.name, args.package, args.version, icon,
                    allow_zoom=args.zoom)
        print("\nAPK:", apk)
    except ForgeError as e:
        print("\n❌ " + str(e))
        sys.exit(1)
