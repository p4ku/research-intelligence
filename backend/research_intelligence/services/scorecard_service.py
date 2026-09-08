import re
import uuid

from django.core.paginator import Paginator

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


def format_definitions_metadata(definitions: list) -> list:
    """Formats extraction definitions into metadata dictionaries for the scorecard payload."""
    definitions_data = []
    for d in definitions:
        has_post = bool(d.postprocessing_code and d.postprocessing_code.strip())
        exit_list = d.get_exit_metrics_list()
        prim_exit = d.get_primary_exit_metric()
        d_slug = d.name.lower().replace(' ', '_').replace('-', '_')

        if has_post:
            main_key = f"{d_slug}_postprocessed"
            aux_keys = exit_list
        else:
            main_key = exit_list[0] if exit_list else prim_exit
            aux_keys = exit_list[1:] if len(exit_list) > 1 else []

        definitions_data.append({
            'id': str(d.id),
            'name': d.name,
            'key': d_slug,
            'category': d.name,
            'response_schema': d.response_schema,
            'exit_metrics': exit_list,
            'primary_exit_metric': prim_exit,
            'has_postprocessing': has_post,
            'postprocessing_code': d.postprocessing_code or None,
            'primary_metric_key': main_key,
            'main_metric_key': main_key,
            'secondary_metric_keys': aux_keys,
            'auxiliary_metric_keys': aux_keys,
            'llm_model': d.llm_model,
            'is_active': d.is_active,
            'created_at': d.created_at.isoformat(),
        })
    return definitions_data


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
    target_metric = None
    if target_pr_id:
        norm_target_pr = str(target_pr_id)
        for m in metrics_list:
            if str(m.pipeline_run_id) == norm_target_pr:
                target_metric = m
                break
    if not target_metric and metrics_list:
        target_metric = metrics_list[0]

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

        is_trl = bool(re.search(r'\btrl\b', d.name, re.IGNORECASE))
        if is_trl:
            max_val = 9
        elif re.search(r'\(1-10\)', d.name):
            max_val = 10
        else:
            max_val = 100

        primary_metric, secondary_metrics, has_post = extract_metrics_for_extraction(e, d)
        dim_key = d.name.lower().replace(' ', '_').replace('-', '_')

        numeric_val = primary_metric.get('numeric_value') if primary_metric else None
        raw_val = (
            str(primary_metric.get('value'))
            if (primary_metric and primary_metric.get('value') is not None)
            else (str(e.exit_metric) if (e and e.exit_metric is not None) else '—')
        )

        rich_details = extract_rich_dimension_details(
            fields_data=e.fields_data if (e and e.fields_data) else {},
            primary_metric=primary_metric or {},
            secondary_metrics=secondary_metrics or [],
            max_val=max_val,
            is_trl=is_trl,
            order=d.get_exit_metrics_list() if d else None,
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
            'main_metric': primary_metric,
            'auxiliary_metrics': secondary_metrics,
            'is_hitl': bool(e.is_hitl_validated) if e else False,
            'fields_data': e.fields_data if e else None,
            'response_schema': d.response_schema,
            'exit_metrics': d.get_exit_metrics_list(),
            'rationale': rich_details.get('rationale'),
            'evidence': rich_details.get('evidence', []),
            'confidence': float(e.confidence_score) if (e and e.confidence_score is not None) else None,
            'validation_status': e.validation_status if e else 'valid',
            'review_required': bool(e.review_required) if e else False,
            'extraction_id': str(e.id) if e else None,
            'band': rich_details.get('band'),
            'facets': rich_details.get('facets', []),
            'texts': rich_details.get('texts', []),
            'lists': rich_details.get('lists', []),
            'facts': rich_details.get('facts', []),
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
            is_trl = bool(re.search(r'\btrl\b', e.category or '', re.IGNORECASE))
            max_val = 9 if is_trl else 100

            rich_details = extract_rich_dimension_details(
                fields_data=e.fields_data or {},
                primary_metric=primary_metric or {},
                secondary_metrics=secondary_metrics or [],
                max_val=max_val,
                is_trl=is_trl,
            )

            numeric_val = primary_metric.get('numeric_value') if primary_metric else None
            raw_val = (
                str(primary_metric.get('value'))
                if (primary_metric and primary_metric.get('value') is not None)
                else (str(e.exit_metric) if e.exit_metric is not None else '—')
            )

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
                'main_metric': primary_metric,
                'auxiliary_metrics': secondary_metrics,
                'is_hitl': bool(e.is_hitl_validated),
                'fields_data': e.fields_data,
                'response_schema': None,
                'exit_metrics': [primary_metric['key']] if primary_metric else [],
                'rationale': rich_details.get('rationale'),
                'evidence': rich_details.get('evidence', []),
                'confidence': float(e.confidence_score) if e.confidence_score is not None else None,
                'validation_status': e.validation_status,
                'review_required': bool(e.review_required),
                'extraction_id': str(e.id),
                'band': rich_details.get('band'),
                'facets': rich_details.get('facets', []),
                'texts': rich_details.get('texts', []),
                'lists': rich_details.get('lists', []),
                'facts': rich_details.get('facts', []),
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

    final_evaluation_label = (
        target_metric.evaluation_label
        if target_metric
        else (
            paper_data.get('evaluation_label')
            if paper_data
            else getattr(paper, 'evaluation_label', None)
        )
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

    return {
        'id': str(paper.id),
        'workspace_id': str(paper.workspace_id),
        'pipeline_run_id': str(target_pr_id) if target_pr_id else '00000000-0000-0000-0000-000000000000',
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
        'pdf_key': getattr(paper, 'pdf_path', None) or None,
        'markdown_key': getattr(paper, 'converted_md_path', None) or getattr(paper, 'markdown_path', None) or None,
        'source_url': final_source_url,
        'is_benchmark': final_is_benchmark,
        'evaluation_label': final_evaluation_label,
        'published_date': pub_date,
        'created_at': paper.created_at.isoformat(),
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

    # Fallback to paper's newest run if not specified
    if not target_pr_id:
        latest_m = paper.metrics.order_by('-created_at').first()
        if latest_m and latest_m.pipeline_run_id:
            target_pr_id = latest_m.pipeline_run_id
            target_pr = latest_m.pipeline_run
        elif getattr(paper, 'pipeline_run_id', None):
            target_pr_id = paper.pipeline_run_id
            target_pr = getattr(paper, 'pipeline_run', None)

    target_metric = None
    if target_pr_id:
        target_metric = paper.metrics.filter(pipeline_run_id=target_pr_id).first()
    if not target_metric:
        target_metric = paper.metrics.order_by('-created_at').first()

    paper_serializer = PaperSerializer(paper, context={'request': request, 'pipeline_run': target_pr_id})
    paper_data = paper_serializer.data

    extractions = list(
        Extraction.objects.filter(paper=paper)
        .select_related('extraction_definition')
        .order_by('-created_at')
    )
    definitions = list(
        ExtractionDefinition.objects.filter(workspace=paper.workspace, is_active=True)
        .order_by('created_at')
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
            if has_post:
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

    ws_summary = {
        'id': str(paper.workspace.id),
        'name': paper.workspace.name,
        'definitions': definitions_data,
        'scrapers_count': paper.workspace.scrapers.count(),
    }

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
        .order_by('created_at')
    )
    definitions_data = format_definitions_metadata(definitions)

    ws_summary = {
        'id': str(workspace.id),
        'name': workspace.name,
        'definitions': definitions_data,
        'scrapers_count': workspace.scrapers.count(),
    }

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
    papers_qs = (
        Paper.objects.filter(workspace=workspace)
        .select_related('workspace')
        .prefetch_related(
            'metrics',
            'metrics__pipeline_run',
            'extractions',
            'extractions__extraction_definition',
        )
        .order_by('-created_at')
    )

    # Optional screening status filter
    if request:
        screening_param = request.query_params.get('screening') or request.query_params.get('screening_status')
        if screening_param:
            sc_clean = screening_param.strip().lower()
            if sc_clean == 'passed':
                papers_qs = papers_qs.filter(screening_status__in=['abstract_passed', 'full_text_passed', 'accepted'])
            elif sc_clean != 'all':
                papers_qs = papers_qs.filter(screening_status=sc_clean)

    # Optional pagination
    page_number = 1
    page_size = None
    if request:
        page_param = request.query_params.get('page')
        size_param = request.query_params.get('page_size')
        if page_param:
            try:
                page_number = int(page_param)
            except (ValueError, TypeError):
                page_number = 1
        if size_param:
            try:
                page_size = min(int(size_param), 200)
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

    res = {
        'workspace': ws_summary,
        'papers': scored_papers,
        'results': scored_papers,
        'count': total_count,
    }
    if page_size:
        res['next'] = has_next
        res['previous'] = has_prev
        res['page'] = page_number
        res['page_size'] = page_size
    return res
