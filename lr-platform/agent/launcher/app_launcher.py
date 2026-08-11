import os
import subprocess


def launch_application(target, arguments=None, working_directory=None):
    if not target:
        raise ValueError("Application target is required")

    command = [str(target)]
    if arguments:
        if isinstance(arguments, str):
            command.extend(arguments.split())
        else:
            command.extend(str(item) for item in arguments)

    cwd = working_directory or os.path.dirname(str(target)) or None
    process = subprocess.Popen(command, cwd=cwd)
    return {
        "success": True,
        "pid": process.pid,
        "command": command,
    }
