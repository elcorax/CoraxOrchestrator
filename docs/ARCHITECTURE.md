# Corax Orchestrator Architecture

## Overview

Corax Orchestrator is designed as a modular, event-driven deployment system with a clean separation of concerns. The architecture prioritizes:

- **Extensibility** - New tools, platforms, and installers can be added without modifying core code
- **Resilience** - Self-healing engine provides automatic recovery from failures
- **Observability** - Structured logging, progress callbacks, and comprehensive reporting
- **Cross-Platform** - Abstract platform layer enables Windows, macOS, and Linux support

## Core Design Principles

### 1. Modular Architecture

Each module has a single responsibility and communicates through well-defined interfaces:

```
┌─────────────────────────────────────────────────────────────┐
│                    TaskOrchestrator                          │
│  (Workflow Orchestration & Coordination)                     │
├──────────┬──────────┬──────────┬──────────┬─────────────────┤
│ Scanner  │ Analyzer │ Installer│ Model    │ Permission      │
│          │          │ Engine   │ Manager  │ Manager         │
├──────────┴──────────┼──────────┼──────────┼─────────────────┤
│ Self-Healing Engine │ State    │ Reporting│ Tool Registry   │
│                     │ Persist. │ Engine   │                 │
├─────────────────────┴──────────┴──────────┴─────────────────┤
│                    Platform Abstraction Layer                 │
│         (Windows / macOS / Linux Implementations)            │
└─────────────────────────────────────────────────────────────┘
```

### 2. Dependency Injection

Modules receive their dependencies through constructor injection, making them testable and swappable:

```python
class TaskOrchestrator:
    def __init__(
        self,
        scanner: Optional[SystemScanner] = None,
        analyzer: Optional[EnvironmentAnalyzer] = None,
        installer: Optional[InstallerEngine] = None,
        # ...
    ):
        self.scanner = scanner or SystemScanner()
        # ...
```

### 3. Async-First Design

All I/O operations are asynchronous using Python's `asyncio`, enabling concurrent operations and non-blocking execution:

```python
async def run_deployment(self, tools, models) -> DeploymentTask:
    await self._phase_scan(task)
    await self._phase_analyze(task)
    await self._phase_install(task)
    # ...
```

### 4. Error Hierarchy

A custom exception hierarchy enables precise error handling and recovery:

```
CoraxError (base)
├── ConfigurationError
├── DetectionError
├── InstallationError
├── PermissionError
├── ModelError
├── PersistenceError
├── PlatformError
└── RecoveryError
```

Each exception includes:

- `message` - Human-readable description
- `code` - Machine-readable error code
- `recoverable` - Whether the error can be automatically recovered
- `details` - Additional context for debugging

## Module Details

### System Scanner (`system_scanner.py`)

**Responsibility:** Detect hardware specifications and software inventory.

**Key Classes:**

- `SystemScanner` - Main scanner with async `scan()` method
- `ScanResult` - Data class containing all scan data
- `HardwareSpecs` - CPU, GPU, memory, disk, network info
- `SoftwareInventory` - OS, installed apps, dev tools, runtimes

**Detection Methods:**

- Platform API (WMI on Windows, sysctl on macOS, /proc on Linux)
- psutil for cross-platform resource detection
- Subprocess checks for development tools
- Registry scanning (Windows) for installed software

### Environment Analyzer (`environment_analyzer.py`)

**Responsibility:** Evaluate system readiness for AI development.

**Key Classes:**

- `EnvironmentAnalyzer` - Analyzes scan results against requirements
- `EnvironmentAnalysis` - Readiness score, issues, recommendations
- `ToolStatus` - Per-tool installation and compatibility status

**Scoring:**

- 100 base score
- -15 per hardware issue
- -10 per missing required tool
- -5 per outdated tool
- -3 per warning

### Tool Registry (`tool_registry.py`)

**Responsibility:** Maintain metadata about all supported tools.

**Key Classes:**

- `ToolRegistry` - Registry with lookup, search, and dependency resolution
- `ToolMetadata` - Tool name, description, category, dependencies
- `ToolDependency` - Dependency relationship between tools
- `ToolCategory` - Enum of tool categories

**Features:**

- Built-in definitions for 12+ tools
- Topological sort for installation ordering
- Transitive dependency resolution
- Platform compatibility checking
- Full-text search across name, description, and tags

### Installer Engine (`installer_engine.py`)

**Responsibility:** Orchestrate tool installations.

**Key Classes:**

- `InstallerEngine` - Creates plans and executes installations
- `InstallationPlan` - Dependency-ordered install sequence
- `InstallerResult` - Per-tool installation outcome

**Features:**

- Dependency resolution and ordering
- Already-installed detection
- Batch installation with failure propagation
- Estimated size and privilege requirements

### Model Manager (`model_manager.py`)

**Responsibility:** Manage local AI models.

**Key Classes:**

- `ModelManager` - Download, list, and remove models
- `ModelInfo` - Model metadata and download status
- `ModelProvider` - Supported providers (Ollama, LM Studio, HuggingFace)

**Features:**

- Ollama model listing and pulling
- Local model storage management
- Size parsing and storage usage tracking

### Permission Manager (`permission_manager.py`)

**Responsibility:** Manage privilege escalation and user consent.

**Key Classes:**

- `PermissionManager` - Check, request, and track permissions
- `PermissionRequest` - Request details and grant status
- `PermissionLevel` - None, User, Admin, System

**Features:**

- Configurable auto-accept mode
- Consent callback for GUI integration
- Permission history tracking
- Admin elevation requests

### Self-Healing Engine (`self_healing.py`)

**Responsibility:** Automatic error recovery.

**Key Classes:**

- `SelfHealingEngine` - Recovery orchestration
- `RecoveryResult` - Recovery attempt outcomes
- `RecoveryAttempt` - Individual attempt details
- `HealthStatus` - Component health monitoring
- `RecoveryStrategy` - Retry, restart, reinstall, etc.

**Strategies:**

- `RETRY` - Simple retry with delay
- `RESTART_SERVICE` - Restart a service
- `REINSTALL` - Reinstall the tool
- `CLEAN_CACHE` - Clear cached data
- `ESCALATE_PRIVILEGES` - Request admin rights
- `SKIP` - Skip the operation

### State Persistence (`state_persistence.py`)

**Responsibility:** Persist task state across restarts.

**Key Classes:**

- `StatePersistence` - High-level persistence manager
- `StateStore` - File-based key-value store
- `PersistedState` - Versioned state entry

**Features:**

- JSON and MessagePack formats
- Atomic writes via temp file + rename
- In-memory caching with disk fallback
- Multiple stores (tasks, config, progress, reports)
- Auto-save capability

### Reporting Engine (`reporting.py`)

**Responsibility:** Generate deployment reports.

**Key Classes:**

- `ReportingEngine` - Report creation and export
- `DeploymentReport` - Complete report data

**Output Formats:**

- JSON - Machine-readable
- Markdown - Readable in any text editor
- HTML - Styled report viewable in browser

### Task Orchestrator (`task_orchestrator.py`)

**Responsibility:** Coordinate the complete deployment workflow.

**Key Classes:**

- `TaskOrchestrator` - Main workflow coordinator
- `DeploymentTask` - Complete task state
- `TaskProgress` - Progress tracking
- `TaskStatus` - Status enum

**Workflow Phases:**

1. Scan (10-25%)
2. Analyze (30-45%)
3. Permissions (50-55%)
4. Install (60-80%)
5. Models (85-90%)
6. Report (95-100%)

## Cross-Platform Layer

### Platform Abstraction (`platform/`)

The platform layer provides a unified interface for OS-specific operations:

```
PlatformBase (ABC)
├── WindowsPlatform
├── MacOSPlatform
└── LinuxPlatform
```

**Abstract Methods:**

- `detect()` - Platform detection
- `run_command()` - Async command execution
- Path methods (install dir, downloads, temp, appdata, config)
- `is_admin()` - Privilege check
- `is_process_running()` - Process detection
- Environment variable management
- Shell detection
- Package manager detection
- Hardware info (CPU, memory, disk, GPU, network)
- Software inventory
- UI actions (open explorer, terminal, URL)

### Platform Factory (`factory.py`)

The `PlatformFactory` creates the appropriate platform implementation:

```python
platform = PlatformFactory.create()
info = platform.detect()
exit_code, stdout, stderr = await platform.run_command("python", ["--version"])
```

## Data Flow

### Deployment Request Flow

```
User Request
    │
    ▼
CoraxOrchestrator.deploy()
    │
    ▼
TaskOrchestrator.run_deployment()
    │
    ├── Phase 1: SystemScanner.scan()
    │       │
    │       ├── PlatformFactory.create()
    │       ├── platform.get_cpu_info()
    │       ├── platform.get_memory_info()
    │       ├── platform.get_gpu_info()
    │       ├── platform.get_disk_info()
    │       ├── platform.get_installed_software()
    │       └── subprocess checks for dev tools
    │
    ├── Phase 2: EnvironmentAnalyzer.analyze()
    │       │
    │       ├── Hardware requirements check
    │       ├── Tool version compatibility
    │       └── Readiness score calculation
    │
    ├── Phase 3: PermissionManager.request_permission()
    │
    ├── Phase 4: InstallerEngine.install_multiple()
    │       │
    │       ├── ToolRegistry.get_install_order()
    │       ├── For each tool:
    │       │   ├── is_installed() check
    │       │   └── _execute_installation()
    │       └── SelfHealingEngine.attempt_recovery() on failure
    │
    ├── Phase 5: ModelManager.pull_ollama_model()
    │
    └── Phase 6: ReportingEngine.create_report()
            │
            ├── save_report("json")
            ├── save_report("markdown")
            └── save_report("html")
```

## Configuration Management

Configuration is loaded from YAML files with a layered approach:

1. `config/default.yaml` - Built-in defaults
2. `config/local.yaml` - User overrides (gitignored)
3. Environment variables (prefixed with `CORAX_`)
4. Command-line arguments

## Agent Runtime Layer

### Overview

The Agent Runtime Layer provides autonomous execution capabilities for the Corax Orchestrator. It manages the complete lifecycle of autonomous deployment tasks including reasoning, planning, execution, recovery, and AI model integration.

```
RuntimeEngine (Central Orchestrator)
├── LifecycleManager (State Machine)
│   ├── 10 lifecycle states (created → terminated)
│   ├── Validated state transitions
│   ├── Event/state hooks for extensibility
│   └── Forced transitions for emergency recovery
│
├── ExecutionLoop (Goal-Driven Execution)
│   ├── Continuous goal processing
│   ├── Pause/Resume/Cancel support
│   ├── Action approval via mode system
│   ├── Automatic error recovery
│   └── Comprehensive metrics tracking
│
├── TaskScheduler (Priority-Based Scheduling)
│   ├── Heap-based priority queue
│   ├── Dependency resolution between tasks
│   ├── Concurrent execution with limits
│   ├── Timeout enforcement
│   └── Automatic retry on failure
│
├── RuntimeRecovery (Crash Recovery)
│   ├── Automatic recovery point creation
│   ├── Crash detection on startup
│   ├── State restoration from last point
│   ├── Recovery point pruning
│   └── Manual checkpoint creation
│
├── AgentModes (Safe / Assisted / Autonomous)
│   ├── SafeMode: All actions require explicit approval
│   ├── AssistedMode: Safe actions auto-approved
│   └── AutonomousMode: Full autonomy within boundaries
│
├── ExecutionEngine (Workflow Execution)
│   ├── Step-by-step execution with dependency resolution
│   ├── Pause/Resume/Cancel workflow control
│   ├── Timeout and retry handling
│   ├── Progress tracking with callbacks
│   ├── Capability-based execution (terminal, process, installer, desktop, browser)
│   ├── Sandbox security enforcement
│   └── Execution recovery with checkpoints
│
├── Execution Capabilities (Execution Primitives)
│   ├── TerminalCapability (command execution, shell interaction)
│   ├── ProcessCapability (process lifecycle management)
│   ├── InstallerInteractionCapability (installer UI automation)
│   ├── DesktopCapability (window detection, desktop monitoring)
│   ├── BrowserCapability (browser launch, tab management, CDP)
│   ├── SandboxCapability (command allowlisting, path protection)
│   └── ExecutionRecoveryCapability (checkpoints, recovery strategies)
│
├── ReasoningEngine (Planning & Decisions)
│   ├── Problem analysis and decomposition
│   ├── Action planning and sequencing
│   ├── Risk assessment
│   └── Weighted multi-criteria decision making
│
├── AIProviders (Model Integration)
│   ├── LMStudioProvider (local OpenAI-compatible API)
│   ├── OllamaProvider (local model management)
│   ├── ProviderRegistry (discovery & fallback)
│   └── ProviderConfig (unified configuration)
│
├── Conversation Management
│   ├── ConversationHistory (persistent message storage)
│   ├── ContextManager (token-aware context windows)
│   ├── Message types (system/user/assistant/tool)
│   └── API formatting for model calls
│
├── SessionManager (Session Lifecycle)
│   ├── Session creation and configuration
│   ├── Session persistence to disk
│   ├── Session resumption after restart
│   └── Session listing and search
│
├── AgentState (Persistence & Checkpoints)
│   ├── Session Management (create/resume/archive)
│   ├── Checkpoint System (save/restore)
│   ├── Execution History
│   └── Metrics Collection
│
└── ToolExecutor (Tool Invocation)
    ├── Tool registration and discovery
    ├── Unified execution interface
    └── Execution timeout support
```

### Runtime Engine Architecture

The `RuntimeEngine` is the central orchestrator that integrates all runtime subsystems:

```
RuntimeEngine
├── LifecycleManager    → State machine for runtime lifecycle
├── TaskScheduler       → Priority-based task execution
├── RuntimeRecovery     → Crash recovery and restart
├── ExecutionLoop       → Goal-driven autonomous execution
├── Mode Management     → Safe/Assisted/Autonomous modes
├── Session Management  → Session lifecycle
└── Callback System     → Approval requests & notifications
```

**Lifecycle States:**

```
CREATED → INITIALIZING → IDLE → RUNNING → PAUSED → ERROR → RECOVERING → SHUTTING_DOWN → TERMINATED
```

**Key Features:**

- Formal state machine with validated transitions
- Goal-driven execution loop with pause/resume/cancel
- Priority-based task scheduling with dependency resolution
- Automatic crash recovery with recovery points
- Three agent modes with configurable autonomy levels
- AI provider abstraction (LM Studio, Ollama, OpenAI-compatible)
- Conversation history with context window management
- Session persistence and resumption

### Lifecycle Manager

The `LifecycleManager` implements a formal state machine with validated transitions:

```python
# State transition: (current_state, event) → new_state
STATE_TRANSITIONS = {
    (LifecycleState.CREATED, LifecycleEvent.INIT): LifecycleState.INITIALIZING,
    (LifecycleState.INITIALIZING, LifecycleEvent.START): LifecycleState.RUNNING,
    (LifecycleState.RUNNING, LifecycleEvent.COMPLETE): LifecycleState.IDLE,
    (LifecycleState.RUNNING, LifecycleEvent.FAIL): LifecycleState.ERROR,
    (LifecycleState.ERROR, LifecycleEvent.RECOVER): LifecycleState.RECOVERING,
    # ... 30+ validated transitions
}
```

**Features:**

- 10 lifecycle states covering all runtime phases
- 30+ validated state transitions
- Event and state hooks for extensibility
- Forced transitions for emergency recovery
- Transition history for auditing

### Execution Loop

The `ExecutionLoop` provides continuous goal-driven execution:

```python
loop = ExecutionLoop(lifecycle, scheduler)
loop.add_goal("Scan system and install tools")
await loop.start()
await loop.pause()   # Pause execution
await loop.resume()  # Resume execution
await loop.cancel()  # Cancel current workflow
```

**Features:**

- Continuous goal processing from a queue
- Automatic workflow creation from goals
- Step-by-step execution with mode approval
- Risk-based action classification
- Automatic error recovery
- Comprehensive metrics tracking

### Task Scheduler

The `TaskScheduler` manages priority-based task execution:

```python
scheduler = TaskScheduler(max_concurrent=5)
scheduler.register_executor("install", install_executor)
task = await scheduler.schedule(
    name="Install Ollama",
    executor_type="install",
    priority=TaskPriority.HIGH,
    timeout_seconds=300,
    max_retries=3,
)
```

**Features:**

- Heap-based priority queue for ordering
- Dependency resolution between tasks
- Configurable concurrent execution limits
- Task timeout enforcement
- Automatic retry on failure
- Task cancellation support

### Runtime Recovery

The `RuntimeRecovery` system provides crash recovery:

```python
recovery = RuntimeRecovery(auto_save_interval=30)
await recovery.start_auto_save()
await recovery.save_recovery_point(
    lifecycle_state="running",
    mode="autonomous",
    workflow_id="wf_001",
)
point = await recovery.load_latest_recovery_point()
```

**Features:**

- Automatic recovery point creation at configurable intervals
- Crash detection on startup
- State restoration from last recovery point
- Recovery point pruning (keep last N)
- Manual checkpoint creation

### AI Providers

The provider abstraction layer enables integration with multiple AI model backends:

```python
# LM Studio (local OpenAI-compatible API)
provider = LMStudioProvider(ProviderConfig(api_base_url="http://localhost:1234"))
models = await provider.list_models()
result = await provider.complete("Hello!", model="llama-3.2-3b")

# Ollama (local model management)
provider = OllamaProvider(ProviderConfig(api_base_url="http://localhost:11434"))
await provider.pull_model("llama3.2")
result = await provider.complete("Hello!", model="llama3.2")

# Provider Registry with fallback
registry = ProviderRegistry()
registry.register_provider_class("lm_studio", LMStudioProvider)
registry.register_provider_class("ollama", OllamaProvider)
discovered = await registry.discover_providers()
result = await registry.complete_with_fallback("Hello!")
```

### Conversation Management

The conversation system manages message history and context windows:

```python
history = ConversationHistory()
await history.add_message(session_id, UserMessage(content="Hello"))
messages = await history.get_api_messages(session_id)

context = ContextManager(default_max_tokens=4096)
truncated = context.truncate_context(session_id, messages)
```

**Message Types:**

- `SystemMessage` - System-level instructions
- `UserMessage` - User input
- `AssistantMessage` - Model responses with usage tracking
- `ToolMessage` - Tool execution results

### Session Management

The `SessionManager` handles session lifecycle:

```python
manager = SessionManager()
session = await manager.create_session(
    mode=AgentModeType.ASSISTED,
    configuration={"auto_approve_safe": True},
)
await manager.end_session(session.session_id)
resumed = await manager.resume_session(session.session_id)
```

### Agent Modes

The agent supports three operation modes that control the level of autonomy:

| Mode           | Description                                   | Auto-Approves                          |
| -------------- | --------------------------------------------- | -------------------------------------- |
| **Safe**       | All actions require explicit user approval    | Nothing                                |
| **Assisted**   | Safe actions auto-approved, risky actions ask | Read-only actions, low-risk operations |
| **Autonomous** | Full autonomy within configured boundaries    | All actions within risk threshold      |

**Action Risk Classification:**

- `SAFE` - Read-only operations (scan, check, list)
- `LOW` - Non-system operations (query, search)
- `MEDIUM` - Network operations (download, configure)
- `HIGH` - System modifications (install, modify)
- `CRITICAL` - Destructive operations (format, delete)

**Autonomous Mode Safety Features:**

- Configurable maximum risk threshold
- Blocked action types (never allowed)
- Allowed action types whitelist
- Concurrent action limits
- Resource usage limits (download size, install time)
- Protected system paths

### Execution Lifecycle

```
Workflow Execution Lifecycle:
┌─────────┐
│ PENDING │──► Execute step
└─────────┘
    │
    ▼
┌─────────┐     ┌──────────┐     ┌───────────┐
│ RUNNING │────►│ COMPLETED│  or  │  FAILED   │
└─────────┘     └──────────┘     └───────────┘
    │                                  │
    ▼                                  ▼
┌─────────┐     ┌──────────┐     ┌───────────┐
│ PAUSED  │────►│ CANCELLED│     │ RETRY (up │
└─────────┘     └──────────┘     │ to N)     │
                                  └───────────┘
```

**Workflow Steps:**

- `ACTION` - Execute a tool or action
- `DECISION` - Make a decision
- `SUBWORKFLOW` - Execute a nested workflow
- `WAIT` - Wait for a condition
- `CONDITIONAL` - Conditional branching
- `PARALLEL` - Parallel execution

### State Management

Agent state is persisted across restarts using JSON files with atomic writes:

```
data/persistence/agent/
├── session_abc123.json    # Active session
├── session_def456.json    # Archived session
└── ...
```

**Session Data:**

- Session ID, mode, status
- Checkpoint history (for pause/resume)
- Execution history (last 100 entries)
- Error history (last 50 entries)
- Metrics and configuration

### Reasoning Engine

The reasoning engine provides rule-based decision-making with extension points for future LLM integration:

**Capabilities:**

- Problem analysis and decomposition
- Template-based planning (full_deploy, quick_scan, install_tool)
- Custom plan generation for arbitrary goals
- Weighted multi-criteria decision making
- Risk assessment with factor analysis

**Decision Criteria Weights (default):**

- Safety: 40%
- Speed: 20%
- Reliability: 20%
- Resource Usage: 10%
- User Preference: 10%

### Tool Executor

The ToolExecutor provides a unified interface for executing tools and actions:

```python
# Register a tool
runtime.register_tool(
    name="scan_system",
    executor=my_scanner.scan,
    metadata={"description": "Scan system hardware"}
)

# Execute a tool
result = await runtime.execute_tool(
    tool_name="scan_system",
    parameters={"detailed": True},
    timeout=30
)
```

### Integration with Existing Modules

The Agent Runtime integrates with the existing Corax modules:

1. **SystemScanner** → Registered as `scan_system` tool
2. **EnvironmentAnalyzer** → Registered as `analyze_environment` tool
3. **InstallerEngine** → Registered as `install_tool` tool
4. **ModelManager** → Registered as `pull_model` tool
5. **ReportingEngine** → Registered as `generate_report` tool
6. **SelfHealingEngine** → Used by execution engine for recovery
7. **StatePersistence** → Used by AgentState for session persistence

### Usage Example

```python
from src.agent import AgentRuntime
from src.agent.modes.base import AgentModeType

# Create runtime
runtime = AgentRuntime()

# Set approval callback
async def approve_action(proposal):
    print(f"Approve: {proposal.description}?")
    return True  # or False

runtime.on_approval_request(approve_action)

# Start session
await runtime.start_session(
    session_id="deploy_001",
    mode=AgentModeType.ASSISTED,
)

# Execute a goal
workflow = await runtime.execute_goal(
    goal="Full deploy AI development workstation",
    context={"system_scanned": False},
)

# Check results
print(f"Status: {workflow.status}")
print(f"Progress: {workflow.progress_percentage()}%")
```

## Deployment Layer

### Overview

The Deployment Layer provides production-ready deployment capabilities for transforming a clean computer into a complete AI development workstation. It builds on the core modules and agent runtime to provide a comprehensive deployment orchestration system.

```
DeploymentOrchestrator (Main Coordinator)
├── DeploymentConfigManager (Configuration)
│   ├── Load/Save YAML/JSON configs
│   ├── DeploymentMode (DRY_RUN, SAFE, AUTOMATED, RECOVERY)
│   └── DeploymentSettings (timeout, retry, parallel, etc.)
│
├── ProfileManager (Deployment Profiles)
│   ├── Built-in profiles (Minimal AI, Coding, Full AI Lab, etc.)
│   ├── Custom profile creation and persistence
│   ├── Natural language intent matching
│   └── Profile resolution (type → config)
│
├── AIInstallerBase (Installer Abstraction)
│   ├── OllamaInstaller (local model server)
│   ├── LMStudioInstaller (local OpenAI-compatible API)
│   ├── OpenWebUIInstaller (web interface for Ollama)
│   ├── AnythingLLMInstaller (document RAG system)
│   ├── ComfyUIInstaller (image/video generation)
│   └── OpenInterpreterInstaller (code execution agent)
│
├── Dev Installers (Development Tools)
│   ├── GitInstaller
│   ├── PythonInstaller
│   ├── NodeInstaller
│   ├── VSCodeInstaller
│   ├── WindsurfInstaller
│   ├── JavaInstaller
│   ├── FlutterInstaller
│   └── DockerInstaller
│
├── ModelRegistry & ModelRecommender (Model Management)
│   ├── Model metadata and categorization
│   ├── Hardware-aware model recommendations
│   ├── RAM/VRAM-based filtering
│   └── Task-specific model suggestions
│
├── HealthChecker (Verification)
│   ├── Tool health checks (API endpoints, service status)
│   ├── System resource checks (RAM, disk, CPU)
│   ├── Network connectivity checks
│   ├── Python environment checks
│   └── Docker availability checks
│
├── IntegrationManager (Tool Integration)
│   ├── Ollama → Open WebUI integration
│   ├── Ollama → Open Interpreter integration
│   ├── Ollama → AnythingLLM integration
│   ├── LM Studio → Open WebUI integration
│   └── LM Studio → Open Interpreter integration
│
├── RepairEngine (Self-Healing)
│   ├── Tool repair (reinstall, restart, reconfigure)
│   ├── Priority-based repair actions
│   ├── Retry with exponential backoff
│   └── Default repair actions (restart, reinstall, fix permissions)
│
├── Execution Layer (Real Execution Engine)
│   ├── TerminalSession (CLI-first command execution)
│   │   ├── Async subprocess execution with streaming
│   │   ├── Timeout enforcement
│   │   ├── Tool version detection
│   │   ├── Concurrent tool checking
│   │   └── Execution history tracking
│   │
│   ├── RetryQueue (Deferred Retry Execution)
│   │   ├── Priority-based retry ordering
│   │   ├── Exponential backoff between retries
│   │   ├── Per-tool max retry limits
│   │   ├── Failure category-based retry strategies
│   │   └── Skip support for non-recoverable failures
│   │
│   ├── FailureAnalyzer (Failure Classification)
│   │   ├── Pattern-based failure classification
│   │   ├── 8 failure categories (permission, network, disk, etc.)
│   │   ├── Exit code analysis
│   │   ├── Confidence scoring
│   │   └── Repair suggestion generation
│   │
│   ├── DeploymentExecutor (Real Execution Engine)
│   │   ├── Sequential and parallel execution
│   │   ├── Dependency-aware execution ordering
│   │   ├── Failure tolerance (continues on failure)
│   │   ├── Automatic retry queue processing
│   │   ├── Repair execution integration
│   │   ├── Final validation pass
│   │   └── Comprehensive execution summary
│   │
│   └── DeploymentSession (Session Management)
│       ├── Session lifecycle (start/stop/resume)
│       ├── State persistence across restarts
│       ├── Deployment report generation
│       ├── Session resumption for failed tools
│       └── Latest session discovery
│
└── Core Module Integration
    ├── SystemScanner → Hardware/software detection
    ├── EnvironmentAnalyzer → Readiness assessment
    ├── InstallerEngine → Installation orchestration
    ├── ModelManager → Model download management
    ├── PermissionManager → Privilege escalation
    ├── SelfHealingEngine → Error recovery
    ├── StatePersistence → State persistence
    └── ReportingEngine → Report generation
```

### Deployment Lifecycle (11 Phases)

```
Phase 1:  Configuration    → Load config, apply overrides
Phase 2:  Profile          → Resolve deployment profile
Phase 3:  System Scan      → Detect hardware and software
Phase 4:  Environment      → Analyze AI readiness
Phase 5:  Permissions      → Check and request privileges
Phase 6:  Installation     → Install AI tools (with retry queue)
Phase 7:  Models           → Download AI models
Phase 8:  Integrations     → Configure tool connections
Phase 9:  Verification     → Health check everything
Phase 10: Report           → Generate deployment report
Phase 11: Persistence      → Save deployment state
```

### Execution Layer Architecture

The Execution Layer is the core engine that drives real installations. It provides fault-tolerant, autonomous deployment execution with intelligent failure handling.

#### Execution Flow

```
DeploymentSession.deploy_tools()
    │
    ▼
DeploymentExecutor.execute_deployment()
    │
    ├── Phase 1: Initial Deployment
    │   │
    │   ├── Sequential or Parallel execution
    │   │   │
    │   │   ├── For each tool:
    │   │   │   ├── detect() → Check if already installed
    │   │   │   ├── install() → Execute real installation
    │   │   │   └── On failure:
    │   │   │       ├── FailureAnalyzer.analyze() → Classify failure
    │   │   │       └── RetryQueue.add() → Queue for retry
    │   │   │
    │   │   └── Continue to next tool (NEVER block on failure)
    │   │
    │   └── Dependency-aware ordering for parallel execution
    │
    ├── Phase 2: Retry Queue Processing
    │   │
    │   ├── For each due retry entry:
    │   │   ├── RepairEngine.repair_tool() → Attempt repair
    │   │   ├── If repair succeeds → verify and mark complete
    │   │   ├── If repair fails → retry installation
    │   │   └── Exponential backoff between retries
    │   │
    │   └── Up to 3 retry rounds with backoff
    │
    └── Phase 3: Final Validation
        │
        ├── Re-check all failed tools
        ├── Run environment validator
        └── Update results with actual installation status
```

#### Failure Classification

The FailureAnalyzer classifies failures into 8 categories:

| Category      | Recoverable | Retry Strategy         | Example                           |
| ------------- | ----------- | ---------------------- | --------------------------------- |
| PERMISSION    | Yes         | 2 retries, 15s backoff | "Access is denied"                |
| NETWORK       | Yes         | 4 retries, 3s backoff  | "Connection refused"              |
| DISK_SPACE    | No          | 1 retry, 30s backoff   | "No space left on device"         |
| DEPENDENCY    | Yes         | 3 retries, 10s backoff | "command not found: node"         |
| CORRUPTION    | Yes         | 3 retries, 5s backoff  | "checksum mismatch"               |
| COMPATIBILITY | No          | 3 retries, 5s backoff  | "not compatible with your system" |
| TIMEOUT       | Yes         | 3 retries, 5s backoff  | "Command timed out"               |
| UNKNOWN       | Yes         | 3 retries, 5s backoff  | Exit code 42                      |

#### Key Design Principles

1. **Never Block on Failure**: The executor continues deployment even when a tool fails. Failed tools are queued for deferred retry.

2. **Intelligent Retry**: Retry strategies are tailored to failure categories. Network failures retry more aggressively; permission failures wait longer.

3. **Repair Before Retry**: Before retrying an installation, the repair engine attempts to fix the underlying issue (e.g., fix permissions, clear cache).

4. **Final Validation Pass**: After all installations and retries, a final validation pass re-checks all tools. Tools that are actually installed despite previous failures are correctly reported.

5. **Session Persistence**: Complete session state is saved to disk, enabling resumption after restarts. Failed tools from previous sessions can be retried.

6. **Comprehensive Reporting**: Every deployment produces a detailed JSON report with tool results, operation history, terminal output, and validation results.

#### Usage Example

```python
from src.deployment.execution import (
    DeploymentSession,
    DeploymentExecutor,
    TerminalSession,
)
from src.deployment.installers.ollama import OllamaInstaller
from src.deployment.installers.open_webui import OpenWebUIInstaller

# Create session
session = DeploymentSession(data_dir="data")

# Register installers
session.executor.register_installers([
    OllamaInstaller(),
    OpenWebUIInstaller(),
])

# Deploy tools
result = await session.deploy_tools(
    tool_keys=["ollama", "open_webui"],
    skip_existing=True,
    parallel=False,
)

print(f"Status: {result.status}")
print(f"Installed: {result.tools_installed}")
print(f"Failed: {result.tools_failed}")
print(f"Report: {result.report_path}")

# Resume failed tools later
resumed = await session.resume_session(result.session_id)
```

### Deployment Profiles

Built-in profiles provide pre-configured deployment configurations:

| Profile                  | Tools                                                                     | Models                                      | Use Case                         |
| ------------------------ | ------------------------------------------------------------------------- | ------------------------------------------- | -------------------------------- |
| **Minimal AI**           | Ollama                                                                    | llama3.2:3b, nomic-embed-text               | Lightweight local AI             |
| **Coding Workstation**   | Ollama, Open WebUI, Open Interpreter                                      | llama3.1:8b, qwen2.5-coder:7b, codegemma:2b | AI-assisted coding               |
| **Full AI Lab**          | Ollama, LM Studio, Open WebUI, AnythingLLM, Open Interpreter              | 6 models                                    | Complete AI environment          |
| **Agent Development**    | Ollama, Open WebUI, Open Interpreter                                      | 5 models including deepseek-r1              | Building AI agents               |
| **Image/Video AI**       | Ollama, ComfyUI                                                           | 2 models                                    | Image/video generation           |
| **Full Dev Workstation** | Git, Python, Node.js, VS Code, Docker, Java                               | None                                        | Complete development environment |
| **AI Dev Workstation**   | Git, Python, Node.js, VS Code, Windsurf, Docker, Java, Flutter + AI tools | 6 models                                    | Full AI development workstation  |

### Deployment Modes

| Mode          | Description                                  |
| ------------- | -------------------------------------------- |
| **DRY_RUN**   | Simulate deployment without making changes   |
| **SAFE**      | Prompt before each action (default)          |
| **AUTOMATED** | Full automated deployment with auto-approval |
| **RECOVERY**  | Attempt to repair existing installation      |

### Usage Example

```python
from src.deployment import DeploymentOrchestrator
from src.deployment.profiles.base import DeploymentProfileType
from src.deployment.installers.ollama import OllamaInstaller
from src.deployment.installers.open_webui import OpenWebUIInstaller

# Create orchestrator
orchestrator = DeploymentOrchestrator()

# Register installers
orchestrator.register_installer(OllamaInstaller())
orchestrator.register_installer(OpenWebUIInstaller())

# Run deployment
result = await orchestrator.deploy(
    profile_type=DeploymentProfileType.CODING_WORKSTATION,
    config_updates={
        "settings": {
            "mode": "automated",
            "auto_approve": True,
            "verify_install": True,
        }
    }
)

print(f"Status: {result['status']}")
print(f"Duration: {result['duration_seconds']}s")
```

## Future Architecture

### Planned Modules

1. **GUI Layer** - PyQt6/Tkinter interface for visual deployment management
2. **Plugin System** - Dynamic loading of custom tools and installers
3. **Remote Agent** - SSH-based deployment to remote machines
4. **Docker Support** - Containerized deployment environments
5. **CI/CD Integration** - GitHub Actions, GitLab CI pipelines
6. **LLM Integration** - Connect reasoning engine to local/cloud LLMs
7. **Browser Automation** - Web-based setup automation
8. **Terminal Automation** - Interactive terminal control
