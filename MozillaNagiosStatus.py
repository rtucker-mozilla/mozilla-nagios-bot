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
import socket

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
        self.use_mklive_status = USE_MKLIVE_STATUS
        self.mklive_status_socket = MKLIVE_STATUS_SOCKET
        self.use_irc_hilight = USE_IRC_HILIGHT
        self.irc_hilight_nick = IRC_HILIGHT_NICK


        ##Start new thread to parse the nagios log file
        thread.start_new_thread(self.tail_file, (self.connection,))
        thread.start_new_thread(self.watch_incoming_sms, (self.connection,))
        thread.start_new_thread(self.monitor_current_oncall, (self.connection,))
        #self.tail_file(self.connection)

    def build_regex_list(self):
        #self.message_commands.append({'regex':'^(?:\s*ack\s*)?(\d+)(?:\s*ack\s*)?[:\s]+([^:]+)\s*$', 'callback':self.ack})
        self.message_commands.append({'regex':'^ack (\d+)\s+(.*)$', 'callback':self.ack})
        self.message_commands.append({'regex':'^ack ([^: ]+):"([^"]+)"\s+(.*)\s*$', 'callback':self.ack_by_host_with_service})
        self.message_commands.append({'regex':'^ack ([^: ]+):"([^"]+)"\s*$', 'callback':self.ack_by_host_with_service})
        self.message_commands.append({'regex':'^ack ([^: ]+):([^:]+)\s*$', 'callback':self.ack_by_host_with_service})
        self.message_commands.append({'regex':'^ack ([^: ]+)\s(.*)$', 'callback':self.ack_by_host})
        self.message_commands.append({'regex':'^ack \S+\s*$', 'callback':self.ack_missing_message})

        self.message_commands.append({'regex':'^unack (\d+)\s*$', 'callback':self.unack})
        self.message_commands.append({'regex':'^unack ([^: ]+):"([^"]+)"\s*$', 'callback':self.unack_by_host})
        self.message_commands.append({'regex':'^unack ([^: ]+):(.+)$', 'callback':self.unack_by_host})
        self.message_commands.append({'regex':'^unack ([^: ]+)\s*$', 'callback':self.unack_by_host})

        self.message_commands.append({'regex':'^recheck (\d+)\s*$', 'callback':self.recheck_by_index})
        self.message_commands.append({'regex':'^recheck ([^: ]+):.*$', 'callback':self.recheck_by_host})
        self.message_commands.append({'regex':'^recheck ([^: ]+)\s*$', 'callback':self.recheck_by_host})

        self.message_commands.append({'regex':'^status (\d+)\s*$', 'callback':self.status_by_index})
        #self.message_commands.append({'regex':'^status ([^: ]+)\s*$', 'callback':self.status_by_host_name})
        #self.message_commands.append({'regex':'^status ([^: ]+):(.+)$', 'callback':self.status_by_host_name})
        self.message_commands.append({'regex':'^status ([^: ]+):"([^"]+)"\s*$', 'callback':self.status_by_host_namemk})
        self.message_commands.append({'regex':'^status ([^: ]+):(.+)$', 'callback':self.status_by_host_namemk})
        self.message_commands.append({'regex':'^status ([^: ]+)\s*$', 'callback':self.status_by_host_namemk})
        self.message_commands.append({'regex':'^status$', 'callback':self.nagios_status})

        self.message_commands.append({'regex':'^validate ([^: ]+)\s*$', 'callback':self.validate_command})

        self.message_commands.append({'regex':'^downtime\s+(\d+)\s+(\d+[ydhms])\s+(.*)\s*$', 'callback':self.downtime_by_index})
        self.message_commands.append({'regex':'^downtime\s+([^: ]+):"([^"]+)"\s+(\d+[ydhms])\s+(.*)\s*$', 'callback':self.downtime})
        self.message_commands.append({'regex':'^downtime\s+([^: ]+):(.+?)\s+(\d+[ydhms])\s+(.*)\s*$', 'callback':self.downtime})
        self.message_commands.append({'regex':'^downtime\s+([^: ]+)\s+(\d+[ydhms])\s+(.*)\s*$', 'callback':self.downtime})

        self.message_commands.append({'regex':'^undowntime ([^: ]+)\s*$', 'callback':self.cancel_downtime})
        self.message_commands.append({'regex':'^undowntime ([^: ]+):"([^"]+)"\s*$', 'callback':self.cancel_downtime})
        self.message_commands.append({'regex':'^undowntime ([^: ]+):(.+)$', 'callback':self.cancel_downtime})

        self.message_commands.append({'regex':'^mute\s*$', 'callback':self.mute})

        self.message_commands.append({'regex':'^unmute\s*$', 'callback':self.unmute})

        # At some point, remove this line and the associated function
        #self.message_commands.append({'regex':'^(oncall|whoisoncall)$', 'callback':self.get_oncall})

        self.message_commands.append({'regex':'^(?:oncall|whoisoncall)\s+(list)\s*$', 'callback':self.get_available_oncall})
        self.message_commands.append({'regex':'^(?:oncall|whoisoncall)\s+(all)\s*$', 'callback':self.get_all_oncall_type})
        self.message_commands.append({'regex':'^(?:oncall|whoisoncall)\s+(.*)$', 'callback':self.get_oncallmk})
        self.message_commands.append({'regex':'^(?:oncall|whoisoncall)$', 'callback':self.get_oncallmk})
        #self.message_commands.append({'regex':'^whoisoncall$', 'callback':self.get_oncall})

    ###Default entry point for each plugin. Simply returns a regex and which static method to call upon matching the regex

    def file_age_in_seconds(self, pathname):
        import os, stat
        return time.time() - os.stat(pathname)[stat.ST_MTIME]

    def return_help(self):
        return [
            'ack <alert_id> <reason for ack>',
            'ack <host> <reason for ack>',
            'ack <host:service> <reason for ack>',
            'unack <alert_id>',
            'unack <host>',
            'unack <host>:<service>',
            'recheck <id_of alert>',
            'recheck <host>',
            'recheck <host>:<service>  # rechecks all services on <host>, not just <service>.',
            'status <host>',
            'status <host:service>',
            'status <alert_id>',
            'downtime <alert_id> <interval><y|d|h|m|s> <message> <interval> is the how long <y|d|h|m|s> is years|days|hours|minutes|seconds',
            'downtime <host:service> <interval><y|d|h|m|s> <message> <interval> is the how long <y|d|h|m|s> is years|days|hours|minutes|seconds',
            'undowntime <host>',
            'undowntime <host:service>',
            'mute',
            'unmute',
            #'oncall|whoisoncall',
            'oncall <who>  # <who> can be <all|list|or an entry from the output of oncallmk list>',
            ]
    def return_plugins(self):
        return self.message_commands

    def execute_query(self, query_string):
        retry = 0
        max_retry = 5
        while retry < max_retry:
            try:
                s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                s.settimeout(10)
                s.connect(self.mklive_status_socket)
                s.send(query_string)
                answer = s.recv(100000000)
                s.shutdown(socket.SHUT_WR)
                return self.parse_table(answer)
            except socket.error:
                time.sleep(3)
                retry += 1
                continue
        return []

    def parse_table(self, answer):
        table = [ line.split(';') for line in answer.split('\n')[:-1] ]
        return table

    def build_wildcard_query(self, query):
        query_string = ''

        if query.startswith('*') and query.endswith('*'):
            query_string = '%s' % (query.replace('*', ''))
        if not query.startswith('*'):
            query_string = '^%s' % (query.replace('*', ''))
        if not query.endswith('*'):
            query_string = '%s$' % (query.replace('*', ''))

        return query_string
    
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
            m = re.search("(\d+)([ydhms])", duration)
            if m:
                duration = self.interval_to_seconds(m.group(1), m.group(2))

                if service is not None:
                    write_string = "[%lu] SCHEDULE_SVC_DOWNTIME;%s;%s;%d;%d;1;0;%d;%s;%s\n" % (int(time.time()), host, service, int(time.time()), int(time.time()) + duration, duration, event.source, comment)
                    self.write_to_nagios_cmd(write_string)
                    return event.target, "%s: Downtime for service %s:%s scheduled for %s" % (event.source, host, service, self.get_hms_from_seconds(original_duration))
                else:
                    write_string = "[%lu] SCHEDULE_HOST_DOWNTIME;%s;%d;%d;1;0;%d;%s;%s\n" % (int(time.time()), host, int(time.time()), int(time.time()) + duration, duration, event.source, comment)
                    self.write_to_nagios_cmd(write_string)
                    return event.target, "%s: Downtime for host %s scheduled for %s" % (event.source, host, self.get_hms_from_seconds(original_duration) )
        else:
            return event.target, "%s: Unable to find host" % (event.source)

    def cancel_downtime(self, event, message, options):
        message = ""
        host = options.group(1)
        query = []
        query.append("GET downtimes")
        query.append("Filter: host_alias = %s" % host)
        query.append("Columns: id")
        try:
            service = options.group(2)
            query.append("Filter: service_display_name = %s" % service)
        except IndexError:
            query.append("Filter: service_display_name =")
            service = None
        
        query_string = "%s\n\n" % ('\n'.join(query))
        try:
            downtime_id = self.execute_query(query_string)[0][0]
            print downtime_id
            if service:
                command_string = 'DEL_SVC_DOWNTIME'
            else:
                command_string = 'DEL_HOST_DOWNTIME'
            write_string = "[%lu] %s;%s" % (int(time.time()), command_string, downtime_id)
            self.write_to_nagios_cmd(write_string)
            if not service:
                message = "cancelled downtime for host %s" % (host)
            else:
                message = "cancelled downtime for service %s:%s" % (host, service)
            if not downtime_id or downtime_id == '':
                if not service:
                    message = "Unable to cancel downtime for host %s" % (host)
                else:
                    message = "Unable to cancel downtime for service %s:%s" % (host, service)
        except IndexError:
            if not service:
                message = "Unable to cancel downtime for host %s" % (host)
            else:
                message = "Unable to cancel downtime for service %s:%s" % (host, service)

        return event.target, message

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

        if self.use_mklive_status:
            host_and_service_search = self.mksearch(host, service)

            if len(host_and_service_search) == 0:
                return event.target, "%s: I'm sorry but I cannot find the host or service" % (event.source)

        if self.validate_host(host) is True:
            current_time = time.time() 
            m = re.search("(\d+)([ydhms])", duration)
            if m:
                duration = self.interval_to_seconds(m.group(1), m.group(2))
                if service is not None:
                    write_string = "[%lu] SCHEDULE_SVC_DOWNTIME;%s;%s;%d;%d;1;0;%d;%s;%s" % (int(time.time()), host, service, int(time.time()), int(time.time()) + duration, duration, event.source, comment)
                    self.write_to_nagios_cmd(write_string)
                    return event.target, "%s: Downtime for service %s:%s scheduled for %s" % (event.source, host, service, self.get_hms_from_seconds(original_duration)) 
                else:
                    write_string = "[%lu] SCHEDULE_HOST_DOWNTIME;%s;%d;%d;1;0;%d;%s;%s" % (int(time.time()), host, int(time.time()), int(time.time()) + duration, duration, event.source, comment)
                    self.write_to_nagios_cmd(write_string)
                    return event.target, "%s: Downtime for host %s scheduled for %s" % (event.source, host, self.get_hms_from_seconds(original_duration) )
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
        elif type == "y":
            duration = int(amount) * 86400 * 365
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

    def validate_command(self, event, message, options):
        host = options.group(1)
        return self.validate_host(host)

    def validate_host(self, host):

        ##Following is for the test case to pass. We shouldn't ever have a host with this name
        if host == 'test-host.fake.mozilla.com':
            return True

        if host is None:
            host = options.group(1)

        if self.use_mklive_status:
            host_and_service_search = self.mksearch(host, None)
            if len(host_and_service_search) > 0:
                return True
            else:
                return False, "Could not find host %s" % (host) 
        else:
            conf = self.parseConf(self.status_file)
            host = host.strip()
            if conf is not False:
                for entry in conf:
                    if entry[0] == 'hoststatus' and entry[1]['host_name'] == host:
                        return True
                    else:
                        continue

            return False, "Could not find host %s" % (host) 

    def nagios_status(self, event, message, options):
        service_statuses = []
        host_statuses = []
        has_statuses = True
        if self.use_mklive_status:
            has_statuses = True
            hosts = self.mkgetallhosts()
            for host in hosts:
                host_statuses.append({
                                'current_state': host[1],
                                })
            service_statuses = []
            services = self.mkgetallservices()
            for service in services:
                service_statuses.append({
                                'current_state': service[1],
                                'check_type': service[6],
                                })
        else:
            conf = self.parseConf(self.status_file)
            has_statuses = True
            for entry in conf:
                if entry[0] == 'hoststatus':
                    host_statuses.append(entry[1])
                if entry[0] == 'servicestatus':
                    service_statuses.append(entry[1])

        if has_statuses:
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
                return_string = "%s: acknowledged host %s" % (event.source, host)
            else:
                write_string = "[%lu] ACKNOWLEDGE_SVC_PROBLEM;%s;%s;1;1;1;nagiosadmin;(%s)%s\n" % (timestamp,host,service,from_user,message)
                return_string = "%s: acknowledged service %s:%s" % (event.source, host, service)
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
        host = options.group(1)
        try:
            svc = options.group(2)
        except:
            svc = None

        if svc:
            try:
                write_string = "[%lu] REMOVE_SVC_ACKNOWLEDGEMENT;%s;%s" % (timestamp, host, svc)
                self.write_to_nagios_cmd(write_string)
                return event.target, "%s: removed acknowledgment (if any) for service %s:%s" % (event.source, host, svc)
            except Exception, e:
                return event.target, "%s Could not ack" % (e)

        else:
            try:
                write_string = "[%lu] REMOVE_HOST_ACKNOWLEDGEMENT;%s" % (timestamp, host)
                self.write_to_nagios_cmd(write_string)
                return event.target, "%s: removed acknowledgment (if any) for host %s" % (event.source, host)
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
                return event.target, "%s: removed acknowledgment (if any) for host %s" % (event.source, host)
            else:
                write_string = "[%lu] REMOVE_SVC_ACKNOWLEDGEMENT;%s;%s" % (timestamp, host, service)
                return event.target, "%s: removed acknowledgment (if any) for service %s:%s" % (event.source, host, service)
            self.write_to_nagios_cmd(write_string)
            return event.target, "%s" % (write_string) 
        except TypeError:
            return event.target, "%s: Sorry, but no alert exists at this index" % (event.source) 
        except IndexError:
            return event.target, "%s: Sorry, but no alert exists at this index" % (event.source) 
        except Exception, e:
            return event.target, "%s: %s Could not ack" % (event.source, e)

    def ack_missing_message(self, event, message, options):
            return event.target, "%s: Could not ack. Missing message argument." % (event.source)

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
                return event.target, "%s: acknowledged host %s" % (event.source, host) 
            else:
                write_string = "[%lu] ACKNOWLEDGE_SVC_PROBLEM;%s;%s;1;1;1;%s;%s\n" % (timestamp, host, service, from_user, message)
                self.write_to_nagios_cmd(write_string)
                return event.target, "%s: acknowledged service %s:%s" % (event.source, host, service) 
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
            return event.target, "%s: acknowledged host %s" % (event.source, host) 
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
        """
            Going to pad some sleep in here so the connection
            object exists when we get going.
        """
        time.sleep(5)
        #current_oncall = self.get_oncall_from_file()
        current_oncall = self.get_oncall_name_from_statusmk('sysadmin')
        while 1:
            #new_oncall = self.get_oncall_from_file()
            new_oncall = self.get_oncall_name_from_statusmk('sysadmin')
            if new_oncall != current_oncall:
                for channel in self.oncall_channels:
                    self.send_oncall_update(connection, channel['name'], new_oncall)
                if self.update_oncall:
                    self.set_new_oncall(connection, new_oncall)
                current_oncall = new_oncall
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
            elif re.search("DOWNTIME", l.state):
                is_ack = True
                state_string = format.color(l.state, format.YELLOW)
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
            elif re.search("DOWNTIME", l.state):
                is_ack = True
                state_string = format.color(l.state, format.YELLOW)
            else:
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
                if self.use_irc_hilight and l.notification_recipient == self.irc_hilight_nick:
                    write_string = "(%s) %s" % (format.color("IRC", format.PURPLE), write_string)
                self.connection.send_message(channel, write_string)
        elif channel:
            if self.use_irc_hilight and l.notification_recipient == self.irc_hilight_nick:
                write_string = "(%s) %s" % (format.color("IRC", format.PURPLE), write_string)
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
            return event.target, "%s: rechecking all services on host %s" % (event.source, host)
        except Exception, e:
            return event.target, "%s Sorry, but I'm unable to recheck" % (event.source) 

        return event.target, "%s: rechecking all services on host %s" % (event.source, host)
    def status_by_index(self, event, message, options):
        ret = None
        host_statuses =  []
        service_statuses =  []
        try:
            dict_object = self.ackable_list[int(options.group(1)) - self.list_offset]
            host = dict_object['host']
            try:
                service = dict_object['service']
            except:
                service is None
            if self.use_mklive_status:
                host_and_service_search = self.mksearch(host, service)
                if len(host_and_service_search) > 0:
                    plugin_output = host_and_service_search[0][2]
                    last_check = host_and_service_search[0][3]
                    ret = True
            else:
                conf = self.parseConf(self.status_file)
                for entry in conf:
                    if service is None:
                        if entry[0] == 'hoststatus':
                            plugin_output = entry[1]['plugin_output']
                            last_check = entry[1]['last_check']
                            ret = True
                            break
                    elif service is not None and '*' not in service:
                        if entry[0] == 'servicestatus' and entry[1]['service_description'].upper() == service:
                            plugin_output = entry[1]['plugin_output']
                            last_check = entry[1]['last_check']
                            ret = True
                            break
        except Exception, e:
            return event.target, "%s Sorry, but I can't find any matching services" % (event.source) 

        if not ret:
            return event.target, "%s Sorry, but I can't find any matching services" % (event.source) 

        return event.target, "%s: %s %s Last Checked: %s" % (event.source, host, plugin_output, self.readable_from_timestamp(last_check) )

    def readable_from_timestamp(self, unix_time):
        tz = strftime("%Z", time.localtime())
        return "%s %s" % (datetime.datetime.fromtimestamp(int(unix_time)).strftime('%Y-%m-%d %H:%M:%S'), tz)

    def mkgetallhosts(self):
        query = []
        query.append("GET hosts")
        query.append("Columns: host_name state plugin_output last_check host_acknowledged")
        query_string = "%s\n\n" % ('\n'.join(query))
        return self.execute_query(query_string)

    def mkgetallservices(self):
        query = []
        query.append("GET services")
        query.append("Columns: host_name state plugin_output last_check service_acknowledged description check_type")
        query_string = "%s\n\n" % ('\n'.join(query))
        return self.execute_query(query_string)

    def mksearch(self, host_search=None, service_search=None):
        query = []
        if not service_search and host_search and len(host_search) > 0:
            query.append("GET hosts")
            query.append("Columns: host_name state plugin_output last_check host_acknowledged")
            host_query = self.build_wildcard_query(host_search)
            query.append("Filter: host_name ~ %s" % host_query)
        else:
            query.append("GET services")
            query.append("Columns: host_name state plugin_output last_check service_acknowledged description")
            service_query = self.build_wildcard_query(service_search)
            query.append("Filter: description ~ %s" % service_query)
            if host_search and len(host_search) > 0:
                host_query = self.build_wildcard_query(host_search)
                query.append("Filter: host_name ~ %s" % host_query)
        query_string = "%s\n\n" % ('\n'.join(query))
        return self.execute_query(query_string)

    def status_by_host_namemk(self, event, message, options):
        if not self.use_mklive_status:
            return event.target, "Sorry, but the mklivestatus plugin is not enabled"

        output_list = []
        hostname = options.group(1)
        try:
            service = options.group(2)
        except:
            service = None

        results = self.mksearch(hostname, service)

        if len(results) == 0:
            write_string = "%s: I'm sorry, I couldn't find any hosts/services for you." % (event.source)
            return event.target, write_string

        for entry in results:
            host_name = entry[0]
            current_state = entry[1]
            plugin_output = entry[2]
            last_check = entry[3]
            is_acked = entry[4]
            if service:
                description = entry[5]
            else:
                description = ''
            if is_acked == '1':
                if current_state == '0':
                    state_string = format.color('ACKNOWLEDGEMENT (OK)', format.BLUE)
                if current_state == '1':
                    state_string = format.color('ACKNOWLEDGEMENT (WARNING)', format.BLUE)
                if current_state == '2':
                    state_string = format.color('ACKNOWLEDGEMENT (CRITICAL)', format.BLUE)
                if current_state == '3':
                    state_string = format.color('ACKNOWLEDGEMENT (UNKNOWN)', format.BLUE)
            else:
                if current_state == '0':
                    state_string = format.color('OK', format.GREEN)
                if current_state == '1':
                    state_string = format.color('WARNING', format.YELLOW)
                if current_state == '2':
                    state_string = format.color('CRITICAL', format.RED)
                if current_state == '3':
                    state_string = format.color('UNKNOWN', format.YELLOW)
            if service:
                write_string = "%s: %s:%s is %s - %s Last Checked: %s" % (event.source,
                                host_name, description, state_string, plugin_output,
                                self.readable_from_timestamp(last_check))
            else:
                write_string = "%s: %s:%s is %s - %s Last Checked: %s" % (event.source,
                                host_name, description, state_string, plugin_output,
                                self.readable_from_timestamp(last_check))
            output_list.append(write_string)

        if len(output_list) < self.service_output_limit:
            return event.target, output_list
        else:
            write_string = "%s: more than %i services returned. Please be more specific." % (event.source, self.service_output_limit)
            return event.target, write_string


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

    def get_available_oncall(self, event, message, options):
        query = []
        query.append("GET contacts")
        query.append("Columns: alias")
        query.append("Filter: alias ~~ OnCall \(.*\)")
        query_string = "%s\n\n" % ('\n'.join(query))
    
        oncalls = []
        message = ""
        try:
            oncall_list = self.execute_query(query_string)
            message = "Available Oncall Types:"
            oncall_string = ""
            for i in oncall_list:
                m = re.search('(.*) Oncall', i[0])
                if m:
                    oncall_string += " %s" % (m.group(1))
            message += oncall_string
        except IndexError:
            message = "I've failed to detect available oncalls"

        return event.target, "%s" % message
        
    def get_all_oncall_type(self, event, message, options):
        event_source = event.source
        query = []
        query.append("GET contacts")
        query.append("Columns: alias")
        query.append("Filter: alias ~~ OnCall \(")
        query_string = "%s\n\n" % ('\n'.join(query))
        try:
            oncall_list = self.execute_query(query_string)
            return_list = []
            for i in oncall_list:
                m = re.search('(.*) Oncall \((.*)\)', i[0])
                if m:
                    return_list.append("%s: %s currently has the %s pager" % (event_source, m.group(2), m.group(1)))
            return event.target, return_list
        except IndexError:
            return event_source, "I've failed to detect available oncalls"
    def get_oncall_name_from_statusmk(self, oncall_type):
        query = []
        query.append("GET contacts")
        query.append("Columns: alias")
        query.append("Filter: alias ~~ %s OnCall" % oncall_type)
        query_string = "%s\n\n" % ('\n'.join(query))
        try:
            m = re.search('\((.*)\)', self.execute_query(query_string)[0][0])
            if m:
                return "%s" % m.group(1)
            else:
                return "UNKNOWN"
        except IndexError:
            return "ERROR :%s" % oncall_type

    def get_oncall_from_statusmk(self, oncall_type):
        oncall_from_statusmk = self.get_oncall_name_from_statusmk(oncall_type)
        return "%s currently has the pager" % oncall_from_statusmk


    def get_oncallmk(self, event, message, options):
        try:
            oncall_type = options.group(1)
        except:
            oncall_type = None

        """
            The old functionality returned the sysadmin
            who was oncall by default. This will replicate
            this.
        """
        if oncall_type == '' or not oncall_type:
            oncall_type = 'sysadmin'

        if oncall_type != 'all':
            return event.target, "%s: %s" % (event.source, self.get_oncall_from_statusmk(oncall_type)) 
        else:
            return self.get_all_oncall_type(event.source)

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
