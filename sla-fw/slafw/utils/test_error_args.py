from pydbus import SystemBus
import pydbus
import sys
a = SystemBus().get("cz.prusa3d.sl1.admin0")
a.enter()
i = SystemBus().get("cz.prusa3d.sl1.admin0", '/cz/prusa3d/sl1/admin0/Items/Firmware')
i.execute()
i = pydbus.SystemBus().get("cz.prusa3d.sl1.admin0", '/cz/prusa3d/sl1/admin0/Items/Firmware_tests')
i.execute()
i = pydbus.SystemBus().get("cz.prusa3d.sl1.admin0", '/cz/prusa3d/sl1/admin0/Items/Errors_test')
i.execute()

"""
if bool(sys.argv[1:]):
    i = pydbus.SystemBus().get("cz.prusa3d.sl1.admin0", '/cz/prusa3d/sl1/admin0/Items/_10127___FAN_RPM_OUT_OF_TEST_RANGE_e10127_FanRpmOutOfTestRangeId')
    i.execute()
else:
    i = pydbus.SystemBus().get("cz.prusa3d.sl1.admin0", '/cz/prusa3d/sl1/admin0/Items/_10127___FAN_RPM_OUT_OF_TEST_RANGE_e10127_FanRPMOutOfTestRange')
    i.execute()
"""

i = pydbus.SystemBus().get("cz.prusa3d.sl1.admin0", "/cz/prusa3d/sl1/admin0/Items/_10702___AMBIENT_TEMP__TOO_HIGH_e10702_AmbientTooHotWarning")
i.execute()
for child in a.children:
    print(child)
