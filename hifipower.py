#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""hifipower - a daemon for controlling a dual-channel power distribution
unit for hi-fi equipment.

Designed and coded for the AC-1 audio computer.
Keri Szafir, Keritech Electronics - 2018-2022

This daemon listens on specified address and provides web API for changing
the power state; when this happens, a GPIO line is turned on or off,
controlling two power relays that switch the equipment power on or off.
Separate control is available over the web API; the big red button allows
for simultaneous control of both channels.

This program was written for an Orange Pi PC Plus platform for its connectivity,
but it can be used with a different Orange Pi, or a regular Raspberry Pi.
Since OPi.GPIO does NOT support software debouncing, the device was
designed for RC hardware debouncing for all buttons.

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
import atexit
import logging
import signal
import os
import sys
import time
from configparser import ConfigParser
from flask import Flask
from systemd.journal import JournalHandler

LOG = logging.getLogger('hifipowerd')
CFG = ConfigParser(defaults=dict(auto_mode_in='PA8', onoff_button='PA3',
                                 relay_out_1='PA9', relay_out_2='PA10',
                                 shutdown_button='PA0', reboot_button='PA1',
                                 manual_mode_in='PA6', ready_led='PA7'))
CFG.read('/etc/hifipowerd.conf')


# Conditional platform-based imports
try:
    # use SUNXI as it gives the most predictable results
    from OPi import GPIO
    GPIO.setmode(GPIO.SUNXI)
    print('Using OPi.GPIO on an Orange Pi with the SUNXI numbering.')

except ImportError:
    # maybe we're using Raspberry Pi?
    # use BCM as it is the most conventional scheme here
    from RPi import GPIO
    GPIO.setmode(GPIO.BCM)
    print('Using RPi.GPIO on a Raspberry Pi with the BCM numbering.')


ON, OFF = GPIO.HIGH, GPIO.LOW


def webapi():
    """JSON web API for communicating with the casting software."""
    def index():
        """Display front page"""
        page = """<h1>Keritech Electronics AC-1 Audio Computer</h1><br>"""
        return page

    def status_json():
        """Get or change the interface's current status."""
        return dict(power_state=get_power_state(),
                    auto_mode=auto_control_check(),
                    manual_override=manual_override_check(),
                    relay1=relay1(),
                    relay2=relay2(),
                    relay1_active=relay1_active(),
                    relay2_active=relay2_active())


    def out1_on():
        """turn on the first relay"""
        relay1(ON)
        return output_status()

    def out1_off():
        """turn off the first relay"""
        relay1(OFF)
        return output_status()

    def out2_on():
        """turn on the second relay"""
        relay2(ON)
        return output_status()

    def out2_off():
        """turn off the second relay"""
        relay2(OFF)
        return output_status()

    def all_on():
        """turn the power on sequentially"""
        power_on()
        return output_status()

    def all_off():
        """turn the power off sequentially"""
        power_off()
        return output_status()

    def toggle():
        """toggle power button-style"""
        power_toggle()
        return output_status()

    def output_status():
        """text message about both devices status"""
        msg = ''
        if get_power_state() == -1:
            msg = '''<div>Manual override is on -
                   software control inactive.</div>'''
        main_pwr = 'ON' if relay1_active() else 'OFF'
        amp_pwr = 'ON' if relay2_active() else 'OFF'
        return f'''{msg}<div>Main power is {main_pwr}<br>
                   Amp power is {amp_pwr}</div>'''

    app = Flask('rpi2casterd')
    app.route('/')(index)
    app.route('/json')(status_json)
    app.route('/power')(output_status)
    app.route('/power/on')(all_on)
    app.route('/power/off')(all_off)
    app.route('/power/toggle')(toggle)
    app.route('/power/1')(relay1_active)
    app.route('/power/2')(relay2_active)
    app.route('/power/1/on')(out1_on)
    app.route('/power/1/off')(out1_off)
    app.route('/power/2/on')(out2_on)
    app.route('/power/2/off')(out2_off)
    config = CFG.defaults()
    app.run(config.get('address'), config.get('port'),
            debug=config.get('debug_mode'))


def gpio_setup():
    """Reads the gpio definitions dictionary,
    sets the outputs and inputs accordingly."""
    config = CFG.defaults()
    def shutdown(*_):
        """Shut the system down"""
        led(blink=5)
        command = config.get('shutdown_command', 'sudo poweroff')
        os.system(command)

    def reboot(*_):
        """Restart the system"""
        led(blink=5)
        command = config.get('reboot_command', 'sudo reboot')
        os.system(command)

    def finish(*_):
        """Blink a LED and then clean the GPIO"""
        led(OFF, blink=5, duration=5)
        relay1(OFF)
        relay2(OFF)
        GPIO.cleanup()

    # run the finish function when program ends e.g. during shutdown
    atexit.register(finish)

    # input configuration
    inputs = [('onoff_button', power_toggle),
              ('shutdown_button', shutdown),
              ('reboot_button', reboot),
              ('auto_mode_in', None),
              ('manual_mode_in', None)]

    for (gpio_name, callback) in inputs:
        gpio_id = config.get(gpio_name)
        GPIO.setup(gpio_id, GPIO.IN)
        # add a threaded callback on this GPIO
        if callback is not None:
            GPIO.add_event_detect(gpio_id, GPIO.RISING, callback=callback)

    # output configuration
    GPIO.setup(config.get('relay_out_1'), GPIO.OUT, initial=OFF)
    GPIO.setup(config.get('relay_out_2'), GPIO.OUT, initial=OFF)
    GPIO.setup(config.get('ready_led'), GPIO.OUT, initial=ON)


def journald_setup():
    """Set up and start journald logging"""
    debug_mode = CFG.defaults().get('debug_mode')
    if debug_mode:
        LOG.setLevel(logging.DEBUG)
        LOG.addHandler(logging.StreamHandler(sys.stderr))
    journal_handler = JournalHandler()
    log_entry_format = '[%(levelname)s] %(message)s'
    journal_handler.setFormatter(logging.Formatter(log_entry_format))
    LOG.setLevel(logging.INFO)
    LOG.addHandler(journal_handler)


def get_power_state():
    """Checks the power state: -1 = automatic control OFF,
    0 = off, 1 = main power ON but amp power OFF,
    2 = both main and amp power are ON.
    """
    if not auto_control_check():
        return -1
    if relay2_active():
        # stage 2
        return 2
    if relay1_active():
        # stage 1
        return 1
    return 0


def get_channel(gpio_name):
    """Get the GPIO number for a channel name"""
    return CFG.defaults().get(gpio_name)


def auto_control_check():
    """Checks if the device is in the automatic/software control mode"""
    return GPIO.input(get_channel('auto_mode_in'))


def manual_override_check():
    """Checks if the device is in the manual override ON state"""
    return GPIO.input(get_channel('manual_mode_in'))


def relay1_active():
    """Checks if the channel 1 relay is on.
    This is true either in manual override, or in auto control when
    channel 1 output is set to ON.
    """
    # we can use GPIO.input() on outputs to check their state
    return manual_override_check() or auto_control_check() and relay1()


def relay2_active():
    """Checks if the channel 2 relay is on.
    This is true either in manual override, or in auto control when
    channel 2 output is set to ON.
    """
    # we can use GPIO.input() on outputs to check their state
    return manual_override_check() or auto_control_check() and relay2()


def relay1(state=None):
    """Controls the state of the power relay - channel 1.
       If state is None, returns the current state."""
    channel = get_channel('relay_out_1')
    if state is not None:
        GPIO.output(channel, state)
    return GPIO.input(channel)


def relay2(state=None):
    """Controls the state of the power relay - channel 2.
    If state is None, returns the current state."""
    channel = get_channel('relay_out_2')
    if state is not None:
        GPIO.output(channel, state)
    return GPIO.input(channel)


def power_on():
    """Turns the hifi system on, main output first, amp output after 5s"""
    power_state = get_power_state()
    if power_state == 1:
        # turn on the amps right away
        relay2(ON)
    elif power_state == 0:
        # turn on the main gear, wait 5s, turn on the amps
        relay1(ON)
        time.sleep(5)
        relay2(ON)
    else:
        # either fully on or manual control = do nothing
        return


def power_off():
    """Turns the hifi system off, amp output first, then wait 15s
    and turn all the rest off"""
    power_state = get_power_state()
    if power_state == 2:
        # full de-powering sequence
        relay2(OFF)
        time.sleep(15)
        relay1(OFF)
    elif power_state == 1:
        # power off main only
        relay1(OFF)
    else:
        # either powered off or manual mode, do nothing
        return


def power_toggle(*_):
    """Cycles through power: if it's fully ON, powers off;
    if it's partially ON (no amps, state 1), powers amps up;
    if it's fully OFF, powers both main and amps up.
    """
    power_state = get_power_state()
    if power_state < 0:
        # auto control disabled, do nothing
        return
    if power_state == 2:
        power_off()
    elif get_power_state() < 2:
        power_on()


def led(state=None, blink=0, duration=0.5):
    """LED control:
        state - 0/1, True/False - sets the new state;
                None preserves the previous one
        blink - number of LED blinks before the state is set
        duration - total time of blinking in seconds"""
    channel = get_channel('ready_led')
    # preserve the previous state in case it is None
    if state is None:
        state = GPIO.input(channel)
    # each blink cycle has 2 timesteps,
    # how long they are depends on the number of cycles and blinking duration
    timestep = 0.5 * duration / (blink or 1)
    # blinking a number of times
    for _ in range(blink):
        GPIO.output(channel, ON)
        time.sleep(timestep)
        GPIO.output(channel, OFF)
        time.sleep(timestep)
    # final state
    GPIO.output(channel, state)


def pw_control(state, config):
    """starts or stops the pipewire daemon whenever the power
    relay goes on or off, or the web service demands it"""
    if state:
        command = config.get('pipewire_start_command',
                             'systemctl --user start pipewire.service')
    else:
        command = config.get('pipewire_stop_command',
                             'systemctl --user stop pipewire.service')
    os.system(command)


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
    gpio_setup()
    # start the webapi loop
    webapi()


if __name__ == '__main__':
    main()
