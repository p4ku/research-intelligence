from rest_framework import viewsets
from research_intelligence.models import Paper
from ..serializers.papers import PaperSerializer

class PaperViewSet(viewsets.ModelViewSet):
    """
    Explore papers ingested in weekly batch runs.
    """
    queryset = Paper.objects.all()
    serializer_class = PaperSerializer
