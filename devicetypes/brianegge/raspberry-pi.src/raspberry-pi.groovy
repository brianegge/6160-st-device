/*
 *  Raspberry Pi 6160 controller
 *  Category: Device Handler
 * 
 *  Source: https://community.smartthings.com/t/beta-release-uri-switch-device-handler-for-controlling-items-via-http-calls/37842
 * 
 *  Credit: tguerena and surge919
 *
 *  Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except
 *  in compliance with the License. You may obtain a copy of the License at:
 *
 *      http://www.apache.org/licenses/LICENSE-2.0
 *
 *  Unless required by applicable law or agreed to in writing, software distributed under the License is distributed
 *  on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the License
 *  for the specific language governing permissions and limitations under the License.
*/

import groovy.json.JsonSlurper

metadata {
    definition (name: "6160 Keypad", namespace: "brianegge", author: "Brian Egge") {
        capability "Switch"
        attribute "triggerswitch", "string"
        command "DeviceTrigger"
    }

    preferences {
        input("DeviceIP", "string", title:"Device IP Address", description: "Please enter your device's IP Address", required: true, displayDuringSetup: true)
        input("DevicePort", "string", title:"Device Port", description: "Empty assumes port 8282.", required: false, displayDuringSetup: true)
        input("DevicePathOn", "string", title:"URL Path for ON", description: "Rest of the URL, include forward slash.", displayDuringSetup: true)
        input("DevicePathOff", "string", title:"URL Path for OFF", description: "Rest of the URL, include forward slash.", displayDuringSetup: true)
        input(name: "DevicePostGet", type: "enum", title: "POST or GET", options: ["POST","GET"], defaultValue: "POST", required: false, displayDuringSetup: true)
        section() {
            input("HTTPAuth", "bool", title:"Requires User Auth?", description: "Choose if the HTTP requires basic authentication", defaultValue: false, required: true, displayDuringSetup: true)
            input("HTTPUser", "string", title:"HTTP User", description: "Enter your basic username", required: false, displayDuringSetup: true)
            input("HTTPPassword", "string", title:"HTTP Password", description: "Enter your basic password", required: false, displayDuringSetup: true)
        }
    }


    // simulator metadata
    simulator {
    }

    // UI tile definitions
    tiles {
        standardTile("DeviceTrigger", "device.triggerswitch", width: 2, height: 2, canChangeIcon: true) {
            state "triggeroff", label: 'Off', action: "on", icon: "st.switches.switch.off", backgroundColor: "#ffffff", nextState: "on"
            state "triggeron", label: 'On', action: "off", icon: "st.switches.switch.on", backgroundColor: "#79b821", nextState: "off"
        }
        main "DeviceTrigger"
            details (["DeviceTrigger"])
    }
}

def parse(String description) {
    log.debug(description)
}

def on() {
    log.debug "---ON COMMAND--- ${DevicePathOn}"
    sendEvent(name: "triggerswitch", value: "triggeron", isStateChange: true)
    runCmd(DevicePathOn)
}

def off() {
    log.debug "---ON COMMAND--- ${DevicePathOff}"
    sendEvent(name: "triggerswitch", value: "triggeroff", isStateChange: true)
    runCmd(DevicePathOff)
}

def runCmd(String varCommand) {
    def host = DeviceIP
    def LocalDevicePort = ''
    if (DevicePort==null) { LocalDevicePort = "8282" } else { LocalDevicePort = DevicePort }

    def userpassascii = "${HTTPUser}:${HTTPPassword}"
    def userpass = "Basic " + userpassascii.encodeAsBase64().toString()

    log.debug "The device id configured is: $device.deviceNetworkId"

    def path = varCommand
    log.debug "path is: $path"
    def body = "" 

    def headers = [:] 
    headers.put("HOST", "$host:$LocalDevicePort")
    headers.put("Content-Type", "application/x-www-form-urlencoded")
    if (HTTPAuth) {
        headers.put("Authorization", userpass)
    }
    log.debug "The Header is $headers"
    def method = "POST"
    try {
        if (DevicePostGet.toUpperCase() == "GET") {
            method = "GET"
            }
        }
    catch (Exception e) {
        settings.DevicePostGet = "POST"
        log.debug e
        log.debug "You must not have set the preference for the DevicePOSTGET option"
    }
    log.debug "The method is $method"
    try {
        def hubAction = new physicalgraph.device.HubAction(
            method: method,
            path: path,
            body: body,
            headers: headers
            )
        log.debug hubAction
        return hubAction
    }
    catch (Exception e) {
        log.debug "Hit Exception $e on $hubAction"
    }
    
    //sendEvent
    if (varCommand == "off"){
        sendEvent(name: "switch", value: "off")
        log.debug "Executing OFF"
    } else {
        sendEvent(name: "switch", value: "on")
        log.debug "Executing ON"
    }
    
}
