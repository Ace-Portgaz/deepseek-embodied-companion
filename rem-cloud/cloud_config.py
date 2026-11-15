"""Generate the upstream configuration without putting credentials in source files."""
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import csv
import io
import ipaddress

ROOT = Path(__file__).resolve().parent
UPSTREAM_COMMIT = "4b1a54a41c28112bc06b1ab605d2ba723f678ad3"
SECRET_FIELDS = ("deepseek_api_key", "volc_asr_api_key", "volc_tts_api_key")


def private_write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        identity = subprocess.check_output(["whoami", "/user", "/fo", "csv", "/nh"],
                                           text=True, creationflags=subprocess.CREATE_NO_WINDOW)
        sid = next(csv.reader(io.StringIO(identity.strip())))[1]
        if not re.fullmatch(r"S-1-[0-9-]+", sid):
            raise OSError("Unable to identify local file owner")
        subprocess.run(["icacls", str(path.parent), "/inheritance:r", "/grant:r",
                        f"*{sid}:(OI)(CI)F", "*S-1-5-18:(OI)(CI)F"],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       creationflags=subprocess.CREATE_NO_WINDOW)
    else:
        path.parent.chmod(0o700)
    temporary = path.with_name(path.name + ".new")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
        stream.write(value)
    os.replace(temporary, path)
    if os.name != "nt":
        path.chmod(0o600)


def load_private(root=ROOT):
    root = Path(root)
    settings_path = root / ".private/settings.json"
    credentials_path = root / ".private/credentials.json"
    settings = json.loads((root / "settings.example.json").read_text(encoding="utf-8"))
    if settings_path.exists():
        settings.update(json.loads(settings_path.read_text(encoding="utf-8")))
    credentials = json.loads(credentials_path.read_text(encoding="utf-8")) if credentials_path.exists() else {}
    return settings, credentials


def validate(settings, credentials, cloud=True):
    missing = [key for key in SECRET_FIELDS if not credentials.get(key, "").strip()]
    if not settings.get("tts_speaker", "").strip():
        missing.append("tts_speaker")
    if settings.get("asr_language") != "ja-JP":
        missing.append("asr_language must be ja-JP")
    if settings.get("tts_resource") not in {"seed-tts-2.0", "seed-icl-2.0"}:
        missing.append("tts_resource must be seed-tts-2.0 or seed-icl-2.0")
    rate = settings.get("speech_rate", -5)
    if not isinstance(rate, int) or not -50 <= rate <= 100:
        missing.append("speech_rate must be an integer between -50 and 100")
    if cloud:
        host = settings.get("public_host", "")
        domain = bool(re.fullmatch(r"(?=.{1,253}$)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,63}", host))
        try:
            address = ipaddress.ip_address(host)
            public_ipv4 = address.version == 4 and address.is_global and not address.is_multicast
        except ValueError:
            public_ipv4 = False
        if not domain and not public_ipv4:
            missing.append("public_host (a domain or public IPv4, without https://)")
        if not re.fullmatch(r"(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}", settings.get("device_id", "")):
            missing.append("device_id (ESP32 MAC address)")
        for key in ("device_setup_secret", "server_auth_key"):
            if not re.fullmatch(r"[A-Za-z0-9_-]{40,128}", credentials.get(key, "")):
                missing.append(key)
    return missing


def with_device_secrets(credentials):
    credentials = dict(credentials)
    for key in ("device_setup_secret", "server_auth_key"):
        if not credentials.get(key):
            credentials[key] = secrets.token_urlsafe(32)
    return credentials


def build_config(settings, credentials, prompt):
    problems = validate(settings, credentials)
    if problems:
        raise ValueError("Missing or invalid fields: " + ", ".join(problems))
    return {
        "server": {
            "ip": "0.0.0.0", "port": 8000, "http_port": 8003,
            "websocket": f"wss://{settings['public_host']}/xiaozhi/v1/",
            "vision_explain": "", "timezone_offset": 8,
            "auth_key": credentials["server_auth_key"],
            "auth": {"enabled": True, "allowed_devices": [], "expire_seconds": 2592000},
            "mqtt_gateway": None, "mqtt_signature_key": None, "udp_gateway": None,
        },
        "selected_module": {"VAD": "SileroVAD", "ASR": "RemVolcASR", "LLM": "RemDeepSeek",
                            "VLLM": None, "TTS": "RemVolcTTS",
                            "Memory": "RemMemory" if settings.get("memory_enabled", True) else "nomem",
                            "Intent": "nointent"},
        "ASR": {"RemVolcASR": {"type": "rem_volc_asr", "api_key": credentials["volc_asr_api_key"],
                                 "resource_id": settings["asr_resource"], "enable_multilingual": True,
                                 "language": "ja-JP", "end_window_size": 600, "output_dir": "tmp/"}},
        "LLM": {"RemDeepSeek": {"type": "openai", "url": "https://api.deepseek.com",
                                  "api_key": credentials["deepseek_api_key"],
                                  "model_name": settings["deepseek_model"], "thinking": "off",
                                  "max_tokens": 400, "temperature": 0.7,
                                  "timeout": {"connect": 5, "read": 40, "write": 10, "pool": 5}}},
        "TTS": {"RemVolcTTS": {"type": "rem_volc_tts", "api_key": credentials["volc_tts_api_key"],
                                 "resource_id": settings["tts_resource"], "speaker": settings["tts_speaker"],
                                 "ws_url": "wss://openspeech.bytedance.com/api/v3/tts/bidirection",
                                 "enable_ws_reuse": False, "language": "日语", "output_dir": "tmp/",
                                 "audio_params": {"speech_rate": settings["speech_rate"], "loudness_rate": 0},
                                 "additions": {"explicit_language": "ja"}}},
        # Administrator-owned aliases; device messages cannot select another memory.
        # Leave empty until the new device has its own authenticated enrollment.
        "Memory": {"RemMemory": {"type": "rem_memory",
                                  "identity_aliases": settings.get("memory_identity_aliases", {})}},
        "prompt": prompt, "prompt_template": "rem-prompt-template.txt",
        "phone_devices": credentials.get("phone_devices", {}),
        "delete_audio": True, "enable_greeting": False,
        "enable_wakeup_words_response_cache": False, "enable_stop_tts_notify": False,
        "close_connection_no_voice_time": 90, "end_prompt": {"enable": False},
        "system_error_response": "ごめんなさい。今、接続が少し不安定です。もう一度話しかけてもらえますか。",
        "exit_commands": ["会話を終了", "おやすみ", "退出"],
        "mcp_endpoint": None, "plugins": {}, "context_providers": [], "voiceprint": None,
        "manager-api": {"url": "", "secret": ""},
        "log": {"log_level": "WARNING", "log_dir": "tmp", "data_dir": "data"},
    }
