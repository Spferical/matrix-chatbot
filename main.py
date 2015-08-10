from __future__ import print_function
import time
from matrix_client.client import MatrixClient
import argparse
import random
from ConfigParser import ConfigParser
import re
import json
import datetime
import tempfile


BRAIN_FILE = 'brain.txt'


def train(brain, line):
    for i in range(len(line) - 2):
        prefix = line[i], line[i + 1]
        follow = line[i + 2]
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
    with open('BRAIN_FILE', 'r') as brainfile:
        for line in brainfile:
            words = line.split(' ')
            followers = {}
            for i in range(2, len(words), 2):
                followers[words[i]] = words[i + 1]
            brain[(words[0], words[1])] = followers
    return brain


def save_brain(brain):
    with tempfile.NamedTemporaryFile(
            'w', delete=False) as tf:
        for pair in brain:
            followers = brain[pair]
            line = "{} {}".format(pair[0], pair[1])
            line = ' '.join(line, "{} {}".format(word, followers[word]) for
                    word in followers)
            tf.write(line + '\n')
        name = tf.name
    os.rename(name, BRAIN_FILE)


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
    train = args['train']

    try:
        brain = load_brain()
    except FileNotFoundError:
        brain = {}

    if train:
        print("Training...")
        with open(train) as train_file:
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
                client.listen_for_events()

        finally:
            save_brain(brain)
            cfgparser.set('General', 'response rate', str(response_rate))
            print('Saving config...')
            write_config(cfgparser)


if __name__ == '__main__':
    main()
