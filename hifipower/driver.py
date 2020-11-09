# -*- coding: utf-8 -*-
"""hardware control backend for hifipower.
Can be used with Orange Pi (the original device is based on OPi Plus,
as it has gigabit Ethernet port and SATA controller),
or a regular Raspberry Pi"""
import atexit
import os
import time

try:
    # use SUNXI as it gives the most predictable results
    import OPi.GPIO as GPIO
    GPIO.setmode(GPIO.SUNXI)
    GPIO_DEFINITIONS = dict(onoff_button='PA7', mode_led='PC4',
                            relay_out='PC7', auto_mode_in='PA8',
                            shutdown_button='PA9', reboot_button='PA10',
                            relay_state='PA11', ready_led='PA12')
    print('Using OPi.GPIO on an Orange Pi with the SUNXI numbering.')

except ImportError:
    # maybe we're using Raspberry Pi?
    # use BCM as it is the most conventional scheme here
    import RPi.GPIO as GPIO
    GPIO.setmode(GPIO.BCM)
    GPIO_DEFINITIONS = dict(onoff_button=5, mode_led=23,
                            relay_out=24, auto_mode_in=6,
                            shutdown_button=13, reboot_button=19,
                            relay_state=3, ready_led=2)
    print('Using RPi.GPIO on a Raspberry Pi with the BCM numbering.')

ON, OFF = GPIO.HIGH, GPIO.LOW
STATE = dict(relay=OFF, auto_mode=OFF)


def gpio_setup(config):
    """Reads the gpio definitions dictionary,
    sets the outputs and inputs accordingly."""
    def shutdown(channel):
        """Shut the system down"""
        if not debounce(channel):
            return
        led('mode_led', blink=2)
        command = config.get('shutdown_command', 'sudo shutdown -h now')
        os.system(command)

    def reboot(channel):
        """Restart the system"""
        if not debounce(channel):
            return
        led('mode_led', blink=2)
        command = config.get('reboot_command', 'sudo reboot')
        os.system(command)

    def toggle_relay_state(channel):
        """Turn the power on or off after pressing the on/off button,
        depending on the previous state"""
        # do nothing in off/manual mode
        if not check_auto_mode():
            return
        # need to hold the button for 0.1s to avoid spurious (de)activations
        if not debounce(channel, 100):
            return
        led('mode_led', blink=2)
        current_relay_state = check_state('relay_state')
        new_state = not current_relay_state
        relay(new_state)

    def update_relay_state(channel):
        """Read the relay control input whenever its state changes
        and update the state dict. This enables the function to work
        even in a forced manual control mode."""
        if not debounce(channel, 20):
            return
        # start/stop pulseaudio depending on relay state
        relay_state = GPIO.input(channel)
        pulseaudio_control(relay_state, config)
        STATE['relay'] = relay_state

    def read_auto_mode():
        """Reads the auto mode input and sets the value in STATE"""
        channel = GPIO_DEFINITIONS['auto_mode_in']
        auto_mode = GPIO.input(channel)
        STATE['auto_mode'] = auto_mode
        return auto_mode

    def update_auto_mode(channel):
        """When the automatic control mode is on, turn on the red LED,
        when it's off, turn the LED off. Update the state dictionary."""
        if not debounce(channel, 20):
            return
        auto_mode = read_auto_mode()
        led('mode_led', auto_mode)
        # restore the last relay state
        relay_state = STATE['relay']
        relay(relay_state)

    def finish(*_):
        """Blink a LED and then clean the GPIO"""
        led('ready_led', OFF, blink=5, duration=5)
        GPIO.cleanup()

    def debounce(channel, bounce_ms=1000):
        """Workaround for software debouncing not implemented in OPi.GPIO
        Checks if the state is unchanged after given time"""
        initial_state = GPIO.input(channel)
        time.sleep(bounce_ms/1000)
        return GPIO.input(channel) == initial_state

    def get_gpio_id(gpio_name):
        """Gets the GPIO id (e.g. "PA7") from the configuration,
        updating the id in GPIO_DEFINITIONS if overriden in config.
        If the GPIO name is not found in config, it's looked up
        in GPIO_DEFINITIONS.
        """
        gpio_id = config.get(gpio_name)
        if gpio_id is None:
            gpio_id = GPIO_DEFINITIONS[gpio_name]
        else:
            # update definitions with the value found in config
            GPIO_DEFINITIONS[gpio_name] = gpio_id

        return gpio_id

    # run the finish function when program ends e.g. during shutdown
    atexit.register(finish)

    # input configuration
    inputs = [('onoff_button', toggle_relay_state, GPIO.RISING),
              ('auto_mode_in', update_auto_mode, GPIO.BOTH),
              ('relay_state', update_relay_state, GPIO.BOTH),
              ('shutdown_button', shutdown, GPIO.RISING),
              ('reboot_button', reboot, GPIO.RISING)]

    for (gpio_name, callback, edge) in inputs:
        gpio_id = get_gpio_id(gpio_name)
        # set the input with pulldown resistor, if supported by GPIO library
        GPIO.setup(gpio_id, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
        # add a threaded callback on this GPIO
        GPIO.add_event_detect(gpio_id, edge, callback=callback, bouncetime=200)

    # output configuration
    # ability to check mode_led state depends on input configuration
    outputs = [('mode_led', check_state('auto_mode_in')),
               ('relay_out', OFF), ('ready_led', ON)]

    for (gpio_name, initial_state) in outputs:
        gpio_id = get_gpio_id(gpio_name)
        GPIO.setup(gpio_id, GPIO.OUT, initial=initial_state)

    # this prevents lack of control via web interface
    # in case the mode switch was initially set to AUTO
    read_auto_mode()


def check_state(gpio_name):
    """Checks the output state"""
    channel = GPIO_DEFINITIONS[gpio_name]
    return GPIO.input(channel)


def check_auto_mode():
    """Checks if the mode switch is set to auto"""
    return STATE['auto_mode']


def relay(state):
    """Controls the state of the power relay"""
    channel = GPIO_DEFINITIONS['relay_out']
    GPIO.output(channel, state)


def led(gpio_name, state=None, blink=0, duration=0.5):
    """LED control:
        state - 0/1, True/False - sets the new state;
                None preserves the previous one
        blink - number of LED blinks before the state is set
        duration - total time of blinking in seconds"""
    channel = GPIO_DEFINITIONS[gpio_name]
    # preserve the previous state in case it is None
    if state is None:
        state = check_state(gpio_name)
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


def pulseaudio_control(state, config):
    """starts or stops the pulseaudio daemon whenever the power
    relay goes on or off, or the web service demands it"""
    if state:
        command = config.get('puseaudio_start_command',
                             'sudo systemctl start pulseaudio.service')
    else:
        command = config.get('puseaudio_stop_command',
                             'sudo systemctl stop pulseaudio.service')
    os.system(command)
