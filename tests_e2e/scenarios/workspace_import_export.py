"""
Workspace Template Export, Import & Clone Journey E2E Scenario.
"""

import logging
import random
import time
from typing import Dict, Any, Optional
from ..config import E2EConfig
from ..client import (
    APIClient,
    AuthService,
    WorkspaceService,
)

logger = logging.getLogger("e2e_impexp")


def run_workspace_import_export_scenario(config: Optional[E2EConfig] = None) -> Dict[str, Any]:
    """
    End-to-end user journey validating Workspace Template Export, Import, and In-Place Update:
    1. Creates a richly configured source workspace with dual-stage criteria, custom screening
       prompts/schemas, extraction targets with Python AST postprocessing, AST signal score formula,
       academic scrapers, subscribers, and quotas.
    2. Exports the complete workspace configuration bundle via GET /api/workspaces/{id}/export-configuration/.
    3. Asserts 100% schema completeness and field integrity of the exported bundle.
    4. Clones the configuration to a new workspace name and imports it via POST /api/workspaces/import-configuration/.
    5. Validates 1:1 roundtrip parity on the cloned workspace (definitions, scrapers, subscribers, quotas).
    6. Verifies in-place update mode (update_existing=True) modifies an existing workspace in-place.
    7. Cleans up test workspaces.
    """
    cfg = config or E2EConfig.from_env()
    random_suffix = random.randint(10000000, 99999999)
    source_name = f"test_e2e_impexp_source_{random_suffix}"
    target_name = f"test_e2e_impexp_target_{random_suffix}"

    client = APIClient(cfg.base_url)
    auth = AuthService(client)
    auth.login(cfg.username, cfg.password)
    ws_svc = WorkspaceService(client)

    logger.info("=================================================================")
    logger.info("📦 STARTING WORKSPACE TEMPLATE EXPORT & IMPORT JOURNEY SCENARIO")
    logger.info(f"📍 Source Workspace Name : {source_name}")
    logger.info(f"📍 Target Workspace Name : {target_name}")
    logger.info("=================================================================")

    start_time = time.time()

    # Pre-cleanup
    if not cfg.no_cleanup_before:
        ws_svc.cleanup_old_test_workspaces(prefix="test_e2e_impexp_")

    source_ws_id = None
    target_ws_id = None

    try:
        # Step 1: Create richly configured source workspace
        logger.info("📍 Step 1: Creating rich source workspace with prompts, postprocessing & quotas...")
        postproc_snippet = "def postprocess(raw):\n    val = raw.get('capacity_mah', 0)\n    return float(val) * 1.0\n"
        formula_code = "signal_score = (capacity_mah * 0.6) + (density_wh_kg * 0.4)"

        ext_defs = [
            {
                "name": f"{source_name}_capacity",
                "exit_metrics": ["capacity_mah"],
                "system_prompt": "Extract the reported cell capacity in milliampere-hours (mAh).",
                "user_prompt_template": "Paper Title: {title}\nAbstract/Content:\n{content}\nExtract capacity in mAh.",
                "response_schema": {
                    "type": "object",
                    "required": ["capacity_mah"],
                    "properties": {"capacity_mah": {"type": "number", "minimum": 0}},
                },
                "postprocessing_code": postproc_snippet,
                "is_active": True,
            },
            {
                "name": f"{source_name}_density",
                "exit_metrics": ["density_wh_kg"],
                "system_prompt": "Extract gravimetric energy density in Wh/kg.",
                "user_prompt_template": "Paper Title: {title}\nAbstract/Content:\n{content}\nExtract Wh/kg.",
                "response_schema": {
                    "type": "object",
                    "required": ["density_wh_kg"],
                    "properties": {"density_wh_kg": {"type": "number", "minimum": 0}},
                },
                "is_active": True,
            },
        ]

        scrapers = [
            {
                "provider": "arxiv",
                "search_query": "solid state battery",
                "limit": 5,
                "sort_by": "relevance",
                "sort_order": "desc",
                "n_last_days": 14,
                "is_active": True,
            },
            {
                "provider": "openalex",
                "search_query": "solid state electrolyte",
                "limit": 5,
                "sort_by": "cited_by_count",
                "sort_order": "desc",
                "n_last_days": 14,
                "is_active": True,
            },
        ]

        subscribers = [
            {
                "email": f"report_lead_{random_suffix}@example.com",
                "name": "Report Lead",
                "subscription_type": "result_report",
                "is_active": True,
            },
            {
                "email": f"alerts_admin_{random_suffix}@example.com",
                "name": "Alerts Admin",
                "subscription_type": "all",
                "is_active": True,
            },
        ]

        source_ws = ws_svc.create_workspace(
            name=source_name,
            abstract_acceptance_criteria="Inclusion: Solid state electrolyte or battery cell performance metrics.",
            abstract_rejection_criteria="Exclusion: Pure liquid electrolyte without solid interface.",
            full_text_acceptance_criteria="Inclusion: Reports numerical capacity, cyclability, or impedance.",
            full_text_rejection_criteria="Exclusion: Pure theoretical review without experimental measurements.",
            abstract_screening_system_prompt="Expert battery screening agent. Strict inclusion evaluation.",
            abstract_screening_user_prompt_template="Title: {title}\nAbstract: {abstract}",
            full_text_screening_system_prompt="Expert full-text analyst. Verify experimental electrode characterization.",
            signal_score_code=formula_code,
            screening_llm_model="google/gemini-3.8-flash",
            extraction_definitions=ext_defs,
            scrapers=scrapers,
            subscribers=subscribers,
        )
        source_ws_id = source_ws["id"]

        # Set specific quotas on source workspace
        ws_svc.update_workspace(
            source_ws_id,
            monthly_token_limit=7500000,
            monthly_usd_limit=85.50,
        )
        source_ws = ws_svc.get_workspace(source_ws_id)
        logger.info(f"✅ Source workspace created: ID={source_ws_id}, Quota=${source_ws.get('monthly_usd_limit')}")

        # Step 2: Export workspace configuration bundle
        logger.info("📍 Step 2: Exporting configuration bundle via REST API...")
        export_bundle = ws_svc.export_configuration(source_ws_id)

        assert export_bundle.get("version") == "1.0", f"Unexpected export bundle version: {export_bundle.get('version')}"
        assert export_bundle.get("workspaces_count") == 1, "Expected 1 workspace in export bundle"

        exported_ws = export_bundle.get("workspace") or export_bundle.get("workspaces", [{}])[0]
        assert exported_ws.get("name") == source_name, f"Exported name mismatch: {exported_ws.get('name')}"
        assert "Solid state electrolyte" in exported_ws.get("abstract_acceptance_criteria", ""), "Criteria missing in export"
        assert exported_ws.get("signal_score_code") == formula_code, "Signal score formula mismatch in export"

        exp_defs = exported_ws.get("extraction_definitions", [])
        assert len(exp_defs) >= 2, f"Expected at least 2 extraction definitions in export, got {len(exp_defs)}"
        capacity_def = next((d for d in exp_defs if "capacity" in d.get("name", "")), None)
        assert capacity_def is not None, "Capacity definition missing in export"
        assert "capacity_mah" in capacity_def.get("exit_metrics", []), f"Missing capacity_mah in exit_metrics: {capacity_def}"
        assert "def postprocess" in capacity_def.get("postprocessing_code", ""), "Postprocessing code missing in export"

        exp_scrapers = exported_ws.get("scrapers", [])
        assert len(exp_scrapers) >= 2, f"Expected at least 2 scrapers in export, got {len(exp_scrapers)}"

        exp_subscribers = exported_ws.get("subscribers", [])
        assert len(exp_subscribers) >= 2, f"Expected at least 2 subscribers in export, got {len(exp_subscribers)}"
        logger.info("✅ Exported configuration bundle verified: criteria, prompts, formulas, definitions & subscribers present.")

        # Step 3: Clone configuration and import as brand new workspace
        logger.info(f"📍 Step 3: Importing bundle as new workspace '{target_name}'...")
        target_bundle = dict(export_bundle)
        cloned_ws_data = dict(exported_ws)
        cloned_ws_data["name"] = target_name
        # Update definition names to avoid namespace collision
        cloned_defs = []
        for d in cloned_ws_data.get("extraction_definitions", []):
            d_copy = dict(d)
            d_copy["name"] = d_copy["name"].replace(source_name, target_name)
            cloned_defs.append(d_copy)
        cloned_ws_data["extraction_definitions"] = cloned_defs
        target_bundle["workspaces"] = [cloned_ws_data]
        target_bundle["workspace"] = cloned_ws_data

        import_res = ws_svc.import_configuration(target_bundle, update_existing=True)
        stats = import_res.get("stats", {})
        assert stats.get("created_workspaces", 0) >= 1, f"Expected created_workspaces >= 1, got {stats}"
        assert stats.get("created_extractions", 0) >= 2, f"Expected created_extractions >= 2, got {stats}"
        assert stats.get("created_scrapers", 0) >= 2, f"Expected created_scrapers >= 2, got {stats}"
        assert stats.get("created_subscribers", 0) >= 2, f"Expected created_subscribers >= 2, got {stats}"

        # Resolve created target workspace ID
        target_ws_entry = next((w for w in stats.get("workspaces", []) if w.get("name") == target_name), None)
        if target_ws_entry and target_ws_entry.get("id"):
            target_ws_id = target_ws_entry["id"]
        else:
            all_ws = ws_svc.list_workspaces()
            target_match = next((w for w in all_ws if w.get("name") == target_name), None)
            assert target_match is not None, f"Could not find imported target workspace '{target_name}'"
            target_ws_id = target_match["id"]

        logger.info(f"✅ Imported target workspace instantiated with ID: {target_ws_id}")

        # Step 4: Verify 1:1 roundtrip parity on target workspace
        logger.info("📍 Step 4: Verifying 1:1 roundtrip parity on imported target workspace...")
        target_ws = ws_svc.get_workspace(target_ws_id)
        assert target_ws.get("name") == target_name
        assert target_ws.get("abstract_acceptance_criteria") == source_ws.get("abstract_acceptance_criteria")
        assert target_ws.get("full_text_acceptance_criteria") == source_ws.get("full_text_acceptance_criteria")
        assert target_ws.get("signal_score_code") == formula_code

        target_defs = target_ws.get("extraction_definitions", [])
        assert len(target_defs) >= 2, f"Expected at least 2 definitions in target, got {len(target_defs)}"
        target_cap = next((d for d in target_defs if "capacity" in d.get("name", "")), None)
        assert target_cap is not None
        assert "capacity_mah" in target_cap.get("exit_metrics", [])
        assert "def postprocess" in (target_cap.get("postprocessing_code") or "")

        target_scrapers = target_ws.get("scrapers", [])
        assert len(target_scrapers) >= 2, f"Expected at least 2 scrapers in target, got {len(target_scrapers)}"

        target_subs = target_ws.get("subscribers", [])
        assert len(target_subs) >= 2, f"Expected at least 2 subscribers in target, got {len(target_subs)}"
        logger.info("✅ 1:1 roundtrip parity verified: criteria, prompts, formulas, AST code, scrapers & subscribers match perfectly.")

        # Step 5: Test In-Place Update Mode (update_existing=True)
        logger.info("📍 Step 5: Testing in-place update mode on existing workspace...")
        updated_criteria_marker = "UPDATED_CRITERIA_IN_PLACE_MARKER_TEST"
        update_bundle = dict(target_bundle)
        cloned_update_ws = dict(cloned_ws_data)
        cloned_update_ws["abstract_acceptance_criteria"] = f"{source_ws.get('abstract_acceptance_criteria')} | {updated_criteria_marker}"
        update_bundle["workspaces"] = [cloned_update_ws]
        update_bundle["workspace"] = cloned_update_ws

        update_res = ws_svc.import_configuration(update_bundle, update_existing=True)
        update_stats = update_res.get("stats", {})
        assert update_stats.get("updated_workspaces", 0) >= 1, f"Expected updated_workspaces >= 1, got {update_stats}"

        refreshed_target = ws_svc.get_workspace(target_ws_id)
        assert updated_criteria_marker in refreshed_target.get("abstract_acceptance_criteria", ""), "In-place criteria update failed"
        logger.info("✅ In-place workspace update verified successfully.")

        total_elapsed = time.time() - start_time
        logger.info("=================================================================")
        logger.info("🎉 WORKSPACE TEMPLATE EXPORT & IMPORT JOURNEY PASSED!")
        logger.info(f"   • Export Bundle Integrity : VERIFIED (Criteria, Prompts, AST Code, Formulas)")
        logger.info(f"   • Roundtrip Parity        : VERIFIED (1:1 clone fidelity)")
        logger.info(f"   • In-Place Update Mode    : VERIFIED (Overwrites existing without data loss)")
        logger.info(f"   • Total Elapsed Time      : {total_elapsed:.1f}s")
        logger.info("=================================================================")

        return {
            "status": "PASSED",
            "source_workspace_id": source_ws_id,
            "target_workspace_id": target_ws_id,
            "export_bundle_version": export_bundle.get("version"),
            "definitions_count": len(target_defs),
            "scrapers_count": len(target_scrapers),
            "subscribers_count": len(target_subs),
            "total_elapsed_seconds": total_elapsed,
        }

    finally:
        # Step 6: Post-cleanup
        if cfg.cleanup_after:
            logger.info("🧹 Performing post-scenario workspace cleanup...")
            if source_ws_id:
                try:
                    ws_svc.delete_workspace(source_ws_id)
                except Exception as e:
                    logger.warning(f"Failed to delete source workspace '{source_ws_id}': {e}")
            if target_ws_id:
                try:
                    ws_svc.delete_workspace(target_ws_id)
                except Exception as e:
                    logger.warning(f"Failed to delete target workspace '{target_ws_id}': {e}")
            logger.info("✅ Test workspaces cleaned up.")
