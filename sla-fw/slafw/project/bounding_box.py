# This file is part of the SLA firmware
# Copyright (C) 2020 Prusa Development a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

import logging


class BBox:
    def __init__(self, coords=None):
        self._logger = logging.getLogger(__name__)
        if not coords:
            coords = 1000000, 1000000, 0, 0
        elif len(coords) != 4 or coords[2] <= coords[0] or coords[3] <= coords[1] or coords[0] < 0 or coords[1] < 0:
            self._logger.error("coords %s are not a rectangle", str(coords))
            coords = 1000000, 1000000, 0, 0
        self.x1 = coords[0]
        self.y1 = coords[1]
        self.x2 = coords[2]
        self.y2 = coords[3]

    def __repr__(self):
        if self.__bool__():
            return f"({self.x1}, {self.y1}, {self.x2}, {self.y2})"
        return "None"

    def __bool__(self):
        size = self.size
        return size[0] > 0 and size[1] > 0

    def __eq__(self, other):
        return (
            isinstance(other, type(self))
            and self.x1 == other.x1
            and self.y1 == other.y1
            and self.x2 == other.x2
            and self.y2 == other.y2
        )

    def __sub__(self, other):
        return other.x1 - self.x1, other.y1 - self.y1, self.x2 - other.x2, self.y2 - other.y2

    @property
    def coords(self):
        return self.x1, self.y1, self.x2, self.y2

    @coords.setter
    def coords(self, coords):
        self.x1 = coords[0]
        self.y1 = coords[1]
        self.x2 = coords[2]
        self.y2 = coords[3]

    @property
    def size(self):
        size = self.x2 - self.x1, self.y2 - self.y1
        if size[0] > 0 and size[1] > 0:
            return size
        return 0, 0

    def maximize(self, bbox):
        if bbox.x1 < self.x1:
            self.x1 = bbox.x1
        if bbox.y1 < self.y1:
            self.y1 = bbox.y1
        if bbox.x2 > self.x2:
            self.x2 = bbox.x2
        if bbox.y2 > self.y2:
            self.y2 = bbox.y2

    def crop(self, bbox):
        if bbox.x1 > self.x1:
            self.x1 = bbox.x1
        if bbox.y1 > self.y1:
            self.y1 = bbox.y1
        if bbox.x2 < self.x2:
            self.x2 = bbox.x2
        if bbox.y2 < self.y2:
            self.y2 = bbox.y2

    def shrink(self, new_size):
        width = self.x2 - self.x1
        if width > new_size[0]:
            self.x1 = self.x1 + width // 2 - new_size[0] // 2
            self.x2 = self.x1 + new_size[0]
        height = self.y2 - self.y1
        if height > new_size[1]:
            self.y1 = self.y1 + height // 2 - new_size[1] // 2
            self.y2 = self.y1 + new_size[1]
