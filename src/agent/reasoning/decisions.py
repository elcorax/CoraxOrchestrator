"""
Corax Orchestrator - Decision Engine.

Provides rule-based decision-making for the autonomous agent.
Supports weighted decisions, constraint evaluation, and
priority-based selection.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Callable
from uuid import uuid4

from src.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class Decision:
    """
    The result of a decision-making process.

    Contains the selected option, rationale, and alternatives
    considered.
    """
    decision_id: str
    question: str
    selected_option: str
    confidence: float  # 0.0 to 1.0
    rationale: List[str] = field(default_factory=list)
    alternatives: List[str] = field(default_factory=list)
    scores: Dict[str, float] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "question": self.question,
            "selected_option": self.selected_option,
            "confidence": self.confidence,
            "rationale": self.rationale,
            "alternatives": self.alternatives,
            "scores": self.scores,
            "timestamp": self.timestamp,
        }


class DecisionEngine:
    """
    Rule-based decision engine for the autonomous agent.

    Evaluates options against configurable criteria and selects
    the best choice based on weighted scoring.

    Features:
    - Weighted multi-criteria decision making
    - Constraint-based filtering
    - Priority-based selection
    - Custom scoring functions
    - Decision logging and audit trail
    """

    def __init__(self) -> None:
        self._scoring_functions: Dict[str, Callable[[str, Dict[str, Any]], float]] = {}
        self._default_weights: Dict[str, float] = {
            "safety": 0.4,
            "speed": 0.2,
            "reliability": 0.2,
            "resource_usage": 0.1,
            "user_preference": 0.1,
        }

    def register_scoring_function(
        self,
        name: str,
        func: Callable[[str, Dict[str, Any]], float],
    ) -> None:
        """
        Register a custom scoring function.

        Args:
            name: Name of the scoring criterion
            func: Function that takes (option, context) and returns score 0-1
        """
        self._scoring_functions[name] = func
        logger.debug("Scoring function registered", name=name)

    def decide(
        self,
        question: str,
        options: List[str],
        context: Optional[Dict[str, Any]] = None,
        weights: Optional[Dict[str, float]] = None,
    ) -> Decision:
        """
        Make a decision given options and context.

        Args:
            question: The decision question
            options: Available options to choose from
            context: Decision context with relevant information
            weights: Custom scoring weights (overrides defaults)

        Returns:
            Decision with selected option and rationale
        """
        context = context or {}
        weights = weights or self._default_weights

        # Normalize weights
        total_weight = sum(weights.values())
        if total_weight > 0:
            weights = {k: v / total_weight for k, v in weights.items()}

        # Score each option
        scores: Dict[str, float] = {}
        option_scores: Dict[str, Dict[str, float]] = {}

        for option in options:
            option_scores[option] = {}
            total = 0.0

            for criterion, weight in weights.items():
                score = self._score_option(option, criterion, context)
                option_scores[option][criterion] = score
                total += score * weight

            scores[option] = total

        # Select best option
        if not scores:
            return Decision(
                decision_id=str(uuid4()),
                question=question,
                selected_option="none",
                confidence=0.0,
                rationale=["No options available to evaluate"],
                alternatives=options,
                scores={},
            )

        best_option = max(scores, key=scores.get)
        best_score = scores[best_option]

        # Build rationale
        rationale = self._build_rationale(
            question=question,
            selected=best_option,
            score=best_score,
            option_scores=option_scores,
            weights=weights,
            context=context,
        )

        # Sort alternatives (excluding best)
        alternatives = sorted(
            [o for o in options if o != best_option],
            key=lambda o: scores.get(o, 0),
            reverse=True,
        )

        return Decision(
            decision_id=str(uuid4()),
            question=question,
            selected_option=best_option,
            confidence=best_score,
            rationale=rationale,
            alternatives=alternatives,
            scores=scores,
            metadata={"weights": weights, "option_scores": option_scores},
        )

    def _score_option(
        self,
        option: str,
        criterion: str,
        context: Dict[str, Any],
    ) -> float:
        """
        Score an option for a given criterion.

        Uses registered scoring functions or default heuristics.
        """
        # Check for custom scoring function
        if criterion in self._scoring_functions:
            return self._scoring_functions[criterion](option, context)

        # Default scoring heuristics
        return self._default_score(option, criterion, context)

    def _default_score(
        self,
        option: str,
        criterion: str,
        context: Dict[str, Any],
    ) -> float:
        """Default scoring heuristics for common criteria."""
        option_lower = option.lower()

        if criterion == "safety":
            # Prefer options that don't modify system
            if "safe" in option_lower or "check" in option_lower:
                return 1.0
            if "install" in option_lower or "modify" in option_lower:
                return 0.3
            return 0.7

        elif criterion == "speed":
            # Prefer faster options
            if "quick" in option_lower or "fast" in option_lower:
                return 1.0
            if "full" in option_lower or "complete" in option_lower:
                return 0.4
            return 0.7

        elif criterion == "reliability":
            # Prefer more thorough options
            if "full" in option_lower or "complete" in option_lower:
                return 1.0
            if "quick" in option_lower or "fast" in option_lower:
                return 0.5
            return 0.7

        elif criterion == "resource_usage":
            # Prefer options that use fewer resources
            if "minimal" in option_lower or "light" in option_lower:
                return 1.0
            if "full" in option_lower or "complete" in option_lower:
                return 0.3
            return 0.6

        elif criterion == "user_preference":
            # Check if user has expressed preference in context
            user_prefs = context.get("user_preferences", {})
            for pref_key, pref_value in user_prefs.items():
                if pref_key.lower() in option_lower:
                    return 1.0 if pref_value else 0.0
            return 0.5

        return 0.5

    def _build_rationale(
        self,
        question: str,
        selected: str,
        score: float,
        option_scores: Dict[str, Dict[str, float]],
        weights: Dict[str, float],
        context: Dict[str, Any],
    ) -> List[str]:
        """Build a human-readable rationale for the decision."""
        rationale = []

        rationale.append(
            f"Decision: '{selected}' selected for: {question}"
        )
        rationale.append(
            f"Overall confidence: {score:.2f}"
        )

        # Add criterion breakdown
        if selected in option_scores:
            rationale.append("Scoring breakdown:")
            for criterion, criterion_score in option_scores[selected].items():
                weight = weights.get(criterion, 0)
                weighted = criterion_score * weight
                rationale.append(
                    f"  - {criterion}: {criterion_score:.2f} "
                    f"(weight: {weight:.2f}, weighted: {weighted:.2f})"
                )

        # Add context factors
        if context.get("mode"):
            rationale.append(
                f"Agent mode: {context['mode']}"
            )

        return rationale
