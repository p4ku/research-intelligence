from rest_framework import serializers


class StarUpdateSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=['paper', 'briefing'], help_text="What is being starred: a paper or a briefing (pipeline run)")
    id = serializers.UUIDField(help_text="Paper UUID or PipelineRun UUID")
    starred = serializers.BooleanField(help_text="True to star, False to unstar")


class StarsSerializer(serializers.Serializer):
    papers = serializers.ListField(child=serializers.UUIDField(), help_text="Starred Paper UUIDs, oldest star first")
    briefings = serializers.ListField(child=serializers.UUIDField(), help_text="Starred PipelineRun UUIDs, oldest star first")
