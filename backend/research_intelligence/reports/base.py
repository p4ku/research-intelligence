from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
import logging

logger = logging.getLogger(__name__)


class BaseSubscriptionReporter(ABC):
    """
    Abstract Base Class for all subscription report generators and email templates.
    Enforces standardized contract for gathering context data, subject generation,
    and responsive HTML/text email rendering.
    """
    subscription_type: str = "base"
    display_name: str = "Base Report"
    description: str = "Base subscription notification generator"
    template_name: str = "emails/pipeline_digest"

    @abstractmethod
    def build_payload(
        self,
        workspace: Any,
        pipeline_run: Optional[Any] = None,
        agent_process: Optional[Any] = None,
        error_context: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Gathers domain-specific metrics, records, and context required for rendering.
        Must return a dict containing at minimum:
        {
            'subject': str,
            'context': dict,
            'stats': dict,
            'template_name': str
        }
        """
        pass

    def get_template_name(self) -> str:
        return self.template_name
