from __future__ import print_function
import time
import mh_python as mh
from matrix_client.client import MatrixClient
import argparse
import random
from ConfigParser import ConfigParser
import re
import json
import datetime


def get_default_config():
    config = ConfigParser()
    config.add_section('General')
    config.set('General', 'response rate', "0.10")
    config.add_section('Login')
    config.set('Login', 'username', 'username')
    config.set('Login', 'password', 'password')
    config.set('Login', 'server', 'http://matrix.org')
    return config


def write_config(config):
    with open('config.cfg', 'wt') as configfile:
        config.write(configfile)


def reply(client, event, message):
    room = client.rooms[event['room_id']]
    print("Reply: %s" % message)
    room.send_text(message)


def get_name(sc):
    reply = sc.api_call("auth.test")
    data = json.loads(reply.decode('utf-8'))
    return data['user']


def global_callback(event):
    global response_rate, username, client
    # join rooms if invited
    if event['type'] == 'm.room.member':
        if 'content' in event and 'membership' in event['content']:
            if event['content']['membership'] == 'invite':
                room = event['room_id']
                client.join_room(room)
                print('Joined room ' + room)
    elif event['type'] == 'm.room.message':
        # only care about text messages by other people
        if event['user_id'] != client.user_id and \
                event['content']['msgtype'] == 'm.text':
            message = event['content']['body']
            # lowercase message so we can search it
            # case-insensitively
            message = message.lower()
            print("Handling message: %s" % message)
            match = re.search(
                "%s, set response rate to [0-9]{2}(%%|)" % username,
                message)
            if match:
                words = match.group().split()
                num = words[-1]
                if num[-1] == '%':
                    rate = float(num[:-1]) / 100
                else:
                    rate = float(num)
                response_rate = rate
                reply(client, event, "Response rate set to %f" % rate)
            else:
                match = re.search(
                    "%s, what is your response rate?" % username, message)
                if match:
                    reply(client, event,
                        "My response rate is set at %f."
                        % response_rate)
                elif username in message or \
                        random.random() < response_rate:
                    response = mh.doreply(message)
                    reply(client, event, response)
                else:
                    mh.learn(message)

def main():
    global response_rate, username, client
    cfgparser = ConfigParser()
    success = cfgparser.read('config.cfg')
    if not success:
        cfgparser = get_default_config()
        write_config(cfgparser)
    response_rate = cfgparser.getfloat('General', 'response rate')
    username = cfgparser.get('Login', 'username')
    password = cfgparser.get('Login', 'password')
    server = cfgparser.get('Login', 'server')
    argparser = argparse.ArgumentParser(
        description="Slack chatbot using MegaHAL")
    argparser.add_argument("--debug",
                           help="Output raw events to help debug",
                           action="store_true")
    args = vars(argparser.parse_args())
    debug = args['debug']
    mh.initbrain()

    try:
        client = MatrixClient(server)
        token = client.login_with_password(username, password)
        client.add_listener(global_callback)

        while True:
            client.listen_for_events()

    finally:
        mh.cleanup()
        cfgparser.set('General', 'response rate', str(response_rate))
        print('Saving config...')
        write_config(cfgparser)


if __name__ == '__main__':
    main()
