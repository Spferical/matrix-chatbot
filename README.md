# matrix-chatbot

Matrix-chatbot connects to a Matrix (Matrix.org) server and responds to messages at a configurable reponse rate.

It automatically joins any rooms it is invited to and replies to any messages containing its username.

Its response rate per-room may be configured by issuing a `!rate` command to the bot in that room. To tell the bot to reply to about a tenth of messages, message `!rate 0.1`.

Its response rate may be queried by messaging `!rate` without any arguments.

## Requirements
- Python v2.7
- matrix-client
- SQLAlchemy v1.1.4

`pip install -r requirements.txt`

## Usage

`$ python main.py`

The first time you run it, a config file will be generated for you to edit as needed.

You may also "train" your bot with a UTF-8 text file before you run it. This can be done with
`$ python main.py --train trainfile.txt`

## Docker

A dockerfile is also provided for running in docker.

To build the image locally and run the chatbot:

```
$ docker build . -t matrix-chatbot
$ docker run -it -v /host/data/path/:/matrixbot/data/ matrix-chatbot
A config has been generated. Please set your bot's username, password, and homeserver in /host/data/path/config.cfg then run this again.
$ vim /host/data/path/config.cfg
$ docker run -d -v /host/data/path/:/matrixbot/data/ matrix-chatbot
```
