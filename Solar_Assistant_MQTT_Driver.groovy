/**
 *  ****************  Solar Assistant MQTT Driver  ****************
 *
 *  This driver is based on Aaron Ward's driver located here: https://raw.githubusercontent.com/PrayerfulDrop/Hubitat/master/drivers/Generic%20MQTT%20Client.groovy
 *
 *  Design Usage:
 *  This driver is a designed to make it easier to communicate with Victron GX devices via MQTT.
 *
 *  Copyright 2019 Aaron Ward
 *  Modifications Copyright 2021 Jeremy Akers
 *
 * ------------------------------------------------------------------------------------------------------------------------------
 *  Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except
 *  in compliance with the License. You may obtain a copy of the License at:
 *
 *      http://www.apache.org/licenses/LICENSE-2.0
 *
 *  Unless required by applicable law or agreed to in writing, software distributed under the License is distributed
 *  on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the License
 *  for the specific language governing permissions and limitations under the License.
 *
 * ------------------------------------------------------------------------------------------------------------------------------
 *
 *
 *  Changes:
 *  2.0.0 - Forked from Aaron Ward's driver and modified to poll specific MQTT topics for Victron devices such as voltage, power, energy, temperature, etc
 *  1.0.4 - added generic notification and hub event support
 *  1.0.3 - added retained and QOS support
 *  1.0.2 - added support for AppWatchDogv2
 *  1.0.1 - added importURL and updated to new MQTT client methods
 *  1.0.0 - Initial release
 */
import groovy.json.JsonSlurper
import groovy.json.JsonOutput

metadata {
    definition (name: "Solar Assistant MQTT Driver", namespace: "jeremy.akers", author: "Jeremy Akers & Aaron Ward") {
        capability "Initialize"
        capability "Notification"
        capability "Sensor"
        capability "Switch"
        capability "PowerMeter"
        capability "EnergyMeter"
        capability "VoltageMeasurement"
        capability "Battery"
        capability "TemperatureMeasurement"
        command "updateVersion"
        command "poll"
        command "logsOff"
	    command "publishMsg", ["String"]
        command "setMode", ["number"]
        command "disconnect"
        command "set_monitored_battery_soc", ["number"]
        attribute "current", "number"
	    attribute "delay", "number"
	    attribute "distance", "number"
	    attribute "dwDriverInfo", "string"
        attribute "status", "string"
        attribute "charge_limit", "number"
        attribute "mode", "number"
        attribute "min_cell_voltage", "number"
        attribute "max_cell_voltage", "number"
        
	   }

    preferences {
        input name: "polltime", type: "number", title:"How often to keepalive in minutes", description:"Keepalive time (minutes)", required: false, displayDuringSetup: true
        input name: "MQTTBroker", type: "text", title: "MQTT Broker Address:", required: true, displayDuringSetup: true
		input name: "username", type: "text", title: "MQTT Username:", description: "(blank if none)", required: false, displayDuringSetup: true
		input name: "password", type: "password", title: "MQTT Password:", description: "(blank if none)", required: false, displayDuringSetup: true
        input name: "keepalive_topic", type: "text", title: "KeepAlive Topic:", description: "Example Topic (topic/device/#)", required: false, displayDuringSetup: true
        input name: "switch_topic", type: "text", title: "Switch Topic:", description: "Example Topic (topic/device/#)", required: false, displayDuringSetup: true
        input name: "switch_on_val", type: "text", title: "Switch On Value:", description: "Value", required: false, displayDuringSetup: true
        input name: "switch_off_val", type: "text", title: "Switch Off Value:", description: "Value", required: false, displayDuringSetup: true
		input name: "voltage_topic", type: "text", title: "Voltage Topic:", description: "Example Topic (topic/device/#)", required: false, displayDuringSetup: true
        input name: "min_cell_voltage_topic", type: "text", title: "Min Cell Voltage Topic:", description: "Example Topic (topic/device/#)", required: false, displayDuringSetup: true
        input name: "max_cell_voltage_topic", type: "text", title: "Max Cell Voltage Topic:", description: "Example Topic (topic/device/#)", required: false, displayDuringSetup: true
		input name: "power_topic", type: "text", title: "Power Topic:", description: "Example Topic (topic/device/#)", required: false, displayDuringSetup: true
        input name: "load_topic", type: "text", title: "Inverter Load Topic:", description: "Example Topic (topic/device/#)", required: false, displayDuringSetup: true
		input name: "energy_topic", type: "text", title: "Daily Energy Topic:", description: "Example Topic (topic/device/#)", required: false, displayDuringSetup: true
		input name: "soc_topic", type: "text", title: "Battery State of Charge Topic:", description: "Example Topic (topic/device/#)", required: false, displayDuringSetup: true
        input name: "temp_topic", type: "text", title: "Temperature Topic:", description: "Example Topic (topic/device/#)", required: false, displayDuringSetup: true
		input name: "charge_limit", type: "text", title: "Battery Max Charge Current Limit:", description: "Example Topic (topic/device/#)", required: false, displayDuringSetup: true        
        input name: "count_to_avg", type: "number", title: "Number of messages to accumulate/average:", description: "Number of messages to accumulate/average", required: true, displayDuringSetup: true

		input name: "topicPub", type: "text", title: "Topic to Publish:", description: "Topic Value (topic/device/value)", required: false, displayDuringSetup: true
        input name: "QOS", type: "text", title: "QOS Value:", required: false, defaultValue: "1", displayDuringSetup: true
        input name: "retained", type: "bool", title: "Retain message:", required: false, defaultValue: false, displayDuringSetup: true
        input name: "json_payload", type: "bool", title: "JSON Payloads?", required: true, defaultValue: false, displayDuringSetup: true
	    input("logEnable", "bool", title: "Enable logging", required: true, defaultValue: true)
    }

}

def set_monitored_battery_soc(newSoC)
{
    log.info "Setting state.monitored_battery_soc to $newSoC"
    state.monitored_battery_soc = newSoC
    log.info "state.monitored_battery_soc = ${state.monitored_battery_soc}"
}

def installed() {
    log.info "installed..."
}

def setVersion(){
    appName = "MQTT_Solar_Assistant_Driver"
	version = "2.0.0" 
    dwInfo = "${appName}:${version}"
    sendEvent(name: "dwDriverInfo", value: dwInfo, displayed: true)
}

def updateVersion() {
    log.info "In updateVersion"
    setVersion()
}

void eventProcess(Map evt) {
    if (device.currentValue(evt.name).toString() != evt.value.toString() || !eventFilter) {
        if (txtEnable && evt.descriptionText) log.info evt.descriptionText
        evt.isStateChange=true
        sendEvent(evt)
    }
}

def poll()
{
    if(interfaces.mqtt.isConnected())
    {
        interfaces.mqtt.publish(settings?.keepalive_topic, '', settings?.QOS.toInteger(), settings?.retained)
    }
    else
    {
        log.info "Poll: Solar Assistant MQTT Disconnected"
        initialize()
    }
}

def on()
{
    setMode(settings.switch_on_val)
}

def off()
{
    setMode(settings.switch_off_val)
}

def disconnect()
{
    interfaces.mqtt.disconnect()
    sendEvent(name: "status", value: "disconnected", unit: "message", descriptionText: "Disconnected from MQTT", isStateChange: true)
}


def setMode(newMode)
{
    topic_prefix = settings?.switch_topic.substring(0, settings?.switch_topic.lastIndexOf("/")+1)
    write_topic = topic_prefix + 'set'
    write_val = newMode
    log.debug("Writing: '${write_val}' to '${write_topic}'")
    interfaces.mqtt.publish(write_topic, write_val, settings?.QOS.toInteger(), false)
/*    if(newMode == settings?.switch_off_val) 
    {
        sendEvent(name: "power", value: "0", unit: "W", displayed: true)
        state.powers = []
    }*/
}

// Parse incoming device messages to generate events
def parse(String description) {
    def slurper = new JsonSlurper()
    def parsed = new Object()
    Date date = new Date()
    parsedMessageMap = interfaces.mqtt.parseMessage(description)
    topic = parsedMessageMap.topic
	topic_name = topic.substring(topic.lastIndexOf("/") + 1)
	payload = parsedMessageMap.payload
    //log.debug "Description: ${description}"
    //log.debug "Parsed MQTT Map: ${parsedMessageMap}"
    if(json_payload)
    {
        try
        {
            parsed = slurper.parseText(payload)
            payload = parsed.value
        }
        catch (Exception e)
        {
            log.debug "Error parsing JSON for topic: " + topic + ", payload was: " + payload
            log.debug "Error message: " + e
        }
    }
    if (logEnable) log.debug "Topic: " + topic + ", Payload: " + payload
    //sendEvent(name: "${topic_name}", value: "${payload}", displayed: true)
	//sendEvent(name: "Last Payload Received", value: "Topic: ${topic} - ${date.toString()}", displayed: true)
	//state."${topic_name}" = "${payload}"
	//state.lastpayloadreceived = "Topic: ${topic} : ${payload} - ${date.toString()}"
    switch(topic)
    {
        case settings.switch_topic:
            if (payload == 'Disabled')
            {
                sendEvent(name: "switch", value: "off")
                sendEvent(name: "power", value: "0", unit: "W", displayed: true)
                state.powers = []
            }
            else if(payload == 'Enabled')
            {
                sendEvent(name: "switch", value: "on")
            }
            else
            {
                log.error ("Invalid switch setting received: ${payload}")
            }
        break
        case settings.energy_topic:
            energy = payload.toFloat().round(2)
            sendEvent(name: "energy", value: "${energy}", unit: "kwh", displayed: true)
        break
        case settings.power_topic:
            state.lastpowertime = now()
        
            if(payload)
            {
                power = payload.toFloat().round(2)
                battery = device.currentValue('battery')
                state.powers << power
                if(settings?.topicPub && !settings?.load_topic)
                {
                    if (battery >= 99)
                        chargepower = (power * 3.75)
                    else
                        chargepower = (power * 2.75)
                
                    if (chargepower < 0) 
                       chargepower = 0
                
                    if(chargepower > 0)
                    {
                        if(state.monitored_battery_soc > 50)
                            chargemod = (state.monitored_battery_soc - 50) * 2.25;
                        else
                            chargemod = 0;
                        if(logEnable) log.info "Parse Power: state.monitored_battery_soc = " + state.monitored_battery_soc + ", chargepower = $chargepower, charge mod % = ($chargemod * 100.0) / 10000.0 = " + ((chargemod * 100.0) / 10000.0)
                        mod_chargepower = chargepower * (chargemod * 100.0) / 10000.0
                        if(chargepower > 11000)
                            min_chargepower = chargepower - 11000
                        else
                            min_chargepower = 0
                        if(mod_chargepower < min_chargepower)
                            mod_chargepower = min_chargepower
                        if(logEnable) log.info "Parse Power: min chargepower = $min_chargepower, modified chargepower = $mod_chargepower"
                        publishMsg(mod_chargepower.toString())
                    }
                }
            }
            else
            {
                state.powers = []
                sendEvent(name: "power", value: "0", unit: "W", displayed: true)
            }

            
            if (state.powers.size() >= settings.count_to_avg)
            {
                sendAverages()
            }
        break
        case settings.load_topic:
            //state.lastloadtime = now()  // Not sending events for this topic
        
            if(payload)
            {
                //state.loads << load  // Not sending events for this topic
                if(settings?.topicPub)
                {
                	load = payload.toFloat().round(2)
                	mybattery = device.currentValue('battery')
                	ev_battery = state.monitored_battery_soc //100 //hubitat.app.HubVariables.getVariable("battery_soc_plugged_ev_at_home")
                    battery = mybattery + (80 - ev_battery)
                    
                    if(battery > 50)
                    {
                    	chargemod = (battery - 50) * 2;
                    	loadmod = 10000.0 * chargemod / 100.0
                    }
                    else
                    	loadmod = 0.0
                    
                    mod_load = load - loadmod + 10000;
                    log.info "mybattery = $mybattery, ev_battery = $ev_battery, battery = $battery, load = $load, chargemod = $chargemod, loadmod = $loadmod, modified load = $mod_load"
                    publishMsg(mod_load.toString())
                    
                }
            }

        break
        case settings.voltage_topic:
            state.lastvoltagetime = now()
            voltage = payload.toFloat().round(2)
            state.voltages << voltage
            if (state.voltages.size() >= settings.count_to_avg)
            {
                sendAverages()
            }
        break
        case settings.min_cell_voltage_topic:
            state.lastminvoltagetime = now()
            voltage = payload.toFloat().round(2)
            state.min_cell_voltages << voltage
            if (state.min_cell_voltages.size() >= settings.count_to_avg)
            {
                sendAverages()
            }
        break
        case settings.max_cell_voltage_topic:
            state.lastmaxvoltagetime = now()
            voltage = payload.toFloat().round(2)
            state.max_cell_voltages << voltage
            if (state.max_cell_voltages.size() >= settings.count_to_avg)
            {
                sendAverages()
            }
        break
        case settings.soc_topic:
            soc = payload.toFloat().round(1)
            sendEvent(name: "battery", value: "${soc}", unit: "%", displayed: true)
        break   
        case settings.temp_topic:
            temp = payload.toFloat().round(1)
            sendEvent(name: "temperature", value: "${temp}", unit: "C", displayed: true)
        break   
        case settings.charge_limit:
            limit = payload.toFloat().round(1)
            sendEvent(name: "charge_limit", value: "${limit}", unit: "A", displayed: true)
        break  
    }
    
}

def sendAverages()
{
    if(state.powers.size())
    {
        int avg = 0;
        //if(state.powers.last() > 0)
        //{
            float sum = state.powers.sum()
            float size = state.powers.size()
            avg = (sum / size).round()
        //    if (logEnable) log.debug "sum = ${sum}, size = ${size}, avg = ${avg}"
        //}
        if (logEnable) log.debug "sum = ${sum}, size = ${size}, avg = ${avg}"
        sendEvent(name: "power", descriptionText: "Power is ${avg} watts", value: "${avg}", unit: "W", displayed: true)
        state.powers = []
    }
/*    else if(now() - state.lastpowertime > 30)
    {
        log.info "No power reported in > 30 seconds"
    }*/
    if(state.voltages && state.voltages.size())
    {
        float avg = 0.0
        if(state.voltages.last() > 0)
        {
            float sum = state.voltages.sum()
            float size = state.voltages.size()
            avg = (sum / size).round()
        }
        float sum = state.voltages.sum()
        float size = state.voltages.size()
        avg = (sum / size).round(1)
        sendEvent(name: "voltage", value: "${avg}", unit: "V", displayed: true)
        state.voltages = []
    }
    if(state.min_cell_voltages && state.min_cell_voltages.size())
    {
        float avg = 0.0
        if(state.min_cell_voltages.last() > 0)
        {
            float sum = state.min_cell_voltages.sum()
            float size = state.min_cell_voltages.size()
            avg = (sum / size).round()
        }
        float sum = state.min_cell_voltages.sum()
        float size = state.min_cell_voltages.size()
        avg = (sum / size).round(2)
        sendEvent(name: "min_cell_voltage", value: "${avg}", unit: "V", displayed: true)
        state.min_cell_voltages = []
    }
    if(state.max_cell_voltages && state.max_cell_voltages.size())
    {
        float avg = 0.0
        if(state.max_cell_voltages.last() > 0)
        {
            float sum = state.max_cell_voltages.sum()
            float size = state.max_cell_voltages.size()
            avg = (sum / size).round()
        }
        float sum = state.max_cell_voltages.sum()
        float size = state.max_cell_voltages.size()
        avg = (sum / size).round(2)
        sendEvent(name: "max_cell_voltage", value: "${avg}", unit: "V", displayed: true)
        state.max_cell_voltages = []
    }
}

def publishMsg(String s) {
    if (logEnable) log.debug "Sent this: ${s} to ${settings?.topicPub} - QOS Value: ${settings?.QOS.toInteger()} - Retained: ${settings?.retained}"
    if(settings?.topicPub)
        interfaces.mqtt.publish(settings?.topicPub, s, settings?.QOS.toInteger(), settings?.retained)
}

def deviceNotification(String s) {
    if (logEnable) log.debug "Sent this: ${s} to ${settings?.topicPub} - QOS Value: ${settings?.QOS.toInteger()} - Retained: ${settings?.retained}"
    
    // Attempt to parse message as JSON
    def slurper = new JsonSlurper()
	def parsed = slurper.parseText(s)

    // If this is a hub event message, do something special
	if (parsed.keySet().contains('path') && 
        parsed.keySet().contains('body') &&
        parsed.body.keySet().contains('name') &&
        parsed.body.keySet().contains('type') &&
        parsed.body.keySet().contains('value') &&
        (parsed.path == '/push')) {
          def body = new JsonOutput().toJson(parsed.body)
          interfaces.mqtt.publish("${settings?.topicPub}/push/${parsed.body.name}/${parsed.body.type}/value", parsed.body.value, settings?.QOS.toInteger(), settings?.retained)
	} else {
    // If its not, or json parse fails dump the input string to the topic
        interfaces.mqtt.publish(settings?.topicPub, s, settings?.QOS.toInteger(), settings?.retained)
    }
}

def updated() {
    if (logEnable) log.info('Solar Assistant MQTT: updated()')
	unschedule()
    //interfaces.mqtt.disconnect()
	initialize()
    if(settings.polltime && settings.keepalive_topic)
    {    
	    if (logEnable) log.debug("Scheduling for: 0 */${settings.polltime} * * * ?")
	    schedule("0 */${settings.polltime} * * * ?", poll)
        poll()
    }
}

def uninstalled() {
    if (logEnable) log.info "Disconnecting from mqtt"
    interfaces.mqtt.disconnect()
}


def initialize() {
	if (logEnable) runIn(900,logsOff)
	try {
        if(settings?.retained==null) settings?.retained=false
        if(settings?.QOS==null) setting?.QOS="1"
        state.voltages=[]
        state.min_cell_voltages=[]
        state.max_cell_voltages=[]
        state.energycount=0
        state.powers=[]
        state.monitored_battery_soc = 0
        //open connection
		mqttbroker = "tcp://" + settings?.MQTTBroker + ":1883"
        interfaces.mqtt.connect(mqttbroker, device.getName(), settings?.username,settings?.password)
        //give it a chance to start
        pauseExecution(1000)
        log.info "Connection established for: " + device.getName()
        sendEvent(name: "status", value: "connected", unit: "message", descriptionText: "Connected to MQTT", isStateChange: true)
        if(settings?.switch_topic)
        {
		    log.info "Subscribed to: ${settings?.switch_topic}"
            interfaces.mqtt.subscribe(settings?.switch_topic)
        }
        if(settings?.voltage_topic)
        {
		    log.info "Subscribed to: ${settings?.voltage_topic}"
            interfaces.mqtt.subscribe(settings?.voltage_topic)
        }
        if(settings?.min_cell_voltage_topic)
        {
		    log.info "Subscribed to: ${settings?.min_cell_voltage_topic}"
            interfaces.mqtt.subscribe(settings?.min_cell_voltage_topic)
        }
        if(settings?.max_cell_voltage_topic)
        {
		    log.info "Subscribed to: ${settings?.max_cell_voltage_topic}"
            interfaces.mqtt.subscribe(settings?.max_cell_voltage_topic)
        }        
        if(settings?.power_topic)
        {
		    log.info "Subscribed to: ${settings?.power_topic}"
            interfaces.mqtt.subscribe(settings?.power_topic)
        }
        if(settings?.load_topic)
        {
		    log.info "Subscribed to: ${settings?.power_topic}"
            interfaces.mqtt.subscribe(settings?.load_topic)
        }
        if(settings?.energy_topic)
        {
		    log.info "Subscribed to: ${settings?.energy_topic}"
            interfaces.mqtt.subscribe(settings?.energy_topic)
        }
        if(settings?.soc_topic)
        {
		    log.info "Subscribed to: ${settings?.soc_topic}"
            interfaces.mqtt.subscribe(settings?.soc_topic)
        }     
        if(settings?.temp_topic)
        {
		    log.info "Subscribed to: ${settings?.temp_topic}"
            interfaces.mqtt.subscribe(settings?.temp_topic)
        }    
        if(settings?.charge_limit)
        {
		    log.info "Subscribed to: ${settings?.charge_limit}"
            interfaces.mqtt.subscribe(settings?.charge_limit)
        }  
    } 
    catch(e) 
    {
        log.debug "Initialize error: ${e.toString()}"
        log.debug "Caused by: ${e.getCause()}"
        log.debug "Stacktrace: ${e.stackTrace}"
        sendEvent(name: "status", value: "error", unit: "message", descriptionText: e.toString(), isStateChange: true)
    }
}

def mqttClientStatus(String status){
    if (logEnable) log.debug "MQTTStatus - : ${status}"
    if (status.startsWith("Error"))
    {
        sendEvent(name: "status", value: "error", unit: "message", descriptionText: status, isStateChange: true)
        initialize()
    }
}

def logsOff(){
    log.warn "Debug logging disabled."
    //updateSetting("logEnable",false)
    device.updateSetting("logEnable",[value:"false",type:"bool"])
}