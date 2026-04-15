#!/usr/bin/env python3
"""
Network Delay Measurement Tool – Custom Mininet Topology
=========================================================
Topology Overview:

    h1 --[2ms]-- s1 --[10ms]-- s2 --[25ms]-- s3 --[2ms]-- h3
                                |                           |
                              [2ms]                       [2ms]
                                |                           |
                               h2                          h4

Expected one-way delays:
  h1 -> h2  :  2 + 10 + 2              = 14 ms  (RTT ≈ 28 ms)  [SHORT]
  h2 -> h3  :  2 + 25 + 2              = 29 ms  (RTT ≈ 58 ms)  [MEDIUM]
  h1 -> h3  :  2 + 10 + 25 + 2         = 39 ms  (RTT ≈ 78 ms)  [LONG]
  h3 -> h4  :  2 + 2                   =  4 ms  (RTT ≈  8 ms)  [SAME-SW]

Author : SDN Mininet Project
"""

from mininet.net import Mininet
from mininet.node import RemoteController, OVSSwitch
from mininet.cli import CLI
from mininet.log import setLogLevel, info
from mininet.link import TCLink


# ─────────────────────────────────────────────
#  Topology builder
# ─────────────────────────────────────────────

def create_delay_topology():
    """
    Build and return the Mininet network object.
    Uses TCLink so that every link can carry tc-netem delay settings.
    """

    net = Mininet(
        controller=RemoteController,
        switch=OVSSwitch,
        link=TCLink,
        autoSetMacs=True
    )

    # ── Controller ──────────────────────────────────────────────────────────
    info('*** Adding remote POX controller (127.0.0.1:6633)\n')
    net.addController(
        'c0',
        controller=RemoteController,
        ip='127.0.0.1',
        port=6633
    )

    # ── Switches ────────────────────────────────────────────────────────────
    info('*** Adding switches s1, s2, s3\n')
    s1 = net.addSwitch('s1', protocols='OpenFlow10')
    s2 = net.addSwitch('s2', protocols='OpenFlow10')
    s3 = net.addSwitch('s3', protocols='OpenFlow10')

    # ── Hosts ───────────────────────────────────────────────────────────────
    info('*** Adding hosts h1-h4\n')
    h1 = net.addHost('h1', ip='10.0.0.1/24', mac='00:00:00:00:00:01')
    h2 = net.addHost('h2', ip='10.0.0.2/24', mac='00:00:00:00:00:02')
    h3 = net.addHost('h3', ip='10.0.0.3/24', mac='00:00:00:00:00:03')
    h4 = net.addHost('h4', ip='10.0.0.4/24', mac='00:00:00:00:00:04')

    # ── Links ────────────────────────────────────────────────────────────────
    info('*** Adding links with configured delay values\n')

    # Host ↔ switch access links (2 ms each)
    net.addLink(h1, s1, cls=TCLink, delay='2ms', bw=100, loss=0)
    net.addLink(h2, s2, cls=TCLink, delay='2ms', bw=100, loss=0)
    net.addLink(h3, s3, cls=TCLink, delay='2ms', bw=100, loss=0)
    net.addLink(h4, s3, cls=TCLink, delay='2ms', bw=100, loss=0)

    # Switch ↔ switch backbone links (varying delays)
    net.addLink(s1, s2, cls=TCLink, delay='10ms', bw=100, loss=0)   # short hop
    net.addLink(s2, s3, cls=TCLink, delay='25ms', bw=100, loss=0)   # long hop

    return net


# ─────────────────────────────────────────────
#  Entry point
# ─────────────────────────────────────────────

if __name__ == '__main__':
    setLogLevel('info')
    net = create_delay_topology()

    info('\n*** Starting network\n')
    net.start()

    info('\n*** Running initial connectivity test (pingAll)\n')
    net.pingAll()

    info('\n*** Dropping into Mininet CLI – type "exit" to quit\n')
    CLI(net)

    info('\n*** Stopping network\n')
    net.stop()
