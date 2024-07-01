# This file is part of the SLA firmware
# Copyright (C) 2020 Prusa Research a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

import re
import unittest
from dataclasses import fields, is_dataclass
from glob import glob
from pathlib import Path

from gi.repository.GLib import Variant
from prusaerrors.sl1.codes import Sl1Codes

from slafw.api.devices import HardwareDeviceId
from slafw.errors.errors import PrinterException

import slafw
from slafw.api.decorators import wrap_dict_data
from slafw.errors.tests import FAKE_ARGS, get_classes, get_instance


class TestExceptions(unittest.TestCase):
    """
    This automatically tests exception instantiation and DBus wrapping

    Fake args are provided by FAKE_ARGS dictionary. Exceptions are instantiated and processed in the same way as if
    exported to DBus.
    """

    def test_instantiation(self):
        for name, cls in get_classes():
            print(f"Testing dbus wrapping for class: {name}")
            wrapped_exception = PrinterException.as_dict(get_instance(cls))
            wrapped_dict = wrap_dict_data(wrapped_exception)
            self.assertIsInstance(wrapped_dict, dict)
            for key, value in wrapped_dict.items():
                self.assertIsInstance(key, str)
                self.assertIsInstance(value, Variant)

    @staticmethod
    def test_string_substitution():
        for name, cls in get_classes():
            print(f"\nTesting string substitution for class: {name}.")

            instance = get_instance(cls)
            message = cls.CODE.message
            print(f'Source text:\n"{message}"')

            arguments = {}
            if is_dataclass(instance):
                for field in fields(instance):
                    if field.name.endswith("__map_HardwareDeviceId"):
                        # Sensor name is special. UI looks it up in an enum dictionary and translates name.
                        arguments[field.name] = HardwareDeviceId(FAKE_ARGS[field.name]).name
                    else:
                        arguments[field.name] = FAKE_ARGS[field.name]

            print(f"Arguments:{arguments}")

            # Note simplified processing in the UI does not have problems with standalone '%' character.
            substituted = re.sub(r"%(?!\()", "%%", message) % arguments
            print(f'Substituted text:\n"{substituted}"')

    def test_error_codes_dummy(self):
        """This is a stupid test that checks all attempts to use Sl1Codes.UNKNOWN likes are valid. Pylint cannot do
        this for us as Sl1Codes are runtime generated from Yaml source"""

        # This goes through all the source code looking for Sl1Codes usages and checks whenever these are legit.
        root = Path(slafw.__file__).parent
        sources = [Path(source) for source in glob(str(root / "**/*.py"), recursive=True)]
        code_pattern = re.compile(r"(?<=Sl1Codes\.)\w+")
        for source in sources:
            text = source.read_text()
            matches = code_pattern.findall(text)
            for match in matches:
                self.assertIn(match, dir(Sl1Codes))


if __name__ == "__main__":
    unittest.main()
