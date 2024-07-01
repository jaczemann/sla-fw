# This file is part of the SLA firmware
# Copyright (C) 2014-2018 Futur3d - www.futur3d.net
# Copyright (C) 2018-2019 Prusa Research s.r.o. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

# TODO: Fix following pylint problems
# pylint: disable=too-many-branches
# pylint: disable=too-few-public-methods

import logging
import configparser
import re
from typing import Optional

from slafw import defines
from slafw.slicer.slicer_profile import SlicerProfile


class ProfileParser:

    def __init__(self, printer_type_name: str):
        self.logger = logging.getLogger(__name__)
        self.printer_type_name = printer_type_name
        self.config: Optional[configparser.ConfigParser] = None

    @staticmethod
    def _convert(val: str):
        """
        'smart' value conversion
        """
        # TODO split on "," and handle as list of values
        try:
            val = int(val)  # type: ignore
        except ValueError:
            try:
                val = float(val)  # type: ignore
            except ValueError:
                pass
        return val


    def _inherit(self, section: str) -> dict:
        tmp = {}
        inherits = self.config[section].get('inherits', None)
        if inherits:
            section_type = section.split(":")[0]
            items = inherits.split(";")
            for item in reversed(items):    # generic section is last one
                item = item.strip()
                parent = f"{section_type}:{item}"
                #self.logger.debug("'%s' inherits from '%s'", section, parent)
                tmp.update(self._inherit(parent))   # "recursion": see "recursion" ;-)
        for key in self.config[section]:
            if key == 'inherits':
                continue
            tmp[key] = self._convert(self.config[section][key])
        return tmp


    def _condition(self, condition: str, compact: bool, find_in: dict) -> bool:
        # TODO need to be improved for non SLA printers
        result = True
        if compact:
            tests = list((condition,))
        else:
            tests = condition.split(" ")
        for test in tests:
            pt = test.split("==")
            if len(pt) > 1:
                key = pt[0].strip()
                val = self._convert(pt[1].strip())
                if find_in.get(key, None) != val:
                    #self.logger.debug("False comparsion '%s' in '%s'", val, key)
                    result = False
                    break
                continue
            pt = test.split("=~")
            if len(pt) > 1:
                key = pt[0].strip()
                val = pt[1].strip(" /")
                if not re.search(val, find_in.get(key, "")):
                    #self.logger.debug("False regex '%s' in '%s'", val, key)
                    result = False
                    break
                continue
            if test == "and":
                continue
            self.logger.debug("Unknown test '%s', failing whole condition", test)
            result = False
            break
        return result


    def parse(self, filename: str):
        self.config = configparser.ConfigParser(comment_prefixes=("#",), interpolation=None)
        try:
            self.config.read(filename)
        except Exception:
            self.logger.exception("Error when parsing ini file:")
            self.logger.error("Slicer profiles failed to load")
            return None

        # collect all data from parents
        tmp = {}
        for section in self.config.sections():
            if section.find("*") < 0:
                tmp[section] = self._inherit(section)

        # find printer
        printer = None
        for key, value in tmp.items():
            if value.get('printer_technology', None) != "SLA":
                continue
            printerName = key.split(":")[1]
            self.logger.info("Found SLA technology printer '%s'", printerName)
            if value.get('printer_model', None) != self.printer_type_name or value.get('printer_variant', None) != defines.printerVariant:
                self.logger.debug("SLA printer '%s' not match printer model or printer variant", key)
                continue
            printer = value
            printer['name'] = printerName
            break

        if not printer:
            self.logger.info("No suitable printer found in slicer profiles")
            return None

        # find print settings
        printer['sla_print_profiles'] = {}
        for key, value in tmp.items():
            condition1 = value.get('compatible_printers_condition', None)
            condition2 = value.get('compatible_prints_condition', None)
            if condition1 and not condition2 and self._condition(condition1, False, printer):
                settings = key.split(":")[1]
                self.logger.info("Found print profile '%s'", settings)
                value['sla_material_profiles'] = {}
                del value['compatible_printers_condition']
                printer['sla_print_profiles'][settings] = value

        if not printer['sla_print_profiles']:
            self.logger.info("No suitable print profiles found in slicer profiles")
            return None

        # find materials
        for key, value in tmp.items():
            condition1 = value.get('compatible_printers_condition', None)
            condition2 = value.get('compatible_prints_condition', None)
            if condition1 and condition2 and self._condition(condition1, False, printer):
                for setting in printer['sla_print_profiles']:
                    if self._condition(condition2, True, printer['sla_print_profiles'][setting]):
                        material = key.split(":")[1]
                        self.logger.info("Found material profile '%s' for print profile '%s'", material, setting)
                        del value['compatible_printers_condition']
                        del value['compatible_prints_condition']
                        printer['sla_print_profiles'][setting]['sla_material_profiles'][material] = value

        profile = SlicerProfile()
        profile.printer = printer

        # vendor section
        profile.vendor = tmp.get('vendor', {})

        return profile
