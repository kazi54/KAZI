"""KAZI — Open-source platform for building AI-powered professional services products."""

__version__ = "0.1.0"

from kazi.agents.base import BaseAgent
from kazi.orchestrator.pipeline import Pipeline
from kazi.orchestrator.fanout import FanOut
from kazi.orchestrator.orchestrator import Orchestrator
from kazi.scoring.legend import ScoreLegend
from kazi.scoring.dimensions import ScoringDimension

__all__ = [
    "BaseAgent",
    "Pipeline",
    "FanOut",
    "Orchestrator",
    "ScoreLegend",
    "ScoringDimension",
]
