#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WebToApp Forge — web server (samo stdlib, bez eksternih zavisnosti)."""
import base64
import binascii
import json
import os
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

import forge_engine

BASE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.environ.get("FORGE_OUT_DIR", os.path.join(BASE, "out"))
JOBS = {}
JOBS_LOCK = threading.Lock()
MAX_ICON = 3 * 1024 * 1024


class Job(dict):
    def __init__(self):
        super().__init__(state="building", log=[], apk=None, apk_name=None,
                         size_mb=None, error=None)

    def log_line(self, msg):
        with JOBS_LOCK:
            self["log"].append(str(msg))


def run_job(job_id, payload):
    job = JOBS[job_id]

    def log(m):
        print(f"[{job_id[:6]}] {m}", flush=True)
        job.log_line(m)

    try:
        icon = None
        if payload.get("icon_b64"):
            try:
                icon = base64.b64decode(payload["icon_b64"], validate=True)
                if len(icon) > MAX_ICON:
                    raise forge_engine.ForgeError("Ikonica je prevelika (max 3 MB).")
            except (binascii.Error, ValueError):
                raise forge_engine.ForgeError("Ikonica nije validna (očekujem PNG).")
        apk = forge_engine.forge(
            url=payload.get("url", ""),
            app_name=payload.get("app_name", ""),
            package=payload.get("package", ""),
            version_name=payload.get("version_name", "1.0"),
            icon_bytes=icon,
            log=log)
        name = os.path.basename(apk)
        job.update(state="done", apk=f"/api/download?job={job_id}",
                   apk_name=name,
                   size_mb=round(os.path.getsize(apk) / (1024 * 1024), 2))
    except forge_engine.ForgeError as e:
        log("❌ " + str(e))
        job.update(state="error", error=str(e))
    except Exception as e:  # neočekivano
        log(f"❌ Neočekivana greška: {e}")
        job.update(state="error", error=f"Neočekivana greška: {e}")


class Handler(BaseHTTPRequestHandler):
    server_version = "WebToAppForge/1.0"

    # ---------- helperi
    def _json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _file(self, path, ctype="text/html; charset=utf-8"):
        with open(path, "rb") as f:
            body = f.read()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        pass  # tišina

    # ---------- GET
    def do_GET(self):
        u = urlparse(self.path)
        if u.path in ("/", "/index.html"):
            return self._file(os.path.join(BASE, "index.html"))
        if u.path == "/api/health":
            return self._json({"ok": True, "sdk": forge_engine.sdk_ready()})
        if u.path == "/api/status":
            jid = parse_qs(u.query).get("job", [""])[0]
            job = JOBS.get(jid)
            if not job:
                return self._json({"error": "nepoznat job"}, 404)
            return self._json({k: job[k] for k in
                               ("state", "log", "apk", "apk_name", "size_mb", "error")})
        if u.path == "/api/download":
            jid = parse_qs(u.query).get("job", [""])[0]
            job = JOBS.get(jid)
            if not job or job.get("state") != "done":
                return self._json({"error": "APK nije spreman"}, 404)
            # fajl je u OUT_DIR, naziv je u apk_name
            fpath = os.path.join(OUT_DIR, job["apk_name"])
            if not os.path.exists(fpath):
                return self._json({"error": "fajl nije na disku"}, 404)
            with open(fpath, "rb") as f:
                body = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "application/vnd.android.package-archive")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Content-Disposition",
                             f'attachment; filename="{job["apk_name"]}"')
            self.end_headers()
            self.wfile.write(body)
            return
        self._json({"error": "404"}, 404)

    # ---------- POST
    def do_POST(self):
        u = urlparse(self.path)
        if u.path != "/api/forge":
            return self._json({"error": "404"}, 404)
        try:
            length = int(self.headers.get("Content-Length", 0))
            if length > 6 * 1024 * 1024:
                return self._json({"error": "zahtev prevelik"}, 413)
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except Exception:
            return self._json({"error": "neispravan JSON"}, 400)

        if not payload.get("url"):
            return self._json({"error": "URL je obavezan"}, 400)

        jid = uuid.uuid4().hex
        JOBS[jid] = Job()
        threading.Thread(target=run_job, args=(jid, payload), daemon=True).start()
        return self._json({"job": jid})


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    port = int(os.environ.get("PORT", "8080"))
    srv = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print(f"🔥 WebToApp Forge sluša na 0.0.0.0:{port}", flush=True)
    print(f"   SDK spreman: {forge_engine.sdk_ready()}", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
