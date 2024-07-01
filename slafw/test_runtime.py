# This file is part of the SLA firmware
# Copyright (C) 2020 Prusa Research a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Runtime test data

Used to share information among different mock objects and production code
"""

from datetime import datetime
from typing import Optional

testing = False
test_uvmeter_present = True
injected_preprint_warning = None
uv_pwm = 0
uv_on_until: Optional[datetime] = None
exposure_image = None
uv_error_each = 0
