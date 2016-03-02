"""For testing"""
import main
import unittest
import psutil


class TestMatrixChatbot(unittest.TestCase):
    def test_markov_backend(self):
        mb = main.MarkovBackend()

        mb.load_brain_line('I have a 1 the 2 smores 3 potatoes 1')
        self.assertEqual(
            mb.brain[('I', 'have')],
            {'a': 1, 'the': 2, 'smores': 3, 'potatoes': 1})

        mb.load_brain_line('What the what 1')
        self.assertEqual(
            mb.brain[('What', 'the')],
            {'what': 1})

        mb.learn('Test that first and second are \n\nap\n\npro\nximately\n\r\n')
        self.assertEqual(
            mb.brain[('second', 'are')],
            {'approximately': 1})

        lines = mb.get_save_brain_lines()
        mb2 = main.MarkovBackend()
        for line in lines:
            mb2.load_brain_line(line)
        self.assertEqual(mb2.brain, mb.brain)

if __name__ == '__main__':
    unittest.main()
