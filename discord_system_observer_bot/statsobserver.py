import datetime
import typing
from base64 import b64encode
from collections import defaultdict
from functools import lru_cache, partial
from io import BytesIO

from discord_system_observer_bot.gpuinfo import get_gpus
from discord_system_observer_bot.gpuinfo import (
    _get_gpu_util,
    _get_gpu_mem_load,
    _get_gpu_temp,
)
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


LimitTypesSetType = typing.Optional[typing.Tuple[str]]


# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def has_extra_deps_gpu() -> bool:
    try:
        import GPUtil  # pylint: disable=import-outside-toplevel,unused-import
    except ImportError:
        return False
    return True


@lru_cache(maxsize=1)
def has_extra_deps_plot() -> bool:
    try:
        import matplotlib  # pylint: disable=import-outside-toplevel,unused-import
    except ImportError:
        return False
    return True


# ---------------------------------------------------------------------------


def collect_stats(
    include: typing.Set[str] = ("cpu", "disk", "gpu")
) -> typing.Dict[str, typing.Union[float, int]]:
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


def stats2rows(
    stats_list: typing.List[typing.Dict[str, typing.Union[float, int]]]
) -> typing.Optional[typing.Tuple[typing.Tuple[str, typing.List]]]:
    if not stats_list:
        return None
    names = tuple(stats_list[0].keys())
    # TODO: need to order by _id/_datetime values?
    # TODO: filter those values?
    series = list(zip(*[tuple(s.values()) for s in stats_list]))
    return tuple(zip(names, series))


def plot_rows(
    data_series: typing.Tuple[typing.Tuple[str, typing.List]], as_data_uri: bool = True
) -> typing.Optional[typing.Union[str, bytes]]:
    if not has_extra_deps_plot():
        return None

    # pylint: disable=import-outside-toplevel

    # import matplotlib.dates as mdates
    import matplotlib.pyplot as plt

    # pylint: enable=import-outside-toplevel

    meta_series = [ds for ds in data_series if ds[0].startswith("_")]
    data_series = [ds for ds in data_series if not ds[0].startswith("_")]

    # how many subplots
    nrows = len(data_series)
    ncols = 2

    # shared x-axis
    x = [  # pylint: disable=invalid-name
        datetime.datetime.utcfromtimestamp(v)
        for n, vs in meta_series
        if n == "_datetime"
        for v in vs
    ]
    # alternative numeric x-labels
    # x = [vs for n, vs in meta_series if n == "_id"][0]  # pylint: disable=invalid-name

    # plt.gca().xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d %H:%M"))
    # plt.gca().xaxis.set_major_locator(mdates.DayLocator(interval=1))

    # fig, axes = plt.subplots(int((nrows + ncols - 1) / ncols), ncols, sharex=True, figsize=(8, 10))
    fig = plt.figure(figsize=(8, 10))
    # how many rows / columns, round up
    plt_layout_fmt = (int((nrows + ncols - 1) / ncols), ncols)

    # plot series
    for axis_nr, (name, series) in enumerate(data_series, 1):
        # get current plot
        ax = fig.add_subplot(*(plt_layout_fmt + (axis_nr,)))
        # plot
        ax.plot(x, series)
        # set plot title
        ax.set_title(name)

    for axis_nr, ax in enumerate(fig.axes, 1):
        # set x-axis to start with 0
        # ax.set_xlim(left=0, right=len(x))

        # disable inner x-axis labels
        # ax.label_outer()
        # if not ax.is_last_row():
        # if axis_nr not in (nrows, nrows - 1):
        #    print(ax.get_title())
        #    for label in ax.get_xticklabels(which="both"):
        #        label.set_visible(False)
        #    ax.get_xaxis().get_offset_text().set_visible(False)
        #    ax.set_xlabel("")
        pass

    plt.gcf().autofmt_xdate()

    plt.tight_layout()

    # serialize result
    bbuf = BytesIO()
    # https://matplotlib.org/3.1.1/api/_as_gen/matplotlib.pyplot.savefig.html
    fig.savefig(bbuf, format="png")

    if as_data_uri:
        data_uri = f"data:image/png;base64,{b64encode(bbuf.getvalue()).decode()}"
        return data_uri
    return bbuf.getvalue()


# ---------------------------------------------------------------------------


class ObservableLimit(typing.NamedTuple):
    #: visible name of the check/limit/...
    name: str
    #: function that returns a numeric value
    fn_retrieve: typing.Callable[[], float]
    #: function that get current and threshold value (may be ignored)
    #: and returns True if current value is ok
    fn_check: typing.Callable[[float, float], bool]
    #: unit, str (for visibility purposes, nothing functional, like %, °C, GB)
    unit: str
    #: threshold, numeric (for visibility purposes)
    threshold: float
    #: message to send if check failed (e. g. resource exhausted)
    message: str
    #: badness increment for each failed check, None for default
    #: can be smaller than threshold to allow for multiple consecutive failed checks
    #: or same as threshold to immediatly notify
    badness_inc: typing.Optional[int] = None
    #: WARNING: currently ignored! (default value of 1 used)
    #: allows for faster/slower decay of bad status
    badness_dec: typing.Optional[int] = None
    #: badness threshold if reached, a message is sent, None for default
    #: allows for fluctuations until message is sent
    badness_threshold: typing.Optional[int] = None


class BadCounterManager:
    """Manager that gathers badness values for keys with
    individual thresholds and increments."""

    def __init__(
        self,
        default_threshold: int = 3,
        default_increase: int = 1,
        default_decrease: int = 1,
    ):
        self.bad_counters = defaultdict(int)
        self.default_increase = default_increase
        self.default_decrease = default_decrease
        self.default_threshold = default_threshold

    def reset(self, name: typing.Optional[str] = None) -> None:
        """Reset counters etc. to normal/default levels."""
        if name is not None:
            self.bad_counters[name] = 0
        else:
            for name_ in self.bad_counters.keys():
                self.bad_counters[name_] = 0

    def increase_counter(self, name: str, limit: ObservableLimit) -> bool:
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

    def decrease_counter(
        self, name: str, limit: typing.Optional[ObservableLimit] = None
    ) -> bool:
        """Decrease the badness counter and return True if normal."""
        if self.bad_counters[name] > 0:
            bad_dec = (
                limit.badness_dec
                if limit is not None and limit.badness_dec is not None
                else self.default_decrease
            )

            self.bad_counters[name] = max(0, self.bad_counters[name] - bad_dec)

        return self.is_normal(name)

    def threshold_reached(self, name: str, limit: ObservableLimit) -> bool:
        """Return True if the badness counter has reached the threshold."""
        bad_threshold = (
            limit.badness_threshold
            if limit.badness_threshold is not None
            else self.default_threshold
        )

        return self.bad_counters[name] >= bad_threshold

    def is_normal(self, name: str) -> bool:
        """Return True if the badness counter is zero/normal."""
        return self.bad_counters[name] == 0


class NotifyBadCounterManager(BadCounterManager):
    """Manager that collects badness values and notification statuses."""

    def __init__(
        self,
        default_threshold: int = 3,
        default_increase: int = 1,
        default_decrease: int = 1,
    ):
        super().__init__(
            default_threshold=default_threshold,
            default_increase=default_increase,
            default_decrease=default_decrease,
        )
        self.notified = defaultdict(bool)

    def reset(self, name: typing.Optional[str] = None) -> None:
        super().reset(name=name)

        if name is not None:
            self.notified[name] = False
        else:
            for name_ in self.notified.keys():
                self.notified[name_] = False

    def decrease_counter(
        self, name: str, limit: typing.Optional[ObservableLimit] = None
    ) -> bool:
        """Decrease the counter and reset the notification flag
        if the normal level has been reached.
        Returns True on change from non-normal to normal
        (for a one-time notification setup)."""
        was_normal_before = self.is_normal(name)
        has_notified_before = self.notified[name]
        is_normal = super().decrease_counter(name, limit=limit)
        if is_normal:
            self.notified[name] = False
        # return True if changed, else False if it was already normal
        # additionally require a limit exceeded message to be sent, else ignore the change
        return was_normal_before != is_normal and has_notified_before

    def should_notify(self, name: str, limit: ObservableLimit) -> bool:
        """Return True if a notification should be sent."""
        if not self.threshold_reached(name, limit):
            return False

        if self.notified[name]:
            return False

        return True

    def mark_notified(self, name: str) -> None:
        """Mark this counter as already notified."""
        self.notified[name] = True


# ---------------------------------------------------------------------------


def make_observable_limits(
    include: LimitTypesSetType = (
        "cpu",
        "ram",
        "disk",
        "disk_gb",
        "gpu_load",
        "gpu_temp",
    )
) -> typing.Dict[str, ObservableLimit]:
    limits = dict()

    if include is None:
        # critical: more for early warnings
        include = ("disk", "disk_gb", "gpu_temp")

        # more for notification purposes (if free or not)
        # include += ("cpu", "ram", "gpu_load")

    if "cpu" in include:
        limits["cpu_load_5min"] = ObservableLimit(
            name="CPU Load Avg [5min]",
            fn_retrieve=lambda: round(_get_loadavg()[1], 1),
            fn_check=lambda cur, thres: cur < thres,
            unit="%",
            threshold=95.0,
            message="**CPU Load Avg [5min]** is too high! (value: `{cur_value:.1f}%`, threshold: `{threshold:.1f})`",
            # increase badness level by 2
            badness_inc=2,
            # notify, when badness counter reached 6
            badness_threshold=6,
        )

    if "ram" in include:
        limits["mem_util"] = ObservableLimit(
            name="Memory Utilisation",
            fn_retrieve=lambda: round(_get_mem_util(), 1),
            fn_check=lambda cur, thres: cur < thres,
            unit="%",
            threshold=85.0,
            message="**Memory Usage** is too high! (value: `{cur_value:.1f}%`, threshold: `{threshold:.1f})`",
            # increase badness level by 1
            badness_inc=1,
            # notify, when badness counter reached 3
            badness_threshold=3,
        )

    if "disk" in include or "disk_gb" in include:
        for i, path in enumerate(_get_disk_paths()):
            if "disk" in include:
                limits[f"disk_util_perc{i}"] = ObservableLimit(
                    name=f"Disk Usage: {path}",
                    fn_retrieve=partial(_get_disk_usage, path),
                    fn_check=lambda cur, thres: cur < thres,
                    unit="%",
                    threshold=95.0,
                    message=(
                        f"**Disk Usage for `{path}`** is too high! "
                        "(value: `{cur_value:.1f}%`, threshold: `{threshold:.1f})`"
                    ),
                    # use default increment amount
                    badness_inc=None,
                    # notify immediately
                    badness_threshold=None,
                )

            # TODO: disable the static values test if system has less or not significantly more total disk space
            if "disk_gb" in include:

                def _round_get_disk_gree_gb(path):
                    return round(_get_disk_free_gb(path), 1)

                limits[f"disk_util_gb{i}"] = ObservableLimit(
                    name=f"Disk Space (Free): {path}",
                    fn_retrieve=partial(_round_get_disk_gree_gb, path),
                    fn_check=lambda cur, thres: cur > thres,
                    unit="GB",
                    # currently a hard-coded limit of 30GB (for smaller systems (non-servers) unneccessary?)
                    threshold=30.0,
                    message=(
                        "No more **Disk Space for `{path}`**! "
                        "(value: `{cur_value:.1f}GB`, threshold: `{threshold:.1f})`"
                    ),
                    # use default increment amount
                    badness_inc=None,
                    # notify immediately
                    badness_threshold=None,
                )

    if ("gpu_load" in include or "gpu_temp" in include) and has_extra_deps_gpu():
        for gpu in get_gpus():
            # NOTE: may be useful if you just want to know when GPU is free for new stuff ...
            if "gpu_load" in include:
                limits[f"gpu_util_perc:{gpu.id}"] = ObservableLimit(
                    name=f"GPU {gpu.id} Utilisation",
                    fn_retrieve=partial(_get_gpu_util, gpu.id),
                    fn_check=lambda cur, thres: cur < thres,
                    unit="%",
                    threshold=85,
                    message="**GPU {gpu.id} Utilisation** is working! (value: `{cur_value}%`, threshold: `{threshold})`",
                    # increase by 2, decrease by 1
                    badness_inc=2,
                    badness_threshold=6,
                )
                limits[f"gpu_mem_perc:{gpu.id}"] = ObservableLimit(
                    name=f"GPU {gpu.id} Memory Utilisation",
                    fn_retrieve=partial(_get_gpu_mem_load, gpu.id),
                    fn_check=lambda cur, thres: cur < thres,
                    unit="%",
                    threshold=85.0,
                    message="**GPU {gpu.id} Memory** is full! (value: `{cur_value:.1f}%`, threshold: `{threshold:.1f})`",
                    # increase by 2, decrease by 1
                    badness_inc=2,
                    badness_threshold=6,
                )

            if "gpu_temp" in include:
                limits[f"gpu_util_perc:{gpu.id}"] = ObservableLimit(
                    name=f"GPU {gpu.id} Temperature",
                    fn_retrieve=partial(_get_gpu_temp, gpu.id),
                    fn_check=lambda cur, thres: cur < thres,
                    unit="°C",
                    threshold=90,
                    message="**GPU {gpu.id} Temperature** too high! (value: `{cur_value:.1f}{unit}`, threshold: `{threshold:.1f}{unit})`",
                    # 3 times the charm
                    badness_inc=1,
                    badness_threshold=3,
                )

    return limits


# ---------------------------------------------------------------------------
