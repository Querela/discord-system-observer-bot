import datetime
import logging
import typing
from collections import defaultdict, deque
from io import BytesIO

import discord
from discord.ext import commands, tasks

from discord_system_observer_bot.gpuinfo import get_gpu_info
from discord_system_observer_bot.statsobserver import collect_stats as _collect_stats
from discord_system_observer_bot.statsobserver import stats2rows
from discord_system_observer_bot.statsobserver import plot_rows
from discord_system_observer_bot.statsobserver import has_extra_deps_gpu
from discord_system_observer_bot.statsobserver import make_observable_limits
from discord_system_observer_bot.statsobserver import NotifyBadCounterManager
from discord_system_observer_bot.sysinfo import get_local_machine_name
from discord_system_observer_bot.sysinfo import get_cpu_info, get_disk_info


LOGGER = logging.getLogger(__name__)


# ---------------------------------------------------------------------------


# Hack, will not allow multiple instances to be run in threads
# Well, should previously have been the same, as the local_machine_name
#   is always the same.


_LOCAL_MACHINE_NAME = get_local_machine_name()


def get_name() -> str:
    """Gets the locally stored "machine" name.

    Returns
    -------
    str
        name of the machine the bot runs on
    """
    return _LOCAL_MACHINE_NAME


def set_name(name: str) -> None:
    """Set the local "machine" name.

    Parameters
    ----------
    name : str
        the name of the machine/system the bot runs on
    """
    global _LOCAL_MACHINE_NAME
    _LOCAL_MACHINE_NAME = name


# ---------------------------------------------------------------------------


def make_sysinfo_message(
    cpu: bool = True,
    disk: bool = True,
    gpu: bool = True,
    name: typing.Optional[str] = None,
) -> str:
    if name is None:
        name = get_name()
    message = f"**Status of `{name}`**\n"
    message += f"Date: `{datetime.datetime.now()}`\n\n"

    if cpu:
        message += "System information:"
        ret = get_cpu_info()
        if ret is not None:
            message += "\n" + ret + "\n"
        else:
            message += " N/A\n"

    if disk:
        message += "Disk information:"
        ret = get_disk_info()
        if ret is not None:
            message += "\n" + ret + "\n"
        else:
            message += " N/A\n"

    if gpu and has_extra_deps_gpu():
        message += "GPU information:"
        ret = get_gpu_info()
        if ret is not None:
            message += "\n" + ret + "\n"
        else:
            message += " N/A\n"

    return message


def make_sysinfo_embed(
    cpu: bool = True,
    disk: bool = True,
    gpu: bool = True,
    name: typing.Optional[str] = None,
) -> discord.Embed:
    if name is None:
        name = get_name()
    embed = discord.Embed(title=f"System Status of `{name}`")

    # embed.set_thumbnail(url="")  # TODO: add "private" logo (maybe as an config option ...)

    if cpu:
        embed.add_field(
            name="System information", value=get_cpu_info() or "N/A", inline=False
        )
    if disk:
        embed.add_field(
            name="Disk information", value=get_disk_info() or "N/A", inline=False
        )
    if gpu:
        embed.add_field(
            name="GPU information", value=get_gpu_info() or "N/A", inline=False
        )

    embed.set_footer(text=f"Date: {datetime.datetime.now()}")

    return embed


# ---------------------------------------------------------------------------


class SelfOrAllName:
    """Discord Type Converter. Checks whether the local machine
    name is star '*' or the actual name. If not raise BadArgument
    to abort subcommand execution."""

    def __init__(self, name: str):
        self._name = name

    @classmethod
    async def convert(
        cls, ctx, argument: str  # pylint: disable=unused-argument
    ) -> "SelfOrAllName":
        if argument not in ("*", get_name()):
            raise commands.BadArgument("Not the local machine name or wildcard!")
        return cls(argument)

    @property
    def name(self) -> str:
        return self._name

    def __str__(self):
        return self._name


# ---------------------------------------------------------------------------


class SystemResourceObserverCog(commands.Cog, name="System Resource Observer"):
    def __init__(self, bot: "ObserverBot"):
        self.bot = bot

        self.limits = dict()
        self.bad_checker = NotifyBadCounterManager()
        self.stats = defaultdict(int)

        self.init_limits()

    def init_limits(self):
        # TODO: pack them in an optional file (like Flask configs) and try to load else nothing.
        self.limits.update(make_observable_limits())

    def reset_notifications(self):
        self.bad_checker.reset()

    @tasks.loop(minutes=5.0)
    async def observe_system(self):
        LOGGER.debug("Running observe system task loop ...")

        async with self.bot.get_channel(self.bot.channel_id).typing():
            # perform checks
            for name, limit in self.limits.items():
                try:
                    await self.run_single_check(name, limit)
                except Exception as ex:  # pylint: disable=broad-except
                    LOGGER.debug(
                        f"Failed to evaulate check: {limit.name}, reason: {ex}"
                    )

            self.stats["num_checks"] += 1

    async def run_single_check(self, name, limit):
        LOGGER.debug(f"Running check: {limit.name}")

        cur_value = limit.fn_retrieve()
        is_ok = limit.fn_check(cur_value, limit.threshold)

        if not is_ok:
            # check of limit was "bad", now check if we have to notify someone
            self.stats["num_limits_reached"] += 1
            self.stats[f"num_limits_reached:{name}:{limit.name}"] += 1

            # increase badness
            self.bad_checker.increase_counter(name, limit)
            if self.bad_checker.should_notify(name, limit):
                # check if already notified (that limit reached)
                # even if shortly recovered but not completely, e. g. 3->2->3 >= 3 (thres) <= 0 (not completely reset)
                await self.send(
                    limit.message.format(cur_value=cur_value, threshold=limit.threshold)
                    + f" @`{self.bot.local_machine_name}`"
                )
                self.bad_checker.mark_notified(name)
                self.stats["num_limits_notified"] += 1
        else:
            if self.bad_checker.decrease_counter(name):
                # get one-time True if changed from non-normal to normal
                await self.send(
                    f"*{limit.name} has recovered*" f" @`{self.bot.local_machine_name}`"
                )
                self.stats["num_normal_notified"] += 1

    @observe_system.before_loop
    async def before_observe_start(self):
        LOGGER.debug("Wait for observer bot to be ready ...")
        await self.bot.wait_until_ready()

    async def send(self, message):
        # TODO: send to default channel?
        channel = self.bot.get_channel(self.bot.channel_id)
        await channel.send(message)

    def cog_unload(self):
        self.observe_system.cancel()  # pylint: disable=no-member

    @commands.group(name="observer", invoke_without_command=False)
    async def observer_cmd(
        self, ctx, name: typing.Optional[SelfOrAllName] = SelfOrAllName("*"),
    ):
        """Management commands, like start/stop/status ...

        Optionally supply the name of the local machine to filter
        command execution. Beware for machine names that are the
        same as sub command names."""
        # if ctx.invoked_subcommand is None:
        # on invalid name fall back to default ("*"), but no sub-command
        # await ctx.send(f"Name provided: {name}")
        # if no name provided or wrong name, it would fall back to
        # sending help. We would need an additional attribute for checking.
        # await ctx.send_help(ctx.command)

    @observer_cmd.error
    async def observer_cmd_error(self, ctx, error):
        # seems not to really matter, i think
        # did not observe any calls to it
        pass

    @observer_cmd.command(name="start")
    @commands.cooldown(1.0, 10.0)
    async def observer_start(self, ctx):
        """Starts the background system observer loop."""
        # NOTE: check for is_running() only added in version 1.4.0
        if self.observe_system.get_task() is None:  # pylint: disable=no-member
            self.observe_system.start()  # pylint: disable=no-member
            await ctx.send(f"Observer started @`{self.bot.local_machine_name}`")
        else:
            self.observe_system.restart()  # pylint: disable=no-member
            await ctx.send(f"Observer restarted @`{self.bot.local_machine_name}`")

    @observer_cmd.command(name="stop")
    @commands.cooldown(1.0, 10.0)
    async def observer_stop(self, ctx):
        """Stops the background system observer."""
        self.observe_system.cancel()  # pylint: disable=no-member
        self.reset_notifications()
        await ctx.send(f"Observer stopped @`{self.bot.local_machine_name}`")

    @observer_cmd.command(name="status")
    @commands.cooldown(1.0, 10.0)
    async def observer_status(self, ctx):
        """Displays statistics about notifications etc."""

        if not self.stats:
            await ctx.send(f"N/A [`{self.bot.local_machine_name}`] [`not-started`]")
            return

        len_keys = max(len(k) for k in self.stats.keys())
        len_vals = max(
            len(str(v))
            for v in self.stats.values()
            if isinstance(v, (int, float, bool))
        )

        try:
            # pylint: disable=no-member
            next_time = self.observe_system.next_iteration - datetime.datetime.now(
                datetime.timezone.utc
            )
            # pylint: enable=no-member
        except TypeError:
            # if stopped, then ``next_iteration`` is None
            next_time = "?"

        message = "".join(
            [
                f"**Observer status for** `{self.bot.local_machine_name}`",
                f""" [`{"running" if self.observe_system.next_iteration is not None else "stopped"}`]""",  # pylint: disable=no-member
                "\n```\n",
                "\n".join(
                    [f"{k:<{len_keys}} {v:>{len_vals}}" for k, v in self.stats.items()]
                ),
                "\n```",
                f"\nNext check in `{next_time}`",
            ]
        )

        await ctx.send(message)

    @observer_cmd.command(name="dump-badness")
    @commands.cooldown(1.0, 10.0)
    async def observer_dump_badness(self, ctx):
        """Dump current badness values."""

        if not self.bad_checker.bad_counters:
            await ctx.send(f"N/A [`{self.bot.local_machine_name}`] [`not-started`]")
            return

        len_keys = max(len(k) for k in self.bad_checker.bad_counters.keys())
        len_vals = max(
            len(str(v))
            for v in self.bad_checker.bad_counters.values()
            if isinstance(v, (int, float, bool))
        )

        message = "".join(
            [
                f"**Badness values for** `{self.bot.local_machine_name}`",
                f""" [`{"running" if self.observe_system.next_iteration is not None else "stopped"}`]""",  # pylint: disable=no-member
                "\n```\n",
                "\n".join(
                    [
                        f"{k:<{len_keys}} {v:>{len_vals}}"
                        for k, v in self.bad_checker.bad_counters.items()
                    ]
                ),
                "\n```",
            ]
        )

        await ctx.send(message)

    @observer_cmd.command(name="dump-limits")
    @commands.cooldown(1.0, 10.0)
    async def observer_dump_limits(self, ctx):
        """Write out limits."""

        len_keys = max(len(k) for k in self.limits.keys())
        len_vals = 10

        message = "".join(
            [
                f"**Limits for** `{self.bot.local_machine_name}`",
                f""" [`{"running" if self.observe_system.next_iteration is not None else "stopped"}`]""",  # pylint: disable=no-member
                "\n```\n",
                f"""{"name":<{len_keys}} {"threshold":>{len_vals}} {"exceed?":>{len_vals}} {"notified":>{len_vals}}\n""",
                "\n".join(
                    [
                        f"{k:<{len_keys}} {v.threshold:>{len_vals}} "
                        f"{str(self.bad_checker.threshold_reached(k, v)):>{len_vals}} "
                        f"{str(self.bad_checker.notified[k]):>{len_vals}}"
                        for k, v in self.limits.items()
                    ]
                ),
                "\n```",
            ]
        )

        await ctx.send(message)


# ---------------------------------------------------------------------------


class SystemStatsCollectorCog(commands.Cog, name="System Statistics Collector"):
    def __init__(self, bot: "ObserverBot"):
        self.bot = bot

        # for a total of a week
        #   10 / 60 how often per minute,
        #     times minutes in hour, hours in day, days in week
        num = 10 / 60 * 60 * 24 * 7
        self.stats = deque(maxlen=round(num))

    @tasks.loop(minutes=5.0)
    async def collect_stats(self):
        LOGGER.debug("Running collect system stats task loop ...")

        async with self.bot.get_channel(self.bot.channel_id).typing():
            # collect stats
            try:
                cur_stats = _collect_stats(include=("cpu", "disk", "gpu"))
                if self.stats:
                    cur_stats["_id"] = self.stats[-1]["_id"] + 1
                self.stats.append(cur_stats)
            except Exception as ex:  # pylint: disable=broad-except
                LOGGER.debug(f"Failed to collect stats, reason: {ex}")

    @collect_stats.before_loop
    async def before_collect_stats_start(self):
        LOGGER.debug("Wait for observer bot to be ready ...")
        await self.bot.wait_until_ready()

    @commands.group(name="collector", invoke_without_command=False)
    async def collector_cmd(
        self, ctx, name: typing.Optional[SelfOrAllName] = SelfOrAllName("*"),
    ):
        """Management commands, like start/stop/status ...

        Optionally supply the name of the local machine to filter
        command execution. Beware for machine names that are the
        same as sub command names."""

    @collector_cmd.command(name="start")
    @commands.cooldown(1.0, 10.0)
    async def collector_start(self, ctx):
        """Starts the background system statistics collector loop."""
        # NOTE: check for is_running() only added in version 1.4.0
        if self.collect_stats.get_task() is None:  # pylint: disable=no-member
            self.collect_stats.start()  # pylint: disable=no-member
            await ctx.send(f"Collector started @`{self.bot.local_machine_name}`")
        else:
            self.collect_stats.restart()  # pylint: disable=no-member
            await ctx.send(f"Collector restarted @`{self.bot.local_machine_name}`")

    @collector_cmd.command(name="stop")
    @commands.cooldown(1.0, 10.0)
    async def collector_stop(self, ctx):
        """Stops the background system statistics collector."""
        self.collect_stats.cancel()  # pylint: disable=no-member
        await ctx.send(f"Collector stopped @`{self.bot.local_machine_name}`")

    @collector_cmd.command(name="plot")
    @commands.cooldown(1.0, 10.0)
    async def collector_plot(self, ctx):
        """Plots collected stats."""
        if not self.stats:
            await ctx.send(f"N/A @`{self.bot.local_machine_name}`")
            return

        series = stats2rows(self.stats)

        plot_bytes = plot_rows(series, as_data_uri=False)

        dfile = discord.File(
            BytesIO(plot_bytes),
            filename=f"plot-{datetime.datetime.now(datetime.timezone.utc)}.png",
        )

        await ctx.send(f"Plot @`{self.bot.local_machine_name}`", file=dfile)


# ---------------------------------------------------------------------------


class GeneralCommandsCog(commands.Cog, name="General"):
    def __init__(self, bot: "ObserverBot"):
        self.bot = bot

    @commands.command()
    async def ping(self, ctx):
        """Standard Ping-Pong latency/is-alive test."""
        await ctx.send(
            f"Pong (latency: {self.bot.latency * 1000:.1f} ms) @`{self.bot.local_machine_name}`"
        )

    @commands.command()
    async def info(self, ctx):
        """Query local system information and send it back."""
        embed = make_sysinfo_embed(name=self.bot.local_machine_name)
        await ctx.send(embed=embed)


# ---------------------------------------------------------------------------


class ObserverBot(commands.Bot):
    def __init__(
        self, channel_id: int, *args, name: typing.Optional[str] = None, **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.channel_id = channel_id

        self.local_machine_name = name or get_name()

        self.add_cog(GeneralCommandsCog(self))
        self.add_cog(SystemResourceObserverCog(self))
        self.add_cog(SystemStatsCollectorCog(self))

    async def on_ready(self):
        LOGGER.info(f"Logged on as {self.user}")
        LOGGER.debug(f"name: {self.user.name}, id: {self.user.id}")

        channel = self.get_channel(self.channel_id)
        LOGGER.info(f"Channel: {channel} {type(channel)} {repr(channel)}")
        await channel.send(
            f"Running observer bot on `{self.local_machine_name}`...\n"
            f"Type `{self.command_prefix}help` to display available commands."
        )

        await self.change_presence(status=discord.Status.idle)

    async def on_disconnect(self):
        LOGGER.warning(f"Bot {self.user} disconnected!")


# ---------------------------------------------------------------------------


def run_observer(
    token: str, channel_id: int, name: typing.Optional[str] = None
) -> typing.NoReturn:
    """Starts the observer bot and blocks until finished.

    Parameters
    ----------
    token : str
        bot authentiation token
    channel_id : int
        Discord channel id
    name : typing.Optional[str], optional
        local machine name, used for filtering, by default None
    """

    if name:
        LOGGER.info(f"Set local machine name to: {name}")
        set_name(name)

    observer_bot = ObserverBot(channel_id, name=name, command_prefix=".")
    LOGGER.info("Start observer bot ...")
    observer_bot.run(token)
    LOGGER.info("Quit observer bot.")


# ---------------------------------------------------------------------------
