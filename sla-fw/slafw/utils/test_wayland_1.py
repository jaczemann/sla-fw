#!/usr/bin/env python3

# This file is part of the SLA firmware
# Based on code by Sean Vig https://github.com/flacjacket/pywayland/blob/main/example/surface.py
# Copyright (C) 2021 Prusa Research s.r.o. - www.prusa3d.com
# SPDX-License-Identifier: Apache-2.0

# pylint: skip-file

from __future__ import absolute_import, print_function

import mmap
import os
import sys

this_file = os.path.abspath(__file__)
this_dir = os.path.split(this_file)[0]
root_dir = os.path.split(this_dir)[0]
pywayland_dir = os.path.join(root_dir, "pywayland")
if os.path.exists(pywayland_dir):
    sys.path.append(root_dir)

from pywayland.client import Display  # noqa: E402
from pywayland.protocol.wayland import WlCompositor, WlSubcompositor, WlShm, WlOutput  # noqa: E402
from pywayland.protocol.xdg_shell import XdgWmBase  # noqa: E402
from pywayland.utils import AnonymousFile  # noqa: E402


MARGIN = 10

class Surface:
    def __init__(self, width, height):
        self.width = width
        self.height = height
        self.wl_surface = None
        self.buffer = None
        self.shm_data = None

        self.pattern_offset = MARGIN
        self.pattern_direction = 1
        self.last_time = 0
        self.frames = 0


class Window:
    def __init__(self):
        self.display = None
        self.wl_compositor = None
        self.wl_subcompositor = None
        self.wl_shm = None
        self.wl_output = None
        self.xdg_wm_base = None
        self.closed = False

        self.background = None
        self.overlay_1 = None
        self.subsurface = None


def wm_base_ping_handler(wm_base, serial):
    wm_base.pong(serial)
    print("-> pinged/ponged")


def xdg_surface_configure_handler(xdg_surface, serial):
    window = xdg_surface.user_data
    background = window.background
    xdg_surface.ack_configure(serial)
    print("-> xdg_surface_configure_handler(%d, %d)" % (background.width, background.height))

    if background.width and background.height:
        create_buffer(background, window.wl_shm)
        background.wl_surface.attach(background.buffer, 0, 0)
        background.wl_surface.commit()
        overlay_1 = window.overlay_1
        window.subsurface.set_position((background.width - overlay_1.width) // 2, (background.height - overlay_1.height) // 2)


def xdg_toplevel_close_handler(xdg_toplevel):
    print("-> closed")
    window = xdg_toplevel.user_data
    window.closed = True


def xdg_toplevel_configure_handler(xdg_toplevel, width, height, states):
    if width and height:
        print("-> configure - width: %d  height: %d" % (width, height))
        window = xdg_toplevel.user_data
        window.background.width = width
        window.background.height = height


def shm_format_handler(shm, format_):
    if format_ == WlShm.format.argb8888.value:
        s = "ARGB8888"
    elif format_ == WlShm.format.xrgb8888.value:
        s = "XRGB8888"
    elif format_ == WlShm.format.rgb565.value:
        s = "RGB565"
    else:
        s = hex(format_)
    print("Possible shmem format: {}".format(s))


def output_mode_handler(wl_output, flags, width, height, refresh):
    print("flags:%d width:%d height:%d refresh:%d" % (flags, width, height, refresh))


def registry_global_handler(registry, id_, interface, version):
    print(interface)
    window = registry.user_data
    if interface == "wl_compositor":
        print("-> got wl_compositor")
        window.wl_compositor = registry.bind(id_, WlCompositor, version)
    elif interface == "wl_subcompositor":
        print("-> got wl_subcompositor")
        window.wl_subcompositor = registry.bind(id_, WlSubcompositor, version)
    elif interface == "xdg_wm_base":
        print("-> got xdg_wm_base")
        window.xdg_wm_base = registry.bind(id_, XdgWmBase, version)
        window.xdg_wm_base.dispatcher["ping"] = wm_base_ping_handler
    elif interface == "wl_shm":
        print("-> got wl_shm")
        window.wl_shm = registry.bind(id_, WlShm, version)
        window.wl_shm.dispatcher["format"] = shm_format_handler
    elif interface == "wl_output":
        print("-> got wl_output")
        window.wl_output = registry.bind(id_, WlOutput, version)
        window.wl_output.dispatcher["mode"] = output_mode_handler


def registry_global_remover(registry, id_):
    print("-> got a registry losing event for {}".format(id_))


def create_buffer(surface, wl_shm):
    print("-> create_buffer %dx%d" % (surface.width, surface.height))
    stride = surface.width * 4
    size = stride * surface.height

    with AnonymousFile(size) as fd:
        surface.shm_data = mmap.mmap(
            fd, size, prot=mmap.PROT_READ | mmap.PROT_WRITE, flags=mmap.MAP_SHARED
        )
        pool = wl_shm.create_pool(fd, size)
        surface.buffer = pool.create_buffer(0, surface.width, surface.height, stride, WlShm.format.argb8888.value)
        pool.destroy()


def redraw(callback, time, destroy_callback=True):
#    print("redraw")
    window = callback.user_data
    if destroy_callback:
        callback.destroy()

    callback = window.background.wl_surface.frame()
    callback.dispatcher["done"] = redraw
    callback.user_data = window

    background = window.background
    grid = window.overlay_1

    if background.width and background.height:
        paint_line(background)
        background.wl_surface.damage_buffer(0, background.pattern_offset-2, background.width, 5)
        background.wl_surface.attach(background.buffer, 0, 0)
        background.wl_surface.commit()

        paint_grid(grid)
        grid.wl_surface.damage_buffer(0, 0, grid.width, grid.height)
        grid.wl_surface.attach(grid.buffer, 0, 0)
        grid.wl_surface.commit()

        background.frames += 1

        if grid.last_time:
            elapsed = time - grid.last_time
            grid.pattern_offset += elapsed / 1000 * 24

        if time - background.last_time > 1000:
            print("%d FPS" % background.frames)
            background.last_time = time
            background.frames = 0

    grid.last_time = time


def paint_grid(surface):
    mm = surface.shm_data
    mm.seek(0)

    # draw checkerboxed background
    offset = surface.pattern_offset % 8
    for y in range(surface.height):
        for x in range(surface.width):
            if (x + offset + (y + offset) // 8 * 8) % 16 < 8:
                mm.write(b"\x00\x80\x00\x00")
            else:
                mm.write(b"\x80\x00\x00\x00")


def paint_line(surface):
    mm = surface.shm_data
    fill = b"\x00"

    # clear
    mm.seek(0)
    mm.write(fill * 4 * surface.width * surface.height)

    # draw progressing line
    mm.seek((surface.pattern_offset * surface.width + MARGIN) * 4)
    mm.write(b"\x00\x00\xff\xff" * (surface.width - 2 * MARGIN))
    surface.pattern_offset += surface.pattern_direction

    # maybe reverse direction of progression
    if surface.pattern_offset >= surface.height - MARGIN or surface.pattern_offset <= MARGIN:
        surface.pattern_direction = -surface.pattern_direction


def main():
    window = Window()
    window.background = Surface(320, 200)
    window.overlay_1 = Surface(160, 100)

    window.display = Display()
    window.display.connect()
    print("-> connected to display")

    registry = window.display.get_registry()
    registry.dispatcher["global"] = registry_global_handler
    registry.dispatcher["global_remove"] = registry_global_remover
    registry.user_data = window

    window.display.dispatch(block=True)
    window.display.roundtrip()

    if window.wl_compositor is None:
        raise RuntimeError("no wl_compositor found")
    if window.wl_subcompositor is None:
        raise RuntimeError("no wl_subcompositor found")
    if window.xdg_wm_base is None:
        raise RuntimeError("no xdg_wm_base found")
    if window.wl_shm is None:
        raise RuntimeError("no wl_shm found")

    window.background.wl_surface = window.wl_compositor.create_surface()

    xdg_surface = window.xdg_wm_base.get_xdg_surface(window.background.wl_surface)
    xdg_surface.dispatcher["configure"] = xdg_surface_configure_handler
    xdg_surface.user_data = window

    xdg_toplevel = xdg_surface.get_toplevel()
    xdg_toplevel.set_title("Example python client")
    xdg_toplevel.set_app_id("org.freedesktop.weston-simple-framebuffer")
    xdg_toplevel.dispatcher["configure"] = xdg_toplevel_configure_handler
    xdg_toplevel.dispatcher["close"] = xdg_toplevel_close_handler
    xdg_toplevel.user_data = window

    window.overlay_1.wl_surface = window.wl_compositor.create_surface()
    window.subsurface = window.wl_subcompositor.get_subsurface(window.overlay_1.wl_surface, window.background.wl_surface)
    window.subsurface.set_position(80, 50)
    window.subsurface.set_sync()
    create_buffer(window.overlay_1, window.wl_shm)
    window.overlay_1.wl_surface.attach(window.overlay_1.buffer, 0, 0)
    window.overlay_1.wl_surface.commit()

    window.background.wl_surface.commit()

    frame_callback = window.background.wl_surface.frame()
    frame_callback.dispatcher["done"] = redraw
    frame_callback.user_data = window

    while window.display.dispatch(block=True) != -1 and not window.closed:
        pass
    window.display.disconnect()


if __name__ == "__main__":
    main()
