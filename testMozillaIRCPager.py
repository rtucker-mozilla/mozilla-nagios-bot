#!/usr/bin/python
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
