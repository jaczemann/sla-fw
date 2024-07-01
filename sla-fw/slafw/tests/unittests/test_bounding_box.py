#!/usr/bin/env python3

# This file is part of the SLA firmware
# Copyright (C) 2014-2018 Futur3d - www.futur3d.net
# Copyright (C) 2018-2019 Prusa Research s.r.o. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

import unittest

from slafw.tests.base import SlafwTestCase
from slafw.project.bounding_box import BBox


class TestBBox(SlafwTestCase):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def test_create(self):
        bbox = BBox((100, 200, 300, 400))
        self.assertEqual(bbox.x1, 100)
        self.assertEqual(bbox.y1, 200)
        self.assertEqual(bbox.x2, 300)
        self.assertEqual(bbox.y2, 400)

    def test_print(self):
        bbox = BBox()
        self.assertEqual(str(bbox), "None")
        bbox = BBox((100, 200, 300, 400))
        self.assertEqual(str(bbox), "(100, 200, 300, 400)")

    def test_limits(self):
        bbox = BBox()
        self.assertFalse(bbox)
        bbox = BBox((100, 200, 300, 400))
        self.assertTrue(bbox)
        bbox = BBox((100, 200))
        self.assertFalse(bbox)
        bbox = BBox((100, 200, 100, 400))
        self.assertFalse(bbox)
        bbox = BBox((100, 200, 300, 100))
        self.assertFalse(bbox)
        bbox = BBox((-1, -1, 300, 400))
        self.assertFalse(bbox)
        bbox = BBox((0, 0, -1, -1))
        self.assertFalse(bbox)

    def test_compare(self):
        bbox1 = BBox()
        bbox2 = BBox()
        self.assertEqual(bbox1, bbox2)
        bbox1 = BBox((100, 200, 300, 400))
        bbox2 = BBox((100, 200, 300, 400))
        self.assertEqual(bbox1, bbox2)
        bbox1 = BBox((200, 100, 400, 300))
        bbox2 = BBox((100, 200, 300, 400))
        self.assertNotEqual(bbox1, bbox2)

    def test_sub(self):
        bbox1 = BBox((10, 10, 100, 100))
        bbox2 = BBox((20, 25, 80, 75))
        self.assertEqual(bbox1 - bbox2, (10, 15, 20, 25))

    def test_coords(self):
        bbox = BBox()
        bbox.coords = 100, 200, 300, 400
        self.assertEqual(bbox.coords, (100, 200, 300, 400))

    def test_size(self):
        bbox = BBox()
        self.assertEqual(bbox.size, (0, 0))
        bbox = BBox((100, 200, 300, 400))
        self.assertEqual(bbox.size, (200, 200))

    def test_maximize(self):
        bbox = BBox()
        bbox.maximize(BBox((10, 20, 30, 40)))
        self.assertEqual(bbox.coords, (10, 20, 30, 40))
        bbox.maximize(BBox((200, 300, 400, 500)))
        self.assertEqual(bbox.coords, (10, 20, 400, 500))

    def test_crop(self):
        bbox = BBox((100, 200, 300, 400))
        bbox.crop(BBox((100, 200, 275, 375)))
        self.assertEqual(bbox.coords, (100, 200, 275, 375))
        bbox.crop(BBox((125, 225, 300, 400)))
        self.assertEqual(bbox.coords, (125, 225, 275, 375))

    def test_shrink(self):
        bbox = BBox((100, 200, 300, 400))
        bbox.shrink((25, 30))
        self.assertEqual(bbox.coords, (188, 285, 213, 315))

if __name__ == '__main__':
    unittest.main()
