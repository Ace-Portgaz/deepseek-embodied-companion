"""Container entry: check private configuration, then start the Xiaozhi protocol server."""
import json
import os
from pathlib import Path
from cloud_config import build_config, private_write


def main():
    try:
        secret_dir = Path(os.environ.get("CREDENTIALS_DIRECTORY", "/run/secrets"))
        settings = json.loads((secret_dir / "rem_settings").read_text(encoding="utf-8"))
        credentials = json.loads((secret_dir / "rem_credentials").read_text(encoding="utf-8"))
        prompt = Path("rem-persona.txt").read_text(encoding="utf-8")
        config = build_config(settings, credentials, prompt)
        if os.environ.get("REM_NATIVE") == "1":
            config["server"]["ip"] = "127.0.0.1"
        private_write("data/.config.yaml", json.dumps(config, ensure_ascii=False))
    except (OSError, ValueError, KeyError):
        raise SystemExit("Configuration is missing or invalid. Run the local configuration check.")
    os.execvp("python", ["python", "app.py"])


if __name__ == "__main__":
    main()
