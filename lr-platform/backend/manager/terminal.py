import shlex
import subprocess


def run_command(command):
    if not command:
        return 'No command provided', 400

    unsafe_tokens = {';', '&&', '||', '|', '$(', '`', '>'}
    if any(token in command for token in unsafe_tokens):
        return 'Command contains unsafe tokens', 400

    try:
        args = shlex.split(command)
    except ValueError:
        return 'Invalid command format', 400

    try:
        result = subprocess.run(
            args,
            shell=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return result.stderr or f'Command exited with code {result.returncode}', 400
        return result.stdout
    except subprocess.TimeoutExpired:
        return 'Command timed out', 500
    except Exception as exc:
        return str(exc), 500
