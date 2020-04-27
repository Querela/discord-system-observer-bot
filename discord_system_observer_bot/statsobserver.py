import datetime
from collections import defaultdict, namedtuple
from functools import lru_cache, partial


from discord_system_observer_bot.gpuinfo import get_gpus
from discord_system_observer_bot.sysinfo import (
    _get_loadavg,
    _get_mem_util,
    _get_mem_used,
)
from discord_system_observer_bot.sysinfo import (
    _get_disk_paths,
    _get_disk_usage,
    _get_disk_free_gb,
)


# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def has_extra_deps_gpu():
    try:
        import GPUtil  # pylint: disable=import-outside-toplevel,unused-import
    except ImportError:
        return False
    return True


@lru_cache(maxsize=1)
def has_extra_deps_plot():
    try:
        import matplotlib  # pylint: disable=import-outside-toplevel,unused-import
    except ImportError:
        return False
    return True


# ---------------------------------------------------------------------------


# TODO: refactor disk path gathering (used above/below)


def collect_stats(include=("cpu", "disk", "gpu")):
    stats = dict()

    stats["_id"] = 0
    stats["_datetime"] = int(datetime.datetime.now(datetime.timezone.utc).timestamp())

    if "cpu" in include:
        (
            stats["load_avg_1m_perc_percpu"],
            stats["load_avg_5m_perc_percpu"],
            stats["load_avg_15m_perc_percpu"],
        ) = [round(v, 1) for v in _get_loadavg()]
        stats["mem_util_perc"] = round(_get_mem_util(), 1)
        stats["mem_used_gb"] = round(_get_mem_used(), 1)

    if "disk" in include:
        for dpath in _get_disk_paths():
            stats[f"disk_usage_perc:{dpath}"] = round(_get_disk_usage(dpath), 1)
            stats[f"disk_free_gb:{dpath}"] = round(_get_disk_free_gb(dpath), 1)

    if "gpu" in include and has_extra_deps_gpu():
        for gpu in get_gpus():
            stats[f"gpu_util_perc:{gpu.id}"] = round(gpu.load * 100)
            stats[f"gpu_mem_perc:{gpu.id}"] = round(gpu.memoryUtil * 100, 1)
            stats[f"gpu_temp:{gpu.id}"] = round(gpu.temperature, 1)
            stats[f"gpu_mem_used_mb:{gpu.id}"] = int(gpu.memoryUsed)
            stats[f"gpu_mem_total_mb:{gpu.id}"] = int(gpu.memoryTotal)

    return stats


def stats2rows(stats_list):
    if not stats_list:
        return None
    names = tuple(stats_list[0].keys())
    # TODO: need to order by _id/_datetime values?
    # TODO: filter those values?
    series = list(zip(*[tuple(s.values()) for s in stats_list]))
    return tuple(zip(names, series))


def plot_rows(data_series, as_data_uri=True):
    if not has_extra_deps_plot():
        return None

    # pylint: disable=import-outside-toplevel,unused-import

    from base64 import b64encode
    from io import BytesIO

    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt
    import numpy as np

    # pylint: enable=import-outside-toplevel,unused-import

    nrows = len([n for n, _ in data_series if not n.startswith("_")])

    # shared x-axis
    x = [  # pylint: disable=invalid-name
        datetime.datetime.utcfromtimestamp(v)
        for n, vs in data_series
        if n == "_datetime"
        for v in vs
    ]
    x = [vs for n, vs in data_series if n == "_id"][0]  # pylint: disable=invalid-name

    # plt.gca().xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d"))
    # plt.gca().xaxis.set_major_locator(mdates.DayLocator(interval=1))

    fig, axes = plt.subplots(nrows, sharex=True, figsize=(4, 8))

    # plot series
    ai = -1  # pylint: disable=invalid-name
    for name, series in data_series:
        if name.startswith("_"):
            continue
        ai += 1  # pylint: disable=invalid-name
        ax = axes[ai]  # pylint: disable=invalid-name
        ax.plot(x, series)
        # ax.set(ylabel=name)
        ax.set_title(name)
        ax.label_outer()

    # plt.gcf().autofmt_xdate()

    # serialize result
    bbuf = BytesIO()
    # https://matplotlib.org/3.1.1/api/_as_gen/matplotlib.pyplot.savefig.html
    fig.savefig(bbuf, format="png")
    if as_data_uri:
        data_uri = f"data:image/png;base64,{b64encode(bbuf.getvalue()).decode()}"
        return data_uri
    return bbuf.getvalue()


# ---------------------------------------------------------------------------


ObservableLimit = namedtuple(
    "ObservableLimit",
    (
        #: visible name of the check/limit/...
        "name",
        #: function that returns a numeric value
        "fn_retrieve",
        #: function that get current and threshold value (may be ignored)
        #: and returns True if current value is ok
        "fn_check",
        #: threshold, numeric (for visibility purposes)
        "threshold",
        #: message to send if check failed (e. g. resource exhausted)
        "message",
        #: badness increment for each failed check, None for default
        #: can be smaller than threshold to allow for multiple consecutive failed checks
        #: or same as threshold to immediatly notify
        "badness_inc",
        #: badness threshold if reached, a message is sent, None for default
        #: allows for fluctuations until message is sent
        "badness_threshold",
    ),
)


class BadCounterManager:
    """Manager that gathers badness values for keys with
    individual thresholds and increments."""

    def __init__(self, default_threshold=3, default_increase=3):
        self.bad_counters = defaultdict(int)
        self.default_increase = default_increase
        self.default_threshold = default_threshold

    def reset(self, name=None):
        """Reset counters etc. to normal/default levels."""
        if name is not None:
            self.bad_counters[name] = 0
        else:
            for name_ in self.bad_counters.keys():
                self.bad_counters[name_] = 0

    def increase_counter(self, name, limit):
        """Increse the badness level and return True if threshold reached."""
        bad_threshold = (
            limit.badness_threshold
            if limit.badness_threshold is not None
            else self.default_threshold
        )
        bad_inc = (
            limit.badness_inc
            if limit.badness_inc is not None
            else self.default_increase
        )

        # increse value
        self.bad_counters[name] = min(bad_threshold, self.bad_counters[name] + bad_inc)

        return self.threshold_reached(name, limit)

    def decrease_counter(self, name):
        """Decrease the badness counter and return True if normal."""
        if self.bad_counters[name] > 0:
            self.bad_counters[name] = max(0, self.bad_counters[name] - 1)

        return self.is_normal(name)

    def threshold_reached(self, name, limit):
        """Return True if the badness counter has reached the threshold."""
        bad_threshold = (
            limit.badness_threshold
            if limit.badness_threshold is not None
            else self.default_threshold
        )

        return self.bad_counters[name] >= bad_threshold

    def is_normal(self, name):
        """Return True if the badness counter is zero/normal."""
        return self.bad_counters[name] == 0


class NotifyBadCounterManager(BadCounterManager):
    """Manager that collects badness values and notification statuses."""

    def __init__(self, default_threshold=3, default_increase=3):
        super().__init__(
            default_threshold=default_threshold, default_increase=default_increase
        )
        self.notified = defaultdict(bool)

    def reset(self, name=None):
        super().reset(name=name)

        if name is not None:
            self.notified[name] = False
        else:
            for name_ in self.notified.keys():
                self.notified[name_] = False

    def decrease_counter(self, name):
        """Decrease the counter and reset the notification flag
        if the normal level has been reached.
        Returns True on change from non-normal to normal
        (for a one-time notification setup)."""
        was_normal_before = self.is_normal(name)
        has_notified_before = self.notified[name]
        is_normal = super().decrease_counter(name)
        if is_normal:
            self.notified[name] = False
        # return True if changed, else False if it was already normal
        # additionally require a limit exceeded message to be sent, else ignore the change
        return was_normal_before != is_normal and has_notified_before

    def should_notify(self, name, limit):
        """Return True if a notification should be sent."""
        if not self.threshold_reached(name, limit):
            return False

        if self.notified[name]:
            return False

        return True

    def mark_notified(self, name):
        """Mark this counter as already notified."""
        self.notified[name] = True


# ---------------------------------------------------------------------------


def make_observable_limits():
    limits = dict()

    limits["cpu_load_5min"] = ObservableLimit(
        name="CPU-Load-Avg-5min",
        fn_retrieve=lambda: _get_loadavg()[1],
        fn_check=lambda cur, thres: cur < thres,
        threshold=95.0,
        message="**CPU Load Avg [5min]** is too high! (value: `{cur_value}%`, threshold: `{threshold})`",
        # increase badness level by 1
        badness_inc=1,
        # notify, when badness counter reached 3
        badness_threshold=3,
    )
    limits["mem_util"] = ObservableLimit(
        name="Memory-Utilisation",
        fn_retrieve=_get_mem_util,  # pylint: disable=unnecessary-lambda
        fn_check=lambda cur, thres: cur < thres,
        threshold=85.0,
        message="**Memory Usage** is too high! (value: `{cur_value}%`, threshold: `{threshold})`",
        # increase badness level by 1
        badness_inc=1,
        # notify, when badness counter reached 3
        badness_threshold=3,
    )

    for i, path in enumerate(_get_disk_paths()):
        limits[f"disk_util_perc{i}"] = ObservableLimit(
            name=f"Disk-Usage-{path}",
            fn_retrieve=partial(_get_disk_usage, path),
            fn_check=lambda cur, thres: cur < thres,
            threshold=95.0,
            message=(
                f"**Disk Usage for `{path}`** is too high! "
                "(value: `{cur_value}%`, threshold: `{threshold})`"
            ),
            # use default increment amount
            badness_inc=None,
            # notify immediately
            badness_threshold=None,
        )
        # TODO: disable the static values test if system has less or not significantly more total disk space
        limits[f"disk_util_gb{i}"] = ObservableLimit(
            name=f"Disk-Space-Free-{path}",
            fn_retrieve=partial(_get_disk_free_gb, path),
            fn_check=lambda cur, thres: cur > thres,
            # currently a hard-coded limit of 30GB (for smaller systems (non-servers) unneccessary?)
            threshold=30.0,
            message=(
                "No more **Disk Space for `{path}`**! "
                "(value: `{cur_value}GB`, threshold: `{threshold})`"
            ),
            # use default increment amount
            badness_inc=None,
            # notify immediately
            badness_threshold=None,
        )

    # TODO: GPU checks
    # NOTE: may be useful if you just want to know when GPU is free for new stuff ...

    return limits


# ---------------------------------------------------------------------------
