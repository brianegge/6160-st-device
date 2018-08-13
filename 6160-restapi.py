#!/usr/bin/python

import serial
import io
import traceback
from flask import Flask, jsonify
import time
from time import localtime, strftime
import sys
import threading

# Init
app = Flask(__name__)

ser = serial.serial_for_url('/dev/ttyACM0', baudrate=115200, timeout=1)
sio = io.TextIOWrapper(io.BufferedRWPair(ser, ser))
sio_lock = threading.Lock()
def reader():
    last_time = ''
    while True:
        line = sio.readline()
        if len(line):
            sys.stdout.write('<<' + line)
            if 'initialized' in line:
                message(1, 'Raspberry Pi OK')
            continue
        out = strftime("%Y-%m-%d %H:%M", localtime())
        if out != last_time:
            last_time = out
            message(2, out)

def write(msg):
    with sio_lock:
        sys.stdout.write('>>' + msg)
        sio.write(unicode(msg))
        sio.flush()
    return msg

@app.route("/status")
def status():    
    return 'online', 200

@app.route("/message/<line_no>/<text>")
def message(line_no, text):    
    return write('F7 {}={:<16}\n'.format(line_no, text))

@app.route("/ready/<state>")
def ready(state):    
    return write('F7 r={}\n'.format(state))

@app.route("/arm-away/<state>")
def arm_away(state):    
    return write('F7 a={}\n'.format(state))

@app.route("/arm-stay/<state>")
def arm_stay(state):    
    return write('F7 s={}\n'.format(state))

if __name__ == "__main__":
    # start a thread to read events off the serial port
    d = threading.Thread(name='reader', target=reader)
    d.setDaemon(True)
    d.start()
    app.run(host='0.0.0.0', port=8282, debug=True)
