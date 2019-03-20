#!/usr/bin/env python3
import time
from matrix_client.client import MatrixClient
from matrix_client.api import MatrixRequestError
from requests.exceptions import ConnectionError, Timeout
import argparse
import random
from configparser import ConfigParser
import re
import traceback
import urllib.parse
import logging
import os
import sys
import signal
import queue
import codecs
from database import MarkovDatabaseBrain

COMMANDS = [
    '!rate'
]


def sigterm_handler(_signo, _stack_frame):
    """Raises SystemExit(0), causing everything to cleanly shut down."""
    sys.exit(0)


class ConfigParser(ConfigParser):
    # allow case-sensitive option names
    # needed for saving per-room response rates
    optionxform = str


class Backend(object):
    """Interface for chat backends."""
    def __init__(self, brain_file):
        pass

    def train_file(self, filename):
        """Trains the chat backend on the given file."""
        with codecs.open(filename, encoding='utf8') as train_file:
            for line in train_file:
                self.learn(line)

    def learn(self, line):
        """Updates the chat backend based on the given line of input."""
        pass

    def save(self):
        """Saves the backend to disk, if needed."""
        pass

    def reply(self, message):
        """Generates a reply to the given message."""
        return "(dummy response)"


class MarkovBackend(Backend):
    """Chat backend using markov chains."""
    def __init__(self, brain_file):
        self.brain = MarkovDatabaseBrain(brain_file)

    def sanitize(self, word):
        """Removes any awkward whitespace characters from the given word.

        Removes '\n', '\r', and '\\u2028' (unicode newline character)."""
        return word.replace('\n', '').replace('\r', '').replace('\u2028', '')

    def train_file(self, filename):
        with codecs.open(filename, encoding='utf8') as train_file:
            for line in train_file:
                self.learn(line)
        self.save()

    def learn(self, line):
        line = line.strip()
        words = line.split(' ')
        words = [self.sanitize(word) for word in words]
        for i in range(len(words) - 2):
            prefix = words[i], words[i + 1]
            follow = words[i + 2]
            self.brain.add(prefix, follow)

    def save(self):
        self.brain.save()

    def get_random_next_link(self, word1, word2):
        """Gives a word that could come after the two provided.

        Words that follow the two given words are weighted by how frequently
        they appear after them.
        """
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
        if self.brain.is_empty():
            return ''

        seed = None
        # try to seed reply from the message
        possible_seed_words = message.split()
        while seed is None and possible_seed_words:
            message_word = random.choice(possible_seed_words)
            seeds = list(self.brain.get_pairs_containing_word_ignoring_case(
                    message_word))
            if seeds:
                seed = random.choice(seeds)
            else:
                possible_seed_words.remove(message_word)

        # we couldn't seed the reply from the input
        # fall back to random seed
        if seed is None:
            seed = self.brain.get_three_random_words()

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
        """Returns our response rate for the room with the given room id."""
        if room_id in self.response_rates:
            return self.response_rates[room_id]
        else:
            return self.default_response_rate

    def write(self):
        """Writes this config back to the file, with any changes reflected."""
        cfgparser = ConfigParser()
        cfgparser.add_section('General')
        cfgparser.set('General', 'default response rate',
                      str(self.default_response_rate))
        cfgparser.set('General', 'backend', self.backend)
        cfgparser.set('General', 'display name', self.display_name)
        cfgparser.set('General', 'learning', str(self.learning))
        cfgparser.add_section('Login')
        cfgparser.set('Login', 'username', self.username)
        cfgparser.set('Login', 'password', self.password)
        cfgparser.set('Login', 'server', self.server)
        cfgparser.add_section('Response Rates')
        for room_id, rate in list(self.response_rates.items()):
            # censor colons because they are a configparser special
            # character
            room_id = room_id.replace(':', '-colon-')
            cfgparser.set('Response Rates', room_id, str(rate))
        with open('config.cfg', 'wt') as configfile:
            cfgparser.write(configfile)


def get_default_configparser():
    """Returns a ConfigParser object for the default config file."""
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
    """Handles everything that the bot does."""
    def __init__(self, config, chat_backend):
        self.config = config
        self.client = None
        self.chat_backend = chat_backend
        self.event_queue = queue.Queue()
        self.invite_queue = queue.Queue()

    def login(self):
        """Logs onto the server."""
        client = MatrixClient(self.config.server)
        client.login_with_password_no_sync(
            self.config.username, self.config.password)
        self.client = client

    def get_room(self, event):
        """Returns the room the given event took place in."""
        return self.client.rooms[event['room_id']]

    def handle_command(self, event, command, args):
        """Handles the given command, possibly sending a reply to it."""
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
        """Replies to the given event with the provided message."""
        room = self.get_room(event)
        logging.info("Reply: %s" % message)
        room.send_notice(message)

    def is_name_in_message(self, message):
        """Returns whether the message contains the bot's name.

        Considers both display name and username.
        """
        regex = "({}|{})".format(
            self.config.display_name, self.config.username)
        return re.search(regex, message, flags=re.IGNORECASE)

    def handle_invite(self, room_id, invite_state):
        # join rooms if invited
        try:
            self.client.join_room(room_id)
            logging.info('Joined room: %s' % room_id)
        except MatrixRequestError as e:
            if e.code == 404:
                # room was deleted after invite or something; ignore it
                logging.info('invited to nonexistent room {}'.format(room_id))
            elif e.code in range(500, 600):
                # synapse v0.99.1 500s if it cannot locate a room sometimes
                # (when there are federation issues)
                logging.warning('got 500 trying to join room we were invited to')
            else:
                raise(e)

    def handle_event(self, event):
        """Handles the given event.

        Joins a room if invited, learns from messages, and possibly responds to
        messages.
        """
        if event['type'] == 'm.room.message':
            # only care about text messages by other people
            if event['sender'] != self.client.user_id and \
                    event['content']['msgtype'] == 'm.text':
                message = str(event['content']['body'])
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
                        self.reply(event, response)
                    if self.config.learning:
                        self.chat_backend.learn(message)
        self.send_read_receipt(event)

    def set_display_name(self, display_name):
        """Sets the bot's display name on the server."""
        self.client.api.set_display_name(self.client.user_id, display_name)

    def get_display_name(self):
        """Gets the bot's display name from the server."""
        return self.client.api.get_display_name(self.client.user_id)

    def run(self):
        """Indefinitely listens for messages and handles all that come."""
        current_display_name = self.get_display_name()
        if current_display_name != self.config.display_name:
            self.set_display_name(self.config.display_name)

        last_save = time.time()

        # listen for invites, including initial sync invites
        self.client.add_invite_listener(
            lambda room_id, state: self.invite_queue.put((room_id, state)))

        # get rid of initial event sync
        logging.info("initial event stream")
        self.client.listen_for_events()

        # listen to events and add them all to the event queue
        # for handling in this thread
        self.client.add_listener(self.event_queue.put)

        def exception_handler(e):
            if isinstance(e, Timeout):
                logging.warning("listener thread timed out.")
            logging.error("exception in listener thread:")
            traceback.print_exc()

        # start listen thread
        logging.info("starting listener thread")
        self.client.start_listener_thread(exception_handler=exception_handler)

        try:
            while True:
                time.sleep(1)

                # handle any queued events
                while not self.event_queue.empty():
                    event = self.event_queue.get_nowait()
                    self.handle_event(event)

                while not self.invite_queue.empty():
                    room_id, invite_state = self.invite_queue.get_nowait()
                    self.handle_invite(room_id, invite_state)

                # save every 10 minutes or so
                if time.time() - last_save > 60 * 10:
                    self.chat_backend.save()
                    last_save = time.time()
        finally:
            logging.info("stopping listener thread")
            self.client.stop_listener_thread()

    def send_read_receipt(self, event):
        """Sends a read receipt for the given event."""
        if "room_id" in event and "event_id" in event:
            room_id = urllib.parse.quote(event['room_id'])
            event_id = urllib.parse.quote(event['event_id'])
            self.client.api._send("POST", "/rooms/" + room_id +
                                  "/receipt/m.read/" + event_id,
                                  api_path="/_matrix/client/r0")


def train(backend, train_file):
    """Trains the given chat backend on the given train_file & saves it."""
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
    argparser.add_argument("--brain", metavar="brain.db", type=str,
                           help="Bot's brain file (must be read-writable)")
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
        else os.getenv('MATRIX_CHATBOT_BRAIN', 'brain.db')

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

    if train_path:
        train(backend, train_path)
    else:
        signal.signal(signal.SIGTERM, sigterm_handler)
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
