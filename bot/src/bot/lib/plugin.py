from .errors import PluginException
from .logging import logger
from .helpers import formatting as f
from .transaction import Transaction
from .decorators.validator import COMMAND_VALIDATORS_ATTR

from time import time
from inspect import getmembers, isfunction
from functools import partial
from traceback import format_exc

import asyncio
import logging

class Plugin:

    def __init__(self, bot, config):
        self.bot = bot
        self.db = bot.db
        self.config = config

        self.actions = self._action_list()

        # Logging helpers
        self.debug    = partial(self.log, logging.DEBUG)
        self.info     = partial(self.log, logging.INFO)
        self.warning  = partial(self.log, logging.WARNING)
        self.error    = partial(self.log, logging.ERROR)
        self.critical = partial(self.log, logging.CRITICAL)

    '''
    Helpers
    '''

    def log(self, level, message):
        extra = dict(plugin_name=self.__class__.__name__)
        logger.log(level, message, extra=extra)

    def transaction(self):
        return Transaction(self.db)

    async def send_message(self, channel, content, **kwargs):
        self.debug('Sending message: "{}"'.format(content))
        return await self._send(
            self.bot.send_message, channel,
            content=content, **kwargs
        )

    async def send_file(self, channel, file_path, **kwargs):
        self.debug('Sending file: "{}"'.format(file_path))
        return await self._send(
            self.bot.send_file, channel, file_path,
            **kwargs
        )

    async def edit_message(self, message, content, **kwargs):
        self.debug(
            'Editing message: "{}" -> "{}"'
                .format(message.content, content)
        )
        return await self.bot.edit_message(
            message,
            f.truncated_content(content)
        )

    async def stream_data(self, message, iterator, formatter, lines=15, every=3):
        formatted_lines = []
        started = 0

        async def update_stream():
            content = f.code_block(formatted_lines[-lines:])
            await self.edit_message(message, content)

        async for data in iterator:
            text = formatter(data)
            formatted_lines.append(text)

            if time() - started > every:
                await update_stream()
                started = time()

        await update_stream()

    async def delete_message_after(self, message, seconds):
        await asyncio.sleep(seconds)
        await self.bot.delete_message(message)

    def run_async(self, future):

        async def run():
            try:
                await future
            except Exception:
                self.error(format_exc(10))

        asyncio.ensure_future(run())

    '''
    Dispatchers
    '''

    async def dispatch_new(self, message):
        self.match_commands(message)
        await self.on_new(message)

    async def dispatch_deleted(self, message):
        await self.on_delete(message)

    async def dispatch_edit(self, before, after):
        if not after.edited_timestamp: # resolved links, ignored for now
            return

        self.match_commands(after)
        await self.on_edit(before, after)

    async def on_new(self, message):
        pass

    async def on_delete(self, message):
        pass

    async def on_edit(self, before, after):
        pass

    def match_commands(self, message):
        for validator, action in self.actions:
            is_match, context = validator(message.content)
            if is_match:
                future = self.invoke_command(action, message, **context)
                asyncio.ensure_future(future)

    async def invoke_command(self, command, message, **context):
        try:
            future = command(self, message, **context)
            if future:
                await future
        except PluginException as me:
            await self.send_message(
                message.channel,
                me.error(message),
                delete_after=5
            )
        except Exception:
            self.error(format_exc(10))

    '''
    Detail
    '''

    def _action_list(self):
        actions = []

        for _, function in getmembers(self.__class__, isfunction):
            if hasattr(function, COMMAND_VALIDATORS_ATTR):
                validators = getattr(function, COMMAND_VALIDATORS_ATTR)
                for validator in validators:
                    actions.append((validator, function))

        return actions

    async def _send(self, method, *args, **kwargs):
        try:
            content = kwargs['content']
            kwargs['content'] = f.truncated_content(content)
        except KeyError:
            pass

        delete_after = kwargs.pop('delete_after', None)

        try:
            message = await method(*args, **kwargs)
        except Exception as e:
            self.error('{} failed: {}'.format(method.__name__, e))
            return None

        if delete_after:
            future = self.delete_message_after(message, delete_after)
            asyncio.ensure_future(future)

        return message
