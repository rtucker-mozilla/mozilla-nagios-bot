#!/usr/bin/python2.6
import sys

from ircutils import bot
import re
import os
from settings import *
import subprocess
from MozillaIRCPager import MozillaIRCPager
from MozillaNagiosStatus import MozillaNagiosStatus
class NagiosBot(bot.SimpleBot):
    my_nick = ''
    to_me = False
    message = ''
    ### message_commands is a list of dictionary objects. The regex object is the regex to match, the function object is the function name to call at a match

    plugins = [
                {'plugin':MozillaIRCPager},
                {'plugin':MozillaNagiosStatus},
              ]
    message_commands = []
    def load_plugins(self):
        self.message_commands.append({'class':NagiosBot, 'regex':'help$', 'function':'print_help'})
        for plugin in self.plugins:
            plugin = plugin['plugin'](self)
            for mc in plugin.return_plugins():
                self.message_commands.append(mc)
    def on_channel_message(self, event):
        if re.search('^%s[,: ]' % self.bot_name, event.message):
            self.message = re.sub('^%s[,: ]+' % self.bot_name, '', event.message).strip()
            _is_found = False
            for message_command in self.message_commands:
                if _is_found is False:
                    m = re.search(message_command['regex'], self.message)
                    if m is not None:
                        _is_found = True
                        try:
                            target, message = message_command['callback'](event, event.message, m)
                            if isinstance(message, basestring):
                                self.send_message(target, message)
                            else:
                                for m in message:
                                    self.send_message(target, m)

                        except Exception, e:
                            self.send_message(event.target, "%s: %s From Exception I'm sorry but I don't understand your command" % (e, event.source) )
            if _is_found is False:
                self.send_message(event.target, "%s: I'm sorry but I don't understand your command" % (event.source) )

    @staticmethod            
    def print_help(conn, event, options):
        messages = []
        messages.append("page <id> (Optional) <recipient> (Required) <message> (Reqired)")
        print event.target
        for message in messages:
            conn.send_message(event.target, message)
    

if __name__ == "__main__":
    nagios_bot = NagiosBot(bot_name)
    nagios_bot.bot_name = bot_name
    nagios_bot.connect(server, port=port, use_ssl=use_ssl, channel = channels, ssl_options=ssl_options)
    nagios_bot.load_plugins()
    nagios_bot.start()
