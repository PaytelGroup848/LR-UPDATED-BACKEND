import subprocess

def get_processes():

    result= subprocess.run(['tasklist'], stdout=subprocess.PIPE, text=True)
    return result.stdout

def kill_process(pid):
    result = subprocess.run(['taskkill', '/PID', str(pid), '/F'], shell=True, stdout=subprocess.PIPE, text=True)
    return result.stdout or result.stderr