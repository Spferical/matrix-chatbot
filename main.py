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
            line += u' '.join(u"{} {}".format(word, followers[word]) for
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

    def get_random_next_link(self, word1, word2):
        if (word1, word2) not in self.brain:
            return None

        possibilities = self.brain[(word1, word2)]
        total = 0
        for p in possibilities:
            total += possibilities[p]

        num = random.randint(1, total)
        total = 0
        for p in possibilities:
            total += possibilities[p]
            if total >= num:
                break
        return p

    def reply(self, message):
        seed = None
        # try to seed reply from the message
        possible_seed_words = message.split()
        while seed is None and possible_seed_words:
            message_word = random.choice(possible_seed_words)
            seeds = [key for key in self.brain.keys()
                     if message_word.lower() in (word.lower() for word in key)]
            if seeds:
                seed = random.choice(seeds)
            else:
                possible_seed_words.remove(message_word)

        # we couldn't seed the reply from the input
        # fall back to random seed
        if seed is None:
            seed = random.choice(self.brain.keys())

        words = list(seed)
        while (words[-2], words[-1]) in self.brain and len(words) < 100:
            word = self.get_random_next_link(words[-2], words[-1])
            words.append(word)
        return ' '.join(words)


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
        self.learning = cfgparser.getboolean('General', 'learning')
        self.username = cfgparser.get('Login', 'username')
        self.password = cfgparser.get('Login', 'password')
        self.server = cfgparser.get('Login', 'server')
        self.default_response_rate = cfgparser.getfloat(
            'General', 'default response rate')
        self.response_rates = {}
        for room_id, rate in cfgparser.items('Response Rates'):
            room_id = room_id.replace('-colon-', ':')
            self.response_rates[room_id] = float(rate)

    def get_response_rate(self, room_id):
        if room_id in self.response_rates:
            return self.response_rates[room_id]
        else:
            return self.default_response_rate

    def write(self):
        cfgparser = ConfigParser()
        cfgparser.add_section('General')
        cfgparser.set('General', 'default response rate',
                      str(self.default_response_rate))
        cfgparser.set('General', '# Valid backends are "markov" and "megahal"')
        cfgparser.set('General', 'backend', self.backend)
        cfgparser.set('General', 'display name', self.display_name)
        cfgparser.set('General', 'learning', self.learning)
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


def get_default_configparser():
    config = ConfigParser(allow_no_value=True)
    config.add_section('General')
    config.set('General', 'default response rate', "0.10")
    config.set('General', '# Valid backends are "markov" and "megahal"')
    config.set('General', 'backend', 'markov')
    config.set('General', 'display name', 'Markov')
    config.set('General', 'learning', True)
    config.add_section('Login')
    config.set('Login', 'username', 'username')
    config.set('Login', 'password', 'password')
    config.set('Login', 'server', 'http://matrix.org')
    config.add_section('Response Rates')
    return config


class Bot(object):
    def __init__(self, config, chat_backend):
        client = MatrixClient(config.server)
        client.login_with_password(config.username, config.password)

        self.config = config
        self.client = client
        self.chat_backend = chat_backend
        self.message_queued = None
        self.room_id_queued = None

    def get_room(self, event):
        return self.client.rooms[event['room_id']]

    def queue_reply(self, event, message):
        self.message_queued = message
        self.room_id_queued = event['room_id']

    def handle_command(self, event, command, args):
        command = command.lower()
        if command == '!rate':
            if args:
                try:
                    num = re.match(r'[0-9]*(\.[0-9]+)?(%|)', args[0]).group()
                    if not num:
                        self.reply(event, "Error: Could not parse number.")
                        return
                    if num[-1] == '%':
                        rate = float(num[:-1]) / 100
                    else:
                        rate = float(num)
                    self.config.response_rates[event['room_id']] = rate
                    self.reply(event, "Response rate set to %f." % rate)
                except ValueError:
                    reply(client, event, "Error: Could not parse number.")
            else:
                rate = self.config.get_response_rate(event['room_id'])
                self.reply(
                    event, "Response rate set to %f in this room." % rate)

    def reply(self, event, message):
        room = self.get_room(event)
        print("Reply: %s" % message)
        room.send_text(message.encode('ascii', errors='ignore'))

    def is_name_in_message(self, message):
        regex = "({}|{})".format(
            self.config.display_name, self.config.username)
        return re.match(regex, message, flags=re.IGNORECASE)

    def handle_event(self, event):
        # join rooms if invited
        if event['type'] == 'm.room.member':
            if 'content' in event and 'membership' in event['content']:
                if event['content']['membership'] == 'invite':
                    room = event['room_id']
                    self.client.join_room(room)
                    print('Joined room ' + room)
        elif event['type'] == 'm.room.message':
            # only care about text messages by other people
            if event['user_id'] != self.client.user_id and \
                    event['content']['msgtype'] == 'm.text':
                message = unicode(event['content']['body'])
                # lowercase message so we can search it
                # case-insensitively
                print("Handling message: %s" % message)
                command_found = False
                for command in COMMANDS:
                    match = re.search(command, message, flags=re.IGNORECASE)
                    if match and (match.start() == 0 or
                                  self.is_name_in_message(message)):
                        command_found = True
                        args = message[match.start():].split(' ')
                        self.handle_command(event, args[0], args[1:])
                        break
                if not command_found:
                    room = self.get_room(event)
                    response_rate = self.config.get_response_rate(room)
                    if self.is_name_in_message(message) or \
                            random.random() < response_rate:
                        response = self.chat_backend.reply(message)
                        self.queue_reply(event, response)
                    if self.config.learning:
                        self.chat_backend.learn(message)

    def run(self):
        self.client.add_listener(self.handle_event)

        current_display_name = self.client.api.get_display_name(
                self.client.user_id)
        if current_display_name != self.config.display_name:
            self.client.api.set_display_name(
                    self.client.user_id, self.config.display_name)

        last_save = time.time()

        self.client.start_listener_thread()

        while True:
            time.sleep(1)
            if self.message_queued:
                room = self.client.rooms[self.room_id_queued]
                print("Sending message: " + self.message_queued)
                room.send_text(self.message_queued)
                self.room_id_queued = self.message_queued = None
            # save every 10 minutes or so
            if time.time() - last_save > 60 * 10:
                self.chat_backend.save()
                last_save = time.time()


def train(backend, train_file):
    print("Training...")
    backend.train_file(train_file)
    print("Training complete!")
    backend.save()


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
                Bot(config, backend).run()
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
