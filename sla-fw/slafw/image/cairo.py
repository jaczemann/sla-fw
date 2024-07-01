# This file is part of the SLA firmware
# Copyright (C) 2022 Prusa Development a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

import functools
import cairo
import gi
gi.require_version('Rsvg', '2.0')
from gi.repository import Rsvg  # pylint: disable = wrong-import-position

def draftsman(function):
    @functools.wraps(function)
    def inner(data, width: int, height: int, *args):
        cf = cairo.Format.A8
        surface = cairo.ImageSurface.create_for_data(
                data,
                cf,
                width,
                height,
                cf.stride_for_width(width))
        function(
                cairo.Context(surface),
                width,
                height,
                *args)
        surface.finish()
    return inner

def _fill_white(ctx: cairo.Context):
    ctx.set_operator(cairo.Operator.OVER)
    ctx.set_source_rgba(1.0, 1.0, 1.0, 1.0)
    ctx.paint()

def _fill_black(ctx: cairo.Context):
    ctx.set_operator(cairo.Operator.DEST_OUT)
    ctx.set_source_rgba(1.0, 1.0, 1.0, 1.0)
    ctx.paint()

def _inverse(ctx: cairo.Context):
    ctx.set_operator(cairo.Operator.XOR)
    ctx.set_source_rgba(1.0, 1.0, 1.0, 1.0)
    ctx.paint()

def _offsets(size: int, width: int, height: int):
    offset_w = (width % size + size) // 2
    offset_h = (height % size + size) // 2
    return offset_w, offset_h

@draftsman
def draw_white(ctx: cairo.Context, width: int, height: int):
    # pylint: disable = unused-argument
    _fill_white(ctx)

@draftsman
def draw_chess(ctx: cairo.Context, width: int, height: int, size: int):
    _fill_white(ctx)
    ctx.set_operator(cairo.Operator.DEST_OUT)
    offset_w, offset_h = _offsets(size, width, height)
    for y in range(offset_h, height - offset_h, 2 * size):
        ctx.move_to(offset_w, y + size // 2)
        ctx.rel_line_to(width - 2 * offset_w, 0)
        ctx.set_dash((size,), size)
        ctx.set_line_width(size)
    ctx.stroke()
    for y in range(offset_h + size, height - offset_h, 2 * size):
        ctx.move_to(offset_w, y + size // 2)
        ctx.rel_line_to(width - 2 * offset_w, 0)
        ctx.set_dash((size,), 0)
        ctx.set_line_width(size)
    ctx.stroke()

@draftsman
def draw_grid(ctx: cairo.Context, width: int, height: int, square: int, line: int):
    _fill_white(ctx)
    ctx.set_operator(cairo.Operator.DEST_OUT)
    size = square + line
    offset_w, offset_h = _offsets(size, width, height)
    for y in range(offset_h, height - offset_h, size):
        ctx.move_to(offset_w, y + square / 2)
        ctx.rel_line_to(width - 2 * offset_w, 0)
        ctx.set_dash((square, line), 0)
        ctx.set_line_width(square)
    ctx.stroke()

@draftsman
def draw_gradient(ctx: cairo.Context, width: int, height: int, vertical: bool):
    _fill_white(ctx)
    ctx.set_operator(cairo.Operator.DEST_OUT)
    pat = cairo.LinearGradient(0, 0, width * (not vertical), height * vertical)
    pat.add_color_stop_rgba(0.0, 0.0, 0.0, 0.0, 0.0)
    pat.add_color_stop_rgba(1.1, 1.0, 1.0, 1.0, 1.0)
    ctx.set_source(pat)
    ctx.paint()

@draftsman
def inverse(ctx: cairo.Context, width: int, height: int):
    # pylint: disable = unused-argument
    _inverse(ctx)

@draftsman
def draw_svg_expand(ctx: cairo.Context, width: int, height: int, image_path: str, invert: bool):
    _fill_black(ctx)
    ctx.set_operator(cairo.Operator.XOR)
    svg = Rsvg.Handle().new_from_file(image_path)
    viewport = Rsvg.Rectangle()
    viewport.x = 0
    viewport.y = 0
    viewport.width = width
    viewport.height = height
    svg.render_document(ctx, viewport)
    if invert:
        _inverse(ctx)

@draftsman
def draw_svg_dpi(ctx: cairo.Context, width: int, height: int, image_path: str, invert: bool, dpi: float):
    # pylint: disable = too-many-arguments
    _fill_black(ctx)
    ctx.set_operator(cairo.Operator.XOR)
    svg = Rsvg.Handle().new_from_file(image_path)
    svg.set_dpi(dpi)
    result = svg.get_intrinsic_size_in_pixels()
    if not result[0]:
        raise RuntimeError("No size information in SVG")
    svg_width_px = round(result[1])
    svg_heigt_px = round(result[2])
    if svg_width_px > width or svg_heigt_px > height:
        raise RuntimeError(f"Wrong image size ({svg_width_px}, {svg_heigt_px}), max. ({width}, {height})")
    viewport = Rsvg.Rectangle()
    viewport.x = (width - svg_width_px) // 2
    viewport.y = (height - svg_heigt_px) // 2
    viewport.width = svg_width_px
    viewport.height = svg_heigt_px
    svg.render_document(ctx, viewport)
    if invert:
        _inverse(ctx)
