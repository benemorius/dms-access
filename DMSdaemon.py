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
import threading
from threading import Timer
from queue import Queue
import RELAYplate as RELAY
from ldap3 import Server, Connection, ALL, NTLM


# Cache age thresholds in seconds
cache_age_max = 3600

# Max door open time in seconds
door_open_max = 60


relay_board_lock = threading.Semaphore()
badge_update_queue = Queue()
common_badge_list = []
badge_list_lock = threading.Semaphore()


def stamp():
    now = datetime.now()
    timestamp = now.strftime("%Y-%m-%d %H:%M:%S.") + str(round(int(now.strftime("%f")) / 1000)).zfill(3)
    return timestamp


def main():
    parser = argparse.ArgumentParser(
        description='Opens doors based on badge numbers or pin codes',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument('-d', '--daemon', help='Fork and run in background', action='store_true')
    parser.add_argument('-l', '--logfile', help='Absolute path of logfile', default='/root/dms_dev_log')
    parser.add_argument('-c', '--cachefile', help='Absolute path of badge cache file', default='/root/dms_ad_pickle')
    parser.add_argument('-a', '--address', help='Address to listen on', default='127.0.0.1')
    parser.add_argument('-p', '--port', help='Port to listen on', default=55555, type=int)
    args = parser.parse_args()

    global log_path
    log_path = args.logfile

    if args.daemon:
        start_background(address=args.address, port=args.port, relay_address=args.address, relay_port=args.port+1, logfile=args.logfile, cachefile=args.cachefile)
    else:
        start_foreground(address=args.address, port=args.port, relay_address=args.address, relay_port=args.port+1, logfile=args.logfile, cachefile=args.cachefile)


def start_background(address, port, relay_address, relay_port, logfile, cachefile):
    assert False, "--daemon is unimplemented"

    out = open(logfile, 'a+')

    relay_thread = RelayManager(address=relay_address, port=relay_port, RELAY=RELAY)
    relay_thread.start()

    with daemon.DaemonContext(stdout=out, stderr=out):
        access_thread(address=address, port=port, relay_address=relay_address, relay_port=relay_port)


def start_foreground(address, port, relay_address, relay_port, logfile, cachefile):
    relay_thread = RelayManager(address=relay_address, port=relay_port, RELAY=RELAY)
    relay_thread.start()

    access_thread = AccessManager(address=address, port=port, relay_address=relay_address, relay_port=relay_port)
    access_thread.start()

    cache_thread = CacheManager(ad_address=ad_address, ad_user=ad_user, ad_password=ad_password, cache_file_path=cachefile)
    cache_thread.start()

    relay_thread.join()
    access_thread.join()
    cache_thread.join()


class AccessManager(threading.Thread):
    def __init__(self, address, port, relay_address, relay_port):
        threading.Thread.__init__(self, daemon=True, name="AccessManager")
        self.address = address
        self.port = port
        self.relay_address = relay_address
        self.relay_port = relay_port

    def run(self):
        serverSocket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        serverSocket.bind((self.address, self.port))

        while True:
            message, address = serverSocket.recvfrom(1024)
            print(stamp() + " " + message.decode().strip())
            message = json.loads(message.decode())
            door = message['door']

            if 'badge' in message:
                badge = message['badge']
                badge = str(badge).lstrip('0')
                if self._verify_badge(door, badge):
                    os.system('echo {} - Opening door {} for badge {} >> {}'.format(stamp(), door, str(badge).lstrip('0'), log_path))
                    self._open_door(door)
                else:
                    os.system('echo {} - Badge failed for door {} {} >> {}'.format(stamp(), door, str(badge).lstrip('0'), log_path))
                badge_update_queue.put(badge)

            elif 'pin' in message:
                pin = message['pin']
                if self._verify_pin(door, pin):
                    os.system('echo {} - Opening door {} for pin {} >> {}'.format(stamp(), door, pin, log_path))
                    self._open_door(door)
                else:    
                    os.system('echo {} - Pin failed for door {} {} >> {}'.format(stamp(), door, pin, log_path))

            else:
                print("message contains no badge or pin")


    def _verify_pin(self, door, pin):
        return True if pin in hard_pins else False

    def _verify_badge(self, door, badge):
        if badge in blacklisted_badges: return False
        
        with badge_list_lock:
            common_badges.extend(common_badge_list)
            garage_badges.extend(common_badge_list)

        if door in common_doors:
            return True if badge in common_badges else False

        if door in server_doors:
            return True if badge in server_badges else False

        if door in electrical_doors:
            return True if badge in electrical_badges else False

        if door in garage_doors:
            return True if badge in garage_badges else False

        return False

    def _open_door(self, door):
        seconds = 5
        message = '{{"relay": "{}", "seconds": "{}"}}'.format(door, seconds)
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.sendto(bytes(message, "utf-8"), (self.relay_address, self.relay_port))


class CacheManager(threading.Thread):
    def __init__(self, ad_address, ad_user, ad_password, cache_file_path):
        threading.Thread.__init__(self, daemon=True, name="CacheManager")
        self.ad_address = ad_address
        self.ad_user = ad_user
        self.ad_password = ad_password
        self.cache_file_path = cache_file_path
        with badge_list_lock:
            global common_badge_list
            try:
                common_badge_list = self._cache_file_load()
            except:
                common_badge_list = []
        badge_update_queue.put(None)

    def run(self):
        # all updates to the badge cache will happen from here
        while True:
            badge = badge_update_queue.get()
            if len(common_badge_list) == 0:
                os.system('echo {} - Updating the badge cache because there is none >> {}'.format(stamp(), log_path))
                self._update_all_badges()
            elif self._cache_age() > cache_age_max:
                os.system('echo {} - Updating the badge cache because it is older than {} seconds >> {}'.format(stamp(), cache_age_max, log_path))
                self._update_all_badges()
            elif badge is None:
                os.system('echo {} - Updating the badge cache because reasons >> {}'.format(stamp(), log_path))
                self._update_all_badges()
            else:
                # os.system('echo {} - Updating single badge >> {}'.format(stamp(), log_path))
                self._update_badge(badge)
            badge_update_queue.task_done()

    def _update_badge(self, badge):
        print("{} SKIPPING single badge update for {} because badges need to be zero-stripped in AD for single badge queries to work".format(stamp(), badge))
        return

        print("{} updating single badge {}".format(stamp(), badge))
        is_valid = self._query_single_badge(badge)
        print("{} updated badge {} is {} valid".format(stamp(), badge, "\b" if is_valid else "not"))

        if is_valid and badge not in common_badge_list:
            with badge_list_lock:
                common_badge_list.append(badge)
        elif not is_valid:
            with badge_list_lock:
                while badge in common_badge_list: common_badge_list.remove(badge)
        self._cache_file_write(common_badge_list)

    def _update_all_badges(self):
        global common_badge_list
        with badge_list_lock:
            common_badge_list = self._get_badges_from_ad()
        self._cache_file_write(common_badge_list)

    def _cache_file_write(self, badge_list):
        with open(self.cache_file_path, 'wb') as handle:
            pickle.dump(badge_list, handle)

    def _cache_file_load(self):
        with open(self.cache_file_path, 'rb') as handle:
            badge_list = pickle.load(handle)
        return badge_list

    def _cache_age(self):
        modified = os.path.getmtime(self.cache_file_path)
        current = time.time()
        delta = current - modified
        return delta

    def _get_badges_from_ad(self):
        server = Server(self.ad_address, get_info=ALL)
        conn = Connection(server, user=self.ad_user, password=self.ad_password, authentication=NTLM)
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
    def _query_single_badge(self, badge):
        badge = str(badge).lstrip('0')
        ad_string = '(&(objectClass=person)(|(userAccountControl=512)(userAccountControl=66048))(employeeID={}))'.format(badge)

        server = Server(self.ad_address, get_info=ALL)
        conn = Connection(server, user=self.ad_user, password=self.ad_password, authentication=NTLM)
        conn.bind()
        badge_list = []
        conn.search("ou=Members,dc=dms,dc=local", ad_string, attributes=['employeeID'], paged_size=1)

        return True if len(conn.entries) > 0 else False                 


class Relay():
    def __init__(self, RELAY, number):
        self.RELAY = RELAY
        self.number = number
        self.open_seconds = 0
        self.timer = None
        self.activated_time = None

    def activate(self, seconds):
        self._activate()
        self._add_seconds_to_timer(seconds)

    def deactivate(self):
        self.open_seconds = 0
        self.activated_time = None
        self._deactivate()

    def _add_seconds_to_timer(self, seconds):
        self.open_seconds += seconds
        if self.open_seconds > door_open_max:
            self.open_seconds = door_open_max

        if self.activated_time is None:
            self.activated_time = datetime.utcnow()
            interval = self.open_seconds
        else:
            now = datetime.utcnow()
            seconds_since_activation = (now - self.activated_time).total_seconds()
            interval = self.open_seconds - seconds_since_activation

        try:
            self.timer.cancel()
            self.timer = None
        except:
            pass
        self.timer = Timer(interval, self._timer_action)
        self.timer.start()

    def _timer_action(self):
        self.deactivate()
        self.timer = None
   
    def _activate(self):
        with relay_board_lock:
            print("{} relay {} on".format(stamp(), self.number))
            self.RELAY.relayON(0, int(door_layout[self.number]))

    def _deactivate(self):
        with relay_board_lock:
            print("{} relay {} off".format(stamp(), self.number))
            self.RELAY.relayOFF(0, int(door_layout[self.number]))


class RelayManager(threading.Thread):
    def __init__(self, address, port, RELAY):
        threading.Thread.__init__(self, daemon=True, name="RelayManager")
        self.listen_address = address
        self.listen_port = port
        self.RELAY = RELAY
        self.relays = {}
        for relay_number in door_layout.keys():
            self.relays[relay_number] = Relay(self.RELAY, relay_number)

    def run(self):
        serverSocket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        serverSocket.bind((self.listen_address, self.listen_port))

        while True:
            message, address = serverSocket.recvfrom(1024)
            # print(stamp() + " " + message.decode().strip())
            message = json.loads(message.decode())
            relay = message['relay']
            seconds = int(message['seconds'])
            if seconds == 0:
                self.relays[relay].deactivate()
            else:
                self.relays[relay].activate(seconds)


if __name__ == "__main__":
    main()
