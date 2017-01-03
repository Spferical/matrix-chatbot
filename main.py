from __future__ import print_function
import time
from matrix_client.client import MatrixClient
from matrix_client.api import MatrixRequestError
from requests.exceptions import ConnectionError
import argparse
import random
from ConfigParser import ConfigParser
import re
import tempfile
import shutil
import codecs
import traceback
import urllib
import threading
import logging
from itertools import islice
import os


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


class MarkovBrain(object):
    """Threadsafe wrapper around brain dictionary."""

    def __init__(self):
        self._data = {}
        self._mutex = threading.Lock()

    def set_followers(self, word_pair, followers):
        with self._mutex:
            self._data[word_pair] = followers

    def get_followers(self, word_pair):
        with self._mutex:
            return self._data.get(word_pair, [])

    def get_pairs(self):
        with self._mutex:
            for pair in self._data:
                yield pair

    def get_pairs_and_followers(self):
        with self._mutex:
            for item in self._data.items():
                yield item

    def contains_pair(self, word_pair):
        with self._mutex:
            return word_pair in self._data

    def add(self, word_pair, follower):
        with self._mutex:
            if word_pair in self._data:
                followers = self._data[word_pair]
                followers[follower] = followers.get(follower, 0) + 1
            else:
                self._data[word_pair] = {follower: 1}

    def __len__(self):
        return len(self._data)


class MarkovBackend(Backend):
    def __init__(self, brain_file):
        self.brain = MarkovBrain()
        self.brain_file = brain_file

    def load_brain(self):
        # self.brain_file is a plaintext filepath.
        # each line begins with two words, to form the prefix.
        # After that, the line can have any number of pairs of 1 word and 1
        # positive integer following the prefix. These are the words that may
        # follow the prefix and their weight.
        # e.g. "the fox jumped 2 ran 3 ate 1 ..."
        try:
            with codecs.open(self.brain_file, encoding='utf8',
                             mode='r') as brainfile:
                for line in brainfile:
                    self.load_brain_line(line)
        except IOError:
            self.brain = MarkovBrain()

    def load_brain_line(self, line):
        words = line.rstrip().split(' ')
        followers = {}
        for i in range(2, len(words), 2):
            followers[words[i]] = int(words[i + 1])
        self.brain.set_followers(tuple(words[0:2]), followers)

    def get_save_brain_lines(self):
        for pair, followers in self.brain.get_pairs_and_followers():
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
        return word.replace('\n', '').replace('\r', '').replace(u'\u2028', '')

    def learn(self, line):
        line = line.strip()
        words = line.split(' ')
        words = [self.sanitize(word) for word in words]
        for i in range(len(words) - 2):
            prefix = words[i], words[i + 1]
            follow = words[i + 2]
            self.brain.add(prefix, follow)

    def get_random_next_link(self, word1, word2):
        possibilities = self.brain.get_followers((word1, word2))
        if not possibilities:
            return None

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
        # can't reply with an empty brain
        if not self.brain:
            return ''

        seed = None
        # try to seed reply from the message
        possible_seed_words = message.split()
        while seed is None and possible_seed_words:
            message_word = random.choice(possible_seed_words)
            seeds = [key for key in self.brain.get_pairs()
                     if message_word.lower() in
                     (word.lower() for word in key)]
            if seeds:
                seed = random.choice(seeds)
            else:
                possible_seed_words.remove(message_word)

        # we couldn't seed the reply from the input
        # fall back to random seed
        if seed is None:
            num = random.randint(0, len(self.brain) - 1)

            def get_nth(generator, n):
                return next(islice(generator, n, n + 1))

            seed = get_nth(self.brain.get_pairs(), num)

        words = list(seed)
        while self.brain.contains_pair((words[-2], words[-1])) and \
                len(words) < 100:
            word = self.get_random_next_link(words[-2], words[-1])
            words.append(word)
        return ' '.join(words)


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
    config.set('General', 'backend', 'markov')
    config.set('General', 'display name', 'Markov')
    config.set('General', 'learning', 'on')
    config.add_section('Login')
    config.set('Login', 'username', 'username')
    config.set('Login', 'password', 'password')
    config.set('Login', 'server', 'http://matrix.org')
    config.add_section('Response Rates')
    return config


class Bot(object):
    def __init__(self, config, chat_backend):
        self.config = config
        self.client = None
        self.chat_backend = chat_backend
        self.message_queued = None
        self.room_id_queued = None

    def login(self):
        client = MatrixClient(self.config.server)
        client.login_with_password(self.config.username, self.config.password)
        self.client = client

    def get_room(self, event):
        return self.client.rooms[event['room_id']]

    def queue_reply(self, event, message):
        self.message_queued = message
        self.room_id_queued = event['room_id']

    def handle_command(self, event, command, args):
        command = command.lower()
        if command == '!rate':
            if args:
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
            else:
                rate = self.config.get_response_rate(event['room_id'])
                self.reply(
                    event, "Response rate set to %f in this room." % rate)

    def reply(self, event, message):
        room = self.get_room(event)
        logging.info("Reply: %s" % message)
        room.send_text(message.encode('ascii', errors='ignore'))

    def is_name_in_message(self, message):
        regex = "({}|{})".format(
            self.config.display_name, self.config.username)
        return re.search(regex, message, flags=re.IGNORECASE)

    def handle_event(self, event):
        # join rooms if invited
        if event['type'] == 'm.room.member':
            if 'content' in event and 'membership' in event['content']:
                if event['content']['membership'] == 'invite':
                    room = event['room_id']
                    self.client.join_room(room)
                    logging.info('Joined room ' + room)
        elif event['type'] == 'm.room.message':
            # only care about text messages by other people
            if event['user_id'] != self.client.user_id and \
                    event['content']['msgtype'] == 'm.text':
                message = unicode(event['content']['body'])
                # lowercase message so we can search it
                # case-insensitively
                logging.info("Handling message: %s" % message)
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
                    response_rate = self.config.get_response_rate(room.room_id)
                    if self.is_name_in_message(message) or \
                            random.random() < response_rate:
                        # remove name from message and respond to it
                        message_no_name = re.sub(
                            ' *' + re.escape(self.get_display_name()) + ' *',
                            ' ', message, flags=re.IGNORECASE)
                        response = self.chat_backend.reply(message_no_name)
                        self.queue_reply(event, response)
                    if self.config.learning:
                        self.chat_backend.learn(message)
        self.send_read_receipt(event)

    def set_display_name(self, display_name):
        body = {"displayname": display_name}
        return self.client.api._send(
            "PUT", "/profile/" + self.client.user_id + "/displayname", body)

    def get_display_name(self):
        response = self.client.api._send(
            "GET", "/profile/" + self.client.user_id + "/displayname")
        return response['displayname']

    def run(self):
        current_display_name = self.get_display_name()
        if current_display_name != self.config.display_name:
            self.set_display_name(self.config.display_name)

        last_save = time.time()

        # get rid of initial event sync
        logging.info("initial event stream")
        self.client.listen_for_events()

        # set the callback and start listening in a background thread
        self.client.add_listener(self.handle_event)

        # start listen thread
        logging.info("starting listener thread")
        thread = threading.Thread(target=self.client.listen_forever)
        thread.daemon = True
        thread.start()

        while True:
            time.sleep(1)
            # restart thread if dead
            if not thread.is_alive():
                thread = threading.Thread(target=self.client.listen_forever)
                thread.daemon = True
                thread.start()
            # send any queued messages
            if self.message_queued:
                room = self.client.rooms[self.room_id_queued]
                logging.info("Sending message: " + self.message_queued)
                room.send_text(self.message_queued)
                self.room_id_queued = self.message_queued = None
            # save every 10 minutes or so
            if time.time() - last_save > 60 * 10:
                self.chat_backend.save()
                last_save = time.time()

    def send_read_receipt(self, event):
        if "room_id" in event and "event_id" in event:
            room_id = urllib.quote(event['room_id'].encode('utf8'))
            event_id = urllib.quote(event['event_id'].encode('utf8'))
            self.client.api._send("POST", "/rooms/" + room_id +
                                  "/receipt/m.read/" + event_id,
                                  api_path="/_matrix/client/r0")


def train(backend, train_file):
    print("Training...")
    backend.train_file(train_file)
    print("Training complete!")
    backend.save()


def main():
    argparser = argparse.ArgumentParser(
        description="A chatbot for Matrix (matrix.org)")
    argparser.add_argument("--debug",
                           help="Print out way more things.",
                           action="store_true")
    argparser.add_argument("--train", metavar="train.txt", type=str,
                           help="Train the bot with a file of text.")
    argparser.add_argument("--config", metavar="config.cfg", type=str,
                           help="Bot's config file (must be read-writable)")
    argparser.add_argument("--brain", metavar="brain.txt", type=str,
                           help="Bot's config file (must be read-writable)")
    args = vars(argparser.parse_args())
    debug = args['debug']

    # suppress logs of libraries
    logging.getLogger("requests").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    log_level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(level=log_level,
                        format='%(asctime)s %(name)s '
                        '%(levelname)s %(message)s')

    train_path = args['train']

    config_path = args['config'] if args['config'] \
        else os.getenv('MATRIX_CHATBOT_CONFIG', 'config.cfg')
    brain_path = args['brain'] if args['brain'] \
        else os.getenv('MATRIX_CHATBOT_BRAIN', 'brain.txt')

    cfgparser = ConfigParser()
    success = cfgparser.read(config_path)
    if not success:
        cfgparser = get_default_configparser()
        with open(config_path, 'wt') as configfile:
            cfgparser.write(configfile)
        print("A config has been generated. "
              "Please set your bot's username, password, and homeserver "
              "in " + config_path + " then run this again.")
        return

    config = Config(cfgparser)

    backends = {'markov': MarkovBackend}
    backend = backends[config.backend](brain_path)
    logging.info("loading brain")
    backend.load_brain()

    if train_path:
        train(backend, train_path)
    else:
        while True:
            try:
                bot = Bot(config, backend)
                bot.login()
                bot.run()
            except (MatrixRequestError, ConnectionError):
                traceback.print_exc()
                logging.warning("disconnected. Waiting a minute to see if"
                                " the problem resolves itself...")
                time.sleep(60)
            finally:
                backend.save()
                logging.info('Saving config...')
                config.write()


if __name__ == '__main__':
    main()
