import os
import unittest
import tempfile

import main


class TestMarkov(unittest.TestCase):

    def setUp(self):
        temp = tempfile.NamedTemporaryFile(delete=False)
        self.tempfile_path = temp.name
        temp.close()
        self.markov = main.MarkovBackend(self.tempfile_path)
        self.markov.learn("1 2 3 4 5 6 7 8 9 10")
        self.markov.learn("ALL CAPS IS GREAT")

    def tearDown(self):
        del self.markov
        os.remove(self.tempfile_path)

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
        self.markov.learn('Test that first and second are '
                          '\n\nap\n\npro\nximately\n\r\n')
        self.assertEqual(
            self.markov.brain.get_followers(('second', 'are')),
            {'approximately': 1})

    def test_is_name_in_message(self):
        configparser = main.get_default_configparser()
        configparser.set('General', 'display name', 'DisplayName')
        config = main.Config(configparser)
        bot = main.Bot(config, main.Backend(""))

        self.assertTrue(bot.is_name_in_message("displayName?"))
        self.assertTrue(bot.is_name_in_message("what up displayName? sdf"))
        self.assertFalse(bot.is_name_in_message("what up d1spl@yName"))
        config.display_name = "Eldie"
        self.assertTrue(bot.is_name_in_message("eldie?"))
        self.assertTrue(bot.is_name_in_message("what up eldie?"))
        self.assertFalse(bot.is_name_in_message(''))


if __name__ == '__main__':
    unittest.main()
