# -*- coding: utf-8 -*-
"""hifipower - a mini-daemon for controlling a switchable PDU
for hi-fi equipment.

This daemon listens on specified address and provides web API for changing
the power state; when this happens, a GPIO line is turned on or off,
controlling a power relay that switches the equipment power on or off.

The daemon detects whether the equipment is in automatic control mode
(then it can be software-driven) or manual control mode (then sending the
commands to it won't do anything).

Additional functionality is planned for auto power-off after silence is
detected on the device's audio input. This will be optional and require
the sound card input to be wired to the audio output of a preamplifier/mixer.
If no signal is present for a certain time, and the PDU is in "auto control"
mode, the software will turn the power off.

Auto power-on is also planned. Whenever the sound card's active
(i.e. PulseAudio sink is no longer suspended), the equipment power is
turned on. This may be problematic though, in case a longer time is needed
for the switch-on (e.g. when using a vacuum tube power amp).
"""
from . import driver

