# 6160 SmartThings Device Handler
This repository requires an Arduino running https://github.com/TomVickers/Arduino2keypad

This repository contains code to interface a 6160 alarm keypad with an SmartThings Smart Home Monitor.  If you are interested in using a 6160 alarm keypad (commonly found connected to a variety of Honeywell alarm systems like the Vista-20p), this code may be useful to you.

Without Tom Vickers Arduino2keypad project, this project would not be possible. His project does the work of interfacing with the non-standard 4800 baud keypad. Tom chose to write an entire security panel on his Raspberry Pi while this project simply aims to make the keypad accessabe from the SmartThings ecosystem.

Install

# pi setup
sudo apt-get install vim git python3-pip
sudo update-alternatives --config editor

# project
git clone git@github.com:brianegge/6160-st-device.git
sudo pip3 install -r requirements.txt
sudo ln -s /home/pi/6160-st-device/6160.service /etc/systemd/system/6160.service
sudo systemctl enable 6160
