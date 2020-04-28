import os
import time
import typing
from datetime import timedelta

import psutil
from psutil._common import bytes2human

from discord_system_observer_bot.utils import make_table


Percentage100Type = float
SizeGBType = float


# ---------------------------------------------------------------------------


def _get_loadavg() -> typing.List[Percentage100Type]:
    return [x / psutil.cpu_count() * 100 for x in psutil.getloadavg()]


def _get_mem_util() -> Percentage100Type:
    mem = psutil.virtual_memory()
    return mem.used / mem.total * 100


def _get_mem_used() -> SizeGBType:
    mem = psutil.virtual_memory()
    return mem.used / 1024 ** 3


def get_disk_list() -> typing.List:
    return [
        disk
        for disk in psutil.disk_partitions(all=False)
        if "loop" not in disk.device and not disk.mountpoint.startswith("/boot")
    ]


def _get_disk_paths() -> typing.List[str]:
    disks = get_disk_list()
    paths = [disk.mountpoint for disk in disks]
    return paths


def _get_disk_usage(path: str) -> Percentage100Type:
    return psutil.disk_usage(path).percent


def _get_disk_free_gb(path: str) -> SizeGBType:
    return psutil.disk_usage(path).free / 1024 ** 3


# ---------------------------------------------------------------------------


def get_cpu_info() -> str:
    meminfo = psutil.virtual_memory()
    GB_div = 1024 ** 3  # pylint: disable=invalid-name

    info = (
        "```\n"
        + "\n".join(
            [
                f"Uptime:  {timedelta(seconds=int(time.time() - psutil.boot_time()))}",
                f"CPUs:    {psutil.cpu_count()}",
                f"RAM:     {meminfo.total / GB_div:.1f} GB",
                "",
                "Load:    1min: {0[0]:.1f}%, 5min: {0[1]:.1f}%, 15min: {0[2]:.1f}%".format(
                    _get_loadavg()
                ),
                f"Memory:  {(meminfo.used / meminfo.total) * 100:.1f}% [used: {meminfo.used / GB_div:.1f} / {meminfo.total / GB_div:.1f} GB] [available: {meminfo.available  / GB_div:.1f} GB]",
            ]
        )
        + "\n```"
    )

    return info


def get_disk_info() -> str:
    disks = get_disk_list()

    headers = ("Device", "Mount", "Use", "Total", "Used", "Free")

    rows = list()
    for disk in disks:
        usage = psutil.disk_usage(disk.mountpoint)
        rows.append(
            (
                disk.device,
                disk.mountpoint,
                f"{usage.percent:.1f} %",
                bytes2human(usage.total),
                bytes2human(usage.used),
                bytes2human(usage.free),
                # disk.fstype,
            )
        )

    info = make_table(rows, headers)

    return info


def get_local_machine_name() -> str:
    return os.uname().nodename


# ---------------------------------------------------------------------------
