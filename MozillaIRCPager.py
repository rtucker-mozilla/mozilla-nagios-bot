import subprocess
from MozillaIRCPager_settings import *
from settings import logger

class MozillaIRCPager:
    def __init__(self, connection):
        self.PAGE_SCRIPT = PAGE_SCRIPT
        self.message_commands = []
        self.build_regex_list()

    def build_regex_list(self):
        self.message_commands.append({'regex':'^page\s+([A-Za-z][_A-Za-z0-9]+?)\s+(.+)\s*$', 'callback':self.page,})

    ###Default entry point for each plugin. Simply returns a regex and which static method to call upon matching the regex
    def return_plugins(self):
        return self.message_commands

    def page(self, event, message, options):
        should_page = False
        recipient = options.group(1)
        message = options.group(2)

        ##Check that we have a valid message and recipient and set should_page to true
        if message is not None and recipient is not None:
            should_page = True
        ##If we should page, than page. If not set the return code to a non-zero value so we can display a message to the caller
        if should_page is True:
            ret = subprocess.call([self.PAGE_SCRIPT, recipient, message])
        else:
            ret = -1

        if ret is 0:
            return event.target, "%s: %s has been paged" % (event.source, recipient)
        else:
            return event.target, "%s: %s could not be paged" % (event.source, recipient)
