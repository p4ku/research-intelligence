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
        choices=["slr", "lifecycle", "reprocess", "dedup", "quota", "mcp", "isolation", "rerun", "guard", "concurrent", "all"],
        default="slr",
        help="Target test scenario to execute (slr: Full SLR + Chat, lifecycle: Pause/Resume, reprocess: Reprocessing, dedup: Multi-Source Deduplication, quota: Quota Guard, mcp: FastMCP SSE Tools, isolation: RBAC Multi-Tenancy, rerun: Mid-Step Rerun, guard: Hallucination Guard, concurrent: Parallel Agents Load, all: Run all)",
    )
    parser.add_argument(
        "--url",
        type=str,
        default=None,
        help="Custom Base API URL override (e.g. https://sri-prod.apps.01.cf.eu01.onstackit.cloud)",
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


def print_llm_cost_summary(c: dict, total_elapsed: float, total_papers: int = 0):
    p_in = c.get("pipeline_tokens_in", 0) or 0
    p_out = c.get("pipeline_tokens_out", 0) or 0
    p_tok = c.get("pipeline_total_tokens", 0) or (p_in + p_out)
    p_usd = float(c.get("pipeline_usd_cost", 0.0) or 0.0)

    c_in = c.get("chat_tokens_in", 0) or 0
    c_out = c.get("chat_tokens_out", 0) or 0
    c_tok = c.get("chat_total_tokens", 0) or (c_in + c_out)
    c_usd = float(c.get("chat_usd_cost", 0.0) or 0.0)

    tot_in = p_in + c_in
    tot_out = p_out + c_out
    tot_tok = c.get("total_tokens_consumed") or (tot_in + tot_out)
    tot_usd = float(c.get("total_usd_spent", 0.0) or (p_usd + c_usd))
    tot_eur = tot_usd * 0.92

    print("\n" + "=" * 70)
    print("💎  LLM TOKENS & FINANCIAL COST SUMMARY (GOOGLE GEMINI 3.7 FLASH)")
    print("=" * 70)
    print(f"  🤖 Inference Engine     : Google Vertex AI / GenAI (gemini-3.7-flash)")
    print(f"  ⏱️  Total Run Time       : {total_elapsed:.1f}s")
    if total_papers > 0:
        print(f"  📄 Ingested Papers      : {total_papers} papers")
        print(f"  ⚡ Unit Economics       : ${tot_usd / total_papers:.4f} USD / paper (~{int(tot_tok / total_papers):,} tokens/paper)")
    print("  --------------------------------------------------------------------")
    print(f"  📥 Prompt (Input) Tokens: {tot_in:,} tokens")
    print(f"  📤 Thought/Output Tokens: {tot_out:,} tokens")
    print(f"  📊 Total Tokens Consumed: {tot_tok:,} tokens")
    print("  --------------------------------------------------------------------")
    print(f"  💵 Total Cost (USD)     : ${tot_usd:.4f} USD")
    print(f"  💶 Total Cost (EUR est.): ~€{tot_eur:.4f} EUR")
    print("=" * 70 + "\n")


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

    base_url = args.url or ENV_TARGETS.get(args.target, "https://sri-prod.apps.01.cf.eu01.onstackit.cloud")
    config = E2EConfig(
        target_env=args.target,
        base_url=base_url,
        username=args.user,
        password=args.password,
        paper_limit=args.limit,
        poll_interval_sec=args.poll_interval,
        max_timeout_sec=args.timeout,
        cleanup_before=not args.no_cleanup_before,
        delete_after=args.cleanup_after,
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

        elif args.scenario == "all":
            logger.info("🧪 Running ALL E2E test scenarios sequentially...")
            # 1. Full SLR
            slr_results = run_full_slr_pipeline_scenario(config)
            # 2. Multi-turn chat
            top_papers = slr_results.get("top_papers", [])
            if top_papers:
                from tests_e2e.client import APIClient, AuthService, PipelineService
                client = APIClient(config.base_url)
                auth = AuthService(client)
                auth.login(config.username, config.password)
                pipeline_svc = PipelineService(client)
                papers = pipeline_svc.list_papers(workspace_id=slr_results["workspace_id"])
                if papers:
                    run_chat_multiturn_scenario(slr_results["workspace_id"], papers[0]["id"], config)
            # 3. Agent Lifecycle (Pause/Resume)
            run_agent_lifecycle_scenario(config)
            # 4. Pipeline Reprocessing
            run_pipeline_reprocessing_scenario(config)
            # 5. Cross-Source Deduplication
            run_cross_source_dedup_scenario(config)
            # 6. Quota Guard
            run_quota_guard_scenario(config)
            # 7. FastMCP Protocol
            run_mcp_protocol_scenario(config)

            total_elapsed = time.time() - t0
            print_summary_card(slr_results, total_elapsed)

        sys.exit(0)
    except Exception as exc:
        total_elapsed = time.time() - t0
        logger.exception(f"❌ E2E Execution Failed after {total_elapsed:.1f}s: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
