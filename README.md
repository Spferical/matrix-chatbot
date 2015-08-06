# matrix-megahal

Matrix-megahal connects to a Matrix (Matrix.org) server and responds to messages at a configurable rate by connecting to megabot through its python bindings.

It automatically joins any rooms it is invited to and replies to any messages containing its username.

## Requirements
- matrix-client
- megahal

## Usage

`$ python main.py`

The first time you run it, a config file will be generated for you to edit as needed.

You may also want to "train" your megabot instance with a megabot.trn file.
