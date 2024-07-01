# This file is part of the SLA firmware
# Copyright (C) 2021-2024 Prusa Development a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

from slafw.admin.control import AdminControl
from slafw.admin.items import AdminAction, AdminLabel, AdminBoolValue
from slafw.admin.menu import AdminMenu
from slafw.admin.safe_menu import SafeAdminMenu
from slafw.libPrinter import Printer
from slafw.states.wizard import WizardId
from slafw.wizard.wizard import SingleCheckWizard
from slafw.wizard.data_package import fill_wizard_data_package
from slafw.wizard.wizards.calibration import CalibrationWizard
from slafw.wizard.wizards.displaytest import DisplayTestWizard
from slafw.wizard.wizards.factory_reset import PackingWizard, FactoryResetWizard
from slafw.wizard.wizards.new_expo_panel import NewExpoPanelWizard
from slafw.wizard.wizards.self_test import SelfTestWizard
from slafw.wizard.wizards.sl1s_upgrade import SL1SUpgradeWizard, SL1DowngradeWizard
from slafw.wizard.wizards.unboxing import CompleteUnboxingWizard, KitUnboxingWizard
from slafw.wizard.wizards.uv_calibration import UVCalibrationWizard
from slafw.wizard.wizards.tank_surface_cleaner import TankSurfaceCleaner
from slafw.wizard.checks.uvfans import UVFansTest


class WizardsTestMenu(AdminMenu):
    def __init__(self, control: AdminControl, printer: Printer):
        super().__init__(control)
        self._printer = printer

        self.add_back()
        self.add_items(
            (
                AdminAction("Display test", self.api_display_test, "display_test_color"),
                AdminAction("Unpacking (C)", self.api_unpacking_c, "cover_color"),
                AdminAction("Unpacking (K)", self.api_unpacking_k, "cover_color"),
                AdminAction("Self test", self.api_self_test, "wizard_color"),
                AdminAction("Calibration", self.api_calibration, "calibration_color"),
                AdminAction("Factory reset", self.api_factory_reset, "factory_color"),
                AdminAction("Packing (Factory factory reset)", self.api_packing, "factory_color"),
                AdminAction(
                    "API UV Calibration wizard",
                    lambda: self._control.enter(TestUVCalibrationWizardMenu(self._control, self._printer)),
                    "uv_calibration"
                ),
                AdminAction("SL1S upgrade", self.sl1s_upgrade, "cover_color"),
                AdminAction("SL1 downgrade", self.sl1_downgrade, "cover_color"),
                AdminAction("Self-test - UV & fans test only", self.api_selftest_uvfans, "led_set_replacement"),
                AdminAction("Tank Surface Cleaner", self.tank_surface_cleaner, "clean-tank-icon"),
                AdminAction("New expo panel", self.new_expo_panel, "display_replacement")
            )
        )

    def api_display_test(self):
        self._printer.action_manager.start_wizard(DisplayTestWizard(fill_wizard_data_package(self._printer)))

    def api_unpacking_c(self):
        self._printer.action_manager.start_wizard(CompleteUnboxingWizard(fill_wizard_data_package(self._printer)))

    def api_unpacking_k(self):
        self._printer.action_manager.start_wizard(KitUnboxingWizard(fill_wizard_data_package(self._printer)))

    def api_self_test(self):
        self._printer.action_manager.start_wizard(SelfTestWizard(fill_wizard_data_package(self._printer)))

    def api_calibration(self):
        self._printer.action_manager.start_wizard(CalibrationWizard(fill_wizard_data_package(self._printer)))

    def api_packing(self):
        self._printer.action_manager.start_wizard(PackingWizard(fill_wizard_data_package(self._printer)))

    def api_factory_reset(self):
        self._printer.action_manager.start_wizard(FactoryResetWizard(fill_wizard_data_package(self._printer)))

    def sl1s_upgrade(self):
        self._printer.action_manager.start_wizard(SL1SUpgradeWizard(fill_wizard_data_package(self._printer)))

    def sl1_downgrade(self):
        self._printer.action_manager.start_wizard(SL1DowngradeWizard(fill_wizard_data_package(self._printer)))

    def api_selftest_uvfans(self):
        package = fill_wizard_data_package(self._printer)
        self._printer.action_manager.start_wizard(SingleCheckWizard(
            WizardId.SELF_TEST,
            UVFansTest(package),
            package,
            show_results=False))

    def tank_surface_cleaner(self):
        self._printer.action_manager.start_wizard(TankSurfaceCleaner(fill_wizard_data_package(self._printer)))

    def new_expo_panel(self):
        self._printer.action_manager.start_wizard(NewExpoPanelWizard(fill_wizard_data_package(self._printer)))


class TestUVCalibrationWizardMenu(SafeAdminMenu):
    def __init__(self, control: AdminControl, printer: Printer):
        super().__init__(control)
        self._lcd_replaced = False
        self._led_replaced = False
        self._printer = printer

        self.add_back()
        self.add_item(AdminLabel("UV Calibration wizard setup", "uv_calibration"))
        self.add_item(AdminBoolValue.from_value("LCD replaced", self, "_lcd_replaced", "display_replacement"))
        self.add_item(AdminBoolValue.from_value("LED replaced", self, "_led_replaced", "led_set_replacement"))
        self.add_item(AdminAction("Run calibration", self.run_calibration, "uv_calibration"))

    def run_calibration(self):
        self._control.pop()

        self._printer.action_manager.start_wizard(
            UVCalibrationWizard(
                fill_wizard_data_package(self._printer),
                display_replaced=self._lcd_replaced,
                led_module_replaced=self._led_replaced,
            )
        )
