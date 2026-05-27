# Corax Orchestrator - Clean Machine Test Guide

## Overview

This guide covers testing Corax on a clean Windows machine with no pre-existing development tools, Python, or dependencies. The goal is to validate that Corax can bootstrap itself from scratch.

## Prerequisites

- A clean Windows 10/11 machine (physical or VM)
- Internet connection (for initial download)
- Administrator access (for elevation when needed)
- At least 20GB free disk space
- At least 8GB RAM

## Test Scenarios

### Scenario 1: Fresh Install from Executable

1. Copy `dist/` folder to the clean machine
2. Run `corax.exe` (or `run_corax.bat`)
3. Expected behavior:
   - GUI launches within 10 seconds
   - Environment validation runs automatically
   - Missing dependencies detected
   - Self-healing initiates dependency installation
   - Dashboard shows system status

### Scenario 2: Offline Installation

1. Pre-download all installers to `data/cache/`
2. Copy entire `dist/` folder with cache
3. Disconnect from internet
4. Run `corax.exe`
5. Expected behavior:
   - GUI launches without internet
   - Uses cached installers
   - Deployment proceeds offline

### Scenario 3: Partial Installation Recovery

1. Start a deployment
2. Kill the process mid-deployment
3. Restart Corax
4. Expected behavior:
   - Detects interrupted deployment
   - Recovers from last checkpoint
   - Resumes deployment

### Scenario 4: Antivirus Handling

1. Run Corax with Windows Defender enabled
2. Expected behavior:
   - Corax detects antivirus interference
   - Requests exclusions if needed
   - Continues deployment with fallback strategies

## Validation Checklist

- [ ] GUI launches without errors
- [ ] Dashboard shows accurate system status
- [ ] Tool selection panel lists all installers
- [ ] Deployment control panel responds to commands
- [ ] Runtime monitor shows live output
- [ ] Reports viewer loads and displays reports
- [ ] Settings panel saves and loads configuration
- [ ] Permissions panel shows accurate status
- [ ] Emergency stop works correctly
- [ ] Mode switching works (safe/assisted/autonomous)
- [ ] Unattended mode toggle works
- [ ] Progress visualization updates in real-time
- [ ] Retry queue visibility shows pending retries
- [ ] Repair activity visibility shows active repairs

## Known Limitations (Internal Alpha)

- GUI is functional but not fully polished
- Some panels may show placeholder data
- Executable size is large (~200MB+)
- First launch may trigger antivirus warnings
- Some installers require manual elevation
- Model downloads require significant bandwidth
