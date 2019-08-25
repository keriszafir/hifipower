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
    GPIO_DEFINITIONS = dict(relay_out='PA7', auto_mode_in='PA8',
                            shutdown_button='PA9', reboot_button='PA10',
                            relay_state='PA11', ready_led='PA12')
    print('Using OPi.GPIO on an Orange Pi with the SUNXI numbering.')

except ImportError:
    # use BCM as it is the most conventional scheme on a RPi
    import RPi.GPIO as GPIO
    GPIO.setmode(GPIO.BCM)
    GPIO_DEFINITIONS = dict(relay_out=5, auto_mode_in=6,
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
        command = config.get('shutdown_command', 'sudo systemctl poweroff')
        subprocess.run([x.strip() for x in command.split(' ')])

    def reboot():
        """Restart the system"""
        command = config.get('reboot_command', 'sudo systemctl reboot')
        subprocess.run([x.strip() for x in command.split(' ')])

    def finish():
        """Blink a LED and then clean the GPIO"""
        for _ in range(5):
            set_led(OFF)
            time.sleep(0.2)
            set_led(ON)
            time.sleep(0.2)
        set_led(OFF)
        GPIO.cleanup()

    gpios = dict(relay_out=GPIO.OUT, auto_mode_in=GPIO.IN,
                 shutdown_button=GPIO.IN, reboot_button=GPIO.IN,
                 relay_state=GPIO.IN, ready_led=GPIO.OUT)

    callbacks = dict(shutdown_button=shutdown, reboot_button=reboot)

    for gpio_name, direction in gpios.items():
        gpio_id = config.get(gpio_name, GPIO_DEFINITIONS[gpio_name])
        GPIO.setup(gpio_id, direction)
        # update the value in main storage
        GPIO_DEFINITIONS[gpio_name] = gpio_id
        # set up a threaded callback if needed
        with suppress(KeyError):
            callback_function = callbacks[gpio_id]
            GPIO.add_event_detect(gpio_id, GPIO.RISING, bouncetime=1000,
                                  callback=callback_function)

    # flash a LED and clean up the definitions
    atexit.register(finish)
    set_led(ON)


def check_automatic_mode():
    """Checks if the device is in automatic control mode"""
    channel = GPIO_DEFINITIONS['auto_mode_in']
    return GPIO.input(channel)


def check_output_state():
    """Checks the output state"""
    channel = GPIO_DEFINITIONS['relay_state']
    return GPIO.input(channel)


def set_output(state):
    """Controls the state of the output"""
    if not check_automatic_mode():
        raise AutoControlDisabled
    channel = GPIO_DEFINITIONS['relay_out']
    GPIO.output(channel, state)


def set_led(state):
    """Controls the state of the "ready" LED"""
    channel = GPIO_DEFINITIONS['led_out']
    GPIO.output(channel, state)
