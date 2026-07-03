from rest_framework import serializers
from research_intelligence.models import Paper, PaperMetric

class PaperMetricSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaperMetric
        fields = '__all__'

class PaperSerializer(serializers.ModelSerializer):
    metrics = PaperMetricSerializer(many=True, read_only=True)

    class Meta:
        model = Paper
        fields = [
            'id', 'workspace', 'pipeline_run', 'hash_id', 'doi', 'arxiv_id',
            'title', 'authors', 'abstract', 'source_database',
            'original_pdf_path', 'converted_md_path', 'screening_status',
            'screening_reasoning', 'is_evaluation_benchmark',
            'evaluation_label', 'metrics', 'created_at'
        ]
