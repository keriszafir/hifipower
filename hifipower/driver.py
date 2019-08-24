# -*- coding: utf-8 -*-
"""hardware control backend for hifipower.
Can be used with Orange Pi (the original device is based on OPi Plus,
as it has gigabit Ethernet port and SATA controller),
or a regular Raspberry Pi"""
import atexit
import subprocess
from contextlib import suppress

try:
    # use SUNXI as it gives the most predictable results
    import OPi.GPIO as GPIO
    GPIO.setmode(GPIO.SUNXI)
    GPIO_DEFINITIONS = dict(relay_out='PA7', auto_mode_in='PA8',
                            shutdown_button='PA9', reboot_button='PA10')
    print('Using OPi.GPIO on an Orange Pi with the SUNXI numbering.')

except ImportError:
    # use BCM as it is the most conventional scheme on a RPi
    import RPi.GPIO as GPIO
    GPIO.setmode(GPIO.BCM)
    GPIO_DEFINITIONS = dict(relay_out=5, auto_mode_in=6,
                            shutdown_button=13, reboot_button=19)
    print('Using RPi.GPIO on a Raspberry Pi with the BCM numbering.')


ON, OFF = True, False


class AutoControlDisabled(Exception):
    """Exception raised when trying to turn the device on or off
    if the equipment is switched OFF or ON manually.
    """


def gpio_setup(config):
    """Reads the gpio definitions dictionary,
    sets the outputs and inputs accordingly."""
    def shutdown():
        """Shut the system down"""
        command = 'sudo systemctl poweroff'
        subprocess.run([x.strip() for x in command.split(' ')])

    def reboot():
        """Restart the system"""
        command = 'sudo systemctl reboot'
        subprocess.run([x.strip() for x in command.split(' ')])

    # update the defaults with values from config
    gpio_defs = {k: v for k, v in config.items() if k in GPIO_DEFINITIONS}

    gpios = dict(relay_out=dict(direction=GPIO.OUT),
                 auto_mode_in=dict(direction=GPIO.IN),
                 shutdown_button=dict(direction=GPIO.IN,
                                      pull_up_down=GPIO.PUD_UP),
                 reboot_button=dict(direction=GPIO.IN,
                                    pull_up_down=GPIO.PUD_UP))
    callbacks = dict(shutdown_button=shutdown,
                     reboot_button=reboot)

    for gpio_name, gpio_id in gpio_defs.items():
        if gpio_id is None:
            # skip the undefined GPIO
            continue

        parameters = dict()
        try:
            parameters.update(gpios[gpio_name])
        except KeyError:
            # not found in gpios: unknown GPIO, or no GPIO definition at all
            continue

        GPIO.setup(gpio_id, **parameters)
        # update the value in main storage
        GPIO_DEFINITIONS[gpio_name] = gpio_id
        # set up a threaded callback if needed
        with suppress(KeyError):
            callback_function = callbacks[gpio_id]
            GPIO.add_event_detect(gpio_id, GPIO.RISING, bouncetime=1000,
                                  callback=callback_function)

    # force to clean up the definitions
    atexit.register(GPIO.cleanup)


def check_automatic_mode():
    """Checks if the device is in automatic control mode"""
    channel = GPIO_DEFINITIONS['auto_mode_in']
    return GPIO.input(channel)


def check_output_state():
    """Checks the output state"""
    channel = GPIO_DEFINITIONS['relay_out']
    return GPIO.input(channel)


def set_output(state):
    """Controls the state of the output"""
    if not check_automatic_mode():
        raise AutoControlDisabled
    channel = GPIO_DEFINITIONS['relay_out']
    GPIO.output(channel, state)


def turn_on():
    """Turns the power ON"""
    set_output(ON)


def turn_off():
    """Turns the power OFF"""
    set_output(OFF)
