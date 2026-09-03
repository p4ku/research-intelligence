import logging
from typing import Dict, List, Any, Optional, Set
from django.utils import timezone
from django.db import transaction

from .base_node import BaseWorkflowNode

logger = logging.getLogger(__name__)


def sync_agent_stage_results(agent_process, pipeline_run, dag_nodes, config=None) -> Dict[str, Any]:
    """
    Synchronizes all stage results into the agent_process.stage_results dictionary
    by delegating to each node's polymorphic get_stage_result_entry implementation.
    """
    from research_intelligence.models import ComponentRun
    stage_results = dict(agent_process.stage_results or {})
    comp_runs = ComponentRun.objects.filter(pipeline_run=pipeline_run).order_by('started_at', 'id')
    cfg = config or {}

    for name, node in dag_nodes.items():
        if name == 'abstract_screening':
            node_runs = comp_runs.filter(component_name='abstract_screening')
        elif name == 'full_text_screening':
            node_runs = comp_runs.filter(component_name='full_text_screening')
        else:
            node_runs = comp_runs.filter(step_type=node.step_type)

        if node_runs.exists():
            last_run = node_runs.last()
            stage_results[name] = node.get_stage_result_entry(comp_run=last_run)
        elif node.is_skippable(pipeline_run, pipeline_run.workspace, cfg):
            stage_results[name] = node.get_stage_result_entry(status="skipped")
        elif name not in stage_results:
            stage_results[name] = node.get_stage_result_entry(status="pending")

    agent_process.stage_results = stage_results
    return stage_results


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

    def get_node_status_map(self, pipeline_run, config: Optional[Dict[str, Any]] = None) -> Dict[str, str]:
        """
        Queries the database and returns a mapping of node_name -> status
        ('pending', 'running', 'completed', 'skipped', 'failed').
        """
        from research_intelligence.models import ComponentRun
        comp_runs = ComponentRun.objects.filter(pipeline_run=pipeline_run).order_by('started_at', 'id')

        status_map = {name: "pending" for name in self.nodes}
        cfg = config or {}

        for node_name, node in self.nodes.items():
            if node_name == 'abstract_screening':
                matching_runs = comp_runs.filter(component_name='abstract_screening')
            elif node_name == 'full_text_screening':
                matching_runs = comp_runs.filter(component_name='full_text_screening')
            elif node_name == 'screening':
                matching_runs = comp_runs.filter(step_type='screening')
            else:
                matching_runs = comp_runs.filter(step_type=node.step_type)

            if matching_runs.filter(status='running').exists():
                status_map[node_name] = "running"
            elif matching_runs.filter(status='failed').exists() and not matching_runs.filter(status='completed').exists():
                status_map[node_name] = "failed"
            elif matching_runs.filter(status='completed').exists():
                status_map[node_name] = "completed"
            elif matching_runs.filter(status='skipped').exists():
                status_map[node_name] = "skipped"
            else:
                # If no matching runs for this node, but any downstream node has started or completed,
                # mark this prerequisite node as completed (implicit completion from downstream presence)
                downstream = self.get_downstream_nodes(node_name)
                downstream_started = False
                for d in downstream:
                    d_node = self.nodes[d]
                    if d == 'abstract_screening':
                        d_matches = comp_runs.filter(component_name='abstract_screening')
                    elif d == 'full_text_screening':
                        d_matches = comp_runs.filter(component_name='full_text_screening')
                    elif d == 'screening':
                        d_matches = comp_runs.filter(step_type='screening')
                    else:
                        d_matches = comp_runs.filter(step_type=d_node.step_type)

                    if d_matches.filter(status__in=['running', 'completed', 'skipped']).exists():
                        downstream_started = True
                        break

                if downstream_started:
                    status_map[node_name] = "completed"
                else:
                    status_map[node_name] = "pending"

        return status_map

    def get_ready_nodes(self, pipeline_run, workspace, config: Optional[Dict[str, Any]] = None) -> List[BaseWorkflowNode]:
        """
        Calculates all nodes whose dependencies are all satisfied ('completed' or 'skipped')
        and are currently 'pending'.
        """
        cfg = config or {}
        status_map = self.get_node_status_map(pipeline_run, config=cfg)
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
        from research_intelligence.models import ComponentRun
        workspace = pipeline_run.workspace
        cfg = dict(config or {})
        if agent_process and getattr(agent_process, 'configuration_override', None):
            cfg = {**agent_process.configuration_override, **cfg}

        with transaction.atomic():
            if agent_process:
                # Refresh with row lock
                from research_intelligence.models import ResearchAgentProcess
                agent_process = ResearchAgentProcess.objects.select_for_update().get(id=agent_process.id)
                if agent_process.status in ('paused', 'aborted', 'failed', 'completed'):
                    return {
                        "success": True,
                        "status": agent_process.status,
                        "current_step": agent_process.current_step,
                        "message": f"Process in terminal or paused state: {agent_process.status}"
                    }

            status_map = self.get_node_status_map(pipeline_run, config=cfg)
            if agent_process:
                sync_agent_stage_results(agent_process, pipeline_run, self.nodes, config=cfg)

            # 0. Check Workspace Monthly Quota & Budget Enforcement
            is_exceeded, quota_reason = workspace.is_quota_exceeded()
            if is_exceeded:
                logger.warning(f"🛑 [QUOTA LIMIT EXCEEDED] Workspace '{workspace.name}': {quota_reason}")
                pipeline_run.status = 'failed'
                pipeline_run.status_message = quota_reason
                pipeline_run.completed_at = timezone.now()
                pipeline_run.save(update_fields=['status', 'status_message', 'completed_at'])

                if agent_process:
                    sync_agent_stage_results(agent_process, pipeline_run, self.nodes, config=cfg)
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
                    _send_agent_notification(agent_process)

                return {
                    "success": False,
                    "status": "failed",
                    "current_step": agent_process.current_step if agent_process else "search",
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
                pipeline_run.completed_at = timezone.now()
                pipeline_run.save(update_fields=['status', 'status_message', 'completed_at'])

                if agent_process:
                    sync_agent_stage_results(agent_process, pipeline_run, self.nodes, config=cfg)
                    agent_process.status = 'failed'
                    agent_process.stopped_at_step = failed_node_name
                    agent_process.stop_reason = fail_summary
                    agent_process.error_message = err_msg
                    agent_process.completed_at = timezone.now()
                    agent_process.save(update_fields=['status', 'stopped_at_step', 'stop_reason', 'stage_results', 'error_message', 'completed_at', 'updated_at'])

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
                            pipeline_run.current_stage = name
                            pipeline_run.status_message = halt_reason
                            pipeline_run.completed_at = timezone.now()
                            pipeline_run.save(update_fields=['status', 'current_stage', 'status_message', 'completed_at'])
                            if agent_process:
                                sync_agent_stage_results(agent_process, pipeline_run, self.nodes, config=cfg)
                                agent_process.status = 'completed'
                                agent_process.current_step = 'completed'
                                agent_process.stopped_at_step = name
                                agent_process.stop_reason = halt_reason
                                agent_process.completed_at = timezone.now()
                                history = list(agent_process.step_history or [])
                                event_name = "halted_zero_papers" if ("0" in halt_reason and "paper" in halt_reason) else "completed"
                                history.append({
                                    "step": name,
                                    "event": event_name,
                                    "message": halt_reason,
                                    "timestamp": timezone.now().isoformat()
                                })
                                agent_process.step_history = history
                                agent_process.save(update_fields=['status', 'current_step', 'stopped_at_step', 'stop_reason', 'stage_results', 'completed_at', 'step_history', 'updated_at'])
                                from research_intelligence.tasks.orchestrator.agent_engine import _send_agent_notification
                                _send_agent_notification(agent_process)
                            return {
                                "success": True,
                                "status": "completed",
                                "current_step": "completed",
                                "stopped_at_step": name,
                                "message": halt_reason
                            }

            # 3. Resolve Ready Nodes and Dispatch
            ready_nodes = self.get_ready_nodes(pipeline_run, workspace, config=cfg)
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

                if agent_process:
                    sync_agent_stage_results(agent_process, pipeline_run, self.nodes, config=cfg)
                    agent_process.current_step = node.name
                    history = list(agent_process.step_history or [])
                    history.append({
                        "step": node.name,
                        "event": "started",
                        "timestamp": timezone.now().isoformat()
                    })
                    agent_process.step_history = history
                    agent_process.save(update_fields=['current_step', 'stage_results', 'step_history', 'updated_at'])

                pipeline_run.current_stage = node.name
                pipeline_run.save(update_fields=['current_stage'])

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
                if agent_process:
                    sync_agent_stage_results(agent_process, pipeline_run, self.nodes, config=cfg)
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
                accepted_count = pipeline_run.get_papers(screening_status=['accepted', 'full_text_passed']).count()
                extracted_count = Extraction.objects.filter(paper__in=pipeline_run.get_papers()).count()
                total_fetched = pipeline_run.get_papers().count()
                summary_msg = (
                    f"Full SLR pipeline finished successfully. "
                    f"Papers: {total_fetched} fetched, {accepted_count} passed screening, "
                    f"{extracted_count} parameter extractions completed."
                )

                pipeline_run.status = 'completed'
                pipeline_run.current_stage = 'completed'
                pipeline_run.status_message = summary_msg
                if not pipeline_run.completed_at:
                    pipeline_run.completed_at = timezone.now()

                # Refresh and aggregate USD cost and tokens across component runs if needed
                comp_costs = sum(
                    float((cr.metrics or {}).get("usd_cost") or 0.0)
                    for cr in pipeline_run.component_runs.all()
                )
                if comp_costs > float(pipeline_run.usd_cost or 0.0):
                    pipeline_run.usd_cost = comp_costs

                comp_tokens_in = sum(int((cr.metrics or {}).get("tokens_in", (cr.metrics or {}).get("total_prompt_tokens", 0)) or 0) for cr in pipeline_run.component_runs.all())
                comp_tokens_out = sum(int((cr.metrics or {}).get("tokens_out", (cr.metrics or {}).get("total_candidates_tokens", 0)) or 0) for cr in pipeline_run.component_runs.all())
                comp_tokens = sum(int((cr.metrics or {}).get("tokens_consumed", (cr.metrics or {}).get("total_tokens", (cr.metrics or {}).get("total_tokens_consumed", 0))) or 0) for cr in pipeline_run.component_runs.all())

                if comp_tokens > (pipeline_run.tokens_consumed or 0):
                    pipeline_run.tokens_consumed = comp_tokens
                if comp_tokens_in > (pipeline_run.tokens_in or 0):
                    pipeline_run.tokens_in = comp_tokens_in
                if comp_tokens_out > (pipeline_run.tokens_out or 0):
                    pipeline_run.tokens_out = comp_tokens_out

                pipeline_run.total_papers_passed_screening = accepted_count

                pipeline_run.save(update_fields=[
                    'status', 'current_stage', 'status_message', 'completed_at',
                    'usd_cost', 'tokens_in', 'tokens_out', 'tokens_consumed',
                    'total_papers_passed_screening'
                ])

                if agent_process:
                    sync_agent_stage_results(agent_process, pipeline_run, self.nodes, config=cfg)
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
                    _send_agent_notification(agent_process)

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

        from research_intelligence.models import ComponentRun
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

            pipeline_run.status = 'running'
            pipeline_run.current_stage = self.nodes[node_name].step_type
            pipeline_run.save(update_fields=['status', 'current_stage'])
