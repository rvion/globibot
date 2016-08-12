from bot.lib.plugin import Plugin
from bot.lib.decorators import command
from bot.lib.helpers import parsing as p
from bot.lib.helpers import formatting as f
from bot.lib.helpers.hooks import master_only

from itertools import groupby

from .ws_handler import LoggerWebSocketHandler
from . import queries as q

class Logger(Plugin):

    def load(self):
        self.ws_consumers = set()

        self.bot.web.add_handlers(r'.*$', [
            (r'/ws/logs', LoggerWebSocketHandler, dict(module=self)),
        ])

    '''
    Raw events
    '''

    async def on_new(self, message):
        self.save_log(message, message.timestamp)
        self.notify_ws(message, 'original')

    async def on_delete(self, message):
        with self.transaction() as trans:
            trans.execute(q.mark_deleted, dict(
                id = message.id
            ))

        self.notify_ws(message, 'deleted')

    async def on_edit(self, before, after):
        self.save_log(after, after.edited_timestamp)
        self.notify_ws(after, 'edit')

    '''
    Commands
    '''

    @command(
        p.string('!deleted') + p.bind(p.mention,          'user_id')
                             + p.bind(p.maybe(p.integer), 'count'),
        master_only
    )
    async def deleted_messages(self, message, user_id, count=5):
        with self.transaction() as trans:
            trans.execute(q.last_deleted_logs, dict(
                author_id = user_id,
                limit     = count
            ))
            results = trans.fetchall()
            messages = [
                '{}{}'.format(row[0], ' '.join(row[1]))
                for row in results
            ]

            await self.send_message(
                message.channel,
                'last **{}** deleted messages from <@{}>:\n{}'
                    .format(len(results), user_id, f.code_block(messages)),
                delete_after = 30
            )

    @command(
        p.string('!edited') + p.bind(p.mention,          'user_id')
                            + p.bind(p.maybe(p.integer), 'count'),
        master_only
    )
    async def edited_messages(self, message, user_id, count=10):
        with self.transaction() as trans:
            trans.execute(q.last_edited_logs, dict(
                author_id = user_id,
                limit     = count
            ))
            results = trans.fetchall()
            grouped = groupby(results, key=lambda row: row[0])

            messages = [
                ' ➡ '.join([
                    '{}{}'.format(c[1], ' '.join(c[2]))
                    for c in reversed(list(contents))
                ])
                for _, contents in grouped
            ]

            await self.send_message(
                message.channel,
                'last **{}** edited messages from <@{}>:\n{}'
                    .format(len(messages), user_id, '\n'.join(messages)),
                delete_after = 30
            )

    @command(
        p.string('!logs') + p.string('find')
                          + p.bind(p.mention, 'user_id')
                          + p.bind(p.word, 'what')
                          + p.bind(p.maybe(p.integer), 'count'),
        master_only
    )
    async def logs_find(self, message, user_id, what, count=10):
        with self.transaction() as trans:
            trans.execute(q.find_logs, dict(
                author_id = user_id,
                str       = '%%{}%%'.format(what),
                limit     = count
            ))
            results = trans.fetchall()
            messages = [r[0] for r in results]

            await self.send_message(
                message.channel,
                'Found **{}** messages\n{}'
                    .format(len(results), f.code_block(messages)),
                delete_after = 30
            )

    @command(p.string('!logs') + p.string('top') + p.bind(p.maybe(p.integer), 'count'))
    async def most_active(self, message, count = 10):
        with self.transaction() as trans:
            trans.execute(q.most_logs, dict(
                server_id = message.server.id,
                limit     = count
            ))
            results = [
                '{}: {:,} messages'.format(f.mention(r[0]), r[1])
                for r in trans.fetchall()
            ]

            await self.send_message(
                message.channel,
                'most **{}** active users on this server\n{}'
                    .format(len(results), '\n'.join(results)),
                    delete_after = 30
            )

    '''
    Details
    '''

    def save_log(self, message, stamp):
        attachments = [attachment['url'] for attachment in message.attachments]

        with self.transaction() as trans:
            trans.execute(q.create_log, dict(
                id          = message.id,
                server_id   = message.server.id,
                channel_id  = message.channel.id,
                author_id   = message.author.id,
                content     = message.content,
                stamp       = stamp,
                attachments = attachments
            ))

    def notify_ws(self, message, t):
        data = dict(
            server_id   = message.server.id,
            channel_id  = message.channel.id,
            author      = message.author.name,
            content     = message.content,
            type        = t
        )
        for consumer in self.ws_consumers:
            consumer.write_message(data)
