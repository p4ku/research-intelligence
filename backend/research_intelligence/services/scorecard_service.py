import re
import uuid

from django.core.paginator import Paginator
from django.db.models import Q

from api.serializers.papers import PaperSerializer
from research_intelligence.models import (
    Extraction,
    ExtractionDefinition,
    NarrativeReport,
    Paper,
    PipelineRun,
)
from .scorecard_extractors import (
    extract_metrics_for_extraction,
    extract_rich_dimension_details,
    extract_risk_and_affiliation,
    is_risk_dimension,
)


def resolve_dimension_scale(name: str = "") -> tuple[int, bool]:
    """
    Shared helper to determine maximum numeric scale and TRL classification (~2 lines, no schema change).
    Ensures WorkspaceSummary.definitions and Paper.dimensions are always 100% in agreement.
    """
    is_trl = bool(re.search(r'\btrl\b', name or '', re.IGNORECASE))
    if is_trl:
        return 9, True
    if re.search(r'\(1-10\)', name or ''):
        return 10, False
    return 100, False


def format_definitions_metadata(definitions: list) -> list:
    """Formats extraction definitions into metadata dictionaries for the scorecard payload."""
    definitions_data = []
    for d in definitions:
        has_post = bool(d.postprocessing_code and d.postprocessing_code.strip())
        exit_list = d.get_exit_metrics_list()
        prim_exit = d.get_primary_exit_metric()
        d_slug = d.name.lower().replace(' ', '_').replace('-', '_')
        max_val, is_trl = resolve_dimension_scale(d.name)
        has_explicit = bool(d.has_explicit_frontend_metrics())

        if has_explicit:
            main_key = d.get_primary_frontend_metric()
            aux_keys = d.get_secondary_frontend_metrics_list()
        elif has_post:
            main_key = f"{d_slug}_postprocessed"
            aux_keys = exit_list
        else:
            main_key = exit_list[0] if exit_list else prim_exit
            aux_keys = exit_list[1:] if len(exit_list) > 1 else []

        created_str = None
        if hasattr(d, 'created_at') and d.created_at:
            dt = d.created_at
            created_str = dt.isoformat() if (hasattr(dt, 'tzinfo') and dt.tzinfo) else (dt.isoformat() + "Z")

        definitions_data.append({
            'id': str(d.id),
            'name': d.name,
            'key': d_slug,
            'category': d.name,
            'response_schema': d.response_schema,
            'exit_metrics': exit_list,
            'primary_exit_metric': prim_exit,
            'primary_frontend_metric': d.primary_frontend_metric or None,
            'secondary_frontend_metrics': d.get_secondary_frontend_metrics_list(),
            'has_postprocessing': has_post,
            'postprocessing_code': d.postprocessing_code or None,
            'primary_metric_key': main_key,
            'main_metric_key': main_key,
            'secondary_metric_keys': aux_keys,
            'auxiliary_metric_keys': aux_keys,
            'llm_model': d.llm_model,
            'is_active': bool(d.is_active),
            'is_trl': is_trl,
            'is_risk_and_affiliation': is_risk_dimension(d.name, d_slug),
            'max': max_val,
            'scale_max': max_val,
            'created_at': created_str,
        })
    return definitions_data


def format_workspace_summary(workspace, definitions_data: list = None, request=None) -> dict:
    """Formats full WorkspaceSummary matching frontend contract (WorkspaceSummary)."""
    if definitions_data is None:
        definitions_data = []
    scrapers = []
    if hasattr(workspace, 'scrapers'):
        for s in workspace.scrapers.all():
            scrapers.append({
                'id': str(s.id),
                'provider': s.provider,
                'search_query': s.search_query,
                'is_active': bool(s.is_active),
            })

    user_role = None
    if request and getattr(request, 'user', None) and request.user.is_authenticated:
        from research_intelligence.models import WorkspaceMember
        member = WorkspaceMember.objects.filter(workspace=workspace, user=request.user).first()
        if member:
            user_role = member.role

    created_at_str = ""
    if hasattr(workspace, 'created_at') and workspace.created_at:
        dt = workspace.created_at
        created_at_str = dt.isoformat() if (hasattr(dt, 'tzinfo') and dt.tzinfo) else (dt.isoformat() + "Z")

    return {
        'id': str(workspace.id),
        'name': workspace.name,
        'user_role': user_role,
        'definitions': definitions_data,
        'scrapers': scrapers,
        'scrapers_count': len(scrapers),
        'digest_schedule': getattr(workspace, 'digest_schedule', None) or None,
        'screening_llm_model': getattr(workspace, 'screening_llm_model', None) or None,
        'llm_provider': getattr(workspace, 'llm_provider', None) or None,
        'created_at': created_at_str,
    }


def resolve_paper_representing_metric(metrics, target_pr_id=None):
    """
    Selects the canonical PaperMetric representing a paper.
    If target_pr_id is provided, selects the metric for that run.
    If unscoped (target_pr_id is None), prefers evaluated metrics
    (screening_status != 'pending' or signal_score is not None), sorted newest first,
    preventing an in-flight rerun from masking completed scores.
    """
    if not metrics:
        return None

    metrics_list = list(metrics)
    if target_pr_id:
        norm_target_pr = str(target_pr_id)
        for m in metrics_list:
            if str(m.pipeline_run_id) == norm_target_pr:
                return m
        return None

    # Unscoped: prefer evaluated metrics over pending reruns
    evaluated = [
        m for m in metrics_list
        if (getattr(m, 'screening_status', None) not in ('pending', None) or getattr(m, 'signal_score', None) is not None)
    ]
    pool = evaluated if evaluated else metrics_list

    def _metric_sort_key(m):
        dt = getattr(m, 'created_at', None)
        ts = dt.timestamp() if (dt and hasattr(dt, 'timestamp')) else 0.0
        return (ts, str(getattr(m, 'id', '')))

    return sorted(pool, key=_metric_sort_key, reverse=True)[0]


def build_single_scored_paper(
    paper: Paper,
    definitions: list,
    target_pr_id=None,
    target_pr=None,
    metrics_list: list = None,
    extractions_list: list = None,
    paper_data: dict = None,
    request=None,
) -> dict:
    """
    Builds the dictionary representation of a single ScoredPaper matching frontend schema.
    """
    if metrics_list is None:
        metrics_list = list(paper.metrics.all())
    if extractions_list is None:
        extractions_list = list(paper.extractions.all())

    # 1. Resolve target_metric
    target_metric = resolve_paper_representing_metric(metrics_list, target_pr_id=target_pr_id)

    if not target_pr_id and target_metric and target_metric.pipeline_run_id:
        target_pr_id = target_metric.pipeline_run_id
        target_pr = target_metric.pipeline_run
    if not target_pr_id and getattr(paper, 'pipeline_run_id', None):
        target_pr_id = paper.pipeline_run_id
        target_pr = getattr(paper, 'pipeline_run', None)

    raw_authors = paper.authors or ''
    authors_list = [a.strip() for a in raw_authors.split(',') if a.strip()] if raw_authors else []

    # Format signal_score_details
    ssd = (
        target_metric.signal_score_details
        if (target_metric and target_metric.signal_score_details)
        else (paper_data.get('signal_score_details') if paper_data else None)
    )
    formatted_ssd = None
    if isinstance(ssd, dict) and ssd:
        formatted_ssd = {
            'variables': ssd.get('variables') if isinstance(ssd.get('variables'), dict) else {},
            'code_snippet': ssd.get('code_snippet') or None,
            'calculated_at': ssd.get('calculated_at') or None,
            'error': ssd.get('error') or None,
        }

    # 2. Risk and affiliation
    risk_and_affiliation_info = None
    for e in extractions_list:
        d_obj = getattr(e, 'extraction_definition', None)
        cat = d_obj.name if d_obj else (e.category or '')
        dim_key = cat.lower().replace(' ', '_')
        is_risk = is_risk_dimension(cat, dim_key)
        if is_risk and e.fields_data and not risk_and_affiliation_info:
            risk_and_affiliation_info = extract_risk_and_affiliation(e.fields_data)

    # 3. Dynamic dimensions with rich layout details (facets, texts, facts, lists, rationale, evidence)
    ext_by_def = {}
    for e in extractions_list:
        if e.extraction_definition_id and e.extraction_definition_id not in ext_by_def:
            ext_by_def[e.extraction_definition_id] = e

    dimensions = []
    for d in definitions:
        e = ext_by_def.get(d.id)
        if not d.is_active and not e:
            continue

        max_val, is_trl = resolve_dimension_scale(d.name)

        primary_metric, secondary_metrics, has_post = extract_metrics_for_extraction(e, d)
        dim_key = d.name.lower().replace(' ', '_').replace('-', '_')

        numeric_val = primary_metric.get('numeric_value') if primary_metric else None
        if primary_metric and primary_metric.get('raw') and primary_metric.get('raw') != '—':
            raw_val = primary_metric.get('raw')
        elif primary_metric and primary_metric.get('value') is not None:
            raw_val = str(primary_metric.get('value'))
        elif d and d.has_explicit_frontend_metrics():
            raw_val = None
        else:
            raw_val = str(e.exit_metric) if (e and e.exit_metric is not None and str(e.exit_metric) != '—') else None

        if raw_val and (raw_val.startswith('{') or raw_val.startswith('OrderedDict(')):
            raw_val = None if (d and d.has_explicit_frontend_metrics()) else '—'

        rich_details = extract_rich_dimension_details(
            fields_data=e.fields_data if (e and e.fields_data) else {},
            primary_metric=primary_metric or {},
            secondary_metrics=secondary_metrics or [],
            max_val=max_val,
            is_trl=is_trl,
            order=d.get_secondary_frontend_metrics_list() if (d and d.has_explicit_frontend_metrics()) else (d.get_exit_metrics_list() if d else None),
        )

        dimensions.append({
            'key': dim_key,
            'definition_id': str(d.id),
            'name': d.name,
            'label': d.name,
            'value': numeric_val,
            'raw': raw_val,
            'max': max_val,
            'is_trl': is_trl,
            'is_risk_and_affiliation': is_risk_dimension(d.name, dim_key),
            'has_postprocessing': has_post,
            'primary_metric': primary_metric,
            'secondary_metrics': secondary_metrics,
            'primary_frontend_metric': d.primary_frontend_metric or None,
            'secondary_frontend_metrics': d.get_secondary_frontend_metrics_list(),
            'is_hitl': bool(e.is_hitl_validated) if e else False,
            'fields_data': e.fields_data if e else None,
            'response_schema': d.response_schema,
            'exit_metrics': d.get_exit_metrics_list(),
            'rationale': rich_details.get('rationale'),
            'evidence': rich_details.get('evidence') or [],
            'confidence': float(e.confidence_score) if (e and e.confidence_score is not None) else None,
            'validation_status': e.validation_status if e else 'valid',
            'review_required': bool(e.review_required) if e else False,
            'extraction_id': str(e.id) if e else None,
            'band': rich_details.get('band') or None,
            'facets': rich_details.get('facets') or [],
            'texts': rich_details.get('texts') or [],
            'lists': rich_details.get('lists') or [],
            'facts': rich_details.get('facts') or [],
            'model': (
                e.version_info.get('llm_model')
                if (e and isinstance(e.version_info, dict) and e.version_info.get('llm_model'))
                else d.llm_model
            ) if e else d.llm_model,
        })

    # Trailing definition-less extractions
    def_ids = {d.id for d in definitions}
    for e in extractions_list:
        if not e.extraction_definition_id or e.extraction_definition_id not in def_ids:
            primary_metric, secondary_metrics, has_post = extract_metrics_for_extraction(e, None)
            dim_key = (e.category or 'custom').lower().replace(' ', '_').replace('-', '_')
            max_val, is_trl = resolve_dimension_scale(e.category or '')

            rich_details = extract_rich_dimension_details(
                fields_data=e.fields_data or {},
                primary_metric=primary_metric or {},
                secondary_metrics=secondary_metrics or [],
                max_val=max_val,
                is_trl=is_trl,
            )

            numeric_val = primary_metric.get('numeric_value') if primary_metric else None
            if primary_metric and primary_metric.get('raw') and primary_metric.get('raw') != '—':
                raw_val = primary_metric.get('raw')
            elif primary_metric and primary_metric.get('value') is not None:
                raw_val = str(primary_metric.get('value'))
            else:
                raw_val = str(e.exit_metric) if e.exit_metric is not None else '—'

            if raw_val and (raw_val.startswith('{') or raw_val.startswith('OrderedDict(')):
                raw_val = '—'

            dimensions.append({
                'key': dim_key,
                'definition_id': None,
                'name': e.category or 'Extraction',
                'label': e.category or 'Extraction',
                'value': numeric_val,
                'raw': raw_val,
                'max': max_val,
                'is_trl': is_trl,
                'is_risk_and_affiliation': is_risk_dimension(e.category or '', dim_key),
                'has_postprocessing': has_post,
                'primary_metric': primary_metric,
                'secondary_metrics': secondary_metrics,
                'primary_frontend_metric': None,
                'secondary_frontend_metrics': [],
                'is_hitl': bool(e.is_hitl_validated),
                'fields_data': e.fields_data,
                'response_schema': None,
                'exit_metrics': [primary_metric['key']] if primary_metric else [],
                'rationale': rich_details.get('rationale'),
                'evidence': rich_details.get('evidence') or [],
                'confidence': float(e.confidence_score) if e.confidence_score is not None else None,
                'validation_status': e.validation_status,
                'review_required': bool(e.review_required),
                'extraction_id': str(e.id),
                'band': rich_details.get('band') or None,
                'facets': rich_details.get('facets') or [],
                'texts': rich_details.get('texts') or [],
                'lists': rich_details.get('lists') or [],
                'facts': rich_details.get('facts') or [],
                'model': e.version_info.get('llm_model') if isinstance(e.version_info, dict) else None,
            })

    # 4. Resolve source_url
    final_source_url = None
    if paper.source_url:
        final_source_url = paper.source_url
    elif paper.arxiv_id:
        final_source_url = f"https://arxiv.org/abs/{paper.arxiv_id}"
    elif paper.doi:
        final_source_url = f"https://doi.org/{paper.doi}"

    final_screening_status = (
        target_metric.screening_status
        if (target_metric and target_metric.screening_status)
        else (paper_data.get('screening_status') if paper_data else getattr(paper, 'screening_status', 'pending'))
    ) or 'pending'

    final_signal_score = (
        float(target_metric.signal_score)
        if (target_metric and target_metric.signal_score is not None)
        else (
            float(paper_data.get('signal_score'))
            if (paper_data and paper_data.get('signal_score') is not None)
            else (float(getattr(paper, 'signal_score', None)) if getattr(paper, 'signal_score', None) is not None else None)
        )
    )

    final_is_benchmark = (
        bool(target_metric.is_evaluation_benchmark)
        if target_metric
        else (
            bool(paper_data.get('is_evaluation_benchmark'))
            if paper_data
            else bool(getattr(paper, 'is_benchmark', False))
        )
    )

    raw_eval_label = (
        target_metric.evaluation_label
        if target_metric
        else (
            paper_data.get('evaluation_label')
            if paper_data
            else getattr(paper, 'evaluation_label', None)
        )
    )
    final_evaluation_label = (
        raw_eval_label if (isinstance(raw_eval_label, str) and raw_eval_label in ('passed', 'rejected')) else None
    )

    pub_date = None
    if hasattr(paper, 'published_date') and paper.published_date:
        pub_date = paper.published_date.isoformat() if hasattr(paper.published_date, 'isoformat') else str(paper.published_date)
    elif paper_data and paper_data.get('published_date'):
        pub_date = paper_data.get('published_date')

    run_name = (
        target_pr.name if (target_pr and hasattr(target_pr, 'name'))
        else (
            target_metric.pipeline_run.name
            if (target_metric and target_metric.pipeline_run and hasattr(target_metric.pipeline_run, 'name'))
            else (paper_data.get('pipeline_run_name') if paper_data else (f"Run #{str(target_pr_id)[:8]}" if target_pr_id else None))
        )
    )

    dt = paper.created_at
    created_at_str = dt.isoformat() if (hasattr(dt, 'tzinfo') and dt.tzinfo) else (dt.isoformat() + "Z")

    return {
        'id': str(paper.id),
        'workspace_id': str(paper.workspace_id),
        'pipeline_run_id': str(target_pr_id) if target_pr_id else '',
        'title': paper.title,
        'authors': authors_list,
        'authors_raw': raw_authors,
        'abstract': paper.abstract or '',
        'doi': paper.doi or None,
        'arxiv_id': paper.arxiv_id or None,
        'source': getattr(paper, 'source_database', None) or getattr(paper, 'source', None) or 'arxiv',
        'screening_status': final_screening_status,
        'screening_reasoning': (
            target_metric.latest_screening_reasoning
            if target_metric
            else (paper_data.get('screening_reasoning') if paper_data else getattr(paper, 'screening_reasoning', None))
        ),
        'abstract_screening_reasoning': (
            target_metric.abstract_screening_reasoning
            if target_metric
            else (paper_data.get('abstract_screening_reasoning') if paper_data else None)
        ),
        'full_text_screening_reasoning': (
            target_metric.full_text_screening_reasoning
            if target_metric
            else (paper_data.get('full_text_screening_reasoning') if paper_data else None)
        ),
        'signal_score': final_signal_score,
        'signal_score_details': formatted_ssd,
        'dimensions': dimensions,
        'pdf_key': getattr(paper, 'original_pdf_path', None) or getattr(paper, 'pdf_path', None) or None,
        'markdown_key': getattr(paper, 'converted_md_path', None) or getattr(paper, 'markdown_path', None) or None,
        'source_url': final_source_url,
        'is_benchmark': final_is_benchmark,
        'evaluation_label': final_evaluation_label,
        'published_date': pub_date,
        'created_at': created_at_str,
        'pipeline_run_name': run_name,
        'risk_and_affiliation': risk_and_affiliation_info,
    }


def build_paper_scorecard_data(paper: Paper, pipeline_run_id=None, request=None) -> dict:
    """
    Builds the dynamic, schema-driven Paper Scorecard data dictionary.
    Usable by both REST API (GET /api/papers/{id}/scorecard/) and MCP tools.
    """
    # 1. Resolve target pipeline run
    pr_param = pipeline_run_id
    target_pr = None
    target_pr_id = None

    if pr_param and str(pr_param).lower() not in ('undefined', 'null', ''):
        if str(pr_param).lower() == 'latest':
            target_pr = (
                PipelineRun.objects.filter(workspace=paper.workspace)
                .exclude(status__in=['failed', 'aborted'])
                .order_by('-started_at', '-id')
                .first()
            )
            if not target_pr:
                target_pr = (
                    PipelineRun.objects.filter(workspace=paper.workspace)
                    .order_by('-started_at', '-id')
                    .first()
                )
            if target_pr:
                target_pr_id = target_pr.id
        else:
            try:
                pr_uuid = uuid.UUID(str(pr_param))
                target_pr = PipelineRun.objects.filter(id=pr_uuid, workspace=paper.workspace).first()
                if target_pr:
                    target_pr_id = target_pr.id
                else:
                    target_pr_id = pr_uuid
            except (ValueError, TypeError):
                target_pr_id = None

    # Fallback to paper's canonical run if not specified
    if not target_pr_id:
        canon_m = resolve_paper_representing_metric(paper.metrics.all())
        if canon_m and canon_m.pipeline_run_id:
            target_pr_id = canon_m.pipeline_run_id
            target_pr = canon_m.pipeline_run
        elif getattr(paper, 'pipeline_run_id', None):
            target_pr_id = paper.pipeline_run_id
            target_pr = getattr(paper, 'pipeline_run', None)
        target_metric = canon_m
    else:
        target_metric = resolve_paper_representing_metric(paper.metrics.all(), target_pr_id=target_pr_id)

    paper_serializer = PaperSerializer(paper, context={'request': request, 'pipeline_run': target_pr_id})
    paper_data = paper_serializer.data

    extractions = list(
        Extraction.objects.filter(paper=paper)
        .select_related('extraction_definition')
        .order_by('-created_at')
    )
    definitions = list(
        ExtractionDefinition.objects.filter(workspace=paper.workspace, is_active=True)
        .order_by('order', 'created_at')
    )

    # Format signal_score_details
    ssd = (
        target_metric.signal_score_details
        if (target_metric and target_metric.signal_score_details)
        else paper_data.get('signal_score_details')
    )
    formatted_ssd = None
    if isinstance(ssd, dict) and ssd:
        formatted_ssd = {
            'variables': ssd.get('variables') if isinstance(ssd.get('variables'), dict) else {},
            'code_snippet': ssd.get('code_snippet') or None,
            'calculated_at': ssd.get('calculated_at') or None,
            'error': ssd.get('error') or None,
        }

    definitions_data = format_definitions_metadata(definitions)

    extractions_data = []
    risk_and_affiliation_info = None

    for e in extractions:
        d_obj = e.extraction_definition
        primary_metric, secondary_metrics, has_post = extract_metrics_for_extraction(e, d_obj)
        is_risk = is_risk_dimension(
            d_obj.name if d_obj else e.category,
            (d_obj.name if d_obj else e.category or '').lower().replace(' ', '_'),
        )
        if is_risk and e.fields_data and not risk_and_affiliation_info:
            risk_and_affiliation_info = extract_risk_and_affiliation(e.fields_data)

        def_dict = None
        if d_obj:
            exit_list = d_obj.get_exit_metrics_list()
            prim_exit = d_obj.get_primary_exit_metric()
            d_slug = d_obj.name.lower().replace(' ', '_').replace('-', '_')
            has_explicit = bool(d_obj.has_explicit_frontend_metrics())
            if has_explicit:
                main_key = d_obj.get_primary_frontend_metric()
                aux_keys = d_obj.get_secondary_frontend_metrics_list()
            elif has_post:
                main_key = f"{d_slug}_postprocessed"
                aux_keys = exit_list
            else:
                main_key = exit_list[0] if exit_list else prim_exit
                aux_keys = exit_list[1:] if len(exit_list) > 1 else []

            def_dict = {
                'id': str(d_obj.id),
                'name': d_obj.name,
                'key': d_slug,
                'response_schema': d_obj.response_schema,
                'exit_metrics': exit_list,
                'primary_exit_metric': prim_exit,
                'primary_frontend_metric': d_obj.primary_frontend_metric or None,
                'secondary_frontend_metrics': d_obj.get_secondary_frontend_metrics_list(),
                'has_postprocessing': has_post,
                'postprocessing_code': d_obj.postprocessing_code or None,
                'primary_metric_key': main_key,
                'main_metric_key': main_key,
                'secondary_metric_keys': aux_keys,
                'auxiliary_metric_keys': aux_keys,
                'llm_model': d_obj.llm_model,
                'is_active': d_obj.is_active,
            }

        extractions_data.append({
            'id': str(e.id),
            'workspace_id': str(e.workspace_id),
            'paper_id': str(e.paper_id),
            'extraction_definition_id': str(e.extraction_definition_id) if e.extraction_definition_id else None,
            'category': e.category,
            'is_risk_and_affiliation': is_risk,
            'fields_data': e.fields_data,
            'exit_metric': e.exit_metric,
            'has_postprocessing': has_post,
            'primary_metric': primary_metric,
            'secondary_metrics': secondary_metrics,
            'main_metric': primary_metric,
            'auxiliary_metrics': secondary_metrics,
            'confidence_score': float(e.confidence_score) if e.confidence_score is not None else None,
            'confidence_method': e.confidence_method,
            'validation_status': e.validation_status,
            'review_required': bool(e.review_required),
            'is_hitl_validated': bool(e.is_hitl_validated),
            'model': (
                e.version_info.get('llm_model')
                if isinstance(e.version_info, dict)
                else (d_obj.llm_model if d_obj else None)
            ),
            'version_info': e.version_info,
            'created_at': e.created_at.isoformat(),
            'definition': def_dict,
        })

    ws_summary = format_workspace_summary(paper.workspace, definitions_data, request=request)

    report = None
    if target_pr_id:
        report = NarrativeReport.objects.filter(pipeline_run_id=target_pr_id).first()
    if not report:
        report = NarrativeReport.objects.filter(workspace=paper.workspace).order_by('-created_at').first()

    narrative_report_data = None
    if report:
        narrative_report_data = {
            'id': str(report.id),
            'pipeline_run_id': str(report.pipeline_run_id) if report.pipeline_run_id else None,
            'workspace_id': str(report.workspace_id),
            'title': report.title,
            'content_markdown': report.content_markdown,
            'content_latex': report.content_latex or None,
            'bibtex_content': report.bibtex_content or None,
            'compiled_pdf_path': report.compiled_pdf_path or None,
            'refinement_depth': report.refinement_depth,
            'created_at': report.created_at.isoformat(),
        }

    metric_data = None
    if target_metric:
        metric_data = {
            'id': str(target_metric.id),
            'paper_id': str(target_metric.paper_id),
            'pipeline_run_id': str(target_metric.pipeline_run_id) if target_metric.pipeline_run_id else None,
            'workspace_id': str(target_metric.workspace_id),
            'screening_status': target_metric.screening_status,
            'screening_reasoning': target_metric.latest_screening_reasoning,
            'abstract_screening_reasoning': target_metric.abstract_screening_reasoning,
            'full_text_screening_reasoning': target_metric.full_text_screening_reasoning,
            'signal_score': float(target_metric.signal_score) if target_metric.signal_score is not None else None,
            'signal_score_details': formatted_ssd,
            'metrics_data': target_metric.metrics_data or {},
            'is_evaluation_benchmark': bool(target_metric.is_evaluation_benchmark),
            'evaluation_label': target_metric.evaluation_label,
            'created_at': target_metric.created_at.isoformat(),
        }

    scored_paper = build_single_scored_paper(
        paper=paper,
        definitions=definitions,
        target_pr_id=target_pr_id,
        target_pr=target_pr,
        metrics_list=list(paper.metrics.all()),
        extractions_list=extractions,
        paper_data=paper_data,
    )

    return {
        'workspace': ws_summary,
        'paper': scored_paper,
        'definitions': definitions_data,
        'extractions': extractions_data,
        'metric': metric_data,
        'narrative_report': narrative_report_data,
    }


def build_workspace_scorecard_data(workspace, pipeline_run_id=None, request=None) -> dict:
    """
    Builds the workspace-level scorecard containing:
      - workspace: summary details and definition metadata
      - papers: list of ScoredPaper objects
    Supports optional run_id filtering and pagination.
    """
    definitions = list(
        ExtractionDefinition.objects.filter(workspace=workspace, is_active=True)
        .order_by('order', 'created_at')
    )
    definitions_data = format_definitions_metadata(definitions)

    ws_summary = format_workspace_summary(workspace, definitions_data, request=request)

    # 1. Resolve pipeline_run filter
    target_pr = None
    target_pr_id = None
    if pipeline_run_id and str(pipeline_run_id).lower() not in ('undefined', 'null', ''):
        if str(pipeline_run_id).lower() == 'latest':
            target_pr = (
                PipelineRun.objects.filter(workspace=workspace)
                .exclude(status__in=['failed', 'aborted'])
                .order_by('-started_at', '-id')
                .first()
            )
            if target_pr:
                target_pr_id = target_pr.id
        else:
            try:
                pr_uuid = uuid.UUID(str(pipeline_run_id))
                target_pr = PipelineRun.objects.filter(id=pr_uuid, workspace=workspace).first()
                if target_pr:
                    target_pr_id = target_pr.id
                else:
                    target_pr_id = pr_uuid
            except (ValueError, TypeError):
                target_pr_id = None

    # 2. Query papers for workspace
    papers_qs = Paper.objects.filter(workspace=workspace)
    if target_pr:
        papers_qs = papers_qs.filter(metrics__pipeline_run=target_pr)
    elif target_pr_id:
        papers_qs = papers_qs.filter(metrics__pipeline_run_id=target_pr_id)

    from django.db.models import Case, F, OuterRef, Subquery, Value, When
    from research_intelligence.models import PaperMetric

    if target_pr_id:
        metric_score_qs = PaperMetric.objects.filter(paper=OuterRef('pk'), pipeline_run_id=target_pr_id)
        metric_status_qs = PaperMetric.objects.filter(paper=OuterRef('pk'), pipeline_run_id=target_pr_id)
    else:
        metric_score_qs = PaperMetric.objects.filter(paper=OuterRef('pk')).order_by(
            Case(When(signal_score__isnull=False, then=Value(0)), default=Value(1)),
            '-created_at',
            '-id',
        )
        metric_status_qs = PaperMetric.objects.filter(paper=OuterRef('pk')).order_by(
            Case(When(screening_status='pending', then=Value(1)), default=Value(0)),
            '-created_at',
            '-id',
        )

    score_subquery = Subquery(metric_score_qs.values('signal_score')[:1])
    status_subquery = Subquery(metric_status_qs.values('screening_status')[:1])

    # Optional screening status filter
    if request:
        screening_param = request.query_params.get('screening') or request.query_params.get('screening_status')
        if screening_param:
            sc_clean = screening_param.strip().lower()
            papers_qs = papers_qs.annotate(annotated_screening_status=status_subquery)
            if sc_clean == 'passed':
                papers_qs = papers_qs.filter(
                    annotated_screening_status__in=['abstract_passed', 'full_text_passed', 'accepted']
                )
            elif sc_clean != 'all':
                papers_qs = papers_qs.filter(annotated_screening_status=sc_clean)

        search_query = request.query_params.get('search') or request.query_params.get('q')
        if search_query and str(search_query).strip():
            term = str(search_query).strip()
            papers_qs = papers_qs.filter(
                Q(title__icontains=term) |
                Q(authors__icontains=term) |
                Q(abstract__icontains=term) |
                Q(doi__icontains=term) |
                Q(arxiv_id__icontains=term)
            )

    ordering_param = None
    if request:
        ordering_param = request.query_params.get('ordering') or request.query_params.get('sort')

    papers_qs = papers_qs.annotate(annotated_signal_score=score_subquery)

    if ordering_param:
        ord_clean = ordering_param.strip().lower()
        if ord_clean in ('signal_score', '+signal_score'):
            papers_qs = papers_qs.order_by(F('annotated_signal_score').asc(nulls_last=True), 'created_at', 'id')
        elif ord_clean == '-signal_score':
            papers_qs = papers_qs.order_by(F('annotated_signal_score').desc(nulls_last=True), '-created_at', '-id')
        elif ord_clean in ('title', '+title'):
            papers_qs = papers_qs.order_by('title', 'id')
        elif ord_clean == '-title':
            papers_qs = papers_qs.order_by('-title', '-id')
        elif ord_clean in ('created_at', '+created_at'):
            papers_qs = papers_qs.order_by('created_at', 'id')
        elif ord_clean == '-created_at':
            papers_qs = papers_qs.order_by('-created_at', '-id')
    elif target_pr_id:
        papers_qs = papers_qs.order_by(F('annotated_signal_score').desc(nulls_last=True), '-created_at', '-id')
    else:
        papers_qs = papers_qs.order_by('-created_at', '-id')

    papers_qs = (
        papers_qs
        .select_related('workspace')
        .prefetch_related(
            'metrics',
            'metrics__pipeline_run',
            'extractions',
            'extractions__extraction_definition',
        )
    )

    # Optional pagination
    page_number = 1
    page_size = None
    if request:
        page_param = request.query_params.get('page')
        size_param = request.query_params.get('page_size')
        if page_param:
            try:
                raw_page = int(page_param)
                page_number = max(1, raw_page)
            except (ValueError, TypeError):
                page_number = 1
        if size_param:
            try:
                raw_size = int(size_param)
                page_size = max(1, min(raw_size, 200))
            except (ValueError, TypeError):
                page_size = None

    total_count = papers_qs.count()
    has_next = False
    has_prev = False

    if page_size:
        paginator = Paginator(papers_qs, page_size)
        page_obj = paginator.get_page(page_number)
        paper_items = list(page_obj.object_list)
        has_next = page_obj.has_next()
        has_prev = page_obj.has_previous()
    else:
        paper_items = list(papers_qs)

    scored_papers = []
    for p in paper_items:
        sp = build_single_scored_paper(
            paper=p,
            definitions=definitions,
            target_pr_id=target_pr_id,
            target_pr=target_pr,
            metrics_list=list(p.metrics.all()),
            extractions_list=list(p.extractions.all()),
            request=request,
        )
        scored_papers.append(sp)

    next_url = None
    prev_url = None
    if page_size:
        base_url = f"/api/workspaces/{workspace.id}/scorecard/"
        params = []
        if target_pr_id:
            params.append(f"run_id={target_pr_id}")
        params.append(f"page_size={page_size}")
        if ordering_param:
            params.append(f"ordering={ordering_param}")
        if request and (request.query_params.get('screening') or request.query_params.get('screening_status')):
            sc_val = request.query_params.get('screening') or request.query_params.get('screening_status')
            params.append(f"screening={sc_val}")
        if request and (request.query_params.get('search') or request.query_params.get('q')):
            q_val = request.query_params.get('search') or request.query_params.get('q')
            params.append(f"search={q_val}")
        p_str = "&".join(params)

        if page_obj.has_next():
            next_url = f"{base_url}?page={page_obj.next_page_number()}&{p_str}"
        if page_obj.has_previous():
            prev_url = f"{base_url}?page={page_obj.previous_page_number()}&{p_str}"

    res = {
        'workspace': ws_summary,
        'papers': scored_papers,
        'results': scored_papers,
        'count': total_count,
        'next': next_url,
        'previous': prev_url,
    }
    if page_size:
        res['page'] = page_number
        res['page_size'] = page_size
    return res
