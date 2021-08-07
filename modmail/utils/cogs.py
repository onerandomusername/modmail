from dataclasses import dataclass
from enum import IntEnum, auto

from discord.ext import commands


class BitwiseAutoEnum(IntEnum):
    """Enum class which generates binary value for each item."""

    def _generate_next_value_(name, start, count, last_values) -> int:  # noqa: ANN001 N805
        return 1 << count


class BotModes(BitwiseAutoEnum):
    """
    Valid modes for the bot.

    These values affect logging levels, which extensions are loaded, and so forth.
    """

    production = auto()
    develop = auto()
    plugin_dev = auto()


BOT_MODES = BotModes


@dataclass()
class ExtMetadata:
    """Ext metadata class to determine if extension should load at runtime depending on bot configuration."""

    # prod mode
    # set this to true if the cog should always load
    production: bool = False
    # load if bot is in development mode
    # development mode is when the bot has its metacogs loaded, like the eval and extension cogs
    develop: bool = False
    # plugin development mode
    # used for loading bot plugins that help with plugin debugging
    plugin_dev: bool = False


def calc_mode(metadata: ExtMetadata) -> int:
    """Calculate the combination of different variables and return the binary combination."""
    mode = int(getattr(metadata, "production", False))
    mode += int(getattr(metadata, "develop", False) << 1) or 0
    mode = mode + (int(getattr(metadata, "plugin_dev", False)) << 2)
    return mode


class ModmailCog(commands.Cog):
    """
    The base class that all cogs must inherit from.

    A cog is a collection of commands, listeners, and optional state to
    help group commands together. More information on them can be found on
    the :ref:`ext_commands_cogs` page.

    When inheriting from this class, the options shown in :class:`CogMeta`
    are equally valid here.
    """

    pass