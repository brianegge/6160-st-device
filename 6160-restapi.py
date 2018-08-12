#!/usr/bin/python

import serial
from serial.threaded import LineReader, ReaderThread
import traceback
from flask import Flask, jsonify
import time
import sys

# Init
app = Flask(__name__)
LineReader.TERMINATOR='\n'
class PrintLines(LineReader):
    i = 0
    def connection_made(self, transport):
        super(PrintLines, self).connection_made(transport)
        sys.stdout.write('port opened\n')

    def handle_line(self, data):
        sys.stdout.write('line received: {}\n'.format(repr(data)))
        self.i = self.i + 1
        if self.i > 2:
            sys.stdout.write('ready\n')
            self.write_line('F7 1=Raspberry Pi   ')

    def connection_lost(self, exc):
        if exc:
            traceback.print_exc(exc)
        sys.stdout.write('port closed\n')

ser = serial.serial_for_url('/dev/ttyACM0', baudrate=115200, timeout=1)
with ReaderThread(ser, PrintLines) as protocol:
    time.sleep(2)

# Create dictionary with elements 
things = {'fans':   [{'name': 'bedroom',    'gpio': {'light':11, 'stop':13, 'fast':15, 'slow':16}}],
          'blinds': [{'name': 'bedroom',    'gpio': {'up':3,'stop':5,'down': 7}},
                     {'name': 'livingroom', 'gpio': {'up':8,'stop':10,'down':12}}]}

def thing_do(f,action):
    #print 'thing_do'
    #print action 
    if action in f['gpio']:
        GPIO.output(f['gpio'][action], GPIO.HIGH)
        time.sleep(1)
        GPIO.output(f['gpio'][action], GPIO.LOW)
        return 200
    else:
        return 400

@app.route("/status")
def status():    
    return 'online', 200

@app.route("/<ttype>/<thing>/<action>")
def action(ttype,thing, action):    
    res = 400
    if ttype in things:
        for f in things[ttype]:
            if thing == f['name'] or thing == "all":
                res = thing_do(f,action)
    return jsonify({'res':res}), res

def write_time():
    ser.write('F7 r=0 1=Today67890123456\n')
    True

if __name__ == "__main__":
   #app.run(host='0.0.0.0', port=82, debug=False)
   write_time()
   time.sleep(10)
