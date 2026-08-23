# 🔥 WebToApp Forge

Pretvara **bilo koji sajt** u pravi, potpisan **Android .apk** (WebView aplikacija).
Ukucaš URL → klikneš **⚒️ FORGE APK** → preuzmeš APK spreman za telefon.

---

## 🚀 Deploy na Render (preporučeno)

Repo je spreman za Render **Docker** deploy — sve se instalira automatski (Java + Android SDK).

1. **GitHub:** napravi novi repo (npr. `webtoapp-forge`) i uploaduj SVE fajlove iz ovog projekta
   (`server.py`, `forge_engine.py`, `index.html`, `setup_sdk.sh`, `default-icon.png`,
   `Dockerfile`, `render.yaml`, `.gitignore`, `.dockerignore`, `README.md`).
2. **Render:** Dashboard → **New → Web Service** → poveži GitHub repo.
   Render sam detektuje `Dockerfile` → klikni **Deploy**.
   (Ili: **New → Blueprint** i Render pročita `render.yaml` sam.)
3. Sačekaj build ~5–10 min (skida Android SDK) → dobijaš javni URL, npr.
   `https://webtoapp-forge.onrender.com` — i forge radi 24/7.

> ℹ️ Free plan: servis "spava" posle 15 min bez aktivnosti; prvi klik posle toga sačeka ~30 s
> da se probudi (cold start) — normalno.

### Trajni potpisni ključ (važno za update aplikacija)

Na besplatnom planu fajl sistem je privremen → potpisni ključ se regeneriše pri svakom
redeploy/restartu, pa telefon neće dozvoliti **update** aplikacije preko stare (potpis se razlikuje;
rešenje: deinstaliraj staru pa instaliraj novu). Za stabilan ključ:
Render servis → **Disks** → dodaj disk (npr. 1 GB) mountovan na `/var/data`, pa u
**Environment** dodaj:

```
FORGE_KEYS_DIR=/var/data/keys
FORGE_OUT_DIR=/var/data/out
```

---

## 💻 Lokalno pokretanje

Potrebno: Python 3, JDK (`javac`), `zip`, `unzip`, `curl`, `openssl`.

```bash
bash setup_sdk.sh        # jednokratno: skida minimalni Android SDK
python3 server.py        # http://localhost:8080  (ili PORT env)
```

## ⚒️ CLI (bez weba)

```bash
python3 forge_engine.py "https://moj-sajt.com" "Moja App" \
    --package com.mojafirma.app --version 1.0 --icon ikonica.png
```

APK završi u `out/`.

## 🔧 Kako radi (pravi build, bez lažnjaka)

1. `aapt2 compile` + `link` — resursi i manifest (pravi Android SDK)
2. `javac --release 8` — `MainActivity.java` (WebView omotač)
3. `d8` — `.class` → `classes.dex`
4. `zip` + `zipalign` — dex u APK + poravnanje
5. `apksigner --key/--cert` — potpis (self-signed, generiše openssl)
6. `apksigner verify` + `aapt2 dump badging` — provera

## 📁 Fajlovi

| Fajl | Uloga |
|---|---|
| `server.py` | web server (stdlib, čita `PORT`) |
| `forge_engine.py` | engine koji kova APK |
| `index.html` | web interfejs |
| `Dockerfile` | Render/Docker image (Java + SDK + app) |
| `render.yaml` | Render Blueprint (opciono) |
| `setup_sdk.sh` | download minimalnog Android SDK-a |
| `default-icon.png` | podrazumevana ikonica |
| `keys/` | potpisni ključ (auto-generiše se; ne commituj) |
| `out/` | iskovani APK-ovi (ne commituj) |

## 📱 Napomene

- **Instalacija na telefon:** otvori APK i dozvoli „Install unknown apps".
- **Google Play:** APK je tehnički validan; za prodavnicu ga prepotpiši sopstvenim keystore-om.
- Aplikacija je WebView omotač: sajt preko celog ekrana, back dugme, progress bar,
  JavaScript + localStorage uključeni.
