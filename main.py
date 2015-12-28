from __future__ import print_function
import time
from matrix_client.client import MatrixClient
from matrix_client.api import MatrixRequestError
from requests.exceptions import ConnectionError
import argparse
import random
from ConfigParser import ConfigParser
import re
import json
import datetime
import tempfile
import shutil
import codecs


COMMANDS = [
    '!rate'
]


class Backend(object):

    def train_file(self, filename):
        with open(filename) as train_file:
            for line in train_file:
                self.learn(line)

    def load_brain(self):
        pass

    def learn(self, line):
        pass

    def clean_up(self):
        pass

    def reply(self, message):
        return "(dummy response)"


class MarkovBackend(Backend):
    brain_file = 'brain.txt'

    def __init__(self):
        self.brain = {}

    def load_brain(self):
        # self.brain_file is a plaintext file.
        # each line begins with two words, to form the prefix.
        # After that, the line can have any number of pairs of 1 word and 1
        # positive integer following the prefix. These are the words that may
        # follow the prefix and their weight.
        # e.g. "the fox jumped 2 ran 3 ate 1 ..."
        try:
            with codecs.open(
                    self.brain_file, encoding='utf8', mode='r') as brainfile:
                for line in brainfile:
                    self.load_brain_line(line)
        except IOError:
            self.brain = {}

    def load_brain_line(self, line):
            words = line.rstrip().split(' ')
            followers = {}
            for i in range(2, len(words), 2):
                followers[words[i]] = int(words[i + 1])
            self.brain[(words[0], words[1])] = followers

    def get_save_brain_lines(self):
        for pair in self.brain:
            followers = self.brain[pair]
            line = u"{} {} ".format(pair[0], pair[1])
            line +=u' '.join(u"{} {}".format(word, followers[word]) for
                    word in followers)
            yield (line + u'\n').encode('utf8')

    def save_brain(self):
        with tempfile.NamedTemporaryFile(
                'w', delete=False) as tf:
            name = tf.name
            for line in self.get_save_brain_lines():
                tf.write(line)
        shutil.move(name, self.brain_file)


    def clean_up(self):
        self.save_brain()

    def sanitize(self, word):
        return word.replace('\n', '').replace('\r', '')

    def learn(self, line):
        line = line.strip()
        words = line.split(' ')
        words = [self.sanitize(word) for word in words]
        for i in range(len(words) - 2):
            prefix = words[i], words[i + 1]
            follow = words[i + 2]
            if prefix in self.brain:
                if follow in self.brain[prefix]:
                    self.brain[prefix][follow] += 1
                else:
                    self.brain[prefix][follow] = 1
            else:
                self.brain[prefix] = {follow: 1}

    def reply(self, message):
        words = []
        words.extend(random.choice(self.brain.keys()))
        while (words[-2], words[-1]) in self.brain and len(words) < 100:
            possibilities = self.brain[(words[-2], words[-1])]
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
        return ' '.join(words).capitalize()


class MegaHALBackend(Backend):

    def __init__(self):
        # only loads megahal if backend is being used
        import mh_python
        self.mh = mh_python

    def load_brain(self):
        self.mh.initbrain()

    def learn(self, line):
        self.mh.learn(line.encode('utf8'))

    def clean_up(self):
        self.mh.cleanup()

    def reply(self, message):
        return self.mh.doreply(message.encode('utf8'))


def get_room(client, event):
    return client.rooms[event['room_id']]


def handle_command(client, event, command, args):
    global response_rates, default_response_rate
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
                room = get_room(client, event)
                response_rates[room.room_id] = rate
                reply(client, event,
                      "Response rate set to %f." % rate)
            except ValueError:
                reply(client, event,
                      "Error: Could not parse number.")
        else:
            room = get_room(client, event)
            rate = get_response_rate(room)
            reply(client, event,
                  "Response rate set to %f in this room." % rate)



def get_default_config():
    config = ConfigParser(allow_no_value=True)
    config.add_section('General')
    config.set('General', 'default response rate', "0.10")
    config.set('General', '# Valid backends are "markov" and "megahal"')
    config.set('General', 'backend', 'markov')
    config.add_section('Login')
    config.set('Login', 'username', 'username')
    config.set('Login', 'password', 'password')
    config.set('Login', 'server', 'http://matrix.org')
    config.add_section('Response Rates')
    return config


def write_config(config):
    with open('config.cfg', 'wt') as configfile:
        config.write(configfile)


def reply(client, event, message):
    room = get_room(client, event)
    print("Reply: %s" % message)
    room.send_text(message.encode('utf8'))


def get_name(sc):
    reply = sc.api_call("auth.test")
    data = json.loads(reply.decode('utf-8'))
    return data['user']


def get_response_rate(room):
    global default_response_rate, response_rates
    if room.room_id in response_rates:
        return response_rates[room.room_id]
    else:
        return default_response_rate


def global_callback(event):
    global response_rates, default_response_rate, username, client, backend
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
            message = unicode(event['content']['body'])
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
                room = get_room(client, event)
                if username in message or \
                        random.random() < get_response_rate(room):
                    response = backend.reply(message)
                    time.sleep(3)
                    reply(client, event, response)
                backend.learn(message)

def main():
    global default_response_rate, response_rates, username, client, backend
    cfgparser = ConfigParser()
    success = cfgparser.read('config.cfg')
    if not success:
        cfgparser = get_default_config()
        write_config(cfgparser)
        print("A config has been generated. "
              "Please set your bot's username, password, and homeserver "
              "in config.cfg, then run this again.")
        return
    default_response_rate = cfgparser.getfloat(
        'General', 'default response rate')
    response_rates = {}
    for room_id, rate in cfgparser.items('Response Rates'):
        room_id = room_id.replace('-colon-', ':')
        response_rates[room_id] = rate
    backend = cfgparser.get('General', 'backend')
    username = cfgparser.get('Login', 'username')
    password = cfgparser.get('Login', 'password')
    server = cfgparser.get('Login', 'server')
    argparser = argparse.ArgumentParser(
        description="A chatbot for Matrix (matrix.org)")
    argparser.add_argument("--debug",
                           help="Output raw events to help debug",
                           action="store_true")
    argparser.add_argument("--train", metavar="TRAIN.TXT", type=str,
                           help="Train the bot with a file of text.")
    args = vars(argparser.parse_args())
    debug = args['debug']
    train_file = args['train']

    backends = {'markov': MarkovBackend,
                'megahal': MegaHALBackend}
    backend = backends[backend]()
    backend.load_brain()

    if train_file:
        print("Training...")
        backend.train_file(train_file)
        print("Training complete!")
        backend.clean_up()

    else:
        try:
            client = MatrixClient(server)
            token = client.login_with_password(username, password)
            client.add_listener(global_callback)

            while True:
                try:
                    client.listen_for_events()
                except (MatrixRequestError, ConnectionError):
                    print("Warning: disconnected. Waiting a minute to see if"
                          " the problem resolves itself...")
                    time.sleep(60)

        finally:
            backend.clean_up()
            for room_id, rate in response_rates.items():
                # censor colons because they are a configparser special
                # character
                room_id = room_id.replace(':', '-colon-')
                cfgparser.set('Response Rates', room_id, str(rate))
            print('Saving config...')
            write_config(cfgparser)


if __name__ == '__main__':
    main()
