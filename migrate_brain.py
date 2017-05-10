"""Migrates the brain from the text-based format previously used by this
project to SQLite."""
import argparse
import codecs
import os

import database


def load_brain(brain_file, dbbrain):
    # self.brain_file is a plaintext filepath.
    # each line begins with two words, to form the prefix.
    # After that, the line can have any number of pairs of 1 word and 1
    # positive integer following the prefix. These are the words that may
    # follow the prefix and their weight.
    # e.g. "the fox jumped 2 ran 3 ate 1 ..."
    with codecs.open(brain_file, encoding='utf8',
                     mode='r') as brainfile:
        for line in brainfile:
            load_brain_line(line, dbbrain)

    dbbrain.save()


def load_brain_line(line, dbbrain):
    words = line.rstrip().split(' ')
    followers = {}
    for i in range(2, len(words), 2):
        followers[words[i]] = int(words[i + 1])
    word_pair = tuple(words[0:2])
    for (follower, count) in followers.items():
        dbbrain.add(word_pair, follower, count=count, check_existing=False)


def main():
    argparser = argparse.ArgumentParser(
        description="Migration script to migrate the chatbot markov brain"
        "from the text-based format previously used by this project to SQLite")
    argparser.add_argument("text_brain", type=str,
                           help="The old, text-based brain file")
    argparser.add_argument("sqlite_brain", type=str,
                           help="Where to put the new SQLite brain")
    args = vars(argparser.parse_args())

    assert not os.path.exists(args['sqlite_brain'])
    dbbrain = database.MarkovDatabaseBrain(args['sqlite_brain'])
    old_brain_path = args['text_brain']
    load_brain(old_brain_path, dbbrain)


if __name__ == '__main__':
    main()
