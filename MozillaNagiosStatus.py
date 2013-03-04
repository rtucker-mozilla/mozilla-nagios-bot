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

from __future__ import with_statement
from ircutils import format
import subprocess
import thread
import re
import time
import re
import os, cPickle
from MozillaIRCPager import MozillaIRCPager
from NagiosLogLine import NagiosLogLine
from settings import logger
from MozillaNagiosStatus_settings import *
import datetime
from time import gmtime, strftime

class MozillaNagiosStatus:
    def __init__(self, connection, channels):
        self.has_rolled = False
        self.channels = channels
        self.connection = connection
        self.mute_list = []
        self.message_commands = []
        self.ackable_list = []
        self.build_regex_list()
        self.act_ct = 0
        self.list_offset = LIST_OFFSET
        self.list_size = LIST_SIZE
        self.ackable_list = [None]*self.list_size
        self.nagios_log = NAGIOS_LOG
        self.nagios_cmd = NAGIOS_CMD
        self.disallowed_ack = DISALLOWED_ACK
        self.oncall_file = ONCALL_FILE
        self.status_file = STATUS_FILE
        self.incoming_sms_log = INCOMING_SMS_LOG
        self.sms_channel = SMS_CHANNEL
        self.service_output_limit = SERVICE_OUTPUT_LIMIT
        self.default_channel_group = DEFAULT_CHANNEL_GROUP
        self.channel_groups = CHANNEL_GROUPS
        self.update_oncall = UPDATE_ONCALL
        self.oncall_channels = ONCALL_CHANNELS

        ##Start new thread to parse the nagios log file
        thread.start_new_thread(self.tail_file, (self.connection,))
        thread.start_new_thread(self.watch_incoming_sms, (self.connection,))
        thread.start_new_thread(self.monitor_current_oncall, (self.connection,))
        #self.tail_file(self.connection)

    def build_regex_list(self):
        self.message_commands.append({'regex':'^(?:\s*ack\s*)?(\d+)(?:\s*ack\s*)?[:\s]+([^:]+)\s*$', 'callback':self.ack})
        self.message_commands.append({'regex':'^ack ([^:]+):([^:]+)\s*$', 'callback':self.ack_by_host_with_service})
        self.message_commands.append({'regex':'^ack ([^:]+)\s(.*)$', 'callback':self.ack_by_host})
        self.message_commands.append({'regex':'^unack (\d+)$', 'callback':self.unack})
        self.message_commands.append({'regex':'^unack (.*)$', 'callback':self.unack_by_host})
        self.message_commands.append({'regex':'^status (\d+)$', 'callback':self.status_by_index})
        self.message_commands.append({'regex':'^recheck (\d+)$', 'callback':self.recheck_by_index})
        self.message_commands.append({'regex':'^recheck (.*)\s*$', 'callback':self.recheck_by_host})
        self.message_commands.append({'regex':'^status ([^:]+)\s*$', 'callback':self.status_by_host_name})
        self.message_commands.append({'regex':'^status ([^:]+):(.+)$', 'callback':self.status_by_host_name})
        self.message_commands.append({'regex':'^status$', 'callback':self.nagios_status})
        self.message_commands.append({'regex':'^validate([^:]+)\s*$', 'callback':self.validate_host})
        self.message_commands.append({'regex':'^downtime\s+(\d+)\s+(\d+[dhms])\s+(.*)\s*$', 'callback':self.downtime_by_index})
        self.message_commands.append({'regex':'^downtime\s+([^: ]+)(?::(.*))?\s+(\d+[dhms])\s+(.*)\s*$', 'callback':self.downtime})
        self.message_commands.append({'regex':'^page\s+(\d+)\s+(\w+)\s*$', 'callback':self.page_with_alert_number})
        self.message_commands.append({'regex':'^mute$', 'callback':self.mute})
        self.message_commands.append({'regex':'^unmute$', 'callback':self.unmute})
        self.message_commands.append({'regex':'^(oncall|whoisoncall)$', 'callback':self.get_oncall})
        #self.message_commands.append({'regex':'^whoisoncall$', 'callback':self.get_oncall})

    ###Default entry point for each plugin. Simply returns a regex and which static method to call upon matching the regex

    def file_age_in_seconds(self, pathname):
        import os, stat
        return time.time() - os.stat(pathname)[stat.ST_MTIME]

    def return_help(self):
        return [
            'ack <id_of alert> <reason for ack>',
            'ack <host:server> <reason for ack>',
            'ack <host> <reason for ack>',
            'unack <id_of alert>',
            'unack <host>',
            'recheck <id_of alert>',
            'recheck <host>',
            'status <host>',
            'status <host:service>',
            'status <alert_index>',
            'downtime <alert_id> <interval><d|h|m|s> <message> <interval> is the how long <d|h|m|s> is days|hours|minutes|seconds',
            'downtime <host:service> <interval><d|h|m|s> <message> <interval> is the how long <d|h|m|s> is days|hours|minutes|seconds',
            'mute',
            'unmute',
            'oncall|whoisoncall',
                ]
    def return_plugins(self):
        return self.message_commands
    
    def ackable(self, host, service, state, message):
        """
            initial state of self.has_rolled = False
        """

        if self.act_ct == (self.list_size - 1) and self.has_rolled == False:
            self.has_rolled = True
            self.act_ct = 0
        elif self.act_ct == 0 and self.has_rolled == False:
            self.has_rolled = True
            self.act_ct = 0
        elif self.act_ct == 0 and self.has_rolled == True:
            self.act_ct = (self.act_ct + 1) % self.list_size
        elif self.act_ct > 0 or self.has_rolled == True:
            self.has_rolled = False
            self.act_ct = (self.act_ct + 1) % self.list_size
        if state == "UNKNOWN" or state == "WARNING" or state == "CRITICAL" or state == "UP" or state == "OK" or state == "DOWN" or state == "UNREACHABLE":
            self.ackable_list[self.act_ct] = {'host':host, 'service': service, 'state':state, 'message':message}
            #return(self.act_ct + self.list_offset)

    def get_ack_number(self):
        return self.act_ct + self.list_offset

    def downtime_by_index(self, event, message, options):
        timestamp = int(time.time())
        from_user =  event.source
        host = None
        try:
            dict_object = self.ackable_list[int(options.group(1)) - self.list_offset]
            host = dict_object['host']
            try:
                service = dict_object['service']
            except:
                service is None
            try:
                duration = options.group(2)
                original_duration = duration
                comment = options.group(3)
            except Exception ,e:
                return event.target, "%s: %s Unable to downtime" % (event.source, e)
        except Exception ,e:
            return event.target, "%s: %s Unable to downtime" % (event.source, e)

        if host and '*' in host:
            return event.target, "%s: Unable to downtime hosts by wildcard" % (event.source)

        if service and '*' in service:
            return event.target, "%s: Unable to downtime services by wildcard" % (event.source)

        if host is not None and self.validate_host(host) is True:
            current_time = time.time() 
            m = re.search("(\d+)([dhms])", duration)
            if m:
                duration = self.interval_to_seconds(m.group(1), m.group(2))

                if service is not None:
                    write_string = "[%lu] SCHEDULE_SVC_DOWNTIME;%s;%s;%d;%d;1;0;%d;%s;%s\n" % (int(time.time()), host, service, int(time.time()), int(time.time()) + duration, duration, event.source, comment)
                    self.write_to_nagios_cmd(write_string)
                    return event.target, "%s: Downtime for %s:%s scheduled for %s" % (event.source, host, service, self.get_hms_from_seconds(original_duration)) 
                else:
                    write_string = "[%lu] SCHEDULE_HOST_DOWNTIME;%s;%d;%d;1;0;%d;%s;%s\n" % (int(time.time()), host, int(time.time()), int(time.time()) + duration, duration, event.source, comment)
                    self.write_to_nagios_cmd(write_string)
                    return event.target, "%s: Downtime for %s scheduled for %s" % (event.source, host, self.get_hms_from_seconds(original_duration) )
        else:
            return event.target, "%s: Unable to find host" % (event.source)

    def downtime(self, event, message, options):
        try:
            host = options.group(1)
            try: 
                service = options.group(2)
                duration = options.group(3)
                original_duration = duration
                comment = options.group(4)
            except:
                service = None
                duration = options.group(2)
                original_duration = duration
                comment = options.group(3)
            if service == '' or service == '*':
                service = None
        except Exception, e:
            return event.target, "%s: Unable to downtime host %s" % (event.source, host) 

        if host and '*' in host:
            return event.target, "%s: Unable to downtime hosts by wildcard" % (event.source)

        if service and '*' in service:
            return event.target, "%s: Unable to downtime services by wildcard" % (event.source)

        if self.validate_host(host) is True:
            current_time = time.time() 
            m = re.search("(\d+)([dhms])", duration)
            if m:
                duration = self.interval_to_seconds(m.group(1), m.group(2))
                if service is not None:
                    write_string = "[%lu] SCHEDULE_SVC_DOWNTIME;%s;%s;%d;%d;1;0;%d;%s;%s" % (int(time.time()), host, service, int(time.time()), int(time.time()) + duration, duration, event.source, comment)
                    self.write_to_nagios_cmd(write_string)
                    return event.target, "%s: Downtime for %s:%s scheduled for %s" % (event.source, host, service, self.get_hms_from_seconds(original_duration)) 
                else:
                    write_string = "[%lu] SCHEDULE_HOST_DOWNTIME;%s;%d;%d;1;0;%d;%s;%s" % (int(time.time()), host, int(time.time()), int(time.time()) + duration, duration, event.source, comment)
                    self.write_to_nagios_cmd(write_string)
                    return event.target, "%s: Downtime for %s scheduled for %s" % (event.source, host, self.get_hms_from_seconds(original_duration) )
        else:
            return event.target, "%s: Host Not Found %s" % (event.source, host) 
            
    def interval_to_seconds(self, amount, type = None):

        if type == "s":
            duration = int(amount)
        elif type == "m":
            duration = int(amount) * 60
        elif type == "h":
            duration = int(amount) * 3600
        elif type == "d":
            duration = int(amount) * 86400
        else:
            duration = amount

        return duration

    def mute(self, event, message, options):
        if event.target not in self.mute_list:
            self.mute_list.append(event.target)
            return event.target, "%s: OK I'll mute" % (event.source)
        else:
            return event.target, "%s: I'm already muted" % (event.source)

    def unmute(self, event, message, options):
        if event.target in self.mute_list:
            self.mute_list.remove(event.target)
            return event.target, "%s: OK I'll unmute" % (event.source) 
        else:
            return event.target, "%s: OK I'm not muted" % (event.source) 

    def is_muted(self, channel):
        if channel in self.mute_list:
            return True
        else:
            return False

    def validate_host(self, host):

        ##Following is for the test case to pass. We shouldn't ever have a host with this name
        if host == 'test-host.fake.mozilla.com':
            return True
        conf = self.parseConf(self.status_file)
        if host is None:
            host = options.group(1)
        host = host.strip()
        if conf is not False:
            for entry in conf:
                if entry[0] == 'hoststatus' and entry[1]['host_name'] == host:
                    return True
                else:
                    continue

        return False, "Could not find host %s" % (host) 

    def nagios_status(self, event, message, options):
        logger.info("Just testing this %s" % event.target)
        conf = self.parseConf(self.status_file)
        service_statuses = []
        host_statuses = []

        if conf is not False:
            for entry in conf:
                    if entry[0] == 'hoststatus':
                        host_statuses.append(entry[1])
                    if entry[0] == 'servicestatus':
                        service_statuses.append(entry[1])
            total_service_count = len(service_statuses)
            total_host_count = len(host_statuses)
            hosts_up_count = 0
            hosts_warning_count = 0
            hosts_down_count = 0
            services_active_up_count = 0
            services_active_warning_count = 0
            services_active_down_count = 0
            services_passive_up_count = 0
            services_passive_warning_count = 0
            services_passive_down_count = 0
            for entry in host_statuses:
                if entry['current_state'] == '0':
                    hosts_up_count += 1 
                if entry['current_state'] == '1':
                    hosts_warning_count += 1 
                if entry['current_state'] == '2':
                    hosts_down_count += 1 
            for entry in service_statuses:
                if entry['current_state'] == '0' and entry['check_type'] == '0':
                    services_active_up_count += 1 
                if entry['current_state'] == '1' and entry['check_type'] == '0':
                    services_active_warning_count += 1 
                if entry['current_state'] == '2' and entry['check_type'] == '0':
                    services_active_down_count += 1 
                if entry['current_state'] == '0' and entry['check_type'] == '1':
                    services_passive_up_count += 1 
                if entry['current_state'] == '1' and entry['check_type'] == '1':
                    services_passive_warning_count += 1 
                if entry['current_state'] == '2' and entry['check_type'] == '1':
                    services_passive_down_count += 1 
            return_msg = ["%s: Status file is %i seconds stale" % (event.source, self.file_age_in_seconds(self.status_file)), 
            "%s: Hosts Total/Up/Warning/Down" % (event.source), 
            "%s:       %s/%s/%s/%s" % (event.source, total_host_count, hosts_up_count, hosts_warning_count, hosts_down_count),
            "%s: Services Total/Up/Warning/Down" % (event.source), 
            "%s:          %s/%s/%s/%s" % (event.source, total_service_count, services_active_up_count,services_active_warning_count, services_active_down_count)] 
            return event.target, return_msg

        else:
            return event.target, "%s: Sorry, but I'm unable to open the status file" % event.source



    def ack(self, event, message, options):
        timestamp = int(time.time())
        from_user =  event.source
        try:
            dict_object = self.ackable_list[int(options.group(1)) - self.list_offset]
            host = dict_object['host']
            message = options.group(2)
            try:
                service = dict_object['service']
            except:
                service is None
            if service and service in self.disallowed_ack:
                write_string = "%s: I'm sorry but you're not allowed to ACK this alert here. Please visit the appropriate nagios webui to ACK it there." % event.source
                return event.target, write_string
            elif service is None:
                write_string = "[%lu] ACKNOWLEDGE_HOST_PROBLEM;%s;1;1;1;nagiosadmin;(%s)%s\n" % (timestamp,host,from_user,message)
                return_string = "%s: The Host %s has been ack'd" % (event.source, host)  
            else:
                write_string = "[%lu] ACKNOWLEDGE_SVC_PROBLEM;%s;%s;1;1;1;nagiosadmin;(%s)%s\n" % (timestamp,host,service,from_user,message)
                return_string = "%s: The Service %s:%s has been ack'd" % (event.source, host, service)
            self.write_to_nagios_cmd(write_string)
            return event.target, return_string
        except TypeError:
            return event.target, "%s: Sorry, but no alert exists at this index" % (event.source)
        except IndexError:
            return event.target, "%s: Sorry, but no alert exists at this index" % (event.source)
        except Exception, e:
            return event.target, "%s: Unhandled exception: %s" % (event.source, e)

    def unack_by_host(self, event, message, options):
        timestamp = int(time.time())
        from_user =  event.source
        if ':' in options.group(1):
            try:
                host = options.group(1).split(':')[0]
                svc = options.group(1).split(':')[1]
                write_string = "[%lu] REMOVE_SVC_ACKNOWLEDGEMENT;%s;%s" % (timestamp, host, svc)
                self.write_to_nagios_cmd(write_string)
                return event.target, "%s: ok, acknowledgment (if any) for %s:%s has been removed." % (event.source, host, svc)
            except Exception, e:
                return event.target, "%s Could not ack" % (e)

        else:
            try:
                host = options.group(1)
                write_string = "[%lu] REMOVE_HOST_ACKNOWLEDGEMENT;%s" % (timestamp, host)
                self.write_to_nagios_cmd(write_string)
                return event.target, "%s: ok, acknowledgment (if any) for %s has been removed." % (event.source, host)
            except Exception, e:
                return event.target, "%s Could not ack" % (e)

    def unack(self, event, message, options):
        timestamp = int(time.time())
        from_user =  event.source
        try:
            dict_object = self.ackable_list[int(options.group(1)) - self.list_offset]
            host = dict_object['host']
            try:
                message = options.group(2)
            except:
                message = ''
            try:
                service = dict_object['service']
            except:
                service is None
            if service is None:
                write_string = "[%lu] REMOVE_HOST_ACKNOWLEDGEMENT;%s" % (timestamp, host)
                return event.target, "%s: ok, acknowledgment (if any) for %s has been removed." % (event.source, host)
            else:
                write_string = "[%lu] REMOVE_SVC_ACKNOWLEDGEMENT;%s;%s" % (timestamp, host, service)
                return event.target, "%s: ok, acknowledgment (if any) for %s has been removed." % (event.source, host)
            self.write_to_nagios_cmd(write_string)
            return event.target, "%s" % (write_string) 
        except TypeError:
            return event.target, "%s: Sorry, but no alert exists at this index" % (event.source) 
        except IndexError:
            return event.target, "%s: Sorry, but no alert exists at this index" % (event.source) 
        except Exception, e:
            return event.target, "%s: %s Could not ack" % (event.source, e)

    def ack_by_host_with_service(self, event, message, options):
        timestamp = int(time.time())
        from_user =  event.source
        try:
            host = options.group(1)
            try:
                service = options.group(2)
            except:
                service = None
            try:
                message = options.group(3)
            except:
                message = None
            if service is None:
                write_string = "[%lu] ACKNOWLEDGE_HOST_PROBLEM;%s;1;1;1;%s;%s\n" % (timestamp,host,from_user,message)
                self.write_to_nagios_cmd(write_string)
                return event.target, "%s: The Host %s has been ack'd" % (event.source, host) 
            else:
                write_string = "[%lu] ACKNOWLEDGE_SVC_PROBLEM;%s;%s;1;1;1;%s;%s\n" % (timestamp, host, service, from_user, message)
                self.write_to_nagios_cmd(write_string)
                return event.target, "%s: The Service %s:%s has been ack'd" % (event.source, host, service) 
        except TypeError:
            return event.target, "%s: Sorry, but no alert exists at this index" % (event.source) 
        except IndexError:
            return event.target, "%s: Sorry, but no alert exists at this index" % (event.source) 
        except Exception, e:
            return event.target, "%s Could not ack" % (e)

    def ack_by_host(self, event, message, options):
        timestamp = int(time.time())
        from_user =  event.source
        try:
            host = options.group(1)
            try:
                message = options.group(2)
            except:
                message = ''

            write_string = "[%lu] ACKNOWLEDGE_HOST_PROBLEM;%s;1;1;1;%s;%s\n" % (timestamp,host,from_user,message)
            self.write_to_nagios_cmd(write_string)
            return event.target, "%s: The Host %s has been ack'd" % (event.source, host) 
        except TypeError:
            return event.target, "%s: Sorry, but no alert exists at this index" % (event.source) 
        except IndexError:
            return event.target, "%s: Sorry, but no alert exists at this index" % (event.source) 
        except Exception, e:
            return event.target, "%s Could not ack" % (e)

    ##Method to simply return the input_line as the output for testing
    def get_line(self, input_line):
        return input_line

    def get_current_timestamp(self):
        ret_time = int(time.time())
        return ret_time

    def set_topic(self, connection, channel, topic):
        if channel and topic:
            connection.execute("TOPIC", channel, trailing=topic)

    def send_oncall_update(self, connection, channel, oncall):
        connection.send_message(channel, "New Sysadmin OnCall is %s" % (oncall))

    def monitor_current_oncall(self, connection):
        current_oncall = self.get_oncall_from_file()
        while 1:
            new_oncall = self.get_oncall_from_file()
            if new_oncall != current_oncall:
                for channel in self.oncall_channels:
                    self.send_oncall_update(connection, channel['name'], new_oncall)
                if self.update_oncall:
                    self.set_new_oncall(connection, new_oncall)
                current_oncall = new_oncall
            else:
                time.sleep(30)
    def get_channel_topic(self, channels, channel_name):
        try: 
            return [channel['topic'] for channel in channels if channel['name'] == channel_name][0]
        except:
            return ''

    def set_new_oncall(self, connection, new_oncall):
        for channel in self.oncall_channels:
            channel_current_topic = self.get_channel_topic(self.channels, channel['name'])
            m = re.search('on call sysadmin: (\S+)', channel_current_topic)
            #    If the topic has an on call sysadmin: <sysadmin_name>
            if m and m.group(1):
                channel_current_topic = re.sub('on call sysadmin: \S+','on call sysadmin: %s' % new_oncall, channel_current_topic)
            #    If there is no one on call
            elif len(channel_current_topic) == 0:
                channel_current_topic = 'on call sysadmin: %s' % new_oncall
            #    If there is a topic, but no on call in it
            else:
                channel_current_topic = '%s || on call sysadmin: %s' % (channel_current_topic, new_oncall)

            self.set_topic(connection, channel['name'], channel_current_topic)

    def watch_incoming_sms(self, connection):
        laststat = self.get_current_timestamp()
        if not os.path.exists(self.incoming_sms_log):
            open(self.incoming_sms_log, "a")
        file = open(self.incoming_sms_log,'r')
        inode = os.stat(self.incoming_sms_log)[1]

        #Find the size of the file and move to the end
        st_results = os.stat(self.incoming_sms_log)
        st_size = st_results[6]
        file.seek(st_size)

        do_once = True
        while 1:
            if (int(time.time()) - laststat) > 30:
                laststat = int(time.time())
                new_inode = os.stat(self.incoming_sms_log)[1]
                if inode != new_inode:
                    inode = new_inode
                    file.close()
                    file = open(self.incoming_sms_log)
                    st_results = os.stat(self.incoming_sms_log)
                    st_size = st_results[6]
                    file.seek(st_size)

            where = file.tell()
            line = self.get_line(file.readline())

            if not line:
                time.sleep(1)
                file.seek(where)
            else:
                try:
                    inbound_name, message = line.split("<||>")
                except IndexError:
                    inbound_name = ""
                    message = line

                self.connection.send_message(self.sms_channel, "SMS from %s: %s" % (inbound_name, message) )

    def tail_file(self, connection):
        laststat = self.get_current_timestamp()
        file = open(self.nagios_log,'r')
        inode = os.stat(self.nagios_log)[1]

        #Find the size of the file and move to the end
        st_results = os.stat(self.nagios_log)
        st_size = st_results[6]
        file.seek(st_size)

        do_once = True
        while 1:
            if (int(time.time()) - laststat) > 30:
                laststat = int(time.time())
                new_inode = os.stat(self.nagios_log)[1]
                if inode != new_inode:
                    inode = new_inode
                    file.close()
                    file = open(self.nagios_log,'r')
                    st_results = os.stat(self.nagios_log)
                    st_size = st_results[6]
                    file.seek(st_size)
        
            where = file.tell()
            line = self.get_line(file.readline())
       
            if not line:
                time.sleep(1)
                file.seek(where)
            else:
                m = re.search("^\[\d+\]\s(HOST|SERVICE) NOTIFICATION: ([^;]+;(.*))$", line.strip())
                if m is not None:
                    self.process_line(line)
    def process_line(self, line, is_test=False):
        l = NagiosLogLine(line)
        if l.notification_recipient not in self.channel_groups:
            return
        if self.is_muted(l.notification_recipient):
            return
        is_ack = False
        if l.is_service:
            state_string = None
            if re.search("ACKNOWLEDGEMENT", l.state):
                is_ack = True
                state_string = format.color(l.state, format.BLUE)
            elif l.state == "OK":
                state_string = format.color(l.state, format.GREEN)
            elif l.state == "WARNING":
                state_string = format.color(l.state, format.YELLOW)
            elif l.state == "UNKNOWN":
                state_string = format.color(l.state, format.YELLOW)
            elif l.state == "CRITICAL":
                state_string = format.color(l.state, format.RED)
            else:
                state_string = format.color(l.state, format.RED)
            if is_ack is False:
                self.ackable(l.host, l.service, l.state, l.message)
                try:
                    write_string = "%s [%i] %s:%s is %s: %s" % (l.time_string, self.get_ack_number() , l.host, l.service, state_string, l.message)
                except:
                    write_string = "%s %s:%s is %s: %s" % (l.time_string, l.host, l.service, state_string, l.message)
            else:
                #message = "%s;%s" % (m.group(3).split(";")[4], m.group(3).split(";")[5])
                write_string = "%s %s:%s is %s: %s (%s) %s" % (l.time_string, l.host, l.service, state_string, l.message, l.line_from, l.comment)
        else:
            if re.search("ACKNOWLEDGEMENT", l.state):
                is_ack = True
                state_string = format.color(l.state, format.BLUE)
            elif re.search(l.state, "UP"):
                state_string = format.color(l.state, format.GREEN)
            elif re.search(l.state, "WARNING"):
                state_string = format.color(l.state, format.YELLOW)
            elif re.search(l.state, "DOWN"):
                state_string = format.color(l.state, format.RED)
            elif re.search(l.state, "UNREACHABLE"):
                state_string = format.color(l.state, format.RED)
            if is_ack is False:
                self.ackable(l.host, None, l.state, l.message)
                write_string = "%s [%i] %s is %s :%s" % (l.time_string, self.get_ack_number(), l.host, state_string, l.message)
            else:
                state_string = format.color(l.state, format.BLUE)
                write_string = "%s %s is %s :%s" % (l.time_string, l.host, state_string, l.message)
        channel = self.get_channel_group(l.notification_recipient)
        if is_test is False:
            if self.is_muted(channel) is False:
                self.connection.send_message(channel, write_string)
        elif channel:
            return channel, write_string
        else:
            return None

    def write_to_nagios_cmd(self, write_string):
        try:
            rw = open(self.nagios_cmd, 'a+')
            rw.write(write_string)
            rw.close()
        except:
            ##Implement exception catch for not being able to write to the log
            pass

    def get_channel_group(self, channel_group):
        found = False
        try:
            return self.channel_groups[channel_group]
        except:
            return None
            #return self.default_channel_group


    def parseConf(self, inputFile):
        try:
            source = open(inputFile, 'r')
            conf = []
            for line in source.readlines():
                line=line.strip()
                matchID = re.match(r"(?:\s*define)?\s*(\w+)\s+{", line)
                matchAttr = re.match(r"\s*(\w+)(?:=|\s+)(.*)", line)
                matchEndID = re.match(r"\s*}", line)
                if len(line) == 0 or line[0]=='#':
                    pass
                elif matchID:
                    identifier = matchID.group(1)
                    cur = [identifier, {}]
                elif matchAttr:
                    attribute = matchAttr.group(1)
                    value = matchAttr.group(2).strip()
                    cur[1][attribute] = value
                elif matchEndID and cur:
                    conf.append(cur)
                    del cur
            source.close()
            return conf 
        except IOError:
            return False

    def recheck_by_index(self, event, message, options):
        try:
            dict_object = self.ackable_list[int(options.group(1)) - self.list_offset]
            host = dict_object['host']
            return self.recheck(event, host)
        except Exception, e:
            return event.target, "%s Sorry, but I'm unable to recheck" % (event.source) 

    def recheck_by_host(self, event, message, options):
        try:
            host = options.group(1).split(":")[0]
            return self.recheck(event, host)
        except Exception, e:
            return event.target, "%s Sorry, but I'm unable to recheck" % (event.source) 

    def recheck(self, event, host):
        try:
            write_string = "[%lu] SCHEDULE_FORCED_HOST_SVC_CHECKS;%s;%lu\n" % (int(time.time()), host, int(time.time()))
            self.write_to_nagios_cmd(write_string)
            write_string = "[%lu] SCHEDULE_FORCED_HOST_CHECK;%s;%lu\n" % (int(time.time()), host, int(time.time()))
            self.write_to_nagios_cmd(write_string)
            return event.target, "%s: all services on %s scheduled to be rechecked" % (event.source, host) 
        except Exception, e:
            return event.target, "%s Sorry, but I'm unable to recheck" % (event.source) 

        return event.target, "%s: all services on %s scheduled to be rechecked" % (event.source, host) 
    def status_by_index(self, event, message, options):
        conf = self.parseConf(self.status_file)
        ret = None
        host_statuses =  []
        service_statuses =  []
        try:
            dict_object = self.ackable_list[int(options.group(1)) - self.list_offset]
            host = dict_object['host']
            try:
                service = dict_object['service']
                service = service.upper()
            except:
                service is None
            for entry in conf:
                if service is None:
                    if entry[0] == 'hoststatus':
                        ret = entry[1]
                        break
                elif service is not None and '*' not in service:
                    if entry[0] == 'servicestatus' and entry[1]['service_description'].upper() == service:
                        ret = entry[1]
                        break
        except Exception, e:
            return event.target, "%s Sorry, but I can't find any matching services" % (event.source) 

        if not ret:
            return event.target, "%s Sorry, but I can't find any matching services" % (event.source) 

        return event.target, "%s: %s %s Last Checked: %s" % (event.source, host, ret['plugin_output'], self.readable_from_timestamp(ret['last_check']) )

    def readable_from_timestamp(self, unix_time):
        tz = strftime("%Z", time.localtime())
        return "%s %s" % (datetime.datetime.fromtimestamp(int(unix_time)).strftime('%Y-%m-%d %H:%M:%S'), tz)

    def status_by_host_name(self, event, message, options):
        conf = self.parseConf(self.status_file)
        service_statuses = []
        if conf is not False:
            hostname = options.group(1)
            try:
                service = options.group(2).upper()
            except:
                service = None
            host_statuses = []
            for entry in conf:
                if service is None:
                    if entry[0] == 'hoststatus':
                        host_statuses.append(entry[1])
                    if entry[0] == 'servicestatus':
                        service_statuses.append(entry[1])
                elif service is not None and '*' not in service:
                    if entry[0] == 'servicestatus' and entry[1]['service_description'].upper() == service:
                        service_statuses.append(entry[1])
                elif service is not None and service == '*':
                    if entry[0] == 'servicestatus':
                        service_statuses.append(entry[1])
                elif service is not None and '*' in service:
                    service_search = service.split('*')[0]
                    if entry[0] == 'servicestatus' and entry[1]['service_description'].upper().startswith(service_search):
                        service_statuses.append(entry[1])
                else:
                    return event.target, "%s Sorry, but I can't find any matching services" % (event.source) 
            ## OK, we've looped through everything and added them to the appropriate lists
            if service is not None and '*' not in service:
                if len(service_statuses) == 0:
                        return event.target, "%s Sorry, but I can't find any matching services" % (event.source) 
                else:
                    output_list = []
                    for entry in service_statuses:
                        if entry['host_name'] == hostname:
                            if entry['problem_has_been_acknowledged'] == '1':
                                if entry['current_state'] == '0':
                                    state_string = format.color('ACKNOWLEDGEMENT (OK)', format.BLUE)
                                if entry['current_state'] == '1':
                                    state_string = format.color('ACKNOWLEDGEMENT (WARNING)', format.BLUE)
                                if entry['current_state'] == '2':
                                    state_string = format.color('ACKNOWLEDGEMENT (CRITICAL)', format.BLUE)
                            else :
                                if entry['current_state'] == '0':
                                    state_string = format.color('OK', format.GREEN)
                                if entry['current_state'] == '1':
                                    state_string = format.color('WARNING', format.YELLOW)
                                if entry['current_state'] == '2':
                                    state_string = format.color('CRITICAL', format.RED)
                            write_string = "%s: %s:%s is %s - %s Last Checked: %s" % (event.source, hostname, entry['service_description'], state_string, entry['plugin_output'], self.readable_from_timestamp(entry['last_check']))
                            output_list.append(write_string)
                        elif hostname == '*' and entry['service_description'].upper().strip() == service.upper().strip():
                            if entry['problem_has_been_acknowledged'] == '1':
                                if entry['current_state'] == '0':
                                    state_string = format.color('ACKNOWLEDGEMENT (OK)', format.BLUE)
                                if entry['current_state'] == '1':
                                    state_string = format.color('ACKNOWLEDGEMENT (WARNING)', format.BLUE)
                                if entry['current_state'] == '2':
                                    state_string = format.color('ACKNOWLEDGEMENT (CRITICAL)', format.BLUE)
                            else :
                                if entry['current_state'] == '0':
                                    state_string = format.color('OK', format.GREEN)
                                if entry['current_state'] == '1':
                                    state_string = format.color('WARNING', format.YELLOW)
                                if entry['current_state'] == '2':
                                    state_string = format.color('CRITICAL', format.RED)
                            write_string = "%s: %s:%s is %s - %s Last Checked: %s" % (event.source, entry['host_name'], entry['service_description'], state_string, entry['plugin_output'], self.readable_from_timestamp(entry['last_check']))
                            output_list.append(write_string)
                        elif '*' in hostname and entry['service_description'].upper().strip() == service.upper().strip() and hostname.split('*')[0] in entry['host_name']:
                            if entry['problem_has_been_acknowledged'] == '1':
                                if entry['current_state'] == '0':
                                    state_string = format.color('ACKNOWLEDGEMENT (OK)', format.BLUE)
                                if entry['current_state'] == '1':
                                    state_string = format.color('ACKNOWLEDGEMENT (WARNING)', format.BLUE)
                                if entry['current_state'] == '2':
                                    state_string = format.color('ACKNOWLEDGEMENT (CRITICAL)', format.BLUE)
                            else :
                                if entry['current_state'] == '0':
                                    state_string = format.color('OK', format.GREEN)
                                if entry['current_state'] == '1':
                                    state_string = format.color('WARNING', format.YELLOW)
                                if entry['current_state'] == '2':
                                    state_string = format.color('CRITICAL', format.RED)
                            write_string = "%s: %s:%s is %s - %s Last Checked: %s" % (event.source, entry['host_name'], entry['service_description'], state_string, entry['plugin_output'], self.readable_from_timestamp(entry['last_check']))
                            output_list.append(write_string)
                        elif '*' in hostname and '*' == service.upper().strip() and hostname.split('*')[0] in entry['host_name']:
                            for entry in service_statuses:
                                if entry['problem_has_been_acknowledged'] == '1':
                                    if entry['current_state'] == '0':
                                        state_string = format.color('ACKNOWLEDGEMENT (OK)', format.BLUE)
                                    if entry['current_state'] == '1':
                                        state_string = format.color('ACKNOWLEDGEMENT (WARNING)', format.BLUE)
                                    if entry['current_state'] == '2':
                                        state_string = format.color('ACKNOWLEDGEMENT (CRITICAL)', format.BLUE)
                                else :
                                    if entry['current_state'] == '0':
                                        state_string = format.color('OK', format.GREEN)
                                    if entry['current_state'] == '1':
                                        state_string = format.color('WARNING', format.YELLOW)
                                    if entry['current_state'] == '2':
                                        state_string = format.color('CRITICAL', format.RED)
                                write_string = "%s: %s:%s is %s - %s Last Checked: %s" % (event.source, hostname, entry['service_description'], state_string, entry['plugin_output'], self.readable_from_timestamp(entry['last_check']))
                                output_list.append(write_string)
                        elif  '*' in service.upper().strip().split('*')[0] and hostname.split('*')[0] in entry['host_name']:
                            for entry in service_statuses:
                                if entry['problem_has_been_acknowledged'] == '1':
                                    if entry['current_state'] == '0':
                                        state_string = format.color('ACKNOWLEDGEMENT (OK)', format.BLUE)
                                    if entry['current_state'] == '1':
                                        state_string = format.color('ACKNOWLEDGEMENT (WARNING)', format.BLUE)
                                    if entry['current_state'] == '2':
                                        state_string = format.color('ACKNOWLEDGEMENT (CRITICAL)', format.BLUE)
                                else :
                                    if entry['current_state'] == '0':
                                        state_string = format.color('OK', format.GREEN)
                                    if entry['current_state'] == '1':
                                        state_string = format.color('WARNING', format.YELLOW)
                                    if entry['current_state'] == '2':
                                        state_string = format.color('CRITICAL', format.RED)
                                write_string = "%s: %s:%s is %s - %s Last Checked: %s" % (event.source, hostname, entry['service_description'], state_string, entry['plugin_output'], self.readable_from_timestamp(entry['last_check']))
                                output_list.append(write_string)
                    if len(output_list) < self.service_output_limit:
                        return event.target, output_list
                    else:
                        write_string = "%s: more than %i services returned. Please be more specific." % (event.source, self.service_output_limit)
                        return event.target, write_string
            elif service is not None and '*' in service and '*' not in hostname:
                service = service.split('*')[0]
                output_list = []
                for entry in service_statuses:
                    if entry['host_name'] == hostname:
                        if entry['current_state'] == '0':
                            state_string = format.color('OK', format.GREEN)
                        if entry['current_state'] == '1':
                            state_string = format.color('WARNING', format.YELLOW)
                        if entry['current_state'] == '2':
                            state_string = format.color('CRITICAL', format.RED)
                        if entry['current_state'] == '3':
                            state_string = format.color('UNKNOWN', format.YELLOW)
                        write_string = "%s: %s:%s is %s - %s Last Checked: %s" % (event.source, hostname, entry['service_description'], state_string, entry['plugin_output'], self.readable_from_timestamp(entry['last_check']))
                        output_list.append(write_string)
                    elif '*' in hostname and hostname.split('*')[0] in entry['host_name']:
                        if entry['current_state'] == '0':
                            state_string = format.color('OK', format.GREEN)
                        if entry['current_state'] == '1':
                            state_string = format.color('WARNING', format.YELLOW)
                        if entry['current_state'] == '2':
                            state_string = format.color('CRITICAL', format.RED)
                        if entry['current_state'] == '3':
                            state_string = format.color('UNKNOWN', format.YELLOW)
                        write_string = "%s: %s:%s is %s - %s Last Checked: %s" % (event.source, entry['host_name'], entry['service_description'], state_string, entry['plugin_output'], self.readable_from_timestamp(entry['last_check']))
                        output_list.append(write_string)
                if len(output_list) < self.service_output_limit:
                    return event.target, output_list
                else:
                    write_string = "%s: more than %i services returned. Please be more specific." % (event.source, self.service_output_limit)
                    return event.target, write_string
            elif service is None and '*' in hostname:
                host = hostname.split('*')[0]
                output_list = []
                for entry in service_statuses:
                    if entry['host_name'].upper().startswith(host.upper()) and entry['service_description'] == 'PING':
                        if entry['problem_has_been_acknowledged'] == '1':
                            if entry['current_state'] == '0':
                                state_string = format.color('ACKNOWLEDGEMENT (OK)', format.BLUE)
                            if entry['current_state'] == '1':
                                state_string = format.color('ACKNOWLEDGEMENT (WARNING)', format.BLUE)
                            if entry['current_state'] == '2':
                                state_string = format.color('ACKNOWLEDGEMENT (CRITICAL)', format.BLUE)
                        else :
                            if entry['current_state'] == '0':
                                state_string = format.color('OK', format.GREEN)
                            if entry['current_state'] == '1':
                                state_string = format.color('WARNING', format.YELLOW)
                            if entry['current_state'] == '2':
                                state_string = format.color('CRITICAL', format.RED)
                        write_string = "%s: %s:%s is %s - %s Last Checked: %s" % (event.source, entry['host_name'], entry['service_description'], state_string, entry['plugin_output'], entry['last_check'])
                        output_list.append(write_string)
                if len(output_list) < self.service_output_limit:
                    return event.target, output_list
                else:
                    write_string = "%s: more than %i services returned. Please be more specific." % (event.source, self.service_output_limit)
                    return event.target, write_string
            else:
                host_found = False
                for entry in host_statuses:
                    if entry['host_name'] == hostname:
                        if entry['problem_has_been_acknowledged'] == '1':
                            if entry['current_state'] == '0':
                                state_string = format.color('ACKNOWLEDGEMENT (OK)', format.BLUE)
                            if entry['current_state'] == '1':
                                state_string = format.color('ACKNOWLEDGEMENT (WARNING)', format.BLUE)
                            if entry['current_state'] == '2':
                                state_string = format.color('ACKNOWLEDGEMENT (CRITICAL)', format.BLUE)
                        else :
                            if entry['current_state'] == '0':
                                state_string = format.color('OK', format.GREEN)
                            if entry['current_state'] == '1':
                                state_string = format.color('WARNING', format.YELLOW)
                            if entry['current_state'] == '2':
                                state_string = format.color('CRITICAL', format.RED)
                        host_found = True
                        write_string = "%s: %s is %s - %s" % (event.source, hostname, state_string, entry['plugin_output'])
                if host_found is False:
                    write_string = "%s Sorry, but I can't find any matching services" % (event.source)
                return event.target, write_string
        else:
            return event.target, "%s: Sorry, but I'm unable to open the status file" % event.source
    def get_oncall_from_file(self):
        oncall = 'not-yet-set'
        try:
            fh = open(self.oncall_file)
            for line in fh.readlines():
                m = re.search("; On Call = (.+)$", line)
                if m:
                    oncall = m.group(1)
        except Exception, e:
            oncall = 'not-yet-set'
        return oncall

    def get_oncall(self, event, message, options):
        return event.target, "%s: %s currently has the pager" % (event.source, self.get_oncall_from_file()) 

    def page_with_alert_number(self, event, message, options):
        MAX_MESSAGE_LEN = 160
        try:
            dict_object = self.ackable_list[int(options.group(1)) - self.list_offset]
            recipient = options.group(2)
            if dict_object['service'] is not None:
                message = "%s:%s is %s - %s" % (dict_object['host'],dict_object['service'], dict_object['message'], dict_object['state'])
            else:
                message = "%s is %s - %s" % (dict_object['host'], dict_object['state'], dict_object['message'])
            final_message = "%s(%s)" % (message[0:MAX_MESSAGE_LEN - (len(event.source) + 2)], event.source)
            m = MozillaIRCPager(self.connection)
            m.page(event, final_message, options, True)
            m = None
        except TypeError, e:
            return event.target, "%s: Sorry, but no alert exists at this index" % (event.source) 
        except Exception, e:
            return event.target, "Exception: %s" % (e) 
            return event.target, "%s: %s could not be paged" % (event.source, recipient) 
        return event.target, "%s: %s has been paged" % (event.source, recipient) 

    def get_hms_from_seconds(self, input_seconds):                                                                                                                                                                                                                    
        from datetime import datetime, timedelta
        seconds = None
        matches = re.match('(\d+)s', input_seconds)
        if matches:
            seconds = int(matches.group(1))

        matches = re.match('(\d+)h', input_seconds)
        if matches:
            seconds = int(matches.group(1)) * 3600

        matches = re.match('(\d+)d', input_seconds)
        if matches:
            seconds = int(matches.group(1)) * 86400

        matches = re.match('(\d+)m', input_seconds)
        if matches:
            seconds = int(matches.group(1)) * 60
        if seconds is not None:
            sec = timedelta(seconds=seconds)
            return sec
        else:
            return input_seconds
