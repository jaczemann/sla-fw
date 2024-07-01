# This file is part of the SLA firmware
# Copyright (C) 2014-2018 Futur3d - www.futur3d.net
# Copyright (C) 2018-2019 Prusa Research s.r.o. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

from io import IOBase
from queue import Queue
from typing import Optional


class QueueStream(IOBase):
    def __init__(self, timeout_sec = None):
        super().__init__()
        self._queue = Queue()
        self._timeout_sec = timeout_sec

    def read(self, size: int = 1) -> Optional[bytes]:
        ret = b''
        for _ in range(size):
            ret += self._queue.get(timeout=self._timeout_sec)
        return ret

    def put(self, data: bytes) -> None:
        for b in data:
            self._queue.put(bytes([b]))

    def waiting(self) -> bool:
        return bool(self._queue.qsize())
