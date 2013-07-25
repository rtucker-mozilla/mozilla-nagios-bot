#!/usr/bin/perl

use feature 'say';

say '# ack';
say((
        'ack 123 message:message' =~ '^ack (\d+)\s+(.*)$'
    ) ? "ok -- $1 .. $2" : 'not ok');
say((
        'ack host:"service name" message:message' =~ '^ack ([^:]+):"([^"]+)"\s+(.*)\s*$'
    ) ? "ok -- $1 .. $2 .. $3" : 'not ok');
say((
        'ack host:"service name"' =~ '^ack ([^:]+):"([^"]+)"\s*$'
    ) ? "ok -- $1 .. $2" : 'not ok');
say((
        'ack host:service name' =~ '^ack ([^:]+):([^:]+)\s*$'
    ) ? "ok -- $1 .. $2" : 'not ok');
say((
        'ack host message:message' =~ '^ack ([^:]+)\s(.*)$'
    ) ? "ok -- $1 .. $2" : 'not ok');
say((
        'ack 123' =~ '^ack \S+\s*$'
    ) ? "ok" : 'not ok');

say '# unack';
say((
        'unack 123' =~ '^unack (\d+)\s*$'
    ) ? "ok -- $1" : 'not ok');
say((
        'unack host:"service name"' =~ '^unack ([^:]+):"([^"]+)"\s*$'
    ) ? "ok -- $1 $2" : 'not ok');
say((
        'unack host:service name' =~ '^unack ([^:]+):(.+)$'
    ) ? "ok -- $1 $2" : 'not ok');
say((
        'unack host' =~ '^unack ([^:]+)\s*$'
    ) ? "ok -- $1" : 'not ok');

say '# recheck';
say((
        'recheck 123' =~ '^recheck (\d+)\s*$'
    ) ? "ok -- $1" : 'not ok');
say((
        'recheck host:service name' =~ '^recheck ([^:]+):.*$'
    ) ? "ok -- $1" : 'not ok');
say((
        'recheck host' =~ '^recheck ([^:]+)\s*$'
    ) ? "ok -- $1" : 'not ok');

say '# status';
say((
        'status 123' =~ '^status (\d+)\s*$'
    ) ? "ok -- $1" : 'not ok');
say((
        'status host:"service name"' =~ '^status ([^:]+):"([^"]+)"\s*$'
    ) ? "ok -- $1 .. $2" : 'not ok');
say((
        'status host:service name' =~ '^status ([^:]+):(.+)$'
    ) ? "ok -- $1 .. $2" : 'not ok');
say((
        'status host' =~ '^status ([^:]+)\s*$'
    ) ? "ok -- $1" : 'not ok');
say((
        '^status$'
    ) ? "ok" : 'not ok');

say '# validate';
say((
        'validate host' =~ '^validate ([^:]+)\s*$'
    ) ? "ok -- $1" : 'not ok');

say '# downtime';
say((
        'downtime 123 4d message:message' =~ '^downtime\s+(\d+)\s+(\d+[ydhms])\s+(.*)\s*$'
    ) ? "ok -- $1 .. $2 .. $3" : 'not ok');
say((
        'downtime host:"service name" 4d message:message' =~ '^downtime\s+([^: ]+):"([^"]+)"\s+(\d+[ydhms])\s+(.*)\s*$'
    ) ? "ok -- $1 .. $2 .. $3 .. $4" : 'not ok');
say((
        'downtime host:service name 4d message:message' =~ '^downtime\s+([^: ]+):(.+?)\s+(\d+[ydhms])\s+(.*)\s*$'
    ) ? "ok -- $1 .. $2 .. $3 .. $4" : 'not ok');
say((
        'downtime host 4d message:message' =~ '^downtime\s+([^: ]+)\s+(\d+[ydhms])\s+(.*)\s*$'
    ) ? "ok -- $1 .. $2 .. $3" : 'not ok');

say '# undowntime';
say((
        'undowntime host' =~ '^undowntime ([^:]+)\s*$'
    ) ? "ok -- $1" : 'not ok');
say((
        'undowntime host:"service name"' =~ '^undowntime ([^:]+):"([^"]+)"\s*$'
    ) ? "ok -- $1 .. $2" : 'not ok');
say((
        'undowntime host:service name' =~ '^undowntime ([^:]+):(.+)$'
    ) ? "ok -- $1 .. $2" : 'not ok');

say '# mute';
say((
        'mute' =~ '^mute\s*$'
    ) ? "ok" : 'not ok');

say '# unmute';
say((
        'unmute' =~ '^unmute\s*$'
    ) ? "ok" : 'not ok');

say '# oncall';
say((
        'oncall list' =~ '^(?:oncall|whoisoncall)\s+(list)\s*$'
    ) ? "ok -- $1" : 'not ok');
say((
        'oncall all' =~ '^(?:oncall|whoisoncall)\s+(all)\s*$'
    ) ? "ok -- $1" : 'not ok');
say((
        'oncall name' =~ '^(?:oncall|whoisoncall)\s+(.*)$'
    ) ? "ok -- $1" : 'not ok');
say((
        'oncall' =~ '^(?:oncall|whoisoncall)$'
    ) ? "ok" : 'not ok');

say '# edge cases';
say((
        'downtime host:service name 4d downtime host for 4d :)' =~ '^downtime\s+([^: ]+):(.+?)\s+(\d+[ydhms])\s+(.*)\s*$'
    ) ? "ok -- $1 .. $2 .. $3 .. $4" : 'not ok');

