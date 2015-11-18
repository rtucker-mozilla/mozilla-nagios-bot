#!/usr/bin/python2.6
import sys

from ircutils import bot
import re
import os
from settings import *
import subprocess
import time
from MozillaIRCPager import MozillaIRCPager
from MozillaNagiosStatus import MozillaNagiosStatus
class NagiosBot(bot.SimpleBot):
    my_nick = ''
    to_me = False
    message = ''
    state = 1
    MESSEGE_BUFFER = 10
    buffer_state = MESSEGE_BUFFER
    sent_mode = False
    channel_modes = {}
    ### message_commands is a list of dictionary objects. The regex object is the regex to match, the function object is the function name to call at a match

    plugins = [
                {'plugin':MozillaIRCPager},
                {'plugin':MozillaNagiosStatus},
              ]
    help_commands = []
    message_commands = []
    def load_plugins(self):
        for plugin in self.plugins:
            plugin = plugin['plugin'](self, channels)
            for mc in plugin.return_plugins():
                self.message_commands.append(mc)
            for mc in plugin.return_help():
                self.help_commands.append(mc)
    def on_channel_message(self, event):
        if re.search('^%s[,: ]' % self.bot_name, event.message):
            self.message = re.sub('^%s[,: ]+' % self.bot_name, '', event.message).strip()
            if not event.target in self.channel_modes:
                resp = self.conn.execute("MODE %s" % event.target)
                self.send_message(event.target, "%s: Checking channel security, please try again." % (event.source))
                return
            elif event.target in self.channel_modes and not 'k' in self.channel_modes[event.target]:
                self.send_message(event.target, "%s: Sorry, cannot perform action without a key being set on this channel." % (event.source))
                self.send_message(event.target, "%s: Please set a key, configure the bot to use the key and restart the bot to rejoin with a valid key." % (event.source))
                return

            if self.message.startswith('help'):
                sendable_help_messages = []
                help_command = ''
                m = re.search('help\s(.*)', self.message)
                if m:
                    help_command = m.group(1)
                    for hc in self.help_commands:
                        if hc.startswith(help_command):
                            sendable_help_messages.append(hc)
                else:
                    abbreviated_help_message = 'Available Commands: '

                    holder = []
                    for hc in self.help_commands:
                        new_message = hc.split()[0].strip()
                        holder.append(new_message) if new_message not in holder else None

                    for new_message in holder:
                        abbreviated_help_message += "| %s " % (new_message.split("|")[0])
                    sendable_help_messages.append(abbreviated_help_message)
                    if HELP_DOCUMENTATION_LINK:
                        help_text = "Documentation Here: %s" % (HELP_DOCUMENTATION_LINK)
                        sendable_help_messages.append(help_text)
                if len(sendable_help_messages) > 0:
                    if help_command != '':
                        self.send_message(event.target, "%s: Here is the help for '%s':" % (event.source, help_command))
                    for hc in sendable_help_messages:
                        self.send_message(event.target, "  %s" % (hc))
                else:
                    self.send_message(event.target, "%s: No help available for '%s'." % (event.source, help_command))

            else:
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

    def on_notice(self, event):
        print event.params
        pass
    def on_any(self, event):
        if event.command == 'RPL_CHANNELMODEIS':
            try:
                m_channel = event.params[0]
            except IndexError:
                m_channel = None

            try:
                m_channel_mode = event.params[1]
            except IndexError:
                m_channel_mode = None

            if not m_channel is None and not m_channel_mode is None:
                if not m_channel in self.channel_modes:
                    self.channel_modes[m_channel] = m_channel_mode
                else:
                    self.channel_modes[m_channel] = m_channel_mode

        """
        We need a state machine.
        start: -> s1

        s1: If we see 'End of /MOTD command'.
            If we need to register. send creds to nickserv. -> s3
            If we don't need to register. -> s4.

        s2: Send creds to nickserv. -> s3

        s3: Check the next MESSEGE_BUFFER messeges for registration
            confirmation.

            If one of the next MESSEGE_BUFFER messeges is registration
            confirmation from nickserv. -> s4.

            If we didn't see the right thing after MESSEGE_BUFFER messeges.
            Send creds to nickserv. -> s2

        s4: JOIN ALL OF THE CHANNELS! ...and then do nothing.
        """
        print event.params  # For debug
        to_nickserv = "IDENTIFY {0}".format(identify_pass)
        accept_messeges = ('Password accepted - you are now recognized.',
                'You are already identified.')
        if self.state == 1:
            if (len(event.params) > 0 and (
                    event.params[0] == "End of /MOTD command." or
                    event.params[0] == "End of message of the day."
               )):
                if REGISTER:
                    nagios_bot.send_message("NickServ", to_nickserv)
                    self.state = 3
                else:
                    print "Not going to register."
                    self.join_channels()
                    self.state = 4
                return

        if self.state == 2:
            nagios_bot.send_message("NickServ", to_nickserv)
            time.sleep(2)
            self.state == 3
            return

        # State 3 should really move to the on_notice function, but that would
        # be confusing.
        if self.state == 3:
            if (len(event.params) > 0 and event.params[0] in accept_messeges
                    and event.source == "NickServ"):
                print "Registered!!!"
                self.join_channels()
                self.state = 4
                return
            else:
                self.buffer_state -= 1
                return
            if self.buffer_state > 0:
            # We need to retry sending nickserv a messege
                self.state = 2
                self.buffer_state = self.MESSEGE_BUFFER
                return
        if event.command == "TOPIC" or event.command == 'RPL_LIST' or event.command == 'RPL_TOPIC' or event.command == 'RPL_TOPICWHOTIME':
            self.set_topic(event)

    def join_channels(self):
        print "Joining channels..."
        for channel in channels:
            self.join_channel(channel['name'])

    """ Handler for when the bot joins a room.
        Bot will ask for the topic and then it will get caught by the on_any handler
        The on_any handler will dispatch to set_topic()
    """
    def on_join(self, event):

        if not event.target in self.channel_modes:
            resp = self.conn.execute("MODE %s" % event.target)
        self.execute("TOPIC", event.target)

    def set_topic(self, event):
        #print event.target
        channel = None
        topic = None
        if event.command == "TOPIC" or event.command == 'RPL_TOPIC':
            channel = event.target
            topic = event.params[0]
        if event.command == 'RPL_TOPIC':
            channel = event.params[0]
            topic = event.params[1]
        if channel and topic:
            for c in channels:
                if c['name'] == channel:
                    c['topic'] = topic
    def on_disconnect(self, event):
        print "Disconnected, trying reconnect in 5 sec."
        time.sleep(5)
        # We need to reregister
        self.state = 1
        self.connect(server, port=port, use_ssl=use_ssl, ssl_options=ssl_options)

if __name__ == "__main__":
    nagios_bot = NagiosBot(bot_name)
    nagios_bot.bot_name = bot_name
    nagios_bot.connect(server, port=port, use_ssl=use_ssl, ssl_options=ssl_options)
    nagios_bot.load_plugins()
    nagios_bot.start()
    nagios_bot.register_listener('RPL_TOPIC', on_topic)
    nagios_bot.register_listener('topic', on_topic)
    nagios_bot.identify(identify_pass)
