import paramiko

from backend.manager.logger import get_logger

logger = get_logger(__name__)


def connect_ssh(host, port, username, password):
    try:
  
        host = str(host).strip() if host else ""
        username = str(username).strip() if username else ""
        
        if not host or not username:
            raise ValueError("Host and username cannot be empty")
        
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(hostname=host, port=port, username=username, password=password, timeout=5)
        return ssh, None
    except Exception as e:
        error_msg = f"{type(e).__name__}: {str(e)}"
        logger.error("SSH connection error: %s", error_msg)
        return None, error_msg
