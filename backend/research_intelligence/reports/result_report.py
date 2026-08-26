import logging
from typing import Dict, Any, Optional
from research_intelligence.tasks.auxiliary.email_digest import build_pipeline_run_digest_payload
from .base import BaseSubscriptionReporter

logger = logging.getLogger(__name__)



class ResultReportReporter(BaseSubscriptionReporter):
    """
    Generates executive findings, accepted paper scorecards, and parameter extraction matrices
    for completed pipeline runs.
    """
    subscription_type = "result_report"
    display_name = "Result Report"
    description = "Executive scorecard and dynamic parameter extraction matrix for accepted papers."
    template_name = "emails/pipeline_digest"

    def build_payload(
        self,
        workspace: Any,
        pipeline_run: Optional[Any] = None,
        agent_process: Optional[Any] = None,
        error_context: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        # Delegate to unified SLR digest payload builder
        payload = build_pipeline_run_digest_payload(
            pipeline_run=pipeline_run,
            agent_process=agent_process
        )
        # Ensure workspace context if pipeline_run was None
        if not payload["context"].get("workspace") and workspace:
            payload["context"]["workspace"] = workspace
            payload["context"]["workspace_name"] = workspace.name

        # Ensure stats has standard summary keys for testing / audit
        payload["stats"]["accepted_papers_count"] = payload["context"]["accepted_count"]
        payload["stats"]["rejected_papers_count"] = payload["context"]["rejected_count"]
        payload["stats"]["total_cost_usd"] = payload["context"]["cost_usd"]
        payload["stats"]["avg_signal_score"] = float(payload["context"]["avg_signal_score"]) if payload["context"].get("avg_signal_score") else None
        payload["stats"]["top_signal_score"] = float(payload["context"]["top_signal_score"]) if payload["context"].get("top_signal_score") else None
        payload["template_name"] = self.template_name

        return payload

