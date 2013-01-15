# The contents of this file are subject to the Mozilla Public License
# Version 1.1 (the "License"); you may not use this file except in
# compliance with the License. You may obtain a copy of the License at
# http://www.mozilla.org/MPL/
#
# Software distributed under the License is distributed on an "AS IS"
# basis, WITHOUT WARRANTY OF ANY KIND, either express or implied. See the
# License for the specific language governing rights and limitations
# under the License.
#
# The Original Code is mozilla-nagios-bot
#
# The Initial Developer of the Original Code is Rob Tucker. Portions created
# by Rob Tucker are Copyright (C) Mozilla, Inc. All Rights Reserved.
#
# Alternatively, the contents of this file may be used under the terms of the
# GNU Public License, Version 2 (the "GPLv2 License"), in which case the
# provisions of GPLv2 License are applicable instead of those above. If you
# wish to allow use of your version of this file only under the terms of the
# GPLv2 License and not to allow others to use your version of this file under
# the MPL, indicate your decision by deleting the provisions above and replace
# them with the notice and other provisions required by the GPLv2 License. If
# you do not delete the provisions above, a recipient may use your version of
# this file under either the MPL or the GPLv2 License.

import subprocess
from MozillaIRCPager_settings import *
from MozillaNagiosStatus_settings import ONCALL_FILE
from settings import logger
import re
class MozillaIRCPager:
    def __init__(self, connection, channels=[]):
        self.PAGE_SCRIPT = PAGE_SCRIPT
        self.oncall_file = ONCALL_FILE
        self.message_commands = []
        self.build_regex_list()

    def build_regex_list(self):
        self.message_commands.append({'regex':'^page\s+([A-Za-z][_A-Za-z0-9]*?)\s+(.+)\s*$', 'callback':self.page,})

    ###Default entry point for each plugin. Simply returns a regex and which static method to call upon matching the regex
    def return_plugins(self):
        return self.message_commands

    def page(self, event, message, options, is_indexed_page=False):
        """
            call a shell script passing recipient then message to send a page to a person
            param: event - the irc event that occured
            param: message - the message to send
            param: options - regular expression object that contains the message from irc
            param: is_indexed_page - variable to be set if we're paging based on an alert index
                   If set to true, the recipient is the options.group(2) instead of options.group(1)
                   This is a bit hacky and should be refactored at a later point
        """

        should_page = False
        if is_indexed_page:
            recipient = options.group(2)
        else:
            recipient = options.group(1)
            message = "%s(%s)" % (options.group(2), event.source)
        if recipient == "oncall":
            recipient = self.get_oncall_from_file()
        ##Check that we have a valid message and recipient and set should_page to true
        if message is not None and recipient is not None:
            should_page = True
        ##If we should page, than page. If not set the return code to a non-zero value so we can display a message to the caller
        if should_page is True:
            ret = subprocess.call([self.PAGE_SCRIPT, recipient, message])
        else:
            ret = -1

        if ret is 0:
            return event.target, "%s: %s has been paged with the message \"%s\"" % (event.source, recipient, message)
        else:
            return event.target, "%s: %s could not be paged" % (event.source, recipient)

    def get_oncall_from_file(self):
        oncall = 'not-yet-set'
        try:
            fh = open(self.oncall_file)
            for line in fh.readlines():
                m = re.search("; On Call = (.+)$", line)
                if m:
                    oncall = m.group(1)
        except Exception, e:
            print e
            oncall = 'not-yet-set'
        return oncall

    def return_help(self):
        return [
            'page <recipient|oncall> <message to send>',
                ]
