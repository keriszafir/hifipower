# -*- coding: utf-8 -*-
"""hardware control backend for hifipower.
Can be used with Orange Pi (the original device is based on OPi Plus,
as it has gigabit Ethernet port and SATA controller),
or a regular Raspberry Pi"""
import atexit
import subprocess
import time
from contextlib import suppress

try:
    # use SUNXI as it gives the most predictable results
    import OPi.GPIO as GPIO
    GPIO.setmode(GPIO.SUNXI)
    GPIO_DEFINITIONS = dict(onoff_button='PC4', mode_led='PC7',
                            relay_out='PA7', auto_mode_in='PA8',
                            shutdown_button='PA9', reboot_button='PA10',
                            relay_state='PA11', ready_led='PA12')
    print('Using OPi.GPIO on an Orange Pi with the SUNXI numbering.')

except ImportError:
    # maybe we're using Raspberry Pi?
    # use BCM as it is the most conventional scheme here
    import RPi.GPIO as GPIO
    GPIO.setmode(GPIO.BCM)
    GPIO_DEFINITIONS = dict(onoff_button=23, mode_led=4,
                            relay_out=5, auto_mode_in=6,
                            shutdown_button=13, reboot_button=19,
                            relay_state=3, ready_led=2)
    print('Using RPi.GPIO on a Raspberry Pi with the BCM numbering.')

ON, OFF = GPIO.HIGH, GPIO.LOW


class AutoControlDisabled(Exception):
    """Exception raised when trying to turn the device on or off
    if the equipment is switched OFF or ON manually.
    """


def gpio_setup(config):
    """Reads the gpio definitions dictionary,
    sets the outputs and inputs accordingly."""
    def shutdown():
        """Shut the system down"""
        command = config.get('shutdown_command', 'poweroff')
        subprocess.run([x.strip() for x in command.split(' ')])

    def reboot():
        """Restart the system"""
        command = config.get('reboot_command', 'reboot')
        subprocess.run([x.strip() for x in command.split(' ')])

    def toggle_state():
        """Turn the power on or off after pressing the on/off button,
        depending on the previous state"""
        set_relay(not check_state('relay_out'))

    def check_auto_mode():
        """When the automatic control mode is on, turn on the red LED,
        when it's off, turn the LED off"""
        set_led('mode_led', check_state('auto_mode_in'))

    def finish():
        """Blink a LED and then clean the GPIO"""
        set_led('ready_led', OFF, blink=5)
        GPIO.cleanup()

    gpios = dict(onoff_button=GPIO.IN, mode_led=GPIO.OUT,
                 relay_out=GPIO.OUT, auto_mode_in=GPIO.IN,
                 shutdown_button=GPIO.IN, reboot_button=GPIO.IN,
                 relay_state=GPIO.IN, ready_led=GPIO.OUT)

    callbacks = dict(shutdown_button=shutdown, reboot_button=reboot,
                     onoff_button=toggle_state, auto_mode_in=check_auto_mode)

    for gpio_name, direction in gpios.items():
        # if not configured then use fallback
        gpio_id = config.get(gpio_name, GPIO_DEFINITIONS[gpio_name])
        if direction == GPIO.OUT:
            # set the "off" initial state of outputs just in case
            GPIO.setup(gpio_id, direction, initial_state=OFF)
        else:
            # pull down all inputs to GND
            GPIO.setup(gpio_id, direction, pull_up_down=GPIO.PUD_DOWN)
        # update the value in main storage if overriden by config
        GPIO_DEFINITIONS[gpio_name] = gpio_id
        # set up a threaded callback if needed
        with suppress(KeyError):
            callback_function = callbacks[gpio_name]
            # detect both on and off on auto mode input
            edge = GPIO.BOTH if gpio_name == 'auto_mode_in' else GPIO.RISING
            GPIO.add_event_detect(gpio_id, edge, bouncetime=1000,
                                  callback=callback_function)

    # flash a LED and clean up the definitions
    atexit.register(finish)
    set_led('ready_led', ON)


def check_state(gpio_name):
    """Checks the output state"""
    channel = GPIO_DEFINITIONS[gpio_name]
    return GPIO.input(channel)


def set_relay(state):
    """Controls the state of the power relay"""
    if not check_state('auto_mode_in'):
        raise AutoControlDisabled
    channel = GPIO_DEFINITIONS['relay_out']
    GPIO.output(channel, state)


def set_led(gpio_name, state=False, blink=0):
    """Set the LED state"""
    channel = GPIO_DEFINITIONS[gpio_name]
    # blinking a number of times
    for _ in range(blink):
        GPIO.output(channel, ON)
        time.sleep(0.2)
        GPIO.output(channel, OFF)
        time.sleep(0.2)
    # final state
    GPIO.output(channel, state)
