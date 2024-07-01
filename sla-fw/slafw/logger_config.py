# This file is part of the SLA firmware
# Copyright (C) 2014-2018 Futur3d - www.futur3d.net
# Copyright (C) 2018-2019 Prusa Research s.r.o. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

import json
import logging
from logging.config import dictConfig
from typing import Dict

from slafw import defines
from slafw.errors.errors import FailedToSetLogLevel

def default_config(name: str) -> Dict:
    return {
        "version": 1,
        "formatters": {name: {"format": "%(levelname)s - %(name)s - %(message)s"}},
        "handlers": {
            "journald": {"class": "systemd.journal.JournalHandler", "formatter": name, "SYSLOG_IDENTIFIER": name.upper()}
        },
        "root": {"level": "INFO", "handlers": ["journald"]},
    }

def _get_config(name: str) -> Dict:
    filename = f"{name}-logger.json"
    config_file = defines.configDir / filename
    with config_file.open("r") as f:
        return json.load(f)


def configure_log(name: str) -> bool:
    """
    Configure logger according to configuration file or hardcoded config

    :return: True if configuration file was used, False otherwise
    """
    try:
        dictConfig(_get_config(name))
        return True
    except Exception:
        dictConfig(default_config(name))
        return False


def get_log_level(name: str) -> int:
    """
    Get current loglevel from configuration file

    :return: Current loglevel as LogLevel
    """
    try:
        config = _get_config(name)
    except Exception:
        config = default_config(name)
    raw_level = config["root"]["level"]
    return logging.getLevelName(raw_level)


def _set_config(name: str, config: Dict, level: int, persistent: bool):
    try:
        config["root"]["level"] = logging.getLevelName(level)
        # Setting level to root logger changes all loggers (in the same process)
        logging.getLogger().setLevel(level)

        if persistent:
            filename = f"{name}-logger.json"
            config_file = defines.configDir / filename
            with config_file.open("w") as f:
                json.dump(config, f)
    except Exception as exception:
        raise FailedToSetLogLevel from exception


def set_log_level(level: int, name: str, persistent=True) -> bool:
    """
    Set log level to configuration file and runtime

    :param level: LogLevel to set
    :param persistent: True to set persisten configuration, False to set transient/runtime configuration
    :return: True if config file was used as a base, False otherwise
    """
    try:
        config = _get_config(name)
        base_used = True
    except Exception:
        config = default_config(name)
        base_used = False

    _set_config(name, config, level, persistent)
    return base_used
