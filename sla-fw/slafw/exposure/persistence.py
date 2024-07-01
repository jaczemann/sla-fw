# This file is part of the SLA firmware
# Copyright (C) 2021 Prusa Development a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

import logging
import json
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime

from slafw import defines
from slafw.exposure.exposure import Exposure
from slafw.functions.files import remove_files
from slafw.states.exposure import ExposureState
from slafw.wizard.data_package import WizardDataPackage


LAST_PROJECT_DATA = defines.previousPrints / "last_project.json"


class ExposurePickler:
    def __init__(self, package: WizardDataPackage):
        self._logger = logging.getLogger(__name__)
        self.package = package

    def save(self, exposure: Exposure, filename: Optional[Path] = None) -> None:
        if filename is None:
            filename = LAST_PROJECT_DATA
        self._logger.debug("Saving exposure %d data to '%s'", exposure.data.instance_id, str(filename))
        try:
            data: Dict[str, Any] = {}
            for key, val in exposure.persistent_data.items():
                if isinstance(val, datetime):
                    data["datetime:" + key] = val.timestamp()
                elif isinstance(val, ExposureState):
                    data["ExposureState:" + key] = val.value
                else:
                    data[key] = val
            data["project"] = exposure.project.persistent_data
            with filename.open("w") as file:
                file.write(json.dumps(data, indent=2, sort_keys=True))
        except Exception:
            self._logger.exception("Failed to save exposure:")


    def load(self, filename: Optional[Path] = None, instance_id = 0) -> Optional[Exposure]:
        if filename is None:
            filename = LAST_PROJECT_DATA
        self._logger.debug("Loading exposure data from '%s'", str(filename))
        try:
            with filename.open("r") as file:
                data = json.load(file)
            exposure = Exposure(instance_id, self.package)
            exposure.read_project(data["project"]["path"])
            exposure.project.persistent_data = data.pop("project")
            newdata: Dict[str, Any] = {}
            for key, val in data.items():
                if key.startswith("datetime:"):
                    newdata[key[9:]] = datetime.utcfromtimestamp(val)
                elif key.startswith("ExposureState:"):
                    newdata[key[14:]] = ExposureState(val)
                else:
                    newdata[key] = val
            exposure.persistent_data = newdata
            return exposure
        except FileNotFoundError:
            self._logger.info("No saved exposure")
        except Exception:
            self._logger.exception("Failed to load exposure:")
        return None


    def cleanup_last_data(self) -> None:
        remove_files(self._logger, [LAST_PROJECT_DATA,])
