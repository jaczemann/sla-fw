# This file is part of the SLA firmware
# Copyright (C) 2014-2018 Futur3d - www.futur3d.net
# Copyright (C) 2018-2019 Prusa Research s.r.o. - www.prusa3d.com
# Copyright (C) 2019-2022 Prusa Development a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import Dict
from abc import ABC, abstractmethod

from slafw import defines
from slafw.errors.errors import UnknownPrinterModel
from slafw.hardware.printer_options import PrinterOptions


class PrinterModelBase(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @property
    @abstractmethod
    def label_name(self) -> str:
        ...

    @property
    def extensions(self) -> set[str]:
        # TODO: remove code related to handling projects.
        # Filemanager should be the only one who takes care about files
        return {self.extension}

    @property
    def extension(self) -> str:
        # TODO: remove code related to handling projects.
        # Filemanager should be the only one who takes care about files
        return "." + str(self.name).lower()

    @property
    @abstractmethod
    def options(self) -> PrinterOptions:
        ...

    @property
    @abstractmethod
    def value(self) -> int:
        ...


class PrinterModelMeta(type):
    def __getattr__(cls, item):
        if item in cls.MODELS:
            return cls.MODELS[item]
        return super().__getattribute__(item)

    def __iter__(cls):
        return cls.MODELS.values().__iter__()


class PrinterModel(metaclass=PrinterModelMeta):
    # TODO: This mimics existing PrinterModel behaviour defined by enum. Maybe this is not the best way to handle
    # TODO: dynamic registration of models. Maybe a class factory method on base model would be more readable.
    MODELS: Dict[str, PrinterModelBase] = {}

    def __new__(cls):
        return cls.detect_model()

    @classmethod
    def register_model(cls, model: PrinterModelBase):
        cls.MODELS[model.name.upper()] = model

    @classmethod
    def detect_model(cls) -> PrinterModelBase:
        for model in cls.MODELS.values():
            if (defines.printer_model_run / model.name.lower()).exists():
                return model
        raise UnknownPrinterModel

    @property
    def extensions(self) -> set[str]:
        return set()


class PrinterModelNone(PrinterModelBase):
    @property
    def name(self) -> str:
        return "NONE"

    @property
    def label_name(self) -> str:
        return "NONE"

    @property
    def value(self) -> int:
        return 0

    @property
    def extension(self) -> str:
        return ""

    @property
    def options(self) -> PrinterOptions:
        return PrinterOptions(
            has_tilt=False,
            has_booster=False,
            vat_revision=0,
            has_UV_calibration=False,
            has_UV_calculation=False,
        )


class PrinterModelVirtual(PrinterModelBase):
    @property
    def name(self) -> str:
        return "VIRTUAL"

    @property
    def label_name(self) -> str:
        return "VIRTUAL"

    @property
    def value(self) -> int:
        return 999

    @property
    def extension(self) -> str:
        return ".sl1"

    @property
    def options(self) -> PrinterOptions:
        return PrinterOptions(
            has_tilt=False,
            has_booster=False,
            vat_revision=0,
            has_UV_calibration=False,
            has_UV_calculation=False,
        )


PrinterModel.register_model(PrinterModelNone())
PrinterModel.register_model(PrinterModelVirtual())
