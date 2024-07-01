# This file is part of the SLA firmware
# Copyright (C) 2014-2018 Futur3d - www.futur3d.net
# Copyright (C) 2018-2019 Prusa Research s.r.o. - www.prusa3d.com
# Copyright (C) 2020 Prusa Development a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

import logging
from typing import Optional, Tuple, List
from PIL import Image, ImageDraw, ImageFont

from slafw import defines
from slafw.project.project import LayerCalibrationType
from slafw.project.bounding_box import BBox


class Area(BBox):
    # pylint: disable=unused-argument
    def __init__(self, coords=None):
        super().__init__(coords)
        self.paste_position = 0, 0

    def set_paste_position(self, bbox: BBox):
        self.paste_position = self.x1, self.y1

    def set_label_text(self, font, text, text_padding, label_size):
        pass

    def set_label_position(self, label_size, calibrate_penetration_px, project_bbox, first_layer_bbox):
        pass

    def paste(self, image: Image, source: Image, calibration_type: LayerCalibrationType):
        image.paste(source, box=self.paste_position)


class AreaWithLabel(Area):
    def __init__(self, coords=None):
        super().__init__(coords)
        self._text_layer: Optional[Image] = None
        self._pad_layer: Optional[Image] = None
        self._label_position = 0, 0

    def _transpose(self, image: Image):
        # pylint: disable=no-self-use
        return image.transpose(Image.FLIP_LEFT_RIGHT)

    def set_paste_position(self, bbox: BBox):
        bbox_size = bbox.size
        self_size = self.size
        self.paste_position = self.x1 + (self_size[0] - bbox_size[0]) // 2, self.y1 + (self_size[1] - bbox_size[1]) // 2
        self._logger.debug("copy position: %s", str(self.paste_position))

    def set_label_text(self, font, text, text_padding, label_size):
        self._logger.debug("calib. label size: %s  text padding: %s", str(label_size), str(text_padding))
        tmp = Image.new("L", label_size)
        tmp_draw = ImageDraw.Draw(tmp)
        tmp_draw.text(text_padding, text, fill=255, font=font, spacing=0)
        self._text_layer = self._transpose(tmp)
        self._pad_layer = self._transpose(Image.new("L", label_size, 255))

    def set_label_position(self, label_size, calibrate_penetration_px, project_bbox, first_layer_bbox):
        first_padding = project_bbox - first_layer_bbox
        label_x = self.x1 + (self.size[0] - label_size[0]) // 2
        label_y = self.paste_position[1] + first_padding[1] - label_size[1] + calibrate_penetration_px
        if label_y < self.y1:
            label_y = self.y1
        self._label_position = label_x, label_y
        self._logger.debug("label position: %s", str(self._label_position))

    def paste(self, image: Image, source: Image, calibration_type: LayerCalibrationType):
        image.paste(source, box=self.paste_position)
        if calibration_type == LayerCalibrationType.LABEL_TEXT:
            image.paste(self._pad_layer, box=self._label_position, mask=self._text_layer)
        elif calibration_type == LayerCalibrationType.LABEL_PAD:
            image.paste(self._pad_layer, box=self._label_position)


class AreaWithLabelStripe(AreaWithLabel):
    def _transpose(self, image: Image):
        return image.transpose(Image.ROTATE_270).transpose(Image.FLIP_LEFT_RIGHT)

    def set_paste_position(self, bbox: BBox):
        bbox_size = bbox.size
        self_size = self.size
        self.paste_position = 0, self.y1 + (self_size[1] - bbox_size[1]) // 2
        self._logger.debug("copy position: %s", str(self.paste_position))

    def set_label_position(self, label_size, calibrate_penetration_px, project_bbox, first_layer_bbox):
        first_size = first_layer_bbox.size
        label_x = first_size[0] - calibrate_penetration_px
        label_y = self.y1 + (self.size[1] - label_size[0]) // 2  # text is 90 degree rotated
        label_y = max(label_y, 0)
        self._label_position = label_x, label_y
        self._logger.debug("label position: %s", str(self._label_position))


class Calibration:
    # pylint: disable=too-many-arguments
    def __init__(self, exposure_size_px: Tuple):
        self.areas: List[Area] = []
        self.is_cropped = False
        self._logger = logging.getLogger(__name__)
        self._width_px, self._height_px = exposure_size_px
        self._project_bbox: Optional[BBox] = None
        self._first_layer_bbox: Optional[BBox] = None

    def new_project(
        self,
        project_bbox: BBox,
        first_layer_bbox: BBox,
        calibrate_regions: int,
        calibrate_compact: bool,
        calibrate_times_ms: list,
        calibrate_penetration_px: int,
        calibrate_text_size_px: int,
        calibrate_pad_spacing_px: int,
    ):
        self._project_bbox = project_bbox
        self._first_layer_bbox = first_layer_bbox
        if self.create_areas(calibrate_regions, project_bbox if calibrate_compact else None):
            self._check_project_size()
            return self._create_overlays(
                calibrate_times_ms, calibrate_penetration_px, calibrate_text_size_px, calibrate_pad_spacing_px
            )
        return False

    def create_areas(self, regions, bbox: BBox):
        areaMap = {
            2: (2, 1),
            4: (2, 2),
            6: (3, 2),
            8: (4, 2),
            9: (3, 3),
            10: (10, 1),
        }
        if regions not in areaMap:
            self._logger.error("bad value regions (%d)", regions)
            return False
        divide = areaMap[regions]
        if self._width_px > self._height_px:
            x = 0
            y = 1
        else:
            x = 1
            y = 0
        if bbox:
            size = list(bbox.size)
            if size[0] * divide[x] > self._width_px:
                size[0] = self._width_px // divide[x]
            if size[1] * divide[y] > self._height_px:
                size[1] = self._height_px // divide[y]
            self._areas_loop(
                ((self._width_px - divide[x] * size[0]) // 2, (self._height_px - divide[y] * size[1]) // 2),
                (size[0], size[1]),
                (divide[x], divide[y]),
                Area,
            )
        else:
            self._areas_loop(
                (0, 0),
                (self._width_px // divide[x], self._height_px // divide[y]),
                (divide[x], divide[y]),
                AreaWithLabelStripe if regions == 10 else AreaWithLabel,
            )
        return True

    def _areas_loop(self, begin, step, rnge, area_type):
        for i in range(rnge[0]):
            for j in range(rnge[1]):
                x = i * step[0] + begin[0]
                y = j * step[1] + begin[1]
                area = area_type((x, y, x + step[0], y + step[1]))
                self._logger.debug("%d-%d: %s", i, j, area)
                self.areas.append(area)

    def _check_project_size(self):
        orig_size = self._project_bbox.size
        self._logger.debug("project bbox: %s  project size: %dx%d", str(self._project_bbox), orig_size[0], orig_size[1])
        area_size = self.areas[0].size
        self._project_bbox.shrink(area_size)
        new_size = self._project_bbox.size
        if new_size != orig_size:
            self._logger.warning(
                "project size %dx%d was reduced to %dx%d to fit area size %dx%d",
                orig_size[0],
                orig_size[1],
                new_size[0],
                new_size[1],
                area_size[0],
                area_size[1],
            )
            self.is_cropped = True
            orig_size = self._first_layer_bbox.size
            self._first_layer_bbox.crop(self._project_bbox)
            new_size = self._first_layer_bbox.size
            if new_size != orig_size:
                self._logger.warning(
                    "project first layer bbox %s was cropped to project bbox %s",
                    str(self._first_layer_bbox),
                    str(self._project_bbox.size),
                )

    def _create_overlays(
        self,
        calibrate_times_ms: list,
        calibrate_penetration_px: int,
        calibrate_text_size_px: int,
        calibrate_pad_spacing_px: int,
    ):
        if len(calibrate_times_ms) != len(self.areas):
            self._logger.error("calibrate_times_ms != areas (%d, %d)", len(calibrate_times_ms), len(self.areas))
            return False
        font = ImageFont.truetype(defines.fontFile, calibrate_text_size_px)
        actual_time_ms = 0
        for area, time_ms in zip(self.areas, calibrate_times_ms):
            area.set_paste_position(self._project_bbox)
            actual_time_ms += time_ms
            text = f"{actual_time_ms / 1000:.1f}"
            self._logger.debug("calib. text: '%s'", text)
            text_size = font.getsize(text)
            text_offset = font.getoffset(text)
            self._logger.debug("text_size: %s  text_offset: %s", str(text_size), str(text_offset))
            label_size = (
                text_size[0] + 2 * calibrate_pad_spacing_px - text_offset[0],
                text_size[1] + 2 * calibrate_pad_spacing_px - text_offset[1],
            )
            text_padding = (
                (label_size[0] - text_size[0] - text_offset[0]) // 2,
                (label_size[1] - text_size[1] - text_offset[1]) // 2,
            )
            area.set_label_text(font, text, text_padding, label_size)
            area.set_label_position(label_size, calibrate_penetration_px, self._project_bbox, self._first_layer_bbox)
        return True
