# hifipower

high fidelity equipment power controller daemon
-----------------------------------------------

A daemon running on an Orange Pi or RPi, exposing a web API for switching the audio equipment on or off, using a relay connected with one of the GPIO pins.

This software reads a configuration file (``/etc/hifipowerd.conf``) and gets the pin numbers for shutdown and reboot buttons, automatic mode sense and relay drive output. Then the web API is started, exposing three endpoints:

``address/hifi/power`` (GET) - get the current state as JSON,

``address/hifi/power/on`` (GET) - turns the power on,

``address/hifi/power/off`` (GET) - turns the power off.

Future features
---------------

Use PulseAudio or ALSA to detect lack of audio signal on the input (configurable), then if no audio is present for a preset time (e.g. 10 minutes), turn the equipment off automatically. Prevents idle power draw by e.g. vacuum tube amplifiers.
