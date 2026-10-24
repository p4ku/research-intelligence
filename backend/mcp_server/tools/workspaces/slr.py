from __future__ import annotations
import json
import uuid
from typing import Optional, List, Dict, Any, Union
from django.contrib.auth import get_user_model
from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction

from research_intelligence.models import Workspace, WorkspaceMember
from research_intelligence.services import check_workspace_access, create_workspace_record
from slr_review.models import (
    SLRWorkspaceConfig,
    SLRProtocol,
    get_default_exclusion_reasons,
)

User = get_user_model()


def _resolve_user(identifier: Union[str, int, User, None]) -> Optional[User]:
    """Resolves a User by username, email, ID, or direct instance."""
    if not identifier:
        return None
    if isinstance(identifier, User):
        return identifier
    id_str = str(identifier).strip()
    user = User.objects.filter(username__iexact=id_str).first()
    if user:
        return user
    user = User.objects.filter(email__iexact=id_str).first()
    if user:
        return user
    try:
        user = User.objects.filter(pk=id_str).first()
        if user:
            return user
    except Exception:
        pass
    return None


def serialize_slr_config(config: Optional[SLRWorkspaceConfig]) -> Optional[Dict[str, Any]]:
    """Serializes SLRWorkspaceConfig model into a structured JSON-compatible dictionary."""
    if not config:
        return None
    return {
        "id": str(config.id),
        "checkpoint_gate_mode": config.checkpoint_gate_mode,
        "checkpoint_gate_mode_display": config.get_checkpoint_gate_mode_display(),
        "enable_extraction_gate": config.enable_extraction_gate,
        "screening_quorum_size": config.screening_quorum_size,
        "extraction_quorum_size": config.extraction_quorum_size,
        "require_blind_review": config.require_blind_review,
        "sampling_mode": config.sampling_mode,
        "sampling_mode_display": config.get_sampling_mode_display(),
        "abstract_sample_percentage": config.abstract_sample_percentage,
        "full_text_sample_percentage": config.full_text_sample_percentage,
        "extraction_sample_percentage": config.extraction_sample_percentage,
        "negative_control_percentage": config.negative_control_percentage,
        "enable_rob_assessment": config.enable_rob_assessment,
        "rob_framework": config.rob_framework,
        "rob_framework_display": config.get_rob_framework_display(),
        "require_human_rob_validation": config.require_human_rob_validation,
        "designated_arbiter": {
            "id": config.designated_arbiter.id,
            "username": config.designated_arbiter.username,
            "email": config.designated_arbiter.email,
        } if config.designated_arbiter else None,
        "tie_breaker_strategy": config.tie_breaker_strategy,
        "tie_breaker_strategy_display": config.get_tie_breaker_strategy_display(),
        "exclusion_reasons": config.exclusion_reasons or [],
        "require_evidence_on_exclusion": config.require_evidence_on_exclusion,
        "require_evidence_on_override": config.require_evidence_on_override,
        "notify_reviewers_on_pause": config.notify_reviewers_on_pause,
        "stale_queue_reminder_days": config.stale_queue_reminder_days,
        "created_at": config.created_at.isoformat() if config.created_at else None,
        "updated_at": config.updated_at.isoformat() if config.updated_at else None,
    }


def serialize_slr_protocol(protocol: Optional[SLRProtocol]) -> Optional[Dict[str, Any]]:
    """Serializes SLRProtocol model into a structured JSON-compatible dictionary."""
    if not protocol:
        return None
    return {
        "id": str(protocol.id),
        "title": protocol.title,
        "review_question": protocol.review_question,
        "pico": {
            "population": protocol.pico_population,
            "intervention": protocol.pico_intervention,
            "comparison": protocol.pico_comparison,
            "outcome": protocol.pico_outcome,
            "study_design_criteria": protocol.study_design_criteria,
        },
        "prospero_registration_id": protocol.prospero_registration_id,
        "is_locked": protocol.is_locked,
        "version": protocol.version,
        "created_by": protocol.created_by.username if protocol.created_by else None,
        "created_at": protocol.created_at.isoformat() if protocol.created_at else None,
        "updated_at": protocol.updated_at.isoformat() if protocol.updated_at else None,
    }


def build_prisma_summary(config: SLRWorkspaceConfig) -> Dict[str, Any]:
    """Generates PRISMA 2020 operational workflow summary."""
    gates = []
    if config.checkpoint_gate_mode == 'two_stage_split':
        gates = [
            {"gate": "Gate 1: Abstract Screening", "sample_rate": f"{config.abstract_sample_percentage}%", "quorum": config.screening_quorum_size},
            {"gate": "Gate 2: Full-Text Screening", "sample_rate": f"{config.full_text_sample_percentage}%", "quorum": config.screening_quorum_size},
        ]
    elif config.checkpoint_gate_mode == 'single_combined_post_fulltext':
        gates = [
            {"gate": "Combined Gate: Post Full-Text Screening", "sample_rate": f"{config.full_text_sample_percentage}%", "quorum": config.screening_quorum_size},
        ]
    elif config.checkpoint_gate_mode == 'abstract_only_gate':
        gates = [
            {"gate": "Gate 1: Abstract Screening (Scoping)", "sample_rate": f"{config.abstract_sample_percentage}%", "quorum": config.screening_quorum_size},
        ]
    elif config.checkpoint_gate_mode == 'autonomous_benchmark':
        gates = []

    if config.enable_extraction_gate:
        gates.append({
            "gate": "Gate 3: Parameter Extraction",
            "sample_rate": f"{config.extraction_sample_percentage}%",
            "quorum": config.extraction_quorum_size
        })

    return {
        "active_gates": gates,
        "blind_dual_review": config.require_blind_review,
        "sampling_strategy": config.get_sampling_mode_display(),
        "negative_controls": f"{config.negative_control_percentage}% of AI-rejected papers audited",
        "risk_of_bias_enabled": config.enable_rob_assessment,
        "risk_of_bias_framework": config.get_rob_framework_display(),
        "tie_breaking": config.get_tie_breaker_strategy_display(),
    }


def _format_criteria(crit: Union[List[str], str, None]) -> str:
    if crit is None:
        return ""
    if isinstance(crit, list):
        return "\n".join(str(c).strip() for c in crit if c and str(c).strip())
    return str(crit).strip()


def configure_slr_workspace_logic(
    user,
    workspace_id: Optional[str] = None,
    # Base Workspace parameters
    name: Optional[str] = None,
    abstract_acceptance_criteria: Optional[Union[List[str], str]] = None,
    abstract_rejection_criteria: Optional[Union[List[str], str]] = None,
    full_text_acceptance_criteria: Optional[Union[List[str], str]] = None,
    full_text_rejection_criteria: Optional[Union[List[str], str]] = None,
    screening_llm_model: Optional[str] = None,
    llm_provider: Optional[str] = None,
    reasoning_effort: Optional[str] = None,
    ocr_provider: Optional[str] = None,
    skip_abstract_screening: Optional[bool] = None,
    reprocess_existing: Optional[bool] = None,
    signal_score_code: Optional[str] = None,
    monthly_token_limit: Optional[int] = None,
    cost_limit_usd: Optional[float] = None,
    # Dynamic screening and briefing prompt overrides
    abstract_screening_system_prompt: Optional[str] = None,
    abstract_screening_user_prompt_template: Optional[str] = None,
    abstract_screening_response_schema: Optional[dict] = None,
    abstract_screening_exit_metric: Optional[str] = None,
    full_text_screening_system_prompt: Optional[str] = None,
    full_text_screening_user_prompt_template: Optional[str] = None,
    full_text_screening_response_schema: Optional[dict] = None,
    full_text_screening_exit_metric: Optional[str] = None,
    narrative_report_prompt: Optional[str] = None,
    narrative_report_system_prompt: Optional[str] = None,
    narrative_report_top_n_papers: Optional[int] = None,
    # SLR Policy & Gate parameters (SLRWorkspaceConfig)
    checkpoint_gate_mode: Optional[str] = None,
    enable_extraction_gate: Optional[bool] = None,
    screening_quorum_size: Optional[int] = None,
    extraction_quorum_size: Optional[int] = None,
    require_blind_review: Optional[bool] = None,
    sampling_mode: Optional[str] = None,
    abstract_sample_percentage: Optional[float] = None,
    full_text_sample_percentage: Optional[float] = None,
    extraction_sample_percentage: Optional[float] = None,
    negative_control_percentage: Optional[float] = None,
    enable_rob_assessment: Optional[bool] = None,
    rob_framework: Optional[str] = None,
    require_human_rob_validation: Optional[bool] = None,
    designated_arbiter: Optional[Union[str, int, User]] = None,
    tie_breaker_strategy: Optional[str] = None,
    exclusion_reasons: Optional[Union[List[str], str]] = None,
    require_evidence_on_exclusion: Optional[bool] = None,
    require_evidence_on_override: Optional[bool] = None,
    notify_reviewers_on_pause: Optional[bool] = None,
    stale_queue_reminder_days: Optional[int] = None,
    # Formal Systematic Review Protocol fields
    protocol_title: Optional[str] = None,
    protocol_review_question: Optional[str] = None,
    pico_population: Optional[str] = None,
    pico_intervention: Optional[str] = None,
    pico_comparison: Optional[str] = None,
    pico_outcome: Optional[str] = None,
    study_design_criteria: Optional[str] = None,
    prospero_registration_id: Optional[str] = None,
) -> str:
    """
    Configures all SLR (Systematic Literature Review) parameters side-by-side with Workspace settings.
    If workspace_id is provided, updates the existing workspace and its SLR policy.
    If workspace_id is omitted/None, creates a new SLR Workspace and provisions its SLR policy engine.
    """
    with transaction.atomic():
        # 1. Workspace Resolution or Creation
        is_new_workspace = False
        if workspace_id:
            workspace, membership, error = check_workspace_access(user, workspace_id, required_roles=['admin', 'manager'])
            if error:
                return json.dumps({"status": "error", "error": error}, indent=2)
            
            # Apply base workspace updates if supplied
            ws_fields_to_save = []
            if name is not None:
                workspace.name = name.strip()
                ws_fields_to_save.append('name')
            if abstract_acceptance_criteria is not None:
                workspace.abstract_acceptance_criteria = _format_criteria(abstract_acceptance_criteria)
                ws_fields_to_save.append('abstract_acceptance_criteria')
            if abstract_rejection_criteria is not None:
                workspace.abstract_rejection_criteria = _format_criteria(abstract_rejection_criteria)
                ws_fields_to_save.append('abstract_rejection_criteria')
            if full_text_acceptance_criteria is not None:
                workspace.full_text_acceptance_criteria = _format_criteria(full_text_acceptance_criteria)
                ws_fields_to_save.append('full_text_acceptance_criteria')
            if full_text_rejection_criteria is not None:
                workspace.full_text_rejection_criteria = _format_criteria(full_text_rejection_criteria)
                ws_fields_to_save.append('full_text_rejection_criteria')
            if screening_llm_model is not None:
                workspace.screening_llm_model = screening_llm_model
                ws_fields_to_save.append('screening_llm_model')
            if llm_provider is not None:
                workspace.llm_provider = llm_provider
                ws_fields_to_save.append('llm_provider')
            if reasoning_effort is not None:
                workspace.reasoning_effort = reasoning_effort
                ws_fields_to_save.append('reasoning_effort')
            if ocr_provider is not None:
                norm_ocr = None if str(ocr_provider).lower() == 'none' else ocr_provider
                workspace.ocr_provider = norm_ocr
                ws_fields_to_save.append('ocr_provider')
            if skip_abstract_screening is not None:
                workspace.skip_abstract_screening = bool(skip_abstract_screening)
                ws_fields_to_save.append('skip_abstract_screening')
            if reprocess_existing is not None:
                workspace.reprocess_existing = bool(reprocess_existing)
                ws_fields_to_save.append('reprocess_existing')
            if signal_score_code is not None:
                workspace.signal_score_code = signal_score_code
                ws_fields_to_save.append('signal_score_code')
            if monthly_token_limit is not None:
                workspace.monthly_token_limit = monthly_token_limit
                ws_fields_to_save.append('monthly_token_limit')
            if cost_limit_usd is not None:
                workspace.monthly_usd_limit = cost_limit_usd
                ws_fields_to_save.append('monthly_usd_limit')
            if abstract_screening_system_prompt is not None:
                workspace.abstract_screening_system_prompt = abstract_screening_system_prompt
                ws_fields_to_save.append('abstract_screening_system_prompt')
            if abstract_screening_user_prompt_template is not None:
                workspace.abstract_screening_user_prompt_template = abstract_screening_user_prompt_template
                ws_fields_to_save.append('abstract_screening_user_prompt_template')
            if abstract_screening_response_schema is not None:
                workspace.abstract_screening_response_schema = abstract_screening_response_schema
                ws_fields_to_save.append('abstract_screening_response_schema')
            if abstract_screening_exit_metric is not None:
                workspace.abstract_screening_exit_metric = abstract_screening_exit_metric
                ws_fields_to_save.append('abstract_screening_exit_metric')
            if full_text_screening_system_prompt is not None:
                workspace.full_text_screening_system_prompt = full_text_screening_system_prompt
                ws_fields_to_save.append('full_text_screening_system_prompt')
            if full_text_screening_user_prompt_template is not None:
                workspace.full_text_screening_user_prompt_template = full_text_screening_user_prompt_template
                ws_fields_to_save.append('full_text_screening_user_prompt_template')
            if full_text_screening_response_schema is not None:
                workspace.full_text_screening_response_schema = full_text_screening_response_schema
                ws_fields_to_save.append('full_text_screening_response_schema')
            if full_text_screening_exit_metric is not None:
                workspace.full_text_screening_exit_metric = full_text_screening_exit_metric
                ws_fields_to_save.append('full_text_screening_exit_metric')
            if narrative_report_prompt is not None:
                workspace.narrative_report_prompt = narrative_report_prompt
                ws_fields_to_save.append('narrative_report_prompt')
            if narrative_report_system_prompt is not None:
                workspace.narrative_report_system_prompt = narrative_report_system_prompt
                ws_fields_to_save.append('narrative_report_system_prompt')
            if narrative_report_top_n_papers is not None:
                workspace.narrative_report_top_n_papers = narrative_report_top_n_papers
                ws_fields_to_save.append('narrative_report_top_n_papers')

            if ws_fields_to_save:
                workspace.save(update_fields=ws_fields_to_save)
        else:
            is_new_workspace = True
            if not name or not name.strip():
                return json.dumps({"status": "error", "error": "Workspace name is required when creating a new SLR workspace."}, indent=2)

            workspace, err = create_workspace_record(
                user=user,
                name=name.strip(),
                abstract_acceptance_criteria=abstract_acceptance_criteria,
                abstract_rejection_criteria=abstract_rejection_criteria,
                full_text_acceptance_criteria=full_text_acceptance_criteria,
                full_text_rejection_criteria=full_text_rejection_criteria,
                abstract_screening_system_prompt=abstract_screening_system_prompt,
                abstract_screening_user_prompt_template=abstract_screening_user_prompt_template,
                abstract_screening_response_schema=abstract_screening_response_schema,
                abstract_screening_exit_metric=abstract_screening_exit_metric,
                full_text_screening_system_prompt=full_text_screening_system_prompt,
                full_text_screening_user_prompt_template=full_text_screening_user_prompt_template,
                full_text_screening_response_schema=full_text_screening_response_schema,
                full_text_screening_exit_metric=full_text_screening_exit_metric,
                narrative_report_prompt=narrative_report_prompt,
                narrative_report_system_prompt=narrative_report_system_prompt,
                narrative_report_top_n_papers=narrative_report_top_n_papers or 10,
                ocr_provider=ocr_provider,
                screening_llm_model=screening_llm_model or 'google/gemini-3.8-flash',
                llm_provider=llm_provider or 'google',
                reasoning_effort=reasoning_effort or 'medium',
                monthly_token_limit=monthly_token_limit or 10000000,
                monthly_usd_limit=cost_limit_usd or 100.0,
                signal_score_code=signal_score_code,
                skip_abstract_screening=bool(skip_abstract_screening),
                reprocess_existing=bool(reprocess_existing)
            )
            if err:
                return json.dumps({"status": "error", "error": err}, indent=2)

        # 2. SLR Policy Engine Configuration (SLRWorkspaceConfig)
        slr_config, _ = SLRWorkspaceConfig.objects.get_or_create(workspace=workspace)
        slr_fields_to_save = []

        # Validate & assign gate mode
        if checkpoint_gate_mode is not None:
            valid_gates = [k for k, _ in SLRWorkspaceConfig.GATE_MODES]
            if checkpoint_gate_mode not in valid_gates:
                return json.dumps({
                    "status": "error",
                    "error": f"Invalid checkpoint_gate_mode '{checkpoint_gate_mode}'. Choose from: {valid_gates}"
                }, indent=2)
            slr_config.checkpoint_gate_mode = checkpoint_gate_mode
            slr_fields_to_save.append('checkpoint_gate_mode')

        if enable_extraction_gate is not None:
            slr_config.enable_extraction_gate = bool(enable_extraction_gate)
            slr_fields_to_save.append('enable_extraction_gate')

        # Validate quorum sizes
        if screening_quorum_size is not None:
            if screening_quorum_size < 1 or screening_quorum_size > 6:
                return json.dumps({"status": "error", "error": "screening_quorum_size must be between 1 and 6."}, indent=2)
            slr_config.screening_quorum_size = screening_quorum_size
            slr_fields_to_save.append('screening_quorum_size')

        if extraction_quorum_size is not None:
            if extraction_quorum_size < 1 or extraction_quorum_size > 4:
                return json.dumps({"status": "error", "error": "extraction_quorum_size must be between 1 and 4."}, indent=2)
            slr_config.extraction_quorum_size = extraction_quorum_size
            slr_fields_to_save.append('extraction_quorum_size')

        if require_blind_review is not None:
            slr_config.require_blind_review = bool(require_blind_review)
            slr_fields_to_save.append('require_blind_review')

        # Validate sampling policies
        if sampling_mode is not None:
            valid_sampling = [k for k, _ in SLRWorkspaceConfig.SAMPLING_MODES]
            if sampling_mode not in valid_sampling:
                return json.dumps({
                    "status": "error",
                    "error": f"Invalid sampling_mode '{sampling_mode}'. Choose from: {valid_sampling}"
                }, indent=2)
            slr_config.sampling_mode = sampling_mode
            slr_fields_to_save.append('sampling_mode')

        if abstract_sample_percentage is not None:
            if abstract_sample_percentage < 0.0 or abstract_sample_percentage > 100.0:
                return json.dumps({"status": "error", "error": "abstract_sample_percentage must be between 0.0 and 100.0%"}, indent=2)
            slr_config.abstract_sample_percentage = float(abstract_sample_percentage)
            slr_fields_to_save.append('abstract_sample_percentage')

        if full_text_sample_percentage is not None:
            if full_text_sample_percentage < 0.0 or full_text_sample_percentage > 100.0:
                return json.dumps({"status": "error", "error": "full_text_sample_percentage must be between 0.0 and 100.0%"}, indent=2)
            slr_config.full_text_sample_percentage = float(full_text_sample_percentage)
            slr_fields_to_save.append('full_text_sample_percentage')

        if extraction_sample_percentage is not None:
            if extraction_sample_percentage < 0.0 or extraction_sample_percentage > 100.0:
                return json.dumps({"status": "error", "error": "extraction_sample_percentage must be between 0.0 and 100.0%"}, indent=2)
            slr_config.extraction_sample_percentage = float(extraction_sample_percentage)
            slr_fields_to_save.append('extraction_sample_percentage')

        if negative_control_percentage is not None:
            if negative_control_percentage < 0.0 or negative_control_percentage > 50.0:
                return json.dumps({"status": "error", "error": "negative_control_percentage must be between 0.0 and 50.0%"}, indent=2)
            slr_config.negative_control_percentage = float(negative_control_percentage)
            slr_fields_to_save.append('negative_control_percentage')

        # Validate Risk of Bias
        if enable_rob_assessment is not None:
            slr_config.enable_rob_assessment = bool(enable_rob_assessment)
            slr_fields_to_save.append('enable_rob_assessment')

        if rob_framework is not None:
            valid_rob = [k for k, _ in SLRWorkspaceConfig.ROB_FRAMEWORKS]
            if rob_framework not in valid_rob:
                return json.dumps({
                    "status": "error",
                    "error": f"Invalid rob_framework '{rob_framework}'. Choose from: {valid_rob}"
                }, indent=2)
            slr_config.rob_framework = rob_framework
            slr_fields_to_save.append('rob_framework')

        if require_human_rob_validation is not None:
            slr_config.require_human_rob_validation = bool(require_human_rob_validation)
            slr_fields_to_save.append('require_human_rob_validation')

        # Validate Arbiter and Tie Breaking
        if designated_arbiter is not None:
            if str(designated_arbiter).strip().lower() in ("", "none", "null"):
                slr_config.designated_arbiter = None
                slr_fields_to_save.append('designated_arbiter')
            else:
                arbiter_user = _resolve_user(designated_arbiter)
                if not arbiter_user:
                    return json.dumps({
                        "status": "error",
                        "error": f"Designated arbiter user '{designated_arbiter}' could not be found by username, email, or ID."
                    }, indent=2)
                slr_config.designated_arbiter = arbiter_user
                slr_fields_to_save.append('designated_arbiter')

        if tie_breaker_strategy is not None:
            valid_ties = [k for k, _ in SLRWorkspaceConfig.TIE_STRATEGIES]
            if tie_breaker_strategy not in valid_ties:
                return json.dumps({
                    "status": "error",
                    "error": f"Invalid tie_breaker_strategy '{tie_breaker_strategy}'. Choose from: {valid_ties}"
                }, indent=2)
            slr_config.tie_breaker_strategy = tie_breaker_strategy
            slr_fields_to_save.append('tie_breaker_strategy')

        # Exclusion Reasons Checklist
        if exclusion_reasons is not None:
            if isinstance(exclusion_reasons, str):
                try:
                    parsed = json.loads(exclusion_reasons)
                    if isinstance(parsed, list):
                        exclusion_reasons = parsed
                    else:
                        exclusion_reasons = [exclusion_reasons]
                except Exception:
                    exclusion_reasons = [line.strip() for line in exclusion_reasons.splitlines() if line.strip()]
            reasons_clean = [str(r).strip() for r in exclusion_reasons if str(r).strip()]
            if not reasons_clean:
                reasons_clean = get_default_exclusion_reasons()
            slr_config.exclusion_reasons = reasons_clean
            slr_fields_to_save.append('exclusion_reasons')

        # Grounding & Governance
        if require_evidence_on_exclusion is not None:
            slr_config.require_evidence_on_exclusion = bool(require_evidence_on_exclusion)
            slr_fields_to_save.append('require_evidence_on_exclusion')

        if require_evidence_on_override is not None:
            slr_config.require_evidence_on_override = bool(require_evidence_on_override)
            slr_fields_to_save.append('require_evidence_on_override')

        if notify_reviewers_on_pause is not None:
            slr_config.notify_reviewers_on_pause = bool(notify_reviewers_on_pause)
            slr_fields_to_save.append('notify_reviewers_on_pause')

        if stale_queue_reminder_days is not None:
            slr_config.stale_queue_reminder_days = max(1, int(stale_queue_reminder_days))
            slr_fields_to_save.append('stale_queue_reminder_days')

        if slr_fields_to_save:
            slr_config.save(update_fields=slr_fields_to_save)

        # 3. Formal Protocol Initialization (Optional)
        protocol = None
        has_protocol_input = any([
            protocol_title, protocol_review_question, pico_population,
            pico_intervention, pico_comparison, pico_outcome, prospero_registration_id
        ])
        if has_protocol_input:
            protocol = SLRProtocol.objects.filter(workspace=workspace).order_by('-version').first()
            if not protocol or protocol.is_locked:
                new_version = (protocol.version + 1) if protocol else 1
                protocol = SLRProtocol.objects.create(
                    workspace=workspace,
                    title=protocol_title or f"{workspace.name} Systematic Review Protocol",
                    review_question=protocol_review_question or "Evaluate primary efficacy and safety endpoints in clinical studies.",
                    pico_population=pico_population or "Target patient population.",
                    pico_intervention=pico_intervention or "Intervention under review.",
                    pico_comparison=pico_comparison or "Control / standard of care.",
                    pico_outcome=pico_outcome or "Primary clinical outcome.",
                    study_design_criteria=study_design_criteria or "Randomized controlled trials, prospective cohorts.",
                    prospero_registration_id=prospero_registration_id,
                    version=new_version,
                    created_by=user if user and user.is_authenticated else (slr_config.designated_arbiter or User.objects.first())
                )
            else:
                proto_fields = []
                if protocol_title is not None:
                    protocol.title = protocol_title
                    proto_fields.append('title')
                if protocol_review_question is not None:
                    protocol.review_question = protocol_review_question
                    proto_fields.append('review_question')
                if pico_population is not None:
                    protocol.pico_population = pico_population
                    proto_fields.append('pico_population')
                if pico_intervention is not None:
                    protocol.pico_intervention = pico_intervention
                    proto_fields.append('pico_intervention')
                if pico_comparison is not None:
                    protocol.pico_comparison = pico_comparison
                    proto_fields.append('pico_comparison')
                if pico_outcome is not None:
                    protocol.pico_outcome = pico_outcome
                    proto_fields.append('pico_outcome')
                if study_design_criteria is not None:
                    protocol.study_design_criteria = study_design_criteria
                    proto_fields.append('study_design_criteria')
                if prospero_registration_id is not None:
                    protocol.prospero_registration_id = prospero_registration_id
                    proto_fields.append('prospero_registration_id')
                if proto_fields:
                    protocol.save(update_fields=proto_fields)
        else:
            protocol = SLRProtocol.objects.filter(workspace=workspace).order_by('-version').first()

        response_data = {
            "status": "success",
            "message": f"SLR Workspace '{workspace.name}' {'created' if is_new_workspace else 'updated'} successfully with SLR policy engine.",
            "workspace_id": str(workspace.id),
            "workspace_type": "slr",
            "workspace": {
                "name": workspace.name,
                "screening_llm_model": workspace.screening_llm_model,
                "llm_provider": workspace.llm_provider,
                "reasoning_effort": workspace.reasoning_effort,
                "ocr_provider": workspace.ocr_provider,
                "abstract_acceptance_criteria": workspace.get_abstract_acceptance_criteria(),
                "abstract_rejection_criteria": workspace.get_abstract_rejection_criteria(),
                "full_text_acceptance_criteria": workspace.get_full_text_acceptance_criteria(),
                "full_text_rejection_criteria": workspace.get_full_text_rejection_criteria(),
                "skip_abstract_screening": workspace.skip_abstract_screening,
                "reprocess_existing": workspace.reprocess_existing,
                "monthly_token_limit": workspace.monthly_token_limit,
                "monthly_usd_limit": float(workspace.monthly_usd_limit) if workspace.monthly_usd_limit is not None else 100.0,
            },
            "slr_config": serialize_slr_config(slr_config),
            "protocol": serialize_slr_protocol(protocol),
            "prisma_summary": build_prisma_summary(slr_config),
        }

        return json.dumps(response_data, indent=2, cls=DjangoJSONEncoder)


def get_slr_workspace_config_logic(user, workspace_id: str) -> str:
    """
    Retrieves full SLR review parameters, checkpoint gate policies, PRISMA flow rules,
    and side-by-side Workspace settings for a given workspace.
    """
    workspace, membership, error = check_workspace_access(user, workspace_id)
    if error:
        return json.dumps({"status": "error", "error": error}, indent=2)

    slr_config = SLRWorkspaceConfig.objects.filter(workspace=workspace).first()
    protocol = SLRProtocol.objects.filter(workspace=workspace).order_by('-version').first()

    data = {
        "status": "success",
        "workspace_id": str(workspace.id),
        "name": workspace.name,
        "workspace_type": "slr" if slr_config else "standard",
        "is_slr_configured": bool(slr_config),
        "role": getattr(membership, 'role', 'unknown'),
        "workspace": {
            "name": workspace.name,
            "screening_llm_model": workspace.screening_llm_model,
            "llm_provider": workspace.llm_provider,
            "reasoning_effort": workspace.reasoning_effort,
            "ocr_provider": workspace.ocr_provider,
            "abstract_acceptance_criteria": workspace.get_abstract_acceptance_criteria(),
            "abstract_rejection_criteria": workspace.get_abstract_rejection_criteria(),
            "full_text_acceptance_criteria": workspace.get_full_text_acceptance_criteria(),
            "full_text_rejection_criteria": workspace.get_full_text_rejection_criteria(),
            "abstract_screening_exit_metric": workspace.abstract_screening_exit_metric,
            "full_text_screening_exit_metric": workspace.full_text_screening_exit_metric,
            "skip_abstract_screening": workspace.skip_abstract_screening,
            "reprocess_existing": workspace.reprocess_existing,
            "monthly_token_limit": workspace.monthly_token_limit,
            "monthly_usd_limit": float(workspace.monthly_usd_limit) if workspace.monthly_usd_limit is not None else 100.0,
            "tokens_consumed_this_month": workspace.tokens_consumed_this_month,
            "usd_spent_this_month": float(workspace.usd_spent_this_month),
            "created_at": workspace.created_at.isoformat(),
        },
        "slr_config": serialize_slr_config(slr_config),
        "protocol": serialize_slr_protocol(protocol),
        "prisma_summary": build_prisma_summary(slr_config) if slr_config else None,
    }

    return json.dumps(data, indent=2, cls=DjangoJSONEncoder)
