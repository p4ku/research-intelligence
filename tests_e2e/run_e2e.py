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
from tests_e2e.scenarios.full_slr_pipeline import run_full_slr_pipeline_scenario

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
        "--keep-workspace",
        action="store_true",
        help="Keep the created test workspace instead of automatically deleting it and its storage files after test completion",
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

    if results.get("cost_metrics"):
        c = results["cost_metrics"]
        print("\n  💰 FINANCIAL & TOKEN ECONOMICS AUDIT:")
        print(f"     • Pipeline Prompt Tokens     : {c.get('pipeline_tokens_in', 0):,}")
        print(f"     • Pipeline Completion Tokens : {c.get('pipeline_tokens_out', 0):,}")
        print(f"     • Pipeline Total Tokens      : {c.get('pipeline_total_tokens', 0):,}")
        print(f"     • Pipeline USD Cost          : ${c.get('pipeline_usd_cost', 0.0):.4f} USD")
        if c.get("chat_total_tokens", 0) > 0:
            print(f"     • Chat Turn Tokens           : {c.get('chat_total_tokens', 0):,} (USD: ${c.get('chat_usd_cost', 0.0):.4f})")
        print(f"     • TOTAL RUN TOKENS CONSUMED  : {c.get('total_tokens_consumed', 0):,}")
        print(f"     • TOTAL RUN SPEND            : ${c.get('total_usd_spent', 0.0):.4f} USD")

    if results.get("cleaned_up"):
        print("\n  🧹 CLEANUP & ARTIFACTS PURGE : ✅ Test workspace, DB records & storage files deleted cleanly.")

    print("=" * 70)
    print("🎉 ALL CHECKS PASSED - PRODUCTION / STAGING INTEGRITY VERIFIED!\n")


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
        delete_after=not args.keep_workspace,
    )

    t0 = time.time()
    try:
        results = run_full_slr_pipeline_scenario(config)
        total_elapsed = time.time() - t0
        print_summary_card(results, total_elapsed)
        sys.exit(0)
    except Exception as exc:
        total_elapsed = time.time() - t0
        logger.exception(f"❌ E2E Execution Failed after {total_elapsed:.1f}s: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
