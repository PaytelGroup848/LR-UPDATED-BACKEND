import os

import psutil


def get_disk_metrics(path=None):
    target = path or os.getcwd()
    usage = psutil.disk_usage(target)
    partitions = []
    for partition in psutil.disk_partitions(all=False):
        partitions.append({
            "device": partition.device,
            "mountpoint": partition.mountpoint,
            "fstype": partition.fstype,
        })
    return {
        "path": target,
        "total": usage.total,
        "used": usage.used,
        "free": usage.free,
        "percent": usage.percent,
        "partitions": partitions,
    }
