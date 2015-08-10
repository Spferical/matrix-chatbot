# matrix-chatbot

Matrix-chatbot connects to a Matrix (Matrix.org) server and responds to messages at a configurable reponse rate.

It automatically joins any rooms it is invited to and replies to any messages containing its username.

The bot supports multiple backends: 'markov', implemented with markov chains, and 'megahal', which conencts to MegaHAL using its Python bindings.

## Requirements
- matrix-client
- megahal (if using megahal backend)

## Usage

`$ python main.py`

The first time you run it, a config file will be generated for you to edit as needed.

You may also want to "train" your bot with a text file before you run it. This can be done with
`$ python main.py --train trainfile.txt`
