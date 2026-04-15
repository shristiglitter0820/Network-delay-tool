# pox/ext/delay_monitor.py
"""
POX Controller – Network Delay Monitor
=======================================
Implements a learning switch with:
  • packet_in handling and MAC learning
  • Match-action flow rule installation (OpenFlow 1.0)
  • Per-switch statistics logging (packet_in events, flow count)
  • Scenario 2: optional host-pair BLOCKING (h1 ↔ h3 blocked)

Usage
-----
  Normal (all hosts communicate):
    ./pox.py log.level --DEBUG delay_monitor

  Blocking mode (h1 cannot reach h3):
    ./pox.py log.level --DEBUG delay_monitor --block=True

Author : SDN Mininet Project
"""

from pox.core import core
from pox.lib.util import dpid_to_str, str_to_bool
from pox.lib.recoco import Timer
import pox.openflow.libopenflow_01 as of
import datetime
import time

log = core.getLogger()

# ─── Flow-rule tuning knobs ───────────────────────────────────────────────────
FLOW_IDLE_TIMEOUT = 30     # seconds – idle flow removed
FLOW_HARD_TIMEOUT = 120    # seconds – flow removed regardless of activity
FLOW_PRIORITY     = 100    # base priority for learned flows
DROP_PRIORITY     = 200    # higher priority so drop rules win


# ─── Per-switch logic ─────────────────────────────────────────────────────────

class DelayMonitorSwitch(object):
    """
    One instance per connected switch.
    Learns MAC→port mappings and installs OpenFlow rules.
    """

    def __init__(self, connection, block_mode=False):
        self.connection  = connection
        self.block_mode  = block_mode          # True → block h1↔h3
        self.mac_to_port = {}                  # { mac_str : port_no }
        self.flow_count      = 0
        self.packet_in_count = 0
        self.dpid_str = dpid_to_str(connection.dpid)

        connection.addListeners(self)

        if block_mode:
            self._install_drop_rules()

        log.info("[%s] Switch connected  |  block_mode=%s",
                 self.dpid_str, block_mode)

    # ── Scenario 2 – drop rules for h1↔h3 ────────────────────────────────────

    def _install_drop_rules(self):
        """
        Install high-priority DROP rules so h1 (10.0.0.1) and
        h3 (10.0.0.3) cannot communicate in either direction.
        """
        for src_ip, dst_ip in [('10.0.0.1', '10.0.0.3'),
                                ('10.0.0.3', '10.0.0.1')]:
            msg = of.ofp_flow_mod()
            msg.match.dl_type  = 0x0800           # IPv4
            msg.match.nw_src   = src_ip
            msg.match.nw_dst   = dst_ip
            msg.priority       = DROP_PRIORITY
            msg.idle_timeout   = 0
            msg.hard_timeout   = 0
            # No actions → implicit DROP
            self.connection.send(msg)
            log.info("[%s] DROP rule installed: %s -> %s",
                     self.dpid_str, src_ip, dst_ip)

    # ── OpenFlow event handlers ───────────────────────────────────────────────

    def _handle_PacketIn(self, event):
        """
        Called for every packet the switch cannot handle locally.
        1. Learn source MAC → in-port mapping.
        2. If destination known → install flow rule + unicast.
        3. If destination unknown → flood.
        """
        self.packet_in_count += 1

        pkt      = event.parsed
        if not pkt.parsed:
            log.warning("[%s] Incomplete packet ignored", self.dpid_str)
            return

        ofp_msg  = event.ofp
        in_port  = event.port
        src_mac  = str(pkt.src)
        dst_mac  = str(pkt.dst)

        # ── MAC learning ──────────────────────────────────────────────────────
        self.mac_to_port[src_mac] = in_port
        log.debug("[%s] Learned  %s → port %d", self.dpid_str, src_mac, in_port)

        # ── Forwarding decision ───────────────────────────────────────────────
        if dst_mac in self.mac_to_port:
            out_port = self.mac_to_port[dst_mac]
            log.info("[%s] UNICAST  %s → %s  via port %d",
                     self.dpid_str, src_mac, dst_mac, out_port)
            self._install_flow(event, out_port)
            self._send_out(ofp_msg, out_port)
            self.flow_count += 1
        else:
            log.debug("[%s] FLOOD   src=%s  dst=%s (unknown)",
                      self.dpid_str, src_mac, dst_mac)
            self._send_out(ofp_msg, of.OFPP_FLOOD)

    # ── Flow rule helpers ─────────────────────────────────────────────────────

    def _install_flow(self, event, out_port):
        """
        Build and send an ofp_flow_mod message.

        Match  : destination MAC (+ optional in-port from packet)
        Action : output to learned port
        """
        pkt = event.parsed
        msg = of.ofp_flow_mod()

        # Match on the full packet tuple
        msg.match       = of.ofp_match.from_packet(pkt, event.port)
        msg.match.in_port = None   # allow same rule to match any in-port

        msg.idle_timeout = FLOW_IDLE_TIMEOUT
        msg.hard_timeout = FLOW_HARD_TIMEOUT
        msg.priority     = FLOW_PRIORITY
        msg.data         = event.ofp              # re-sends original packet

        msg.actions.append(of.ofp_action_output(port=out_port))
        self.connection.send(msg)

        log.info("[%s] FLOW_MOD installed: dst=%s → port %d  "
                 "(idle=%ds hard=%ds)",
                 self.dpid_str, str(pkt.dst), out_port,
                 FLOW_IDLE_TIMEOUT, FLOW_HARD_TIMEOUT)

    def _send_out(self, ofp_msg, out_port):
        """Send a packet-out message on the specified port."""
        msg = of.ofp_packet_out()
        msg.data = ofp_msg
        msg.actions.append(of.ofp_action_output(port=out_port))
        self.connection.send(msg)

    # ── Stats printer ─────────────────────────────────────────────────────────

    def print_stats(self):
        log.info("  ── Switch %s ──", self.dpid_str)
        log.info("     packet_in events : %d", self.packet_in_count)
        log.info("     flows installed  : %d", self.flow_count)
        log.info("     MAC table entries: %d", len(self.mac_to_port))
        for mac, port in self.mac_to_port.items():
            log.info("       %s → port %d", mac, port)


# ─── Top-level POX component ──────────────────────────────────────────────────

class DelayMonitor(object):
    """
    Manages one DelayMonitorSwitch per connected switch.
    Also fires a periodic stats timer.
    """

    def __init__(self, block_mode=False):
        self.block_mode = block_mode
        self.switches   = {}            # { dpid : DelayMonitorSwitch }

        core.openflow.addListeners(self)
        Timer(30, self._periodic_stats, recurring=True)

        log.info("=" * 55)
        log.info("  DelayMonitor controller started")
        log.info("  block_mode = %s  (h1↔h3 blocked if True)", block_mode)
        log.info("  Waiting for switch connections …")
        log.info("=" * 55)

    # ── OpenFlow connection events ────────────────────────────────────────────

    def _handle_ConnectionUp(self, event):
        dpid = event.connection.dpid
        log.info("Switch UP: %s", dpid_to_str(dpid))
        self.switches[dpid] = DelayMonitorSwitch(
            event.connection, block_mode=self.block_mode
        )

    def _handle_ConnectionDown(self, event):
        dpid = event.connection.dpid
        log.info("Switch DOWN: %s", dpid_to_str(dpid))
        self.switches.pop(dpid, None)

    # ── Periodic statistics ───────────────────────────────────────────────────

    def _periodic_stats(self):
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        log.info("")
        log.info("══════════════════════════════════════════════════")
        log.info("  DELAY MONITOR STATS   [%s]", ts)
        log.info("══════════════════════════════════════════════════")
        if not self.switches:
            log.info("  (no switches connected)")
        for sw in self.switches.values():
            sw.print_stats()
        log.info("══════════════════════════════════════════════════")
        log.info("")


# ─── POX launch entry-point ───────────────────────────────────────────────────

def launch(block=False):
    """
    Register the DelayMonitor component with POX core.

    Examples
    --------
    Normal mode   : ./pox.py log.level --DEBUG delay_monitor
    Blocking mode : ./pox.py log.level --DEBUG delay_monitor --block=True
    """
    block_mode = str_to_bool(str(block))
    core.registerNew(DelayMonitor, block_mode=block_mode)
