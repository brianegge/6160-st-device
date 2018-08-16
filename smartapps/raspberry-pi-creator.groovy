/**
 *  Raspberry Pi 6160 Creator
 *  Category: Smart App
 *
 *  Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except
 *  in compliance with the License. You may obtain a copy of the License at:
 *
 *      http://www.apache.org/licenses/LICENSE-2.0
 *
 *  Unless required by applicable law or agreed to in writing, software distributed under the License is distributed
 *  on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the License
 *  for the specific language governing permissions and limitations under the License.
 *
 *  Credit: Soon Chye - HTTP Switch Creator
 *  Credit: Eric Roberts (baldeagle072) - Virtual switch creator
 *  Credit: tguerena and surge919 - URI Switch
 *  
 */
public static String version() { return "1.0.0" }

definition(
    name: "Raspberry Pi 6160 Creator",
    namespace: "brianegge",
    author: "Brian Egge",
    description: "Creates 6160 Keypad devices",
    category:    "Safety & Security",
    iconUrl: "https://github.com/chancsc/icon/raw/master/standard-tile%401x.png",
    iconX2Url: "https://github.com/chancsc/icon/raw/master/standard-tile@2x.png",
    iconX3Url: "https://github.com/chancsc/icon/raw/master/standard-tile@3x.png"
    singleInstance: true
)


preferences {
    section("Create Raspberry Pi 6160") {
        input "keypadLabel", "text", title: "Keypad Label", required: true
    }
    section("on this hub...") {
        input "theHub", "hub", multiple: false, required: true
    }
}

def installed() {
    log.debug "Installed with settings: ${settings}"

    initialize()
}

def updated() {
    log.debug "Updated with settings: ${settings}"

    unsubscribe()
    initialize()
}

def initialize() {
    def deviceId = app.id
    log.debug(deviceId)
    def existing = getChildDevice(deviceId)
    if (!existing) {
        def childDevice = addChildDevice("brianegge", "6160 Keypad", deviceId, theHub.id, [label: switchLabel])
    }
}

def uninstalled() {
    removeChildDevices(getChildDevices())
}

private removeChildDevices(delete) {
    delete.each {
        deleteChildDevice(it.deviceNetworkId)
    }
}
