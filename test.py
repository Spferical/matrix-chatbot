import unittest

from main import MarkovBackend


class TestMarkov(unittest.TestCase):

    def setUp(self):
        self.markov = MarkovBackend()
        self.markov.learn("1 2 3 4 5 6 7 8 9 10")
        self.markov.learn("ALL CAPS IS GREAT")

    def test_reply_seeding(self):
        # basic seeding
        for x in range(1, 10):
            reply = self.markov.reply(str(x))
            reply_words = reply.split()

            # reply should be seeded with the input
            self.assertIn(str(x), reply_words[:2])

        # should be case insensitive
        reply = self.markov.reply("all")
        self.assertIn("ALL", reply.split())


if __name__ == '__main__':
    unittest.main()
