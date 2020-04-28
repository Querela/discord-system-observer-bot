import typing


try:
    import GPUtil

    _HAS_GPU = True
except ImportError:
    _HAS_GPU = False


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

    rows = list()
    fields = ["ID", "Util", "Mem", "Temp", "Memory (Used)"]  # , "Name"]
    rows.append(fields)

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

    lengths = [
        max(len(row[field_idx]) for row in rows) for field_idx in range(len(rows[0]))
    ]

    info = (
        "```\n"
        + "\n".join(
            # header
            [
                # "| " +
                " | ".join(
                    [
                        f"{field:{field_len}s}"
                        for field, field_len in zip(rows[0], lengths)
                    ]
                )
                # + " |"
            ]
            # separator
            + [
                # "| " +
                " | ".join(["-" * field_len for field_len in lengths])
                # + " |"
            ]
            # rows
            + [
                # "| " +
                " | ".join(
                    [f"{field:>{field_len}s}" for field, field_len in zip(row, lengths)]
                )
                # + " |"
                for row in rows[1:]
            ]
        )
        + "\n```"
    )

    return info


# ---------------------------------------------------------------------------
