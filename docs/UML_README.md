# UML Diagrams for Network Simulation Project

This folder contains UML diagrams in **PlantUML** format (.puml files), which is a free and open-source tool.

## Viewing the Diagrams

### Option 1: Online Renderer (Recommended - No installation)
1. Go to [PlantUML Online Server](https://www.plantuml.com/plantuml/uml/)
2. Paste the contents of any `.puml` file
3. View or download the rendered diagram

### Option 2: VS Code Extension (Free)
1. Install the "PlantUML" extension by jebbs
2. Open any `.puml` file
3. Press `Alt+D` to preview

### Option 3: PlantUML CLI (Free, requires Java)
```bash
# Download plantuml.jar from https://plantuml.com/download
java -jar plantuml.jar filename.puml
```

### Option 4: Other Free Tools
- **draw.io** / **diagrams.net**: Can import PlantUML
- **Kroki**: Online rendering service
- **IntelliJ IDEA**: Has PlantUML plugin

---

## Diagram Descriptions

### 1. Network Simulation Layer

#### `uml_network_level.puml` - Class Diagram
Shows the class structure of the network simulation layer:
- **DES (Discrete Event Simulator)**: Core simulation engine with priority queue
- **Network Core**: Network, NetworkNode, Host, Switch
- **Network Infrastructure**: Link, Port
- **Packet Model**: Packet structure with headers and tracking info
- **Scenario**: Abstract base for traffic definitions

#### `uml_network_packet_flow.puml` - Sequence Diagram
Shows how a packet travels through the network:
1. Host creates and packetizes message
2. Port queues and drains packets to Link
3. Link schedules delivery based on bandwidth/delay
4. Switch forwards based on routing table
5. Destination Host receives and marks delivered

#### `uml_des_state_machine.puml` - State Diagram
Shows the DES event processing loop:
- Dequeue → Update Time → Execute Action → Repeat
- Actions can schedule new events during execution

---

### 2. AI Factory Application Layer

#### `uml_ai_factory_level.puml` - Class Diagram
Shows the AI Factory simulation classes:
- **Core Entities**: Job, JobStep, Phase (Compute/Comm), Bucket
- **Traffic Layer**: Flow, Collective patterns
- **Runtime**: JobRunner, FlowInjector, NetworkFlowInjector
- **Scheduling**: BarrierBookkeeper, Join (barriers)
- **Metrics**: JobMetrics, StepMetrics, PhaseMetrics
- **Scenarios**: MixedScenario with job configurations

#### `uml_ai_factory_job_flow.puml` - Sequence Diagram
Shows job execution flow:
1. Scenario installs and builds jobs
2. JobRunner advances through steps and phases
3. Compute phases → DES timers
4. Comm phases → Flow injection with barrier synchronization
5. NetworkFlowInjector bridges to network layer

---

### 3. Overall Architecture

#### `uml_architecture_overview.puml` - Component Diagram
High-level view showing how all layers interact:
- **AI Factory Layer**: Scenarios, JobRunner, Workloads, Traffic patterns
- **DES Layer**: Event simulation, barriers
- **Network Layer**: Topology, routing, packet handling

---

## Key Concepts

### Two-Layer Architecture
```
┌─────────────────────────────────────────────┐
│     AI Factory Application Layer            │
│  (Jobs, Steps, Phases, Flows, Collectives)  │
├─────────────────────────────────────────────┤
│          NetworkFlowInjector                │
│       (Adapter: Flow → Packets)             │
├─────────────────────────────────────────────┤
│       Network Simulation Layer              │
│   (Hosts, Switches, Links, Packets)         │
├─────────────────────────────────────────────┤
│     Discrete Event Simulator (DES)          │
│      (Event queue, time management)         │
└─────────────────────────────────────────────┘
```

### Event Flow
1. **AI Factory** creates Jobs with Steps containing ComputePhase/CommPhase
2. **JobRunner** advances state machine, scheduling DES events
3. **CommPhase** injects Flows via NetworkFlowInjector
4. **Network Layer** handles packetization, routing, transmission
5. **Barriers** synchronize on flow completion before next phase
