"""
CIAR Scoring System for Memory Promotion

Implements the Certainty-Impact-Age-Recency (CIAR) scoring algorithm
as specified in ADR-004. Calculates scores to determine which facts
should be promoted from L1 (Active Context) to L2 (Working Memory).

Formula: CIAR = (Certainty x Impact) x Age_Decay x Recency_Boost

Components:
- Certainty (C): Confidence in the fact's accuracy (0.0-1.0)
- Impact (I): Importance/relevance of the fact (0.0-1.0)
- Age Decay (AD): Time-based decay factor (0.1-1.0)
- Recency Boost (RB): Access-based reinforcement (1.0-1.3)

Author: MAS Memory Layer Team
Date: November 2025
"""

from pathlib import Path
from typing import Any, cast

import yaml

from src.memory.ciar_formula import (
    DEFAULT_AGE_DECAY_LAMBDA,
    DEFAULT_CIAR_THRESHOLD,
    DEFAULT_RECENCY_ALPHA,
    calculate_age_decay,
    calculate_ciar_score,
    calculate_recency_boost,
    resolve_created_at,
)
from src.memory.models import Fact


class CIARScorer:
    """
    Calculate CIAR scores for facts to determine promotion eligibility.

    The CIAR score combines multiple factors to assess a fact's value:
    - How certain/reliable is it?
    - How impactful/important is it?
    - How recent is it? (older = lower)
    - How frequently accessed? (more = higher)

    Example:
        >>> scorer = CIARScorer()
        >>> fact = {
        ...     'content': 'User prefers morning meetings',
        ...     'fact_type': 'preference',
        ...     'certainty': 0.9,
        ...     'created_at': datetime.now(),
        ...     'access_count': 5
        ... }
        >>> score = scorer.calculate(fact)
        >>> print(f"CIAR Score: {score:.3f}")
        CIAR Score: 0.756
    """

    def __init__(self, config_path: str | None = None):
        """
        Initialize the CIAR scorer with configuration.

        Args:
            config_path: Path to ciar_config.yaml, defaults to config/ciar_config.yaml
        """
        if config_path is None:
            config_path_obj = Path(__file__).parent.parent.parent / "config" / "ciar_config.yaml"
        else:
            config_path_obj = Path(config_path)

        with open(config_path_obj) as f:
            config = cast(dict[str, Any], yaml.safe_load(f))

        self.config = cast(dict[str, Any], config["ciar"])
        self.threshold = float(self.config.get("threshold", DEFAULT_CIAR_THRESHOLD))

        # Age decay parameters
        age_decay_config = cast(dict[str, Any], self.config.get("age_decay", {}))
        self.age_decay_lambda = float(age_decay_config.get("lambda", DEFAULT_AGE_DECAY_LAMBDA))
        max_age_days = age_decay_config.get("max_age_days")
        self.max_age_days = float(max_age_days) if max_age_days is not None else None
        min_age_score = age_decay_config.get("min_score", 0.0)
        self.min_age_score = float(min_age_score) if min_age_score is not None else 0.0

        # Recency boost parameters
        recency_config = cast(dict[str, Any], self.config.get("recency", {}))
        self.recency_boost_factor = float(recency_config.get("boost_factor", DEFAULT_RECENCY_ALPHA))
        max_recency_boost = recency_config.get("max_boost")
        self.max_recency_boost = float(max_recency_boost) if max_recency_boost is not None else None

        # Certainty parameters
        self.default_certainty = float(self.config["certainty"]["default"])
        self.certainty_heuristics = cast(dict[str, Any], self.config["certainty"])

        # Impact weights
        self.impact_weights = cast(dict[str, float], self.config["impact_weights"])

    def calculate(self, fact: dict[str, Any] | Fact) -> float:
        """
        Calculate the complete CIAR score for a fact.

        Formula: (Certainty x Impact) x Age_Decay x Recency_Boost

        Args:
            fact: Fact dictionary or Fact model instance

        Returns:
            float: CIAR score (typically 0.0-1.0, can exceed 1.0 with high recency boost)

        Example:
            >>> fact = {'content': 'Test', 'fact_type': 'preference',
            ...         'certainty': 0.8, 'created_at': datetime.now()}
            >>> score = scorer.calculate(fact)
            >>> assert 0.0 <= score <= 1.5
        """
        # Convert Fact model to dict if needed, preserving whether impact was explicitly set
        if isinstance(fact, Fact):
            fact_dict = fact.model_dump()
            fact_dict["_impact_set_explicitly"] = "impact" in getattr(
                fact, "model_fields_set", set()
            )
        else:
            fact_dict = fact
            if isinstance(fact_dict, dict) and "impact" in fact_dict:
                fact_dict = {**fact_dict, "_impact_set_explicitly": True}

        # Calculate components
        certainty = self._calculate_certainty(fact_dict)
        impact = self._calculate_impact(fact_dict)
        age_decay = self._calculate_age_decay(fact_dict)
        recency_boost = self._calculate_recency(fact_dict)

        return calculate_ciar_score(certainty, impact, age_decay, recency_boost)

    def _calculate_certainty(self, fact: dict[str, Any]) -> float:
        """
        Calculate certainty score (confidence in fact's accuracy).

        Priority:
        1. Explicit 'certainty' field (from LLM)
        2. Heuristic based on content analysis
        3. Default certainty value

        Args:
            fact: Fact dictionary

        Returns:
            float: Certainty score (0.0-1.0)
        """
        # Check for explicit certainty from LLM
        if "certainty" in fact and fact["certainty"] is not None:
            return max(0.0, min(1.0, float(fact["certainty"])))

        # Apply heuristics based on content
        content = fact.get("content", "").lower()

        # Check for certainty indicators in content
        if any(phrase in content for phrase in ["i prefer", "i want", "i need", "always", "never"]):
            return float(self.certainty_heuristics.get("explicit_statement", 0.9))
        elif any(phrase in content for phrase in ["usually", "often", "typically", "generally"]):
            return float(self.certainty_heuristics.get("implied_preference", 0.8))
        elif any(phrase in content for phrase in ["might", "maybe", "possibly", "could"]):
            return float(self.certainty_heuristics.get("speculation", 0.4))
        elif any(phrase in content for phrase in ["observed", "noticed", "seen"]):
            return float(self.certainty_heuristics.get("observation", 0.6))

        # Default certainty
        return float(self.default_certainty)

    def _calculate_impact(self, fact: dict[str, Any]) -> float:
        """
        Calculate impact score (importance/relevance of fact).

        Based on fact_type classification. Higher weight = more important
        to remember long-term.

        Args:
            fact: Fact dictionary

        Returns:
            float: Impact score (0.0-1.0)
        """
        explicit_flag = fact.get("_impact_set_explicitly")
        if explicit_flag is None:
            explicit_flag = "impact" in fact

        # If caller provided an explicit impact score, trust it (bounded)
        if explicit_flag and "impact" in fact and fact["impact"] is not None:
            try:
                return max(0.0, min(1.0, float(fact["impact"])))
            except (TypeError, ValueError):
                # Fall back to heuristics if the explicit value is unusable
                pass

        fact_type = fact.get("fact_type", "mention").lower()

        # Look up impact weight for this fact type
        impact = float(self.impact_weights.get(fact_type, 0.5))

        # Adjust impact based on metadata
        # Boost if fact has high access count (indicates importance)
        if fact.get("access_count", 0) > 10:
            impact = min(1.0, impact * 1.1)

        # Boost if fact is tagged as important
        if fact.get("is_important", False):
            impact = min(1.0, impact * 1.2)

        return float(impact)

    def _calculate_age_decay(self, fact: dict[str, Any]) -> float:
        """
        Calculate age decay factor (older facts decay exponentially).

        Formula: exp(-lambda * age_days)

        Where:
        - lambda: decay rate (higher = faster decay)
        - age_days: days since fact creation

        Args:
            fact: Fact dictionary with 'created_at' timestamp

        Returns:
            float: Age decay factor (min_score to 1.0)
        """
        created_at = resolve_created_at(fact)

        if created_at is None:
            # No timestamp, assume it's new
            return 1.0

        return calculate_age_decay(
            created_at,
            decay_lambda=self.age_decay_lambda,
            max_age_days=self.max_age_days,
            min_score=self.min_age_score,
        )

    def _calculate_recency(self, fact: dict[str, Any]) -> float:
        """
        Calculate recency boost (rewards frequently accessed facts).

        Formula: 1 + (alpha * access_count)

        Args:
            fact: Fact dictionary with 'access_count'

        Returns:
            float: Recency boost (1.0 or higher)
        """
        return calculate_recency_boost(
            fact.get("access_count", 0),
            alpha=self.recency_boost_factor,
            max_boost=self.max_recency_boost,
        )

    def exceeds_threshold(self, fact: dict[str, Any] | Fact) -> bool:
        """
        Check if a fact's CIAR score exceeds the promotion threshold.

        Args:
            fact: Fact dictionary or Fact model

        Returns:
            bool: True if score >= threshold, eligible for promotion
        """
        score = self.calculate(fact)
        return score >= self.threshold

    def calculate_components(self, fact: dict[str, Any] | Fact) -> dict[str, float]:
        """
        Calculate all CIAR components separately for debugging/analysis.

        Args:
            fact: Fact dictionary or Fact model

        Returns:
            dict: Component scores with keys:
                - certainty: Confidence score (0.0-1.0)
                - impact: Importance score (0.0-1.0)
                - age_decay: Time decay factor (0.1-1.0)
                - recency_boost: Access boost (1.0-1.3)
                - base_score: certainty x impact
                - temporal_score: age_decay x recency_boost
                - final_score: base_score x temporal_score
        """
        # Convert Fact model to dict if needed, preserving whether impact was explicitly set
        if isinstance(fact, Fact):
            fact_dict = fact.model_dump()
            fact_dict["_impact_set_explicitly"] = "impact" in getattr(
                fact, "model_fields_set", set()
            )
        else:
            fact_dict = fact
            if isinstance(fact_dict, dict) and "impact" in fact_dict:
                fact_dict = {**fact_dict, "_impact_set_explicitly": True}

        certainty = self._calculate_certainty(fact_dict)
        impact = self._calculate_impact(fact_dict)
        age_decay = self._calculate_age_decay(fact_dict)
        recency_boost = self._calculate_recency(fact_dict)

        base_score = certainty * impact
        temporal_score = age_decay * recency_boost
        final_score = calculate_ciar_score(certainty, impact, age_decay, recency_boost)

        return {
            "certainty": certainty,
            "impact": impact,
            "age_decay": age_decay,
            "recency_boost": recency_boost,
            "base_score": base_score,
            "temporal_score": temporal_score,
            "final_score": final_score,
        }
