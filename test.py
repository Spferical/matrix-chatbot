import unittest

import main


class TestMarkov(unittest.TestCase):

    def setUp(self):
        self.markov = main.MarkovBackend()
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

    def test_brain(self):
        self.markov.load_brain_line(u'I have a 1 the 2 smores 3 potatoes 1')
        self.assertEqual(
            self.markov.brain.get_followers((u'I', u'have')),
            {u'a': 1, u'the': 2, u'smores': 3, u'potatoes': 1})

        self.markov.load_brain_line(u'What the what 1')
        self.assertEqual(
            self.markov.brain.get_followers((u'What', u'the')),
            {u'what': 1})

        self.markov.learn(u'Test that first and second are '
                          '\n\nap\n\npro\nximately\n\r\n')
        self.assertEqual(
            self.markov.brain.get_followers((u'second', u'are')),
            {u'approximately': 1})

    def test_is_name_in_message(self):
        configparser = main.get_default_configparser()
        configparser.set('General', 'display name', 'DisplayName')
        config = main.Config(configparser)
        bot = main.Bot(config, main.Backend())

        self.assertTrue(bot.is_name_in_message("displayName?"))
        self.assertTrue(bot.is_name_in_message("what up displayName? sdf"))
        self.assertFalse(bot.is_name_in_message("what up d1spl@yName"))
        config.display_name = "Eldie"
        self.assertTrue(bot.is_name_in_message("eldie?"))
        self.assertTrue(bot.is_name_in_message("what up eldie?"))
        self.assertFalse(bot.is_name_in_message(''))

    def test_saving(self):
        lines = self.markov.get_save_brain_lines()
        markov2 = main.MarkovBackend()
        for line in lines:
            markov2.load_brain_line(line)
        self.assertEqual(dict(markov2.brain.get_pairs_and_followers()),
                         dict(self.markov.brain.get_pairs_and_followers()))


if __name__ == '__main__':
    unittest.main()
