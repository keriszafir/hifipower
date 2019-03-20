# -*- coding: utf-8 -*-
"""hardware control backend for hifipower.
Can be used with Orange Pi (the original device is based on OPi Plus,
as it has gigabit Ethernet port and SATA controller),
or a regular Raspberry Pi"""

try:
    # use SUNXI as it gives the most predictable results
    import OPi.GPIO as GPIO
    GPIO.setmode(GPIO.SUNXI)
    print('Using OPi.GPIO on an Orange Pi with the SUNXI numbering.')

except ImportError:
    # use BCM as it is the most conventional scheme on a RPi
    import RPi.GPIO as GPIO
    GPIO.setmode(GPIO.BCM)
    print('Using RPi.GPIO on a Raspberry Pi with the BCM numbering.')


ON, OFF = True, False
GPIO_DEFINITIONS = dict(auto_mode_in=None, control_out=None,
                        shutdown_button=None, reboot_button=None)


class AutoControlDisabled(Exception):
    """Exception raised when trying to turn the device on or off
    if the equipment is switched OFF or ON manually.
    """


def gpio_setup(gpio_definitions):
    """Reads the gpio definitions dictionary,
    sets the outputs and inputs accordingly."""
    # update the defaults with values from config
    GPIO_DEFINITIONS.update(gpio_definitions)

    gpios = dict(auto_mode_in=GPIO.IN,
                 control_out=GPIO.OUT,
                 shutdown_button=(GPIO.IN, GPIO.PUD_UP),
                 reboot_button=(GPIO.IN, GPIO.PUD_UP))

    for gpio_name, gpio_id in gpio_definitions.items():
        if gpio_id is None:
            # skip the undefined GPIO
            continue

        try:
            # GPIO pin defined with a pull-up / pull-down argument
            direction, pull_up_down = gpios[gpio_name]
            GPIO.setup(gpio_id, direction, pull_up_down=pull_up_down)
        except TypeError:
            # no pull-up/pull-down info
            direction = gpios[gpio_name]
            GPIO.setup(gpio_id, direction)
        except KeyError:
            # trying to set up an unregistered GPIO
            continue


def automatic_mode():
    """Checks if the device is in automatic control mode"""
    channel = GPIO_DEFINITIONS['auto_mode_in']
    return GPIO.input(channel)


def output_control(state):
    """Controls the state of the output"""
    if not automatic_mode():
        raise AutoControlDisabled
    channel = GPIO_DEFINITIONS['control_out']
    GPIO.output(channel, state)


def turn_on():
    """Turns the power ON"""
    output_control(ON)


def turn_off():
    """Turns the power OFF"""
    output_control(OFF)
