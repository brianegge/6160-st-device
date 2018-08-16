#!/usr/bin/python

import serial
import io
import traceback
from flask import Flask, jsonify
import time
from time import localtime, strftime
import sys
import threading
import thread
import os

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
        out = strftime("%a %b %e %I:%M", localtime())
        if out != last_time:
            last_time = out
            message(2, out)

def write(msg):
    with sio_lock:
        sys.stdout.write('>>' + msg)
        sio.write(unicode(msg))
        sio.flush()
    return msg, 200

@app.route("/status")
def status():    
    return 'online', 200

@app.route("/message/<line_no>/<text>", methods=['GET', 'POST'])
def message(line_no, text):    
    return write('F7 {}={:<16}\n'.format(line_no, text))

@app.route("/ready/<state>", methods=['GET', 'POST'])
def ready(state):    
    return write('F7 r={}\n'.format(state))

@app.route("/arm-away/<state>", methods=['GET', 'POST'])
def arm_away(state):    
    return write('F7 1={:<16} a={}\n'.format('Armed Away' if state == '1' else 'Disarmed', state))

@app.route("/arm-stay/<state>", methods=['GET', 'POST'])
def arm_stay(state):    
    return write('F7 1={:<16} s={}\n'.format('Armed Stay' if state == '1' else 'Disarmed', state))

if __name__ == "__main__":
    # start a thread to read events off the serial port
    d = threading.Thread(name='reader', target=reader)
    d.setDaemon(True)
    d.start()
    # reloader causes problem with background reader
    app.run(host='0.0.0.0', port=8282, debug=True, use_reloader=False)
