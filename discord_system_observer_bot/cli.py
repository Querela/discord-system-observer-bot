import argparse
import configparser
import logging
import os
import pathlib
import sys

from discord_system_observer_bot.bot import run_observer


LOGGER = logging.getLogger(__name__)


# ---------------------------------------------------------------------------


CONFIG_SECTION_NAME = "discord-bot"

CONFIG_PATHS = [
    pathlib.Path.home() / ".dbot.conf",
    pathlib.Path.home() / "dbot.conf",
    pathlib.Path(".") / ".dbot.conf",
    pathlib.Path(".") / "dbot.conf",
    pathlib.Path("/etc/dbot.conf"),
]


def find_config_file():
    for filename in CONFIG_PATHS:
        if filename.exists():
            LOGGER.info(f"Found config file: {filename}")
            return filename

    LOGGER.error("Found no configuration file in search path!")
    return None


def load_config_file(filename):
    config = configparser.ConfigParser()

    LOGGER.debug(f"Try loading configurations from {filename}")

    try:
        config.read(filename)

        if CONFIG_SECTION_NAME not in config:
            LOGGER.error(f"Missing configuration section header: {CONFIG_SECTION_NAME}")
            return None

        configs = config[CONFIG_SECTION_NAME]

        return {
            "token": configs["token"].strip('"'),
            "channel": int(configs["channel"]),
        }
    except KeyError as ex:
        LOGGER.error(f"Missing configuration key! >>{ex.args[0]}<<")
    except:  # pylint: disable=bare-except
        LOGGER.exception("Loading configuration failed!")
    return None


def load_config(filename=None, **kwargs):
    configs = None

    if filename and os.path.isfile(filename):
        configs = load_config_file(filename)
        if configs is None:
            LOGGER.error("Loading given config file failed! Trying default ones ...")

    if configs is None:
        filename = find_config_file()
        if filename is not None:
            configs = load_config_file(filename)

    if configs is None:
        if "token" not in kwargs or "channel" not in kwargs:
            raise Exception("No configuration file found!")

    configs = {**configs, **kwargs}

    return configs


# ---------------------------------------------------------------------------


def parse_args(args=None):
    parser = argparse.ArgumentParser()

    parser.add_argument("-c", "--config", type=str, default=None, help="Config file")
    parser.add_argument(
        "-d", "--debug", action="store_true", help="Enable debug logging"
    )

    args = parser.parse_args(args)
    return args


def setup_logging(debug=False):
    if debug:
        # logging.basicConfig(format="* %(message)s", level=logging.INFO)
        logging.basicConfig(
            format="[%(levelname).1s] {%(name)s} %(message)s", level=logging.DEBUG
        )
        logging.getLogger("websockets.protocol").setLevel(logging.WARNING)
        logging.getLogger("websockets.client").setLevel(logging.WARNING)
        logging.getLogger("discord.client").setLevel(logging.WARNING)


# ---------------------------------------------------------------------------


def main(args=None):
    args = parse_args(args)

    setup_logging(args.debug)

    configs = load_config(filename=args.config)
    LOGGER.debug(f"Run bot with configs: {configs}")

    try:
        run_observer(configs["token"], configs["channel"])
    except:  # pylint: disable=bare-except
        sys.exit(1)

    LOGGER.info("Done.")


# ---------------------------------------------------------------------------
