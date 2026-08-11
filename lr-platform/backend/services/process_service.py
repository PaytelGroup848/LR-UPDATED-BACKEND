import platform
import subprocess
import time


_PROCESS_CACHE = {"expires_at": 0, "response": None, "status_code": 200}


class ProcessService:

    @staticmethod
    def list_processes():

        if platform.system() != "Windows":
            return (
                "<pre>Process management is only supported on Windows hosts.</pre>",
                501
            )

        now = time.monotonic()
        if _PROCESS_CACHE["response"] is not None and _PROCESS_CACHE["expires_at"] > now:
            return _PROCESS_CACHE["response"], _PROCESS_CACHE["status_code"]

        completed = subprocess.run(
            ["tasklist"],
            capture_output=True,
            text=True,
            timeout=60
        )

        response = f"<pre>{completed.stdout or completed.stderr}</pre>"
        _PROCESS_CACHE.update({
            "expires_at": now + 10,
            "response": response,
            "status_code": 200,
        })

        return response, 200

    @staticmethod
    def kill_process(pid, user_id=None):

        if not pid:
            return (
                "<pre>PID is required</pre>",
                400
            )

        if platform.system() != "Windows":
            return (
                "<pre>Process management is only supported on Windows hosts.</pre>",
                501
            )

        completed = subprocess.run(
            ["taskkill", "/PID", str(pid), "/F"],
            capture_output=True,
            text=True,
            timeout=60
        )

        return (
            f"<pre>{completed.stdout or completed.stderr}</pre>",
            200 if completed.returncode == 0 else 400
        )
