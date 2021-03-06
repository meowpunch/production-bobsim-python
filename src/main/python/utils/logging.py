import yaml
import logging
import logging.config

from utils.executable import get_destination


def init_logger(name='__main__'):
    config_path = 'config/logging.yaml'
    with open(get_destination(config_path)) as file:
        config = yaml.load(file, Loader=yaml.FullLoader)

    logging.config.dictConfig(config)
    return logging.getLogger(name)
