`F0cf`c

>>Connect to Chicago Offline

`a`Ffff

>TCP Transport (Internet)

Add this to your Reticulum config under `![interfaces]`!:

`Ffb3`l
  [[Chicago Offline]]
    type = TCPClientInterface
    enabled = yes
    target_host = rns.chicagooffline.com
    target_port = 4242
`a`Ffff

Works with `!Sideband`!, `!NomadNet`!, or any Reticulum app.
The node is always on and routes traffic for the network.

`F0cf
-

>LoRa Radio (Off-Grid)

`FfffIf you have an `!RNode`! or compatible LoRa hardware,
use these parameters to join the Chicago Offline
Reticulum radio network:

`Ffb3`l
  Frequency:        914.875 MHz
  Bandwidth:        125.0 KHz
  Spreading Factor: 8
  Coding Rate:      5
  TX Power:         22 dBm (check your hardware)
`a`Ffff

RNode config example:

`Ffb3`l
  [[RNode LoRa]]
    type = RNodeInterface
    enabled = yes
    port = /dev/ttyACM0
    frequency = 914875000
    bandwidth = 125000
    txpower = 22
    spreadingfactor = 8
    codingrate = 5
`a`Ffff

`F0cf
-

>Compatible Hardware

`F3f1  >>  `FfffRNode (any supported board)
`F3f1  >>  `FfffHeltec V3 / V4 / T114 with RNode firmware
`F3f1  >>  `FfffLilyGO T-Beam, T-LoRa
`F3f1  >>  `FfffRAK4631 based devices
`F3f1  >>  `FfffAny SX1262/SX1276 board running RNode FW

Flash RNode firmware with: `!rnodeconf --autoinstall`!

`F0cf
-

>Software

`Ffff
`F3f1  >>  `!`FfffNomadNet`!`Ffff  — terminal client + node browser
`F3f1  >>  `!`FfffSideband`!`Ffff  — mobile/desktop LXMF messenger
`F3f1  >>  `!`Ffffrns`!`Ffff       — core networking stack (rnsd)

`Ffb3pip install nomadnet`Ffff  (installs everything)

`F555
-
`c`F0cf`[Back to Home`/page/index.mu]
