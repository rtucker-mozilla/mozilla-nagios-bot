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
import datetime
import re
class NagiosLogLine:
    def __init__(self, line):
        self.is_service = False
        self.time_string = datetime.datetime.now().strftime("%a %H:%m:%S")
        self.line = line.strip()
        self.notification_list = []
        self.notification_recipient = None
        self.notification_type = None
        self.host = None
        self.service = None
        self.message = None
        self._is_notification()
        
        if self.is_notification:
            self.notification_type = self._get_notification_type()
            self._build_notification_list()
            self.notification_recipient = self._get_notification_recipient()
            self.host = self._get_host()
            self.service = self._get_service()
            self.state = self._get_state()
            self.message = self._get_message()

    def _get_host(self):
        return self.notification_list[1]

    def _get_service(self):
        if self.is_service:
            self.is_service = True
            return self.notification_list[2]
        else:
            return None

    def _get_state(self):
        if self.is_service:
            return self.notification_list[3]
        else:
            return self.notification_list[2]

    def _get_message(self):
        if self.is_service:
            return self.notification_list[5]
        else:
            return self.notification_list[4]

    def _is_notification(self):
        m = re.search("^\[\d+\]\s(HOST|SERVICE) NOTIFICATION:", self.line)
        if m:
            self.is_notification = True
        else:
            self.is_notification = False

    def _build_notification_list(self):
        m = re.search("^\[\d+\]\s(HOST|SERVICE) NOTIFICATION: ([^;]+;(.*))$", self.line)
        self.notification_list = m.group(2).split(";")

    def _get_notification_recipient(self):
        return self.notification_list[0]

    def _get_notification_type(self):
        m = re.search("^\[\d+\]\s(HOST|SERVICE) NOTIFICATION:", self.line)
        if m:
            if m.group(1) == 'HOST':
                return 'HOST'
            elif m.group(1) == 'SERVICE':
                self.is_service = True
                return 'SERVICE'
            else:
                return False
