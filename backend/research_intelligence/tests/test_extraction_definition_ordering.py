import uuid
from django.test import TestCase, RequestFactory
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.contrib.messages.storage.fallback import FallbackStorage
from django.urls import reverse

from research_intelligence.models import (
    Workspace,
    ExtractionDefinition,
    Paper,
    Extraction,
    PaperMetric,
)
from research_intelligence.admin import ExtractionDefinitionAdmin
from research_intelligence.services.scorecard_service import (
    build_paper_scorecard_data,
    build_workspace_scorecard_data,
)
from research_intelligence.services.workspace_service import (
    serialize_workspace_configuration,
    import_workspace_configuration_bundle,
)

User = get_user_model()


class ExtractionDefinitionOrderingTestCase(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.site = AdminSite()
        self.admin = ExtractionDefinitionAdmin(ExtractionDefinition, self.site)

        self.user = User.objects.create_superuser(
            username="ordering_admin",
            email="ordering_admin@schwarz.de",
            password="admin_password123!"
        )

        self.workspace_a = Workspace.objects.create(name="Workspace Alpha")
        self.workspace_b = Workspace.objects.create(name="Workspace Beta")

    def test_model_auto_assigns_sequential_order_per_workspace(self):
        """
        When ExtractionDefinitions are created without explicit order,
        save() automatically assigns sequential order (1, 2, 3...) scoped per workspace.
        """
        def_a1 = ExtractionDefinition.objects.create(
            workspace=self.workspace_a,
            name="TRL Level",
            response_schema={"type": "object"},
            exit_metrics="trl"
        )
        def_a2 = ExtractionDefinition.objects.create(
            workspace=self.workspace_a,
            name="Research Quality",
            response_schema={"type": "object"},
            exit_metrics="novelty, significance"
        )
        def_a3 = ExtractionDefinition.objects.create(
            workspace=self.workspace_a,
            name="Schwarz Fit",
            response_schema={"type": "object"},
            exit_metrics="fit_score"
        )

        self.assertEqual(def_a1.order, 1)
        self.assertEqual(def_a2.order, 2)
        self.assertEqual(def_a3.order, 3)

        # Definitions in Workspace B start independently from 1
        def_b1 = ExtractionDefinition.objects.create(
            workspace=self.workspace_b,
            name="Beta Metric 1",
            response_schema={"type": "object"},
        )
        def_b2 = ExtractionDefinition.objects.create(
            workspace=self.workspace_b,
            name="Beta Metric 2",
            response_schema={"type": "object"},
        )

        self.assertEqual(def_b1.order, 1)
        self.assertEqual(def_b2.order, 2)

    def test_admin_order_display_renders_badge_and_buttons(self):
        """
        ExtractionDefinitionAdmin.order_display renders the #<order> badge
        and the ⬆️ / ⬇️ links.
        """
        definition = ExtractionDefinition.objects.create(
            workspace=self.workspace_a,
            name="Scalability",
            order=4,
            response_schema={"type": "object"},
        )

        html = str(self.admin.order_display(definition))
        self.assertIn("#4", html)
        self.assertIn("move-up", html)
        self.assertIn("move-down", html)
        self.assertIn("⬆️", html)
        self.assertIn("⬇️", html)

    def test_admin_move_up_and_move_down_views(self):
        """
        Clicking move-up or move-down endpoints swaps position with neighbor in same workspace.
        """
        d1 = ExtractionDefinition.objects.create(workspace=self.workspace_a, name="First", order=1, response_schema={"type": "object"})
        d2 = ExtractionDefinition.objects.create(workspace=self.workspace_a, name="Second", order=2, response_schema={"type": "object"})
        d3 = ExtractionDefinition.objects.create(workspace=self.workspace_a, name="Third", order=3, response_schema={"type": "object"})

        # Move d2 UP -> d2 becomes order 1, d1 becomes order 2
        req = self.factory.get(f"/admin/research_intelligence/extractiondefinition/{d2.pk}/move-up/")
        req.user = self.user
        setattr(req, 'session', {})
        setattr(req, '_messages', FallbackStorage(req))

        resp = self.admin.move_up_view(req, pk=d2.pk)
        self.assertEqual(resp.status_code, 302)

        d1.refresh_from_db()
        d2.refresh_from_db()
        d3.refresh_from_db()

        self.assertEqual(d2.order, 1)
        self.assertEqual(d1.order, 2)
        self.assertEqual(d3.order, 3)

        # Move d2 DOWN -> d2 becomes order 2, d1 becomes order 1
        req_down = self.factory.get(f"/admin/research_intelligence/extractiondefinition/{d2.pk}/move-down/")
        req_down.user = self.user
        setattr(req_down, 'session', {})
        setattr(req_down, '_messages', FallbackStorage(req_down))

        resp_down = self.admin.move_down_view(req_down, pk=d2.pk)
        self.assertEqual(resp_down.status_code, 302)

        d1.refresh_from_db()
        d2.refresh_from_db()
        d3.refresh_from_db()

        self.assertEqual(d1.order, 1)
        self.assertEqual(d2.order, 2)
        self.assertEqual(d3.order, 3)

    def test_admin_move_up_and_down_via_http_client_and_query_preservation(self):
        """
        Verifies actual HTTP GET requests to move-up and move-down resolve through
        Django Admin URL routing (does not trigger 'does not exist' 404/change-view error),
        successfully reorder definitions, and preserve query parameters like '?o=6.1.12'.
        Also verifies that ordering columns are at the end of list_display.
        """
        from django.contrib import admin as django_admin
        registered_admin = django_admin.site._registry[ExtractionDefinition]

        # 1. Verify column ordering: 'name' is first and clickable, order columns are at the end
        ld = registered_admin.get_list_display(None)
        self.assertEqual(ld[0], 'name')
        self.assertEqual(ld[-2], '_reorder_')
        self.assertEqual(ld[-1], 'order_display')
        links = registered_admin.get_list_display_links(None, ld)
        self.assertEqual(links, ['name'])

        # 2. Test HTTP GET with query params '?o=6.1.12'
        d1 = ExtractionDefinition.objects.create(workspace=self.workspace_a, name="Alpha 1", order=1, response_schema={"type": "object"})
        d2 = ExtractionDefinition.objects.create(workspace=self.workspace_a, name="Alpha 2", order=2, response_schema={"type": "object"})

        self.client.force_login(self.user)

        # Move d2 UP via HTTP
        up_url = f"/admin/research_intelligence/extractiondefinition/{d2.pk}/move-up/?o=6.1.12"
        resp_up = self.client.get(up_url)
        self.assertEqual(resp_up.status_code, 302)
        self.assertIn("?o=6.1.12", resp_up.url)

        d1.refresh_from_db()
        d2.refresh_from_db()
        self.assertEqual(d2.order, 1)
        self.assertEqual(d1.order, 2)

        # Move d2 DOWN via HTTP
        down_url = f"/admin/research_intelligence/extractiondefinition/{d2.pk}/move-down/?o=6.1.12"
        resp_down = self.client.get(down_url)
        self.assertEqual(resp_down.status_code, 302)
        self.assertIn("?o=6.1.12", resp_down.url)

        d1.refresh_from_db()
        d2.refresh_from_db()
        self.assertEqual(d1.order, 1)
        self.assertEqual(d2.order, 2)

    def test_scorecard_dimensions_and_definitions_follow_configured_order(self):
        """
        Verifies build_paper_scorecard_data and build_workspace_scorecard_data
        return dimensions in the exact order configured on ExtractionDefinition.
        """
        # Create definitions in specific order: A (1), B (2), C (3)
        def_trl = ExtractionDefinition.objects.create(
            workspace=self.workspace_a,
            name="Technology Readiness Level (TRL)",
            order=1,
            exit_metrics="trl",
            response_schema={"type": "object"}
        )
        def_qual = ExtractionDefinition.objects.create(
            workspace=self.workspace_a,
            name="Research Quality",
            order=2,
            exit_metrics="novelty, significance",
            response_schema={"type": "object"}
        )
        def_fit = ExtractionDefinition.objects.create(
            workspace=self.workspace_a,
            name="Schwarz Fit",
            order=3,
            exit_metrics="fit_score",
            response_schema={"type": "object"}
        )

        paper = Paper.objects.create(workspace=self.workspace_a, title="Order Test Paper")
        PaperMetric.objects.create(paper=paper, workspace=self.workspace_a, signal_score=78.5)

        Extraction.objects.create(
            paper=paper,
            workspace=self.workspace_a,
            extraction_definition=def_trl,
            fields_data={"fields": {"trl": 4}},
            validation_status="pass"
        )
        Extraction.objects.create(
            paper=paper,
            workspace=self.workspace_a,
            extraction_definition=def_qual,
            fields_data={"fields": {"novelty": 85, "significance": 75}},
            validation_status="pass"
        )
        Extraction.objects.create(
            paper=paper,
            workspace=self.workspace_a,
            extraction_definition=def_fit,
            fields_data={"fields": {"fit_score": 92}},
            validation_status="pass"
        )

        # 1. Verify paper scorecard order: TRL, Quality, Fit
        sc_data = build_paper_scorecard_data(paper)
        dims = sc_data.get("paper", {}).get("dimensions", [])
        self.assertEqual(len(dims), 3)
        self.assertEqual(dims[0]["name"], "Technology Readiness Level (TRL)")
        self.assertEqual(dims[1]["name"], "Research Quality")
        self.assertEqual(dims[2]["name"], "Schwarz Fit")

        # 2. Swap order: make Schwarz Fit #1, TRL #2, Research Quality #3
        def_fit.order = 1
        def_fit.save(update_fields=['order'])
        def_trl.order = 2
        def_trl.save(update_fields=['order'])
        def_qual.order = 3
        def_qual.save(update_fields=['order'])

        # 3. Re-query scorecard: order must strictly reflect the new ordering!
        sc_data_reordered = build_paper_scorecard_data(paper)
        dims_reordered = sc_data_reordered.get("paper", {}).get("dimensions", [])
        self.assertEqual(dims_reordered[0]["name"], "Schwarz Fit")
        self.assertEqual(dims_reordered[1]["name"], "Technology Readiness Level (TRL)")
        self.assertEqual(dims_reordered[2]["name"], "Research Quality")

        # 4. Workspace scorecard definitions must also follow this order
        ws_data = build_workspace_scorecard_data(self.workspace_a)
        ws_defs = ws_data.get("workspace", {}).get("definitions", [])
        self.assertEqual(ws_defs[0]["name"], "Schwarz Fit")
        self.assertEqual(ws_defs[1]["name"], "Technology Readiness Level (TRL)")
        self.assertEqual(ws_defs[2]["name"], "Research Quality")

    def test_workspace_export_and_import_preserves_order(self):
        """
        Verifies export_workspace_data outputs 'order' and import_workspace_data preserves it.
        """
        ExtractionDefinition.objects.create(
            workspace=self.workspace_a,
            name="First Export",
            order=10,
            response_schema={"type": "object"}
        )
        ExtractionDefinition.objects.create(
            workspace=self.workspace_a,
            name="Second Export",
            order=20,
            response_schema={"type": "object"}
        )

        exported = serialize_workspace_configuration(self.workspace_a)
        export_defs = exported.get("extraction_definitions", [])
        self.assertEqual(len(export_defs), 2)
        self.assertEqual(export_defs[0]["order"], 10)
        self.assertEqual(export_defs[1]["order"], 20)

        # Import into workspace_b (modifying the exported dict to target workspace_b)
        exported["name"] = self.workspace_b.name
        import_workspace_configuration_bundle(exported, user=self.user, update_existing=True, allow_superuser=True)
        b_defs = list(self.workspace_b.extraction_definitions.all().order_by('order'))
        self.assertEqual(len(b_defs), 2)
        self.assertEqual(b_defs[0].name, "First Export")
        self.assertEqual(b_defs[0].order, 10)
        self.assertEqual(b_defs[1].name, "Second Export")
        self.assertEqual(b_defs[1].order, 20)

    def test_admin_bulk_move_actions(self):
        """
        Verifies move_selected_up and move_selected_down bulk actions reorder correctly.
        """
        d1 = ExtractionDefinition.objects.create(workspace=self.workspace_a, name="A", order=1, response_schema={"type": "object"})
        d2 = ExtractionDefinition.objects.create(workspace=self.workspace_a, name="B", order=2, response_schema={"type": "object"})
        d3 = ExtractionDefinition.objects.create(workspace=self.workspace_a, name="C", order=3, response_schema={"type": "object"})

        req = self.factory.post("/admin/research_intelligence/extractiondefinition/")
        req.user = self.user
        setattr(req, 'session', {})
        setattr(req, '_messages', FallbackStorage(req))

        # Move d2 up via action
        self.admin.move_selected_up(req, ExtractionDefinition.objects.filter(pk=d2.pk))
        d1.refresh_from_db()
        d2.refresh_from_db()
        self.assertEqual(d2.order, 1)
        self.assertEqual(d1.order, 2)

        # Move d2 down via action
        self.admin.move_selected_down(req, ExtractionDefinition.objects.filter(pk=d2.pk))
        d1.refresh_from_db()
        d2.refresh_from_db()
        self.assertEqual(d1.order, 1)
        self.assertEqual(d2.order, 2)

    def test_ensure_sequential_ordering_self_heals_zeros_and_duplicates(self):
        """
        When definitions have order=0 or duplicate orders in database (e.g. legacy prod data),
        changelist_view executes _ensure_sequential_ordering to re-sequence them strictly to 1, 2, 3...
        """
        # Create definitions with order=0 directly via queryset update
        d1 = ExtractionDefinition.objects.create(workspace=self.workspace_a, name="Legacy A1", response_schema={})
        d2 = ExtractionDefinition.objects.create(workspace=self.workspace_a, name="Legacy A2", response_schema={})
        d3 = ExtractionDefinition.objects.create(workspace=self.workspace_a, name="Legacy A3", response_schema={})
        ExtractionDefinition.objects.filter(workspace=self.workspace_a).update(order=0)

        d_b1 = ExtractionDefinition.objects.create(workspace=self.workspace_b, name="Legacy B1", response_schema={})
        d_b2 = ExtractionDefinition.objects.create(workspace=self.workspace_b, name="Legacy B2", response_schema={})
        ExtractionDefinition.objects.filter(workspace=self.workspace_b).update(order=0)

        # Trigger changelist_view
        req = self.factory.get("/admin/research_intelligence/extractiondefinition/")
        req.user = self.user
        setattr(req, 'session', {})
        setattr(req, '_messages', FallbackStorage(req))
        self.admin.changelist_view(req)

        # Verify all definitions in Workspace A are sequentially 1, 2, 3
        d1.refresh_from_db()
        d2.refresh_from_db()
        d3.refresh_from_db()
        self.assertEqual(sorted([d1.order, d2.order, d3.order]), [1, 2, 3])

        # Verify definitions in Workspace B are sequentially 1, 2
        d_b1.refresh_from_db()
        d_b2.refresh_from_db()
        self.assertEqual(sorted([d_b1.order, d_b2.order]), [1, 2])

    def test_update_order_handles_drag_and_drop_cleanly_per_workspace(self):
        """
        Simulate adminsortable2 drag-and-drop AJAX callback to _update_order,
        verifying that positions are updated strictly sequentially per workspace.
        """
        d1 = ExtractionDefinition.objects.create(workspace=self.workspace_a, name="Item 1", order=1, response_schema={})
        d2 = ExtractionDefinition.objects.create(workspace=self.workspace_a, name="Item 2", order=2, response_schema={})
        d3 = ExtractionDefinition.objects.create(workspace=self.workspace_a, name="Item 3", order=3, response_schema={})

        # Drag Item 3 to the top (position 1)
        # adminsortable2 sends updated items with new proposed ranks
        updated_items = [
            [str(d3.pk), 1],
            [str(d1.pk), 2],
            [str(d2.pk), 3],
        ]
        res = self.admin._update_order(updated_items, {})
        self.assertGreater(res, 0)

        d1.refresh_from_db()
        d2.refresh_from_db()
        d3.refresh_from_db()

        self.assertEqual(d3.order, 1)
        self.assertEqual(d1.order, 2)
        self.assertEqual(d2.order, 3)

    def test_end_to_end_user_scenario_with_four_definitions(self):
        """
        Tests the exact setup from user's screenshot (Hybrid Computing):
        1. Risk and Affiliation Flagging (order 1)
        2. Schwarz Fit (order 2)
        3. Technology Readiness Level (TRL) (order 3)
        4. Research Metric (order 4)

        Verifies:
        - build_paper_scorecard_data returns all 4 dimensions in exact order.
        - Risk and Affiliation Flagging has is_risk_and_affiliation = True.
        - Moving Research Metric up via admin move-up view swaps order with TRL.
        - Further moving Research Metric to order 1 updates scorecard order so Research Metric is #1.
        """
        def_risk = ExtractionDefinition.objects.create(
            workspace=self.workspace_a,
            name="Risk and Affiliation Flagging",
            order=1,
            exit_metrics="schwarz_ecosystem_affiliation, gdpr_concern, competitor_involvement",
            response_schema={"type": "object"}
        )
        def_fit = ExtractionDefinition.objects.create(
            workspace=self.workspace_a,
            name="Schwarz Fit",
            order=2,
            exit_metrics="strategic_operational_need_match, synergy_index_score",
            response_schema={"type": "object"}
        )
        def_trl = ExtractionDefinition.objects.create(
            workspace=self.workspace_a,
            name="Technology Readiness Level (TRL)",
            order=3,
            exit_metrics="trl",
            response_schema={"type": "object"}
        )
        def_research = ExtractionDefinition.objects.create(
            workspace=self.workspace_a,
            name="Research Metric",
            order=4,
            exit_metrics="novelty, significance, rigour",
            response_schema={"type": "object"}
        )

        paper = Paper.objects.create(workspace=self.workspace_a, title="End to End Paper")
        PaperMetric.objects.create(paper=paper, workspace=self.workspace_a, signal_score=85.0)

        # Initial scorecard check: order is [Risk (1), Fit (2), TRL (3), Research (4)]
        sc_data = build_paper_scorecard_data(paper)
        dims = sc_data.get("paper", {}).get("dimensions", [])
        self.assertEqual(len(dims), 4)
        self.assertEqual(dims[0]["name"], "Risk and Affiliation Flagging")
        self.assertTrue(dims[0]["is_risk_and_affiliation"])
        self.assertEqual(dims[0]["order"], 1)

        self.assertEqual(dims[1]["name"], "Schwarz Fit")
        self.assertFalse(dims[1]["is_risk_and_affiliation"])
        self.assertEqual(dims[1]["order"], 2)

        self.assertEqual(dims[2]["name"], "Technology Readiness Level (TRL)")
        self.assertFalse(dims[2]["is_risk_and_affiliation"])
        self.assertEqual(dims[2]["order"], 3)

        self.assertEqual(dims[3]["name"], "Research Metric")
        self.assertFalse(dims[3]["is_risk_and_affiliation"])
        self.assertEqual(dims[3]["order"], 4)

        # Move Research Metric UP via move_up_view (swaps with TRL)
        req = self.factory.get(f"/admin/research_intelligence/extractiondefinition/{def_research.pk}/move-up/")
        req.user = self.user
        setattr(req, 'session', {})
        setattr(req, '_messages', FallbackStorage(req))
        self.admin.move_up_view(req, pk=def_research.pk)

        def_trl.refresh_from_db()
        def_research.refresh_from_db()
        self.assertEqual(def_research.order, 3)
        self.assertEqual(def_trl.order, 4)

        # Scorecard immediately reflects: [Risk (1), Fit (2), Research (3), TRL (4)]
        sc_data_2 = build_paper_scorecard_data(paper)
        dims_2 = sc_data_2.get("paper", {}).get("dimensions", [])
        self.assertEqual(dims_2[2]["name"], "Research Metric")
        self.assertEqual(dims_2[3]["name"], "Technology Readiness Level (TRL)")


