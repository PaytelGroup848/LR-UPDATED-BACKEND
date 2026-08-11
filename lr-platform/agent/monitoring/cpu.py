import psutil


def get_cpu_metrics(interval=0.1):
    return {
        "percent": psutil.cpu_percent(interval=interval),
        "count": psutil.cpu_count(),
        "load_average": psutil.getloadavg() if hasattr(psutil, "getloadavg") else None,
    }
