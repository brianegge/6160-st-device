#!/usr/bin/python3

import serial
import io
import traceback
from flask import Flask, jsonify, g, request
import time
from time import localtime, strftime, sleep
import sys
import threading
import os
import re
from pprint import pprint

# Init
app = Flask(__name__)

if os.path.exists('/dev/ttyACM0'):
    ser = serial.serial_for_url('/dev/ttyACM0', baudrate=115200, timeout=1)
elif os.path.exists('/dev/ttyACM1'):
    ser = serial.serial_for_url('/dev/ttyACM1', baudrate=115200, timeout=1)
else:
    raise Exception("No serial device found")

sio = io.TextIOWrapper(io.BufferedRWPair(ser, ser))
sio_lock = threading.Lock()
state_dir = os.path.join(os.path.dirname(os.path.realpath(__file__)),'state')
state_file = os.path.join(state_dir, 'mode.txt')
sthm_file = os.path.join(state_dir, 'sthm.txt')

def reader():
    last_time = ''
    while True:
        line = sio.readline()
        if len(line):
            sys.stdout.write('<<' + line)
            if 'initialized' in line:
                message(1, 'Raspberry Pi OK')
            continue
        out = strftime("%a %b %e %I:%M", localtime())
        if out != last_time:
            last_time = out
            message(2, out, quiet=True)

def write(msg, quiet):
    with sio_lock:
        if not quiet:
            sys.stdout.write('>>' + msg)
        sio.write(msg)
        sio.flush()
    return msg, 200

@app.route("/status")
def status():    
    return 'online', 200

@app.route("/mode")
def mode():    
    try:
        with open(state_file, 'r') as in_file:
            return in_file.read()
    except FileNotFoundError:
        return 'Unknown mode', 404

@app.route("/mode", methods=[ 'POST'])
def setmode():
    content = request.json
    mode = content['$locationMode'] 
    with open(state_file, 'w') as out_file:
        out_file.write(mode)
    message(1, mode)
    return 'OK', 200

@app.route("/device/<name>", methods=['GET'])
def device(name):
    f = os.path.join(state_dir, name)
    try:
        with open(f, 'r') as in_file:
            return in_file.read()
    except FileNotFoundError:
        return 'Unknown device', 404

@app.route("/device/<name>", methods=[ 'POST'])
def setdevice(name):
    content = request.json
    pprint(content)
    attribute = content['$currentEventValue']
    f = os.path.join(state_dir, name)
    with open(f, 'w') as out_file:
        out_file.write(attribute)
    return 'OK', 200

@app.route("/sthm", methods=['GET'])
def sthm():
    try:
        with open(sthm_file, 'r') as in_file:
            return in_file.read()
    except FileNotFoundError:
        return 'Unknown state', 404

@app.route("/sthm", methods=[ 'POST'])
def setsthm():
    content = request.json
    pprint(content)
    mode = content['@sthm_mode']
    with open(sthm_file, 'w') as out_file:
        out_file.write(mode)
    message(1, mode)
    return 'OK', 200

# parse F7 command, form is F7[A] z=FC t=0 c=1 r=0 a=0 s=0 p=1 b=1 1=1234567890123456 2=ABCDEFGHIJKLMNOP
#   z - zone             (byte arg)
#   t - tone             (nibble arg) 0=Nothing, 1=One Chime + Disarmed, 2=Two chimes + Armed, 3=three chimes, 4=fast beep (alarm will sound), 5=pulse warning beep, 6=pulse warning beep, 7=constant beep
#   c - chime            (bool arg) 0=voice on
#   r - ready            (bool arg)
#   a - arm-away         (bool arg)
#   s - arm-stay         (bool arg)
#   p - power-on         (bool arg)
#   b - lcd-backlight-on (bool arg)
#   1 - line1 text       (16-chars)
#   2 - line2 text       (16-chars)
@app.route("/message/<line_no>/<text>", methods=['GET', 'POST'])
def message(line_no, text, quiet=False):
    args=''
    if text == 'Armed Away':
        args += 'r=0 a=1 s=0 b=0 c=0 t=2 '
    elif text == 'Armed Stay':
        args += 'r=0 a=0 s=1 b=1 c=0 t=2 '
    elif text == 'Disarmed':
        args += 'r=1 a=0 s=0 b=1 c=0 t=1 '
    elif text == 'Raspberry Pi OK':
        args += 'r=1 a=0 s=0 b=1 c=1 t=0 '
    else:
        args += 'c=1 '
    out, code = write('F7 {}{}={:<16}\n'.format(args, line_no, text), quiet)
    if re.match(".*t=[1-9].*", args):
        sleep(1.5)
        out2, code = write('F7 t=0\n'.format(args, line_no, text), quiet)
        return out + out2, code
    else:
        return out, code

@app.route("/message", methods=['POST'])
def show_message():
    sys.stdout.write('Getting json ' )
    content = request.get_json(silent=False)
    pprint(content)
    backlight = content.get('backlight', '1')
    line_no = content.get('line_no', '1')
    text = content.get('text')
    text = shorten(text)
    args = 'b={} '.format(backlight)
    return write('F7 {}{}={:16.16}\n'.format(args, line_no, text), False)

def shorten(msg):
    if len(msg) > 16:
        msg = msg.replace('Window','Win')
    if len(msg) > 16:
        msg = msg.replace('Office','Offc')
    if len(msg) > 16:
        msg = msg.replace('Basement','Bsmt')
    if len(msg) > 16:
        msg = msg.replace('Garage','Grg')
    if len(msg) > 16:
        msg = msg.replace('Right','Rt')
    if len(msg) > 16:
        msg = msg.replace('Left','Lf')
    return msg

if __name__ == "__main__":
    # start a thread to read events off the serial port
    os.makedirs(state_dir, exist_ok = True)
    d = threading.Thread(name='reader', target=reader)
    d.setDaemon(True)
    d.start()
    # reloader causes problem with background reader
    app.run(host='0.0.0.0', port=8282, debug=True, use_reloader=False)
