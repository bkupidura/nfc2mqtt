import logging
import sys
import os
import yaml
import random
import string

def create_logger(config=None):
    level_name = {
        'info': logging.INFO,
        'debug': logging.DEBUG,
        'error': logging.ERROR,
        'fatal': logging.FATAL,
    }

    logging_level = level_name.get(config.get('level', 'info'))

    logging_formatter = '%(asctime)s - %(levelname)s - %(name)s - %(message)s'

    logger = logging.getLogger()
    formatter = logging.Formatter(logging_formatter)

    logger.setLevel(logging_level)

    handler = logging.StreamHandler(sys.stdout)

    handler.setFormatter(formatter)
    logger.addHandler(handler)

def load_config(config_name):
    if not os.path.isfile(config_name):
        raise KeyError('Config {} is missing'.format(config_name))

    with open(config_name) as yaml_config:
        config = yaml.load(yaml_config, Loader=yaml.FullLoader)

    if config is None:
        config = dict()
    return config

def gen_random_string(chars=string.ascii_letters+string.digits, length=5):
    return ''.join(random.choice(chars) for i in range(length))
