import uuid
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from research_intelligence.models import (
    Workspace,
    WorkspaceMember,
    Scraper,
    ExtractionDefinition,
    APIKey,
)


class Command(BaseCommand):
    help = "Seeds standard demo workspaces, scrapers, extraction definitions, and API keys."

    def add_arguments(self, parser):
        parser.add_argument(
            '--clean',
            action='store_true',
            help='Delete existing seeded demo workspaces before seeding.',
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("🌱 Seeding Schwarz Research Intelligence Demo Environment..."))

        # 1. Superuser admin setup
        admin_user, created = User.objects.get_or_create(
            username='admin',
            defaults={
                'email': 'admin@schwarz-intelligence.com',
                'is_staff': True,
                'is_superuser': True,
            }
        )
        if created:
            admin_user.set_password('schwarz123!')
            admin_user.save()
            self.stdout.write(self.style.SUCCESS("  ✅ Superuser 'admin' created (Password: schwarz123!)."))
        else:
            self.stdout.write(self.style.SUCCESS("  ℹ️ Superuser 'admin' already exists."))

        # 2. FastMCP API Key for admin
        api_key_obj, key_created = APIKey.objects.get_or_create(
            key_id='admin_mcp_key',
            defaults={
                'user': admin_user,
                'name': 'Primary Admin MCP Key',
                'is_active': True,
            }
        )
        if key_created:
            api_key_obj.set_secret('schwarz123!')
            api_key_obj.save()
            self.stdout.write(self.style.SUCCESS("  ✅ Admin API Key created (key_id: admin_mcp_key, secret: schwarz123!)."))

        # 3. Clean old demo workspaces if requested
        if options.get('clean'):
            Workspace.objects.filter(name__startswith="[Demo]").delete()
            self.stdout.write(self.style.WARNING("  🗑️ Cleaned existing [Demo] workspaces."))

        # 4. Create Demo Workspace: Neuromorphic Computing & AI Hardware
        ws, ws_created = Workspace.objects.get_or_create(
            name="[Demo] Neuromorphic Computing & AI Acceleration",
            defaults={
                "abstract_acceptance_criteria": "Focus on energy-efficient neuromorphic hardware, memristor arrays, spike-timing-dependent plasticity (STDP), and on-chip learning architectures.",
                "abstract_rejection_criteria": "Pure high-level software algorithms or theoretical surveys without hardware, circuit, or energy efficiency benchmarks.",
                "full_text_acceptance_criteria": "Presents quantitative silicon fabrication data, CMOS integration results, energy-per-synaptic-operation (pJ/fJ), or latency benchmarks.",
                "full_text_rejection_criteria": "Pure simulations without architectural validation, non-reproducible methodology, or non-peer-reviewed whitepapers.",
                "screening_llm_model": "google/gemini-3.8-flash",
                "ocr_provider": None,
                "monthly_token_limit": 20000000,
                "monthly_usd_limit": 250.00,
                "signal_score_code": (
                    "# AST-Sandboxed Python Signal Scoring Formula\n"
                    "base = 0.5 * fit_score + 0.3 * novelty_score + 0.2 * commercial_viability\n"
                    "multiplier = 1.25 if trl_level >= 5.0 else 1.0\n"
                    "score = base * multiplier\n"
                    "return round(min(100.0, max(0.0, score)), 2)\n"
                ),
            }
        )

        WorkspaceMember.objects.get_or_create(
            workspace=ws,
            user=admin_user,
            defaults={'role': 'admin'}
        )

        # 5. Scrapers for Demo Workspace
        Scraper.objects.get_or_create(
            workspace=ws,
            provider="arxiv",
            search_query='cat:cs.NE AND "neuromorphic" AND "memristor"',
            defaults={"limit": 30, "is_active": True, "sort_by": "relevance", "sort_order": "desc"}
        )
        Scraper.objects.get_or_create(
            workspace=ws,
            provider="openalex",
            search_query="neuromorphic computing spike neural network hardware",
            defaults={"limit": 20, "is_active": True, "sort_by": "relevance", "sort_order": "desc"}
        )

        # 6. Dynamic Extraction Definitions
        ExtractionDefinition.objects.get_or_create(
            workspace=ws,
            name="Schwarz Strategic Fit",
            defaults={
                "exit_metrics": "fit_score",
                "system_prompt": "Evaluate strategic fit for Schwarz Group retail logistics, edge inference, and supply chain automation.",
                "user_prompt_template": "Paper: {{paper_title}}\nAbstract: {{abstract}}\nFull Text: {{full_text}}\nEvaluate fit from 0 to 100.",
                "response_schema": {
                    "type": "object",
                    "properties": {
                        "fit_score": {"type": "number", "minimum": 0, "maximum": 100},
                        "key_advantage": {"type": "string"},
                        "evidence_quote": {"type": "string"}
                    },
                    "required": ["fit_score", "evidence_quote"]
                },
                "is_active": True
            }
        )

        ExtractionDefinition.objects.get_or_create(
            workspace=ws,
            name="TRL Assessment",
            defaults={
                "exit_metrics": "trl_level",
                "system_prompt": "Assess Technology Readiness Level from TRL 1 (basic principles) to TRL 9 (proven in operational environment).",
                "user_prompt_template": "Assess TRL for: {{paper_title}}\n{{full_text}}",
                "response_schema": {
                    "type": "object",
                    "properties": {
                        "trl_level": {"type": "number", "minimum": 1, "maximum": 9},
                        "prototype_status": {"type": "string"},
                        "evidence_quote": {"type": "string"}
                    },
                    "required": ["trl_level", "evidence_quote"]
                },
                "is_active": True
            }
        )

        ExtractionDefinition.objects.get_or_create(
            workspace=ws,
            name="Novelty Score",
            defaults={
                "exit_metrics": "novelty_score",
                "system_prompt": "Assess architectural novelty and algorithmic originality from 0.0 to 100.0.",
                "user_prompt_template": "Evaluate novelty for: {{paper_title}}\n{{full_text}}",
                "response_schema": {
                    "type": "object",
                    "properties": {
                        "novelty_score": {"type": "number", "minimum": 0, "maximum": 100},
                        "differentiating_factor": {"type": "string"},
                        "evidence_quote": {"type": "string"}
                    },
                    "required": ["novelty_score", "evidence_quote"]
                },
                "is_active": True
            }
        )

        self.stdout.write(self.style.SUCCESS(f"  ✅ Seeded Demo Workspace '{ws.name}' (ID: {ws.id}) with scrapers and extraction schemas."))
        self.stdout.write(self.style.SUCCESS("🎉 Seeding complete! You can now launch reviews via REST API, FastMCP, or Admin Dashboard."))
