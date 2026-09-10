import logging
from typing import Dict, List, Any, Optional, Set
from django.utils import timezone
from django.db import transaction, connection

from .base_node import BaseWorkflowNode

logger = logging.getLogger(__name__)


def sync_pipeline_run_stage_results(pipeline_run, dag_nodes, config=None, agent_process=None, comp_runs=None) -> Dict[str, Any]:
    """
    Synchronizes all stage results into pipeline_run.stage_results (and optionally
    agent_process.stage_results) by delegating to each node's get_stage_result_entry implementation.
    """
    from research_intelligence.models import ComponentRun
    stage_results = dict(pipeline_run.stage_results or (agent_process.stage_results if agent_process else {}))
    if comp_runs is None:
        comp_runs = list(ComponentRun.objects.filter(pipeline_run=pipeline_run).order_by('started_at', 'id'))
    else:
        comp_runs = list(comp_runs)
    cfg = config or {}

    for name, node in dag_nodes.items():
        if name == 'abstract_screening':
            node_runs = [cr for cr in comp_runs if cr.component_name == 'abstract_screening']
        elif name == 'full_text_screening':
            node_runs = [cr for cr in comp_runs if cr.component_name == 'full_text_screening']
        else:
            node_runs = [cr for cr in comp_runs if cr.step_type == node.step_type]

        if node_runs:
            last_run = node_runs[-1]
            stage_results[name] = node.get_stage_result_entry(comp_run=last_run)
        elif node.is_skippable(pipeline_run, pipeline_run.workspace, cfg):
            stage_results[name] = node.get_stage_result_entry(status="skipped")
        elif name not in stage_results:
            stage_results[name] = node.get_stage_result_entry(status="pending")

    pipeline_run.stage_results = stage_results
    if agent_process:
        agent_process.stage_results = stage_results
    return stage_results


def sync_agent_stage_results(agent_process, pipeline_run, dag_nodes, config=None) -> Dict[str, Any]:
    """
    Backwards-compatible wrapper for sync_pipeline_run_stage_results.
    """
    return sync_pipeline_run_stage_results(pipeline_run, dag_nodes, config=config, agent_process=agent_process)


class WorkflowDAG:
    """
    State-of-the-Art Directed Acyclic Graph (DAG) Workflow Orchestrator.
    
    Provides declarative graph definition, topological dependency resolution,
    parallel branch execution across distributed Celery workers, and restartable steps.
    """

    def __init__(self, name: str = "slr_pipeline_dag"):
        self.name = name
        self.nodes: Dict[str, BaseWorkflowNode] = {}

    def add_node(self, node: BaseWorkflowNode) -> "WorkflowDAG":
        """Adds a workflow node to the DAG."""
        self.nodes[node.name] = node
        return self

    def validate_graph(self) -> None:
        """
        Validates that all dependencies exist and there are no cyclic dependencies in the DAG.
        """
        for name, node in self.nodes.items():
            for dep in node.dependencies:
                if dep not in self.nodes:
                    raise ValueError(f"DAG validation error: Node '{name}' depends on unknown node '{dep}'.")

        # Cycle detection using DFS
        visited = {}  # name: 0 (unvisited), 1 (visiting), 2 (visited)
        for name in self.nodes:
            visited[name] = 0

        def dfs(node_name: str, path: List[str]):
            visited[node_name] = 1
            path.append(node_name)
            for dep in self.nodes[node_name].dependencies:
                # In our definition, node depends on 'dep', so edge is dep -> node
                # To check cycles in dependency graph:
                if visited[dep] == 1:
                    raise ValueError(f"DAG cycle detected: {' -> '.join(path + [dep])}")
                if visited[dep] == 0:
                    dfs(dep, path)
            visited[node_name] = 2
            path.pop()

        for name in self.nodes:
            if visited[name] == 0:
                dfs(name, [])

    def describe_pipeline(self) -> List[Dict[str, Any]]:
        """
        Returns a structured list describing every node in the DAG, its dependencies,
        description, input contract, and output contract.
        """
        result = []
        for name, node in self.nodes.items():
            result.append({
                "name": node.name,
                "step_type": node.step_type,
                "component_name": node.component_name,
                "description": getattr(node, 'description', ''),
                "dependencies": list(node.dependencies),
                "input_contract": getattr(node, 'input_contract', {}),
                "output_contract": getattr(node, 'output_contract', {}),
            })
        return result

    def get_downstream_nodes(self, start_node_name: str) -> Set[str]:
        """
        Returns the set of all downstream nodes that depend directly or indirectly on start_node_name.
        """
        downstream = set()

        def collect(parent_name: str):
            for name, node in self.nodes.items():
                if parent_name in node.dependencies and name not in downstream:
                    downstream.add(name)
                    collect(name)

        collect(start_node_name)
        return downstream

    def get_node_status_map(self, pipeline_run, config: Optional[Dict[str, Any]] = None, comp_runs: Optional[List] = None) -> Dict[str, str]:
        """
        Queries the database and returns a mapping of node_name -> status
        ('pending', 'running', 'completed', 'skipped', 'failed').
        """
        from research_intelligence.models import ComponentRun
        if comp_runs is None:
            comp_runs = list(ComponentRun.objects.filter(pipeline_run=pipeline_run).order_by('started_at', 'id'))
        else:
            comp_runs = list(comp_runs)

        status_map = {name: "pending" for name in self.nodes}
        cfg = config or {}

        for node_name, node in self.nodes.items():
            if node_name == 'abstract_screening':
                matching_runs = [cr for cr in comp_runs if cr.component_name == 'abstract_screening']
            elif node_name == 'full_text_screening':
                matching_runs = [cr for cr in comp_runs if cr.component_name == 'full_text_screening']
            elif node_name == 'screening':
                matching_runs = [cr for cr in comp_runs if cr.step_type == 'screening']
            else:
                matching_runs = [cr for cr in comp_runs if cr.step_type == node.step_type]

            m_statuses = {cr.status for cr in matching_runs}
            if 'running' in m_statuses:
                status_map[node_name] = "running"
            elif 'failed' in m_statuses and 'completed' not in m_statuses:
                status_map[node_name] = "failed"
            elif 'completed' in m_statuses:
                status_map[node_name] = "completed"
            elif 'skipped' in m_statuses:
                status_map[node_name] = "skipped"
            else:
                # If no matching runs for this node, but any downstream node has started or completed,
                # mark this prerequisite node as completed (implicit completion from downstream presence)
                downstream = self.get_downstream_nodes(node_name)
                downstream_started = False
                for d in downstream:
                    d_node = self.nodes[d]
                    if d == 'abstract_screening':
                        d_matches = [cr for cr in comp_runs if cr.component_name == 'abstract_screening']
                    elif d == 'full_text_screening':
                        d_matches = [cr for cr in comp_runs if cr.component_name == 'full_text_screening']
                    elif d == 'screening':
                        d_matches = [cr for cr in comp_runs if cr.step_type == 'screening']
                    else:
                        d_matches = [cr for cr in comp_runs if cr.step_type == d_node.step_type]

                    if any(cr.status in ('running', 'completed', 'skipped') for cr in d_matches):
                        downstream_started = True
                        break

                if downstream_started:
                    status_map[node_name] = "completed"
                else:
                    status_map[node_name] = "pending"

        return status_map

    def get_ready_nodes(self, pipeline_run, workspace, config: Optional[Dict[str, Any]] = None, status_map: Optional[Dict[str, str]] = None, comp_runs: Optional[List] = None) -> List[BaseWorkflowNode]:
        """
        Calculates all nodes whose dependencies are all satisfied ('completed' or 'skipped')
        and are currently 'pending'.
        """
        cfg = config or {}
        if status_map is None:
            status_map = self.get_node_status_map(pipeline_run, config=cfg, comp_runs=comp_runs)
        ready = []

        for name, node in self.nodes.items():
            if status_map.get(name) != "pending":
                continue

            # Check if all dependency nodes are satisfied
            deps_satisfied = True
            for dep_name in node.dependencies:
                dep_status = status_map.get(dep_name, "pending")
                if dep_status not in ("completed", "skipped"):
                    deps_satisfied = False
                    break

            if deps_satisfied:
                ready.append(node)

        return ready

    def evaluate_and_dispatch(
        self,
        pipeline_run,
        agent_process=None,
        config: Optional[Dict[str, Any]] = None,
        limit: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Main DAG execution driver. Evaluates current graph state, handles skippable nodes,
        and launches all ready nodes (in parallel on Celery workers).
        """
        from research_intelligence.models import ComponentRun, PipelineRun
        workspace = pipeline_run.workspace
        cfg = dict(config or {})
        if getattr(pipeline_run, 'configuration_override', None):
            cfg = {**pipeline_run.configuration_override, **cfg}
        if agent_process and getattr(agent_process, 'configuration_override', None):
            cfg = {**agent_process.configuration_override, **cfg}

        with transaction.atomic():
            if connection.vendor == 'postgresql':
                pipeline_run = PipelineRun.objects.select_for_update().get(id=pipeline_run.id)
            else:
                pipeline_run = PipelineRun.objects.get(id=pipeline_run.id)

            if pipeline_run.status in ('paused', 'aborted', 'failed', 'completed'):
                return {
                    "success": True,
                    "status": pipeline_run.status,
                    "current_step": pipeline_run.current_stage,
                    "message": f"PipelineRun in terminal or paused state: {pipeline_run.status}"
                }

            if agent_process:
                # Refresh with row lock
                from research_intelligence.models import ResearchAgentProcess
                if connection.vendor == 'postgresql':
                    agent_process = ResearchAgentProcess.objects.select_for_update().get(id=agent_process.id)
                else:
                    agent_process = ResearchAgentProcess.objects.get(id=agent_process.id)
                if agent_process.status in ('paused', 'aborted', 'failed', 'completed'):
                    return {
                        "success": True,
                        "status": agent_process.status,
                        "current_step": agent_process.current_step,
                        "message": f"Process in terminal or paused state: {agent_process.status}"
                    }

            comp_runs = list(ComponentRun.objects.filter(pipeline_run=pipeline_run).order_by('started_at', 'id'))
            status_map = self.get_node_status_map(pipeline_run, config=cfg, comp_runs=comp_runs)
            sync_pipeline_run_stage_results(pipeline_run, self.nodes, config=cfg, agent_process=agent_process, comp_runs=comp_runs)

            # 0. Check Workspace Monthly Quota & Budget Enforcement
            is_exceeded, quota_reason = workspace.is_quota_exceeded()
            if is_exceeded:
                logger.warning(f"🛑 [QUOTA LIMIT EXCEEDED] Workspace '{workspace.name}': {quota_reason}")
                pipeline_run.status = 'failed'
                pipeline_run.status_message = quota_reason
                pipeline_run.stopped_at_stage = pipeline_run.current_stage
                pipeline_run.completed_at = timezone.now()
                p_hist = list(pipeline_run.step_history or [])
                p_hist.append({
                    "step": pipeline_run.current_stage,
                    "event": "quota_exceeded",
                    "message": quota_reason,
                    "timestamp": timezone.now().isoformat()
                })
                pipeline_run.step_history = p_hist
                pipeline_run.save(update_fields=['status', 'status_message', 'stopped_at_stage', 'completed_at', 'step_history', 'stage_results'])

                if agent_process:
                    agent_process.status = 'failed'
                    agent_process.stopped_at_step = agent_process.current_step
                    agent_process.stop_reason = quota_reason
                    agent_process.error_message = quota_reason
                    agent_process.completed_at = timezone.now()
                    history = list(agent_process.step_history or [])
                    history.append({
                        "step": agent_process.current_step,
                        "event": "quota_exceeded",
                        "message": quota_reason,
                        "timestamp": timezone.now().isoformat()
                    })
                    agent_process.step_history = history
                    agent_process.save(update_fields=['status', 'stopped_at_step', 'stop_reason', 'stage_results', 'error_message', 'completed_at', 'step_history', 'updated_at'])

                from research_intelligence.tasks.orchestrator.agent_engine import _send_agent_notification
                _send_agent_notification(agent_process or pipeline_run)

                return {
                    "success": False,
                    "status": "failed",
                    "current_step": pipeline_run.current_stage,
                    "error": quota_reason
                }

            # 1. Check for any failed nodes
            failed_nodes = [name for name, st in status_map.items() if st == "failed"]
            if failed_nodes:
                failed_node_name = failed_nodes[0]
                if failed_node_name == 'abstract_screening':
                    failed_comp_run = ComponentRun.objects.filter(pipeline_run=pipeline_run, component_name='abstract_screening', status='failed').first()
                elif failed_node_name == 'full_text_screening':
                    failed_comp_run = ComponentRun.objects.filter(pipeline_run=pipeline_run, component_name='full_text_screening', status='failed').first()
                else:
                    failed_comp_run = ComponentRun.objects.filter(
                        pipeline_run=pipeline_run,
                        step_type=self.nodes[failed_node_name].step_type,
                        status='failed'
                    ).first()
                err_msg = (failed_comp_run.error_message if failed_comp_run else f"Node '{failed_node_name}' failed.")
                fail_summary = f"Failed during '{failed_node_name}': {err_msg}"
                
                pipeline_run.status = 'failed'
                pipeline_run.status_message = fail_summary
                pipeline_run.error_message = err_msg
                pipeline_run.stopped_at_stage = failed_node_name
                pipeline_run.completed_at = timezone.now()
                p_hist = list(pipeline_run.step_history or [])
                p_hist.append({
                    "step": failed_node_name,
                    "event": "failed",
                    "message": err_msg,
                    "timestamp": timezone.now().isoformat()
                })
                pipeline_run.step_history = p_hist
                pipeline_run.save(update_fields=['status', 'status_message', 'error_message', 'stopped_at_stage', 'completed_at', 'step_history', 'stage_results'])

                if agent_process and (agent_process is not pipeline_run):
                    agent_process.status = 'failed'
                    agent_process.stopped_at_step = failed_node_name
                    agent_process.stop_reason = fail_summary
                    agent_process.error_message = err_msg
                    agent_process.completed_at = timezone.now()
                    agent_process.save(update_fields=['status', 'stopped_at_step', 'stop_reason', 'stage_results', 'error_message', 'completed_at', 'updated_at'])

                from research_intelligence.tasks.orchestrator.agent_engine import _send_agent_notification
                _send_agent_notification(agent_process or pipeline_run)

                return {"success": False, "status": "failed", "error": err_msg}

            # 2. Check for early halting conditions (e.g. 0 papers found or accepted)
            for name, st in status_map.items():
                if st == "completed":
                    node = self.nodes.get(name)
                    if node:
                        should_halt, halt_reason = node.should_halt_pipeline(pipeline_run, workspace, cfg)
                        if should_halt:
                            logger.info(f"Pipeline halted early at node '{name}': {halt_reason}")
                            pipeline_run.status = 'completed'
                            pipeline_run.current_stage = 'completed'
                            pipeline_run.stopped_at_stage = name
                            pipeline_run.status_message = halt_reason
                            pipeline_run.completed_at = timezone.now()
                            p_hist = list(pipeline_run.step_history or [])
                            event_name = "halted_zero_papers" if ("0 papers" in halt_reason.lower() or "0 new papers" in halt_reason.lower()) else "completed"
                            p_hist.append({
                                "step": name,
                                "event": event_name,
                                "message": halt_reason,
                                "timestamp": timezone.now().isoformat()
                            })
                            pipeline_run.step_history = p_hist
                            pipeline_run.save(update_fields=['status', 'current_stage', 'stopped_at_stage', 'status_message', 'completed_at', 'step_history', 'stage_results'])

                            if agent_process and (agent_process is not pipeline_run):
                                agent_process.status = 'completed'
                                agent_process.current_step = 'completed'
                                agent_process.stopped_at_step = name
                                agent_process.stop_reason = halt_reason
                                agent_process.completed_at = timezone.now()
                                history = list(agent_process.step_history or [])
                                history.append({
                                    "step": name,
                                    "event": event_name,
                                    "message": halt_reason,
                                    "timestamp": timezone.now().isoformat()
                                })
                                agent_process.step_history = history
                                agent_process.save(update_fields=['status', 'current_step', 'stopped_at_step', 'stop_reason', 'stage_results', 'completed_at', 'step_history', 'updated_at'])

                            from research_intelligence.tasks.orchestrator.agent_engine import _send_agent_notification
                            _send_agent_notification(agent_process or pipeline_run)

                            return {
                                "success": True,
                                "status": "completed",
                                "current_step": "completed",
                                "stopped_at_step": name,
                                "message": halt_reason
                            }

            # 3. Resolve Ready Nodes and Dispatch
            ready_nodes = self.get_ready_nodes(pipeline_run, workspace, config=cfg, status_map=status_map)
            dispatched = []

            # First pass: mark all skippable ready nodes as skipped
            skipped_nodes = []
            for node in ready_nodes:
                if node.is_skippable(pipeline_run, workspace, cfg):
                    logger.info(f"DAG Node '{node.name}' is skippable for workspace '{workspace.name}'. Marking skipped.")
                    ComponentRun.objects.create(
                        pipeline_run=pipeline_run,
                        step_type=node.step_type,
                        component_name=node.component_name,
                        status='skipped',
                        started_at=timezone.now(),
                        completed_at=timezone.now(),
                        metrics={"status": "skipped"},
                        input_params=node.get_input_params(pipeline_run, workspace, cfg, limit=limit)
                    )
                    skipped_nodes.append(node.name)

            if skipped_nodes:
                # Re-evaluate recursively to dispatch downstream nodes immediately
                res = self.evaluate_and_dispatch(pipeline_run, agent_process=agent_process, config=cfg, limit=limit)
                if 'ocr' in skipped_nodes and res.get("success"):
                    res["message"] = f"OCR skipped (workspace.ocr_provider is None). {res.get('message', '')}"
                return res

            for node in ready_nodes:
                # Create ComponentRun and dispatch
                input_params = node.get_input_params(pipeline_run, workspace, cfg, limit=limit)
                comp_name = node.component_name

                comp_run = ComponentRun.objects.create(
                    pipeline_run=pipeline_run,
                    step_type=node.step_type,
                    component_name=comp_name,
                    status='running',
                    input_params=input_params
                )

                pipeline_run.current_stage = node.name
                p_hist = list(pipeline_run.step_history or [])
                p_hist.append({
                    "step": node.name,
                    "event": "started",
                    "timestamp": timezone.now().isoformat()
                })
                pipeline_run.step_history = p_hist
                pipeline_run.save(update_fields=['current_stage', 'step_history', 'stage_results'])

                if agent_process and (agent_process is not pipeline_run):
                    agent_process.current_step = node.name
                    history = list(agent_process.step_history or [])
                    history.append({
                        "step": node.name,
                        "event": "started",
                        "timestamp": timezone.now().isoformat()
                    })
                    agent_process.step_history = history
                    agent_process.save(update_fields=['current_step', 'stage_results', 'step_history', 'updated_at'])

                node.execute(pipeline_run, comp_run, limit=limit)
                dispatched.append(node.name)

            if dispatched:
                return {
                    "success": True,
                    "status": "running",
                    "current_step": dispatched[0],
                    "dispatched_nodes": dispatched,
                    "message": f"Dispatched DAG node(s): {', '.join(dispatched)}"
                }

            # 5. If any node is still running, report waiting and synchronize active step
            running_nodes = [name for name, st in status_map.items() if st == "running"]
            if running_nodes:
                active_step = self.nodes[running_nodes[0]].name
                pipeline_run.current_stage = active_step
                pipeline_run.save(update_fields=['current_stage', 'stage_results'])

                if agent_process and (agent_process is not pipeline_run):
                    if agent_process.current_step != active_step:
                        agent_process.current_step = active_step
                    agent_process.save(update_fields=['current_step', 'stage_results', 'updated_at'])

                return {
                    "success": True,
                    "status": "running",
                    "current_step": running_nodes[0],
                    "message": f"DAG nodes currently running: {', '.join(running_nodes)}"
                }

            # 6. If all non-skippable nodes are completed / skipped -> COMPLETED!
            all_done = all(st in ("completed", "skipped") for st in status_map.values())
            if all_done:
                from research_intelligence.models import Extraction
                ft_status = status_map.get('full_text_screening')
                abs_status = status_map.get('abstract_screening')
                if ft_status == 'completed':
                    accepted_count = pipeline_run.get_papers(screening_status=['accepted', 'full_text_passed']).count()
                elif abs_status == 'completed':
                    accepted_count = pipeline_run.get_papers(screening_status=['accepted', 'abstract_passed']).count()
                elif abs_status == 'skipped' and ft_status == 'skipped':
                    accepted_count = pipeline_run.get_papers(exclude_status=['rejected', 'withdrawn']).count()
                else:
                    accepted_count = pipeline_run.get_papers(screening_status=['accepted', 'full_text_passed', 'abstract_passed']).count()

                extracted_count = Extraction.objects.filter(paper__in=pipeline_run.get_papers()).count()
                total_fetched = pipeline_run.get_papers().count()
                summary_msg = (
                    f"Full pipeline finished successfully. "
                    f"Papers: {total_fetched} fetched, {accepted_count} passed screening, "
                    f"{extracted_count} parameter extractions completed."
                )

                pipeline_run.status = 'completed'
                pipeline_run.current_stage = 'completed'
                pipeline_run.stopped_at_stage = 'completed'
                pipeline_run.status_message = summary_msg
                if not pipeline_run.completed_at:
                    pipeline_run.completed_at = timezone.now()

                # Refresh and aggregate USD cost and tokens across component runs if needed
                from decimal import Decimal
                comp_costs = sum(
                    float((cr.metrics or {}).get("usd_cost") or 0.0)
                    for cr in comp_runs
                )
                if comp_costs > float(pipeline_run.usd_cost or 0.0):
                    pipeline_run.usd_cost = Decimal(str(round(comp_costs, 4)))

                comp_tokens_in = sum(int((cr.metrics or {}).get("tokens_in", (cr.metrics or {}).get("total_prompt_tokens", 0)) or 0) for cr in comp_runs)
                comp_tokens_out = sum(int((cr.metrics or {}).get("tokens_out", (cr.metrics or {}).get("total_candidates_tokens", 0)) or 0) for cr in comp_runs)
                comp_tokens = sum(int((cr.metrics or {}).get("tokens_consumed", (cr.metrics or {}).get("total_tokens", (cr.metrics or {}).get("total_tokens_consumed", 0))) or 0) for cr in comp_runs)

                if comp_tokens > (pipeline_run.tokens_consumed or 0):
                    pipeline_run.tokens_consumed = comp_tokens
                if comp_tokens_in > (pipeline_run.tokens_in or 0):
                    pipeline_run.tokens_in = comp_tokens_in
                if comp_tokens_out > (pipeline_run.tokens_out or 0):
                    pipeline_run.tokens_out = comp_tokens_out

                pipeline_run.total_papers_passed_screening = accepted_count
                p_hist = list(pipeline_run.step_history or [])
                p_hist.append({
                    "step": "pipeline",
                    "event": "completed",
                    "message": summary_msg,
                    "timestamp": timezone.now().isoformat()
                })
                pipeline_run.step_history = p_hist

                pipeline_run.save(update_fields=[
                    'status', 'current_stage', 'stopped_at_stage', 'status_message', 'completed_at',
                    'usd_cost', 'tokens_in', 'tokens_out', 'tokens_consumed',
                    'total_papers_passed_screening', 'step_history', 'stage_results'
                ])

                if agent_process and (agent_process is not pipeline_run):
                    agent_process.status = 'completed'
                    agent_process.current_step = 'completed'
                    agent_process.stopped_at_step = 'completed'
                    agent_process.stop_reason = summary_msg
                    if not agent_process.completed_at:
                        agent_process.completed_at = timezone.now()
                    history = list(agent_process.step_history or [])
                    history.append({
                        "step": "pipeline",
                        "event": "completed",
                        "message": summary_msg,
                        "timestamp": timezone.now().isoformat()
                    })
                    agent_process.step_history = history
                    agent_process.save(update_fields=['status', 'current_step', 'stopped_at_step', 'stop_reason', 'stage_results', 'completed_at', 'step_history', 'updated_at'])

                from research_intelligence.tasks.orchestrator.agent_engine import _send_agent_notification
                _send_agent_notification(agent_process or pipeline_run)

                return {
                    "success": True,
                    "status": "completed",
                    "current_step": "completed",
                    "stopped_at_step": "completed",
                    "message": summary_msg
                }

            return {
                "success": True,
                "status": "running",
                "message": "DAG waiting for active components."
            }

    def rerun_from_node(self, pipeline_run, node_name: str) -> None:
        """
        Resets the target node and all downstream dependent nodes in the database,
        allowing the workflow to re-execute from that step forward.
        """
        if node_name not in self.nodes:
            raise ValueError(f"Unknown node '{node_name}' for DAG '{self.name}'.")

        downstream_nodes = self.get_downstream_nodes(node_name)
        affected_nodes = {node_name} | downstream_nodes

        from research_intelligence.models import ComponentRun, PaperMetric, Extraction, NarrativeReport
        from django.db.models import Q

        with transaction.atomic():
            for n in affected_nodes:
                if n == 'abstract_screening':
                    ComponentRun.objects.filter(
                        pipeline_run=pipeline_run
                    ).filter(Q(component_name='abstract_screening') | (Q(step_type='screening') & ~Q(component_name='full_text_screening'))).delete()
                elif n == 'full_text_screening':
                    ComponentRun.objects.filter(
                        pipeline_run=pipeline_run,
                        component_name='full_text_screening'
                    ).delete()
                else:
                    ComponentRun.objects.filter(
                        pipeline_run=pipeline_run,
                        step_type=self.nodes[n].step_type
                    ).delete()

            # Clean data state of downstream affected nodes
            if 'abstract_screening' in affected_nodes:
                pms = list(pipeline_run.paper_metrics.all())
                for pm in pms:
                    pm.screening_status = 'pending'
                    pm.abstract_screening_reasoning = ''
                    pm.full_text_screening_reasoning = ''
                    if isinstance(pm.metrics_data, dict):
                        m_data = dict(pm.metrics_data)
                        m_data.pop('abstract_screening', None)
                        m_data.pop('full_text_screening', None)
                        pm.metrics_data = m_data
                    pm.signal_score = None
                    pm.signal_score_details = {}
                if pms:
                    PaperMetric.objects.bulk_update(
                        pms,
                        ['screening_status', 'abstract_screening_reasoning', 'full_text_screening_reasoning', 'metrics_data', 'signal_score', 'signal_score_details'],
                        batch_size=500
                    )
                paper_ids = [pm.paper_id for pm in pms]
                Extraction.objects.filter(workspace=pipeline_run.workspace, paper_id__in=paper_ids).delete()
                pipeline_run.reports.all().delete()
                pipeline_run.total_papers_passed_screening = 0

            elif 'full_text_screening' in affected_nodes:
                pms = list(pipeline_run.paper_metrics.all())
                pms_to_update = []
                for pm in pms:
                    has_ft = (
                        (pm.metrics_data and 'full_text_screening' in pm.metrics_data) or
                        bool(pm.full_text_screening_reasoning) or
                        pm.screening_status == 'full_text_passed'
                    )
                    if has_ft:
                        has_abstract_pass = (
                            (pm.metrics_data and pm.metrics_data.get('abstract_screening', {}).get('passed') is True) or
                            bool(pm.abstract_screening_reasoning)
                        )
                        pm.screening_status = 'abstract_passed' if has_abstract_pass else 'pending'
                        pm.full_text_screening_reasoning = ''
                        if isinstance(pm.metrics_data, dict):
                            m_data = dict(pm.metrics_data)
                            m_data.pop('full_text_screening', None)
                            pm.metrics_data = m_data
                        pm.signal_score = None
                        pm.signal_score_details = {}
                        pms_to_update.append(pm)
                if pms_to_update:
                    PaperMetric.objects.bulk_update(
                        pms_to_update,
                        ['screening_status', 'full_text_screening_reasoning', 'metrics_data', 'signal_score', 'signal_score_details'],
                        batch_size=500
                    )
                paper_ids = [pm.paper_id for pm in pms]
                Extraction.objects.filter(workspace=pipeline_run.workspace, paper_id__in=paper_ids).delete()
                pipeline_run.reports.all().delete()
                pipeline_run.total_papers_passed_screening = pipeline_run.get_papers(
                    screening_status=['abstract_passed', 'accepted']
                ).count()

            elif 'extraction' in affected_nodes:
                paper_ids = list(pipeline_run.paper_metrics.values_list('paper_id', flat=True))
                Extraction.objects.filter(workspace=pipeline_run.workspace, paper_id__in=paper_ids).delete()
                pipeline_run.paper_metrics.update(signal_score=None, signal_score_details={})
                pipeline_run.reports.all().delete()

            elif 'signal_score' in affected_nodes:
                pipeline_run.paper_metrics.update(signal_score=None, signal_score_details={})
                pipeline_run.reports.all().delete()

            elif 'reporting' in affected_nodes:
                pipeline_run.reports.all().delete()

            pipeline_run.status = 'running'
            pipeline_run.current_stage = self.nodes[node_name].step_type
            pipeline_run.save(update_fields=['status', 'current_stage', 'total_papers_passed_screening'])
