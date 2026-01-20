# AI Factory Simulation – Mechanism Deep Dive

This document explains how the **AI Factory** layer in this repo works end‑to‑end: hierarchy, scheduling/execution model, and where synchronization (barriers) exists.

> Scope: this describes the AI-factory workload runner (`ai_factory_simulation/*`) running on top of the packet network simulator (`network_simulation/*`) and the discrete-event simulator (`des/*`).

---

## 1) Hierarchy: what are the layers and what do they represent?

### Layer A — Discrete-event engine (`des`)
**Key class:** `des.des.DiscreteEventSimulator`

- Represents *time* and an *event queue*.
- Everything in the system ultimately happens because some component calls:
  - `sim.schedule_event(delay, callback)`
- The simulator processes events in time order in `sim.run()` until the queue is empty.

**Real-life analogue:** a timeline where we schedule future “actions” like “finish compute” or “inject a network flow”.

---

### Layer B — Packet network simulator (`network_simulation`)
This is the packet-level world. Important objects:

- **`Network`** (`network_simulation/network.py`)
  - Owns the `DiscreteEventSimulator` instance.
  - Owns all entities: hosts, switches, links.
  - Builds the topology and assigns a `Scenario`.

- **`NetworkNode`** (`network_simulation/network_node.py`)
  - Base class for `Host` and `Switch`.
  - Holds ports, routing tables, and routing policy (ECMP/adaptive).
  - Receives packets via `post(packet)` and processes them in scheduled callbacks to avoid recursion.

- **`Host`** (`network_simulation/host.py`)
  - Edge endpoint: can *send_message()* (which creates a sequence of packets) and can receive packets.

- **`Switch`** (`network_simulation/switch.py`)
  - Forwards packets based on `NetworkNode.select_port_for_packet()`.

- **`Port`** (`network_simulation/port.py`)
  - Egress queue per port.
  - Schedules drain attempts on the DES.

- **`Link`** (`network_simulation/link.py`)
  - Models bandwidth/serialization delay and propagation time.
  - Maintains `next_available_time` per direction (full-duplex availability).

**Real-life analogue:** routers/switches and NICs, with queues, bandwidth, and propagation delays.

---

### Layer C — AI Factory “application” simulation (`ai_factory_simulation`)
This layer is packet-agnostic and operates in terms of “compute time” and “communication flows”:

- **Job hierarchy** (`ai_factory_simulation/core/entities.py`)
  - `Job` → list of `JobStep` → list of `Phase`
  - `Phase` is either:
    - `ComputePhase(duration_s=…)`
    - `CommPhase(buckets=[Bucket(...), ...])`
  - `Bucket` contains an ordered list of `Flow` objects to inject.

- **Workload builder** (`ai_factory_simulation/workloads/workload1_dp_heavy.py`)
  - Constructs a `Job` object for “Workload1 DP-heavy”.
  - Adds compute phases and a “gradient_sync” comm phase consisting of buckets.
  - Communication is expressed as *collectives* (Reduce-Scatter + All-Gather) that get expanded into point-to-point `Flow`s.

- **Runner / state machine** (`ai_factory_simulation/core/runner.py`)
  - `JobRunner` is the event-driven control plane:
    - schedules compute timers
    - injects flows for comm phases
    - waits for flow completion events

- **Flow injection adapter** (`ai_factory_simulation/scenarios/network_flow_injector.py`)
  - `NetworkFlowInjector` bridges a `Flow` into the packet simulator by calling `Host.send_message()`.
  - Tracks completion of an injected flow and calls a completion callback back into the `JobRunner`.

**Real-life analogue:** a DL training job: each step has compute + gradient synchronization + optimizer. The synchronization is modeled as explicit communication flows.

---

### Layer D — Scenario wiring (glue)
- **`Scenario`** (`network_simulation/scenario.py`) ties together topology + application
- **`AIFactorySUDpHeavyScenario.install()`** (`ai_factory_simulation/scenarios/ai_factory_su_dp_heavy_scenario.py`)
  - Builds the job and starts the job runner.

**Real-life analogue:** “deploy this training workload on this cluster topology.”

---

## 2) How a job is built and executed (top → bottom timeline)

This section traces: YAML → Scenario → Job → scheduled events → packets.

### 2.1 YAML runner entrypoint
The YAML-driven entrypoint is `ai_factory_network_simulation.py`.

High-level sequence:
1. Parse YAML → routing/topology/scenario params.
2. Construct a `Network` implementation (e.g. `AIFactorySUNetworkSimulator`).
3. `network.create()` builds the topology (hosts/switches/links) and routing tables.
4. `network.assign_scenario(scenario)` calls `scenario.install(network)`.
5. `network.run()` calls `DiscreteEventSimulator.run()`.

At step (4), the AI-factory layer schedules *future* events (job start, flow injections, timers), but does not run them immediately.

---

### 2.2 Scenario builds the AI job
`AIFactorySUDpHeavyScenario.install(network)` does:

1. Determine participants: `participants = sorted(network.hosts.keys())`
2. Build a `Workload1Config` using the scenario parameters.
3. Build the `Job` object:
   - `job = build_workload1_dp_heavy_job(participants, config)`

At this point **nothing packet-level has happened yet**. This is purely assembling a data structure describing what should happen.

---

### 2.3 JobRunner schedules the job start
The scenario then constructs:
- `injector = NetworkFlowInjector(network)`
- `runner = JobRunner(sim=network.simulator, injector=injector, job=job)`
- `metrics = runner.run()`

**Important:** `JobRunner.run()` does NOT run the simulator. It schedules the initial event:

- `sim.schedule_event(0.0, self._start_job)`

So the first thing the DES will do (at time `t=0`) is call `_start_job()`.

---

### 2.4 JobRunner is a state machine driven by DES events
At runtime:

1. `_start_job()` logs metadata and calls `_run_step(step_index=0)`.

2. `_run_step()` creates `StepMetrics` and calls `_run_phase(step_index, phase_index=0)`.

3. `_run_phase()` chooses behavior based on phase type:

#### ComputePhase
For a compute phase, it schedules a timer:

- `schedule_timer(sim, delay_s=phase.duration_s, cb=done_phase)`
- which is implemented as `sim.schedule_event(delay_s, cb)`

So compute is modeled as “time passes, then the phase is done”. No network activity.

#### CommPhase
For a comm phase, it calls `_run_comm_phase(phase, done_phase)`.

`_run_comm_phase()`:
- creates a `BarrierBookkeeper()`
- iterates buckets sequentially (bucket 0 → 1 → 2 → …), where **each bucket is a barrier**.

For each bucket:
- Build a `Join` barrier whose pending set is all flow IDs in that bucket:
  - `join = Join(pending={f.flow_id for f in bucket.flows}, on_done=done_bucket)`
- Register it with the bookkeeper.

Then it schedules injection of each flow as an event:

- compute delay: `delay = max(0.0, f.start_time - now)`
- schedule injection: `sim.schedule_event(delay, _inject)`
- `_inject()` calls `injector.inject(flow, on_complete=book.on_flow_complete)`

**So what is submitted to the scheduler and when?**

- Job start event (`_start_job`) at t=0.
- For each compute phase: a “done_compute” event in the future.
- For each comm bucket: N “inject flow” events (one per flow), possibly with offsets.
- For each packet and each port drain: additional low-level events are created by the packet simulator.

---

### 2.5 Flow injection into the packet network
`NetworkFlowInjector.inject(flow, on_complete=…)` bridges from AI layer to network layer.

What it does:

1. Resolve flow endpoints:
   - `src = network.get_entity(flow.src_node_id)`
   - `dst = network.get_entity(flow.dst_node_id)`

2. Register completion callback and maintain flow accounting:
   - `_callbacks[flow_id] = on_complete`
   - `_stats[flow_id] = (dst_ip, expected_bytes, received_bytes=0)`

3. Call `src.send_message(...)`:
   - `session_id=flow_id`  ← important: becomes `PacketTransport.flow_id`
   - `dst_ip_address=dst.ip_address`
   - `size_bytes=flow.size_bytes`

So a **Flow** at the AI layer becomes a “bulk message” at the Host, which becomes **many packets**.

---

### 2.6 Host.send_message() turns a flow into packets
`Host.send_message()`:

- Computes `packet_count = ceil(size_bytes / MTU)`.
- For each packet `i`:
  - Creates `PacketL3(five_tuple=…, seq_number=i, size_bytes=…, ttl=…)`
  - Creates `PacketTransport(flow_id=session_id, flow_count=packet_count, flow_seq=i)`
  - Adds `PacketTrackingInfo` and pushes packet into the simulator’s global packet list.
  - Sends the packet to the first hop via `_internal_send_packet(packet)`.

This is the **bottom** where the AI-factory “flow” becomes concrete packets.

---

### 2.7 What happens after the host sends (packet forwarding)
Once a packet is enqueued:

- The `Port` schedules a drain event (`_drain_once`) at current time.
- The drain checks when the attached `Link` is available and either:
  - transmits immediately (and updates `Link.next_available_time`)
  - or schedules itself for later when the link becomes free.

When a packet arrives at the other endpoint, it is delivered to a `NetworkNode.post(packet)` which schedules a `handle_message` event at the same time slice, and the node forwards it (switch) or consumes it (host).

---

## 3) Synchronization points (barriers), completion tracking, and loss behavior

### 3.1 Where are the barriers?
Barriers exist **only at the AI-factory layer**, not in the network layer.

There are two main levels:

1. **Within a CommPhase, buckets are sequential.**
   - `JobRunner._run_comm_phase()` runs bucket 0, waits until its flows complete, then runs bucket 1, etc.
   - This models the “bucketized gradient sync” behavior used in distributed training.

2. **Within a bucket, all flows are joined.**
   - The `Join(pending={flow_ids...})` object is a barrier that completes only when all flows in the bucket complete.

So:
- **Bucket completion** is a barrier.
- **Phase completion** happens after all buckets finish.
- The step completes after all phases finish.

---

### 3.2 How is flow completion detected?
Flow completion is detected by `NetworkFlowInjector` by wrapping each host’s `on_message` method.

Mechanism:
- When `inject(flow)` is called, the injector stores:
  - expected bytes for the flow
  - the destination IP
  - the callback to invoke when complete

- For every packet delivered to any host, the wrapper checks:
  - the packet’s `transport_header.flow_id`
  - whether it is the final destination (`dst_ip` matches)
  - then increments received byte count by `packet.routing_header.size_bytes`

When `received_bytes >= expected_bytes`:
- the injector calls the registered callback: `cb(flow_id)`

That callback is `BarrierBookkeeper.on_flow_complete()`, which updates any pending joins.

---

### 3.3 Is there application-level tracking for “all packets arrived”?
The completion rule is **byte-count based**, not “all packet sequence numbers arrived”.

Practical implications:
- The injector does **not** check `flow_seq` or require receiving exactly `flow_count` packets.
- It also does not detect duplicates or out-of-order delivery.

In this simulator’s current model:
- packets are expected to deliver without loss under normal conditions
- completion by bytes is sufficient for the intended workloads.

If you later introduce loss/retransmit, you’ll likely want to upgrade this to:
- track a bitmap/set of received `flow_seq`
- or track `flow_count` and count unique packets

---

### 3.4 What happens if a packet gets lost/dropped?
At the packet level:
- a packet can be marked dropped (`packet.routing_header.dropped = True`), for example:
  - TTL expiry (switch drops expired)
  - missing route (node drops)
  - failed link handling

At the AI-factory level:
- **there is no retransmission**.
- `NetworkFlowInjector` completion depends on receiving enough bytes.

So if packets are dropped:
- the destination will never accumulate `expected_bytes`
- the flow’s completion callback will never fire
- the corresponding `Join` barrier will never empty
- the simulation will likely “stall” logically (the DES may still drain other events, but the job will not progress past that barrier).

This models a system without transport recovery. The comment in `NetworkFlowInjector` makes it explicit: it expects the flow to be “fully delivered” before calling the callback.

---

## 4) Mental model cheat sheet

- **JobRunner = control-plane FSM** driven by DES events.
- **ComputePhase = timer** (no packets).
- **CommPhase = inject flows + barrier**.
- **FlowInjector = adapter**: Flow → Host.send_message.
- **Host.send_message = packetization** (set `transport_header.flow_id`).
- **Flow completion = bytes received at final dst host**.

---

## 5) Suggested extension points (if you evolve the simulator)

1. **Loss-aware completion**
   - Track `flow_seq` and `flow_count` from `PacketTransport`.

2. **Transport model**
   - Add retransmission/timeouts if simulating TCP-like behavior.

3. **More realistic collective scheduling**
   - Model overlapping buckets or compute/comm overlap by allowing simultaneous bucket joins.

4. **Topology-aware placement**
   - The job currently uses `participants = sorted(network.hosts.keys())` and the collective expander uses participants order.


