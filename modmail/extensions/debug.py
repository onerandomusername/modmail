"""
Useful commands for debugging built in bot issues.

Often a problem is a configuration issue, this cog will help determine issues.
"""

import logging
import typing

import discord
from discord.ext import commands
from discord.ext.commands import Context

import modmail
from modmail.bot import ModmailBot
from modmail.log import ModmailLogger
from modmail.utils.cogs import BotModes, ExtMetadata, ModmailCog
from modmail.utils.extensions import BOT_MODE
from modmail.utils.pagination import ButtonPaginator


logger: ModmailLogger = logging.getLogger(__name__)

EXT_METADATA = ExtMetadata()

EXTRAS_DEBUG_KEY = "only_if_cog_debug"


class AlreadyInModeError(Exception):
    """Raised if the cog is already in a mode."""

    pass


class DebugCog(ModmailCog, name="Debugger"):
    """Debug commands."""

    def __init__(self, bot: ModmailBot):
        self.bot = bot
        self.enable_debug_commands = bool(BOT_MODE & BotModes.DEVELOP.value)
        self.enable_or_disable_commands(self.enable_debug_commands, force=True)

    def enable_or_disable_commands(self, new_status: bool = None, *, force: bool = False) -> bool:
        """Enable or disable debug only commands."""
        if not force and (new_status == self.enable_debug_commands):
            raise AlreadyInModeError(new_status)
        elif new_status is not None:
            self.enable_debug_commands = new_status
        else:
            self.enable_debug_commands = not self.enable_debug_commands

        for com in self.walk_commands():
            if com.extras.get(EXTRAS_DEBUG_KEY, False):
                com.enabled = self.enable_debug_commands
        return self.enable_debug_commands

    @commands.group(invoke_without_command=True)
    async def debug(self, ctx: Context, enable_or_disable: bool = None) -> None:
        """Commands to show logs and debug portions of the bot."""
        if enable_or_disable is not None:
            print(enable_or_disable)
            if enable_or_disable:
                self.enable_or_disable_commands(True)
                msg = "Enabled the debugger commands."
            else:
                self.enable_or_disable_commands(False)
                msg = "Disabled the debugger commands."
            await ctx.send(msg)
            return

        await ctx.send(self.enable_debug_commands)

    @staticmethod
    def get_logs(tail_lines: int = 200, lines_per_page: int = 10) -> typing.List[str]:
        """Get a list of the tail logs."""
        logs = []

        pages = tail_lines // lines_per_page
        if tail_lines < lines_per_page:
            pages = 1

        try:
            f = open(modmail.log_file)
            all_logs = f.read()
        finally:
            f.close()
        # get the last lines on the code
        pos = len(all_logs)
        for _ in range(tail_lines):
            if (nl_pos := all_logs.rfind("\n", None, pos)) == -1:
                break
            pos = nl_pos

        # split away the useless section
        all_logs = all_logs[pos:]
        for _ in range(pages):
            slice_pos = -1
            for _ in range(lines_per_page):
                if (
                    (inital_slice_pos := all_logs.find("\n", slice_pos + 1)) == -1
                ) or slice_pos == inital_slice_pos:
                    break
                slice_pos = inital_slice_pos
            if not len(to_append := all_logs[:slice_pos]) > 0:
                continue
            logs.append(to_append)
            all_logs = all_logs[slice_pos:]

        print(len(logs))
        return logs

    @debug.command(name="logs", aliases=("log",), extras={EXTRAS_DEBUG_KEY: True})
    async def logs(self, ctx: Context) -> None:
        """Paginate through the last 10 pages of logs."""
        logs = self.get_logs()
        await ButtonPaginator.paginate(
            logs,
            ctx.message,
            title="**Modmail Logs**",
            prefix="```prolog\n",
            suffix="```",
            embed=None,
            max_size=2000,
        )

    @debug.command(name="dump", extras={EXTRAS_DEBUG_KEY: True})
    async def dump_logs(self, ctx: Context) -> None:
        """Dump the log file in the chat."""
        logger.info(f"{ctx.author!s} requested the logs")
        async with ctx.typing():
            with open(modmail.log_file, "rb") as f:
                file = discord.File(f, filename="modmail-logs.prolog")

        await ctx.send(
            "Please share this file with the developers. Do not share this with anyone else, "
            "as there may be sensitive information in this file.",
            file=file,
        )


def setup(bot: ModmailBot) -> None:
    """Add the debug cog to the bot."""
    bot.add_cog(DebugCog(bot))
