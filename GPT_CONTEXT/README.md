# Corax Orchestrator

**Autonomous AI Workstation Deployment System**

Corax Orchestrator is a production-oriented, modular deployment system that transforms a clean computer into a complete AI development workstation. It autonomously scans hardware, detects missing dependencies, installs and configures AI tools, manages local models, and generates comprehensive deployment reports.

## Features

- **🔍 System Scanner** - Deep hardware and software inventory (CPU, GPU, RAM, disks, installed apps)
- **📊 Environment Analyzer** - Readiness assessment with 0-100 scoring and actionable recommendations
- **🛠️ Installer Engine** - Dependency-aware installation with topological ordering
- **📦 Tool Registry** - Extensible registry of 12+ supported AI development tools
- **🤖 Model Manager** - Download and manage local AI models (Ollama, HuggingFace)
- **🔄 Task Orchestrator** - 6-phase deployment workflow with progress tracking
- **🛡️ Self-Healing Engine** - Automatic error recovery with configurable strategies
- **🔐 Permission Manager** - Granular privilege control with consent callbacks
- **💾 State Persistence** - JSON/MessagePack storage with atomic writes and versioning
- **📝 Reporting Engine** - JSON, Markdown, and HTML deployment reports
- **🖥️ Cross-Platform** - Windows-first with macOS and Linux abstraction layers

## Supported Tools

| Category           | Tools                                              |
| ------------------ | -------------------------------------------------- |
| **AI Platforms**   | LM Studio, Ollama                                  |
| **AI Tools**       | Open WebUI, AnythingLLM, Open Interpreter, ComfyUI |
| **IDEs**           | Visual Studio Code, Windsurf                       |
| **Runtimes**       | Python, Node.js                                    |
| **Infrastructure** | Docker, Git                                        |

## Quick Start

### Installation

```bash
# Clone the repository
git clone https://github.com/your-org/corax-orchestrator.git
cd corax-orchestrator

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Or use the setup script
python scripts/setup_env.py
```

### Usage

```bash
# Scan system hardware and software
python -m src.main scan

# Analyze environment readiness
python -m src.main analyze

# Run full deployment
python -m src.main deploy

# Deploy specific tools
python -m src.main deploy --tools git,python,ollama

# Deploy tools and pull AI models
python -m src.main deploy --tools git,python,ollama --models llama3.2:3b

# List all supported tools
python -m src.main list-tools

# Search for tools
python -m src.main search ollama

# Deploy development tools (Git, Python, Node.js) with real installers
python -m src.main deploy-dev

# Detect only (no installation)
python -m src.main deploy-dev --detect-only

# Validate environment only
python -m src.main deploy-dev --validate-only

# Skip already-installed tools
python -m src.main deploy-dev --skip-existing

# Deploy in parallel
python -m src.main deploy-dev --parallel
```

### Programmatic API

```python
import asyncio
from src.main import CoraxOrchestrator

async def main():
    corax = CoraxOrchestrator()

    # Scan system
    scan_result = await corax.scan()
    print(f"CPU: {scan_result['hardware']['cpu']['name']}")
    print(f"RAM: {scan_result['hardware']['memory']['total_gb']} GB")

    # Analyze environment
    analysis = await corax.analyze()
    print(f"Readiness Score: {analysis['score']}/100")

    # Deploy tools
    result = await corax.deploy(
        tools=["git", "python", "ollama"],
        models=["llama3.2:3b"],
    )
    print(f"Status: {result['status']}")

asyncio.run(main())
```

### Dev Deploy API

```python
import asyncio
from src.deployment.dev_deploy import DevDeploy

async def main():
    deployer = DevDeploy()

    # Detect installed tools
    detection = await deployer.detect_all()
    for tool, info in detection.items():
        print(f"{tool}: {info['status']}")

    # Deploy all tools
    report = await deployer.deploy()
    print(f"Status: {report.status}")
    print(f"Duration: {report.total_duration_ms}ms")

    # Validate environment
    validation = await deployer.validate_environment()
    print(f"Validation passed: {validation['passed']}")

    # Get summary
    summary = deployer.get_summary()
    print(summary)

asyncio.run(main())
```

## Architecture

```
corax-orchestrator/
├── src/
│   ├── main.py                    # Entry point & CLI
│   ├── core/                      # Core infrastructure
│   │   ├── config.py              # Configuration management
│   │   ├── exceptions.py          # Error hierarchy
│   │   └── logging.py             # Structured logging
│   ├── modules/                   # Business logic modules
│   │   ├── system_scanner.py      # Hardware/software detection
│   │   ├── environment_analyzer.py# Readiness assessment
│   │   ├── tool_registry.py       # Tool metadata & dependencies
│   │   ├── installer_engine.py    # Installation orchestration
│   │   ├── model_manager.py       # AI model management
│   │   ├── permission_manager.py  # Privilege control
│   │   ├── self_healing.py        # Error recovery
│   │   ├── state_persistence.py   # Data persistence
│   │   ├── reporting.py           # Report generation
│   │   └── task_orchestrator.py   # Workflow orchestration
│   ├── platform/                  # Cross-platform abstraction
│   │   ├── base.py                # Abstract base class
│   │   ├── windows.py             # Windows implementation
│   │   ├── macos.py               # macOS implementation
│   │   ├── linux.py               # Linux implementation
│   │   └── factory.py             # Platform factory
│   ├── deployment/                # Real deployment infrastructure
│   │   ├── installers/            # Tool-specific installers
│   │   │   ├── base.py            # AIInstallerBase & InstallResult
│   │   │   ├── dev_base.py        # DevInstallerBase for dev tools
│   │   │   ├── git_installer.py   # Git installer (winget + direct)
│   │   │   ├── python_installer.py# Python installer (winget + direct)
│   │   │   ├── node_installer.py  # Node.js installer (winget + direct)
│   │   │   └── ...                # AI tool installers
│   │   ├── execution/             # Execution engine
│   │   │   ├── terminal.py        # Terminal session management
│   │   │   ├── executor.py        # Deployment executor
│   │   │   ├── session.py         # Deployment session
│   │   │   ├── retry_queue.py     # Retry queue with backoff
│   │   │   └── failure_analyzer.py# Failure analysis
│   │   ├── validation.py          # Installation validation
│   │   ├── dev_deploy.py          # Dev deploy orchestrator
│   │   ├── operations.py          # Deployment operations
│   │   ├── windows_utils.py       # Windows-specific utilities
│   │   ├── repair/                # Repair engine
│   │   └── orchestrator.py        # Deployment orchestrator
│   ├── installers/                # Legacy (deprecated, compatibility shim)
│   └── utils/                     # Utility functions
│       ├── system.py              # System utilities
│       ├── network.py             # Network utilities
│       └── validation.py          # Input validation
├── scripts/
│   └── setup_env.py               # Environment bootstrap script
├── config/
│   └── default.yaml               # Default configuration
├── data/
│   ├── persistence/               # Task state storage
│   ├── reports/                   # Deployment reports
│   ├── logs/                      # Application logs
│   └── models/                    # Local AI models
├── tests/
│   ├── unit/                      # Unit tests
│   └── integration/               # Integration tests
├── docs/                          # Documentation
├── requirements.txt               # Python dependencies
└── README.md                      # This file
```

## Deployment Workflow

The orchestrator runs a 6-phase deployment workflow:

1. **Scan** (10-25%) - Detect hardware specs and installed software
2. **Analyze** (30-45%) - Evaluate environment readiness and identify gaps
3. **Permissions** (50-55%) - Check and request required privileges
4. **Install** (60-80%) - Install tools in dependency order with recovery
5. **Models** (85-90%) - Pull and configure AI models
6. **Report** (95-100%) - Generate comprehensive deployment report

## Dev Deploy Workflow

The `deploy-dev` command runs a focused deployment for development tools:

1. **Detect** - Check which tools are already installed
2. **Install** - Install missing tools using winget (with fallback)
3. **Validate** - Verify installations with version checks
4. **Report** - Generate structured deployment report

Key features:

- **Failure tolerance**: If one installer fails, remaining installations continue
- **Retry queue**: Failed installers are queued for retry
- **Structured logging**: All operations logged with correlation IDs
- **Structured reports**: JSON reports with operation IDs, durations, exit codes

## Configuration

Configuration is managed via YAML files in the `config/` directory:

- `config/default.yaml` - Default configuration (do not edit)
- `config/local.yaml` - Local overrides (create this file)

Key configuration sections:

```yaml
general:
  debug: false
  log_level: "INFO"

installation:
  verify_checksums: true
  max_retries: 3

permissions:
  auto_accept: false

self_healing:
  enabled: true
  max_retries: 3
```

## Development

### Running Tests

```bash
# Run all tests
pytest tests/

# Run with coverage
pytest tests/ --cov=src

# Run specific test file
pytest tests/integration/test_dev_deploy.py -v

# Run integration tests only
pytest tests/integration/ -v
```

### Environment Setup

```bash
# Check environment
python scripts/setup_env.py --check

# Install all dependencies (including dev)
python scripts/setup_env.py --dev

# Install with Windows extras
python scripts/setup_env.py --windows

# Install everything
python scripts/setup_env.py --all
```

### Project Validation

```bash
# Run project integrity checks
python _validate.py
```

### Adding a New Tool

1. Add tool metadata to `ToolRegistry.BUILTIN_TOOLS` in `tool_registry.py`
2. Create an installer class in `src/deployment/installers/` extending `AIInstallerBase`
3. Register the installer in the installer engine

### Project Status

See [TODO.md](docs/TODO.md) for the development roadmap.

## License

MIT License - see LICENSE file for details.
