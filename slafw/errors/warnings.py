# This file is part of the SLA firmware
# Copyright (C) 2014-2018 Futur3d - www.futur3d.net
# Copyright (C) 2018-2020 Prusa Research s.r.o. - www.prusa3d.com
# Copyright (C) 2022 Prusa Research a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

from dataclasses import dataclass, is_dataclass, asdict
from typing import Dict, Tuple, Any

from prusaerrors.sl1.codes import Sl1Codes

from slafw.errors.errors import with_code


@with_code(Sl1Codes.UNKNOWN)
@dataclass(frozen=True)
class PrinterWarning(Warning):

    @staticmethod
    def as_dict(warning: Warning) -> Dict[str, Any]:
        """
        Wrap warning in dictionary

        Warning is represented as dictionary str -> variant
        {
            "code": warning code
            "code_specific_feature1": value1
            "code_specific_feature2": value2
            ...
        }

        :param warning: Warning to wrap
        :return: Warning dictionary
        """
        if not warning:
            return {"code": Sl1Codes.NONE_WARNING.code}

        if isinstance(warning, PrinterWarning):
            ret = {"code": warning.CODE.code, "name": type(warning).__name__, "text": str(warning)}  # type: ignore
            if is_dataclass(warning):
                ret.update(asdict(warning))
            return ret

        return {"code": Sl1Codes.UNKNOWN_WARNING.code, "name": type(warning).__name__, "text": str(warning)}


@dataclass(frozen=True)
class ExposureWarning(PrinterWarning):
    """
    Base for exposure warnings
    """


@dataclass(frozen=True)
class AmbientTemperatureOutOfRange(ExposureWarning):
    ambient_temperature: float


@with_code(Sl1Codes.AMBIENT_TOO_HOT_WARNING)
@dataclass(frozen=True)
class AmbientTooHot(AmbientTemperatureOutOfRange):
    pass


@with_code(Sl1Codes.AMBIENT_TOO_COLD_WARNING)
@dataclass(frozen=True)
class AmbientTooCold(AmbientTemperatureOutOfRange):
    pass


@with_code(Sl1Codes.PRINTING_DIRECTLY_WARNING)
@dataclass(frozen=True)
class PrintingDirectlyFromMedia(ExposureWarning):
    pass


# no longer used
#@with_code(Sl1Codes.PERPARTES_NOAVAIL_WARNING)
#@dataclass(frozen=True)
#class PerPartesPrintNotAvaiable(ExposureWarning):
#    pass


@with_code(Sl1Codes.MASK_NOAVAIL_WARNING)
@dataclass(frozen=True)
class PrintMaskNotAvaiable(ExposureWarning):
    pass


@with_code(Sl1Codes.OBJECT_CROPPED_WARNING)
@dataclass(frozen=True)
class PrintedObjectWasCropped(ExposureWarning):
    pass


@with_code(Sl1Codes.PRINTER_VARIANT_MISMATCH_WARNING)
@dataclass(frozen=True)
class VariantMismatch(ExposureWarning):
    printer_variant: str
    project_variant: str


@with_code(Sl1Codes.RESIN_NOT_ENOUGH_WARNING)
@dataclass(frozen=True)
class ResinNotEnough(ExposureWarning):
    measured_resin_ml: float
    required_resin_ml: float


@with_code(Sl1Codes.RESIN_LOW)
class ResinLow(ExposureWarning):
    ...


@with_code(Sl1Codes.PROJECT_SETTINGS_MODIFIED_WARNING)
@dataclass(frozen=True)
class ProjectSettingsModified(ExposureWarning):
    changes: Dict[str, Tuple[Any, Any]]


# TODO: Add code
@dataclass(frozen=True)
class WrongA64SerialFormat(PrinterWarning):
    sn: str


# TODO: Add code
@dataclass(frozen=True)
class WrongMCSerialFormat(PrinterWarning):
    sn: str


# TODO: Add code
@dataclass(frozen=True)
class FactoryResetCheckFailure(PrinterWarning):
    message: str


@with_code(Sl1Codes.FAN_WARNING)
@dataclass(frozen=True)
class FanWarning(ExposureWarning):
    failed_fans_text: str


@with_code(Sl1Codes.EXPECT_OVERHEATING)
@dataclass(frozen=True)
class ExpectOverheating(ExposureWarning):
    failed_fans_text: str
