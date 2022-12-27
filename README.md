# hifipower

high fidelity equipment power controller daemon
-----------------------------------------------

A daemon running on an Orange Pi or RPi, exposing a web API for switching the audio equipment on or off, using a relay connected with one of the GPIO pins.

This software reads a configuration file (``/etc/hifipowerd.conf``) and gets the pin numbers for shutdown and reboot buttons, automatic mode sense and relay drive output. Then the web API is started, exposing endpoints accessible with ``GET`` method:

``address:port`` - main page,

``address:port/json`` - get state data as JSON,

``address:port/power`` - get the current state,

``address:port/power/on`` - turns the power on, returning the current state of outputs,

``address:port/power/off`` - turns the power off, returning the current state of outputs,

``address:port/power/toggle`` - turns on if power was off, turns off if power was on (like the on/off button does)

``address:port/power/1/on``, ``address:port/power/1/off``, ``address:port/power/2/on``, ``address:port/power/2/off`` - individual channel control.

Future features
---------------

Use PulseAudio or ALSA to detect lack of audio signal on the input (configurable), then if no audio is present for a preset time (e.g. 10 minutes), turn the equipment off automatically. Prevents idle power draw by e.g. vacuum tube amplifiers.
