"""
Run admission: how many pipeline runs a workspace may have in flight, and
whether a new one duplicates a run that is already in flight.

Every path that creates an in-flight PipelineRun (REST start, MCP start,
research agent start, bare create, the scheduler) calls admit_run() inside
a transaction so concurrent starts for one workspace serialise on the
Workspace row and the count cannot be exceeded by a race.
"""
import logging
from typing import Any, Dict, Optional, Tuple

from django.conf import settings
from django.db import connection, transaction

from research_intelligence.models import PipelineRun, Workspace

logger = logging.getLogger(__name__)

DEFAULT_MAX_CONCURRENT_RUNS_PER_WORKSPACE = 5

# A paused run keeps its slot: resume() never has to re-admit it.
IN_FLIGHT_STATUSES = ('pending', 'running', 'paused')

CODE_RUN_LIMIT_REACHED = 'run_limit_reached'
CODE_DUPLICATE_RUN = 'duplicate_run'
ADMISSION_CODES = (CODE_RUN_LIMIT_REACHED, CODE_DUPLICATE_RUN)


def max_concurrent_runs() -> int:
    """Per-workspace cap, from settings so tests can override_settings it."""
    return int(getattr(settings, 'MAX_CONCURRENT_RUNS_PER_WORKSPACE', DEFAULT_MAX_CONCURRENT_RUNS_PER_WORKSPACE))


class RunAdmissionRefused(Exception):
    """A start was refused because the workspace is at its cap or the window is already running."""

    def __init__(self, code: str, message: str, payload: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.payload = payload or {}

    def as_error_json(self) -> Dict[str, Any]:
        """The MCP error envelope, with `code` so views can answer 409."""
        return {"status": "error", "code": self.code, "error": self.message, **self.payload}


def search_window(config_override: Optional[Dict[str, Any]]) -> Tuple[Optional[str], Optional[str], Optional[int]]:
    """
    The search window a run was started with, normalised so two runs compare:
    (start_date, end_date, n_last_days). Dates are cut to YYYY-MM-DD; the
    lookback only counts when no explicit date was given (explicit dates
    override it in the scrapers, so a run with dates ignores n_last_days).
    """
    cfg = config_override or {}

    def day(value: Any) -> Optional[str]:
        text = str(value or '').strip()[:10]
        return text or None

    start = day(cfg.get('start_date'))
    end = day(cfg.get('end_date'))
    if start or end:
        return start, end, None
    lookback = cfg.get('n_last_days')
    try:
        return None, None, int(lookback) if lookback is not None else None
    except (TypeError, ValueError):
        return None, None, None


def in_flight_runs(workspace) -> Any:
    return PipelineRun.objects.filter(workspace=workspace, status__in=IN_FLIGHT_STATUSES)


def admit_run(workspace_id, config_override: Optional[Dict[str, Any]], check_window: bool = True) -> Workspace:
    """
    Lock the workspace, count its in-flight runs and refuse a start that would
    exceed the cap or duplicate an in-flight run's search window. Returns the
    locked Workspace so the caller creates the run in the same transaction.

    Must run inside transaction.atomic(): the row lock is what serialises two
    starts racing for the last slot. On SQLite (tests) select_for_update is a
    no-op, so the race is only proven against Postgres.
    """
    if not connection.in_atomic_block:
        raise RuntimeError("admit_run() must be called inside transaction.atomic()")

    qs = Workspace.objects.filter(pk=workspace_id)
    if connection.vendor == 'postgresql':
        qs = qs.select_for_update()
    workspace = qs.get()

    limit = max_concurrent_runs()
    in_flight = in_flight_runs(workspace)
    count = in_flight.count()
    base_payload = {
        "workspace_id": str(workspace.id),
        "workspace_name": workspace.name,
        "in_flight": count,
        "limit": limit,
    }
    if count >= limit:
        raise RunAdmissionRefused(
            CODE_RUN_LIMIT_REACHED,
            f"{count} of {limit} runs in progress for {workspace.name}. Wait for one to finish.",
            base_payload,
        )

    # A run whose window is unknown (bare create, legacy rows without a
    # configuration_override) cannot be said to duplicate anything.
    window = search_window(config_override)
    if check_window and window != (None, None, None):
        for run_id, existing_cfg in in_flight.values_list('id', 'configuration_override'):
            if search_window(existing_cfg) == window:
                raise RunAdmissionRefused(
                    CODE_DUPLICATE_RUN,
                    f"{workspace.name} is already running this search window.",
                    {**base_payload, "conflicting_run_id": str(run_id)},
                )

    return workspace


def is_admission_error(res_data: Any) -> bool:
    """True for an MCP error envelope produced by RunAdmissionRefused."""
    return isinstance(res_data, dict) and res_data.get("code") in ADMISSION_CODES
