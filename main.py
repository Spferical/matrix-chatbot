from __future__ import print_function
import time
from slackclient import SlackClient
import mh_python as mh
import argparse
import random
from ConfigParser import ConfigParser
import re
import json


def get_default_config():
    config = ConfigParser()
    config.add_section('General')
    config.set('General', 'response rate', "0.10")
    return config


def write_config(config):
    with open('config.cfg', 'wt') as configfile:
        config.write(configfile)

def reply(sc, event, message):
    channel = event['channel']
    print("Reply: %s" % message)
    sc.rtm_send_message(channel, message)

def get_name(sc):
    reply = sc.api_call("auth.test")
    data = json.loads(reply.decode('utf-8'))
    return data['user']

def main():
    cfgparser = ConfigParser()
    success = cfgparser.read('config.cfg')
    if not success:
        cfgparser = get_default_config()
        write_config(cfgparser)
    response_rate = cfgparser.getfloat('General', 'response rate')
    argparser = argparse.ArgumentParser(
        description="Slack chatbot using MegaHAL")
    argparser.add_argument(
        "-t", "--token", type=str, help="Slack token", required=True)
    argparser.add_argument("--debug", help="Output raw events to help debug",
                           action="store_true")
    args = vars(argparser.parse_args())
    token = args['token']
    debug = args['debug']
    sc = SlackClient(token)
    mh.initbrain()
    try:
        if sc.rtm_connect():
            name = get_name(sc)
            print("Detected name: %s" % name)
            while True:
                for event in sc.rtm_read():
                    if debug:
                        print(event)
                    if 'type' in event and event['type'] == 'message' \
                            and 'text' in event:
                        message = event['text'].encode('ascii', 'ignore')
                        # lowercase message so we can search it
                        # case-insensitively
                        message = message.lower()
                        print("Handling message: %s" % message)
                        match = re.search(
                            "%s, set response rate to [0-9]{2}(%%|)" % name,
                            message)
                        if match:
                            words = match.group().split()
                            num = words[-1]
                            if num[-1] == '%':
                                rate = float(num[:-1]) / 100
                            else:
                                rate = float(num)
                            response_rate = rate
                            reply(sc, event, "Response rate set to %f" % rate)
                            time.sleep(1) # sleep to avoid rate limit
                        else:
                            match = re.search(
                                "%s, what is your response rate?" % name,
                                message)
                            if match:
                                reply(sc, event,
                                      "My response rate is set at %f."
                                      % response_rate)
                                time.sleep(1) # sleep to avoid rate limit
                            elif name in message or random.random() < response_rate:
                                response = mh.doreply(message)
                                reply(sc, event, response)
                                time.sleep(1) # sleep to avoid rate limit
                            else:
                                mh.learn(message)
                time.sleep(2)
        else:
            print("Connection Failed, invalid token?")
    finally:
        mh.cleanup()
        cfgparser.set('General', 'response rate', str(response_rate))
        print('Saving config...')
        write_config(cfgparser)

if __name__ == '__main__':
    main()
