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
import time


COMMANDS = [
    '!rate'
]


class ConfigParser(ConfigParser):
    # allow case-sensitive option names
    # needed for saving per-room response rates
    optionxform = str


class Backend(object):

    def train_file(self, filename):
        with open(filename) as train_file:
            for line in train_file:
                self.learn(line)

    def load_brain(self):
        pass

    def learn(self, line):
        pass

    def save(self):
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

    def save(self):
        with tempfile.NamedTemporaryFile(
                'w', delete=False) as tf:
            name = tf.name
            for line in self.get_save_brain_lines():
                tf.write(line)
        shutil.move(name, self.brain_file)


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

    def save(self):
        self.mh.cleanup()

    def reply(self, message):
        return unicode(
            self.mh.doreply(message.encode('utf8')), 'utf8', 'replace')


class Config(object):
    def __init__(self, cfgparser):
        self.backend = cfgparser.get('General', 'backend')
        self.display_name = cfgparser.get('General', 'display name')
        self.username = cfgparser.get('Login', 'username')
        self.password = cfgparser.get('Login', 'password')
        self.server = cfgparser.get('Login', 'server')
        self.default_response_rate = cfgparser.getfloat(
            'General', 'default response rate')
        self.response_rates = {}
        for room_id, rate in cfgparser.items('Response Rates'):
            room_id = room_id.replace('-colon-', ':')
            self.response_rates[room_id] = float(rate)

    def write(self):
        cfgparser = ConfigParser()
        cfgparser.add_section('General')
        cfgparser.set('General', 'default response rate',
                      str(self.default_response_rate))
        cfgparser.set('General', '# Valid backends are "markov" and "megahal"')
        cfgparser.set('General', 'backend', self.backend)
        cfgparser.set('General', 'display name', self.display_name)
        cfgparser.add_section('Login')
        cfgparser.set('Login', 'username', self.username)
        cfgparser.set('Login', 'password', self.password)
        cfgparser.set('Login', 'server', self.server)
        cfgparser.add_section('Response Rates')
        for room_id, rate in self.response_rates.items():
            # censor colons because they are a configparser special
            # character
            room_id = room_id.replace(':', '-colon-')
            cfgparser.set('Response Rates', room_id, str(rate))
        with open('config.cfg', 'wt') as configfile:
            cfgparser.write(configfile)


def get_room(client, event):
    return client.rooms[event['room_id']]


def handle_command(config, client, event, command, args):
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
                config.response_rates[room.room_id] = rate
                reply(client, event,
                      "Response rate set to %f." % rate)
            except ValueError:
                reply(client, event,
                      "Error: Could not parse number.")
        else:
            room = get_room(client, event)
            rate = get_response_rate(config, room)
            reply(client, event,
                  "Response rate set to %f in this room." % rate)



def get_default_configparser():
    config = ConfigParser(allow_no_value=True)
    config.add_section('General')
    config.set('General', 'default response rate', "0.10")
    config.set('General', '# Valid backends are "markov" and "megahal"')
    config.set('General', 'backend', 'markov')
    config.set('General', 'display name', 'Markov')
    config.add_section('Login')
    config.set('Login', 'username', 'username')
    config.set('Login', 'password', 'password')
    config.set('Login', 'server', 'http://matrix.org')
    config.add_section('Response Rates')
    return config


def reply(client, event, message):
    room = get_room(client, event)
    print("Reply: %s" % message)
    room.send_text(message.encode('ascii', errors='ignore'))


def get_name(sc):
    reply = sc.api_call("auth.test")
    data = json.loads(reply.decode('utf-8'))
    return data['user']


def get_response_rate(config, room):
    if room.room_id in config.response_rates:
        return config.response_rates[room.room_id]
    else:
        return config.default_response_rate


def handle_event(event, client, backend, config):
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
                    handle_command(config, client, event, args[0], args[1:])
                    break
            if not command_found:
                room = get_room(client, event)
                if config.username in message or \
                        config.display_name.lower() in message or \
                        random.random() < get_response_rate(config, room):
                    response = backend.reply(message)
                    time.sleep(3)
                    reply(client, event, response)
                backend.learn(message)


def train(backend, train_file):
    print("Training...")
    backend.train_file(train_file)
    print("Training complete!")
    backend.save()


def run(config, backend):
    client = MatrixClient(config.server)
    token = client.login_with_password(config.username, config.password)

    def callback(event):
        handle_event(event, client, backend, config)

    client.add_listener(callback)

    current_display_name = client.api.get_display_name(client.user_id)
    if current_display_name != config.display_name:
        client.api.set_display_name(client.user_id, config.display_name)

    last_save = time.time()

    while True:
        client.listen_for_events()
        # save every 10 minutes or so
        if time.time() - last_save > 60 * 10:
            backend.save()
            last_save = time.time()


def main():
    global debug
    cfgparser = ConfigParser()
    success = cfgparser.read('config.cfg')
    if not success:
        cfgparser = get_default_configparser()
        with open('config.cfg', 'wt') as configfile:
            cfgparser.write(configfile)
        print("A config has been generated. "
              "Please set your bot's username, password, and homeserver "
              "in config.cfg, then run this again.")
        return

    config = Config(cfgparser)

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
    backend = backends[config.backend]()
    backend.load_brain()

    if train_file:
        train(backend, train_file)
    else:
        while True:
            try:
                run(config, backend)
            except (MatrixRequestError, ConnectionError):
                print("Warning: disconnected. Waiting a minute to see if"
                        " the problem resolves itself...")
                time.sleep(60)
            finally:
                backend.save()
                print('Saving config...')
                config.write()


if __name__ == '__main__':
    main()
