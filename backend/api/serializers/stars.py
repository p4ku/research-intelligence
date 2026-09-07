from rest_framework import serializers
from research_intelligence.models import Paper, PipelineRun, Star


# API kind -> (target model, Star FK field, stored kind, label for messages)
STAR_TARGETS = {
    'paper': (Paper, 'paper', Star.KIND_PAPER, 'Paper'),
    'briefing': (PipelineRun, 'pipeline_run', Star.KIND_PIPELINE_RUN, 'Briefing'),
}


class StarUpdateSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=list(STAR_TARGETS), help_text="What is being starred: a paper or a briefing (pipeline run)")
    id = serializers.UUIDField(help_text="Paper UUID or PipelineRun UUID")
    starred = serializers.BooleanField(help_text="True to star, False to unstar")


class StarsSerializer(serializers.Serializer):
    papers = serializers.ListField(child=serializers.UUIDField(), help_text="Starred Paper UUIDs, oldest star first")
    briefings = serializers.ListField(child=serializers.UUIDField(), help_text="Starred PipelineRun UUIDs, oldest star first")
