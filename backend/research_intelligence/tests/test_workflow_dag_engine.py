import uuid
from unittest.mock import patch, MagicMock
from django.test import TestCase
from django.contrib.auth.models import User
from django.utils import timezone

from research_intelligence.models import (
    Workspace,
    PipelineRun,
    ComponentRun,
    ResearchAgentProcess,
    Scraper,
    Paper,
)
from research_intelligence.tasks.orchestrator.dag.base_node import BaseWorkflowNode
from research_intelligence.tasks.orchestrator.dag.nodes import (
    SearchNode,
    DownloadNode,
    OCRNode,
    ScreeningNode,
    ExtractionNode,
    SignalScoreNode,
    ReportingNode,
)
from research_intelligence.tasks.orchestrator.dag.engine import (
    WorkflowDAG,
    build_default_slr_dag,
)


class TestWorkflowDAGTopologyAndNodes(TestCase):
    """
    Unit tests for DAG topological sort, cycle detection, downstream traversal,
    and node-level skippability.
    """

    def setUp(self):
        self.user = User.objects.create_user(username="dag_admin", password="password123")
        self.workspace = Workspace.objects.create(
            name="DAG Test Workspace",
            ocr_provider=None,
        )

    def test_default_slr_dag_construction_and_validation(self):
        dag = build_default_slr_dag(self.workspace)
        self.assertIn("search", dag.nodes)
        self.assertIn("download", dag.nodes)
        self.assertIn("ocr", dag.nodes)
        self.assertIn("screening", dag.nodes)
        self.assertIn("extraction", dag.nodes)
        self.assertIn("signal_score", dag.nodes)
        self.assertIn("reporting", dag.nodes)

        # Graph should validate without error
        dag.validate_graph()

    def test_dag_cycle_detection(self):
        dag = WorkflowDAG(name="cyclic_dag")
        node_a = SearchNode(name="node_a", dependencies=["node_b"])
        node_b = DownloadNode(name="node_b", dependencies=["node_a"])
        dag.add_node(node_a).add_node(node_b)

        with self.assertRaises(ValueError) as ctx:
            dag.validate_graph()
        self.assertIn("cycle detected", str(ctx.exception).lower())

    def test_dag_unknown_dependency_detection(self):
        dag = WorkflowDAG(name="broken_dag")
        node_a = SearchNode(name="node_a", dependencies=["non_existent_node"])
        dag.add_node(node_a)

        with self.assertRaises(ValueError) as ctx:
            dag.validate_graph()
        self.assertIn("depends on unknown node", str(ctx.exception).lower())

    def test_get_downstream_nodes_traversal(self):
        dag = build_default_slr_dag(self.workspace)
        downstream_from_search = dag.get_downstream_nodes("search")
        self.assertEqual(
            downstream_from_search,
            {"download", "ocr", "screening", "extraction", "signal_score", "reporting"}
        )

        downstream_from_extract = dag.get_downstream_nodes("extraction")
        self.assertEqual(downstream_from_extract, {"signal_score", "reporting"})

        downstream_from_reporting = dag.get_downstream_nodes("reporting")
        self.assertEqual(downstream_from_reporting, set())

    def test_ocr_node_skippability_when_provider_none(self):
        ocr_node = OCRNode()
        pipeline_run = PipelineRun.objects.create(workspace=self.workspace)

        # Workspace has ocr_provider=None -> should be skippable
        self.assertTrue(ocr_node.is_skippable(pipeline_run, self.workspace, {}))

        # If override provides 'mistral', should NOT be skippable
        self.assertFalse(ocr_node.is_skippable(pipeline_run, self.workspace, {"ocr_provider": "mistral"}))


class TestWorkflowDAGExecutionAndParallelBranches(TestCase):
    """
    Tests DAG state resolution, strict dependency sequencing, parallel branch execution,
    and partial re-runs.
    """

    def setUp(self):
        self.user = User.objects.create_user(username="dag_tester", password="password123")
        self.workspace = Workspace.objects.create(
            name="Execution DAG Workspace",
            ocr_provider=None,
        )
        self.pipeline_run = PipelineRun.objects.create(
            workspace=self.workspace,
            status='running'
        )

    def test_initial_ready_node_is_only_search(self):
        dag = build_default_slr_dag(self.workspace)
        ready_nodes = dag.get_ready_nodes(self.pipeline_run, self.workspace, {})
        self.assertEqual(len(ready_nodes), 1)
        self.assertEqual(ready_nodes[0].name, "search")

    def test_sequential_progression_prerequisites(self):
        dag = build_default_slr_dag(self.workspace)

        # 1. Complete Search
        ComponentRun.objects.create(
            pipeline_run=self.pipeline_run,
            step_type='search',
            component_name='workspace_search',
            status='completed'
        )
        ready_nodes = dag.get_ready_nodes(self.pipeline_run, self.workspace, {})
        self.assertEqual([n.name for n in ready_nodes], ["download"])

        # 2. Complete Download
        ComponentRun.objects.create(
            pipeline_run=self.pipeline_run,
            step_type='download',
            component_name='document_download',
            status='completed'
        )
        # OCR is ready in graph topology (and is skippable)
        ready_nodes = dag.get_ready_nodes(self.pipeline_run, self.workspace, {})
        self.assertEqual([n.name for n in ready_nodes], ["ocr"])

        # 3. Mark OCR as skipped
        ComponentRun.objects.create(
            pipeline_run=self.pipeline_run,
            step_type='ocr',
            component_name='layout_ocr',
            status='skipped'
        )
        ready_nodes = dag.get_ready_nodes(self.pipeline_run, self.workspace, {})
        self.assertEqual([n.name for n in ready_nodes], ["screening"])

        # 4. Strict sequential check: Signal score is NOT ready during screening or extraction
        self.assertNotIn("signal_score", [n.name for n in ready_nodes])

    def test_parallel_branch_dispatch(self):
        """
        Verify that a DAG with multiple independent branches launches ready nodes simultaneously.
        """
        dag = WorkflowDAG(name="parallel_branches_dag")

        class MockBranchNode(BaseWorkflowNode):
            def execute(self, pipeline_run, comp_run, limit=None):
                comp_run.status = 'completed'
                comp_run.save(update_fields=['status'])
                return {"status": "completed"}

        root = MockBranchNode(name="root_step", step_type="root", dependencies=[])
        branch_a = MockBranchNode(name="branch_a", step_type="branch_a", dependencies=["root_step"])
        branch_b = MockBranchNode(name="branch_b", step_type="branch_b", dependencies=["root_step"])
        join_node = MockBranchNode(name="join_step", step_type="join", dependencies=["branch_a", "branch_b"])

        dag.add_node(root).add_node(branch_a).add_node(branch_b).add_node(join_node)
        dag.validate_graph()

        # Mark root as completed
        ComponentRun.objects.create(
            pipeline_run=self.pipeline_run,
            step_type='root',
            component_name='root_step',
            status='completed'
        )

        # Both branch_a and branch_b must be ready concurrently
        ready = dag.get_ready_nodes(self.pipeline_run, self.workspace, {})
        self.assertEqual(set(n.name for n in ready), {"branch_a", "branch_b"})

        # Dispatch should launch both branches in parallel
        dispatch_res = dag.evaluate_and_dispatch(self.pipeline_run)
        self.assertTrue(dispatch_res["success"])
        self.assertIn("branch_a", dispatch_res["dispatched_nodes"])
        self.assertIn("branch_b", dispatch_res["dispatched_nodes"])

    def test_rerun_from_node_resets_downstream_only(self):
        dag = build_default_slr_dag(self.workspace)

        # Create full run history
        for step in ["search", "download", "ocr", "screening", "extraction", "signal_score"]:
            ComponentRun.objects.create(
                pipeline_run=self.pipeline_run,
                step_type=step,
                component_name=f"{step}_comp",
                status='completed'
            )

        self.assertEqual(ComponentRun.objects.filter(pipeline_run=self.pipeline_run).count(), 6)

        # Re-run from 'extraction'
        dag.rerun_from_node(self.pipeline_run, "extraction")

        remaining_steps = list(
            ComponentRun.objects.filter(pipeline_run=self.pipeline_run).values_list('step_type', flat=True)
        )
        # Search, download, ocr, screening should remain untouched
        self.assertIn("search", remaining_steps)
        self.assertIn("download", remaining_steps)
        self.assertIn("ocr", remaining_steps)
        self.assertIn("screening", remaining_steps)

        # Extraction and signal_score must have been purged/reset
        self.assertNotIn("extraction", remaining_steps)
        self.assertNotIn("signal_score", remaining_steps)


class TestMultiAgentParallelProgress(TestCase):
    """
    Tests that multiple ResearchAgentProcesses progress independently across Celery tasks.
    """

    def setUp(self):
        self.user = User.objects.create_user(username="multi_agent_user", password="password123")
        self.workspace1 = Workspace.objects.create(name="WS 1", ocr_provider=None)
        self.workspace2 = Workspace.objects.create(name="WS 2", ocr_provider=None)

    @patch("research_intelligence.tasks.step_1_search.search.execute_scraper_run_job.delay")
    def test_concurrent_agent_initialization(self, mock_delay):
        mock_delay.return_value = MagicMock(id="task_mock_123")

        Scraper.objects.create(workspace=self.workspace1, provider="arxiv", search_query="quantum", is_active=True)
        Scraper.objects.create(workspace=self.workspace2, provider="arxiv", search_query="optics", is_active=True)

        from research_intelligence.tasks.orchestrator.agent_engine import tick_agent_process

        agent1 = ResearchAgentProcess.objects.create(
            workspace=self.workspace1,
            name="Agent 1",
            status="initialized",
            current_step="initialized"
        )
        agent2 = ResearchAgentProcess.objects.create(
            workspace=self.workspace2,
            name="Agent 2",
            status="initialized",
            current_step="initialized"
        )

        res1 = tick_agent_process(str(agent1.id))
        res2 = tick_agent_process(str(agent2.id))

        self.assertTrue(res1["success"])
        self.assertTrue(res2["success"])

        agent1.refresh_from_db()
        agent2.refresh_from_db()

        self.assertEqual(agent1.status, "running")
        self.assertEqual(agent1.current_step, "search")
        self.assertEqual(agent2.status, "running")
        self.assertEqual(agent2.current_step, "search")

        # Each agent must have its own isolated PipelineRun
        self.assertNotEqual(agent1.pipeline_run_id, agent2.pipeline_run_id)
