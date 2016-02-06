from ..base import Module, command

from .handler import GithubHandler

class Github(Module):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.notified_channels = set()
        self.bot.web_app.add_handlers(r'.*$', [
            (r'/github', GithubHandler, dict(module=self))
        ])

    @command('!github enable')
    async def enable_notifications(self, message):
        self.notified_channels.add(message.channel)

        message = '`Github` notifications are now **enabled** in this channel'
        await self.respond(message)

    @command('!github disable')
    async def disable_notifications(self, message):
        self.notified_channels.discard(message.channel)

        message = '`Github` notifications are now **disabled** in this channel'
        await self.respond(message)

    async def github_notification(self, event_type, data):
        message = build_message(event_type, data)

        for channel in self.notified_channels:
            await self.bot.client.send_message(channel, message)

def build_message(event_type, data):
    message = 'Received a **`{}`** event from Github'.format(event_type)

    try:
        details = DETAILS_HANDLERS[event_type](data)
        message = '{}\n{}'.format(message, details)
    except KeyError:
        pass

    return message

def push_details(data):
    return """
        **@{pusher}** just {forced}pushed **{commit_count} commit(s)** to `{repository}` on branch `{branch}`
        summary of commits:
        ```
        {summary}
        ```
    """.format(
        pusher=data['pusher']['name'],
        forced='**forced** ' if data['forced'] else '',
        commit_count=len(data['commits']),
        repository=data['repository']['name'],
        branch=data['ref'].split('/')[-1],
        summary='\n'.join(map(lambda c: c['message'], data['commits']))
    )

def pull_request_details(data):
    return """
        A pull request has been **{action}** by **@{who}**
        see {link} for more details
    """.format(
        action=data['action'],
        who=data['sender']['login'],
        link=data['pull_request']['html_url']
    )

DETAILS_HANDLERS = {
    'push': push_details,
    'pull_request': pull_request_details
}
