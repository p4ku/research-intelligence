import uuid
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from research_intelligence.models import Workspace, WorkspaceMember
from slr_review.models import SLRWorkspaceConfig, SLRProtocol, get_default_exclusion_reasons

User = get_user_model()


class Command(BaseCommand):
    help = "Initializes an SLR (Systematic Literature Review) workspace with policy config, protocols, and assigned reviewers."

    def add_arguments(self, parser):
        parser.add_argument(
            '--workspace',
            type=str,
            default='Lassa Fever Virus SLR',
            help='Name of the workspace to create or configure.'
        )
        parser.add_argument(
            '--arbiter',
            type=str,
            default='prof_nowak',
            help='Username of the Senior Arbiter (PI/Supervisor).'
        )
        parser.add_argument(
            '--reviewers',
            type=str,
            default='dr_kowalski,mgr_wisniewski',
            help='Comma-separated usernames of independent reviewers.'
        )
        parser.add_argument(
            '--quorum',
            type=int,
            default=2,
            help='Screening quorum size (default: 2 for dual review).'
        )
        parser.add_argument(
            '--sampling-pct',
            type=float,
            default=10.0,
            help='Sample percentage for human audit (default: 10.0).'
        )
        parser.add_argument(
            '--gate-mode',
            type=str,
            default='two_stage_split',
            choices=['two_stage_split', 'single_combined_post_fulltext', 'abstract_only_gate', 'autonomous_benchmark'],
            help='Checkpoint gate mode (default: two_stage_split).'
        )
        parser.add_argument(
            '--password',
            type=str,
            default='slr_demo_pass123',
            help='Default password for newly created test users.'
        )

    def handle(self, *args, **options):
        ws_name = options['workspace']
        arbiter_username = options['arbiter']
        reviewers_list = [r.strip() for r in options['reviewers'].split(',') if r.strip()]
        quorum = options['quorum']
        sampling_pct = options['sampling_pct']
        gate_mode = options['gate_mode']
        password = options['password']

        self.stdout.write(self.style.MIGRATE_HEADING(f"\n🚀 Initializing SLR Workspace: '{ws_name}'"))

        # 1. Create or get Workspace
        workspace, ws_created = Workspace.objects.get_or_create(
            name=ws_name,
            defaults={
                'search_query': 'Lassa fever OR Lassa virus OR Mastomys natalensis',
                'description': 'Systematic literature review on Lassa virus epidemiology, case fatality ratios, and transmission dynamics.'
            }
        )
        if ws_created:
            self.stdout.write(self.style.SUCCESS(f"  ✓ Created Workspace: {workspace.name} ({workspace.id})"))
        else:
            self.stdout.write(self.style.WARNING(f"  ℹ Using Existing Workspace: {workspace.name} ({workspace.id})"))

        # 2. Setup Senior Arbiter
        arbiter_user, arb_created = User.objects.get_or_create(
            username=arbiter_username,
            defaults={
                'email': f"{arbiter_username}@research-intelligence.local",
                'first_name': 'Senior',
                'last_name': 'Arbiter'
            }
        )
        if arb_created:
            arbiter_user.set_password(password)
            arbiter_user.save()
            self.stdout.write(self.style.SUCCESS(f"  ✓ Created Arbiter User: {arbiter_username} (password: {password})"))
        else:
            self.stdout.write(self.style.SUCCESS(f"  ℹ Existing Arbiter User: {arbiter_username}"))

        # Link Arbiter as WorkspaceMember with 'admin' role
        WorkspaceMember.objects.get_or_create(
            workspace=workspace,
            user=arbiter_user,
            defaults={'role': 'admin'}
        )

        # 3. Setup Independent Reviewers
        created_reviewers = []
        for r_name in reviewers_list:
            r_user, r_created = User.objects.get_or_create(
                username=r_name,
                defaults={
                    'email': f"{r_name}@research-intelligence.local",
                    'first_name': 'Reviewer',
                    'last_name': r_name
                }
            )
            if r_created:
                r_user.set_password(password)
                r_user.save()
                self.stdout.write(self.style.SUCCESS(f"  ✓ Created Reviewer User: {r_name} (password: {password})"))
            else:
                self.stdout.write(self.style.SUCCESS(f"  ℹ Existing Reviewer User: {r_name}"))

            WorkspaceMember.objects.get_or_create(
                workspace=workspace,
                user=r_user,
                defaults={'role': 'researcher'}
            )
            created_reviewers.append(r_user)

        # 4. Configure SLRWorkspaceConfig
        config, cfg_created = SLRWorkspaceConfig.objects.get_or_create(
            workspace=workspace,
            defaults={
                'checkpoint_gate_mode': gate_mode,
                'enable_extraction_gate': True,
                'screening_quorum_size': quorum,
                'extraction_quorum_size': 1,
                'require_blind_review': True,
                'sampling_mode': 'uncertainty_stratified',
                'abstract_sample_percentage': sampling_pct,
                'full_text_sample_percentage': sampling_pct * 2,
                'extraction_sample_percentage': sampling_pct,
                'negative_control_percentage': 5.0,
                'enable_rob_assessment': True,
                'rob_framework': 'auto_detect',
                'designated_arbiter': arbiter_user,
                'tie_breaker_strategy': 'arbiter_ruling',
                'exclusion_reasons': get_default_exclusion_reasons(),
                'require_evidence_on_exclusion': True,
            }
        )
        if not cfg_created:
            config.checkpoint_gate_mode = gate_mode
            config.screening_quorum_size = quorum
            config.designated_arbiter = arbiter_user
            config.save()
            self.stdout.write(self.style.SUCCESS(f"  ✓ Updated SLRWorkspaceConfig (Gate: {gate_mode}, Quorum: {quorum}, Arbiter: {arbiter_username})"))
        else:
            self.stdout.write(self.style.SUCCESS(f"  ✓ Created SLRWorkspaceConfig (Gate: {gate_mode}, Quorum: {quorum}, Arbiter: {arbiter_username})"))

        # 5. Create Baseline SLRProtocol
        protocol, proto_created = SLRProtocol.objects.get_or_create(
            workspace=workspace,
            title=f"{ws_name} Protocol",
            defaults={
                'review_question': 'What are the epidemiological reproduction numbers (R0) and case fatality ratios (CFR) of Lassa virus in endemic regions?',
                'pico_population': 'Human cases with laboratory-confirmed Lassa virus infection in West Africa.',
                'pico_intervention': 'Epidemiological observation, clinical treatment, or vaccination interventions.',
                'pico_comparison': 'Standard supportive care or baseline control cohorts.',
                'pico_outcome': 'Basic reproduction number (R0), Case Fatality Ratio (CFR), incubation period, serial interval.',
                'study_design_criteria': 'Prospective/retrospective clinical cohorts, RCTs, and epidemiological surveillance; exclude purely animal-only and in-vitro studies.',
                'is_locked': False,
                'version': 1,
                'created_by': arbiter_user
            }
        )
        if proto_created:
            self.stdout.write(self.style.SUCCESS(f"  ✓ Created SLRProtocol: '{protocol.title}' (PICO defined, PROSPERO ready)"))

        # 6. Summary Output
        self.stdout.write(self.style.MIGRATE_HEADING("\n📋 SLR Workspace Setup Summary:"))
        self.stdout.write(f"  • Workspace ID:      {workspace.id}")
        self.stdout.write(f"  • Workspace Name:    {workspace.name}")
        self.stdout.write(f"  • Checkpoint Gate:   {config.checkpoint_gate_mode}")
        self.stdout.write(f"  • Quorum Size:       {config.screening_quorum_size} independent reviewers")
        self.stdout.write(f"  • Senior Arbiter:    {arbiter_user.username} (admin)")
        self.stdout.write(f"  • Reviewers:         {', '.join([r.username for r in created_reviewers])} (researchers)")
        self.stdout.write(f"  • RoB Framework:     {config.rob_framework} (Cochrane RoB 2 / ROBINS-I)")
        self.stdout.write(f"  • Extraction Gate:   {'Enabled' if config.enable_extraction_gate else 'Disabled'}")
        self.stdout.write(f"  • Frontend URL:      http://localhost:3000/dashboard")
        self.stdout.write(f"  • Audit Queue URL:   http://localhost:3000/audit-queue\n")
        self.stdout.write(self.style.SUCCESS("🎉 Workspace is ready! Users can log in, launch an SLR briefing, and perform audits in the Review Workspace.\n"))
