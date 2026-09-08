import logging
from typing import Dict, Any, Optional, List, Type
from django.db import close_old_connections
from .base import BaseSubscriptionReporter
from .result_report import ResultReportReporter
from .pipeline_errors import PipelineErrorsReporter
from .pipeline_status import PipelineStatusReporter
from research_intelligence.utils.mailer import send_mailgun_message

logger = logging.getLogger(__name__)


class SubscriptionReporterRegistry:
    """
    Central registry and dispatcher for all subscription report generators.
    Allows easy extension with new report types without modifying pipeline core logic.
    """
    def __init__(self):
        self._reporters: Dict[str, BaseSubscriptionReporter] = {}
        # Register core reporters
        self.register(ResultReportReporter())
        self.register(PipelineErrorsReporter())
        self.register(PipelineStatusReporter())

    def register(self, reporter: BaseSubscriptionReporter):
        self._reporters[reporter.subscription_type] = reporter

    def get_reporter(self, subscription_type: str) -> BaseSubscriptionReporter:
        return self._reporters.get(subscription_type, self._reporters.get("result_report", ResultReportReporter()))

    def list_available_types(self) -> List[Dict[str, str]]:
        return [
            {
                "type": rep.subscription_type,
                "name": rep.display_name,
                "description": rep.description,
                "template": rep.get_template_name(),
            }
            for rep in self._reporters.values()
        ]

    def dispatch_report(
        self,
        workspace: Any,
        event_type: str,
        pipeline_run: Optional[Any] = None,
        agent_process: Optional[Any] = None,
        error_context: Optional[Dict[str, Any]] = None,
        recipient_override: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Dispatches targeted reports to workspace subscribers based on their subscription preferences.
        Subscribers matching `subscription_type == event_type` or `subscription_type == 'all'`
        will receive the generated report.
        """
        close_old_connections()
        if not workspace:
            return {"status": "error", "error": "Workspace is required for dispatch."}

        from research_intelligence.features import is_feature_enabled, Feature

        if not is_feature_enabled(Feature.EMAIL_NOTIFICATIONS):
            logger.info(f"📧 [REPORT DISPATCH SKIPPED] Feature EMAIL_NOTIFICATIONS is disabled for Workspace '{workspace.name}'.")
            return {
                "status": "skipped",
                "reason": "Email notifications feature disabled",
                "event_type": event_type,
                "workspace_id": str(workspace.id),
                "workspace_name": workspace.name,
                "pipeline_run_id": str(pipeline_run.id) if pipeline_run else None,
                "total_recipients": 0,
                "sent_count": 0,
                "failed_count": 0,
                "deliveries": [],
            }

        # 1. Resolve recipients
        recipient_emails = []
        if recipient_override and isinstance(recipient_override, list):
            recipient_emails = [e.strip() for e in recipient_override if e and "@" in e]
        else:
            matching_subs = workspace.subscribers.filter(
                is_active=True,
                subscription_type__in=[event_type, 'all']
            )
            recipient_emails = [s.email.strip() for s in matching_subs if s.email]

        if not recipient_emails:
            return {
                "status": "no_subscribers",
                "message": f"No active subscribers found for workspace '{workspace.name}' matching event '{event_type}'.",
                "event_type": event_type,
                "workspace_id": str(workspace.id),
                "sent_count": 0,
                "failed_count": 0,
                "recipients": []
            }

        # 2. Build domain-specific payload using the registered reporter
        reporter = self.get_reporter(event_type)
        payload = reporter.build_payload(
            workspace=workspace,
            pipeline_run=pipeline_run,
            agent_process=agent_process,
            error_context=error_context
        )

        subject = payload["subject"]
        context = payload["context"]
        template_name = payload.get("template_name", reporter.get_template_name())

        sent_count = 0
        failed_count = 0
        delivery_results = []

        for email in recipient_emails:
            try:
                success, resp_or_err = send_mailgun_message(
                    to_email=email,
                    subject=subject,
                    template_name=template_name,
                    context=context,
                )
            except Exception as exc:
                success = False
                resp_or_err = str(exc)

            if success:
                sent_count += 1
                delivery_results.append({"email": email, "status": "sent", "response": resp_or_err})
                logger.info(f"📧 [{event_type.upper()} EMAIL SENT] Workspace '{workspace.name}' -> {email}")
            else:
                failed_count += 1
                delivery_results.append({"email": email, "status": "failed", "error": str(resp_or_err)})
                logger.error(f"❌ [{event_type.upper()} EMAIL FAILED] Workspace '{workspace.name}' -> {email}: {resp_or_err}")


        return {
            "status": "success" if sent_count > 0 else "failed",
            "event_type": event_type,
            "workspace_id": str(workspace.id),
            "workspace_name": workspace.name,
            "pipeline_run_id": str(pipeline_run.id) if pipeline_run else None,
            "total_recipients": len(recipient_emails),
            "sent_count": sent_count,
            "failed_count": failed_count,
            "stats": payload.get("stats", {}),
            "deliveries": delivery_results,
        }


# Global registry singleton
reporter_registry = SubscriptionReporterRegistry()
