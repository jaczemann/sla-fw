# This file is part of the SLA firmware
# Copyright (C) 2021-2022 Prusa Development a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

from datetime import timedelta
from itertools import chain
from functools import partial
from pathlib import Path

from slafw import defines
from slafw.libPrinter import Printer
from slafw.admin.control import AdminControl
from slafw.admin.items import AdminAction, AdminBoolValue
from slafw.admin.safe_menu import SafeAdminMenu
from slafw.admin.menus.dialogs import Info, Confirm
from slafw.functions import files, generate
from slafw.image import cairo


class ExposureDisplayMenu(SafeAdminMenu):
    def __init__(self, control: AdminControl, printer: Printer):
        super().__init__(control)
        self._printer = printer

        self.add_back()
        self.add_items(
            (
                AdminAction(
                    "Exposure display control",
                    lambda: self._control.enter(DisplayControlMenu(self._control, self._printer)),
                    "display_test_color"
                ),
                AdminAction("Display usage heatmap", self.display_usage_heatmap, "frequency"),
                AdminAction(
                    "Show UV calibration data",
                    lambda: self._control.enter(ShowCalibrationMenu(self._control)),
                    "logs-icon"
                ),
                AdminAction("Erase display counter", self.erase_display_counter, "display_replacement"),
                AdminAction("Erase UV LED counter", self.erase_uv_led_counter, "led_set_replacement"),
            )
        )

    @SafeAdminMenu.safe_call
    def erase_uv_led_counter(self):
        self.logger.info("About to erase UV LED statistics")
        self.logger.info("Current statistics UV LED usage seconds %s", self._printer.hw.uv_led.usage_s)
        self._control.enter(
            Confirm(
                self._control,
                self._do_erase_uv_led_counter,
                headline="Do you really want to clear the UV LED counter?",
                text=f"UV counter: {timedelta(seconds=self._printer.hw.uv_led.usage_s)}\n"
                f"Serial number: {self._printer.hw.cpuSerialNo}\n"
                f"IP address: {self._printer.inet.ip}",
            )
        )

    def _do_erase_uv_led_counter(self):
        self._printer.hw.uv_led.clear_usage()
        self._control.enter(
            Info(
                self._control,
                headline="UV counter has been erased.",
                text=f"UV counter: {timedelta(seconds=self._printer.hw.uv_led.usage_s)}\n"
                f"Serial number: {self._printer.hw.cpuSerialNo}\n"
                f"IP address: {self._printer.inet.ip}",
            )
        )

    @SafeAdminMenu.safe_call
    def erase_display_counter(self):
        self.logger.info("About to erase display statistics")
        self.logger.info("Current UV LED usage %d seconds", self._printer.hw.uv_led.usage_s)
        self.logger.info("Current display usage %d seconds", self._printer.hw.exposure_screen.usage_s)

        self._control.enter(
            Confirm(
                self._control,
                self._do_erase_display_counter,
                headline="Do you really want to clear the Display counter?",
                text=f"Display counter: {timedelta(seconds=self._printer.hw.exposure_screen.usage_s)}\n"
                f"Serial number: {self._printer.hw.cpuSerialNo}\n"
                f"IP address: {self._printer.inet.ip}",
            )
        )

    def _do_erase_display_counter(self):
        self._printer.hw.exposure_screen.clear_usage()
        self._control.enter(
            Info(
                self._control,
                headline="Display counter has been erased.",
                text=f"Display counter: {timedelta(seconds=self._printer.hw.exposure_screen.usage_s)}\n"
                f"Serial number: {self._printer.hw.cpuSerialNo}\n"
                f"IP address: {self._printer.inet.ip}",
            )
        )

    @SafeAdminMenu.safe_call
    def display_usage_heatmap(self):
        generate.display_usage_heatmap(
                self._printer.hw.exposure_screen.parameters,
                defines.displayUsageData,
                defines.displayUsagePalette,
                defines.fullscreenImage)
        self._control.fullscreen_image()


class ShowCalibrationMenu(SafeAdminMenu):
    def __init__(self, control: AdminControl):
        super().__init__(control)

        self.add_back()
        data_paths = (
                defines.wizardHistoryPathFactory.glob("uvcalib_data.*"),
                defines.wizardHistoryPathFactory.glob("uvcalibrationwizard_data.*"),
                defines.wizardHistoryPathFactory.glob("uv_calibration_data.*"),
                defines.wizardHistoryPathFactory.glob(f"{defines.manual_uvc_filename}.*"),
                defines.wizardHistoryPath.glob("uvcalib_data.*"),
                defines.wizardHistoryPath.glob("uvcalibrationwizard_data.*"),
                defines.wizardHistoryPath.glob("uv_calibration_data.*"),
                )
        filenames = sorted(list(chain(*data_paths)), key=lambda path: path.stat().st_mtime, reverse=True)
        if filenames:
            for fn in filenames:
                prefix = "F:" if fn.parent == defines.wizardHistoryPathFactory else "U:"
                self.add_item(AdminAction(prefix + fn.name, partial(self.show_calibration, fn), "logs-icon"))
        else:
            self.add_label("(no data)", "info_off_small_white")

    @SafeAdminMenu.safe_call
    def show_calibration(self, filename):
        generate.uv_calibration_result(None, filename, defines.fullscreenImage)
        self._control.fullscreen_image()


class DisplayControlMenu(SafeAdminMenu):
    def __init__(self, control: AdminControl, printer: Printer):
        super().__init__(control)
        self._printer = printer

        self.add_back()
        self.add_items(
            (
                AdminBoolValue("UV", self.get_uv, self.set_uv, "uv_calibration"),
                AdminAction("Open screen", self.open, "display_test_color"),
                AdminAction("Close screen", self.close, "display_test_color"),
                AdminAction("Inverse", self.invert, "display_test_color"),
                AdminAction("Chess 8", self.chess_8, "display_test_color"),
                AdminAction("Chess 16", self.chess_16, "display_test_color"),
                AdminAction("Grid 8", self.grid_8, "display_test_color"),
                AdminAction("Grid 16", self.grid_16, "display_test_color"),
                AdminAction("Gradient vertical", self.gradient_vertical, "display_test_color"),
                AdminAction("Gradient horizontal", self.gradient_horizontal, "display_test_color"),
                AdminAction("Prusa logo", self.prusa_logo, "display_test_color"),
                AdminAction(
                    "file from USB",
                    lambda: self._control.enter(UsbFileMenu(self._control, self._printer)),
                    "usb_color"
                ),
            )
        )

    def on_leave(self):
        self._printer.hw.uv_led.save_usage()

    def get_uv(self):
        return self._printer.hw.uv_led.active

    def set_uv(self, enabled: bool):
        if enabled:
            self._printer.hw.start_fans()
            self._printer.hw.uv_led.pwm = self._printer.hw.config.uvPwmPrint  # use final UV PWM, due to possible test
            self._printer.hw.uv_led.on()
        else:
            self._printer.hw.stop_fans()
            self._printer.hw.uv_led.off()

    @SafeAdminMenu.safe_call
    def open(self):
        self._printer.exposure_image.open_screen()

    @SafeAdminMenu.safe_call
    def close(self):
        self._printer.exposure_image.blank_screen()

    @SafeAdminMenu.safe_call
    def invert(self):
        self._printer.hw.exposure_screen.draw_pattern(cairo.inverse)

    @SafeAdminMenu.safe_call
    def chess_8(self):
        self._printer.hw.exposure_screen.draw_pattern(cairo.draw_chess, 8)

    @SafeAdminMenu.safe_call
    def chess_16(self):
        self._printer.hw.exposure_screen.draw_pattern(cairo.draw_chess, 16)

    @SafeAdminMenu.safe_call
    def grid_8(self):
        self._printer.hw.exposure_screen.draw_pattern(cairo.draw_grid, 7, 1)

    @SafeAdminMenu.safe_call
    def grid_16(self):
        self._printer.hw.exposure_screen.draw_pattern(cairo.draw_grid, 14, 2)

    @SafeAdminMenu.safe_call
    def gradient_horizontal(self):
        self._printer.hw.exposure_screen.draw_pattern(cairo.draw_gradient, False)

    @SafeAdminMenu.safe_call
    def gradient_vertical(self):
        self._printer.hw.exposure_screen.draw_pattern(cairo.draw_gradient, True)

    @SafeAdminMenu.safe_call
    def prusa_logo(self):
        self._printer.hw.exposure_screen.draw_pattern(cairo.draw_svg_expand, defines.prusa_logo_file, True)


class UsbFileMenu(SafeAdminMenu):
    def __init__(self, control: AdminControl, printer: Printer):
        super().__init__(control)
        self._printer = printer
        self.add_back()
        usb_path = files.get_save_path()
        if usb_path is None:
            self.add_label("USB not present. To get files from USB, plug the USB\nand re-enter.", "error_small_white")
        else:
            self.list_files(usb_path, ["**/*.png", "**/*.svg"], self._usb_test, "usb_color")

    @SafeAdminMenu.safe_call
    def _usb_test(self, path: Path, name: str):
        fullname = path / name
        if not fullname.exists():
            raise FileNotFoundError(f"Test image not found: {name}")
        if fullname.suffix == ".svg":
            es = self._printer.hw.exposure_screen
            es.draw_pattern(cairo.draw_svg_dpi, str(fullname), False, es.parameters.dpi)
        else:
            self._printer.exposure_image.show_image_with_path(str(fullname))
