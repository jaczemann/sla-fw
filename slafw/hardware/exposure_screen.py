# This file is part of the SLA firmware
# Copyright (C) 2014-2018 Futur3d - www.futur3d.net
# Copyright (C) 2018-2019 Prusa Research s.r.o. - www.prusa3d.com
# Copyright (C) 2020-2024 Prusa Development a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

import functools
import logging
import mmap
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from threading import Thread, Event
from time import monotonic, sleep
from typing import Optional, Any, List, Tuple

from PIL import Image
from PySignal import Signal
from pywayland.client import Display
from pywayland.protocol.presentation_time import WpPresentation
from pywayland.protocol.wayland import WlCompositor, WlSubcompositor, WlShm, WlOutput
from pywayland.protocol.xdg_shell import XdgWmBase
from pywayland.utils import AnonymousFile

from slafw import defines
from slafw.hardware.component import HardwareComponent


@dataclass(eq=False)
class Bindings:
    compositor: Any = field(init=False, default=None)
    subcompositor: Any = field(init=False, default=None)
    wm_base: Any = field(init=False, default=None)
    shm: Any = field(init=False, default=None)
    output: Any = field(init=False, default=None)
    presentation: Any = field(init=False, default=None)
    shm_format: int = field(init=False, default=None)


@dataclass(eq=False)
class ExposureScreenParameters:
    #pylint: disable=too-many-instance-attributes
    size_px: tuple
    thumbnail_factor: int
    output_factor: int
    pixel_size_nm: int
    refresh_delay_ms: int
    monochromatic: bool
    bgr_pixels: bool
    width_px: int = field(init=False)
    height_px: int = field(init=False)
    pixels_per_percent: int = field(init=False)
    bytes_per_pixel: int = field(init=False)
    apparent_size_px: tuple = field(init=False)
    apparent_width_px: int = field(init=False)
    apparent_height_px: int = field(init=False)
    display_usage_size_px: tuple = field(init=False)
    live_preview_size_px: tuple = field(init=False)
    dpi: float = field(init=False)

    def __post_init__(self):
        self.width_px = self.size_px[0]
        self.height_px = self.size_px[1]
        self.bytes_per_pixel = 3 if self.monochromatic else 1
        self.pixels_per_percent = ((self.width_px * self.bytes_per_pixel) * self.height_px) // 100
        self.apparent_width_px = self.width_px * self.output_factor * self.bytes_per_pixel
        self.apparent_height_px = self.height_px * self.output_factor
        self.apparent_size_px = (self.apparent_width_px, self.apparent_height_px)
        # numpy uses reversed axis indexing
        self.display_usage_size_px = (self.apparent_height_px // self.thumbnail_factor,
                                      self.apparent_width_px // self.thumbnail_factor)
        self.live_preview_size_px = (self.apparent_width_px // self.thumbnail_factor,
                                     self.apparent_height_px // self.thumbnail_factor)
        self.dpi = 1e6 / self.pixel_size_nm * 25.4


class Layer:
    def __init__(self, bindings: Bindings, width: int, height: int,
                 bytes_per_pixel: int):
        self.bindings = bindings
        self.width = width
        self.height = height
        self.bytes_per_pixel = bytes_per_pixel
        self.pool = None
        self.shm_data = None
        self.surfaces: List[Surface] = []

    @property
    def base_wl_surface(self):
        return self.surfaces[0].wl_surface

    @property
    def base_wl_subsurface(self):
        return self.surfaces[0].wl_subsurface

    def add_surface(self, compositor, subcompositor = None, parent = None, position: Tuple[int, int] = (0,0)):
        surface = Surface(compositor)
        surface.set_opaque(self.width, self.height, compositor)
        if subcompositor:
            surface.set_subsurface(subcompositor, parent, position)
        surface.commit()
        self.surfaces.append(surface)

    def init_surfaces(self):
        self._create_pool()
        for surface in self.surfaces:
            surface.wl_surface.attach(self._create_buffer(), 0, 0)
            surface.wl_surface.commit()

    def delete_surfaces(self):
        for surface in self.surfaces:
            if surface.wl_subsurface:
                surface.wl_subsurface.destroy()
            surface.wl_surface.destroy()
        self.surfaces = []
        self.pool.destroy()

    def redraw(self):
        surface = self.base_wl_surface
        surface.attach(self._create_buffer(), 0, 0)
        surface.damage_buffer(0, 0, self.width, self.height)

    def _create_pool(self):
        size = self.width * self.height * self.bytes_per_pixel
        if self.pool:
            self.pool.destroy()
        with AnonymousFile(size) as fd:
            self.shm_data = mmap.mmap(
                fd, size, prot=mmap.PROT_READ | mmap.PROT_WRITE, flags=mmap.MAP_SHARED
            )
            self.pool = self.bindings.shm.create_pool(fd, size)

    def _create_buffer(self):
        stride = self.width * self.bytes_per_pixel
        buffer = self.pool.create_buffer(0, self.width, self.height, stride, self.bindings.shm_format)
        buffer.dispatcher["release"] = self._buffer_release_handler
        return buffer

    @staticmethod
    def _buffer_release_handler(buffer):
        buffer.destroy()


class Surface:
    def __init__(self, compositor):
        self.wl_surface = compositor.create_surface()
        self.wl_subsurface = None

    def set_subsurface(self, subcompositor, parent, position: Tuple[int, int]):
        self.wl_subsurface = subcompositor.get_subsurface(self.wl_surface, parent)
        self.wl_subsurface.set_position(*position)
        self.wl_subsurface.set_sync()
        self.wl_subsurface.place_above(parent)

    def set_opaque(self, width, height, compositor):
        # optimalization: set whole surface opaque
        region = compositor.create_region()
        region.add(0, 0, width, height)
        self.wl_surface.set_opaque_region(region)

    def commit(self):
        self.wl_surface.commit()


def sync_call(function):
    @functools.wraps(function)
    def inner(self, sync: bool, *args):
        main_surface = self.main_layer.base_wl_surface
        if sync:
            feedback = self.bindings.presentation.feedback(main_surface)
            feedback.dispatcher["presented"] = self.feedback_presented_handler
            feedback.dispatcher["discarded"] = self.feedback_discarded_handler
        start_time = monotonic()
        function(self, main_surface, *args)
        main_surface.commit()
        self.logger.debug("%s done in %f ms", function.__name__, 1e3 * (monotonic() - start_time))
        # show immediately
        self.display.flush()
        if sync:
            self.logger.debug("waiting for video sync event")
            start_time = monotonic()
            if not self.video_sync_event.wait(timeout=2):
                self.logger.error("video sync event timeout")
                # TODO this shouldn't happen, need better handling if yes
                raise RuntimeError("video sync timeout")
            self.video_sync_event.clear()
            self.logger.debug("video sync done in %f ms", 1e3 * (monotonic() - start_time))
            delay = self.parameters.refresh_delay_ms / 1e3
            if delay > 0:
                self.logger.debug("waiting %f ms for display refresh", self.parameters.refresh_delay_ms)
                sleep(delay)
    return inner


class Wayland:
    # pylint: disable=too-many-instance-attributes
    # pylint: disable=unused-argument
    # pylint: disable=too-many-arguments
    def __init__(self, parameters: ExposureScreenParameters):
        self.logger = logging.getLogger(__name__)
        self._thread = Thread(target=self._event_loop)
        self.video_sync_event = Event()
        self.display = Display()
        self.bindings = Bindings()
        self.main_layer: Optional[Layer] = None
        self.blank_layer: Optional[Layer] = None
        self.calibration_layer: Optional[Layer] = None
        self.parameters: ExposureScreenParameters = parameters
        self.format_available = False
        self._stopped = False
        self._wl_outputs: List[Any] = []

    def start(self, shm_format: int):
        self.bindings.shm_format = shm_format
        self.display.connect()
        self.logger.debug("connected to display")
        registry = self.display.get_registry()
        registry.dispatcher["global"] = self._registry_global_handler
        registry.dispatcher["global_remove"] = self._registry_global_remover
        self.display.dispatch(block=True)
        self.display.roundtrip()
        if not self.bindings.compositor:
            raise RuntimeError("no wl_compositor found")
        if not self.bindings.subcompositor:
            raise RuntimeError("no wl_subcompositor found")
        if not self.bindings.wm_base:
            raise RuntimeError("no xdg_wm_base found")
        if not self.bindings.shm:
            raise RuntimeError("no wl_shm found")
        if not self.bindings.output:
            raise RuntimeError("no wl_output found")
        if not self.bindings.presentation:
            raise RuntimeError("no wp_presentation found")
        if not self.format_available:
            raise RuntimeError("no suitable shm format available")
        del self._wl_outputs
        self.main_layer = Layer(
                self.bindings,
                self.parameters.width_px,
                self.parameters.height_px,
                self.parameters.bytes_per_pixel)
        self.main_layer.add_surface(self.bindings.compositor)
        main_surface = self.main_layer.base_wl_surface
        xdg_surface = self.bindings.wm_base.get_xdg_surface(main_surface)
        xdg_surface.dispatcher["configure"] = self._xdg_surface_configure_handler
        xdg_toplevel = xdg_surface.get_toplevel()
        xdg_toplevel.set_title("SLA-FW Exposure Output")
        xdg_toplevel.set_app_id("cz.prusa3d.slafw")
        if self.parameters.output_factor == 1:
            xdg_toplevel.set_fullscreen(self.bindings.output)
        xdg_toplevel.dispatcher["configure"] = self._xdg_toplevel_configure_handler
        xdg_toplevel.dispatcher["close"] = self._xdg_toplevel_close_handler
        self.blank_layer = Layer(
                self.bindings,
                self.main_layer.width,
                self.main_layer.height,
                self.parameters.bytes_per_pixel)
        self.blank_layer.add_surface(self.bindings.compositor, self.bindings.subcompositor, main_surface)
        main_surface.commit()
        self.display.dispatch(block=True)
        self.display.roundtrip()
        self._thread.start()

    def exit(self):
        self.logger.debug("stopped")
        self._stopped = True
        if self._thread:
            self._thread.join()
        self.main_layer.pool.destroy()
        self.blank_layer.pool.destroy()
        if self.calibration_layer:
            self.calibration_layer.pool.destroy()
        self.display.disconnect()
        self.logger.debug("disconnected from display")

    def _event_loop(self):
        while self.display.dispatch(block=True) != -1 and not self._stopped:
            pass

    def _registry_global_handler(self, registry, id_, interface, version):
        if interface == "wl_compositor":
            self.logger.debug("got wl_compositor")
            self.bindings.compositor = registry.bind(id_, WlCompositor, version)
        elif interface == "wl_subcompositor":
            self.logger.debug("got wl_subcompositor")
            self.bindings.subcompositor = registry.bind(id_, WlSubcompositor, version)
        elif interface == "xdg_wm_base":
            self.logger.debug("got xdg_wm_base")
            self.bindings.wm_base = registry.bind(id_, XdgWmBase, version)
            self.bindings.wm_base.dispatcher["ping"] = self._wm_base_ping_handler
        elif interface == "wl_shm":
            self.logger.debug("got wl_shm")
            self.bindings.shm = registry.bind(id_, WlShm, version)
            self.bindings.shm.dispatcher["format"] = self._shm_format_handler
        elif interface == "wl_output":
            output = registry.bind(id_, WlOutput, version)
            output.dispatcher["mode"] = self._output_handler
            self._wl_outputs.append(output)
        elif interface == "wp_presentation":
            self.logger.debug("got wp_presentation")
            self.bindings.presentation = registry.bind(id_, WpPresentation, version)

    def _registry_global_remover(self, registry, id_):
        self.logger.debug("got a registry losing event for %d", id_)

    def _wm_base_ping_handler(self, wm_base, serial):
        wm_base.pong(serial)
        self.logger.debug("pinged/ponged")

    def _shm_format_handler(self, shm, shm_format):
        if shm_format == self.bindings.shm_format:
            self.logger.debug("got shm_format")
            self.format_available = True

    def _output_handler(self, wl_output, flags, width, height, refresh):
        self.logger.debug("found output - %dx%d@%.1f flags:%d ", width, height, refresh / 1e3, flags)
        if self.parameters.output_factor == 1:
            if width == self.parameters.width_px and height == self.parameters.height_px:
                self.logger.debug("got wl_output")
                self.bindings.output = wl_output
        else:
            if width >= self.parameters.width_px and height >= self.parameters.height_px:
                self.logger.debug("got wl_output (window)")
                self.bindings.output = wl_output
        if not self.bindings.output:
            self.logger.debug("wrong resolution (%dx%d) - output ignored", width, height)

    def _xdg_toplevel_configure_handler(self, xdg_toplevel, width, height, states):
        if width != self.main_layer.width or height != self.main_layer.height:
            self.logger.error("Invalid resolution request (%dx%d)", width, height)

    def _xdg_toplevel_close_handler(self, xdg_toplevel):
        self.logger.warning("closed")
        self._stopped = True

    def _xdg_surface_configure_handler(self, xdg_surface, serial):
        xdg_surface.ack_configure(serial)
        self.logger.debug("xdg_surface configure")
        self.blank_layer.init_surfaces()
        self.main_layer.init_surfaces()

    def feedback_presented_handler(self, feedback, tv_sec_hi, tv_sec_lo, tv_nsec, refresh, seq_hi, seq_lo, flags):
        self.logger.debug("presented feedback (%d, %d, %d, %d, %d, %d, %d)", tv_sec_hi, tv_sec_lo, tv_nsec, refresh, seq_hi, seq_lo, flags)
        self.video_sync_event.set()

    def feedback_discarded_handler(self, feedback):
        self.logger.warning("discarded feedback")

    @sync_call
    def show_bytes(self, main_surface, image: bytes):
        self.main_layer.shm_data.seek(0)   # type: ignore
        self.main_layer.shm_data.write(image)  # type: ignore
        self._show(main_surface)

    @sync_call
    def show_shm(self, main_surface):
        self._show(main_surface)

    def _show(self, main_surface):
        self.main_layer.redraw()
        self.blank_layer.base_wl_subsurface.place_below(main_surface)
        if self.calibration_layer:
            for surface in self.calibration_layer.surfaces:
                surface.wl_subsurface.place_below(main_surface)

    @sync_call
    def blank_screen(self, main_surface):
        self.blank_layer.base_wl_subsurface.place_above(main_surface)

    def create_areas(self, areas):
        if self.calibration_layer:
            self.calibration_layer.delete_surfaces()
            self.calibration_layer = None
        if areas:
            width, height = areas[0].size
            self.calibration_layer = Layer(
                    self.bindings,
                    width // self.parameters.bytes_per_pixel,
                    height,
                    self.parameters.bytes_per_pixel)
            main_surface = self.main_layer.base_wl_surface
            for area in areas:
                self.calibration_layer.add_surface(
                        self.bindings.compositor,
                        self.bindings.subcompositor,
                        main_surface,
                        (area.x1 // self.parameters.bytes_per_pixel, area.y1))
            self.calibration_layer.init_surfaces()

    @sync_call
    def blank_area(self, main_surface, area_index: int):
        self.calibration_layer.surfaces[area_index].wl_subsurface.place_above(main_surface)


class ExposureScreen(HardwareComponent, ABC):
    def __init__(self):
        super().__init__("Exposure screen")
        self._logger.info("Exposure panel serial number: %s", self.serial_number)
        self._logger.info("Exposure panel transmittance: %s", self.transmittance)
        self._wayland = Wayland(self.parameters)
        self.usage_s_changed = Signal()

    def start(self):
        self._wayland.start(self._find_format())

    def exit(self):
        self._wayland.exit()

    def _find_format(self):
        if self.parameters.bytes_per_pixel == 1:
            return WlShm.format.r8.value
        if self.parameters.bgr_pixels:
            return WlShm.format.bgr888.value
        return WlShm.format.rgb888.value

    def show(self, image: Image, sync: bool = True):
        if image.size != self.parameters.apparent_size_px:
            raise RuntimeError(f"Wrong image size {image.size} for output {self.parameters.apparent_size_px}")
        if image.mode != "L":
            raise RuntimeError(f"Invalid pixel format {image.mode}")
        if self.parameters.output_factor != 1:
            self._logger.debug("resize from: %s", image.size)
            image = image.resize(self.parameters.size_px, Image.BICUBIC)
            self._logger.debug("resize to: %s", image.size)
        self._wayland.show_bytes(sync, image.tobytes())

    def blank_screen(self, sync: bool = True):
        self._wayland.blank_screen(sync)

    def create_areas(self, areas):
        self._wayland.create_areas(areas)

    def blank_area(self, area_index: int, sync: bool = True):
        self._wayland.blank_area(sync, area_index)

    def draw_pattern(self, drawfce, *args):
        start_time = monotonic()
        l = self._wayland.main_layer
        drawfce(l.shm_data, l.width * l.bytes_per_pixel, l.height, *args)
        self._logger.debug("%s done in %f ms", drawfce.__name__, 1e3 * (monotonic() - start_time))
        self._wayland.show_shm(True) # synced

    @functools.cached_property
    @abstractmethod
    def parameters(self) -> ExposureScreenParameters:
        ...

    @property
    def serial_number(self) -> str:
        path = defines.exposure_panel_of_node / "serial-number"
        return path.read_text()[:-1] if path.exists() else ""

    @property
    def transmittance(self) -> float:
        path = defines.exposure_panel_of_node / "transmittance"
        return int.from_bytes(path.read_bytes(), byteorder='big') / 100.0 \
            if path.exists() else 0.0

    @abstractmethod
    def start_counting_usage(self):
        """
        Start counting display usage
        """

    @abstractmethod
    def stop_counting_usage(self):
        """
        Stop counting UV display usage
        """

    @property
    @abstractmethod
    def usage_s(self) -> int:
        """
        How long has the UV LED been used
        """

    @abstractmethod
    def save_usage(self):
        """
        Store usage to permanent storage
        """

    @abstractmethod
    def clear_usage(self):
        """
        Clear usage

        Use this when UV LED is replaced
        """


class VirtualExposureScreen(ExposureScreen):
    @functools.cached_property
    def parameters(self) -> ExposureScreenParameters:
        return ExposureScreenParameters(
            size_px=(360, 640),
            thumbnail_factor=5,
            output_factor=4,
            pixel_size_nm=47250,
            refresh_delay_ms=0,
            monochromatic=False,
            bgr_pixels=False,
        )

    def start_counting_usage(self):
        pass

    def stop_counting_usage(self):
        pass

    @property
    def usage_s(self) -> int:
        return 0

    def save_usage(self):
        pass

    def clear_usage(self):
        pass
