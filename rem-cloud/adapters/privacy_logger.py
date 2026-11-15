"""Upstream log messages may contain credentials/transcripts. Retain only fault locations."""
import sys
from loguru import logger

_ready = False


def _private_record(record):
    record["message"] = ""
    record["exception"] = None
    return True


def setup_logging(config=None):
    global _ready
    if not _ready:
        logger.remove()
        logger.add(sys.stderr, level="WARNING", format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {name}:{line}",
                   filter=_private_record, diagnose=False, backtrace=False)
        _ready = True
    return logger


def get_module_abbreviation(module_name, module_dict):
    value = module_dict.get(module_name) or "00"
    return value.split("_")[-1][:2]


def build_module_string(selected_module):
    return "".join(get_module_abbreviation(k, selected_module) for k in
                   ("VAD", "ASR", "LLM", "TTS", "Memory", "Intent", "VLLM"))


def create_connection_logger(selected_module_str):
    return setup_logging().bind(selected_module=selected_module_str)
