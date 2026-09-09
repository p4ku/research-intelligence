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

