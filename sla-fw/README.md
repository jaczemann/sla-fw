# sla-fw
High level firmware for SL1 3D printer

# Testing

## Pre Requestments

In order to run the tests a simulator of the motion controller is needed. The sources of the simulator are included
as a submodule. The binary is build using a script:

	$ build_sim.sh


## Unittests

Unitests test standalone components while providing mock implementation for other components necessary to run the test.
Unittests are executed using a shell script:

	$ unittest.sh


## Integration tests

Integration tests test the system as a whole. External dependencies as mocked and motion controller is replaced by its
simulation. Rest of the system runs as close to the real deployment as possible. In order to isolate the test
environment from the rest of the system the most of the integration tests run using a dedicated dbus session.
Integration tests include a test of a virtual printer running using a system dbus. Integration tests are executed using
a script:

	$ integrationtest.sh


## Pylint

To check the source code using pylint use the script:

	$ pylint.sh


# Virtual printer

In order to do a quick test of the sla-fw functionality a python script virtual.py can be used to execute a virtual
printer. This one runs in an environment similar to the integration tests while allowing for cooperation with touch-ui
and full control over system dbus. In order to use the virtual printer:

 - it is necessary to have all dbus control files
installed and adjusted to allow the current user to own sl1 dbus names. It should be enough to copy provided virtual 
dbus config to your system: ```$ cp cz.prusa3d.virtual-sla.conf /etc/dbus-1/system.d/cz.prusa3d.virtual-sla.conf```
 - create printer model file in `/run/model` folder. Created file is lowercase name of 
   [PrinterModel](slafw/hardware/printer_model.py) Enum class. Example for SL1S:
   ```$ mkdir /run/model && touch /run/model/sl1s``` 
