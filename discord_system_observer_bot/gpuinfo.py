import typing

from discord_system_observer_bot.utils import make_table

try:
    import GPUtil

    _HAS_GPU = True
except ImportError:
    _HAS_GPU = False

    # make dummy objects
    class GPUtil:
        class GPU:
            pass

        def getGPUs(self):
            return []


# ---------------------------------------------------------------------------


def get_gpus() -> typing.List[GPUtil.GPU]:
    """Return a list of ``GPUtil.GPU`` objects. Empty if none found.

    Returns
    -------
    typing.List[GPUtil.GPU]
        List of GPU info objects. Empty if none found.
    """
    return GPUtil.getGPUs()


# ---------------------------------------------------------------------------


class NoGPUException(Exception):
    pass


def _get_gpu(gpu_id):
    for gpu in get_gpus():
        if gpu.id == gpu_id:
            return gpu
    return None


def _get_gpu_util(gpu_id):
    gpu = _get_gpu(gpu_id)
    if gpu is None:
        raise NoGPUException()
    return round(gpu.load * 100)


def _get_gpu_mem_load(gpu_id):
    gpu = _get_gpu(gpu_id)
    if gpu is None:
        raise NoGPUException()
    return round(gpu.memoryUtil * 100, 1)


def _get_gpu_temp(gpu_id):
    gpu = _get_gpu(gpu_id)
    if gpu is None:
        raise NoGPUException()
    return round(gpu.temperature, 1)


# ---------------------------------------------------------------------------


def get_gpu_info() -> typing.Optional[str]:
    """Generates a summary about GPU status.

    Returns
    -------
    typing.Optional[str]
        ``None`` if no GPU support else a simple markdown formatted
        string.
    """

    if not _HAS_GPU:
        return None

    headers = ("ID", "Util", "Mem", "Temp", "Memory (Used)")  # , "Name")

    rows = list()
    for gpu in GPUtil.getGPUs():
        fields = [
            f"{gpu.id}",
            f"{gpu.load * 100:.0f} %",
            f"{gpu.memoryUtil * 100:.1f} %",
            f"{gpu.temperature:.1f} °C",
            f"{int(gpu.memoryUsed)} / {int(gpu.memoryTotal)} MB",
            # f"{gpu.name}",
        ]
        rows.append(fields)

    info = make_table(rows, headers)

    return info


# ---------------------------------------------------------------------------
