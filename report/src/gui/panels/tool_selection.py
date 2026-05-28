"""
Corax Orchestrator - Tool & Model Selection Panel.

Selectable installers with dependency graph visualization,
AI stack selection, model selection with size visibility,
and dependency chain display.

Uses the centralized UIStateManager for real-time synchronization.
"""

from typing import Optional, Dict, Any, List, Set
from datetime import datetime

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QGroupBox, QGridLayout, QCheckBox, QFrame, QScrollArea,
    QTreeWidget, QTreeWidgetItem, QListWidget, QListWidgetItem,
    QSlider, QSpinBox, QComboBox, QTextEdit, QSplitter,
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QColor, QBrush

from src.core.logging import get_logger
from src.gui.ui_state import ui_state
from src.runtime.state_bus import state_bus, EventType, EventPriority

logger = get_logger(__name__)


# Tool dependency graph
TOOL_DEPENDENCIES = {
    "ollama": [],
    "lm_studio": [],
    "open_webui": ["ollama"],
    "anythingllm": ["ollama"],
    "open_interpreter": ["python"],
    "comfyui": ["python"],
    "git": [],
    "python": [],
    "node": [],
    "vscode": [],
    "windsurf": [],
    "java": [],
    "flutter": ["git"],
    "docker": [],
}

# Tool categories
TOOL_CATEGORIES = {
    "AI Runtimes": ["ollama", "lm_studio"],
    "AI Applications": ["open_webui", "anythingllm", "open_interpreter", "comfyui"],
    "Development Tools": ["git", "python", "node", "vscode", "windsurf", "java", "flutter", "docker"],
}

# Model information with sizes
MODEL_INFO = {
    "llama3.1:8b": {"size_gb": 4.7, "provider": "ollama", "description": "Meta Llama 3.1 8B"},
    "llama3.1:70b": {"size_gb": 40, "provider": "ollama", "description": "Meta Llama 3.1 70B"},
    "llama3.1:405b": {"size_gb": 231, "provider": "ollama", "description": "Meta Llama 3.1 405B"},
    "mistral:7b": {"size_gb": 4.1, "provider": "ollama", "description": "Mistral 7B"},
    "mixtral:8x7b": {"size_gb": 26, "provider": "ollama", "description": "Mixtral 8x7B"},
    "codellama:7b": {"size_gb": 3.8, "provider": "ollama", "description": "Code Llama 7B"},
    "codellama:34b": {"size_gb": 19, "provider": "ollama", "description": "Code Llama 34B"},
    "phi3:3.8b": {"size_gb": 2.2, "provider": "ollama", "description": "Phi-3 3.8B"},
    "phi3:14b": {"size_gb": 7.8, "provider": "ollama", "description": "Phi-3 14B"},
    "gemma2:2b": {"size_gb": 1.6, "provider": "ollama", "description": "Gemma 2 2B"},
    "gemma2:9b": {"size_gb": 5.5, "provider": "ollama", "description": "Gemma 2 9B"},
    "gemma2:27b": {"size_gb": 16, "provider": "ollama", "description": "Gemma 2 27B"},
    "qwen2.5:7b": {"size_gb": 4.4, "provider": "ollama", "description": "Qwen 2.5 7B"},
    "qwen2.5:32b": {"size_gb": 19, "provider": "ollama", "description": "Qwen 2.5 32B"},
    "deepseek-coder:6.7b": {"size_gb": 3.8, "provider": "ollama", "description": "DeepSeek Coder 6.7B"},
    "deepseek-coder:33b": {"size_gb": 19, "provider": "ollama", "description": "DeepSeek Coder 33B"},
    "nomic-embed-text": {"size_gb": 0.27, "provider": "ollama", "description": "Nomic Embed Text"},
    "mxbai-embed-large": {"size_gb": 0.67, "provider": "ollama", "description": "MXBAI Embed Large"},
}


class ToolSelectionPanel(QWidget):
    """Tool and model selection with dependency visualization."""

    def __init__(self, kernel: Any = None):
        super().__init__()
        self._kernel = kernel
        self._selected_tools: Set[str] = set()
        self._selected_models: Set[str] = set()

        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        splitter = QSplitter(Qt.Horizontal)

        # Left side: tool selection
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)

        # Tool categories
        for category, tools in TOOL_CATEGORIES.items():
            group = QGroupBox(category)
            group_layout = QVBoxLayout(group)
            for tool_name in tools:
                cb = QCheckBox(tool_name)
                cb.setChecked(tool_name in ["ollama", "lm_studio", "open_webui"])
                cb.stateChanged.connect(lambda state, t=tool_name: self._on_tool_toggle(t, state))
                group_layout.addWidget(cb)
            left_layout.addWidget(group)

        # Select all / clear buttons
        btn_row = QHBoxLayout()
        select_all = QPushButton("Select All")
        select_all.clicked.connect(self._select_all_tools)
        btn_row.addWidget(select_all)
        clear_all = QPushButton("Clear All")
        clear_all.clicked.connect(self._clear_all_tools)
        btn_row.addWidget(clear_all)
        left_layout.addLayout(btn_row)
        left_layout.addStretch()

        splitter.addWidget(left_widget)

        # Right side: dependency graph and model selection
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)

        # Dependency graph
        dep_group = QGroupBox("Dependency Graph")
        dep_layout = QVBoxLayout(dep_group)
        self._dep_tree = QTreeWidget()
        self._dep_tree.setHeaderLabels(["Component", "Dependencies"])
        self._dep_tree.setAlternatingRowColors(True)
        dep_layout.addWidget(self._dep_tree)
        right_layout.addWidget(dep_group)

        # Model selection
        model_group = QGroupBox("Model Selection")
        model_layout = QVBoxLayout(model_group)

        # Provider filter
        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("Provider:"))
        self._provider_filter = QComboBox()
        self._provider_filter.addItems(["All", "ollama"])
        self._provider_filter.currentTextChanged.connect(self._filter_models)
        filter_row.addWidget(self._provider_filter)
        filter_row.addStretch()
        model_layout.addLayout(filter_row)

        # Model list
        self._model_list = QTreeWidget()
        self._model_list.setHeaderLabels(["Model", "Size", "Provider", "Description"])
        self._model_list.setAlternatingRowColors(True)
        self._model_list.setSelectionMode(QTreeWidget.ExtendedSelection)
        self._model_list.itemChanged.connect(self._on_model_toggle)
        model_layout.addWidget(self._model_list)

        # Model info
        self._model_info = QLabel("Select models to see total download size")
        self._model_info.setObjectName("subheading")
        model_layout.addWidget(self._model_info)

        right_layout.addWidget(model_group, 1)

        splitter.addWidget(right_widget)
        splitter.setSizes([400, 600])

        layout.addWidget(splitter)

        # Populate
        self._populate_dep_graph()
        self._populate_models()

    def _populate_dep_graph(self) -> None:
        """Populate the dependency tree."""
        self._dep_tree.clear()
        for tool, deps in TOOL_DEPENDENCIES.items():
            item = QTreeWidgetItem([tool, ", ".join(deps) if deps else "None"])
            if not deps:
                item.setForeground(1, QColor("#a6e3a1"))
            else:
                item.setForeground(1, QColor("#f9e2af"))
            self._dep_tree.addTopLevelItem(item)

    def _populate_models(self) -> None:
        """Populate the model selection list."""
        self._model_list.clear()
        for model_name, info in MODEL_INFO.items():
            item = QTreeWidgetItem([
                model_name,
                f"{info['size_gb']:.1f} GB",
                info['provider'],
                info['description'],
            ])
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(0, Qt.Unchecked)
            # Color code by size
            if info['size_gb'] < 5:
                item.setForeground(1, QColor("#a6e3a1"))
            elif info['size_gb'] < 20:
                item.setForeground(1, QColor("#f9e2af"))
            else:
                item.setForeground(1, QColor("#f38ba8"))
            self._model_list.addTopLevelItem(item)

    def _filter_models(self, provider: str) -> None:
        """Filter models by provider."""
        for i in range(self._model_list.topLevelItemCount()):
            item = self._model_list.topLevelItem(i)
            if provider == "All":
                item.setHidden(False)
            else:
                item.setHidden(item.text(2) != provider)

    def _on_tool_toggle(self, tool_name: str, state: int) -> None:
        """Handle tool checkbox toggle and sync to ui_state."""
        if state == Qt.Checked:
            self._selected_tools.add(tool_name)
            # Auto-select dependencies
            for dep in TOOL_DEPENDENCIES.get(tool_name, []):
                if dep not in self._selected_tools:
                    self._selected_tools.add(dep)
        else:
            self._selected_tools.discard(tool_name)
        self._update_dep_graph()
        self._sync_selections()

    def _on_model_toggle(self, item: QTreeWidgetItem, column: int) -> None:
        """Handle model checkbox toggle and sync to ui_state."""
        if column != 0:
            return
        model_name = item.text(0)
        if item.checkState(0) == Qt.Checked:
            self._selected_models.add(model_name)
        else:
            self._selected_models.discard(model_name)
        self._update_model_info()
        self._sync_selections()

    def _update_model_info(self) -> None:
        """Update model selection info."""
        total_gb = sum(
            MODEL_INFO[m]["size_gb"] for m in self._selected_models
        )
        count = len(self._selected_models)
        if count > 0:
            self._model_info.setText(
                f"Selected {count} model(s) - Total: {total_gb:.1f} GB"
            )
        else:
            self._model_info.setText("Select models to see total download size")

    def _update_dep_graph(self) -> None:
        """Update dependency graph highlighting."""
        for i in range(self._dep_tree.topLevelItemCount()):
            item = self._dep_tree.topLevelItem(i)
            tool = item.text(0)
            if tool in self._selected_tools:
                item.setForeground(0, QColor("#a6e3a1"))
            else:
                item.setForeground(0, QColor("#cdd6f4"))

    def _sync_selections(self) -> None:
        """Push current tool/model selections to ui_state for cross-panel access."""
        ui_state._selected_tools = list(self._selected_tools)
        ui_state._selected_models = list(self._selected_models)

    def _select_all_tools(self) -> None:
        """Select all tools."""
        for tool in TOOL_DEPENDENCIES:
            self._selected_tools.add(tool)
        self._update_dep_graph()
        self._sync_selections()

    def _clear_all_tools(self) -> None:
        """Clear all tool selections."""
        self._selected_tools.clear()
        self._update_dep_graph()
        self._sync_selections()

    def get_selected_tools(self) -> List[str]:
        """Get list of selected tools."""
        return list(self._selected_tools)

    def get_selected_models(self) -> List[str]:
        """Get list of selected models."""
        return list(self._selected_models)

    def get_total_download_size_gb(self) -> float:
        """Get total estimated download size in GB."""
        return sum(MODEL_INFO[m]["size_gb"] for m in self._selected_models)
