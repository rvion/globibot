from ..errors import PluginException

class NotMasterError(PluginException):

    def error(self, message):
        return (
            '{} You\'re not the boss of me'
                .format(message.author.mention)
        )

def master_only(bot, message):
    return bot.is_master(message.author)

def master_only_verbose(bot, message):
    if not bot.is_master(message.author):
        raise NotMasterError
    return True
