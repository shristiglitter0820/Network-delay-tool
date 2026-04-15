#!/usr/bin/env python3
"""
measure_delay.py – Automated Network Delay Measurement & Analysis
==================================================================
Starts the Mininet topology, runs structured ping + iperf tests,
prints a formatted report, and saves raw results to results.txt.

Run this script directly (as root):
    sudo python3 measure_delay.py [--block]

    --block  : run Scenario 2 (h1↔h3 blocked) instead of normal mode

Author : SDN Mininet Project
"""

import re
import sys
import time
import argparse
import datetime
from mininet.log import setLogLevel, info
from topology import create_delay_topology


# ─────────────────────────────────────────────────────────────────────────────
#  Ping helpers
# ─────────────────────────────────────────────────────────────────────────────

def run_ping(src, dst_ip, count=10, interval=0.3):
    """
    Ping dst_ip from src host object.
    Returns (raw_output, stats_dict).

    stats_dict keys: min, avg, max, mdev, packet_loss, rtts (list)
    """
    cmd = 'ping -c %d -i %.1f %s' % (count, interval, dst_ip)
    raw = src.cmd(cmd)
    return raw, _parse_ping(raw)


def _parse_ping(output):
    """Extract RTT statistics from ping stdout."""
    stats = {'rtts': [], 'min': None, 'avg': None,
             'max': None, 'mdev': None, 'packet_loss': 100}

    # Individual RTT values
    for m in re.finditer(r'time=(\d+\.?\d*)\s*ms', output):
        stats['rtts'].append(float(m.group(1)))

    # Summary line: rtt min/avg/max/mdev = X/X/X/X ms
    m = re.search(r'(\d+\.?\d*)/(\d+\.?\d*)/(\d+\.?\d*)/(\d+\.?\d*)\s*ms',
                  output)
    if m:
        stats['min']  = float(m.group(1))
        stats['avg']  = float(m.group(2))
        stats['max']  = float(m.group(3))
        stats['mdev'] = float(m.group(4))

    # Packet loss
    m = re.search(r'(\d+)%\s*packet loss', output)
    if m:
        stats['packet_loss'] = int(m.group(1))

    return stats


# ─────────────────────────────────────────────────────────────────────────────
#  Test scenarios
# ─────────────────────────────────────────────────────────────────────────────

SEPARATOR = "=" * 64

def scenario1_normal(net, log_lines):
    """
    Scenario 1 – Normal operation.
    Ping between all meaningful host pairs; compare RTTs.
    """
    header = "\n%s\n  SCENARIO 1: Normal Forwarding – Delay Comparison\n%s" % (
        SEPARATOR, SEPARATOR)
    print(header)
    log_lines.append(header)

    # (src_name, dst_name, human-readable path description, expected RTT range)
    tests = [
        ('h3', 'h4', 'SAME-SW  h3 <-> h4  (s3 internal)',              '< 12 ms'),
        ('h1', 'h2', 'SHORT    h1 -> s1 -[10ms]-> s2 -> h2',           '≈ 28 ms'),
        ('h2', 'h3', 'MEDIUM   h2 -> s2 -[25ms]-> s3 -> h3',           '≈ 58 ms'),
        ('h1', 'h3', 'LONG     h1 -> s1 -[10ms]-> s2 -[25ms]-> s3->h3','≈ 78 ms'),
    ]

    results = {}
    for src_name, dst_name, desc, expected in tests:
        src = net.get(src_name)
        dst = net.get(dst_name)
        dst_ip = dst.IP()

        print("\n  [%s → %s]  %s" % (src_name, dst_name, desc))
        print("  Expected RTT: %s" % expected)
        print("  Pinging %s …" % dst_ip, flush=True)

        raw, stats = run_ping(src, dst_ip, count=10)

        if stats['avg'] is not None:
            line = ("  RTT  min/avg/max/mdev = "
                    "%.2f / %.2f / %.2f / %.2f ms   |  loss=%d%%" % (
                        stats['min'], stats['avg'], stats['max'],
                        stats['mdev'], stats['packet_loss']))
        else:
            line = "  [!] No reply from %s" % dst_ip

        print(line)
        log_lines.append("\n[%s → %s] %s" % (src_name, dst_name, desc))
        log_lines.append(line)
        results['%s->%s' % (src_name, dst_name)] = stats

    _comparative_analysis(results, log_lines)
    return results


def scenario2_blocking(net, log_lines):
    """
    Scenario 2 – Controller drops h1 ↔ h3 traffic.
    Verify: h1 ping h3 fails, all other pairs still work.
    NOTE: This scenario requires the controller to be started with
          --block=True (the topology script handles this message).
    """
    header = "\n%s\n  SCENARIO 2: Blocking Mode – h1 ↔ h3 Blocked\n%s" % (
        SEPARATOR, SEPARATOR)
    print(header)
    log_lines.append(header)

    print("\n  NOTE: Ensure POX controller was started with --block=True")
    print("  Expected: h1 → h3 = 100% loss   |   h1 → h2 = reachable\n")

    tests_blocked   = [('h1', 'h3'), ('h3', 'h1')]
    tests_allowed   = [('h1', 'h2'), ('h2', 'h4'), ('h3', 'h4')]

    print("  ── Blocked pairs (expecting 100% loss) ──────────────────────")
    for src_n, dst_n in tests_blocked:
        src  = net.get(src_n)
        dst  = net.get(dst_n)
        raw, stats = run_ping(src, dst.IP(), count=5, interval=0.5)
        loss = stats['packet_loss']
        result_str = "PASS (blocked)" if loss == 100 else "FAIL (packets got through!)"
        line = "  %s → %s : loss=%d%%  → %s" % (src_n, dst_n, loss, result_str)
        print(line)
        log_lines.append(line)

    print("\n  ── Allowed pairs (expecting normal RTT) ─────────────────────")
    for src_n, dst_n in tests_allowed:
        src  = net.get(src_n)
        dst  = net.get(dst_n)
        raw, stats = run_ping(src, dst.IP(), count=5, interval=0.3)
        if stats['avg'] is not None:
            line = ("  %s → %s : avg RTT = %.2f ms  loss=%d%%" % (
                src_n, dst_n, stats['avg'], stats['packet_loss']))
        else:
            line = "  %s → %s : no reply" % (src_n, dst_n)
        print(line)
        log_lines.append(line)


def iperf_test(net, log_lines):
    """Quick iperf throughput test alongside delay measurements."""
    header = "\n%s\n  IPERF THROUGHPUT TEST\n%s" % (SEPARATOR, SEPARATOR)
    print(header)
    log_lines.append(header)

    h1 = net.get('h1')
    h2 = net.get('h2')
    h3 = net.get('h3')

    # Server on h2
    h2.cmd('iperf -s -p 5201 &')
    time.sleep(0.5)

    for src_n, dst in [('h1', h2), ('h3', h2)]:
        src = net.get(src_n)
        print("\n  [%s → h2]  iperf TCP 5 s …" % src_n, flush=True)
        out = src.cmd('iperf -c %s -p 5201 -t 5' % dst.IP())
        # Extract bandwidth line
        for line in out.splitlines():
            if 'Mbits/sec' in line or 'Gbits/sec' in line:
                print("  " + line.strip())
                log_lines.append("[%s → h2] %s" % (src_n, line.strip()))

    h2.cmd('kill %iperf 2>/dev/null')


# ─────────────────────────────────────────────────────────────────────────────
#  Analysis helpers
# ─────────────────────────────────────────────────────────────────────────────

def _comparative_analysis(results, log_lines):
    """Print a side-by-side comparison table."""
    print("\n%s" % SEPARATOR)
    print("  COMPARATIVE DELAY ANALYSIS")
    print(SEPARATOR)
    print("  %-18s  %8s  %8s  %8s  %8s" % (
        "Pair", "min(ms)", "avg(ms)", "max(ms)", "jitter"))
    print("  " + "-" * 60)

    for pair, s in results.items():
        if s['avg'] is not None:
            row = "  %-18s  %8.2f  %8.2f  %8.2f  %8.2f" % (
                pair, s['min'], s['avg'], s['max'], s['mdev'])
        else:
            row = "  %-18s  %s" % (pair, "no reply")
        print(row)
        log_lines.append(row)

    # Ratio commentary
    s_short = results.get('h1->h2')
    s_long  = results.get('h1->h3')
    if s_short and s_long and s_short['avg'] and s_long['avg']:
        ratio = s_long['avg'] / s_short['avg']
        msg = ("\n  Long path RTT is {:.1f}× the short path RTT "
               "({:.2f} ms vs {:.2f} ms)".format(
                   ratio, s_long['avg'], s_short['avg']))
        print(msg)
        log_lines.append(msg)


# ─────────────────────────────────────────────────────────────────────────────
#  Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='Network Delay Measurement Tool – automated test runner')
    parser.add_argument('--block', action='store_true',
                        help='Run Scenario 2 (h1↔h3 blocked)')
    args = parser.parse_args()

    setLogLevel('warning')   # suppress Mininet noise in output

    print("\n%s" % SEPARATOR)
    print("  NETWORK DELAY MEASUREMENT TOOL")
    print("  Started: %s" % datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    print("  Mode   : %s" % ("BLOCKING (Scenario 2)" if args.block
                              else "NORMAL (Scenario 1)"))
    print(SEPARATOR)

    net = create_delay_topology()

    print('\n[*] Starting Mininet network …')
    net.start()
    time.sleep(2)   # let OVS and POX handshake settle

    print('[*] Warming up paths with initial pingAll …')
    net.pingAll(timeout=2)
    time.sleep(1)

    log_lines = []

    try:
        if args.block:
            scenario2_blocking(net, log_lines)
        else:
            scenario1_normal(net, log_lines)

        iperf_test(net, log_lines)

        # ── Save results ──────────────────────────────────────────────────────
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        fname = 'results_%s.txt' % ts
        with open(fname, 'w') as f:
            f.write("Network Delay Measurement Results\n")
            f.write("Generated: %s\n" % ts)
            f.write("\n".join(log_lines))
        print("\n[*] Results saved to %s" % fname)

    finally:
        print('\n[*] Stopping network …')
        net.stop()


if __name__ == '__main__':
    main()
