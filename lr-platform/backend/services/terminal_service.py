import subprocess


def run_command(command):
    completed = subprocess.run(
        command,
        shell=True,
        capture_output=True,
        text=True,
        timeout=60
    )

    return {
        "success": completed.returncode == 0,
        "output": completed.stdout,
        "error": completed.stderr,
        "return_code": completed.returncode
    }


class TerminalManagerService:

    @staticmethod
    def execute_command(user_id, command):

        if not command:
            return {
                "success": False,
                "message": "Command is required"
            }, 400

        result = run_command(command)

        return result, 200
