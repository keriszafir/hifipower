#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""hifipower - a daemon for controlling a dual-channel power distribution
unit for hi-fi equipment.

Designed and coded for the AC-1 audio computer.
Keri Szafir, Keritech Electronics - 2018-2026

This daemon controls two GPIO lines which are sequentially switched,
driving two power relays for the audio equipment power.
Both local (pushbutton) and remote (MQTT) control is available.

The daemon detects whether the equipment is in automatic control mode
(then it can be software-driven) or manual override mode (then sending the
commands to it won't do anything).
"""
import datetime
import logging
import signal
import os
import sys
import time
import gpiod
from configparser import ConfigParser
from systemd.journal import JournalHandler
import paho.mqtt.client as mqtt

CFG = ConfigParser(defaults=dict(shutdown_button='PA0', reboot_button='PA1',
                                 manual_mode_in='PA6', ready_led='PA7',
                                 auto_mode_in='PA8', onoff_button='PA3',
                                 relay_out_1='PA9', relay_out_2='PA10',
                                 chip_path='/dev/gpiochip0', button_debounce_ms=1000,
                                 consumer_str='hifipower GPIO interface',
                                 shutdown_command='sudo systemctl poweroff',
                                 reboot_command='sudo systemctl reboot',
                                 pipewire_start_command='systemctl --user start wireplumber.service',
                                 pipewire_stop_command='systemctl --user stop wireplumber.service',
                                 mqtt_client_id='hifipower', mqtt_broker_address='', mqtt_port=1883,
                                 mqtt_username='', mqtt_password='',
                                 mqtt_status_topic_root='stat/hifipower', 
                                 mqtt_command_topic_root='cmnd/hifipower',
                                 mqtt_update_interval=60))
CFG.read('/etc/hifipowerd.conf')

ON, OFF = gpiod.line.Value.ACTIVE, gpiod.line.Value.INACTIVE
IN, OUT = gpiod.line.Direction.INPUT, gpiod.line.Direction.OUTPUT
RISING, FALLING = gpiod.line.Edge.RISING, gpiod.line.Edge.FALLING
IONUMS = {'PA{}'.format(n): n for n in range(21)}
CHANNELS = {name: IONUMS.get(CFG.defaults().get(name))
            for name in ('shutdown_button', 'reboot_button', 'onoff_button', 'ready_led',
                         'manual_mode_in', 'auto_mode_in', 'relay_out_1', 'relay_out_2')}
DEBOUNCE = datetime.timedelta(milliseconds=int(CFG.defaults().get('button_debounce_ms')))
GPIO_DEFS = {CHANNELS['shutdown_button']: gpiod.LineSettings(direction=IN, edge_detection=RISING, debounce_period=DEBOUNCE),
             CHANNELS['reboot_button']: gpiod.LineSettings(direction=IN, edge_detection=RISING, debounce_period=DEBOUNCE),
             CHANNELS['onoff_button']: gpiod.LineSettings(direction=IN, edge_detection=RISING, debounce_period=DEBOUNCE),
             CHANNELS['manual_mode_in']: gpiod.LineSettings(direction=IN),
             CHANNELS['auto_mode_in']: gpiod.LineSettings(direction=IN),
             CHANNELS['ready_led']: gpiod.LineSettings(direction=OUT, output_value=ON),
             CHANNELS['relay_out_1']: gpiod.LineSettings(direction=OUT, output_value=OFF),
             CHANNELS['relay_out_2']: gpiod.LineSettings(direction=OUT, output_value=OFF)}
GPIO_RQ = gpiod.request_lines(CFG.defaults().get('chip_path'),
                              consumer=CFG.defaults().get('consumer_str'),
                              config=GPIO_DEFS)

MQTT = mqtt.Client(client_id=CFG.defaults().get('mqtt_client_id'), transport='tcp', clean_session=True,
                   callback_api_version=mqtt.CallbackAPIVersion.VERSION2, protocol=mqtt.MQTTv311)


@MQTT.message_callback()
def mqtt_on_message_cb(client, userdata, message, properties=None):
    """message received callback"""
    root = CFG.defaults().get('mqtt_command_topic_root')
    topic = message.topic
    subtopic = message.topic.replace(root, '')
    # decode ASCII string to UTF-8 normal python string
    message_payload = message.payload.decode()
    
    print("Received message {} on topic {}".format(message_payload, topic))
    """translate the value to libgpiod internal state values"""
    control_messages = {'ON': ON, 'OFF': OFF, 'TOGGLE': 'T'}
    value = control_messages.get(message_payload)
    if subtopic == '/power' and value == ON:
        power_on()
    elif subtopic == '/power' and value == OFF:
        power_off()
    elif subtopic == '/power' and value == 'T':
        power_toggle()
    elif subtopic == '/power/1':
        relay(1, value)
    elif subtopic == '/power/2':
        relay(2, value)
    elif subtopic == '/pipewire':
        pw_control(value)


@MQTT.connect_callback()
def mqtt_on_connect_cb(client, userdata, flags, reason_code, properties):
    """connected function"""
    status_topic_root = CFG.defaults().get('mqtt_status_topic_root')
    command_topic_root = CFG.defaults().get('mqtt_command_topic_root')
    print('mqtt connected, subscribing command topics')
    MQTT.subscribe('{}/#'.format(command_topic_root), 2)
    print('publishing welcome message and status info')
    MQTT.publish(status_topic_root, 'Hellorld! from hifipower')
    MQTT.publish(status_topic_root, 'online', retain=True)
    

@MQTT.connect_fail_callback()
def mqtt_on_connect_fail_cb(client, userdata, flags, reason_code, properties):
    """not connected for some reason"""
    print('mqtt connection failed, reason: {}'.format(reason_code))


@MQTT.disconnect_callback()
def mqtt_on_disconnect_cb(client, userdata, flags, reason_code, properties):
    """disconnected from server - print why"""
    print('mqtt disconnected, reason: {}'.format(reason_code))


def mqtt_status_update():
    """Publish info on MQTT channels"""
    root = CFG.defaults().get('mqtt_status_topic_root')
    MQTT.publish("{}/power_state".format(root), get_power_state())
    MQTT.publish("{}/power/1".format(root), 'ON' if relay(1) else 'OFF')
    MQTT.publish("{}/power/2".format(root), 'ON' if relay(2) else 'OFF')
    MQTT.publish("{}/auto_control".format(root), 'ON' if auto_control_check() else 'OFF')
    MQTT.publish("{}/manual_override".format(root), 'ON' if manual_override_check() else 'OFF')
    MQTT.loop()


def mqtt_goodbye():
    """Finishing message, disconnect, client teardown"""
    status_topic_root = CFG.defaults().get('mqtt_status_topic_root')
    mqtt_status_update()
    MQTT.publish(status_topic_root, 'hifipower going down!')
    MQTT.publish(status_topic_root, 'offline', retain=True)
    MQTT.disconnect()
    MQTT.loop_stop()


def get_power_state():
    """Checks the power state: -1 = automatic control OFF,
    0 = off, 1 = main power ON but amp power OFF,
    2 = both main and amp power are ON.
    """
    if not auto_control_check():
        return -1
    if relay(2):
        # stage 2
        return 2
    if relay(1):
        # stage 1
        return 1
    return 0


def get_input_state(gpio_name):
    """Read the input state by the gpio name"""
    return GPIO_RQ.get_value(CHANNELS[gpio_name])


def auto_control_check():
    """Checks if the device is in the automatic/software control mode"""
    return True if get_input_state('auto_mode_in') else False


def manual_override_check():
    """Checks if the device is in the manual override ON state"""
    return True if get_input_state('manual_mode_in') else False


def power_on():
    """Turns the hifi system on, main output first, amp output after 5s"""
    power_state = get_power_state()
    if power_state == 1:
        # turn on the amps right away
        relay(2, ON)
    elif power_state == 0:
        # turn on the main gear, wait 5s, turn on the amps
        relay(1, ON)
        time.sleep(5)
        relay(2, ON)
    pw_control(ON)


def power_off():
    """Turns the hifi system off, amp output first, then wait 15s
    and turn all the rest off"""
    power_state = get_power_state()
    if power_state == 2:
        # full de-powering sequence
        relay(2, OFF)
        time.sleep(15)
        relay(1, OFF)
    elif power_state == 1:
        # power off main only
        relay(1, OFF)
    pw_control(OFF)


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
    
    # each blink cycle has 2 timesteps,
    # how long they are depends on the number of cycles and blinking duration
    timestep = 0.5 * duration / (blink or 1)
    
    
    pin = CHANNELS['ready_led']
    # check the initial state if not supplied
    if state is None:
        state = GPIO_RQ.get_value(pin)
    # do the blinking for a number of cycles
    for _ in range(blink):
        GPIO_RQ.set_value(pin, ON)
        time.sleep(timestep)
        GPIO_RQ.set_value(pin, OFF)
        time.sleep(timestep)
    # final state
    GPIO_RQ.set_value(pin, state)
    return GPIO_RQ.get_value(pin)


def relay(channel_id, state=None):
    """Controls the state of the power relay - channel 1.
       If state is None, returns the current state."""
    
    pin = CHANNELS['relay_out_{}'.format(channel_id)]
    if state is not None and auto_control_check():
        led(blink=2)
        GPIO_RQ.set_value(pin, state)
        mqtt_status_update()
    return GPIO_RQ.get_value(pin)


def pw_control(state):
    """starts or stops the pipewire/wireplumber daemon whenever the power
    relay goes on or off, or the web service demands it"""
    if state:
        command = CFG.defaults().get('pipewire_start_command')
    else:
        command = CFG.defaults().get('pipewire_stop_command')
    os.system(command)


def main():
    """Main function"""
    def signal_handler(*_):
        """Exit gracefully if SIGINT or SIGTERM received"""
        raise KeyboardInterrupt

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # change this to reboot or shutdown and execute at the very end if needed
    exit_command = ''
    
    # how often do we need to post status updates on mqtt? (keepalive too)
    interval = CFG.defaults().get('mqtt_update_interval')
    mqtt_update_interval = datetime.timedelta(seconds=int(interval))
    # force the first update right away
    now = datetime.datetime.now()
    update_last_checked = now - mqtt_update_interval

    # systemd-journal logging setup
    debug_mode = CFG.defaults().get('debug_mode')
    logger = logging.getLogger('hifipowerd')
    if debug_mode:
        logger.setLevel(logging.DEBUG)
        logger.addHandler(logging.StreamHandler(sys.stderr))
    else:
        logger.setLevel(logging.INFO)
    journal_handler = JournalHandler()
    log_entry_format = '[%(levelname)s] %(message)s'
    journal_handler.setFormatter(logging.Formatter(log_entry_format))
    logger.addHandler(journal_handler)
    
    # set up and start the MQTT client
    username, password = CFG.defaults().get('mqtt_username'), CFG.defaults().get('mqtt_password')
    broker, port = CFG.defaults().get('mqtt_broker_address'), CFG.defaults().get('mqtt_port')
    MQTT.username_pw_set(username, password)
    
    print('Connecting MQTT client...')
    MQTT.connect_async(broker, port=int(port), keepalive=60)
    MQTT.loop_start()
    
    
    try:        
        # main loop
        while True:
            now = datetime.datetime.now()
            if now > update_last_checked + mqtt_update_interval:
                mqtt_status_update()
                update_last_checked = now
            
            # use edge detection events rather than reading the line state,
            # because the latter was prone to interference from MQTT issued commands
            # I don't know why really, but it made the program think the GPIOs were active
            for event in GPIO_RQ.read_edge_events():
                gpio_pin = event.line_offset 
                if gpio_pin == CHANNELS['onoff_button']:
                    print('on/off button pressed!')
                    power_toggle()
                elif gpio_pin == CHANNELS['reboot_button']:
                    print('Reboot button pressed! Initiating system reboot...')
                    exit_command = CFG.defaults().get('reboot_command')
                    raise KeyboardInterrupt
                elif gpio_pin == CHANNELS['shutdown_button']:
                    print('Shutdown button pressed! Initiating system shutdown...')
                    exit_command = CFG.defaults().get('shutdown_command')
                    raise KeyboardInterrupt
        
    except KeyboardInterrupt:
        print('Exiting hifipower...')
    finally:
        print('Equipment power down sequence initiated...')
        led(ON, blink=5, duration=5)
        power_off()
        led(OFF)
        print('disconnecting MQTT...')
        mqtt_goodbye()
        if exit_command:
            os.system(exit_command)


if __name__ == '__main__':
    main()

