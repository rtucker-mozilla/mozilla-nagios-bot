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
from MozillaNagiosStatus import MozillaNagiosStatus
import re
from settings import *
from NagiosLogLine import NagiosLogLine

class MozillaNagiosStatusTest(unittest.TestCase):
    tc = None

    def setUp(self):
        self.event = Mock()
        self.event.source = 'rtucker'
        self.event.target = '#sysadmins'
        self.connection = Mock()
        self.tc = MozillaNagiosStatus(self.connection, [])
        self.my_nick = self.event.source
        self.service_line = '[1318882274] SERVICE NOTIFICATION: sysalertslist;fake-host.mozilla.org;root partition;CRITICAL;notify-by-email;DISK CRITICAL - free space: / 5294 MB (5% inode=99%):'
        self.ack_line = '[1318870432] SERVICE NOTIFICATION: socorroalertlist;fake-host.mozilla.org;Disk Space /;ACKNOWLEDGEMENT (WARNING);notify-by-email;DISK WARNING - free space: / 60658 MB (29% inode=97%):;ashish;bug 689547'
        self.host_line = "[1313158996] HOST NOTIFICATION: sysalertslist;fake-host.mozilla.org;DOWN;host-notify-by-email;PING CRITICAL - Packet loss = 100%"
        self.ack_host_line = "[1319720894] HOST NOTIFICATION: sysalertslist;fake-host.mozilla.org;ACKNOWLEDGEMENT (DOWN);host-notify-by-email;PING CRITICAL - Packet loss = 100%;rtucker;known"

    def test_get_environment_vars(self):
        self.assertEqual(self.tc.list_offset, 100)
        self.assertEqual(self.tc.list_size, 100)

    def test_ackable_list_bad_host(self):
        self.assertEqual(len(self.tc.ackable_list), 100)
        self.tc.ackable('Test Host-Not Found', 'Test Service', 'CRITICAL', 'Test Message')
        self.assertEqual(self.tc.get_ack_number(), 100)
        self.assertEqual(len(self.tc.ackable_list), 100)
        self.assertEqual(self.tc.ackable_list[0]['host'], 'Test Host-Not Found')
        self.assertEqual(self.tc.ackable_list[0]['service'], 'Test Service')
        self.assertEqual(self.tc.ackable_list[0]['state'], 'CRITICAL')
        self.assertEqual(self.tc.ackable_list[0]['message'], 'Test Message')

    def test_downtime_by_index_bad_host(self):
        self.tc.ackable('Test Host-Not Found', 'Test Service', 'CRITICAL', 'Test Message')
        self.assertEqual(self.tc.get_ack_number(), 100)
        message = 'downtime 100 1m blah blah'
        m = re.search('^downtime\s+(\d+)\s+(\d+[dhms])\s+(.*)\s*$', message)
        target, message = self.tc.downtime_by_index(self.event, message, m)
        self.assertEqual(target, '#sysadmins')
        self.assertEqual(message, '%s: Unable to find host' % self.my_nick)

    def test_downtime_by_host_only(self):
        self.tc.ackable('test-host.fake.mozilla.com', None, 'CRITICAL', 'Test Message')
        self.assertEqual(self.tc.get_ack_number(), 100)
        message = 'downtime test-host.fake.mozilla.com 1m blah blah'
        m = re.search('^downtime\s+([^: ]+)(?::(.*))?\s+(\d+[dhms])\s+(.*)\s*$', message)
        target, message = self.tc.downtime(self.event, message, m)
        self.assertEqual(target, '#sysadmins')
        self.assertEqual(message, '%s: Downtime for test-host.fake.mozilla.com scheduled for 0:01:00' % (self.my_nick) )

    def test_downtime_by_index_host_only(self):
        self.tc.ackable('test-host.fake.mozilla.com', None, 'CRITICAL', 'Test Message')
        self.assertEqual(self.tc.get_ack_number(), 100)
        message = 'downtime 100 1m blah blah'
        m = re.search('^downtime\s+(\d+)\s+(\d+[dhms])\s+(.*)\s*$', message)
        target, message = self.tc.downtime_by_index(self.event, message, m)
        self.assertEqual(target, '#sysadmins')
        self.assertEqual(message, '%s: Downtime for test-host.fake.mozilla.com scheduled for 0:01:00' % (self.my_nick) )

    def test_downtime_by_index_with_service(self):
        self.tc.ackable('test-host.fake.mozilla.com', 'Test Service', 'CRITICAL', 'Test Message')
        self.assertEqual(self.tc.get_ack_number(), 100)
        message = 'downtime 100 1m blah blah'
        m = re.search('^downtime\s+(\d+)\s+(\d+[dhms])\s+(.*)\s*$', message)
        target, message = self.tc.downtime_by_index(self.event, message, m)
        self.assertEqual(target, '#sysadmins')
        self.assertEqual(message, '%s: Downtime for test-host.fake.mozilla.com:Test Service scheduled for 0:01:00' % (self.my_nick) )

    def test_increment_ackable_list_correctly(self):
        self.tc.ackable('test-host.fake.mozilla.com', 'Test Service', 'CRITICAL', 'Test Message')
        self.assertEqual(self.tc.get_ack_number(), 100)
        self.assertEqual(len(self.tc.ackable_list), 100)
        self.assertEqual(self.tc.ackable_list[0]['service'], 'Test Service')
        self.tc.ackable('test-host.fake.mozilla.com', 'Test Service 2', 'CRITICAL', 'Test Message')
        self.assertEqual(self.tc.ackable_list[0]['service'], 'Test Service')
        self.assertEqual(self.tc.ackable_list[1]['service'], 'Test Service 2')

    def test_downtime_by_hostname_with_service(self):
        self.tc.ackable('test-host.fake.mozilla.com', 'Test Service', 'CRITICAL', 'Test Message')
        self.assertEqual(self.tc.get_ack_number(), 100)
        message = 'downtime 100 1m blah blah'
        m = re.search('^downtime\s+(\d+)\s+(\d+[dhms])\s+(.*)\s*$', message)
        target, message = self.tc.downtime_by_index(self.event, message, m)
        self.assertEqual(target, '#sysadmins')
        self.assertEqual(message, '%s: Downtime for test-host.fake.mozilla.com:Test Service scheduled for 0:01:00' % (self.my_nick) )

    def test_downtime_by_hostname(self):
        self.tc.ackable('test-host.fake.mozilla.com', None, 'CRITICAL', 'Test Message')
        self.assertEqual(self.tc.get_ack_number(), 100)
        message = 'downtime test-host.fake.mozilla.com 1m blah blah'
        m = re.search('^downtime\s+([^: ]+)(?::(.*))?\s+(\d+[dhms])\s+(.*)\s*$', message)
        target, message = self.tc.downtime(self.event, message, m)
        self.assertEqual(target, '#sysadmins')
        self.assertEqual(message, '%s: Downtime for test-host.fake.mozilla.com scheduled for 0:01:00' % (self.my_nick) )

    def test_mute(self):
        message = "mute"
        m = None
        target, message = self.tc.mute(self.event, message, m)
        self.assertEqual(target, "#sysadmins")
        self.assertEqual(message, "%s: OK I'll mute" % (self.my_nick) )

    def test_already_muted(self):
        message = "mute"
        m = None
        target, message = self.tc.mute(self.event, message, m)
        target, message = self.tc.mute(self.event, message, m)
        self.assertEqual(target, "#sysadmins")
        self.assertEqual(message, "%s: I'm already muted" % (self.my_nick) )

    def test_already_muted_unmute(self):
        message = "mute"
        m = None
        target, message = self.tc.mute(self.event, message, m)
        message = "unmute"
        target, message = self.tc.unmute(self.event, message, m)
        self.assertEqual(target, "#sysadmins")
        self.assertEqual(message, "%s: OK I'll unmute" % (self.my_nick) )

    def test_unmute_when_not_previously_muted(self):
        m = None
        message = "unmute"
        target, message = self.tc.unmute(self.event, message, m)
        self.assertEqual(target, "#sysadmins")
        self.assertEqual(message, "%s: OK I'm not muted" % (self.my_nick) )

    def test_oncall(self):
        m = None
        message = "whoisoncall"
        target, message = self.tc.get_oncall(self.event, message, m)
        self.assertEqual(target, "#sysadmins")
        self.assertEqual(message, "%s: unknown currently has the pager" % (self.my_nick) )

    def test_unack_host(self):
        message = "unack test-host.fake.mozilla.com"
        m = re.search('^unack ([^:]+)\s*$', message)
        target, message = self.tc.unack_by_host(self.event, message, m)
        self.assertEqual(target, "#sysadmins")
        self.assertEqual(message, "%s: ok, acknowledgment (if any) for test-host.fake.mozilla.com has been removed." % (self.my_nick) )

    def test_ack_host_with_service(self):
        message = "ack test-host.fake.mozilla.com:asdf test message"
        m = re.search('^\s*ack ([^:]+):([^:]+)\s(.*)$', message)
        target, message = self.tc.ack_by_host_with_service(self.event, message, m)
        self.assertEqual(target, "#sysadmins")
        self.assertEqual(message, "%s: The Service test-host.fake.mozilla.com:asdf test has been ack'd" % (self.my_nick) )

    def test_ack_host(self):
        message = "ack test-host.fake.mozilla.com test message"
        m = re.search('^\s*ack ([^:]+)\s(.*)$', message)
        target, message = self.tc.ack_by_host(self.event, message, m)
        self.assertEqual(target, "#sysadmins")
        self.assertEqual(message, "%s: The Host test-host.fake.mozilla.com test has been ack'd" % (self.my_nick) )

    def test_ack_host_by_index(self):
        self.tc.process_line(self.host_line, True)
        self.assertEqual(self.tc.get_ack_number(), 100)
        message = "ack 100 test message"
        m = re.search('^(?:\s*ack\s*)?(\d+)(?:\s*ack\s*)?[:\s]+([^:]+)\s*$', message)
        target, message = self.tc.ack(self.event, message, m)
        self.assertEqual(target, "#sysadmins")
        self.assertEqual(message, "%s: The Host fake-host.mozilla.org has been ack'd" % (self.my_nick) )
        self.tc.process_line(self.ack_host_line, True)
        self.assertEqual(target, "#sysadmins")
        self.assertEqual(message, "%s: The Host fake-host.mozilla.org has been ack'd" % (self.my_nick) )
        
    def test_ack_host_by_index_after_one_cycle(self):
        self.tc.ackable_list = [None]*self.tc.list_size
        self.assertEqual(len(self.tc.ackable_list), 100)
        for i in range(0,101):
            service_line = "[1318882274] SERVICE NOTIFICATION: sysalertslist;fake-host.mozilla.org;root partition%s;CRITICAL;notify-by-email;DISK CRITICAL - free space: / 5294 MB (5 inode=99):" % i
            self.tc.process_line(service_line, True)
        message = "ack 100 test message"
        m = re.search('^(?:\s*ack\s*)?(\d+)(?:\s*ack\s*)?[:\s]+([^:]+)\s*$', message)
        target, message = self.tc.ack(self.event, message, m)
        self.assertEqual(target, "#sysadmins")
        self.assertEqual(message, "%s: The Service fake-host.mozilla.org:root partition100 has been ack'd" % (self.my_nick) )
        self.tc.process_line(self.ack_host_line, True)

    def test_ack_host_by_index_after_one_cycle_long_service_message(self):
        self.tc.ackable_list = [None]*self.tc.list_size
        self.assertEqual(len(self.tc.ackable_list), 100)
        for i in range(0,12):
            service_line = "[1334695172] SERVICE NOTIFICATION: sysalertslist;db1.foo.bar.mozilla.com;MySQL Replication;UNKNOWN;notify-by-sms;**ePN /usr/lib64/nagios/plugins/mozilla/check_mysql_replication: DBI connect(host=10.0.0.0:database=,username,...) failed: Cant connect to MySQL server on 10.0.0.0 (111) at (eval 6) line 30."
            self.tc.process_line(service_line, True)
        message = "ack 110 test message"
        m = re.search('^(?:\s*ack\s*)?(\d+)(?:\s*ack\s*)?[:\s]+([^:]+)\s*$', message)
        target, message = self.tc.ack(self.event, message, m)
        self.assertEqual(target, "#sysadmins")
        self.assertEqual(message, "%s: The Service db1.foo.bar.mozilla.com:MySQL Replication has been ack'd" % (self.my_nick) )
        self.tc.process_line(self.ack_host_line, True)
        message = "status db1.foo.mozilla.com:MySQL replication"
        m = re.search('^status ([^:]+):(.+)$', message)
        target, message = self.tc.status_by_host_name(self.event, message, m)
        self.assertEqual(target, "#sysadmins")
        self.assertEqual(message[0], "%s: db1.foo.mozilla.com:mysql Replication is \x033OK\x03\x03\x03 - uptime: 18346  threads: 199  questions: 12026601  slow queries: 1  opens: 496  flush tables: 1  open tables: 489  queries per second avg: 655.543" % (self.my_nick) )

    def test_disallowed_ack_list(self):
        self.assertEqual(self.tc.disallowed_ack[0], 'serverops_bugs')

    def test_ack_service_by_index_disallowed(self):
        self.tc.ackable_list = [None]*self.tc.list_size
        self.assertEqual(len(self.tc.ackable_list), 100)
        for i in range(0,12):
            service_line = "[1334695172] SERVICE NOTIFICATION: sysalertslist;db1.foo.bar.mozilla.com;serverops_bugs;CRITICAL;notify-by-sms;some critical bug that I don't want to ack"
            self.tc.process_line(service_line, True)
        message = "ack 110 test message"
        m = re.search('^(?:\s*ack\s*)?(\d+)(?:\s*ack\s*)?[:\s]+([^:]+)\s*$', message)
        target, message = self.tc.ack(self.event, message, m)
        self.assertEqual(target, "#sysadmins")
        self.assertEqual(message, "%s: I'm sorry but you're not allowed to ACK this alert here. Please visit the appropriate nagios webui to ACK it there." % (self.my_nick) )
        self.tc.process_line(self.ack_host_line, True)
        
    def test_ack_host_by_index_after_half_cycle(self):
        self.tc.ackable_list = [None]*self.tc.list_size
        self.assertEqual(len(self.tc.ackable_list), 100)
        for i in range(0,51):
            service_line = "[1318882274] SERVICE NOTIFICATION: sysalertslist;fake-host.mozilla.org;root partition%s;CRITICAL;notify-by-email;DISK CRITICAL - free space: / 5294 MB (5 inode=99):" % i
            self.tc.process_line(service_line, True)
        message = "ack 150 test message"
        m = re.search('^(?:\s*ack\s*)?(\d+)(?:\s*ack\s*)?[:\s]+([^:]+)\s*$', message)
        target, message = self.tc.ack(self.event, message, m)
        self.assertEqual(target, "#sysadmins")
        self.assertEqual(message, "%s: The Service fake-host.mozilla.org:root partition50 has been ack'd" % (self.my_nick) )
        self.assertEqual(self.tc.ackable_list[51], None)

    def test_ack_host_by_index_after_five_cycles(self):
        self.tc.ackable_list = [None]*self.tc.list_size
        self.assertEqual(len(self.tc.ackable_list), 100)
        for i in range(0,501):
            service_line = "[1318882274] SERVICE NOTIFICATION: sysalertslist;fake-host.mozilla.org;root partition%s;CRITICAL;notify-by-email;DISK CRITICAL - free space: / 5294 MB (5 inode=99):" % i
            self.tc.process_line(service_line, True)
        message = "ack 100 test message"
        m = re.search('^(?:\s*ack\s*)?(\d+)(?:\s*ack\s*)?[:\s]+([^:]+)\s*$', message)
        target, message = self.tc.ack(self.event, message, m)
        self.assertEqual(target, "#sysadmins")
        self.assertEqual(message, "%s: The Service fake-host.mozilla.org:root partition500 has been ack'd" % (self.my_nick) )
        self.tc.process_line(self.ack_host_line, True)

    def test_ack_host_by_index_after_five_cycles_with_ack(self):
        self.tc.ackable_list = [None]*self.tc.list_size
        self.assertEqual(len(self.tc.ackable_list), 100)
        for i in range(0,501):
            service_line = "[1318882274] SERVICE NOTIFICATION: sysalertslist;fake-host.mozilla.org;root partition%s;CRITICAL;notify-by-email;DISK CRITICAL - free space: / 5294 MB (5 inode=99):" % i
            self.tc.process_line(service_line, True)
            message = "ack %i test message" % (i % self.tc.list_size)
            m = re.search('^(?:\s*ack\s*)?(\d+)(?:\s*ack\s*)?[:\s]+([^:]+)\s*$', message)
            target, message = self.tc.ack(self.event, message, m)
            self.assertEqual(target, "#sysadmins")
            self.assertEqual(message, "%s: The Service fake-host.mozilla.org:root partition%i has been ack'd" % (self.my_nick, i) )
            self.tc.process_line(self.ack_host_line, True)

    def test_ack_host_by_index_after_five_cycles_with_ack_incorrect_syntax(self):
        self.tc.ackable_list = [None]*self.tc.list_size
        self.assertEqual(len(self.tc.ackable_list), 100)
        for i in range(0,501):
            service_line = "[1318882274] SERVICE NOTIFICATION: sysalertslist;fake-host.mozilla.org;root partition%s;CRITICAL;notify-by-email;DISK CRITICAL - free space: / 5294 MB (5 inode=99):" % i
            self.tc.process_line(service_line, True)
            message = "%i ack test message" % (i % self.tc.list_size)
            m = re.search('^(?:\s*ack\s*)?(\d+)(?:\s*ack\s*)?[:\s]+([^:]+)\s*$', message)
            target, message = self.tc.ack(self.event, message, m)
            self.assertEqual(target, "#sysadmins")
            self.assertEqual(message, "%s: The Service fake-host.mozilla.org:root partition%i has been ack'd" % (self.my_nick, i) )
            self.tc.process_line(self.ack_host_line, True)
    def test_ack_host_by_index_after_hundred_cycles(self):
        self.tc.ackable_list = [None]*self.tc.list_size
        self.assertEqual(len(self.tc.ackable_list), 100)
        for i in range(0,100001):
            service_line = "[1318882274] SERVICE NOTIFICATION: sysalertslist;fake-host.mozilla.org;root partition%s;CRITICAL;notify-by-email;DISK CRITICAL - free space: / 5294 MB (5 inode=99):" % i
            self.tc.process_line(service_line, True)
        message = "ack 100 test message"
        m = re.search('^(?:\s*ack\s*)?(\d+)(?:\s*ack\s*)?[:\s]+([^:]+)\s*$', message)
        target, message = self.tc.ack(self.event, message, m)
        self.assertEqual(target, "#sysadmins")
        self.assertEqual(message, "%s: The Service fake-host.mozilla.org:root partition100000 has been ack'd" % (self.my_nick) )
        self.tc.process_line(self.ack_host_line, True)

    def test_unack_by_index(self):
        cmd = "unack 100"
        m = re.search('^unack (\d+)$', cmd)
        target, message = self.tc.unack(self.event, cmd, m)
        self.assertEqual(target, "#sysadmins")
        self.assertEqual(message, "%s: Sorry, but no alert exists at this index" % (self.my_nick) )

        #Now add an alert to the list and try to unack
        tmp = self.tc.ackable('test-host.fake.mozilla.com', None, 'CRITICAL', 'Test Message')
        self.assertEqual(self.tc.get_ack_number(), 100)
        target, message = self.tc.unack(self.event, cmd, m)
        self.assertEqual(target, "#sysadmins")
        self.assertEqual(message, "%s: The Host test-host.fake.mozilla.com has been ack'd" % (self.my_nick) )
    def test_process_line(self):
        self.tc.process_line(self.service_line, True)
        self.assertEqual(self.tc.get_ack_number(), 100)
        self.tc.process_line(self.host_line, True)
        self.tc.process_line(self.service_line, True)
        self.assertEqual(self.tc.get_ack_number(), 102)

    def test_process_line_with_unknown_contacts(self):
        self.tc.process_line(self.service_line, True)
        self.assertEqual(self.tc.get_ack_number(), 100)
        self.tc.process_line(self.host_line, True)
        self.tc.process_line(self.service_line, True)
        self.assertEqual(self.tc.get_ack_number(), 102)
        service_line = "[1318882274] SERVICE NOTIFICATION: unknowncontacthere;fake-host.mozilla.org;root partition;CRITICAL;notify-by-email;DISK CRITICAL - free space: / 5294 MB (5 inode=99):"
        self.tc.process_line(service_line, True)
        self.assertEqual(self.tc.get_ack_number(), 102)
        self.tc.process_line(self.service_line, True)
        self.assertEqual(self.tc.get_ack_number(), 103)

    def test_get_channel_group(self):
        self.assertEqual(self.tc.get_channel_group('sysalertslist'), '#sysadmins')

    """
        This test is no longer valid, we did away with a default contact channel
    """
    """def test_get_channel_group_not_found(self):
        self.assertEqual(self.tc.get_channel_group('thisshouldnevermatchblahblah'), '#default')
    """

    def test_get_page_plugin(self):
        plugins = self.tc.return_plugins()
        self.assertEqual('^(?:\s*ack\s*)?(\d+)(?:\s*ack\s*)?[:\s]+([^:]+)\s*$', plugins[0]['regex']) 
        
        
class NagiosStatusTest(unittest.TestCase):
    def setUp(self):
        self.event = Mock()
        self.event.source = 'rtucker'
        self.event.target = '#sysadmins'
        self.connection = Mock()
        self.tc = MozillaNagiosStatus(self.connection, [])
        self.my_nick = self.event.source

    def test_empty_host_status(self):
        cmd = "status db2.foo.mozilla.com"
        m = re.search('^status ([^:]+)', cmd)
        target, message = self.tc.status_by_host_name(self.event, cmd, m)
        self.assertEqual(target, "#sysadmins")
        self.assertEqual(message, '%s: db2.foo.mozilla.com is \x033OK\x03\x03\x03 - PING OK - Packet loss = 0%%, RTA = 0.91 ms' % self.event.source)

    def test_empty_host_wildcard(self):
        cmd = "status db*:PING"
        m = re.search('^status ([^:]+)', cmd)
        target, message = self.tc.status_by_host_name(self.event, cmd, m)
        self.assertEqual(len(message), 2)
        self.assertEqual(target, "#sysadmins")
        self.assertEqual(message[0], '%s: db1.foo.mozilla.com:PING is \x033OK\x03\x03\x03 - PING OK - Packet loss = 0%%, RTA = 0.80 ms' % self.event.source)
        self.assertEqual(message[1], '%s: db2.foo.mozilla.com:PING is \x033OK\x03\x03\x03 - PING OK - Packet loss = 0%%, RTA = 0.88 ms' % self.event.source)
        
    def test_basic_host_status_wildcard_services(self):
        cmd = "status db2.foo.mozilla.com:*"
        m = re.search('^status ([^:]+):(.+)$', cmd)
        target, message = self.tc.status_by_host_name(self.event, cmd, m)
        self.assertEqual(target, "#sysadmins")
        self.assertEqual(len(message), 11)

    def test_basic_host_status_specific_service(self):
        cmd = "status db2.foo.mozilla.com:swap"
        m = re.search('^status ([^:]+):(.+)$', cmd)
        target, message = self.tc.status_by_host_name(self.event, cmd, m)
        self.assertEqual(target, "#sysadmins")
        self.assertEqual(len(message), 1)
        self.assertEqual(message[0], "%s: db2.foo.mozilla.com:Swap is \x033OK\x03\x03\x03 - SWAP OK - 100%% free (2043 MB out of 2047 MB)" % self.event.source)

    def test_basic_host_status_wildcard_service_from_start(self):
        cmd = "status db2.foo.mozilla.com:Sw*"
        m = re.search('^status ([^:]+):(.+)$', cmd)
        target, message = self.tc.status_by_host_name(self.event, cmd, m)
        self.assertEqual(target, "#sysadmins")
        self.assertEqual(message[0], "%s: db2.foo.mozilla.com:Swap is \x033OK\x03\x03\x03 - SWAP OK - 100%% free (2043 MB out of 2047 MB)" % self.event.source)
        self.assertEqual(len(message), 1)
class NagiosLogLineTest(unittest.TestCase):

    def setUp(self):
        self.service_line = '[1318882274] SERVICE NOTIFICATION: sysalertslist;fake-host.mozilla.org;root partition;CRITICAL;notify-by-email;DISK CRITICAL - free space: / 5294 MB (5% inode=99%):'
        self.host_line = "[1313158996] HOST NOTIFICATION: sysalertslist;fake-host.mozilla.org;DOWN;host-notify-by-email;PING CRITICAL - Packet loss = 100%"
        pass

    def test_constructor(self):
        l = NagiosLogLine('asdf')
        self.assertEqual(l.line, 'asdf')
        l = NagiosLogLine("asdf\r\n")
        self.assertEqual(l.line, 'asdf')

    def test_is_service_notification(self):
        l = NagiosLogLine(self.service_line)
        self.assertEqual(l.notification_type,'SERVICE')

    def test_is_notification_recipient(self):
        l = NagiosLogLine(self.service_line)
        self.assertEqual(l.notification_recipient,'sysalertslist')

    def test_is_host_notification(self):
        l = NagiosLogLine(self.host_line)
        self.assertEqual(l.notification_type,'HOST')

    def test_get_service(self):
        l = NagiosLogLine(self.service_line)
        self.assertEqual(l.notification_type,'SERVICE')
        self.assertEqual(l.service,'root partition')

    def test_get_service_state(self):
        l = NagiosLogLine(self.service_line)
        self.assertEqual(l.state,'CRITICAL')

    def test_get_host_state(self):
        l = NagiosLogLine(self.host_line)
        self.assertEqual(l.state,'DOWN')

    def test_get_service_message(self):
        l = NagiosLogLine(self.service_line)
        self.assertEqual(l.message,'DISK CRITICAL - free space: / 5294 MB (5% inode=99%):')

    def test_get_service_message_acknowledged(self):
        l = NagiosLogLine('[1318870432] SERVICE NOTIFICATION: sysalertslist;fake-host.mozilla.org;Disk Space /;ACKNOWLEDGEMENT (WARNING);notify-by-email;DISK WARNING - free space: / 60658 MB (29% inode=97%):;ashish;bug 689547')
        self.assertEqual(l.is_service,True)
        self.assertEqual(l.state,'ACKNOWLEDGEMENT (WARNING)')

    def test_get_host_message(self):
        l = NagiosLogLine(self.host_line)
        self.assertEqual(l.message,'PING CRITICAL - Packet loss = 100%')

    def test_get_host_name(self):
        l = NagiosLogLine(self.host_line)
        self.assertEqual(l.host,'fake-host.mozilla.org')

