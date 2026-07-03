from rest_framework import viewsets, serializers
from research_intelligence.models import HITLCorrection

class HITLCorrectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = HITLCorrection
        fields = '__all__'

class HITLViewSet(viewsets.ModelViewSet):
    """
    Scientists validation overrides (verify, modify, reject).
    """
    queryset = HITLCorrection.objects.all()
    serializer_class = HITLCorrectionSerializer
