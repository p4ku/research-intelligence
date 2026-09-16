#!/usr/bin/env python3
"""
Schwarz Research Intelligence - Standalone E2E Pipeline Simulator & Test Runner.

Usage Examples:
  # Run against Staging (Default):
  python -m tests_e2e.run_e2e
  
  # Run against Production:
  python -m tests_e2e.run_e2e --target=prod
  
  # Run against Local development:
  python -m tests_e2e.run_e2e --target=local --cleanup
  
  # Custom limits & credentials:
  python -m tests_e2e.run_e2e --target=staging --limit=10 --user=test_e2e --password='...'
"""

import argparse
import json
import logging
import sys
import time

from tests_e2e.config import E2EConfig, ENV_TARGETS
from tests_e2e.scenarios import (
    run_full_slr_pipeline_scenario,
    run_chat_multiturn_scenario,
    run_agent_lifecycle_scenario,
    run_pipeline_reprocessing_scenario,
    run_cross_source_dedup_scenario,
    run_quota_guard_scenario,
    run_mcp_protocol_scenario,
    run_rbac_data_isolation_scenario,
    run_mid_step_rerun_scenario,
    run_chat_hallucination_guard_scenario,
    run_concurrent_agents_load_scenario,
    run_concurrent_runs_in_workspace_scenario,
    run_workflow_schedule_scenario,
    run_paper_evidence_and_pdf_scenario,
    run_researcher_rbac_guard_scenario,
    run_executive_briefing_export_scenario,
    run_date_range_and_pagination_scenario,
    run_ask_paper_journey_scenario,
    run_signal_score_variables_scenario,
    run_workspace_import_export_scenario,
    run_direct_full_text_and_subscribers_scenario,
    run_hitl_validation_journey_scenario,
    run_stars_curation_journey_scenario,
    run_paper_page_scorecard_journey_scenario,
    run_run_admission_guard_scenario,
    run_briefing_filters_and_pagination_scenario,
    run_three_personas_rbac_journey_scenario,
)

# Configure rich colored terminal logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("e2e_runner")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Schwarz Research Intelligence - E2E Live Pipeline Simulator"
    )
    parser.add_argument(
        "--target",
        choices=["prod", "production", "staging", "local"],
        default="prod",
        help="Target environment (default: prod)",
    )
    parser.add_argument(
        "--scenario",
        choices=[
            "slr", "lifecycle", "reprocess", "dedup", "quota", "mcp", "isolation", "rerun", "guard",
            "concurrent", "parallel", "schedule", "evidence", "researcher", "briefing",
            "date_range", "pagination", "ask", "ask_paper", "variables", "signal_score_variables", "scoring_math",
            "impexp", "import_export", "template",
            "direct_ft", "direct_full_text", "subscribers",
            "hitl", "hitl_validation", "correction",
            "stars", "curation",
            "paper_page", "paper_scorecard", "scorecard_page",
            "admission", "run_admission",
            "briefing_filters", "editions", "briefing_pagination",
            "all"
        ],
        default="slr",
        help="Target test scenario to execute (slr, briefing_filters, editions, date_range, all)",
    )
    parser.add_argument(
        "--provider",
        choices=["arxiv", "openalex"],
        default="arxiv",
        help="Academic data source provider for scraping (arxiv or openalex, default: arxiv)",
    )
    parser.add_argument(
        "--url",
        type=str,
        default=None,
        help="Custom Base API URL override (e.g. https://research-scanner.schwarz)",
    )
    parser.add_argument(
        "--user",
        type=str,
        default="test_e2e",
        help="User account identifier (default: test_e2e)",
    )
    parser.add_argument(
        "--password",
        type=str,
        default="t4st_pa55w0rD!#",
        help="Account password",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Paper limit for the review run (default: 10)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=900,
        help="Maximum timeout in seconds (default: 900s / 15min)",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=5.0,
        help="Polling interval in seconds (default: 5.0s)",
    )
    parser.add_argument(
        "--no-cleanup-before",
        action="store_true",
        help="Skip cleaning up old 'test_e2e_*' workspaces at the start",
    )
    parser.add_argument(
        "--cleanup-after",
        action="store_true",
        help="Delete the test workspace and storage artifacts immediately after test completion (default: keep for inspection)",
    )
    parser.add_argument(
        "--no-reprocess",
        action="store_true",
        help="Disable reprocess_existing (default: enabled so repeated runs reprocess existing papers)",
    )
    return parser.parse_args()


def print_banner():
    print(
        r"""
  ███████╗██████╗ ██╗    ███████╗██████╗ ███████╗
  ██╔════╝██╔══██╗██║    ██╔════╝╚════██╗██╔════╝
  ███████╗██████╔╝██║    █████╗   █████╔╝█████╗  
  ╚════██║██╔══██╗██║    ██╔══╝  ██╔═══╝ ██╔══╝  
  ███████║██║  ██║██║    ███████╗███████╗███████╗
  ╚══════╝╚═╝  ╚═╝╚═╝    ╚══════╝╚══════╝╚══════╝
  Schwarz Research Intelligence - Live E2E Simulator
        """
    )


def print_llm_cost_summary(c: dict, total_elapsed: float, total_papers: int = 0, title: str = "LLM TOKENS & FINANCIAL COST SUMMARY"):
    p_in = int(c.get("pipeline_tokens_in", 0) or 0)
    p_out = int(c.get("pipeline_tokens_out", 0) or 0)
    p_tok = int(c.get("pipeline_total_tokens", 0) or (p_in + p_out))
    p_usd = float(c.get("pipeline_usd_cost", 0.0) or 0.0)

    c_in = int(c.get("chat_tokens_in", 0) or 0)
    c_out = int(c.get("chat_tokens_out", 0) or 0)
    c_tok = int(c.get("chat_total_tokens", 0) or (c_in + c_out))
    c_usd = float(c.get("chat_usd_cost", 0.0) or 0.0)

    tot_in = p_in + c_in
    tot_out = p_out + c_out
    tot_tok = int(c.get("total_tokens_consumed") or (tot_in + tot_out))
    tot_usd = float(c.get("total_usd_spent", 0.0) or (p_usd + c_usd))
    tot_eur = tot_usd * 0.92

    print("\n" + "=" * 70)
    print(f"💎  {title} (GOOGLE GEMINI 3.8 FLASH)")
    print("=" * 70)
    print(f"  🤖 Inference Engine     : Google Vertex AI / GenAI (gemini-3.8-flash)")
    print(f"  ⏱️  Total Run Time       : {total_elapsed:.1f}s")
    if total_papers > 0:
        print(f"  📄 Ingested Papers      : {total_papers} papers")
        print(f"  ⚡ Unit Economics       : ${tot_usd / total_papers:.4f} USD / paper (~{int(tot_tok / total_papers):,} tokens/paper)")
    print("  --------------------------------------------------------------------")
    print(f"  🔄 Pipeline Review Cost : ${p_usd:.4f} USD ({p_tok:,} tokens)")
    if c_tok > 0 or c_usd > 0:
        print(f"  💬 Paper Chat Q&A Cost  : ${c_usd:.4f} USD ({c_tok:,} tokens)")
    print("  --------------------------------------------------------------------")
    print(f"  📥 Prompt (Input) Tokens: {tot_in:,} tokens")
    print(f"  📤 Thought/Output Tokens: {tot_out:,} tokens")
    print(f"  📊 Total Tokens Consumed: {tot_tok:,} tokens")
    print("  --------------------------------------------------------------------")
    print(f"  💵 Total Run Cost (USD) : ${tot_usd:.4f} USD (~€{tot_eur:.4f} EUR)")
    if c.get("workspace_monthly_usd") is not None:
        print(f"  🏢 Workspace Total Spend: ${float(c.get('workspace_monthly_usd', 0.0)):.4f} USD ({int(c.get('workspace_monthly_tokens', 0)):,} monthly tokens)")
    print("=" * 70 + "\n")


def print_suite_summary(scenario_results: list, total_elapsed: float, config=None):
    """
    Aggregates and prints comprehensive scorecard and financial metrics across ALL scenarios in the test suite.
    """
    print("\n" + "=" * 80)
    print("🏆  E2E TEST SUITE EXECUTION SCORECARD (ALL SCENARIOS)")
    print("=" * 80)
    print(f"  {'#':<3} {'Scenario Name':<32} {'Status':<10} {'Duration':<10} {'Papers':<8} {'Tokens':<13} {'Cost (USD)'}")
    print("  " + "-" * 76)

    agg_p_in = 0
    agg_p_out = 0
    agg_p_tok = 0
    agg_p_usd = 0.0
    agg_c_in = 0
    agg_c_out = 0
    agg_c_tok = 0
    agg_c_usd = 0.0
    agg_total_tokens = 0
    agg_total_usd = 0.0
    agg_papers = 0
    passed_count = 0

    for idx, s in enumerate(scenario_results, start=1):
        s_name = s.get("scenario_name", f"Scenario {idx}")
        raw_status = str(s.get("status", "")).lower()
        if raw_status in ("passed", "completed"):
            s_status = "✅ PASS"
            passed_count += 1
        elif raw_status == "skipped":
            s_status = "⏭️ SKIP"
        else:
            s_status = "❌ FAIL"
        s_time = f"{s.get('elapsed_sec', 0.0):.1f}s"
        s_papers = str(s.get("total_papers") or s.get("total_papers_fetched") or s.get("papers_count") or "-")
        if str(s_papers).isdigit():
            agg_papers += int(s_papers)

        cm = s.get("cost_metrics") or {}
        tok = int(cm.get("total_tokens_consumed", 0) or 0)
        usd = float(cm.get("total_usd_spent", 0.0) or 0.0)

        agg_p_in += int(cm.get("pipeline_tokens_in", 0) or 0)
        agg_p_out += int(cm.get("pipeline_tokens_out", 0) or 0)
        agg_p_tok += int(cm.get("pipeline_total_tokens", 0) or 0)
        agg_p_usd += float(cm.get("pipeline_usd_cost", 0.0) or 0.0)

        agg_c_in += int(cm.get("chat_tokens_in", 0) or 0)
        agg_c_out += int(cm.get("chat_tokens_out", 0) or 0)
        agg_c_tok += int(cm.get("chat_total_tokens", 0) or 0)
        agg_c_usd += float(cm.get("chat_usd_cost", 0.0) or 0.0)

        agg_total_tokens += tok
        agg_total_usd += usd

        tok_str = f"{tok:,} tok" if tok > 0 else "-"
        usd_str = f"${usd:.4f}" if usd > 0 else "$0.0000"

        print(f"  {idx:<3} {s_name:<32} {s_status:<10} {s_time:<10} {s_papers:<8} {tok_str:<13} {usd_str}")

    pass_rate = (passed_count / len(scenario_results) * 100) if scenario_results else 100.0
    print("  " + "-" * 76)
    print(f"  🎯 Overall Result: {passed_count}/{len(scenario_results)} Scenarios Passed ({pass_rate:.0f}%) in {total_elapsed:.1f}s")
    print("=" * 80)

    # Calculate suite-level cost dictionary
    suite_cost_metrics = {
        "pipeline_tokens_in": agg_p_in,
        "pipeline_tokens_out": agg_p_out,
        "pipeline_total_tokens": agg_p_tok or (agg_p_in + agg_p_out),
        "pipeline_usd_cost": agg_p_usd,
        "chat_tokens_in": agg_c_in,
        "chat_tokens_out": agg_c_out,
        "chat_total_tokens": agg_c_tok or (agg_c_in + agg_c_out),
        "chat_usd_cost": agg_c_usd,
        "total_tokens_consumed": agg_total_tokens or (agg_p_tok + agg_c_tok),
        "total_usd_spent": agg_total_usd or (agg_p_usd + agg_c_usd),
    }

    # Query all active test workspaces if config is available to verify workspace total spend
    if config:
        try:
            from tests_e2e.client import APIClient, AuthService, WorkspaceService
            cl = APIClient(config.base_url)
            auth = AuthService(cl)
            auth.login(config.username, config.password)
            ws_svc = WorkspaceService(cl)
            workspaces = ws_svc.list_workspaces()
            test_ws = [w for w in workspaces if w.get("name", "").startswith("test_e2e_")]
            if test_ws:
                total_ws_tok = sum(int(w.get("tokens_consumed_this_month", 0) or 0) for w in test_ws)
                total_ws_usd = sum(float(w.get("usd_spent_this_month", 0.0) or 0.0) for w in test_ws)
                suite_cost_metrics["workspace_monthly_usd"] = total_ws_usd
                suite_cost_metrics["workspace_monthly_tokens"] = total_ws_tok
        except Exception:
            pass

    print_llm_cost_summary(
        suite_cost_metrics,
        total_elapsed=total_elapsed,
        total_papers=agg_papers,
        title="SUITE-WIDE LLM TOKENS & FINANCIAL COST SUMMARY"
    )


def print_summary_card(results: dict, total_elapsed: float):
    print("\n" + "=" * 70)
    print("📋  E2E PIPELINE EXECUTION SCORECARD & AUDIT REPORT")
    print("=" * 70)
    print(f"  🏷️  Workspace Name       : {results.get('workspace_name')}")
    print(f"  🆔 Workspace UUID       : {results.get('workspace_id')}")
    print(f"  ⚙️  Process UUID         : {results.get('process_id')}")
    print(f"  🔄 Pipeline Run UUID    : {results.get('pipeline_run_id')}")
    print(f"  ⏱️  Total Duration       : {total_elapsed:.1f}s")
    print(f"  📄 Total Papers Scraped : {results.get('total_papers_fetched', 0)}")
    print(f"  ✅ Accepted Full-Text   : {results.get('accepted_papers_count', 0)}")
    print(f"  📊 Extractions Extracted: {results.get('extractions_count', 0)}")
    print(f"  📑 Reports Generated    : {results.get('reports_count', 0)}")

    print("\n  🔍 STAGE-BY-STAGE VALIDATION:")
    for stage_key, check_status in results.get("stage_checks", {}).items():
        print(f"     • {stage_key:<25} : ✅ {check_status}")

    if results.get("top_papers"):
        print("\n  🏆 TOP-SCORING ACCEPTED PAPERS:")
        for idx, paper in enumerate(results["top_papers"], start=1):
            title = (paper.get("title") or "Untitled")[:65]
            raw_score = paper.get("signal_score")
            score_str = f"{float(raw_score):>5.1f}" if raw_score is not None else "  N/A"
            print(f"     [{idx}] Score: {score_str} | {title}...")

    if results.get("chat_response"):
        chat = results["chat_response"]
        print("\n  💬 INTERACTIVE PAPER CHAT VERIFICATION:")
        print(f"     • Session ID: {chat.get('session_id')}")
        ans = chat.get("answer_snippet") or chat.get("answer") or "Grounded answer received."
        print(f"     • Answer    : {ans}")
        print(f"     • Citations : {chat.get('citations_count', 0)} visual & textual citations grounded")

    if results.get("cleaned_up"):
        print("\n  🧹 CLEANUP & ARTIFACTS PURGE : ✅ Test workspace, DB records & storage files deleted cleanly.")

    print("=" * 70)
    print("🎉 ALL CHECKS PASSED - PRODUCTION / STAGING INTEGRITY VERIFIED!\n")

    if results.get("cost_metrics"):
        print_llm_cost_summary(
            results["cost_metrics"],
            total_elapsed=total_elapsed,
            total_papers=results.get("total_papers_fetched", 0)
        )


def main():
    print_banner()
    args = parse_args()

    base_url = args.url or ENV_TARGETS.get(args.target, "https://research-scanner.schwarz")
    config = E2EConfig(
        target_env=args.target,
        base_url=base_url,
        username=args.user,
        password=args.password,
        provider=args.provider,
        paper_limit=args.limit,
        poll_interval_sec=args.poll_interval,
        max_timeout_sec=args.timeout,
        cleanup_before=not args.no_cleanup_before,
        delete_after=args.cleanup_after,
        cleanup_after=args.cleanup_after,
        reprocess_existing=not args.no_reprocess,
    )

    t0 = time.time()
    try:
        if args.scenario == "slr":
            results = run_full_slr_pipeline_scenario(config)
            total_elapsed = time.time() - t0
            print_summary_card(results, total_elapsed)

        elif args.scenario == "lifecycle":
            res = run_agent_lifecycle_scenario(config)
            total_elapsed = time.time() - t0
            print(f"\n✅ AGENT LIFECYCLE SCENARIO COMPLETED in {total_elapsed:.1f}s (Final Status: {res.get('final_status')})")
            if res.get("cost_metrics"):
                print_llm_cost_summary(res["cost_metrics"], total_elapsed=total_elapsed)

        elif args.scenario == "reprocess":
            res = run_pipeline_reprocessing_scenario(config)
            total_elapsed = time.time() - t0
            print(f"\n✅ PIPELINE REPROCESSING SCENARIO COMPLETED in {total_elapsed:.1f}s (Total Papers: {res.get('total_papers')})")
            if res.get("cost_metrics"):
                print_llm_cost_summary(res["cost_metrics"], total_elapsed=total_elapsed, total_papers=res.get('total_papers', 0))

        elif args.scenario == "dedup":
            res = run_cross_source_dedup_scenario(config)
            total_elapsed = time.time() - t0
            print(f"\n✅ CROSS-SOURCE DEDUPLICATION SCENARIO COMPLETED in {total_elapsed:.1f}s (Total Papers: {res.get('total_papers')})")
            if res.get("cost_metrics"):
                print_llm_cost_summary(res["cost_metrics"], total_elapsed=total_elapsed, total_papers=res.get('total_papers', 0))

        elif args.scenario == "quota":
            res = run_quota_guard_scenario(config)
            total_elapsed = time.time() - t0
            print(f"\n✅ QUOTA GUARD SCENARIO COMPLETED in {total_elapsed:.1f}s")
            if res.get("cost_metrics"):
                print_llm_cost_summary(res["cost_metrics"], total_elapsed=total_elapsed)

        elif args.scenario == "mcp":
            res = run_mcp_protocol_scenario(config)
            total_elapsed = time.time() - t0
            print(f"\n✅ FASTMCP PROTOCOL SCENARIO COMPLETED in {total_elapsed:.1f}s (Papers Verified: {res.get('papers_count')})\n")
            if res.get("cost_metrics"):
                print_llm_cost_summary(res["cost_metrics"], total_elapsed=total_elapsed, total_papers=res.get('papers_count', 0))

        elif args.scenario == "isolation":
            res = run_rbac_data_isolation_scenario(config)
            total_elapsed = time.time() - t0
            print(f"\n✅ RBAC & MULTI-TENANCY DATA ISOLATION SCENARIO COMPLETED in {total_elapsed:.1f}s (Security Checks: PASS)\n")

        elif args.scenario == "rerun":
            res = run_mid_step_rerun_scenario(config)
            total_elapsed = time.time() - t0
            print(f"\n✅ MID-STEP PIPELINE RERUN SCENARIO COMPLETED in {total_elapsed:.1f}s (Component Runs: {res.get('component_runs_count')})\n")

        elif args.scenario == "guard":
            res = run_chat_hallucination_guard_scenario(config)
            total_elapsed = time.time() - t0
            print(f"\n✅ CHAT HALLUCINATION GUARD SCENARIO COMPLETED in {total_elapsed:.1f}s (Guard Verified: {res.get('adversarial_guard_verified')})\n")

        elif args.scenario == "concurrent":
            res = run_concurrent_agents_load_scenario(config, num_agents=2)
            total_elapsed = time.time() - t0
            print(f"\n✅ CONCURRENT AGENTS LOAD SCENARIO COMPLETED in {total_elapsed:.1f}s (Agents: {res.get('agents_count')})\n")

        elif args.scenario == "parallel":
            res = run_concurrent_runs_in_workspace_scenario(config)
            total_elapsed = time.time() - t0
            print(f"\n✅ CONCURRENT RUNS IN SINGLE WORKSPACE SCENARIO COMPLETED in {total_elapsed:.1f}s (Run 1 Papers: {res.get('run1_papers')}, Run 2 Papers: {res.get('run2_papers')})\n")

        elif args.scenario == "schedule":
            res = run_workflow_schedule_scenario(config)
            total_elapsed = time.time() - t0
            if str(res.get("status", "")).lower() == "skipped":
                print(f"\n⏭️ WORKFLOW SCHEDULE & OBSERVABILITY SCENARIO SKIPPED in {total_elapsed:.1f}s (Reason: {res.get('reason')})\n")
            else:
                print(f"\n✅ WORKFLOW SCHEDULE & OBSERVABILITY SCENARIO COMPLETED in {total_elapsed:.1f}s (Status: {res.get('schedule_status')})\n")

        elif args.scenario == "evidence":
            res = run_paper_evidence_and_pdf_scenario(config)
            total_elapsed = time.time() - t0
            print(f"\n✅ PAPER SCORECARD & EVIDENCE QUOTES SCENARIO COMPLETED in {total_elapsed:.1f}s (Signal: {res.get('signal_score')}, PDF Status: {res.get('pdf_status_code')})\n")

        elif args.scenario == "researcher":
            res = run_researcher_rbac_guard_scenario(config)
            total_elapsed = time.time() - t0
            print(f"\n✅ RESEARCHER RBAC & READ-ONLY SAFETY SCENARIO COMPLETED in {total_elapsed:.1f}s (Security: PASS)\n")

        elif args.scenario == "briefing":
            res = run_executive_briefing_export_scenario(config)
            total_elapsed = time.time() - t0
            print(f"\n✅ EXECUTIVE BRIEFING GENERATION SCENARIO COMPLETED in {total_elapsed:.1f}s (Report: '{res.get('report_title')}')\n")

        elif args.scenario in ("date_range", "pagination"):
            res = run_date_range_and_pagination_scenario(config)
            total_elapsed = time.time() - t0
            print(f"\n✅ SCRAPER DATE RANGE & RESULTS PAGINATION SCENARIO COMPLETED in {total_elapsed:.1f}s (Total Papers: {res.get('total_papers')})\n")

        elif args.scenario in ("ask", "ask_paper"):
            res = run_ask_paper_journey_scenario(config)
            total_elapsed = time.time() - t0
            print(f"\n✅ ASK PAPER E2E USER JOURNEY COMPLETED in {total_elapsed:.1f}s (Paper: '{res.get('paper_title')}', Turns: 2, Tokens: {res.get('total_tokens')})\n")
            if res.get("cost_metrics"):
                print_llm_cost_summary(res["cost_metrics"], total_elapsed=total_elapsed)

        elif args.scenario in ("variables", "signal_score_variables", "scoring_math"):
            res = run_signal_score_variables_scenario(config)
            total_elapsed = time.time() - t0
            print(f"\n✅ SIGNAL SCORE VARIABLES & MATH SCENARIO COMPLETED in {total_elapsed:.1f}s (Verified Papers: {res.get('verified_papers_count')})\n")

        elif args.scenario in ("impexp", "import_export", "template"):
            res = run_workspace_import_export_scenario(config)
            total_elapsed = time.time() - t0
            print(f"\n✅ WORKSPACE TEMPLATE EXPORT & IMPORT SCENARIO COMPLETED in {total_elapsed:.1f}s (Definitions: {res.get('definitions_count')}, Scrapers: {res.get('scrapers_count')}, Subs: {res.get('subscribers_count')})\n")

        elif args.scenario in ("direct_ft", "direct_full_text", "subscribers"):
            res = run_direct_full_text_and_subscribers_scenario(config)
            total_elapsed = time.time() - t0
            print(f"\n✅ DIRECT FULL-TEXT SCREENING & SUBSCRIBERS SCENARIO COMPLETED in {total_elapsed:.1f}s (Papers: {res.get('papers_count')}, Subscribers: {res.get('subscribers_count')})\n")

        elif args.scenario in ("hitl", "hitl_validation", "correction"):
            res = run_hitl_validation_journey_scenario(config)
            total_elapsed = time.time() - t0
            print(f"\n✅ HUMAN-IN-THE-LOOP (HITL) VALIDATION SCENARIO COMPLETED in {total_elapsed:.1f}s (Extraction ID: {res.get('extraction_id')})\n")

        elif args.scenario in ("stars", "curation"):
            res = run_stars_curation_journey_scenario(config)
            total_elapsed = time.time() - t0
            print(f"\n✅ STARS & PERSONAL CURATION SCENARIO COMPLETED in {total_elapsed:.1f}s (Status: {res.get('status')})\n")

        elif args.scenario in ("paper_page", "paper_scorecard", "scorecard_page"):
            res = run_paper_page_scorecard_journey_scenario(config)
            total_elapsed = time.time() - t0
            print(f"\n✅ PAPER PAGE SCORECARD SCENARIO COMPLETED in {total_elapsed:.1f}s (Dimensions: {res.get('dimensions_count')}, Risk: {res.get('has_risk_and_affiliation')})\n")

        elif args.scenario in ("admission", "run_admission"):
            res = run_run_admission_guard_scenario(config)
            total_elapsed = time.time() - t0
            print(f"\n✅ RUN ADMISSION GUARD SCENARIO COMPLETED in {total_elapsed:.1f}s (Burst: {res.get('burst_status_codes')}, Duplicate: {res.get('duplicate_status_codes')})\n")

        elif args.scenario in ("briefing_filters", "editions", "briefing_pagination"):
            res = run_briefing_filters_and_pagination_scenario(config)
            total_elapsed = time.time() - t0
            print(f"\n✅ BRIEFING FILTERS, SCOPE & PAGINATION SCENARIO COMPLETED in {total_elapsed:.1f}s (Checks: {res.get('checks')})\n")

        elif args.scenario in ("personas", "three_personas", "rbac_personas"):
            res = run_three_personas_rbac_journey_scenario(config)
            total_elapsed = time.time() - t0
            print(f"\n✅ THREE PERSONAS RBAC JOURNEY COMPLETED in {total_elapsed:.1f}s (Checks: {res.get('persona_checks')})\n")

        elif args.scenario == "all":
            logger.info("🧪 Running ALL E2E test scenarios sequentially...")
            suite_results = []

            def _run_and_track(name: str, fn, *fn_args, **fn_kwargs):
                s_t0 = time.time()
                try:
                    res = fn(*fn_args, **fn_kwargs)
                    s_elapsed = time.time() - s_t0
                    res_dict = dict(res) if isinstance(res, dict) else {}
                    if str(res_dict.get("status", "")).lower() == "skipped":
                        res_dict["scenario_name"] = name
                        res_dict["elapsed_sec"] = s_elapsed
                        suite_results.append(res_dict)
                        logger.info(f"⏭️ [{name}] skipped ({res_dict.get('reason', 'feature disabled')}) in {s_elapsed:.1f}s")
                        return res
                    res_dict.setdefault("status", "passed")
                    res_dict["scenario_name"] = name
                    res_dict["elapsed_sec"] = s_elapsed
                    suite_results.append(res_dict)
                    logger.info(f"✅ [{name}] completed in {s_elapsed:.1f}s")
                    return res
                except Exception as s_err:
                    s_elapsed = time.time() - s_t0
                    suite_results.append({
                        "scenario_name": name,
                        "status": "failed",
                        "error": str(s_err),
                        "elapsed_sec": s_elapsed
                    })
                    logger.error(f"❌ [{name}] failed after {s_elapsed:.1f}s: {s_err}")
                    raise

            # 1. Full SLR Pipeline
            slr_results = _run_and_track("Full SLR Pipeline", run_full_slr_pipeline_scenario, config)

            # 2. Interactive Multi-Turn Chat
            top_papers = slr_results.get("top_papers", [])
            if top_papers:
                from tests_e2e.client import APIClient, AuthService, PipelineService
                client = APIClient(config.base_url)
                auth = AuthService(client)
                auth.login(config.username, config.password)
                pipeline_svc = PipelineService(client)
                papers = pipeline_svc.list_papers(workspace_id=slr_results["workspace_id"])
                if papers:
                    _run_and_track("Interactive Paper Chat", run_chat_multiturn_scenario, slr_results["workspace_id"], papers[0]["id"], config)

            # 3. Agent Lifecycle (Pause / Resume)
            _run_and_track("Agent Lifecycle", run_agent_lifecycle_scenario, config)

            # 4. Pipeline Reprocessing
            _run_and_track("Pipeline Reprocessing", run_pipeline_reprocessing_scenario, config)

            # 5. Cross-Source Deduplication
            _run_and_track("Cross-Source Deduplication", run_cross_source_dedup_scenario, config)

            # 6. Quota Guard & Budget Limits
            _run_and_track("Quota Guard & Limits", run_quota_guard_scenario, config)

            # 7. FastMCP Protocol & AI Tools
            _run_and_track("FastMCP Protocol Tools", run_mcp_protocol_scenario, config)

            # 8. RBAC Data Isolation
            _run_and_track("RBAC Data Isolation", run_rbac_data_isolation_scenario, config)

            # 9. Mid-Step Pipeline Rerun
            _run_and_track("Mid-Step Pipeline Rerun", run_mid_step_rerun_scenario, config)

            # 10. Chat Hallucination Guard
            _run_and_track("Chat Hallucination Guard", run_chat_hallucination_guard_scenario, config)

            # 11. Concurrent Agents Load
            _run_and_track("Concurrent Agents Load", run_concurrent_agents_load_scenario, config, num_agents=2)

            # 11b. Run Admission Guard (cap + duplicate window, needs Postgres row lock)
            _run_and_track("Run Admission Guard", run_run_admission_guard_scenario, config)

            # 12. Workflow Schedule & Observability
            _run_and_track("Workflow Schedule & Observability", run_workflow_schedule_scenario, config)

            # 13. Scraper Date Range & Results Pagination
            _run_and_track("Scraper Date Range & Results Pagination", run_date_range_and_pagination_scenario, config)

            # 14. Ask Paper Complete User Journey
            _run_and_track("Ask Paper Complete Journey", run_ask_paper_journey_scenario, config, workspace_id=slr_results.get("workspace_id"))

            # 15. Signal Score Variables & Math Verification
            _run_and_track("Signal Score Variables & Math", run_signal_score_variables_scenario, config)

            # 16. Workspace Template Export & Import Journey
            _run_and_track("Workspace Template Export & Import", run_workspace_import_export_scenario, config)

            # 17. Direct Full-Text Screening & Subscriber Lifecycle
            _run_and_track("Direct Full-Text & Subscribers", run_direct_full_text_and_subscribers_scenario, config)

            # 18. Human-in-the-Loop Validation Journey
            _run_and_track("Human-in-the-Loop Validation", run_hitl_validation_journey_scenario, config)

            # 19. Stars Curation Journey
            _run_and_track("Stars Curation Journey", run_stars_curation_journey_scenario, config)

            # 20. Paper Page Scorecard Journey
            _run_and_track("Paper Page Scorecard Journey", run_paper_page_scorecard_journey_scenario, config)

            # 21. Executive Briefing Export
            briefing_res = _run_and_track(
                "Executive Briefing Export",
                run_executive_briefing_export_scenario,
                config,
                preserve_workspace=True,
            )

            # 22. Briefing Filters, Scope & Pagination
            _run_and_track(
                "Briefing Filters, Scope & Pagination",
                run_briefing_filters_and_pagination_scenario,
                config,
                workspace_id=briefing_res.get("workspace_id") if isinstance(briefing_res, dict) else None,
            )

            # 23. Three Personas RBAC Journey
            _run_and_track(
                "Three Personas RBAC Journey",
                run_three_personas_rbac_journey_scenario,
                config,
            )

            total_elapsed = time.time() - t0
            print_suite_summary(suite_results, total_elapsed, config=config)

        sys.exit(0)
    except Exception as exc:
        total_elapsed = time.time() - t0
        logger.exception(f"❌ E2E Execution Failed after {total_elapsed:.1f}s: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
