from rest_framework import serializers
from research_intelligence.models import Workspace, Subscriber, ExtractionDefinition, Scraper

class SubscriberSerializer(serializers.ModelSerializer):
    class Meta:
        model = Subscriber
        fields = ['id', 'email', 'name', 'is_active', 'created_at']

class ScraperSerializer(serializers.ModelSerializer):
    class Meta:
        model = Scraper
        fields = ['id', 'workspace', 'provider', 'search_query', 'limit', 'sort_by', 'sort_order', 'is_active', 'created_at']

class ExtractionDefinitionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExtractionDefinition
        fields = [
            'id', 'name', 'system_prompt', 'user_prompt_template',
            'response_schema', 'llm_model', 'is_active', 'created_at'
        ]

class WorkspaceSerializer(serializers.ModelSerializer):
    subscribers = SubscriberSerializer(many=True, read_only=True)
    scrapers = ScraperSerializer(many=True, read_only=True)
    extraction_definitions = ExtractionDefinitionSerializer(many=True, read_only=True)
    user_role = serializers.SerializerMethodField()

    class Meta:
        model = Workspace
        fields = [
            'id', 'name', 'scrapers',
            'abstract_acceptance_criteria', 'abstract_rejection_criteria',
            'full_text_acceptance_criteria', 'full_text_rejection_criteria',
            'abstract_screening_system_prompt', 'abstract_screening_user_prompt_template',
            'abstract_screening_response_schema', 'abstract_screening_exit_metric',
            'full_text_screening_system_prompt', 'full_text_screening_user_prompt_template',
            'full_text_screening_response_schema', 'full_text_screening_exit_metric',
            'signal_score_code', 'skip_abstract_screening', 'notification_email',
            'extraction_definitions', 'ocr_provider',
            'screening_llm_model', 'llm_provider', 'digest_schedule',
            'monthly_token_limit',
            'tokens_in_consumed_this_month', 'tokens_out_consumed_this_month', 'tokens_consumed_this_month',
            'monthly_usd_limit', 'usd_spent_this_month', 'subscribers',
            'user_role',
            'created_at'
        ]

    def get_user_role(self, obj):
        request = self.context.get('request')
        if not request or not getattr(request, 'user', None) or not request.user.is_authenticated:
            return None
        if getattr(request.user, 'is_superuser', False):
            return 'admin'
        from research_intelligence.models import WorkspaceMember
        member = WorkspaceMember.objects.filter(workspace=obj, user=request.user).first()
        return member.role if member else None

