from __future__ import print_function
import time
from matrix_client.client import MatrixClient
from matrix_client.api import MatrixRequestError
import argparse
import random
from ConfigParser import ConfigParser
import re
import json
import datetime
import tempfile
import shutil


BRAIN_FILE = 'brain.txt'


def train(brain, line):
    line = line.strip()
    words = line.split(' ')
    for word in words:
        word = word.replace('\n', '').replace('\r', '')
    for i in range(len(words) - 2):
        prefix = words[i], words[i + 1]
        follow = words[i + 2]
        if prefix in brain:
            if follow in brain[prefix]:
                brain[prefix][follow] += 1
            else:
                brain[prefix][follow] = 1
        else:
            brain[prefix] = {follow: 1}


def load_brain():
    # BRAIN_FILE file is a plaintext file.
    # each line begins with two words, to form the prefix.
    # After that, the line can have any number of pairs of 1 word and 1
    # positive integer following the prefix. These are the words that may
    # follow the prefix and their weight.
    # e.g. "the fox jumped 2 ran 3 ate 1 ..."
    brain = {}
    print(BRAIN_FILE)
    with open(BRAIN_FILE, 'r') as brainfile:
        for line in brainfile:
            words = line.rstrip().split(' ')
            followers = {}
            for i in range(2, len(words), 2):
                followers[words[i]] = int(words[i + 1])
            brain[(words[0], words[1])] = followers
    return brain


def save_brain(brain):
    with tempfile.NamedTemporaryFile(
            'w', delete=False) as tf:
        for pair in brain:
            followers = brain[pair]
            line = "{} {} ".format(pair[0], pair[1])
            line +=' '.join("{} {}".format(word, followers[word]) for
                    word in followers)
            tf.write(line + '\n')
        name = tf.name
    shutil.move(name, BRAIN_FILE)


def generate_message(brain):
    words = []
    words.extend(random.choice(brain.keys()))
    while (words[-2], words[-1]) in brain and len(words) < 100:
        possibilities = brain[(words[-2], words[-1])]
        total = 0
        for p in possibilities:
            total += possibilities[p]
        num = random.randint(1, total)
        total = 0
        for p in possibilities:
            total += possibilities[p]
            if total >= num:
                break
        words.append(p)
    return ' '.join(words).capitalize() + '.'


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
    global response_rate, username, client, brain
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
                    response = generate_message(brain)
                    reply(client, event, response)
                train(brain, message)

def main():
    global response_rate, username, client, brain
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
    argparser.add_argument("--train", metavar="TRAIN.TXT", type=str,
                           help="Train the bot with a file of text.")
    args = vars(argparser.parse_args())
    debug = args['debug']
    train_file = args['train']

    try:
        brain = load_brain()
    except IOError:
        brain = {}

    if train_file:
        print("Training...")
        with open(train_file) as train_file:
            for line in train_file:
                train(brain, line)
        print("Training complete!")
        save_brain(brain)

    else:
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
            save_brain(brain)
            cfgparser.set('General', 'response rate', str(response_rate))
            print('Saving config...')
            write_config(cfgparser)


if __name__ == '__main__':
    main()
