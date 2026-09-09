import uuid
import logging
from typing import Optional, Tuple, List, Dict, Any, Union
from django.contrib.auth import get_user_model
from research_intelligence.models import Workspace, WorkspaceMember

logger = logging.getLogger(__name__)
User = get_user_model()


def check_workspace_access(
    user,
    workspace_id: Union[str, uuid.UUID],
    required_roles: Optional[List[str]] = None
) -> Tuple[Optional[Workspace], Optional[WorkspaceMember], Optional[str]]:
    """
    Verifies that a user has authorized access to a workspace with the required role.

    Returns:
        (workspace, membership, None) on success.
        (None, None, error_message) on failure.
    """
    if isinstance(workspace_id, uuid.UUID):
        ws_uuid = workspace_id
    else:
        try:
            ws_uuid = uuid.UUID(str(workspace_id))
        except (ValueError, TypeError):
            return None, None, f"Error: '{workspace_id}' is not a valid UUID."

    try:
        workspace = Workspace.objects.get(id=ws_uuid)
    except Workspace.DoesNotExist:
        return None, None, f"Error: Workspace with ID '{workspace_id}' does not exist."

    try:
        membership = WorkspaceMember.objects.get(workspace=workspace, user=user)
    except WorkspaceMember.DoesNotExist:
        return None, None, f"Error: Access denied. User '{user}' is not a member of workspace '{workspace.name}'."

    if required_roles and membership.role not in required_roles:
        return None, None, (
            f"Error: Insufficient workspace permissions. Role '{membership.role}' required to be one of "
            f"{required_roles} for this operation."
        )

    return workspace, membership, None


def get_user_accessible_workspaces(user):
    """
    Returns a QuerySet of all workspaces accessible to the user,
    along with a dictionary mapping workspace_id -> member_role.
    """
    memberships = {m.workspace_id: m.role for m in WorkspaceMember.objects.filter(user=user)}
    workspaces = Workspace.objects.filter(id__in=memberships.keys()).order_by('-created_at')
    return workspaces, memberships


def create_workspace_record(
    user,
    name: str,
    abstract_acceptance_criteria: Union[List[str], str] = None,
    abstract_rejection_criteria: Union[List[str], str] = None,
    full_text_acceptance_criteria: Union[List[str], str] = None,
    full_text_rejection_criteria: Union[List[str], str] = None,
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
    narrative_report_top_n_papers: Optional[int] = 10,
    ocr_provider: Optional[str] = None,
    llm_provider: str = "google",
    screening_llm_model: str = "google/gemini-3.8-flash",
    reasoning_effort: str = "medium",
    signal_score_code: Optional[str] = None,
    monthly_token_limit: int = 10000000,
    monthly_usd_limit: float = 100.0,
    skip_abstract_screening: bool = False,
    reprocess_existing: bool = False
) -> Tuple[Optional[Workspace], Optional[str]]:
    """
    Creates a new Workspace domain record, formats screening criteria, and establishes admin membership.
    """
    if not name or not name.strip():
        return None, "Workspace name cannot be empty."

    def _format_criteria(crit):
        if crit is None:
            return ""
        if isinstance(crit, list):
            return "\n".join(str(c).strip() for c in crit if c and str(c).strip())
        return str(crit).strip()

    valid_ocr = ["pypdf", "mistral", "gemini", "none", None]
    if ocr_provider is not None and str(ocr_provider).lower() == "none":
        ocr_provider = None
    elif ocr_provider and ocr_provider not in valid_ocr:
        return None, f"Error: Invalid ocr_provider '{ocr_provider}'. Choose from {valid_ocr}."

    valid_llm = ["google", "openrouter"]
    if llm_provider not in valid_llm:
        return None, f"Error: Invalid llm_provider '{llm_provider}'. Choose from {valid_llm}."

    workspace = Workspace.objects.create(
        name=name.strip(),
        abstract_acceptance_criteria=_format_criteria(abstract_acceptance_criteria),
        abstract_rejection_criteria=_format_criteria(abstract_rejection_criteria),
        full_text_acceptance_criteria=_format_criteria(full_text_acceptance_criteria),
        full_text_rejection_criteria=_format_criteria(full_text_rejection_criteria),
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
        narrative_report_top_n_papers=narrative_report_top_n_papers if narrative_report_top_n_papers is not None else 10,
        ocr_provider=ocr_provider,
        llm_provider=llm_provider,
        screening_llm_model=screening_llm_model,
        reasoning_effort=reasoning_effort or "medium",
        signal_score_code=signal_score_code,
        monthly_token_limit=monthly_token_limit if monthly_token_limit is not None else 10000000,
        monthly_usd_limit=monthly_usd_limit if monthly_usd_limit is not None else 100.0,
        skip_abstract_screening=bool(skip_abstract_screening),
        reprocess_existing=bool(reprocess_existing)
    )

    if user and not getattr(user, "is_anonymous", False) and getattr(user, "pk", None):
        WorkspaceMember.objects.create(
            workspace=workspace,
            user=user,
            role="admin"
        )

    return workspace, None


def serialize_workspace_configuration(workspace: Workspace) -> dict:
    """
    Serializes complete workspace configuration bundle including dual-stage criteria,
    dynamic screening prompts/schemas, exit metrics, signal scoring code, quotas,
    associated extraction definitions, data scrapers, and subscribers.
    """
    return {
        "name": workspace.name,
        "ocr_provider": workspace.ocr_provider,
        "screening_llm_model": workspace.screening_llm_model,
        "llm_provider": workspace.llm_provider,
        "reasoning_effort": workspace.reasoning_effort,
        "skip_abstract_screening": workspace.skip_abstract_screening,
        "reprocess_existing": workspace.reprocess_existing,
        "monthly_token_limit": workspace.monthly_token_limit,
        "monthly_usd_limit": float(workspace.monthly_usd_limit) if workspace.monthly_usd_limit is not None else 100.0,
        "signal_score_code": workspace.signal_score_code,
        "abstract_acceptance_criteria": workspace.abstract_acceptance_criteria,
        "abstract_rejection_criteria": workspace.abstract_rejection_criteria,
        "abstract_screening_system_prompt": workspace.abstract_screening_system_prompt,
        "abstract_screening_user_prompt_template": workspace.abstract_screening_user_prompt_template,
        "abstract_screening_response_schema": workspace.abstract_screening_response_schema,
        "abstract_screening_exit_metric": workspace.abstract_screening_exit_metric,
        "full_text_acceptance_criteria": workspace.full_text_acceptance_criteria,
        "full_text_rejection_criteria": workspace.full_text_rejection_criteria,
        "full_text_screening_system_prompt": workspace.full_text_screening_system_prompt,
        "full_text_screening_user_prompt_template": workspace.full_text_screening_user_prompt_template,
        "full_text_screening_response_schema": workspace.full_text_screening_response_schema,
        "full_text_screening_exit_metric": workspace.full_text_screening_exit_metric,
        "narrative_report_prompt": workspace.narrative_report_prompt,
        "narrative_report_system_prompt": workspace.narrative_report_system_prompt,
        "narrative_report_top_n_papers": workspace.narrative_report_top_n_papers,
        "extraction_definitions": [
            {
                "name": ed.name,
                "system_prompt": ed.system_prompt,
                "user_prompt_template": ed.user_prompt_template,
                "response_schema": ed.response_schema,
                "exit_metrics": ed.get_exit_metrics_list(),
                "primary_frontend_metric": ed.primary_frontend_metric or None,
                "secondary_frontend_metrics": ed.get_secondary_frontend_metrics_list(),
                "postprocessing_code": ed.postprocessing_code or "",
                "llm_model": ed.llm_model,
                "version": ed.version,
                "requires_consensus": ed.requires_consensus,
                "is_active": ed.is_active,
            }
            for ed in workspace.extraction_definitions.all().order_by("name")
        ],
        "scrapers": [
            {
                "provider": sc.provider,
                "search_query": sc.search_query,
                "limit": sc.limit,
                "sort_by": sc.sort_by,
                "sort_order": sc.sort_order,
                "n_last_days": sc.n_last_days,
                "is_active": sc.is_active,
            }
            for sc in workspace.scrapers.all().order_by("provider", "search_query")
        ],
        "subscribers": [
            {
                "email": sub.email,
                "name": sub.name,
                "subscription_type": sub.subscription_type,
                "is_active": sub.is_active,
            }
            for sub in workspace.subscribers.all().order_by("email", "subscription_type")
        ]
    }


def import_workspace_configuration_bundle(
    data: Union[dict, list],
    user=None,
    update_existing: bool = True,
    allow_superuser: bool = False
) -> dict:
    """
    Imports and upserts workspace configuration bundles.
    Supports single workspace dict, list of workspaces, or {version: '...', workspaces: [...]}.
    """
    from research_intelligence.models import ExtractionDefinition, Scraper, Subscriber

    if isinstance(data, dict):
        if "workspaces" in data and isinstance(data["workspaces"], list):
            workspaces_list = data["workspaces"]
        elif "name" in data:
            workspaces_list = [data]
        else:
            raise ValueError("Invalid workspace configuration JSON format. Expected workspace object or list.")
    elif isinstance(data, list):
        workspaces_list = data
    else:
        raise ValueError("Invalid payload type. Expected JSON object or list.")

    stats = {
        "created_workspaces": 0,
        "updated_workspaces": 0,
        "skipped_workspaces": 0,
        "created_extractions": 0,
        "updated_extractions": 0,
        "skipped_extractions": 0,
        "created_scrapers": 0,
        "updated_scrapers": 0,
        "skipped_scrapers": 0,
        "created_subscribers": 0,
        "updated_subscribers": 0,
        "skipped_subscribers": 0,
        "workspaces": [],
    }

    for ws_data in workspaces_list:
        if not isinstance(ws_data, dict) or not ws_data.get("name"):
            continue

        name = ws_data["name"].strip()
        ws_fields = {
            "ocr_provider": ws_data.get("ocr_provider"),
            "screening_llm_model": ws_data.get("screening_llm_model", "google/gemini-3.8-flash"),
            "llm_provider": ws_data.get("llm_provider", "google"),
            "reasoning_effort": ws_data.get("reasoning_effort", "medium"),
            "skip_abstract_screening": bool(ws_data.get("skip_abstract_screening", False)),
            "reprocess_existing": bool(ws_data.get("reprocess_existing", False)),
            "monthly_token_limit": ws_data.get("monthly_token_limit", 10000000),
            "monthly_usd_limit": ws_data.get("monthly_usd_limit", 100.0),
            "signal_score_code": ws_data.get("signal_score_code"),
            "abstract_acceptance_criteria": ws_data.get("abstract_acceptance_criteria", ""),
            "abstract_rejection_criteria": ws_data.get("abstract_rejection_criteria", ""),
            "abstract_screening_system_prompt": ws_data.get("abstract_screening_system_prompt"),
            "abstract_screening_user_prompt_template": ws_data.get("abstract_screening_user_prompt_template"),
            "abstract_screening_response_schema": ws_data.get("abstract_screening_response_schema"),
            "abstract_screening_exit_metric": ws_data.get("abstract_screening_exit_metric"),
            "full_text_acceptance_criteria": ws_data.get("full_text_acceptance_criteria", ""),
            "full_text_rejection_criteria": ws_data.get("full_text_rejection_criteria", ""),
            "full_text_screening_system_prompt": ws_data.get("full_text_screening_system_prompt"),
            "full_text_screening_user_prompt_template": ws_data.get("full_text_screening_user_prompt_template"),
            "full_text_screening_response_schema": ws_data.get("full_text_screening_response_schema"),
            "full_text_screening_exit_metric": ws_data.get("full_text_screening_exit_metric"),
            "narrative_report_prompt": ws_data.get("narrative_report_prompt"),
            "narrative_report_system_prompt": ws_data.get("narrative_report_system_prompt"),
            "narrative_report_top_n_papers": ws_data.get("narrative_report_top_n_papers", 10),
        }

        existing_ws = Workspace.objects.filter(name=name).first()
        if existing_ws:
            if user and not getattr(user, "is_anonymous", False) and getattr(user, "pk", None):
                can_manage = (
                    (allow_superuser and getattr(user, "is_superuser", False))
                    or WorkspaceMember.objects.filter(
                        workspace=existing_ws,
                        user=user,
                        role__in=["admin", "manager"]
                    ).exists()
                )
                if not can_manage:
                    stats["skipped_workspaces"] += 1
                    continue

            if update_existing:
                for k, v in ws_fields.items():
                    setattr(existing_ws, k, v)
                existing_ws.save()
                stats["updated_workspaces"] += 1
            else:
                stats["skipped_workspaces"] += 1
            ws = existing_ws
        else:
            ws = Workspace.objects.create(name=name, **ws_fields)
            stats["created_workspaces"] += 1
            # Ensure importing user is workspace admin for newly created workspace
            if user and not getattr(user, "is_anonymous", False) and getattr(user, "pk", None):
                WorkspaceMember.objects.get_or_create(
                    workspace=ws,
                    user=user,
                    defaults={"role": "admin"}
                )

        stats["workspaces"].append(ws)

        # Extraction definitions
        for ed_data in ws_data.get("extraction_definitions", []):
            if not isinstance(ed_data, dict) or not ed_data.get("name"):
                continue
            ed_name = ed_data["name"].strip()
            exit_m = ed_data.get("exit_metrics")
            if isinstance(exit_m, list):
                exit_m = ", ".join(str(m).strip() for m in exit_m if str(m).strip())
            elif exit_m:
                exit_m = str(exit_m)

            prim_f = ed_data.get("primary_frontend_metric") or ed_data.get("primary_frontend_metrics")
            if isinstance(prim_f, (list, tuple)):
                prim_f = str(prim_f[0]).strip() if prim_f else None
            elif prim_f:
                prim_f = str(prim_f).strip() or None

            sec_f = ed_data.get("secondary_frontend_metrics")
            if isinstance(sec_f, (list, tuple)):
                sec_f = ", ".join(str(m).strip() for m in sec_f if str(m).strip())
            elif sec_f:
                sec_f = str(sec_f).strip() or ""

            ed_fields = {
                "system_prompt": ed_data.get("system_prompt", ""),
                "user_prompt_template": ed_data.get("user_prompt_template", ""),
                "response_schema": ed_data.get("response_schema", {}),
                "exit_metrics": exit_m,
                "primary_frontend_metric": prim_f,
                "secondary_frontend_metrics": sec_f,
                "postprocessing_code": ed_data.get("postprocessing_code"),
                "llm_model": ed_data.get("llm_model", "google/gemini-3.8-flash"),
                "version": ed_data.get("version", 1),
                "requires_consensus": bool(ed_data.get("requires_consensus", False)),
                "is_active": bool(ed_data.get("is_active", True)),
            }
            existing_ed = ws.extraction_definitions.filter(name=ed_name).first()
            if existing_ed:
                if update_existing:
                    for k, v in ed_fields.items():
                        setattr(existing_ed, k, v)
                    existing_ed.save()
                    stats["updated_extractions"] += 1
                else:
                    stats["skipped_extractions"] += 1
            else:
                ExtractionDefinition.objects.create(workspace=ws, name=ed_name, **ed_fields)
                stats["created_extractions"] += 1

        # Scrapers
        for sc_data in ws_data.get("scrapers", []):
            if not isinstance(sc_data, dict) or not sc_data.get("search_query") or not sc_data.get("provider"):
                continue
            sc_provider = sc_data["provider"].strip().lower()
            sc_query = sc_data["search_query"].strip()
            n_days = sc_data.get("n_last_days")
            sc_fields = {
                "limit": sc_data.get("limit", 50),
                "sort_by": sc_data.get("sort_by", "relevance"),
                "sort_order": sc_data.get("sort_order", "desc"),
                "n_last_days": n_days if n_days is not None else 7,
                "is_active": bool(sc_data.get("is_active", True)),
            }
            existing_sc = ws.scrapers.filter(provider=sc_provider, search_query=sc_query).first()
            if existing_sc:
                if update_existing:
                    for k, v in sc_fields.items():
                        setattr(existing_sc, k, v)
                    existing_sc.save()
                    stats["updated_scrapers"] += 1
                else:
                    stats["skipped_scrapers"] += 1
            else:
                Scraper.objects.create(workspace=ws, provider=sc_provider, search_query=sc_query, **sc_fields)
                stats["created_scrapers"] += 1

        # Subscribers
        for sub_data in ws_data.get("subscribers", []):
            if not isinstance(sub_data, dict) or not sub_data.get("email"):
                continue
            sub_email = sub_data["email"].strip().lower()
            sub_type = sub_data.get("subscription_type", "result_report")
            sub_fields = {
                "name": sub_data.get("name"),
                "is_active": bool(sub_data.get("is_active", True)),
            }
            existing_sub = ws.subscribers.filter(email=sub_email, subscription_type=sub_type).first()
            if existing_sub:
                if update_existing:
                    for k, v in sub_fields.items():
                        setattr(existing_sub, k, v)
                    existing_sub.save()
                    stats["updated_subscribers"] += 1
                else:
                    stats["skipped_subscribers"] += 1
            else:
                Subscriber.objects.create(workspace=ws, email=sub_email, subscription_type=sub_type, **sub_fields)
                stats["created_subscribers"] += 1

    return stats
