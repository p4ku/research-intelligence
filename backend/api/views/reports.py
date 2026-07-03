from rest_framework import viewsets
from research_intelligence.models import NarrativeReport
from ..serializers.reports import NarrativeReportSerializer

class ReportViewSet(viewsets.ModelViewSet):
    """
    Weekly compiled narrative briefings.
    """
    queryset = NarrativeReport.objects.all()
    serializer_class = NarrativeReportSerializer
