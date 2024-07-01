# This file is part of the SLA firmware
# Copyright (C) 2014-2018 Futur3d - www.futur3d.net
# Copyright (C) 2018-2019 Prusa Research s.r.o. - www.prusa3d.com
# Copyright (C) 2020-2022 Prusa Development a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

import re
import toml

from slafw.configs.value import BoolValue, ListValue, TextValue
from slafw.configs.common import ValueConfigCommon
from slafw.errors.errors import ConfigException


class IniConfig(ValueConfigCommon):
    """
    Main config class based on INI/TOML files.

    Inherit this to create a INI/TOML configuration

    For details see TOML format specification: https://en.wikipedia.org/wiki/TOML

    Currently the content is parsed using a TOML parser with preprocessor that adjusts older custom configuration format
    if necessary.
    """

    VAR_ASSIGN_PATTERN = re.compile(r"(?P<name>\w+) *= *(?P<value>.+)")
    COMMENT_PATTERN = re.compile(r"#.*")
    ON_YES_PATTERN = re.compile(r"^(on|yes)$")
    OFF_NO_PATTERN = re.compile(r"^(off|no)$")
    NUM_LIST_ONLY = re.compile(r"\A([0-9.-]+ +)+[0-9.-]+\Z")
    NUM_SEP = re.compile(r"\s+")

    # match string whit is not true, false, number or valid string in ""
    # the structure is: EQUALS ANYTHING(but not "true",..) END
    # ANYTHING is (.+) preceded by negative lookahead
    # END is (?=\n|$) - positive lookahead, we want \n or $ to follow
    STRING_PATTERN = re.compile(
        r"\A(?!"  # NL(negative lookahead) in form (...|...|...)
        r"\Atrue\Z|"  # NL part1 - true and end of the line or input
        r"\Afalse\Z|"  # NL part2 - false and end of the line or input
        r"\A[0-9.-]+\Z|"  # NL part3 - number at end of the line or input
        r'\A".*"\Z|'  # NL part4 - string already contained in ""
        r"\A\[ *(?:[0-9.-]+ *, *)+[0-9.-]+ *,? *]\Z"  # NL part4 - number list already in []
        r")"  # end of NL
        r"(.+)\Z"  # the matched string + positive lookahead for end
    )
    SURE_STRING_PATTERN = re.compile(
        r"\A(?!"  # NL(negative lookahead) in form (...|...|...)
        r'\A".*"\Z|'  # NL part4 - string already contained in ""
        r"\A\[ *(?:[0-9.-]+ *, *)+[0-9.-]+ *,? *]\Z"  # NL part4 - number list already in []
        r")"  # end of NL
        r"(.+)\Z"  # the matched string + positive lookahead for end
    )

    def read_text(self, text: str, factory: bool = False, defaults: bool = False) -> None:
        # Drop inconsistent newlines, use \n
        text = self._normalize_text(text)
        try:
            data = toml.loads(text)
        except toml.TomlDecodeError as exception:
            raise ConfigException(f"Failed to decode config content:\n {text}") from exception
        self._fill_from_dict(self, self._values.values(), data, factory, defaults)

    def _normalize_text(self, text: str) -> str:
        """
        Normalize config text

        - Normalize newlines
        - Fix old config format to toml

        :param text: Raw config text
        :return: TOML compatible config text
        """
        text = text.replace("\r\n", "\n").replace("\r", "\n")

        # Split config to lines, process each line separately
        lines = []
        for line in text.split("\n"):
            # Drop empty lines and comments
            line = line.strip()
            if not line or self.COMMENT_PATTERN.match(line):
                continue

            # Split line to variable name and value
            match = self.VAR_ASSIGN_PATTERN.match(line)
            if not match:
                self._logger.warning("Line ignored as it does not match name=value pattern:\n%s", line)
                continue
            name = match.groupdict()["name"].strip()
            value = match.groupdict()["value"].strip()

            # Obtain possibly matching config value for type hints
            value_hint = None
            for val in self._values.values():
                if val.file_key == name:
                    value_hint = val
                elif val.file_key.lower() == name:
                    value_hint = val

            if isinstance(value_hint, BoolValue):
                # Substitute on, off, yes, no with true and false
                value = self.ON_YES_PATTERN.sub("true", value)
                value = self.OFF_NO_PATTERN.sub("false", value)
            elif isinstance(value_hint, ListValue) and self.NUM_LIST_ONLY.match(value):
                # Wrap number lists in [] and separate numbers by comma
                value = self.NUM_SEP.sub(r", ", value)
                value = f"[{value}]"
            elif isinstance(value_hint, TextValue):
                # Wrap strings in ""
                value = self.SURE_STRING_PATTERN.sub(r'"\1"', value)
            else:
                # This is an unknown value, lets guess

                # Substitute on, off, yes, no with true and false
                value = self.ON_YES_PATTERN.sub("true", value)
                value = self.OFF_NO_PATTERN.sub("false", value)

                # Wrap number lists in [] and separate numbers by comma
                if self.NUM_LIST_ONLY.match(value):
                    value = self.NUM_SEP.sub(r", ", value)
                    value = f"[{value}]"

                # Wrap possible strings in ""
                value = self.STRING_PATTERN.sub(r'"\1"', value)

            lines.append(f"{name} = {value}")
        return "\n".join(lines)

    def _dump_for_save(self, factory: bool = False, nondefault: bool = False) -> str:
        return toml.dumps(self.as_dictionary(nondefault=nondefault, factory=factory))
