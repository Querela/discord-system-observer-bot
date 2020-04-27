===========================
Discord-System-Observer-Bot
===========================

.. start-badges

.. image:: https://img.shields.io/github/release/Querela/discord-system-observer-bot.svg
   :alt: GitHub release
   :target: https://github.com/Querela/discord-system-observer-bot/releases/latest

.. image:: https://img.shields.io/github/languages/code-size/Querela/discord-system-observer-bot.svg
   :alt: GitHub code size in bytes
   :target: https://github.com/Querela/discord-system-observer-bot/archive/master.zip

.. image:: https://img.shields.io/github/license/Querela/discord-system-observer-bot.svg
   :alt: MHTML License
   :target: https://github.com/Querela/discord-system-observer-bot/blob/master/LICENSE

.. image:: https://img.shields.io/pypi/pyversions/discord-notifier-bot.svg
   :alt: PyPI supported Python versions
   :target: https://pypi.python.org/pypi/discord-notifier-bot

.. image:: https://img.shields.io/badge/code%20style-black-000000.svg
   :alt: Code style: black
   :target: https://github.com/psf/black

.. end-badges

A simple python `Discord <https://discordapp.com/>`_ bot that observes a local machine and sends notifications on resource exhaustion. It allows additionally to query the machine status via Discord.

It registers the following command:

* ``dbot-observe`` - a blocking script, that runs periodic system checks and notifies about shortages
  (*may require extra dependencies to be installed for more information*)

Requirements
------------

* Python >= 3.6 (*see badges above*)
* `discord.py <https://github.com/Rapptz/discord.py>`_
* `psutil <https://github.com/giampaolo/psutil>`_ (*for cpu/ram/disk information querying*)
* Extra:

  * ``gpu``: `GPUtil <https://github.com/anderskm/gputil>`_
  * ``plot``: matplotlib, for generating plots

Installation
------------

.. code-block:: bash

   python3 -m pip install discord-system-observer-bot

Optionally, install it locally with ``--user``.

For GPU infos, you have to install extra dependencies: **gpu** (``nvidia-smi`` information):

.. code-block:: bash

   python3 -m pip install discord-system-observer-bot[gpu]

Configuration
-------------

Configuration is done by placing a .dbot.conf file in one of the following directories:

   * ``$HOME/.dbot.conf``
   * ``$HOME/dbot.conf``
   * ``./.dbot.conf``
   * ``./dbot.conf``
   * ``/etc/dbot.conf``

Alternatively a configuration file can be provided via ``-c``/``--config`` CLI options.

The configuration file should be a standard INI file. A template can be found in the ``templates`` folder. All configurations are placed under the ``discord-bot`` section.

Example:

.. code-block:: ini

   [discord-bot]
   # the bot token (used for login)
   token = abc
   # the numeric id of a channel, can be found when activating the developer options in appearances
   channel = 123

Usage
-----

``dbot-observe`` is the main entry-point.

Print help and available options:

.. code-block:: bash

   dbot-observe -h

Starting the observer bot (without actually starting the background observation, just waiting for a Discord message to start/stop etc.):

.. code-block:: bash

   dbot-observe 

You are always able to specify the configuration file like this:

.. code-block:: bash

   dbot-observe -c /path/to/dbot.conf [...]

To display debugging information (api calls, log messages etc.):

.. code-block:: bash

   dbot-observe -d [...]

You may also run the bot with the python module notation. But it will only run the same entry-point like ``dbot-observe``.

.. code-block:: bash

   python -m discord_system_observer_bot [...]

System Observer Bot
~~~~~~~~~~~~~~~~~~~

The ``dbot-observe`` command runs a looping Discord task that checks every **5 min** some predefined system conditions,
and sends a notification if a ``badness`` value is over a threshold.
This ``badness`` value serves to either immediatly notify a channel if a system resource is exhausted or after some repeated limit exceedances.

The code (checks and limits) can be found in `discord_system_observer_bot.sysinfo <https://github.com/Querela/discord-system-observer-bot/blob/master/discord_system_observer_bot/sysinfo.py>`_.
The current limits are some less-than educated guesses, and are subject to change.
Dynamic configuration is currently not an main issue, so users may need to clone the repo, change values and install the python package from source:

.. code-block:: bash

   git clone https://github.com/Querela/discord-system-observer-bot.git
   cd discord-system-observer-bot/
   # [do the modifications in discord_system_observer_bot/sysinfo.py]
   python3 -m pip install --user --upgrade --editable .[gpu,plot]

The system information gathering may require the extra dependencies to be installed, like ``gpu`` for GPU information, or ``plot`` for series charts.

I suggest that you provide a different Discord channel for those notifications and create an extra ``.dbot-observer.conf`` configuration file that can then be used like this:

.. code-block:: bash

   dbot-observe [-d] -c ~/.dbot-observer.conf


Embedded in other scripts
~~~~~~~~~~~~~~~~~~~~~~~~~

Sending messages is rather straightforward.
More complex examples can be found in the CLI entrypoints, see file `discord_system_observer_bot.cli <https://github.com/Querela/discord-system-observer-bot/blob/master/discord_system_observer_bot/cli.py>`_.
Below are some rather basic examples (extracted from the CLI code).

Basic setup (logging + config loading):

.. code-block:: python

   from discord_system_observer_bot.cli import setup_logging, load_config

   # logging (rather basic, if needed)
   setup_logging(True)

   # load configuration file (provide filename or None)
   configs = load_config(filename=None)

Sending a message:

.. code-block:: python

   from discord_system_observer_bot.bot import run_observer

   # bot token and channel_id (loaded from configs or hard-coded)
   bot_token, channel_id = configs["token"], configs["channel"]
   # start the observer running (blocks forever)
   run_observer(bot_token, channel_id, message)


Bot Creation etc.
-----------------

See information provided by:

* `Tutorial for setting up a bot <https://github.com/Chikachi/DiscordIntegration/wiki/How-to-get-a-token-and-channel-ID-for-Discord>`_
* `Discord developer application page <https://discordapp.com/developers/applications/>`_

Short description
~~~~~~~~~~~~~~~~~

**You have to own a Discord server! Or know someone with administrator/moderation(?) privileges.**

1. Visit and login to the `Discord developer page <https://discordapp.com/developers/applications/>`_.
#. Create a new application. The given name is also the visible name of the bot. (default, can be changed later?)
#. Create a bot (on the *Bot* page). You should disable the *Public Bot* option.

   * The bot login token (credentials) can be found on the *Bot* page.

#. Change to the *OAuth2* page and check

   * Scopes: *Bot*
   * Bot Permissions: *Send Messages*, *Attach Files* (in the *Text Permissions* column)

#. Copy the URL in the *Scopes* section and paste it in a new browser tab.

   * Now you can choose one (?) of your **own** Discord servers to add the bot to.
     *(For this you need server administration permissions, or be the owner..?)*

To get the channel id, send the following message on your server ``\#channelname``, or enable developer options.
You may want to visit the following pages for more information:

* `discord.py bot help <https://discordpy.readthedocs.io/en/latest/discord.html>`_,
* `Discord Help <https://support.discordapp.com/hc/de/articles/206346498-Wie-finde-ich-meine-Server-ID->`_,
* `reddit post <https://www.reddit.com/r/discordapp/comments/50thqr/finding_channel_id/>`_.

Related
-------

* `Discord-Notifier-Bot <https://github.com/Querela/discord-notifier-bot>`_,
  a simple CLI tool to send notification messages or files to Discord

Copyright and License Information
---------------------------------

Copyright (c) 2020 Erik Körner.  All rights reserved.

See the file "LICENSE" for information on the history of this software, terms &
conditions for usage, and a DISCLAIMER OF ALL WARRANTIES.

All trademarks referenced herein are property of their respective holders.
