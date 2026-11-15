"""Assemble an auditable cloud build; never starts services or calls paid APIs."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
from cloud_config import ROOT, UPSTREAM_COMMIT, load_private, private_write, validate, with_device_secrets


def assemble():
    upstream = ROOT.parent / "upstream/xiaozhi-esp32-server"
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=upstream, text=True).strip()
    if head != UPSTREAM_COMMIT:
        raise SystemExit("Upstream version differs; review it before building.")
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=upstream, text=True).strip():
        raise SystemExit("Upstream has local changes; review them before building.")
    build = ROOT / "build"
    server = build / "server"
    build.mkdir(exist_ok=True)
    shutil.copytree(upstream / "main/xiaozhi-server", server, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns(".config.yaml", ".memory.yaml", "__pycache__", "*.pyc", "tmp", "tests"))
    shutil.copy2(upstream / "LICENSE", server / "UPSTREAM-LICENSE")
    files = {
        "adapters/rem_volc_asr.py": "core/providers/asr/rem_volc_asr.py",
        "adapters/rem_volc_tts.py": "core/providers/tts/rem_volc_tts.py",
        "adapters/rem_memory.py": "core/providers/memory/rem_memory/rem_memory.py",
        "adapters/privacy_logger.py": "config/logger.py",
        "adapters/disabled_plugins.py": "plugins_func/loadplugins.py",
        "adapters/rem_audit.py": "rem_audit.py",
        "prompts/rem_ja.txt": "rem-persona.txt",
        "prompts/agent-base-prompt.txt": "rem-prompt-template.txt",
        "cloud_config.py": "cloud_config.py",
        "speech_budget.py": "speech_budget.py",
        "entrypoint.py": "rem-entrypoint.py",
        "phone_api.py": "phone_api.py",
        "phone_speech.py": "phone_speech.py",
        "phone_clone.py": "phone_clone.py",
    }
    for source, destination in files.items():
        target = server / destination
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / source, target)
    # The selected TTS adapter inherits this module. Its raw traceback bypasses
    # loguru; suppress that escape hatch in the assembled copy only.
    tts_source = server / "core/providers/tts/huoshan_double_stream.py"
    tts_text = tts_source.read_text(encoding="utf-8")
    if tts_text.count("traceback.print_exc()") != 1:
        raise SystemExit("Upstream TTS exception path changed; review required.")
    tts_source.write_text(tts_text.replace("traceback.print_exc()", 'logger.warning("TTS stream failed")'), encoding="utf-8")
    (server / "core/providers/memory/rem_memory/__init__.py").touch()
    app = server / "app.py"
    app_text = app.read_text(encoding="utf-8")
    app_text = app_text.replace("from core.http_server import SimpleHttpServer", "from rem_audit import RemHttpServer as SimpleHttpServer")
    app_text = app_text.replace("from core.websocket_server import WebSocketServer", "from rem_audit import RemWebSocketServer as WebSocketServer")
    app.write_text(app_text, encoding="utf-8")
    http = server / "core/http_server.py"
    text = http.read_text(encoding="utf-8")
    text = text.replace("app = web.Application()", "app = web.Application(client_max_size=1_000_000)\n                from phone_api import install_phone_routes\n                install_phone_routes(app, self.config)")
    text = text.replace("web.AppRunner(app)", "web.AppRunner(app, access_log=None)")
    http.write_text(text, encoding="utf-8")
    shutil.copy2(ROOT / "deploy/Dockerfile", build / "Dockerfile")
    (build / ".dockerignore").write_text("**/__pycache__\n**/*.pyc\n**/.config.yaml\n**/.memory.yaml\n", encoding="utf-8")
    (build / "UPSTREAM_COMMIT").write_text(UPSTREAM_COMMIT + "\n", encoding="utf-8")
    print("Cloud build files prepared. No service has been started.")


def prepare_runtime():
    settings, credentials = load_private()
    credentials = with_device_secrets(credentials)
    problems = validate(settings, credentials)
    if problems:
        raise SystemExit("Still needed: " + ", ".join(problems))
    private_write(ROOT / ".private/credentials.json", json.dumps(credentials))
    # Compose secrets are read-only bind mounts in ordinary Docker Compose.
    # Container UID must be able to read them; the containing runtime directory stays 0700.
    folder = ROOT / "runtime"
    folder.mkdir(mode=0o700, exist_ok=True)
    for name, value in (("settings.json", settings), ("credentials.json", credentials)):
        private_write(folder / name, json.dumps(value, ensure_ascii=False))
        if __import__("os").name != "nt":
            (folder / name).chmod(0o644)
    env = (f"PUBLIC_HOST={settings['public_host']}\nDEVICE_ID={settings['device_id']}\n"
           f"DEVICE_SETUP_SECRET={credentials['device_setup_secret']}\n")
    private_write(folder / "caddy.env", env)
    print("Private runtime files prepared. Credentials were not printed.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime", action="store_true", help="Prepare private runtime files after account and server setup")
    args = parser.parse_args()
    assemble()
    if args.runtime:
        prepare_runtime()
