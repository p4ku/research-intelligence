from rest_framework import serializers
from research_intelligence.models import NarrativeReport

class NarrativeReportSerializer(serializers.ModelSerializer):
    class Meta:
        model = NarrativeReport
        fields = '__all__'
