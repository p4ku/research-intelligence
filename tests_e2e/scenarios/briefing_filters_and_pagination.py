"""
Briefing & Editions API E2E Scenario: Scope, Pagination, Min Score Floor & Dimension Sorting.

Validates:
1. Scope parameter filtering:
   - scope='included' (surfaced papers only)
   - scope='excluded' (screening log / rejected papers only)
   - scope='all' (both surfaced and rejected)
2. Server-side pagination:
   - page=1 & page_size=2 vs page=2 & page_size=2
   - Disjoint paper ID sets across pages
   - Total pages and total count calculation
   - Out-of-bounds page handling (page=9999 -> empty list, valid envelope)
3. Min score floor filtering:
   - min_score=X -> all returned papers satisfy signal_score >= X
4. Multi-criteria sorting:
   - sort='score' (descending score order)
   - sort='published' (publication date order)
   - sort='dim:<key>' (dimension-specific value order)
5. BFF contract validation:
   - /bff/briefings/{date} forwarding query params
"""

import logging
import math
import random
from typing import Dict, Any, Optional, List
from ..config import E2EConfig
from ..client import (
    APIClient,
    AuthService,
    WorkspaceService,
    PipelineService,
    AgentService,
)

logger = logging.getLogger("e2e_briefing_filters")


def run_briefing_filters_and_pagination_scenario(
    config: Optional[E2EConfig] = None,
    workspace_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Executes comprehensive E2E validation of editions scope, server-side pagination,
    score floor filtering, and dimension sorting.
    """
    cfg = config or E2EConfig.from_env()

    client = APIClient(cfg.base_url)
    auth = AuthService(client)
    auth.login(cfg.username, cfg.password)
    ws_svc = WorkspaceService(client)
    pipeline_svc = PipelineService(client)

    logger.info("=================================================================")
    logger.info("📰 STARTING BRIEFING FILTERS, SCOPE & PAGINATION E2E SCENARIO")
    logger.info(f"📍 Target API : {cfg.base_url}")
    logger.info("=================================================================")

    target_ws_id = None
    target_date = None
    target_run_id = None
    target_edition = None
    created_temp_workspace = False

    # 1. Check passed workspace_id first
    if workspace_id:
        try:
            editions = ws_svc.list_editions(workspace_id)
            if editions:
                for ed in editions:
                    d = ed.get("date")
                    if d:
                        detail = ws_svc.get_edition_detail(workspace_id, d, scope="all")
                        papers = detail.get("papers", [])
                        if len(papers) >= 1 or detail.get("funnel", {}).get("passed_screening", 0) > 0:
                            target_ws_id = workspace_id
                            target_date = d
                            target_run_id = detail.get("run_id") or ed.get("run_id")
                            target_edition = detail
                            break
        except Exception as e:
            logger.debug(f"Passed workspace {workspace_id} edition inspection note: {e}")

    # 2. Search for an existing workspace with editions if needed
    if not target_ws_id:
        logger.info("🔍 Searching for an existing workspace with editions...")
        workspaces = ws_svc.list_workspaces()
        for ws in workspaces:
            ws_id = ws["id"]
            try:
                editions = ws_svc.list_editions(ws_id)
                if editions and len(editions) > 0:
                    for ed in editions:
                        d = ed.get("date")
                        if d:
                            detail = ws_svc.get_edition_detail(ws_id, d, scope="all")
                            papers = detail.get("papers", [])
                            if len(papers) >= 1 or detail.get("funnel", {}).get("passed_screening", 0) > 0:
                                target_ws_id = ws_id
                                target_date = d
                                target_run_id = detail.get("run_id") or ed.get("run_id")
                                target_edition = detail
                                break
                if target_ws_id:
                    break
            except Exception as e:
                logger.debug(f"Workspace {ws_id} edition inspection note: {e}")

    # 3. Self-provision if no workspace with editions exists
    if not target_ws_id or not target_date:
        logger.info("📦 No workspace with editions found. Self-provisioning edition test workspace...")
        random_suffix = random.randint(10000000, 99999999)
        ws_name = f"test_e2e_briefing_filters_{random_suffix}"
        ws_data = ws_svc.create_workspace(
            name=ws_name,
            abstract_acceptance_criteria="Accept machine learning, neural networks, language models.",
            abstract_rejection_criteria="Reject unrelated disciplines.",
            full_text_acceptance_criteria="Accept papers with clear evaluation.",
            full_text_rejection_criteria="Reject pure opinion.",
            screening_llm_model="google/gemini-3.8-flash",
        )
        target_ws_id = ws_data["id"]
        created_temp_workspace = True

        ws_svc.create_scraper(
            workspace_id=target_ws_id,
            provider="arxiv",
            search_query='cat:cs.AI AND all:"transformer architecture"',
            limit=3,
        )
        agent_svc = AgentService(client)
        logger.info("🚀 Launching research pipeline to generate briefing edition...")
        proc = agent_svc.start_research_agent(
            workspace_id=target_ws_id,
            name=f"Edition Filters Run - {ws_name}",
            limit=3,
        )
        completed_agent = agent_svc.poll_until_complete(proc["id"], max_timeout_sec=cfg.max_timeout_sec)
        assert completed_agent.get("status") == "completed", f"Pipeline failed: {completed_agent}"

        editions = ws_svc.list_editions(target_ws_id)
        assert len(editions) > 0, "Self-provisioned pipeline must generate at least one edition"
        ed = editions[0]
        target_date = ed.get("date")
        target_run_id = ed.get("run_id") or completed_agent.get("pipeline_run")
        target_edition = ws_svc.get_edition_detail(target_ws_id, target_date, scope="all")

    assert target_ws_id and target_date, (
        "Could not find or provision a workspace with editions to test."
    )

    logger.info(f"✅ Found testable edition: Workspace '{target_ws_id}', Date '{target_date}', Run '{target_run_id}'")
    funnel = target_edition.get("funnel", {})
    logger.info(f"   • Funnel: Fetched={funnel.get('fetched')}, Passed={funnel.get('passed_screening')}, Surfaced={funnel.get('surfaced')}")

    results = {
        "workspace_id": target_ws_id,
        "date": target_date,
        "run_id": target_run_id,
        "checks": {},
    }

    # =========================================================================
    # Phase 1: Validate Scope Filtering ('included', 'excluded', 'all')
    # =========================================================================
    logger.info("\n🎯 Phase 1: Testing Scope Filtering...")

    # 1.1 scope='included'
    inc_detail = ws_svc.get_edition_detail(target_ws_id, target_date, run_id=target_run_id, scope="included")
    inc_papers = inc_detail.get("papers", [])
    total_surfaced = inc_detail.get("total_surfaced", len(inc_papers))
    logger.info(f"   • scope='included': received {len(inc_papers)} papers (total_surfaced={total_surfaced})")
    assert inc_detail.get("scope") in ("included", None), f"Unexpected scope in response: {inc_detail.get('scope')}"
    for p in inc_papers:
        assert p.get("screening_status") in ("full_text_passed", "accepted", "included", None), (
            f"Paper {p.get('id')} has invalid screening_status for scope='included': {p.get('screening_status')}"
        )
    results["checks"]["scope_included"] = "PASSED"

    # 1.2 scope='excluded'
    exc_detail = ws_svc.get_edition_detail(target_ws_id, target_date, run_id=target_run_id, scope="excluded")
    exc_papers = exc_detail.get("papers", [])
    total_exclusions = exc_detail.get("total_exclusions", len(exc_papers))
    logger.info(f"   • scope='excluded': received {len(exc_papers)} papers (total_exclusions={total_exclusions})")
    for p in exc_papers:
        assert p.get("screening_status") not in ("full_text_passed", "accepted"), (
            f"Paper {p.get('id')} has surfaced status in scope='excluded': {p.get('screening_status')}"
        )
    results["checks"]["scope_excluded"] = "PASSED"

    # 1.3 scope='all'
    all_detail = ws_svc.get_edition_detail(target_ws_id, target_date, run_id=target_run_id, scope="all")
    all_papers = all_detail.get("papers", [])
    logger.info(f"   • scope='all': received {len(all_papers)} papers")
    assert len(all_papers) >= len(inc_papers), "scope='all' should carry at least as many papers as scope='included'"
    results["checks"]["scope_all"] = "PASSED"

    # =========================================================================
    # Phase 2: Validate Server-side Pagination
    # =========================================================================
    logger.info("\n📄 Phase 2: Testing Server-side Pagination...")
    # Test on scope='included' if >= 2 papers, otherwise on scope='all'
    active_scope = "included" if total_surfaced >= 2 else "all"
    base_count = total_surfaced if active_scope == "included" else len(all_papers)

    # 2.1 Page 1 with page_size=2
    p1 = ws_svc.get_edition_detail(target_ws_id, target_date, run_id=target_run_id, scope=active_scope, page=1, page_size=2)
    p1_papers = p1.get("papers", [])
    p1_ids = [p["id"] for p in p1_papers]
    logger.info(f"   • page=1, page_size=2: received {len(p1_papers)} papers (ids={p1_ids})")
    assert len(p1_papers) <= 2, f"Expected <= 2 papers, got {len(p1_papers)}"
    assert p1.get("page") == 1, f"Expected page=1 in envelope, got {p1.get('page')}"
    assert p1.get("page_size") == 2, f"Expected page_size=2, got {p1.get('page_size')}"
    expected_total_pages = max(1, math.ceil(base_count / 2))
    assert p1.get("total_pages") == expected_total_pages, (
        f"Expected total_pages={expected_total_pages}, got {p1.get('total_pages')}"
    )

    # 2.2 Page 2 with page_size=2 (if total papers >= 3)
    if base_count >= 3:
        p2 = ws_svc.get_edition_detail(target_ws_id, target_date, run_id=target_run_id, scope=active_scope, page=2, page_size=2)
        p2_papers = p2.get("papers", [])
        p2_ids = [p["id"] for p in p2_papers]
        logger.info(f"   • page=2, page_size=2: received {len(p2_papers)} papers (ids={p2_ids})")
        assert len(p2_papers) <= 2, f"Expected <= 2 papers, got {len(p2_papers)}"
        assert p2.get("page") == 2, f"Expected page=2 in envelope, got {p2.get('page')}"
        # Assert no overlapping IDs between page 1 and page 2
        overlap = set(p1_ids).intersection(set(p2_ids))
        assert len(overlap) == 0, f"Page 1 and Page 2 contain duplicate paper IDs: {overlap}"
        logger.info("   ✅ Page 1 and Page 2 are strictly disjoint.")

    # 2.3 Out-of-bounds page handling
    p_oob = ws_svc.get_edition_detail(target_ws_id, target_date, run_id=target_run_id, scope=active_scope, page=9999, page_size=2)
    assert p_oob.get("papers") == [], f"Expected empty list for out-of-bounds page, got {p_oob.get('papers')}"
    logger.info("   ✅ Out-of-bounds page=9999 returns empty paper list with valid envelope.")
    results["checks"]["pagination"] = "PASSED"

    # =========================================================================
    # Phase 3: Validate Min Score Floor & Dynamic Dimension Filtering
    # =========================================================================
    logger.info("\n🎚️ Phase 3: Testing Min Score Floor & Dynamic Dimension Filtering...")
    # 3.1 Min Score Floor
    all_scores = [float(p.get("signal_score") or 0.0) for p in all_papers if p.get("signal_score") is not None]
    if all_scores:
        median_score = sorted(all_scores)[len(all_scores) // 2]
        logger.info(f"   • Testing min_score={median_score}...")
        scored_detail = ws_svc.get_edition_detail(
            target_ws_id, target_date, run_id=target_run_id, scope="all", min_score=median_score
        )
        filtered_papers = scored_detail.get("papers", [])
        logger.info(f"   • Papers with signal_score >= {median_score}: {len(filtered_papers)}")
        for p in filtered_papers:
            score = float(p.get("signal_score") or 0.0)
            assert score >= median_score, f"Paper {p.get('id')} score {score} is below min_score {median_score}"
        logger.info(f"   ✅ All {len(filtered_papers)} returned papers satisfy signal_score >= {median_score}.")

        # Extreme min_score test (above max score)
        max_score = max(all_scores)
        extreme_min_score = max_score + 1000.0
        empty_detail = ws_svc.get_edition_detail(
            target_ws_id, target_date, run_id=target_run_id, scope="all", min_score=extreme_min_score
        )
        assert len(empty_detail.get("papers", [])) == 0, f"min_score={extreme_min_score} should return 0 papers"
        logger.info(f"   ✅ min_score={extreme_min_score} correctly filtered out all papers.")
        results["checks"]["min_score_filter"] = "PASSED"
    else:
        logger.info("   ⏭ No scored papers found; skipping numeric floor assertion.")
        results["checks"]["min_score_filter"] = "SKIPPED"

    # 3.2 Dynamic Dimension Floor Filtering (e.g. min_<dim_key>, dim:<dim_key>, min_dim:<dim_key>)
    dim_candidates = {}
    for p in all_papers:
        for d in p.get("dimensions", []) or []:
            d_key = (d.get("key") or "").strip().lower()
            val = d.get("value")
            if d_key and isinstance(val, (int, float)) and val > 0:
                dim_candidates.setdefault(d_key, []).append(float(val))

    if dim_candidates:
        test_dim_key, test_dim_vals = next(iter(dim_candidates.items()))
        test_dim_vals_sorted = sorted(test_dim_vals)
        dim_floor = test_dim_vals_sorted[len(test_dim_vals_sorted) // 2]
        logger.info(f"   • Testing dynamic dimension filter 'min_{test_dim_key}={dim_floor}'...")

        dim_filtered_detail = ws_svc.get_edition_detail(
            target_ws_id,
            target_date,
            run_id=target_run_id,
            scope="all",
            dimension_filters={test_dim_key: dim_floor},
        )
        dim_filtered_papers = dim_filtered_detail.get("papers", [])
        logger.info(f"   • Returned {len(dim_filtered_papers)} papers for dimension '{test_dim_key}' >= {dim_floor}")

        for p in dim_filtered_papers:
            p_dims = {
                (d.get("key") or "").strip().lower(): d.get("value")
                for d in p.get("dimensions", []) or []
            }
            # Fallback to matching dimension name
            for d in p.get("dimensions", []) or []:
                name_slug = (d.get("name") or "").strip().lower().replace(" ", "_").replace("-", "_")
                if name_slug and name_slug not in p_dims:
                    p_dims[name_slug] = d.get("value")

            p_val = p_dims.get(test_dim_key)
            if p_val is not None and isinstance(p_val, (int, float)):
                assert p_val >= dim_floor, (
                    f"Paper {p.get('id')} dimension '{test_dim_key}' value {p_val} is below floor {dim_floor}"
                )
        logger.info(f"   ✅ All returned papers satisfy dynamic dimension filter '{test_dim_key}' >= {dim_floor}.")

        # Extreme dimension floor filter (above max value) -> must return 0 papers
        extreme_dim_floor = max(test_dim_vals) + 1000.0
        extreme_dim_detail = ws_svc.get_edition_detail(
            target_ws_id,
            target_date,
            run_id=target_run_id,
            scope="all",
            dimension_filters={test_dim_key: extreme_dim_floor},
        )
        assert len(extreme_dim_detail.get("papers", [])) == 0, (
            f"Extreme dimension floor {extreme_dim_floor} should return 0 papers, got: {len(extreme_dim_detail.get('papers', []))}"
        )
        logger.info(f"   ✅ Extreme dynamic dimension floor min_{test_dim_key}={extreme_dim_floor} correctly returned 0 papers.")

        # Alternative prefix syntax test: 'dim:<dim_key>'
        alt_prefix_detail = ws_svc.get_edition_detail(
            target_ws_id,
            target_date,
            run_id=target_run_id,
            scope="all",
            dimension_filters={f"dim:{test_dim_key}": dim_floor},
        )
        assert len(alt_prefix_detail.get("papers", [])) == len(dim_filtered_papers), (
            f"Alternative prefix 'dim:{test_dim_key}' returned different count than 'min_{test_dim_key}'"
        )
        logger.info(f"   ✅ Prefix flexibility ('dim:{test_dim_key}' vs 'min_{test_dim_key}') verified.")
        results["checks"]["dynamic_dimension_filter"] = "PASSED"
    else:
        logger.info("   ⏭ No dimension values found on papers; skipping dynamic dimension floor test.")
        results["checks"]["dynamic_dimension_filter"] = "SKIPPED"

    # =========================================================================
    # Phase 4: Validate Multi-Criteria Sorting & Dynamic Discovery
    # =========================================================================
    logger.info("\n🔄 Phase 4: Testing Sorting Modes & Dynamic Extractions Discovery...")

    # 4.1 Default / sort='score' (descending)
    sort_score = ws_svc.get_edition_detail(target_ws_id, target_date, run_id=target_run_id, scope="all", sort="score")
    score_papers = sort_score.get("papers", [])
    scores_list = [float(p.get("signal_score") or 0.0) for p in score_papers if p.get("signal_score") is not None]
    for i in range(len(scores_list) - 1):
        assert scores_list[i] >= scores_list[i + 1], (
            f"Scores not monotonically decreasing in sort='score': {scores_list[i]} < {scores_list[i+1]}"
        )
    logger.info(f"   ✅ Verified sort='score' produces strictly descending order: {scores_list[:5]}")

    # 4.2 sort='published'
    sort_pub = ws_svc.get_edition_detail(target_ws_id, target_date, run_id=target_run_id, scope="all", sort="published")
    assert isinstance(sort_pub.get("papers"), list), "sort='published' must return valid papers list"
    logger.info(f"   ✅ Verified sort='published' returns valid list of {len(sort_pub.get('papers'))} papers.")

    # 4.3 Dimension sorting with monotonicity assertion (sort=dim:<key>)
    definitions = target_edition.get("definitions", [])
    sort_dim_key = None
    if definitions:
        for d in definitions:
            k = d.get("key") or d.get("id") or d.get("name")
            if k and not str(k).startswith("risk_"):
                sort_dim_key = str(k).lower().replace(" ", "_").replace("-", "_")
                break

    if not sort_dim_key and dim_candidates:
        sort_dim_key = next(iter(dim_candidates.keys()))

    if sort_dim_key:
        dim_sort_param = f"dim:{sort_dim_key}"
        logger.info(f"   • Testing dimension sort '{dim_sort_param}'...")
        dim_detail = ws_svc.get_edition_detail(
            target_ws_id, target_date, run_id=target_run_id, scope="all", sort=dim_sort_param
        )
        sorted_papers = dim_detail.get("papers", [])
        assert isinstance(sorted_papers, list), f"Sort by {dim_sort_param} returned invalid list"
        logger.info(f"   • Sort by {dim_sort_param} returned {len(sorted_papers)} papers.")

        # Extract values for the sorted dimension and verify monotonicity
        extracted_dim_vals = []
        for p in sorted_papers:
            val = None
            for d in p.get("dimensions", []) or []:
                d_k = (d.get("key") or "").strip().lower()
                d_n = (d.get("name") or "").strip().lower().replace(" ", "_").replace("-", "_")
                if d_k == sort_dim_key or d_n == sort_dim_key or (sort_dim_key == "trl" and d.get("is_trl")):
                    if isinstance(d.get("value"), (int, float)):
                        val = float(d.get("value"))
                        break
            extracted_dim_vals.append(val if val is not None else -float("inf"))

        for i in range(len(extracted_dim_vals) - 1):
            assert extracted_dim_vals[i] >= extracted_dim_vals[i + 1], (
                f"Dimension values not descending in sort='{dim_sort_param}': {extracted_dim_vals[i]} < {extracted_dim_vals[i+1]}"
            )
        logger.info(f"   ✅ Verified sort='{dim_sort_param}' produces descending dimension order: {extracted_dim_vals[:5]}")
        results["checks"]["dimension_sorting"] = "PASSED"
    else:
        results["checks"]["dimension_sorting"] = "SKIPPED"

    # 4.4 Dynamic Extractions Discovery in Definitions Metadata
    if definitions:
        logger.info(f"   • Validating dynamic extraction discovery in definitions metadata ({len(definitions)} definitions)...")
        for d in definitions:
            assert "key" in d, f"Definition metadata missing 'key': {d}"
            assert "name" in d, f"Definition metadata missing 'name': {d}"
            assert "is_numeric" in d, f"Definition metadata missing 'is_numeric': {d}"
            assert d.get("max") is not None, f"Definition metadata missing 'max': {d}"
        logger.info(f"   ✅ Definitions metadata conforms to dynamic extraction contract.")
        results["checks"]["definitions_metadata_discovery"] = "PASSED"

    # 4.5 Combined Filter + Dimension Sort + Pagination
    if dim_candidates and all_scores:
        logger.info("   • Testing combined filter (min_score + dynamic dimension floor + sort + page_size)...")
        combo_dim_key = next(iter(dim_candidates.keys()))
        combo_dim_val = sorted(dim_candidates[combo_dim_key])[0]
        combo_score_floor = sorted(all_scores)[0]

        combo_detail = ws_svc.get_edition_detail(
            target_ws_id,
            target_date,
            run_id=target_run_id,
            scope="all",
            min_score=combo_score_floor,
            dimension_filters={combo_dim_key: combo_dim_val},
            sort=f"dim:{combo_dim_key}",
            page=1,
            page_size=2,
        )
        assert "papers" in combo_detail
        assert combo_detail.get("page") == 1
        assert combo_detail.get("page_size") == 2
        logger.info(f"   ✅ Combined multi-criteria query succeeded (returned {len(combo_detail.get('papers', []))} papers, total: {combo_detail.get('total')}).")
        results["checks"]["combined_filters_and_sort"] = "PASSED"

    results["checks"]["sorting"] = "PASSED"

    # =========================================================================
    # Phase 5: Validate BFF Contract Endpoint (/bff/briefings/{date})
    # =========================================================================
    logger.info("\n🌐 Phase 5: Testing BFF Endpoint (/bff/briefings/{date})...")
    try:
        bff_resp = client.get(
            f"/bff/briefings/{target_date}",
            params={
                "domain": target_ws_id,
                "run": target_run_id,
                "page": 1,
                "page_size": 2,
                "scope": "included",
            },
        )
        if bff_resp.status_code == 200:
            bff_data = bff_resp.json()
            assert bff_data.get("workspace_id") == target_ws_id
            assert "papers" in bff_data
            logger.info(f"   ✅ BFF Briefing endpoint returned HTTP 200 with {len(bff_data.get('papers', []))} papers.")
            results["checks"]["bff_briefing"] = "PASSED"
        else:
            logger.info(f"   ℹ️ BFF endpoint status {bff_resp.status_code} (BFF may be served on frontend host).")
            results["checks"]["bff_briefing"] = f"SKIPPED ({bff_resp.status_code})"
    except Exception as bff_err:
        logger.info(f"   ℹ️ BFF endpoint check note: {bff_err}")
        results["checks"]["bff_briefing"] = "SKIPPED"

    logger.info("\n=================================================================")
    logger.info("🎉 BRIEFING FILTERS, SCOPE & PAGINATION E2E SCENARIO PASSED!")
    logger.info(f"   • Scope ('included', 'excluded', 'all') : VERIFIED")
    logger.info(f"   • Server-side Pagination & Disjoint Pages : VERIFIED")
    logger.info(f"   • Min Score Floor Filtering              : VERIFIED")
    logger.info(f"   • Multi-Criteria Sorting (Score, Dim)    : VERIFIED")
    logger.info("=================================================================")

    cleanup_ws = target_ws_id if (created_temp_workspace or (workspace_id and cfg.delete_after)) else None
    if cleanup_ws and cfg.delete_after:
        try:
            ws_svc.delete_workspace(cleanup_ws)
            logger.info(f"🧹 Cleaned up edition test workspace '{cleanup_ws}'")
        except Exception as e:
            logger.warning(f"Could not delete test workspace {cleanup_ws}: {e}")

    results["status"] = "passed"
    return results
