import subprocess
from dataclasses import dataclass
from typing import Iterable


@dataclass
class ManagedProcess:
    process: subprocess.Popen
    command: list[str]

    @property
    def pid(self):
        return self.process.pid

    def is_running(self):
        return self.process.poll() is None

    def stop(self, timeout=5):
        if not self.is_running():
            return True
        self.process.terminate()
        try:
            self.process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=timeout)
        return True


def start_process(command: Iterable[str], cwd=None, env=None):
    cmd = [str(part) for part in command]
    if not cmd:
        raise ValueError("Command is required")
    process = subprocess.Popen(cmd, cwd=cwd, env=env)
    return ManagedProcess(process=process, command=cmd)
