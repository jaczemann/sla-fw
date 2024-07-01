# This file is part of the SLA firmware
# Copyright (C) 2022-2024 Prusa Development a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

from typing import Collection, Optional
from pathlib import Path
from time import sleep
import re

from slafw.defines import dataPath
from slafw.libPrinter import Printer
from slafw.hardware.profiles import SingleProfile, ProfileSet
from slafw.admin.control import AdminControl
from slafw.admin.items import (
    AdminItem,
    AdminLabel,
    AdminAction,
    AdminIntValue,
    AdminSelectionValue,
    AdminBoolValue,
    AdminFixedValue,
)
from slafw.admin.safe_menu import SafeAdminMenu
from slafw.admin.menu import AdminMenu
from slafw.admin.menus.dialogs import Info, Error
from slafw.hardware.axis import Axis
from slafw.hardware.tower import MovingProfilesTower
from slafw.hardware.tilt import MovingProfilesTilt
from slafw.hardware.power_led_action import WarningAction
from slafw.functions.files import get_save_path, get_export_file_name
from slafw.errors.errors import NoExternalStorage, TiltHomeFailed
from slafw.configs.value import ProfileIndex, BoolValue, TextValue
from slafw.configs.unit import Nm, Ms

CAMEL2SNAKE = re.compile(r'(?<!^)(?=[A-Z])')

def pretty_name(name: str) -> str:
    name = CAMEL2SNAKE.sub('_', name).lower()
    for replace in (("_", " "), (" ms", " [s]"), (" nm", " [mm]")):
        name = name.replace(*replace)
    return name.capitalize()


class Profiles(SafeAdminMenu):
    def __init__(self, control: AdminControl, printer: Printer, pset: ProfileSet, axis: Optional[Axis] = None):
        super().__init__(control)
        self._printer = printer
        self._pset = pset

        self.add_back()
        self.add_items(
            (
                AdminAction(
                    f"Edit {pset.name}",
                    lambda: self.enter(EditProfiles(self._control, printer, pset, axis)),
                    "edit_white"
                ),
                AdminAction(
                    f"Import {pset.name}",
                    lambda: self.enter(ImportProfiles(self._control, pset)),
                    "save_color"
                ),
                AdminAction(f"Save {pset.name} to USB drive", self.save_to_usb, "usb_color"),
                AdminAction(f"Restore to factory {pset.name}", self.factory_profiles, "factory_color"),
            )
        )

    @SafeAdminMenu.safe_call
    def save_to_usb(self):
        save_path = get_save_path()
        if save_path is None or not save_path.parent.exists():
            raise NoExternalStorage()
        model_name = self._printer.hw.printer_model.name    # type: ignore[attr-defined]
        fn = f"{self._pset.name.replace(' ', '_')}-{model_name}.{get_export_file_name(self._printer.hw)}.json"
        self._pset.write_factory(save_path / fn, nondefault=True)
        self._control.enter(Info(self._control, headline=f"{self._pset.name.capitalize()} saved to:", text=fn))

    @SafeAdminMenu.safe_call
    def factory_profiles(self):
        self._pset.factory_reset(True)
        self._pset.write_factory()
        self._pset.apply_all()
        self._control.enter(Info(self._control, text=f"{self._pset.name.capitalize()} restored"))


class EditProfiles(AdminMenu):
    def __init__(self, control: AdminControl, printer: Printer, pset: ProfileSet, axis: Optional[Axis] = None):
        super().__init__(control)
        self.add_back()
        self.add_items(self._get_items(printer, pset, axis))

    def _get_items(self, printer: Printer, pset: ProfileSet, axis: Optional[Axis] = None) -> Collection[AdminItem]:
        if isinstance(pset, (MovingProfilesTilt, MovingProfilesTower)):
            icon = "steppers_color"
        else:
            icon = ""
        for profile in pset:
            yield AdminAction(pretty_name(profile.name), self._get_callback(printer, pset, profile, axis), icon)

    def _get_callback(self,
            printer: Printer,
            pset: ProfileSet,
            profile: SingleProfile,
            axis: Optional[Axis] = None):
        return lambda: self._control.enter(EditProfileItems(self._control, printer, pset, profile, axis))


class EditProfileItems(SafeAdminMenu):
    # pylint: disable = too-many-arguments
    def __init__(self,
            control: AdminControl,
            printer: Printer,
            pset: ProfileSet,
            profile: SingleProfile,
            axis: Optional[Axis] = None):
        super().__init__(control)
        self._printer = printer
        self._axis = axis
        self._pset = pset
        self._profile = profile
        self._temp_profile = None
        self._temp = profile.get_writer()
        self.add_back()
        if isinstance(self._pset, (MovingProfilesTilt, MovingProfilesTower)):
            self.add_items(
                (
                    AdminAction("Test profile", self.test_profile, "touchscreen-icon"),
                    AdminAction("Release motors", printer.hw.motors_release, "disable_steppers_color"),
                )
            )
        self.add_items(self._get_items(profile))

    def _get_items(self, profile: SingleProfile) -> Collection[AdminItem]:
        for value in profile:
            name = pretty_name(value.key)
            if isinstance(value, ProfileIndex):
                yield AdminSelectionValue.from_value(
                        name, self._temp, value.key, [pretty_name(n) for n in value.options], True, "edit_white")
            elif isinstance(value, BoolValue):
                yield AdminBoolValue.from_value(name, self._temp, value.key, "edit_white")
# TODO python 3.10
#            elif value.unit is not None and issubclass(value.unit, Nm | Ms):
            elif value.unit is not None and any((issubclass(value.unit, Nm), issubclass(value.unit, Ms))):
                yield AdminFixedValue.from_value(name, self._temp, value.key, icon="edit_white")
            elif isinstance(value, TextValue):
                yield AdminLabel.from_value(name, self._temp, value.key, "edit_white")
            else:
                yield AdminIntValue.from_value(name, self._temp, value.key, 1, "edit_white")

    def on_leave(self):
        self._temp.commit()
        self._pset.apply_all()

    @SafeAdminMenu.safe_call
    def test_profile(self):
        self._temp_profile = type(self._pset[self._profile.idx])()
        self._temp_profile.name = "temporary"
        self._temp_profile.idx = -1
        for val in self._temp_profile.get_values().values():
            val.set_value(self._temp_profile, getattr(self._temp, val.key))
        if isinstance(self._pset, (MovingProfilesTilt, MovingProfilesTower)):
            self._axis.actual_profile = self._temp_profile
            getattr(self._control, f"{self._axis.name}_moves")()
        else:
            raise RuntimeError(f"Unknown profiles type: {type(self._pset)}")

    def _sync(self, axis: Axis):
        if not axis.synced:
            try:
                axis.sync_ensure()
            except TiltHomeFailed:
                self._control.enter(Error(self._control, text=f"Failed to home {axis.name}"))
                return False
        return True

    def _do_layer_profile_test(self, status: AdminLabel):
        status.set("Moving to start positions")
        hw = self._printer.hw
        with WarningAction(hw.power_led):
            if self._sync(hw.tower) and self._sync(hw.tilt):
                tower_position = Nm(100_000_000)
                hw.tower.actual_profile = hw.tower.profiles.moveFast
                hw.tower.move(tower_position)
                hw.tilt.actual_profile = hw.tilt.profiles.move8000
                hw.tilt.move(hw.tilt.config_height_position)
                while hw.tower.moving or hw.tilt.moving:
                    sleep(0.25)
                status.set(f"Testing profile {self._profile.name}")
                sleep(1)
                hw.beepEcho()
                hw.tilt.layer_peel_moves(self._temp_profile, tower_position + Nm(50000), last_layer=False)
                hw.beepEcho()
                status.set("Done")
                sleep(1)
                hw.tower.move(tower_position)


class ImportProfiles(SafeAdminMenu):
    def __init__(self, control: AdminControl, pset: ProfileSet):
        super().__init__(control)
        self._pset = pset
        self.add_back()
        usb_path = get_save_path()
        basename = self._pset.name.replace(' ', '_')
        if usb_path is None:
            self.add_label("USB not present. To get files from USB, plug the USB\nand re-enter.", "error_small_white")
        else:
            self.add_label("<b>USB</b>", "usb_color")
            self.list_files(usb_path, [f"**/*{basename}*.json"], self._import_profile, "usb_color")
        self.add_label("<b>Internal</b>", "factory_color")
        self.list_files(Path(dataPath), [f"**/*{basename}*.json"], self._import_profile, "factory_color")

    @SafeAdminMenu.safe_call
    def _import_profile(self, path: Path, name: str):
        fullname = path / name
        if not fullname.exists():
            raise FileNotFoundError(f"Profiles file not found: {name}")
        self._pset.read_file_raw(fullname, factory=True)
        self._pset.write_factory()
        self._pset.apply_all()
        self._control.enter(Info(self._control, text="Profiles loaded", pop=2))
