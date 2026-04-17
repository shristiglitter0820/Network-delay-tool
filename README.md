# Network Delay Measurement Tool
> SDN Mininet Project — Orange Problem #15 , SRN:PES1UG24CS903 ; NAME: SHRISTI SAHA

## Problem Statement

This project implements a **Network Delay Measurement Tool** using Mininet and a custom POX OpenFlow controller. The tool:

- Creates a topology with **configurable link delays** to produce measurable RTT differences across paths
- Installs **explicit OpenFlow flow rules** via a learning-switch controller
- Measures and **compares RTT (Round-Trip Time)** between host pairs using `ping`
- Analyses **delay variation (jitter)** and **throughput** using `iperf`
- Demonstrates two test scenarios: normal forwarding and access-controlled blocking

---

## Topology

```
h1 --[2ms]-- s1 --[10ms]-- s2 --[25ms]-- s3 --[2ms]-- h3
                             |                          |
                           [2ms]                      [2ms]
                             |                          |
                            h2                         h4
```

| Host | IP Address  | Switch | Notes           |
|------|-------------|--------|-----------------|
| h1   | 10.0.0.1/24 | s1     | Source host     |
| h2   | 10.0.0.2/24 | s2     | Mid-path host   |
| h3   | 10.0.0.3/24 | s3     | Far host        |
| h4   | 10.0.0.4/24 | s3     | Co-located w/h3 |

### Scenario 1 – Normal Forwarding (Actual Results)

| Pair | min (ms) | avg (ms) | max (ms) | jitter (ms) | Loss |
|------|----------|----------|----------|-------------|------|
| h3 ↔ h4 (same sw) | 8.45 | 9.03 | 9.25 | 0.26 | 0% |
| h1 ↔ h2 (short)   | 28.47 | 30.07 | 31.17 | 0.83 | 0% |
| h2 ↔ h3 (medium)  | 58.61 | 60.09 | 61.17 | 0.80 | 0% |
| h1 ↔ h3 (long)    | 79.55 | 81.47 | 83.58 | 1.16 | 0% |

> RTT values closely match expected values (±3 ms), confirming correct link delay emulation via tc-netem.
> Long path RTT (81 ms) is ~2.7× the short path RTT (30 ms), demonstrating measurable delay differences.

### Scenario 2 – Blocking Mode (Actual Results)

| Pair | Result |
|------|--------|
| h1 → h3 (blocked) | loss=100%  PASS |
| h3 → h1 (blocked) | loss=100%  PASS |
| h1 → h2 (allowed) | avg=49.46 ms, loss=0%  |
| h2 → h4 (allowed) | avg=61.02 ms, loss=0%  |
| h3 → h4 (allowed) | avg=9.48 ms, loss=0%  |

### iperf Throughput (Actual Results)

| Path | Throughput |
|------|------------|
| h1 → h2 | 92.5 Mbits/sec |
| h3 → h2 | 87.2 Mbits/sec |
---

## Repository Structure

```
network-delay-tool/
├── topology.py         # Mininet topology with TCLink delays
├── delay_monitor.py    # POX controller (copy to pox/ext/)
├── measure_delay.py    # Automated ping + iperf measurement script
├── run_experiment.sh   # One-shot launcher (starts POX + runs tests)
└── README.md
```

---

## Prerequisites

| Requirement | Version tested | Install command |
|---|---|---|
| Ubuntu | 22.04 / 24.04 / 25.x | — |
| Python | 3.8+ | built-in |
| Mininet | 2.3+ | `sudo apt install mininet` |
| Open vSwitch | 2.17+ | `sudo apt install openvswitch-switch` |
| POX controller | alchemy / dart | see below |
| iperf | 2.x | `sudo apt install iperf` |

### Install Mininet (if not already installed)
```bash
sudo apt update
sudo apt install mininet openvswitch-switch iperf -y
```

### Install POX (if not already installed)
```bash
cd ~
git clone https://github.com/noxrepo/pox.git
```

---

## Setup & Execution

### Step 1 – Clone this repository
```bash
git clone https://github.com/shristiglitter0820/network-delay-tool.git
cd network-delay-tool
```

### Step 2 – Copy the controller into POX
```bash
cp delay_monitor.py ~/pox/ext/delay_monitor.py
```

### Step 3A – Run Scenario 1 (Normal delay comparison)

**Terminal 1 – Start POX controller:**
```bash
cd ~/pox
python3 pox.py log.level --DEBUG delay_monitor
```

**Terminal 2 – Run Mininet + measurements:**
```bash
cd network-delay-tool
sudo python3 measure_delay.py
```

Or use the one-shot launcher (handles both terminals automatically):
```bash
chmod +x run_experiment.sh
sudo ./run_experiment.sh normal
```

### Step 3B – Run Scenario 2 (Blocking mode)

**Terminal 1 – Start POX with blocking enabled:**
```bash
cd ~/pox
python3 pox.py log.level --DEBUG delay_monitor --block=True
```

**Terminal 2 – Run blocking test:**
```bash
sudo python3 measure_delay.py --block
```

Or:
```bash
sudo ./run_experiment.sh block
```

### Step 4 – Interactive CLI (optional)

To explore the topology manually:
```bash
sudo python3 topology.py
```
This drops into the Mininet CLI where you can run custom tests:
```
mininet> h1 ping -c 5 h3
mininet> h1 iperf h2
mininet> sh ovs-ofctl dump-flows s1
mininet> sh ovs-ofctl dump-flows s2
```

---

## Expected Output

### Scenario 1 – Normal Forwarding
```
================================================================
  SCENARIO 1: Normal Forwarding – Delay Comparison
================================================================

  [h3 → h4]  SAME-SW  h3 <-> h4  (s3 internal)
  RTT  min/avg/max/mdev =  7.xx /  8.xx /  9.xx /  0.xx ms   |  loss=0%

  [h1 → h2]  SHORT    h1 -> s1 -[10ms]-> s2 -> h2
  RTT  min/avg/max/mdev = 27.xx / 28.xx / 30.xx /  0.xx ms   |  loss=0%

  [h2 → h3]  MEDIUM   h2 -> s2 -[25ms]-> s3 -> h3
  RTT  min/avg/max/mdev = 56.xx / 58.xx / 61.xx /  1.xx ms   |  loss=0%

  [h1 → h3]  LONG     h1 -> s1 -> s2 -> s3 -> h3
  RTT  min/avg/max/mdev = 76.xx / 78.xx / 82.xx /  1.xx ms   |  loss=0%

  Long path RTT is 2.8× the short path RTT (78 ms vs 28 ms)
```

### Scenario 2 – Blocking Mode
```
  ── Blocked pairs (expecting 100% loss) ──────────────────────
  h1 → h3 : loss=100%  → PASS (blocked)
  h3 → h1 : loss=100%  → PASS (blocked)

  ── Allowed pairs (expecting normal RTT) ─────────────────────
  h1 → h2 : avg RTT = 28.xx ms  loss=0%
  h2 → h4 : avg RTT = 58.xx ms  loss=0%
  h3 → h4 : avg RTT =  8.xx ms  loss=0%
```

### Flow table inspection (inside Mininet CLI)
```bash
mininet> sh ovs-ofctl dump-flows s1
NXST_FLOW reply: ...
 cookie=0x0, duration=3.4s, table=0, n_packets=10, n_bytes=980,
 idle_timeout=30, hard_timeout=120, priority=100,
 dl_dst=00:00:00:00:00:03 actions=output:2
```

---

## Controller Logic

The POX controller (`delay_monitor.py`) implements:

1. **packet_in handling** — Every unmatched packet triggers a `PacketIn` event
2. **MAC learning** — Source MAC → in-port mapping stored per switch
3. **Match-action flow rules** — Installed with `ofp_flow_mod`:
   - Match: destination MAC
   - Action: `output(learned_port)`
   - Timeouts: idle=30s, hard=120s, priority=100
4. **Drop rules (Scenario 2)** — Installed at priority 200 with no actions (implicit drop) for h1↔h3 IP pairs
5. **Periodic stats** — Every 30 s, per-switch stats are printed to the controller log

---

## SDN Flow Rule Design

```
Match field      : dl_dst (destination MAC)
Action           : OFPAT_OUTPUT → learned port
Idle timeout     : 30 seconds
Hard timeout     : 120 seconds
Priority (fwd)   : 100
Priority (drop)  : 200  ← wins over forwarding rules
```

---

## Performance Observation

| Metric | Tool | What to observe |
|--------|------|-----------------|
| Latency (RTT) | `ping` | min/avg/max/mdev |
| Jitter | `ping` (mdev) | delay variation |
| Throughput | `iperf` | Mbits/sec |
| Flow table | `ovs-ofctl dump-flows` | rule installation |
| Packet counts | `ovs-ofctl dump-flows` | n_packets per rule |

---

## References

1. Mininet documentation – https://mininet.org/api/
2. POX Wiki – https://noxrepo.github.io/pox-doc/html/
3. OpenFlow 1.0 spec – https://opennetworking.org/wp-content/uploads/2013/04/openflow-spec-v1.0.0.pdf
4. Open vSwitch – https://www.openvswitch.org/
5. Linux `tc-netem` (link emulation) – `man tc-netem`
6. Mininet TCLink – https://github.com/mininet/mininet/blob/master/mininet/link.py
