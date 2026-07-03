from rest_framework import serializers
from research_intelligence.models import Workspace, Subscriber, ExtractionDefinition, Scraper

class SubscriberSerializer(serializers.ModelSerializer):
    class Meta:
        model = Subscriber
        fields = ['id', 'email', 'name', 'is_active', 'created_at']

class ScraperSerializer(serializers.ModelSerializer):
    class Meta:
        model = Scraper
        fields = ['id', 'provider', 'search_query', 'is_active', 'created_at']

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

    class Meta:
        model = Workspace
        fields = [
            'id', 'name', 'scrapers', 'acceptance_criteria',
            'rejection_criteria', 'extraction_definitions', 'ocr_provider',
            'screening_llm_model', 'llm_provider', 'digest_schedule',
            'monthly_token_limit', 'tokens_consumed_this_month',
            'monthly_usd_limit', 'usd_spent_this_month', 'subscribers',
            'created_at'
        ]
