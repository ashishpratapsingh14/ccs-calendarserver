#!/usr/bin/env python
#
# MigrationExtra script to maintain the enabled/disabled state of the
# calendar server.
#
# This script examines the launchd preferences from the previous system
# (also taking into account the overrides.plist) and then invokes serveradmin
# to start/stop calendar server.
#
# The only argument this script currently cares about is --sourceRoot, which
# should point to the root of the previous system.
#
# Copyright (c) 2005-2009 Apple Inc.  All Rights Reserved.
#
# IMPORTANT NOTE:  This file is licensed only for use on Apple-labeled
# computers and is subject to the terms and conditions of the Apple
# Software License Agreement accompanying the package this file is a
# part of.  You may not port this file to another platform without
# Apple's written consent.

from __future__ import with_statement

import datetime
import optparse
import os
import plistlib
import subprocess
import sys

LAUNCHD_KEY = "org.calendarserver.calendarserver"
LOG = "/Library/Logs/Migration/calendarmigrator.log"
SERVICE_NAME = "calendar"
LAUNCHD_OVERRIDES = "var/db/launchd.db/com.apple.launchd/overrides.plist"
LAUNCHD_PREFS_DIR = "System/Library/LaunchDaemons"
SERVERADMIN = "/usr/sbin/serveradmin"

def main():

    optionParser = optparse.OptionParser()

    optionParser.add_option('--purge', choices=('0', '1'),
        metavar='[0|1]',
        help='remove old files after migration (IGNORED)')

    optionParser.add_option('--sourceRoot', type='string',
        metavar='DIR',
        help='path to the root of the system to migrate')

    optionParser.add_option('--sourceType', type='string',
        metavar='[System|TimeMachine]',
        help='migration source type (IGNORED)')

    optionParser.add_option('--sourceVersion', type='string',
        metavar='10.X.X',
        help='version number of previous system (IGNORED)')

    optionParser.add_option('--targetRoot', type='string',
        metavar='DIR',
        help='path to the root of the new system (IGNORED)')

    optionParser.add_option('--language', choices=('en', 'fr', 'de', 'ja'),
        metavar='[en|fr|de|ja]',
        help='language identifier (IGNORED)')

    (options, args) = optionParser.parse_args()

    if options.sourceRoot:
        try:
            disabled = isServiceDisabled(options.sourceRoot, LAUNCHD_KEY)
            log("Service '%s' was previously %s" %
                (LAUNCHD_KEY, "disabled" if disabled else "enabled"))
        except ServiceStateError, e:
            log("Couldn't determine previous state of service '%s': %s" %
                (LAUNCHD_KEY, e))
            sys.exit(0)

        command = "stop" if disabled else "start"
        try:
            processArgs = [SERVERADMIN, command, SERVICE_NAME]
            log("Invoking %s" % (processArgs,))
            serveradmin = subprocess.Popen(
                args=processArgs,
                stdout=subprocess.PIPE,
            )
            output, error = serveradmin.communicate()

            expectedState = "STOPPED" if disabled else "RUNNING"
            if '%s:state = "%s"' % (SERVICE_NAME, expectedState) in output:
                log("Service %s is now %s" % (SERVICE_NAME, expectedState))
            else:
                log("ERROR: serveradmin returned %s" % (output,))
                sys.exit(1)

        except Exception, e:
            log("ERROR: Failed to run %s: %s" %
                (SERVERADMIN, e))
            sys.exit(1)

    else:
        log("ERROR: --sourceRoot must be specified")
        sys.exit(1)


def isServiceDisabled(source, service):
    """
    Returns whether or not a service is disabled

    @param source: System root to examine
    @param service: launchd key representing service
    @return: True if service is disabled, False if enabled
    """

    overridesPath = os.path.join(source, LAUNCHD_OVERRIDES)
    if os.path.isfile(overridesPath):
        overrides = plistlib.readPlist(overridesPath)
        try:
            return overrides[service]['Disabled']
        except KeyError:
            # Key is not in the overrides.plist, continue on
            pass

    prefsPath = os.path.join(source, LAUNCHD_PREFS_DIR, "%s.plist" % service)
    if os.path.isfile(prefsPath):
        prefs = plistlib.readPlist(prefsPath)
        try:
            return prefs['Disabled']
        except KeyError:
            return False

    raise ServiceStateError("Neither %s nor %s exist" %
        (overridesPath, prefsPath))


class ServiceStateError(Exception):
    """
    Could not determine service state
    """


def log(msg):
    try:
        with open(LOG, 'w') as output:
            timestamp = datetime.datetime.now().strftime("%b %d %H:%M:%S")
            output.write("%s %s\n" % (timestamp, msg))
    except IOError:
        # Could not write to log
        pass


if __name__ == '__main__':
    main()
