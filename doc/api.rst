SL1 DBus API Example
====================

Printer0 D-Bus API together with Exposure0 D-Bus API is used to start and control the print. The following short example
demonstrate print start and monitoring using the ssh connection to the development printer. The development printer (
booted from the dev SD card) has password-less access configured for the root user. The Python code in the example is
using pydbus library included in the printer system.

First open the ssh connection and start a Python interpreter:

.. code-block:: shell

    $ ssh root@PRINTER_IP_HERE
    $ python3

Now control the printer using the Python interpreter:

.. code-block:: python

    # Import pydbus and resolve printer0 object
    >>> import pydbus
    >>> printer = pydbus.SystemBus().get("cz.prusa3d.sl1.printer0")

    # List available projects
    >>> printer.list_projects_raw()
    ['/some/path/some_object.sl1', '/another/path/another_project.sl1']

    # Start print of a project
    # Any filesystem path should work. For stable prints use local filesystem projects.
    # Passing True instead of False will start print without the project settings screen
    path = printer.print("/path/to/project.sl1", False)

    # Now print exposure is initiated
    # The path variable holds D-Bus object path of the new exposure object
    exposure = pydbus.SystemBus().get("cz.prusa3d.sl1.printer0", path)

    # The exposure can be inspected and configured
    >>> print(f"Layer height {exposure.layer_height_nm} nm")
    Layer height 50000 nm
    >>> print(f"Total height {exposure.total_nm} nm")
    Total height 100000 nm
    >>> print(f"Original exposure time {exposure.exposure_time_ms} ms")
    Original exposure time 1000 ms
    >>> exposure.exposure_time_ms = 1500
    >>> print(f"New exposure time {exposure.exposure_time_ms} ms")
    New exposure time 1500 ms

    # Once configured, the print is started by confirming the configuration
    exposure.confirm_start()

    # Properties of the exposure object are updated as the print is running
    # The basic ones are the state and the progress
    >>> print(f"Current progress {exposure.progress} %")
    Current progress 100.0 %
    >>> print(f"Current state {exposure.state}")
    Current state 11

    # Numeric state can be decoded using the state enum
    >>> from slafw.api.exposure0 import Exposure0State
    >>> print(f"Current state {Exposure0State(exposure.state)}")
    Current state Exposure0State.FINISHED

    # If necessary the exposure can be canceled
    >>> exposure.cancel()

The properties of the printer0 and exposure0 objects have change signals attached.
It is possible to react to property changes:

.. code-block:: python

    # Import pydbus, printer state for printer0 API access
    >>> import pydbus
    >>> from slafw.api.printer0 import Printer0State
    # Import GLib, Thread for DBus event loop
    >>> from gi.repository import GLib
    >>> from threading import Thread

    # Start a new thread to run callbacks registered on property changes
    >>> Thread(target=GLib.MainLoop().run, daemon=True).start()

    # Register print function as printer0 state change callback
    >>> printer.PropertiesChanged.connect(print)
    <pydbus.subscription.Subscription object at 0x7f4eab75b780>

    # As the printer state changes the states are printed
    >>> cz.prusa3d.sl1.printer0 {'state': 6} []
    cz.prusa3d.sl1.printer0 {'state': 1} []
    cz.prusa3d.sl1.printer0 {'state': 6} []

    # Similarly to the exposure states the printer states can be decoded
    >>> from slafw.api.printer0 import Printer0State
    >>> def decode(_, prop, __):
    ...     if "state" in prop:
    ...             print(Printer0State(prop["state"]))
    ...
    >>> printer.PropertiesChanged.connect(decode)

    # Now the printer states are printed as enums
    >>> Printer0State.PRINTING
    Printer0State.IDLE
    Printer0State.PRINTING
    Printer0State.IDLE

Please see :doc:`/printer0` and :doc:`/exposure0` for details.
