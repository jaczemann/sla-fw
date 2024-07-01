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
import cairo
#import math
import gi
gi.require_version('Rsvg', '2.0')
from gi.repository import Rsvg

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
    def stride(self):
        return cairo.Format.ARGB32.stride_for_width(self.width)

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
        draw_cairo(bg)
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
    size = surface_data.stride * surface_data.height

    if surface_data.pool:
        surface_data.pool.destroy()

    with AnonymousFile(size) as fd:
        surface_data.shm_data = mmap.mmap(
            fd, size, prot=mmap.PROT_READ | mmap.PROT_WRITE, flags=mmap.MAP_SHARED
        )
        surface_data.pool = shm.create_pool(fd, size)


def create_buffer(surface_data):
    print("-> create_buffer %dx%d" % (surface_data.width, surface_data.height))
    return surface_data.pool.create_buffer(0, surface_data.width, surface_data.height, surface_data.stride, WlShm.format.argb8888.value)


def draw_cairo(surface_data):
    surface = cairo.ImageSurface.create_for_data(
            surface_data.shm_data,
            cairo.Format.ARGB32,
            surface_data.width,
            surface_data.height,
            surface_data.stride)
    ctx = cairo.Context(surface)
    # fill with white
    ctx.rectangle(0, 0, surface_data.width, surface_data.height);
    ctx.set_source_rgb(1.0, 1.0, 1.0);
    ctx.fill()
    # draw transparent logo
    svg = Rsvg.Handle().new_from_file("../data/logo.svg")
    svg.set_dpi(300)
    print(svg.get_intrinsic_size_in_pixels())
    viewport = Rsvg.Rectangle()
    viewport.x = 0
    viewport.y = 0
    viewport.width = surface_data.width
    viewport.height = surface_data.height
    svg.render_document(ctx, viewport)
    surface.finish()


#def draw_cairo(surface_data):
#    surface = cairo.ImageSurface.create_for_data(
#            surface_data.shm_data,
#            cairo.Format.ARGB32,
#            surface_data.width,
#            surface_data.height,
#            surface_data.stride)
#
#    ctx = cairo.Context(surface)
#    ctx.scale(surface_data.width, surface_data.height)
#
#    pat = cairo.LinearGradient(0.0, 0.0, 0.0, 1.0)
#    pat.add_color_stop_rgba(1, 0.7, 0, 0, 0.5)  # First stop, 50% opacity
#    pat.add_color_stop_rgba(0, 0.9, 0.7, 0.2, 1)  # Last stop, 100% opacity
#
#    ctx.rectangle(0, 0, 1, 1)  # Rectangle(x0, y0, x1, y1)
#    ctx.set_source(pat)
#    ctx.fill()
#
#    ctx.translate(0.1, 0.1)  # Changing the current transformation matrix
#
#    ctx.move_to(0, 0)
#    # Arc(cx, cy, radius, start_angle, stop_angle)
#    ctx.arc(0.2, 0.1, 0.1, -math.pi / 2, 0)
#    ctx.line_to(0.5, 0.1)  # Line to (x,y)
#    # Curve(x1, y1, x2, y2, x3, y3)
#    ctx.curve_to(0.5, 0.2, 0.5, 0.4, 0.2, 0.8)
#    ctx.close_path()
#
#    ctx.set_source_rgb(0.3, 0.2, 0.5)  # Solid color
#    ctx.set_line_width(0.02)
#    ctx.stroke()
#
#    surface.finish()


def event_loop(window):
    while window.display.dispatch(block=True) != -1 and not window.closed:
        pass


def main():
    print("PyCairo version: %s" % cairo.version)
    print("Cairo version: %s" % cairo.cairo_version_string())
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

    window.background = Layer(200, 320)
    window.background.surface.append(Surface(window.compositor))
    bg_wl_surface = window.background.base_wl_surface

    xdg_surface = window.wm_base.get_xdg_surface(bg_wl_surface)
    xdg_surface.dispatcher["configure"] = xdg_surface_configure_handler
    xdg_surface.user_data = window

    xdg_toplevel = xdg_surface.get_toplevel()
    xdg_toplevel.set_title("Example python cairo")
    xdg_toplevel.dispatcher["configure"] = xdg_toplevel_configure_handler
    xdg_toplevel.dispatcher["close"] = xdg_toplevel_close_handler
    xdg_toplevel.user_data = window

    bg_wl_surface.commit()

    while window.display.dispatch(block=True) != -1 and not window.closed:
        pass

    window.background.pool.destroy()
    window.display.disconnect()


if __name__ == "__main__":
    main()
