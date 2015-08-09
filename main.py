from __future__ import print_function
import time
import mh_python as mh
from matrix_client.client import MatrixClient
from matrix_client.api import MatrixRequestError
import argparse
import random
from ConfigParser import ConfigParser
import re
import json
import datetime


COMMANDS = [
    '!rate'
]


def get_room(client, event):
    return client.rooms[event['room_id']]


def handle_command(client, event, command, args):
    global response_rate
    if command == '!rate':
        if args:
            if len(args) > 1:
                reply(client, event,
                      "Too many arguments. Command is "
                      "!rate [response rate].")
                return

            try:
                num = re.match(r'[0-9]*(\.[0-9]+)?(%|)', args[0]).group()
                if not num:
                    reply(client, event,
                          "Error: Could not parse number.")
                    return
                if num[-1] == '%':
                    rate = float(num[:-1]) / 100
                else:
                    rate = float(num)
                response_rate = rate
                reply(client, event,
                      "Response rate set to %f." % response_rate)
            except ValueError:
                reply(client, event,
                      "Error: Could not parse number.")
        else:
            reply(client, event,
                  "Response rate set to %f." % response_rate)



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
    room = get_room(client, event)
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
            command_found = False
            for command in COMMANDS:
                match = re.search(command, message)
                if match:
                    command_found = True
                    args = message.split(' ')
                    handle_command(client, event, args[0], args[1:])
                    break
            if not command_found:
                if username in message or \
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
        print("A config has been generated. "
              "Please set your bot's username, password, and homeserver "
              "in config.cfg, then run this again.")
        return
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
            try:
                client.listen_for_events()
            except MatrixRequestError:
                # wait a minute and see if the problem resolves itself
                time.sleep(60)


    finally:
        mh.cleanup()
        cfgparser.set('General', 'response rate', str(response_rate))
        print('Saving config...')
        write_config(cfgparser)


if __name__ == '__main__':
    main()
