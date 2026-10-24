"""
SLR Review Django Models Package.
Re-exports all Systematic Literature Review data models:
- SLRWorkspaceConfig: Policy engine, gate modes, quorum rules, sampling
- SLRProtocol, ProtocolAmendment: PICO criteria, PROSPERO registry tracking, version locking
- AuditSampleCohort: Sample batches generated at screening and extraction gates
- ScreeningReview: Individual blind dual-evaluations and verbatim evidence quotes
- ExtractionReview: Parameter verification, modification, and quote validation
- AdjudicationDispute: Split-vote conflict resolution and Senior Arbiter rulings
- RiskOfBiasAssessment: Cochrane RoB 2, ROBINS-I appraisal and Traffic Light data
- SLRPRISMAMetrics: PRISMA 2020 flow counts and Cohen's Kappa agreement metrics
- SearchQueryRecord: Multi-source search strategy logging (PRISMA Item 7)
- MetaAnalysisOutcomeData: Structured quantitative effect size data (binary & continuous)
"""

from .workspace_config import SLRWorkspaceConfig, get_default_exclusion_reasons
from .protocol import SLRProtocol, ProtocolAmendment
from .sample_cohort import AuditSampleCohort
from .review import ScreeningReview
from .extraction_review import ExtractionReview
from .dispute import AdjudicationDispute
from .risk_of_bias import RiskOfBiasAssessment
from .prisma import SLRPRISMAMetrics
from .search_query import SearchQueryRecord
from .meta_analysis import MetaAnalysisOutcomeData

__all__ = [
    "SLRWorkspaceConfig",
    "get_default_exclusion_reasons",
    "SLRProtocol",
    "ProtocolAmendment",
    "AuditSampleCohort",
    "ScreeningReview",
    "ExtractionReview",
    "AdjudicationDispute",
    "RiskOfBiasAssessment",
    "SLRPRISMAMetrics",
    "SearchQueryRecord",
    "MetaAnalysisOutcomeData",
]
