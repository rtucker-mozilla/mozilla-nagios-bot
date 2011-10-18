#!/usr/bin/python
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

from mock import Mock
import unittest
from MozillaIRCPager import MozillaIRCPager
import re
from settings import *
class MozillaNagiosStatusTest(unittest.TestCase):
    tc = None

    def setUp(self):
        self.event = Mock()
        self.event.source = 'rtucker'
        self.event.target = '#sysadmins'
        self.connection = Mock()
        self.tc = MozillaIRCPager(self.connection)

    def test_get_page_plugin(self):
        plugins = self.tc.return_plugins()
        self.assertEqual('^page\\s+([A-Za-z][_A-Za-z0-9]+?)\\s+(.+)\\s*$',plugins[0]['regex']) 

    def test_correct_page(self):
        page_message = 'page %s this is a test message' % (self.event.source)
        plugins = self.tc.return_plugins()
        m = re.search(plugins[0]['regex'], page_message)
        target, message = self.tc.page(self.event, page_message, m)
        self.assertEqual(self.event.target, target)
        self.assertEqual(message, '%s: %s has been paged' % (self.event.source, self.event.source) )
