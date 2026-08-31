"""
Core Telemetry & Observability Engine.

Collects, aggregates, and exports platform-wide operational telemetry,
AI token burn rates, pipeline funnel conversion rates, component execution latencies,
and global document cache savings in standard Prometheus Exposition format and JSON.
"""

import time
from typing import Dict, Any, List
from django.db.models import Avg, Min, Max, Sum, Count, Q
from django.utils import timezone

from research_intelligence.models import (
    Workspace,
    Paper,
    PipelineRun,
    ComponentRun,
    ResearchAgentProcess,
    Extraction,
    DocumentRegistry,
    UserActivityLog,
)
from chat.models import PaperChatSession, PaperChatMessage


def collect_telemetry_snapshot() -> Dict[str, Any]:
    """
    Computes an atomic, comprehensive telemetry snapshot of system-wide performance,
    costs, latencies, funnel yields, and efficiency metrics.
    """
    now = timezone.now()

    # --------------------------------------------------------------------------
    # 1. Paper Funnel & Conversion Rates
    # --------------------------------------------------------------------------
    total_papers = Paper.objects.count()
    status_counts = dict(Paper.objects.values('screening_status').annotate(count=Count('id')).values_list('screening_status', 'count'))
    provider_counts = dict(Paper.objects.values('source_database').annotate(count=Count('id')).values_list('source_database', 'count'))

    accepted_count = status_counts.get('accepted', 0)
    full_text_passed = status_counts.get('full_text_passed', 0)
    abstract_passed = status_counts.get('abstract_passed', 0)
    rejected_count = status_counts.get('rejected', 0)
    withdrawn_count = status_counts.get('withdrawn', 0)
    pending_count = status_counts.get('pending', 0)

    total_passed_abstract = accepted_count + full_text_passed + abstract_passed
    total_screened = total_passed_abstract + rejected_count

    abstract_conversion_pct = round((total_passed_abstract / total_screened * 100), 2) if total_screened > 0 else 0.0
    full_text_conversion_pct = round((accepted_count / (accepted_count + full_text_passed + rejected_count) * 100), 2) if (accepted_count + full_text_passed + rejected_count) > 0 else 0.0
    end_to_end_yield_pct = round((accepted_count / total_papers * 100), 2) if total_papers > 0 else 0.0

    # --------------------------------------------------------------------------
    # 2. Token Economics & Cost Distribution
    # --------------------------------------------------------------------------
    pipeline_cost_agg = PipelineRun.objects.aggregate(
        total_usd=Sum('usd_cost'),
        avg_usd=Avg('usd_cost'),
        min_usd=Min('usd_cost'),
        max_usd=Max('usd_cost'),
        total_tokens_in=Sum('tokens_in'),
        total_tokens_out=Sum('tokens_out'),
        total_tokens=Sum('tokens_consumed'),
        total_runs=Count('id')
    )

    chat_cost_agg = PaperChatMessage.objects.aggregate(
        total_usd=Sum('usd_cost'),
        avg_usd=Avg('usd_cost'),
        total_tokens_in=Sum('tokens_in'),
        total_tokens_out=Sum('tokens_out'),
        total_tokens=Sum('total_tokens'),
        total_messages=Count('id')
    )

    pipeline_usd = float(pipeline_cost_agg.get('total_usd') or 0.0)
    chat_usd = float(chat_cost_agg.get('total_usd') or 0.0)
    total_platform_usd = round(pipeline_usd + chat_usd, 4)

    total_prompt_tokens = int((pipeline_cost_agg.get('total_tokens_in') or 0) + (chat_cost_agg.get('total_tokens_in') or 0))
    total_completion_tokens = int((pipeline_cost_agg.get('total_tokens_out') or 0) + (chat_cost_agg.get('total_tokens_out') or 0))
    total_tokens_consumed = total_prompt_tokens + total_completion_tokens

    cost_per_accepted_paper_avg = round((total_platform_usd / accepted_count), 4) if accepted_count > 0 else 0.0
    cost_per_run_avg = round(float(pipeline_cost_agg.get('avg_usd') or 0.0), 4)
    cost_per_run_min = round(float(pipeline_cost_agg.get('min_usd') or 0.0), 4)
    cost_per_run_max = round(float(pipeline_cost_agg.get('max_usd') or 0.0), 4)

    # --------------------------------------------------------------------------
    # 3. Execution Latencies & Timings (Per Component Step)
    # --------------------------------------------------------------------------
    component_stats = {}
    component_types = ['search', 'download', 'ocr', 'screening', 'extraction', 'signal_score', 'reporting']

    for step in component_types:
        qs = ComponentRun.objects.filter(step_type=step, status='completed', started_at__isnull=False, completed_at__isnull=False)
        total_count = qs.count()
        if total_count > 0:
            durations = []
            for cr in qs[:200]:
                if cr.duration_seconds is not None:
                    durations.append(cr.duration_seconds)
            if durations:
                durations.sort()
                avg_sec = round(sum(durations) / len(durations), 2)
                min_sec = round(durations[0], 2)
                max_sec = round(durations[-1], 2)
                p95_idx = int(len(durations) * 0.95)
                p95_sec = round(durations[min(p95_idx, len(durations) - 1)], 2)
            else:
                avg_sec, min_sec, max_sec, p95_sec = 0.0, 0.0, 0.0, 0.0
        else:
            total_count, avg_sec, min_sec, max_sec, p95_sec = 0, 0.0, 0.0, 0.0, 0.0

        component_stats[step] = {
            "count": total_count,
            "avg_seconds": avg_sec,
            "min_seconds": min_sec,
            "max_seconds": max_sec,
            "p95_seconds": p95_sec,
        }

    # Pipeline total duration
    completed_runs = PipelineRun.objects.filter(status='completed', started_at__isnull=False, completed_at__isnull=False)
    run_durations = [r.duration_seconds for r in completed_runs if r.duration_seconds is not None]
    if run_durations:
        run_durations.sort()
        run_duration_avg = round(sum(run_durations) / len(run_durations), 2)
        run_duration_min = round(run_durations[0], 2)
        run_duration_max = round(run_durations[-1], 2)
    else:
        run_duration_avg, run_duration_min, run_duration_max = 0.0, 0.0, 0.0

    # --------------------------------------------------------------------------
    # 4. Global DocumentRegistry Cache Savings
    # --------------------------------------------------------------------------
    doc_reg_agg = DocumentRegistry.objects.aggregate(
        total_docs=Count('id'),
        total_bytes=Sum('pdf_file_size_bytes'),
        total_hits=Sum('access_count')
    )
    cached_docs_count = doc_reg_agg.get('total_docs') or 0
    total_stored_bytes = doc_reg_agg.get('total_bytes') or 0
    total_accesses = doc_reg_agg.get('total_hits') or 0
    cache_hits = max(0, total_accesses - cached_docs_count)
    bandwidth_saved_bytes = cache_hits * (total_stored_bytes / cached_docs_count) if cached_docs_count > 0 else 0

    # --------------------------------------------------------------------------
    # 5. Workspaces & Agent Process Fleet
    # --------------------------------------------------------------------------
    active_workspaces = Workspace.objects.count()
    agent_status_counts = dict(ResearchAgentProcess.objects.values('status').annotate(count=Count('id')).values_list('status', 'count'))

    extractions_count = Extraction.objects.count()
    extractions_validated = Extraction.objects.filter(is_hitl_validated=True).count()

    chat_sessions_count = PaperChatSession.objects.count()
    activity_logs_count = UserActivityLog.objects.count()

    return {
        "timestamp": now.isoformat(),
        "funnel": {
            "total_papers": total_papers,
            "status_breakdown": {
                "pending": pending_count,
                "abstract_passed": abstract_passed,
                "full_text_passed": full_text_passed,
                "accepted": accepted_count,
                "rejected": rejected_count,
                "withdrawn": withdrawn_count,
            },
            "provider_breakdown": provider_counts,
            "conversion_rates": {
                "abstract_pass_pct": abstract_conversion_pct,
                "full_text_pass_pct": full_text_conversion_pct,
                "end_to_end_yield_pct": end_to_end_yield_pct,
            }
        },
        "economics": {
            "total_platform_usd": total_platform_usd,
            "pipeline_usd": pipeline_usd,
            "chat_usd": chat_usd,
            "tokens": {
                "prompt_tokens_total": total_prompt_tokens,
                "completion_tokens_total": total_completion_tokens,
                "tokens_consumed_total": total_tokens_consumed,
            },
            "per_paper_metrics": {
                "cost_per_accepted_paper_avg_usd": cost_per_accepted_paper_avg,
            },
            "per_run_metrics": {
                "cost_per_run_avg_usd": cost_per_run_avg,
                "cost_per_run_min_usd": cost_per_run_min,
                "cost_per_run_max_usd": cost_per_run_max,
            }
        },
        "latencies": {
            "components": component_stats,
            "pipeline_runs": {
                "total_completed_runs": len(run_durations),
                "duration_avg_seconds": run_duration_avg,
                "duration_min_seconds": run_duration_min,
                "duration_max_seconds": run_duration_max,
            }
        },
        "cache_efficiency": {
            "cached_documents_count": cached_docs_count,
            "total_stored_bytes": total_stored_bytes,
            "cache_hits_total": cache_hits,
            "bandwidth_saved_bytes": int(bandwidth_saved_bytes),
            "bandwidth_saved_mb": round(bandwidth_saved_bytes / (1024 * 1024), 2),
        },
        "fleet_health": {
            "active_workspaces": active_workspaces,
            "agent_processes": agent_status_counts,
            "extractions_total": extractions_count,
            "extractions_validated": extractions_validated,
            "chat_sessions_total": chat_sessions_count,
            "chat_messages_total": chat_cost_agg.get('total_messages') or 0,
            "audit_logs_total": activity_logs_count,
        }
    }


def generate_prometheus_metrics_text() -> str:
    """
    Renders Prometheus Exposition Text Format (v0.0.4) for scraping by Prometheus / Datadog / Grafana.
    """
    snapshot = collect_telemetry_snapshot()
    lines: List[str] = []

    def _help(name: str, desc: str, mtype: str = "gauge"):
        lines.append(f"# HELP {name} {desc}")
        lines.append(f"# TYPE {name} {mtype}")

    # 1. Funnel & Paper Metrics
    _help("sri_papers_total", "Total count of papers in system by screening status", "gauge")
    for st, cnt in snapshot["funnel"]["status_breakdown"].items():
        lines.append(f'sri_papers_total{{status="{st}"}} {cnt}')

    _help("sri_papers_ingested_total", "Total count of ingested papers by data provider", "gauge")
    for prov, cnt in snapshot["funnel"]["provider_breakdown"].items():
        prov_name = prov or "unknown"
        lines.append(f'sri_papers_ingested_total{{provider="{prov_name}"}} {cnt}')

    _help("sri_pipeline_conversion_rate_ratio", "Funnel conversion rates between pipeline stages", "gauge")
    lines.append(f'sri_pipeline_conversion_rate_ratio{{stage="abstract_pass"}} {snapshot["funnel"]["conversion_rates"]["abstract_pass_pct"] / 100:.4f}')
    lines.append(f'sri_pipeline_conversion_rate_ratio{{stage="full_text_pass"}} {snapshot["funnel"]["conversion_rates"]["full_text_pass_pct"] / 100:.4f}')
    lines.append(f'sri_pipeline_conversion_rate_ratio{{stage="end_to_end_yield"}} {snapshot["funnel"]["conversion_rates"]["end_to_end_yield_pct"] / 100:.4f}')

    # 2. Token & Cost Economics
    _help("sri_llm_cost_usd_total", "Cumulative platform LLM inference cost in USD", "counter")
    lines.append(f'sri_llm_cost_usd_total{{subsystem="pipeline"}} {snapshot["economics"]["pipeline_usd"]:.4f}')
    lines.append(f'sri_llm_cost_usd_total{{subsystem="chat"}} {snapshot["economics"]["chat_usd"]:.4f}')
    lines.append(f'sri_llm_cost_usd_total{{subsystem="total"}} {snapshot["economics"]["total_platform_usd"]:.4f}')

    _help("sri_llm_tokens_total", "Total prompt and completion tokens consumed across platform", "counter")
    lines.append(f'sri_llm_tokens_total{{type="prompt"}} {snapshot["economics"]["tokens"]["prompt_tokens_total"]}')
    lines.append(f'sri_llm_tokens_total{{type="completion"}} {snapshot["economics"]["tokens"]["completion_tokens_total"]}')
    lines.append(f'sri_llm_tokens_total{{type="total"}} {snapshot["economics"]["tokens"]["tokens_consumed_total"]}')

    _help("sri_cost_per_paper_usd", "Average LLM cost in USD per accepted paper", "gauge")
    lines.append(f'sri_cost_per_paper_usd{{stat="avg"}} {snapshot["economics"]["per_paper_metrics"]["cost_per_accepted_paper_avg_usd"]:.4f}')

    _help("sri_cost_per_run_usd", "Cost distribution in USD per SLR pipeline execution", "gauge")
    lines.append(f'sri_cost_per_run_usd{{stat="avg"}} {snapshot["economics"]["per_run_metrics"]["cost_per_run_avg_usd"]:.4f}')
    lines.append(f'sri_cost_per_run_usd{{stat="min"}} {snapshot["economics"]["per_run_metrics"]["cost_per_run_min_usd"]:.4f}')
    lines.append(f'sri_cost_per_run_usd{{stat="max"}} {snapshot["economics"]["per_run_metrics"]["cost_per_run_max_usd"]:.4f}')

    # 3. Component Latencies
    _help("sri_component_duration_seconds", "Component task execution latency in seconds", "gauge")
    for comp, stats in snapshot["latencies"]["components"].items():
        lines.append(f'sri_component_duration_seconds{{component="{comp}",stat="avg"}} {stats["avg_seconds"]}')
        lines.append(f'sri_component_duration_seconds{{component="{comp}",stat="p95"}} {stats["p95_seconds"]}')
        lines.append(f'sri_component_duration_seconds{{component="{comp}",stat="max"}} {stats["max_seconds"]}')

    _help("sri_pipeline_run_duration_seconds", "Full end-to-end SLR pipeline execution duration in seconds", "gauge")
    lines.append(f'sri_pipeline_run_duration_seconds{{stat="avg"}} {snapshot["latencies"]["pipeline_runs"]["duration_avg_seconds"]}')
    lines.append(f'sri_pipeline_run_duration_seconds{{stat="max"}} {snapshot["latencies"]["pipeline_runs"]["duration_max_seconds"]}')

    # 4. Cache & Efficiency
    _help("sri_document_registry_items_total", "Total unique documents registered in global content-addressable cache", "gauge")
    lines.append(f'sri_document_registry_items_total {snapshot["cache_efficiency"]["cached_documents_count"]}')

    _help("sri_document_registry_cache_hits_total", "Total deduplication cache hits across workspaces", "counter")
    lines.append(f'sri_document_registry_cache_hits_total {snapshot["cache_efficiency"]["cache_hits_total"]}')

    _help("sri_document_registry_bandwidth_saved_bytes_total", "Total network download bandwidth saved in bytes through deduplication", "counter")
    lines.append(f'sri_document_registry_bandwidth_saved_bytes_total {snapshot["cache_efficiency"]["bandwidth_saved_bytes"]}')

    # 5. Fleet & Operational Health
    _help("sri_workspaces_active_total", "Total configured workspaces", "gauge")
    lines.append(f'sri_workspaces_active_total {snapshot["fleet_health"]["active_workspaces"]}')

    _help("sri_agent_processes_total", "Research Agent processes by state", "gauge")
    for st in ["running", "paused", "completed", "failed", "aborted", "pending"]:
        cnt = snapshot["fleet_health"]["agent_processes"].get(st, 0)
        lines.append(f'sri_agent_processes_total{{status="{st}"}} {cnt}')

    _help("sri_extractions_total", "Total parameter extractions and validation counts", "gauge")
    lines.append(f'sri_extractions_total{{status="all"}} {snapshot["fleet_health"]["extractions_total"]}')
    lines.append(f'sri_extractions_total{{status="hitl_validated"}} {snapshot["fleet_health"]["extractions_validated"]}')

    _help("sri_chat_sessions_total", "Total interactive paper chat sessions", "gauge")
    lines.append(f'sri_chat_sessions_total {snapshot["fleet_health"]["chat_sessions_total"]}')

    _help("sri_audit_logs_total", "Total operational audit trail entries recorded", "counter")
    lines.append(f'sri_audit_logs_total {snapshot["fleet_health"]["audit_logs_total"]}')

    lines.append("") # Trailing newline required by Prometheus exposition format
    return "\n".join(lines)
