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

from time import monotonic, sleep
from threading import Thread

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


class Surface:
    def __init__(self, compositor, subcompositor = None, parent = None):
        self.wl_surface = compositor.create_surface()
        if subcompositor:
            self.wl_subsurface = subcompositor.get_subsurface(self.wl_surface, parent)
            self.wl_subsurface.set_sync()
            self.wl_subsurface.place_below(parent)
        else:
            self.wl_subsurface = None
        self.wl_surface.commit()


class Layer:
    def __init__(self, width, height):
        self.width = width
        self.height = height
        self.pool = None
        self.shm_data = None
        self.surface = []

    @property
    def base_wl_surface(self):
        return self.surface[0].wl_surface


class Window:
    def __init__(self):
        self.display = None
        self.compositor = None
        self.subcompositor = None
        self.shm = None
        self.output = None
        self.wm_base = None

        self.background = None
        self.overlay = None

        self.closed = False


def wm_base_ping_handler(wm_base, serial):
    wm_base.pong(serial)
    print("-> wm_base_ping_handler")


def xdg_surface_configure_handler(xdg_surface, serial):
    xdg_surface.ack_configure(serial)
    print("-> xdg_surface_configure_handler")

    window = xdg_surface.user_data
    bg = window.background

    if bg.width and bg.height:
        create_pool(bg, window.shm)
        ovr = window.overlay
        create_pool(ovr, window.shm)
        if ovr.width and ovr.height:
            position = 0
            for srf in ovr.surface:
                srf.wl_subsurface.set_position(position, 0)
                position += ovr.width
                buffer = create_buffer(ovr)
                buffer.dispatcher["release"] = buffer_release_handler
                buffer.user_data = ovr
                srf.wl_surface.attach(buffer, 0, 0)
                srf.wl_surface.damage_buffer(0, 0, ovr.width, ovr.height)
                srf.wl_surface.commit()
        paint_grid(bg)
        buffer = create_buffer(bg)
        buffer.dispatcher["release"] = buffer_release_handler
        buffer.user_data = bg
        bg.base_wl_surface.attach(buffer, 0, 0)
        bg.base_wl_surface.damage_buffer(0, 0, bg.width, bg.height)
        bg.base_wl_surface.commit()


def xdg_toplevel_close_handler(xdg_toplevel):
    print("-> xdg_toplevel_close_handler")
    window = xdg_toplevel.user_data
    window.closed = True


def xdg_toplevel_configure_handler(xdg_toplevel, width, height, states):
    if width and height:
        print("-> xdg_toplevel_configure_handler %dx%d" % (width, height))
        window = xdg_toplevel.user_data
        window.background.width = width
        window.background.height = height
        window.overlay.width = width // len(window.overlay.surface)
        window.overlay.height = height


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


def output_mode_handler(output, flags, width, height, refresh):
    print("-> output_mode_handler:%d width:%d height:%d refresh:%d" % (flags, width, height, refresh))


def buffer_release_handler(buffer):
    print("-> buffer_release_handler %dx%d" % (buffer.user_data.width, buffer.user_data.height))
    buffer.destroy()


def registry_global_handler(registry, id_, interface, version):
    print(interface)
    window = registry.user_data
    if interface == "wl_compositor":
        print("-> got wl_compositor")
        window.compositor = registry.bind(id_, WlCompositor, version)
    elif interface == "wl_subcompositor":
        print("-> got wl_subcompositor")
        window.subcompositor = registry.bind(id_, WlSubcompositor, version)
    elif interface == "xdg_wm_base":
        print("-> got xdg_wm_base")
        window.wm_base = registry.bind(id_, XdgWmBase, version)
        window.wm_base.dispatcher["ping"] = wm_base_ping_handler
    elif interface == "wl_shm":
        print("-> got wl_shm")
        window.shm = registry.bind(id_, WlShm, version)
        window.shm.dispatcher["format"] = shm_format_handler
    elif interface == "wl_output":
        print("-> got wl_output")
        window.output = registry.bind(id_, WlOutput, version)
        window.output.dispatcher["mode"] = output_mode_handler


def registry_global_remover(registry, id_):
    print("-> got a registry losing event for {}".format(id_))


def create_pool(surface_data, shm):
    print("-> create_pool %dx%d" % (surface_data.width, surface_data.height))
    stride = surface_data.width * 4
    size = stride * surface_data.height

    if surface_data.pool:
        surface_data.pool.destroy()

    with AnonymousFile(size) as fd:
        surface_data.shm_data = mmap.mmap(
            fd, size, prot=mmap.PROT_READ | mmap.PROT_WRITE, flags=mmap.MAP_SHARED
        )
        surface_data.pool = shm.create_pool(fd, size)


def create_buffer(surface_data):
    print("-> create_buffer %dx%d" % (surface_data.width, surface_data.height))
    stride = surface_data.width * 4
    return surface_data.pool.create_buffer(0, surface_data.width, surface_data.height, stride, WlShm.format.xrgb8888.value)


def paint_grid(surface_data):
    mm = surface_data.shm_data
    mm.seek(0)

    # draw checkerboxed background
    for y in range(surface_data.height):
        for x in range(surface_data.width):
            if (x + y // 8 * 8) % 16 < 8:
                mm.write(b"\x00\x80\x00\xff")
            else:
                mm.write(b"\x80\x00\x00\xff")


def event_loop(window):
    while window.display.dispatch(block=True) != -1 and not window.closed:
        pass


def main():
    window = Window()
    window.display = Display()
    window.display.connect()
    print("-> connected to display")

    registry = window.display.get_registry()
    registry.dispatcher["global"] = registry_global_handler
    registry.dispatcher["global_remove"] = registry_global_remover
    registry.user_data = window

    window.display.dispatch(block=True)
    window.display.roundtrip()

    if window.compositor is None:
        raise RuntimeError("no wl_compositor found")
    if window.subcompositor is None:
        raise RuntimeError("no wl_subcompositor found")
    if window.wm_base is None:
        raise RuntimeError("no xdg_wm_base found")
    if window.shm is None:
        raise RuntimeError("no wl_shm found")

    window.background = Layer(320, 200)
    window.background.surface.append(Surface(window.compositor))
    bg_wl_surface = window.background.base_wl_surface

    xdg_surface = window.wm_base.get_xdg_surface(bg_wl_surface)
    xdg_surface.dispatcher["configure"] = xdg_surface_configure_handler
    xdg_surface.user_data = window

    xdg_toplevel = xdg_surface.get_toplevel()
    xdg_toplevel.set_title("Example python client")
    xdg_toplevel.set_app_id("org.freedesktop.weston-simple-framebuffer")
    xdg_toplevel.dispatcher["configure"] = xdg_toplevel_configure_handler
    xdg_toplevel.dispatcher["close"] = xdg_toplevel_close_handler
    xdg_toplevel.user_data = window

    window.overlay = Layer(32, 200)
    for i in range(10):
        window.overlay.surface.append(Surface(window.compositor, window.subcompositor, bg_wl_surface))

    bg_wl_surface.commit()

    thread = Thread(target=event_loop, args=(window,))
    thread.start()

    last_time = monotonic()
    overlay_index = 0
    while not window.closed:
        time = monotonic()
        if time - last_time > 1:
            print("overlay %d" % overlay_index)
            last_time = time
            if overlay_index < len(window.overlay.surface):
                overlay = window.overlay.surface[overlay_index]
                overlay.wl_subsurface.place_above(bg_wl_surface)
                overlay_index += 1
            else:
                for overlay in window.overlay.surface:
                    overlay.wl_subsurface.place_below(bg_wl_surface)
                overlay_index = 0
            bg_wl_surface.commit()
            window.display.flush()
        sleep(0.1)
    thread.join()
    window.background.pool.destroy()
    window.overlay.pool.destroy()
    window.display.disconnect()


if __name__ == "__main__":
    main()
