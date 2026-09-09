from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from research_intelligence.models import Workspace, Subscriber, ExtractionDefinition, Scraper

class SubscriberSerializer(serializers.ModelSerializer):
    class Meta:
        model = Subscriber
        fields = ['id', 'workspace', 'email', 'name', 'subscription_type', 'is_active', 'created_at']

class ScraperSerializer(serializers.ModelSerializer):
    class Meta:
        model = Scraper
        fields = ['id', 'workspace', 'provider', 'search_query', 'limit', 'sort_by', 'sort_order', 'n_last_days', 'is_active', 'created_at']

class ExtractionDefinitionSerializer(serializers.ModelSerializer):
    exit_metrics = serializers.ListField(
        child=serializers.CharField(max_length=100),
        required=False,
        allow_empty=True,
        help_text="Ordered list of exit parameter keys to expose for Signal Score."
    )
    primary_frontend_metric = serializers.CharField(
        max_length=255,
        required=False,
        allow_null=True,
        allow_blank=True,
        help_text="Explicit field key for the primary metric shown on the frontend (e.g. 'fit_score' or 'trl_level')."
    )
    secondary_frontend_metrics = serializers.ListField(
        child=serializers.CharField(max_length=100),
        required=False,
        allow_empty=True,
        help_text="Explicit list of field keys for secondary metrics/facets displayed on the frontend (e.g. ['novelty', 'significance'])."
    )
    has_postprocessing_code = serializers.BooleanField(read_only=True)

    class Meta:
        model = ExtractionDefinition
        fields = [
            'id', 'workspace', 'name', 'system_prompt', 'user_prompt_template',
            'response_schema', 'exit_metrics', 'primary_frontend_metric', 'secondary_frontend_metrics',
            'postprocessing_code', 'has_postprocessing_code', 'llm_model', 'version',
            'requires_consensus', 'is_active', 'created_at'
        ]

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        ret['exit_metrics'] = instance.get_exit_metrics_list()
        ret['primary_frontend_metric'] = instance.primary_frontend_metric or None
        ret['secondary_frontend_metrics'] = instance.get_secondary_frontend_metrics_list()
        ret['has_postprocessing_code'] = bool(instance.postprocessing_code)
        if ret.get('postprocessing_code') is None:
            ret['postprocessing_code'] = ""
        return ret

    def validate(self, attrs):
        if 'exit_metric' in self.initial_data:
            raise serializers.ValidationError({
                "exit_metrics": "Field 'exit_metric' is discontinued. Use 'exit_metrics' (list of metric keys) instead."
            })

        raw_exit_metrics = attrs.get('exit_metrics')
        if raw_exit_metrics is None and 'exit_metrics' in self.initial_data:
            raw_exit_metrics = self.initial_data.get('exit_metrics')

        if raw_exit_metrics is not None:
            if isinstance(raw_exit_metrics, (list, tuple)):
                attrs['exit_metrics'] = ", ".join(str(m).strip() for m in raw_exit_metrics if str(m).strip())
            elif isinstance(raw_exit_metrics, str):
                parts = [part.strip() for part in raw_exit_metrics.split(',') if part.strip()]
                attrs['exit_metrics'] = ", ".join(parts) if parts else ""

        # Handle primary_frontend_metric and plural alias primary_frontend_metrics
        raw_prim = attrs.get('primary_frontend_metric')
        if raw_prim is None and 'primary_frontend_metric' in self.initial_data:
            raw_prim = self.initial_data.get('primary_frontend_metric')
        if raw_prim is None and 'primary_frontend_metrics' in self.initial_data:
            raw_prim = self.initial_data.get('primary_frontend_metrics')
        if raw_prim is not None:
            if isinstance(raw_prim, (list, tuple)):
                attrs['primary_frontend_metric'] = str(raw_prim[0]).strip() if raw_prim else None
            elif isinstance(raw_prim, str):
                attrs['primary_frontend_metric'] = raw_prim.strip() or None
            else:
                attrs['primary_frontend_metric'] = str(raw_prim).strip() or None

        # Handle secondary_frontend_metrics
        raw_sec = attrs.get('secondary_frontend_metrics')
        if raw_sec is None and 'secondary_frontend_metrics' in self.initial_data:
            raw_sec = self.initial_data.get('secondary_frontend_metrics')
        if raw_sec is not None:
            if isinstance(raw_sec, (list, tuple)):
                attrs['secondary_frontend_metrics'] = ", ".join(str(m).strip() for m in raw_sec if str(m).strip())
            elif isinstance(raw_sec, str):
                parts = [part.strip() for part in raw_sec.split(',') if part.strip()]
                attrs['secondary_frontend_metrics'] = ", ".join(parts) if parts else ""

        # Validate postprocessing_code syntax
        code = attrs.get('postprocessing_code')
        if code and code.strip():
            import ast
            try:
                ast.parse(code.strip())
            except SyntaxError as e:
                raise serializers.ValidationError({"postprocessing_code": f"Invalid Python syntax: {e.msg} (line {e.lineno})"})

        # Validate duplicate exit metrics within workspace
        workspace = attrs.get('workspace') or (self.instance.workspace if self.instance else None)
        exit_m = attrs.get('exit_metrics', self.instance.exit_metrics if self.instance else None)
        if workspace and exit_m:
            dummy = ExtractionDefinition(
                workspace=workspace,
                name=attrs.get('name', self.instance.name if self.instance else ""),
                exit_metrics=exit_m,
                id=self.instance.id if self.instance else None
            )
            from django.core.exceptions import ValidationError
            try:
                dummy.clean()
            except ValidationError as val_err:
                raise serializers.ValidationError(val_err.message_dict if hasattr(val_err, 'message_dict') else str(val_err))

        return attrs

class WorkspaceSerializer(serializers.ModelSerializer):
    subscribers = SubscriberSerializer(many=True, read_only=True)
    scrapers = ScraperSerializer(many=True, read_only=True)
    extraction_definitions = ExtractionDefinitionSerializer(many=True, read_only=True)
    user_role = serializers.SerializerMethodField()
    digest_schedule = serializers.SerializerMethodField()

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
            'narrative_report_prompt', 'narrative_report_system_prompt', 'narrative_report_top_n_papers',
            'signal_score_code', 'skip_abstract_screening', 'reprocess_existing',
            'extraction_definitions', 'ocr_provider',
            'screening_llm_model', 'llm_provider', 'reasoning_effort', 'digest_schedule',
            'monthly_token_limit',
            'tokens_in_consumed_this_month', 'tokens_out_consumed_this_month', 'tokens_consumed_this_month',
            'monthly_usd_limit', 'usd_spent_this_month', 'subscribers',
            'user_role',
            'created_at'
        ]
        read_only_fields = [
            'id', 'tokens_in_consumed_this_month', 'tokens_out_consumed_this_month',
            'tokens_consumed_this_month', 'usd_spent_this_month', 'created_at', 'digest_schedule'
        ]

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_digest_schedule(self, obj):
        return None

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_user_role(self, obj):
        request = self.context.get('request')
        if not request or not getattr(request, 'user', None) or not request.user.is_authenticated:
            return None
        if not hasattr(self, '_user_roles_cache'):
            req_roles = getattr(request, '_user_ws_roles', None)
            if req_roles is not None:
                self._user_roles_cache = req_roles
            else:
                from research_intelligence.models import WorkspaceMember
                self._user_roles_cache = dict(
                    WorkspaceMember.objects.filter(user=request.user).values_list('workspace_id', 'role')
                )
        return self._user_roles_cache.get(obj.id)

    def create(self, validated_data):
        extraction_defs_data = self.initial_data.get('extraction_definitions', [])
        scrapers_data = self.initial_data.get('scrapers', [])
        subscribers_data = self.initial_data.get('subscribers', [])

        workspace = super().create(validated_data)

        # Create nested extraction definitions if passed in payload
        if isinstance(extraction_defs_data, list):
            for ed in extraction_defs_data:
                if isinstance(ed, dict) and ed.get('name'):
                    if 'exit_metric' in ed:
                        raise serializers.ValidationError({
                            "extraction_definitions": "Field 'exit_metric' is discontinued. Use 'exit_metrics' (list of metric keys) instead."
                        })
                    exit_m = ed.get('exit_metrics')
                    if isinstance(exit_m, list):
                        exit_m = ", ".join(str(m).strip() for m in exit_m if str(m).strip())
                    elif exit_m:
                        exit_m = str(exit_m)

                    prim_f = ed.get('primary_frontend_metric')
                    if prim_f is None and 'primary_frontend_metrics' in ed:
                        prim_f = ed.get('primary_frontend_metrics')
                    if isinstance(prim_f, (list, tuple)):
                        prim_f = str(prim_f[0]).strip() if prim_f else None
                    elif prim_f:
                        prim_f = str(prim_f).strip() or None

                    sec_f = ed.get('secondary_frontend_metrics')
                    if isinstance(sec_f, (list, tuple)):
                        sec_f = ", ".join(str(m).strip() for m in sec_f if str(m).strip())
                    elif sec_f:
                        sec_f = str(sec_f).strip() or ""

                    ExtractionDefinition.objects.create(
                        workspace=workspace,
                        name=ed.get('name'),
                        system_prompt=ed.get('system_prompt', ''),
                        user_prompt_template=ed.get('user_prompt_template', ''),
                        response_schema=ed.get('response_schema', {}),
                        exit_metrics=exit_m,
                        primary_frontend_metric=prim_f,
                        secondary_frontend_metrics=sec_f,
                        postprocessing_code=ed.get('postprocessing_code'),
                        llm_model=ed.get('llm_model', workspace.screening_llm_model),
                        version=ed.get('version', 1),
                        requires_consensus=bool(ed.get('requires_consensus', False)),
                        is_active=bool(ed.get('is_active', True)),
                    )

        # Create nested scrapers if passed in payload
        if isinstance(scrapers_data, list):
            for sc in scrapers_data:
                if isinstance(sc, dict) and sc.get('provider') and sc.get('search_query'):
                    n_days = sc.get('n_last_days')
                    Scraper.objects.create(
                        workspace=workspace,
                        provider=sc.get('provider'),
                        search_query=sc.get('search_query'),
                        limit=sc.get('limit', 50),
                        sort_by=sc.get('sort_by', 'relevance'),
                        sort_order=sc.get('sort_order', 'desc'),
                        n_last_days=n_days if n_days is not None else 7,
                        is_active=bool(sc.get('is_active', True)),
                    )

        # Create nested subscribers if passed in payload
        if isinstance(subscribers_data, list):
            for sub in subscribers_data:
                if isinstance(sub, dict) and sub.get('email'):
                    Subscriber.objects.create(
                        workspace=workspace,
                        email=sub.get('email'),
                        name=sub.get('name', ''),
                        subscription_type=sub.get('subscription_type', 'result_report'),
                        is_active=bool(sub.get('is_active', True)),
                    )

        return workspace

