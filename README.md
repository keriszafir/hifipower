# hifipower

high fidelity equipment power controller daemon
-----------------------------------------------

A daemon running on a single board computer (RPi etc.) using GPIOs for controlling two relays sequentially, and a few GPIOs for buttons, sensing and LED control.

This software reads a configuration file (``/etc/hifipowerd.conf``) and gets the pin numbers for shutdown and reboot buttons, automatic mode sense and relay drive output.
The program uses MQTT for reporting status and accepting commands, supporting separate prefix roots for both.

MQTT_STATUS_ROOT for hello and goodbye messages, ``online`` and ``offline`` status reporting
MQTT_STATUS_ROOT/power_state (-1 = manual control, 0 = off, 1 = stage 1 activated, 2 = stage 2 full power activated) - current power state
MQTT_STATUS_ROOT/power/{1,2} (``ON`` or ``OFF``) - power state of both relays
MQTT_STATUS_ROOT/auto_control (``ON`` or ``OFF``) - whether automatic (software-driven) control is enabled
MQTT_STATUS_ROOT/manual_override (``ON`` or ``OFF``) - whether the device is in manual override ON mode
(not implemented yet) MQTT_STATUS_ROOT/pipewire (``ON`` or ``OFF``) - whether pipewire audio server is started
MQTT_COMMAND_ROOT/power (``ON``, ``OFF`` or  ``T``) - turn power on, off or toggle
MQTT_COMMAND_ROOT/power/{1, 2} (``ON`` or ``OFF``) - turn individual relay's power on or off
MQTT_COMMAND_ROOT/pipewire (``ON`` or ``OFF``) - start or stop the pipewire audio server
