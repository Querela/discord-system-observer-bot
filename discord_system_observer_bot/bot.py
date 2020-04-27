import datetime
import logging
from collections import defaultdict

import discord
from discord.ext import commands, tasks

from discord_system_observer_bot.gpuinfo import get_gpu_info
from discord_system_observer_bot.statsobserver import has_extra_deps_gpu
from discord_system_observer_bot.statsobserver import make_observable_limits
from discord_system_observer_bot.statsobserver import NotifyBadCounterManager
from discord_system_observer_bot.sysinfo import get_local_machine_name
from discord_system_observer_bot.sysinfo import get_cpu_info, get_disk_info


LOGGER = logging.getLogger(__name__)


# ---------------------------------------------------------------------------


def make_sysinfo_message(cpu=True, disk=True, gpu=True):
    message = f"**Status of `{get_local_machine_name()}`**\n"
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


def make_sysinfo_embed(cpu=True, disk=True, gpu=True):
    embed = discord.Embed(title=f"System Status of `{get_local_machine_name()}`")

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


class SystemResourceObserverCog(commands.Cog, name="System Resource Observer"):
    def __init__(self, bot, channel_id):
        self.bot = bot
        self.channel_id = channel_id
        self.local_machine_name = get_local_machine_name()

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

        async with self.bot.get_channel(self.channel_id).typing():
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
                    + f" `@{self.local_machine_name}`"
                )
                self.bad_checker.mark_notified(name)
                self.stats["num_limits_notified"] += 1
        else:
            if self.bad_checker.decrease_counter(name):
                # get one-time True if changed from non-normal to normal
                await self.send(
                    f"*{limit.name} has recovered*" f" `@{self.local_machine_name}`"
                )
                self.stats["num_normal_notified"] += 1

    @observe_system.before_loop
    async def before_observe_start(self):
        LOGGER.debug("Wait for observer bot to be ready ...")
        await self.bot.wait_until_ready()

    async def send(self, message):
        # TODO: send to default channel?
        channel = self.bot.get_channel(self.channel_id)
        await channel.send(message)

    def cog_unload(self):
        self.observe_system.cancel()  # pylint: disable=no-member

    @commands.command(name="observer-start")
    async def start(self, ctx):
        """Starts the background system observer loop."""
        # NOTE: check for is_running() only added in version 1.4.0
        if self.observe_system.get_task() is None:  # pylint: disable=no-member
            self.observe_system.start()  # pylint: disable=no-member
            await ctx.send("Observer started")
        else:
            self.observe_system.restart()  # pylint: disable=no-member
            await ctx.send("Observer restarted")

    @commands.command(name="observer-stop")
    async def stop(self, ctx):
        """Stops the background system observer."""
        self.observe_system.cancel()  # pylint: disable=no-member
        self.reset_notifications()
        await ctx.send("Observer stopped")

    @commands.command(name="observer-status")
    async def status(self, ctx):
        """Displays statistics about notifications etc."""

        if not self.stats:
            await ctx.send(f"N/A [`{self.local_machine_name}`] [`not-started`]")
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
                f"**Observer status for** `{self.local_machine_name}`",
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


def run_observer(token, channel_id):
    observer_bot = commands.Bot(command_prefix=".")

    @observer_bot.event
    async def on_ready():  # pylint: disable=unused-variable
        LOGGER.info(f"Logged on as {observer_bot.user}")
        LOGGER.debug(f"name: {observer_bot.user.name}, id: {observer_bot.user.id}")

        if channel_id is not None:
            channel = observer_bot.get_channel(channel_id)
            LOGGER.info(f"Channel: {channel} {type(channel)} {repr(channel)}")
            await channel.send(
                f"Running observer bot on `{get_local_machine_name()}`...\n"
                f"Type `{observer_bot.command_prefix}help` to display available commands."
            )

        await observer_bot.change_presence(status=discord.Status.idle)

        # TODO: maybe start observe_system task here (if required?)

    @observer_bot.event
    async def on_disconnect():  # pylint: disable=unused-variable
        LOGGER.warning(f"Bot {observer_bot.user} disconnected!")

    @observer_bot.command()
    async def ping(ctx):  # pylint: disable=unused-variable
        """Standard Ping-Pong latency/is-alive test."""
        await ctx.send(
            f"Pong (latency: {observer_bot.latency * 1000:.1f} ms) [`{get_local_machine_name()}`]"
        )

    @observer_bot.command()
    async def info(ctx):  # pylint: disable=unused-variable
        """Query local system information and send it back."""
        # message = get_info_message()
        # await ctx.send(message)
        embed = make_sysinfo_embed()
        await ctx.send(embed=embed)

    observer_bot.add_cog(SystemResourceObserverCog(observer_bot, channel_id))

    LOGGER.info("Start observer bot ...")
    observer_bot.run(token)
    LOGGER.info("Quit observer bot.")


# ---------------------------------------------------------------------------
