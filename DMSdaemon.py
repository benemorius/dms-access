#!/usr/bin/env python3

from DMSconfig import ad_string, ad_address, ad_user, ad_password, hard_pins, door_layout, common_doors, server_doors, electrical_doors, garage_doors, common_badges, server_badges, electrical_badges, garage_badges, blacklisted_badges
import daemon
import argparse
import os
import sys
from datetime import datetime
import time
import pickle
from time import sleep
import socket
import json

# Where to store the cache
picklepath = '/root/dms_ad_pickle'

# Log path
log_path = '/root/dms_dev_log'

# Cache age thresholds in seconds
age_max = 86400.0
age_min = 300.0


def stamp():
    now = datetime.now()
    timestamp = now.strftime("%Y-%m-%d %H:%M:%S.") + str(round(int(now.strftime("%f")) / 1000)).zfill(3)
    return timestamp


def get_badges():
    from ldap3 import Server, Connection, ALL, NTLM
    server = Server(ad_address, get_info=ALL)
    conn = Connection(server, user=ad_user, password=ad_password, authentication=NTLM)
    conn.bind()
    badge_list = []
    conn.extend.standard.paged_search("ou=Members,dc=dms,dc=local", ad_string, attributes=['employeeID'], generator=False)
    for entry in conn.entries:
        badge = str(entry['employeeID'].value).lstrip('0')
        if badge != 'None':
            badge_list.append(badge)
    return badge_list


# whyyyyy is this still only twice as fast as querying for all active badges??
# by the way, this won't function reliably until all badges are zero-stripped in ad itself
def query_single_badge(badge):
    badge = str(badge).lstrip('0')
    ad_string = '(&(objectClass=person)(|(userAccountControl=512)(userAccountControl=66048))(employeeID={}))'.format(badge)

    from ldap3 import Server, Connection, ALL, NTLM
    server = Server(ad_address, get_info=ALL)
    conn = Connection(server, user=ad_user, password=ad_password, authentication=NTLM)
    conn.bind()
    badge_list = []
    conn.search("ou=Members,dc=dms,dc=local", ad_string, attributes=['employeeID'], paged_size=1)

    return True if len(conn.entries) > 0 else False


def queue_badge_update(badge):
    pass # not yet implemented


def cache_write(badge_list):
    with open(picklepath, 'wb') as handle:
        pickle.dump(badge_list, handle)


def cache_load():
    with open(picklepath, 'rb') as handle:
        badge_list = pickle.load(handle)
    return badge_list


def cache_age():
    modified = os.path.getmtime(picklepath)
    current = time.time()
    delta = current - modified
    return delta


def verify_pin(door, pin):
    return True if pin in hard_pins else False


def verify_badge(door, badge):
    badge = str(badge).lstrip('0')

    if badge in blacklisted_badges: return False
    
    try:
        badge_list = cache_load()
    except:
        os.system('echo {} - Updating the badge cache because there is none >> {}'.format(stamp(), log_path))
        badge_list = get_badges()
        cache_write(badge_list)

    badge_list.extend(common_badges)

    if badge not in badge_list and cache_age() > age_min:
        os.system('echo {} - Updating the badge cache because a badge failed >> {}'.format(stamp(), log_path))
        badge_list = get_badges()
        cache_write(badge_list)

    if cache_age() > age_max:
        os.system('echo %s - Updating the badge cache because it is too old >> {}'.format(stamp(), log_path))
        badge_list = get_badges()
        cache_write(badge_list)

    badge_list.extend(common_badges)
    garage_badges.extend(badge_list)

    if door in common_doors:
        return True if badge in badge_list else False

    if door in server_doors:
        return True if badge in server_badges else False

    if door in electrical_doors:
        return True if badge in electrical_badges else False

    if door in garage_doors:
        return True if badge in garage_badges else False

    return False


def activate_relay(RELAY, relay, seconds):
    print("{} relay {} on".format(stamp(), relay))
    RELAY.relayON(0, int(relay))
    sleep(seconds)
    print("{} relay {} off".format(stamp(), relay))
    RELAY.relayOFF(0, int(relay))


def open_door(RELAY, door):
    door = door_layout[door]
    seconds = 5
    # os.system('echo %s - %s >> %s' % (stamp(), "activating relay {}".format(door), log_path))
    activate_relay(RELAY, door, seconds)
    # os.system('echo %s - %s >> %s' % (stamp(), "deactivated relay {}".format(door), log_path))
    return


def main():
    parser = argparse.ArgumentParser(description='Opens doors based on badge or pin numbers')
    parser.add_argument('-d', '--daemon', help='Fork and run in background', action='store_true')
    parser.add_argument('-l', '--logfile', help='Absolute path of logfile', default='/var/log/dms_daemon.log')
    parser.add_argument('-a', '--address', help='Address to listen on', default='127.0.0.1')
    parser.add_argument('-p', '--port', help='Port to listen on', default=55555, type=int)
    args = parser.parse_args()

    if args.daemon:
        start_daemon(address=args.address, port=args.port, logfile=args.logfile)
    else:
        start_foreground(address=args.address, port=args.port, logfile=args.logfile)


def daemon_process(address, port):
    import RELAYplate as RELAY
    
    serverSocket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    serverSocket.bind((address, port))

    while True:
        message, address = serverSocket.recvfrom(1024)
        print(stamp() + " " + message.decode().strip())
        message = json.loads(message.decode())
        door = message['door']

        if 'badge' in message:
            badge = message['badge']
            if verify_badge(door, badge):
                os.system('echo {} - Opening door {} for {} >> {}'.format(stamp(), door, str(badge).lstrip('0'), log_path))
                open_door(RELAY, door)
            else:
                os.system('echo {} - Badge failed for door {} {} >> {}'.format(stamp(), door, str(badge).lstrip('0'), log_path))
                queue_badge_update(badge)

        elif 'pin' in message:
            pin = message['pin']
            if verify_pin(door, pin):
                os.system('echo {} - Opening door {} for {} >> {}'.format(stamp(), door, pin, log_path))
                open_door(RELAY, door)
            else:    
                os.system('echo {} - Pin failed for door {} {} >> {}'.format(stamp(), door, pin, log_path))

        else:
            print("message contains no badge or pin")


def start_daemon(address, port, logfile):
    out = open(logfile, 'a+')
    with daemon.DaemonContext(stdout=out, stderr=out):
        daemon_process(address=address, port=port)

def start_foreground(address, port, logfile):
    daemon_process(address=address, port=port)

if __name__ == "__main__":
    main()
