import os
import sys


def get_start_command():
    executable = sys.executable
    script = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "main.py"))
    return [executable, script]


def should_start_minimized():
    return os.getenv("LR_AGENT_START_MINIMIZED", "1").lower() in {"1", "true", "yes", "on"}
