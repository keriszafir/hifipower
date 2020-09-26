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
import logging
import signal
import sys
from configparser import ConfigParser
from contextlib import suppress
from flask import Flask, jsonify
from . import driver
from .driver import ON, OFF, GPIO_DEFINITIONS as DEFAULT_CONFIG

LOG = logging.getLogger('hifipowerd')

# add default address and port to the default config
# that now stores GPIO definitions
DEFAULT_CONFIG.update(address='0.0.0.0', port=8000)
CFG = ConfigParser(defaults=DEFAULT_CONFIG)
CFG.read('/etc/hifipowerd.conf')


def journald_setup():
    """Set up and start journald logging"""
    debug_mode = CFG.defaults().get('debug_mode')
    if debug_mode:
        LOG.setLevel(logging.DEBUG)
        LOG.addHandler(logging.StreamHandler(sys.stderr))
    with suppress(ImportError):
        from systemd.journal import JournaldLogHandler
        journal_handler = JournaldLogHandler()
        log_entry_format = '[%(levelname)s] %(message)s'
        journal_handler.setFormatter(logging.Formatter(log_entry_format))
        LOG.setLevel(logging.INFO)
        LOG.addHandler(journal_handler)


def webapi():
    """JSON web API for communicating with the casting software."""
    def index():
        """Index page to show that it's alive"""
        return "It works!"

    def status():
        """Get or change the interface's current status."""
        return jsonify(dict(power=driver.check_output_state(),
                            auto_mode=driver.check_automatic_mode()))

    def control(state):
        """Turn power on or off"""
        try:
            driver.set_relay(state)
            message = 'Power is now {}'.format('ON' if state else 'OFF')
            LOG.info(message)
            return message
        except driver.AutoControlDisabled:
            message = ('Canot turn the power {}. Automatic control disabled'
                       .format('ON' if state else 'OFF'))
            LOG.error(message)
            return ('403 Forbidden: {}'.format(message), 403)

    def turn_on():
        """Turn the power on"""
        return control(ON)

    def turn_off():
        """Turn the power off"""
        return control(OFF)

    # webserver name and endpoints
    app = Flask('hifipowerd')
    app.route('/')(index)
    app.route('/power')(status)
    app.route('/power/on')(turn_on)
    app.route('/power/off')(turn_off)
    # configuration to run the webserver
    config = CFG.defaults()
    address, port = config.get('address'), config.get('port')
    debug_mode = config.get('debug_mode')
    message = 'Starting rpi2casterd web API on {}:{}'.format(address, port)
    LOG.info(message)
    app.run(address, port, debug=debug_mode)


def main():
    """Main function"""
    # signal handling routine
    def signal_handler(*_):
        """Exit gracefully if SIGINT or SIGTERM received"""
        raise KeyboardInterrupt

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # get the GPIO definitions and set up the I/O
    journald_setup()
    driver.gpio_setup(CFG.defaults())
    # start the web interface
    webapi()


if __name__ == '__main__':
    main()
