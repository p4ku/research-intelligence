import json
from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from research_intelligence.models import (
    Workspace,
    WorkspaceMember,
    ExtractionDefinition,
    Scraper,
    Subscriber,
)

User = get_user_model()


class WorkspaceImportExportAndSubscribersAPITestCase(TestCase):
    def setUp(self):
        self.admin_user = User.objects.create_user(
            username="ws_admin",
            email="admin@example.com",
            password="password123"
        )
        self.researcher_user = User.objects.create_user(
            username="ws_researcher",
            email="researcher@example.com",
            password="password123"
        )
        self.other_user = User.objects.create_user(
            username="ws_other",
            email="other@example.com",
            password="password123"
        )

        self.workspace = Workspace.objects.create(
            name="Solid State Batteries Project",
            abstract_acceptance_criteria="Inclusion: Solid electrolytes",
            abstract_rejection_criteria="Exclusion: Pure liquid electrolytes",
            full_text_acceptance_criteria="Inclusion: Experimental capacity metrics",
            full_text_rejection_criteria="Exclusion: Theoretical non-validated models",
            signal_score_code="signal_score = capacity * 1.5",
            monthly_usd_limit=95.00,
            monthly_token_limit=8000000,
        )

        WorkspaceMember.objects.create(
            workspace=self.workspace,
            user=self.admin_user,
            role="admin"
        )
        WorkspaceMember.objects.create(
            workspace=self.workspace,
            user=self.researcher_user,
            role="researcher"
        )

        # Child models
        self.ext_def = ExtractionDefinition.objects.create(
            workspace=self.workspace,
            name="Battery Capacity",
            system_prompt="Extract capacity",
            user_prompt_template="Title: {title}",
            response_schema={"type": "object", "properties": {"capacity": {"type": "number"}}},
            exit_metrics="capacity",
            postprocessing_code="def postprocess(raw):\n    return float(raw.get('capacity', 0))\n",
            is_active=True,
        )
        self.scraper = Scraper.objects.create(
            workspace=self.workspace,
            provider="arxiv",
            search_query="solid state battery",
            limit=10,
            is_active=True,
        )
        self.subscriber = Subscriber.objects.create(
            workspace=self.workspace,
            email="digest@example.com",
            name="Digest Reader",
            subscription_type="result_report",
            is_active=True,
        )

        self.client = APIClient()

    def test_export_configuration_endpoint(self):
        """Test GET /api/workspaces/{id}/export-configuration/ returns complete serialized bundle."""
        self.client.force_authenticate(user=self.admin_user)
        res = self.client.get(f"/api/workspaces/{self.workspace.id}/export-configuration/")
        self.assertEqual(res.status_code, 200)
        data = res.json()

        self.assertEqual(data.get("version"), "1.0")
        self.assertEqual(data.get("workspaces_count"), 1)

        ws_data = data.get("workspace") or data.get("workspaces")[0]
        self.assertEqual(ws_data.get("name"), "Solid State Batteries Project")
        self.assertEqual(ws_data.get("abstract_acceptance_criteria"), "Inclusion: Solid electrolytes")
        self.assertEqual(ws_data.get("signal_score_code"), "signal_score = capacity * 1.5")

        # Definitions
        defs = ws_data.get("extraction_definitions", [])
        self.assertEqual(len(defs), 1)
        self.assertEqual(defs[0].get("name"), "Battery Capacity")
        self.assertEqual(defs[0].get("exit_metrics"), ["capacity"])
        self.assertIn("def postprocess", defs[0].get("postprocessing_code", ""))

        # Scrapers & Subscribers
        self.assertEqual(len(ws_data.get("scrapers", [])), 1)
        self.assertEqual(ws_data.get("scrapers")[0].get("provider"), "arxiv")
        self.assertEqual(len(ws_data.get("subscribers", [])), 1)
        self.assertEqual(ws_data.get("subscribers")[0].get("email"), "digest@example.com")

    def test_export_configuration_permissions(self):
        """Test non-members cannot export workspace configuration."""
        self.client.force_authenticate(user=self.other_user)
        res = self.client.get(f"/api/workspaces/{self.workspace.id}/export-configuration/")
        self.assertEqual(res.status_code, 404)

    def test_import_configuration_endpoint_create_and_update(self):
        """Test POST /api/workspaces/import-configuration/ creates new and updates existing."""
        self.client.force_authenticate(user=self.admin_user)

        # 1. Create cloned workspace via import
        bundle = {
            "version": "1.0",
            "workspaces": [
                {
                    "name": "Cloned Batteries Workspace",
                    "abstract_acceptance_criteria": "Inclusion: Electrolytes",
                    "abstract_rejection_criteria": "Exclusion: Liquids",
                    "screening_llm_model": "google/gemini-3.8-flash",
                    "extraction_definitions": [
                        {
                            "name": "Cloned Capacity",
                            "system_prompt": "Extract capacity",
                            "user_prompt_template": "Content: {content}",
                            "exit_metrics": ["capacity"],
                            "postprocessing_code": "def postprocess(raw):\n    return 42.0\n",
                        }
                    ],
                    "scrapers": [
                        {
                            "provider": "openalex",
                            "search_query": "battery electrolyte",
                            "limit": 5,
                        }
                    ],
                    "subscribers": [
                        {
                            "email": "lead@example.com",
                            "subscription_type": "all",
                        }
                    ]
                }
            ]
        }

        res_create = self.client.post("/api/workspaces/import-configuration/", bundle, format="json")
        self.assertEqual(res_create.status_code, 200)
        stats = res_create.json().get("stats", {})
        self.assertEqual(stats.get("created_workspaces"), 1)
        self.assertEqual(stats.get("created_extractions"), 1)
        self.assertEqual(stats.get("created_scrapers"), 1)
        self.assertEqual(stats.get("created_subscribers"), 1)

        cloned_ws = Workspace.objects.get(name="Cloned Batteries Workspace")
        self.assertEqual(cloned_ws.extraction_definitions.count(), 1)
        self.assertEqual(cloned_ws.scrapers.count(), 1)
        self.assertEqual(cloned_ws.subscribers.count(), 1)

        # 2. In-place update of existing workspace
        bundle["workspaces"][0]["abstract_acceptance_criteria"] = "Updated Criteria Marker"
        bundle["overwrite_existing"] = True

        res_update = self.client.post("/api/workspaces/import-configuration/", bundle, format="json")
        self.assertEqual(res_update.status_code, 200)
        update_stats = res_update.json().get("stats", {})
        self.assertEqual(update_stats.get("updated_workspaces"), 1)
        self.assertEqual(update_stats.get("created_workspaces"), 0)

        cloned_ws.refresh_from_db()
        self.assertEqual(cloned_ws.abstract_acceptance_criteria, "Updated Criteria Marker")

    def test_subscriber_viewset_crud_and_rbac(self):
        """Test SubscriberViewSet list, create, update, delete, and permission enforcement."""
        # 1. List subscribers as researcher
        self.client.force_authenticate(user=self.researcher_user)
        res_list = self.client.get(f"/api/subscribers/?workspace={self.workspace.id}")
        self.assertEqual(res_list.status_code, 200)
        data = res_list.json()
        results = data.get("results", data) if isinstance(data, dict) else data
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["email"], "digest@example.com")

        # 2. Researcher cannot create subscriber (403 Forbidden)
        res_create_denied = self.client.post("/api/subscribers/", {
            "workspace": str(self.workspace.id),
            "email": "denied@example.com",
            "subscription_type": "pipeline_errors",
        }, format="json")
        self.assertEqual(res_create_denied.status_code, 403)

        # 3. Admin creates subscriber
        self.client.force_authenticate(user=self.admin_user)
        res_create = self.client.post("/api/subscribers/", {
            "workspace": str(self.workspace.id),
            "email": "sentinel@example.com",
            "name": "Sentinel Operator",
            "subscription_type": "pipeline_errors",
        }, format="json")
        self.assertEqual(res_create.status_code, 201)
        new_sub_id = res_create.json()["id"]

        # 4. Admin updates subscriber
        res_patch = self.client.patch(f"/api/subscribers/{new_sub_id}/", {
            "subscription_type": "all",
            "name": "Updated Sentinel",
        }, format="json")
        self.assertEqual(res_patch.status_code, 200)
        self.assertEqual(res_patch.json()["subscription_type"], "all")
        self.assertEqual(res_patch.json()["name"], "Updated Sentinel")

        # 5. Non-member cannot access subscriber (404)
        self.client.force_authenticate(user=self.other_user)
        res_other = self.client.get(f"/api/subscribers/{new_sub_id}/")
        self.assertEqual(res_other.status_code, 404)

        # 6. Admin deletes subscriber
        self.client.force_authenticate(user=self.admin_user)
        res_del = self.client.delete(f"/api/subscribers/{new_sub_id}/")
        self.assertEqual(res_del.status_code, 204)
        self.assertFalse(Subscriber.objects.filter(id=new_sub_id).exists())
