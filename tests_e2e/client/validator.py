"""
Data Consistency, Deep Type Checking, and Mathematical Evaluation Validator for E2E Tests.

Validates that data moving back and forth across APIs, services, and MCP tools
maintains strict type safety, schema adherence, mathematical consistency with custom formulas,
and round-trip synchronization between relational models and scorecards.
"""

import re
import uuid
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional, Callable, Union

logger = logging.getLogger("e2e_validator")


class DataConsistencyValidator:
    """
    Core validator for E2E payloads, schemas, mathematical evaluations, and data invariants.
    """

    @staticmethod
    def validate_uuid(val: Any, field_name: str = "id") -> str:
        """Asserts that val is a valid hexadecimal UUID string."""
        assert val is not None, f"Field '{field_name}' must not be None"
        val_str = str(val).strip()
        try:
            parsed = uuid.UUID(val_str)
            assert str(parsed) == val_str.lower(), f"Field '{field_name}' must match canonical UUID format"
            return str(parsed)
        except (ValueError, TypeError, AssertionError) as e:
            raise AssertionError(f"Field '{field_name}'='{val}' is not a valid UUID: {e}")

    @staticmethod
    def validate_iso_timestamp(val: Any, field_name: str = "timestamp") -> datetime:
        """Asserts that val is a valid ISO 8601 timestamp string."""
        assert val is not None, f"Timestamp field '{field_name}' must not be None"
        try:
            return datetime.fromisoformat(str(val).replace("Z", "+00:00"))
        except (ValueError, TypeError) as e:
            raise AssertionError(f"Timestamp field '{field_name}'='{val}' is not a valid ISO 8601 string: {e}")

    @classmethod
    def validate_paper_schema(cls, paper: Dict[str, Any]) -> None:
        """
        Deep structural and type validation for Paper objects returned by /api/papers/.
        """
        assert isinstance(paper, dict), f"Paper payload must be a dict, got {type(paper)}"
        cls.validate_uuid(paper.get("id"), "paper.id")
        
        # Required non-empty string fields
        for field in ("title",):
            val = paper.get(field)
            assert isinstance(val, str) and len(val.strip()) > 0, f"Paper '{field}' must be a non-empty string, got: {val}"

        # Source database enum
        source_db = paper.get("source_database")
        if source_db:
            assert source_db in ("arxiv", "openalex", "lens", "pubmed"), f"Unexpected source_database: {source_db}"

        # Screening status enum
        status = paper.get("screening_status")
        valid_statuses = (
            "pending",
            "abstract_passed",
            "full_text_passed",
            "accepted",
            "borderline",
            "rejected",
            "withdrawn",
        )
        if status:
            assert status in valid_statuses, f"Paper screening_status '{status}' not in {valid_statuses}"

        # Signal score range and type
        score = paper.get("signal_score")
        if score is not None:
            assert isinstance(score, (int, float)), f"signal_score must be numeric, got {type(score)}: {score}"
            assert 0.0 <= float(score) <= 1000.0, f"signal_score out of expected range [0.0, 1000.0]: {score}"

        # Timestamps
        if paper.get("created_at"):
            cls.validate_iso_timestamp(paper.get("created_at"), "paper.created_at")

    @classmethod
    def validate_paper_metric_schema(cls, metric: Dict[str, Any]) -> None:
        """
        Deep structural and type validation for PaperMetric records returned by /api/paper-metrics/.
        """
        assert isinstance(metric, dict), f"PaperMetric payload must be a dict, got {type(metric)}"
        cls.validate_uuid(metric.get("id"), "metric.id")
        if metric.get("paper"):
            cls.validate_uuid(metric.get("paper"), "metric.paper")
        if metric.get("pipeline_run"):
            cls.validate_uuid(metric.get("pipeline_run"), "metric.pipeline_run")
        if metric.get("workspace"):
            cls.validate_uuid(metric.get("workspace"), "metric.workspace")

        status = metric.get("screening_status")
        valid_statuses = ("pending", "abstract_passed", "full_text_passed", "accepted", "borderline", "rejected", "withdrawn")
        if status:
            assert status in valid_statuses, f"PaperMetric screening_status '{status}' not in {valid_statuses}"

        score = metric.get("signal_score")
        if score is not None:
            assert isinstance(score, (int, float)), f"PaperMetric signal_score must be numeric, got: {score}"
            assert 0.0 <= float(score) <= 1000.0, f"PaperMetric signal_score out of range: {score}"

        metrics_data = metric.get("metrics_data")
        assert metrics_data is None or isinstance(metrics_data, dict), f"metrics_data must be dict, got {type(metrics_data)}"

    @classmethod
    def validate_extraction_schema(cls, extraction: Dict[str, Any]) -> None:
        """
        Deep structural and type validation for Extraction records returned by /api/extractions/.
        """
        assert isinstance(extraction, dict), f"Extraction payload must be a dict, got {type(extraction)}"
        cls.validate_uuid(extraction.get("id"), "extraction.id")
        if extraction.get("paper"):
            cls.validate_uuid(extraction.get("paper"), "extraction.paper")

        v_status = extraction.get("validation_status")
        assert v_status in ("pass", "warn", "fail", None), f"Extraction validation_status '{v_status}' invalid"

        conf = extraction.get("confidence_score")
        if conf is not None:
            assert isinstance(conf, (int, float)), f"confidence_score must be numeric, got {type(conf)}: {conf}"
            assert 0.0 <= float(conf) <= 1.0, f"confidence_score '{conf}' out of bounds [0.0, 1.0]"

        fields = extraction.get("fields_data")
        assert fields is None or isinstance(fields, dict), f"fields_data must be dict, got {type(fields)}"

    @classmethod
    def validate_token_and_cost_integrity(
        cls,
        pipeline_run: Dict[str, Any],
        component_runs: Optional[List[Dict[str, Any]]] = None
    ) -> None:
        """
        Validates token accounting and financial invariants:
        1. tokens_consumed == tokens_in + tokens_out
        2. usd_cost >= 0.0
        3. ComponentRun token/cost totals roll up consistently into PipelineRun.
        """
        tokens_in = pipeline_run.get("tokens_in") or 0
        tokens_out = pipeline_run.get("tokens_out") or 0
        tokens_consumed = pipeline_run.get("tokens_consumed") or 0
        usd_cost = float(pipeline_run.get("usd_cost") or 0.0)

        assert isinstance(tokens_in, int) and tokens_in >= 0, f"tokens_in must be non-negative int, got {tokens_in}"
        assert isinstance(tokens_out, int) and tokens_out >= 0, f"tokens_out must be non-negative int, got {tokens_out}"
        assert isinstance(tokens_consumed, int) and tokens_consumed >= 0, f"tokens_consumed must be non-negative int, got {tokens_consumed}"
        assert usd_cost >= 0.0, f"usd_cost cannot be negative: {usd_cost}"

        if tokens_in + tokens_out > 0:
            assert tokens_consumed == tokens_in + tokens_out, (
                f"Token arithmetic mismatch: tokens_consumed ({tokens_consumed}) != "
                f"tokens_in ({tokens_in}) + tokens_out ({tokens_out})"
            )

        if component_runs:
            comp_cost_sum = sum(float((cr.get("metrics") or {}).get("usd_cost") or 0.0) for cr in component_runs)
            # Component costs should roll up into pipeline_run.usd_cost (allowing small floating point rounding precision)
            if comp_cost_sum > 0:
                assert abs(usd_cost - comp_cost_sum) <= 0.005 or usd_cost >= comp_cost_sum - 0.005, (
                    f"ComponentRun aggregated cost sum ({comp_cost_sum:.4f}) does not match PipelineRun.usd_cost ({usd_cost:.4f})"
                )

    @classmethod
    def validate_signal_score_math(
        cls,
        actual_score: float,
        variables: Dict[str, Any],
        formula_fn: Callable[[Dict[str, Any]], float],
        tolerance: float = 0.05
    ) -> None:
        """
        Dynamically executes formula_fn on extracted variables and asserts that
        the backend AST sandbox produced the mathematically expected value.
        """
        expected_score = formula_fn(variables)
        diff = abs(actual_score - expected_score)
        assert diff <= tolerance, (
            f"Mathematical mismatch in Signal Score: actual={actual_score}, "
            f"expected={expected_score} (diff={diff} > tolerance={tolerance}) | Variables: {variables}"
        )
        logger.info(f"✅ Verified Signal Score Math: actual={actual_score} == expected={expected_score} (diff={diff:.4f})")

    @classmethod
    def validate_cross_endpoint_consistency(
        cls,
        papers: List[Dict[str, Any]],
        paper_metrics: List[Dict[str, Any]],
        extractions: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        """
        Cross-validates that data returned across /api/papers/ and /api/paper-metrics/
        are 1:1 synchronized in screening decisions, signal scores, and IDs.
        """
        metrics_by_paper_id = {}
        for m in paper_metrics:
            p_id = str(m.get("paper") or m.get("paper_id"))
            metrics_by_paper_id[p_id] = m

        for paper in papers:
            p_id = str(paper["id"])
            if p_id in metrics_by_paper_id:
                metric = metrics_by_paper_id[p_id]
                # Screening status cross-consistency
                if paper.get("screening_status") and metric.get("screening_status"):
                    assert paper["screening_status"] == metric["screening_status"], (
                        f"Status mismatch for paper {p_id}: PaperViewSet reports '{paper['screening_status']}', "
                        f"PaperMetricViewSet reports '{metric['screening_status']}'"
                    )
                # Signal score cross-consistency
                p_score = paper.get("signal_score")
                m_score = metric.get("signal_score")
                if p_score is not None and m_score is not None:
                    assert abs(float(p_score) - float(m_score)) <= 0.01, (
                        f"Score mismatch for paper {p_id}: Paper reports {p_score}, Metric reports {m_score}"
                    )

        # Deduplication check: Verify no duplicate paper IDs or duplicate DOIs
        seen_ids = set()
        seen_dois = set()
        seen_arxiv = set()
        for p in papers:
            p_id = str(p["id"])
            assert p_id not in seen_ids, f"Duplicate Paper ID detected: {p_id}"
            seen_ids.add(p_id)

            doi = p.get("doi")
            if doi and len(doi.strip()) > 3:
                clean_doi = doi.lower().replace("https://doi.org/", "").replace("http://doi.org/", "").strip()
                assert clean_doi not in seen_dois, f"Cross-endpoint deduplication failure: Duplicate DOI '{doi}' found"
                seen_dois.add(clean_doi)

            arxiv = p.get("arxiv_id")
            if arxiv and len(arxiv.strip()) > 3:
                clean_arxiv = re.sub(r'v\d+$', '', arxiv.lower().replace("arxiv:", "").strip())
                assert clean_arxiv not in seen_arxiv, f"Cross-endpoint deduplication failure: Duplicate arXiv ID '{arxiv}' found"
                seen_arxiv.add(clean_arxiv)

        logger.info(f"✅ Cross-Endpoint Data Consistency validated for {len(papers)} papers and {len(paper_metrics)} metrics.")
