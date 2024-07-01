# This file is part of the SLA firmware
# Copyright (C) 2014-2018 Futur3d - www.futur3d.net
# Copyright (C) 2018-2019 Prusa Research s.r.o. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

from collections import deque
from enum import Enum
from typing import Deque


class LineMarker(Enum):
    INPUT = ">"
    GARBAGE = "|"
    OUTPUT = "<"
    RESET = "="

    def __str__(self) -> str:
        return str(self.value)

    def __bytes__(self) -> bytes:
        # pylint: disable=invalid-bytes-returned
        # pylint bug: https://github.com/PyCQA/pylint/issues/3599
        return self.__str__().encode("ascii")


class LineTrace:
    __slots__ = ['_line', '_marker', '_repeats']

    def __init__(self, marker, line: bytes):
        self._line = line
        self._marker = marker
        self._repeats = 1

    def __eq__(self, other):
        if not isinstance(other, self.__class__):
            return False
        return self._line == other._line and self._marker == other._marker

    def repeat(self):
        self._repeats += 1

    def __str__(self):
        if self._repeats > 1:
            return f"{self._repeats}x {self._marker.value} {self._line}"
        return f"{self._marker.value} {self._line}"

    def __bytes__(self) -> bytes:
        if self._repeats > 1:
            return f"{self._repeats}x {self._marker.value} {self._line}".encode('ascii')  # type: ignore
        return f"{self._marker.value} {self._line}".encode('ascii')  # type: ignore


class Trace:
    def __init__(self, size: int):
        self.traces: Deque[LineTrace] = deque(maxlen=size)

    def append_trace(self, current_trace: LineTrace):
        # < b'?mot\n' -3
        # > b'1 ok\n' -2
        # < b'?mot\n' -1
        # > b'1 ok\n' current_trace

        if len(self.traces) > 3 and self.traces[-3] == self.traces[-1] and self.traces[-2] == current_trace:
            self.traces[-3].repeat()
            self.traces[-2].repeat()
            del self.traces[-1]
        else:
            self.traces.append(current_trace)

    def __str__(self) -> str:
        """
        Get formatted motion controller command trace

        :return: Trace string
        """
        return f"last {len(self.traces)} lines:\n" + "\n".join([str(x) for x in self.traces])

    def __bytes__(self):
        return b"\n".join([bytes(x) for x in self.traces])
