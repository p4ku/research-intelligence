from rest_framework import viewsets, serializers
from research_intelligence.models import Extraction

class ExtractionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Extraction
        fields = '__all__'

class ExtractionViewSet(viewsets.ModelViewSet):
    """
    Lists extracted claims and parameters matching schema settings.
    """
    queryset = Extraction.objects.all()
    serializer_class = ExtractionSerializer
