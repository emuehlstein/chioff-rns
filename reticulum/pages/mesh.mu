`F0cf`c

>>Chicago Mesh Network

`a`Ffff

>MeshCore LoRa Network

The Chicago mesh runs MeshCore protocol over LoRa radios
across the Chicagoland area. Nodes relay messages, share
positions, and provide coverage for off-grid comms.

`F0cf
-

>MeshCore Radio Parameters

`Ffb3`l
  Frequency:        910.525 MHz
  Bandwidth:        62.5 KHz
  Spreading Factor: 7
  Coding Rate:      5
  Path Hash Mode:   2 (3-byte)
  Loop Detection:   Moderate
`a`Ffff

`Ff55Note:`Ffff These are `!MeshCore`! parameters (not Reticulum).
MeshCore and Reticulum are separate protocols on
separate frequencies.

`F0cf
-

>Reticulum Radio Parameters

`Ffb3`l
  Frequency:        914.875 MHz
  Bandwidth:        125.0 KHz
  Spreading Factor: 8
  Coding Rate:      5
  TX Power:         22 dBm (hardware dependent)
`a`Ffff

See the `[`F0cfConnect`:/page/connect.mu]`Ffff page for full RNode config.

`F0cf
-

>Observer Network

`FfffMQTT observers bridge radio traffic to the internet,
feeding CoreScope, the live map, and health check tools.

Observer MQTT brokers (by priority):

`F3f1  1. `Ffb3LetsMesh US `Ffff(mqtt-us-v1.letsmesh.net)
`F3f1  2. `Ffb3ChiMesh.org `Ffff(mqtt.chimesh.org)
`F3f1  3. `Ffb3Chicago Offline `Ffff(wsmqtt.chicagooffline.com)
`F3f1  4. `Ffb3rflab.io `Ffff(mqtt.rflab.io)
`F3f1  5. `Ffb3LetsMesh EU `Ffff(mqtt-eu-v1.letsmesh.net)
`F3f1  6. `Ffb3CO TCP fallback `Ffff(mqtt.chioff.com:1883)

Pre-built observer firmware at:
     `Ffb3 chicagooffline.com/observers

`F0cf
-

>Node Types

`F3f1  >>  `!`FfffCompanions`!`Ffff — handheld/personal nodes
`F3f1  >>  `!`FfffRepeaters`!`Ffff  — extend mesh coverage
`F3f1  >>  `!`FfffRoom Servers`!`Ffff — group chat hosting
`F3f1  >>  `!`FfffObservers`!`Ffff  — MQTT bridge to internet

`F555
-
`c`[`F0cf<< Back to Home`:/page/index.mu]
