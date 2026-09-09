import uuid
import logging
from django.db import models
from django.core.exceptions import ValidationError

logger = logging.getLogger(__name__)


class ExtractionDefinition(models.Model):
    """
    Defines a dynamic extraction target (e.g. 'ML Methods') with its own prompts and schema.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey('Workspace', on_delete=models.CASCADE, related_name="extraction_definitions")
    name = models.CharField(max_length=255, help_text="e.g. 'ML Methods', 'Business Models'")
    system_prompt = models.TextField(help_text="System instructions enforcing extraction perspective")
    user_prompt_template = models.TextField(help_text="User prompt with placeholders like {paper_text}")
    response_schema = models.JSONField(help_text="JSON schema describing fields to extract")
    exit_metrics = models.CharField(
        max_length=512,
        blank=True,
        null=True,
        help_text="Comma-separated field keys to unpack from extracted data for Signal Score (e.g. 'rigour_score, param1, param2'). The first metric is used for postprocessing naming."
    )
    primary_frontend_metric = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="Explicit field key for the primary metric shown on the frontend (e.g. 'fit_score' or 'trl_level')."
    )
    secondary_frontend_metrics = models.CharField(
        max_length=512,
        blank=True,
        null=True,
        help_text="Comma-separated field keys for secondary metrics/facets displayed on the frontend (e.g. 'novelty, significance')."
    )
    postprocessing_code = models.TextField(
        blank=True,
        null=True,
        help_text="Custom Python snippet to postprocess extracted fields and compute an additional parameter accessible in Signal Score."
    )
    llm_model = models.CharField(max_length=100, default="google/gemini-3.8-flash", help_text="LLM model used for this specific extraction")
    version = models.IntegerField(default=1, help_text="Tracks prompt/schema evolution")
    requires_consensus = models.BooleanField(default=False, help_text="Requires multi-sample self-consistency for difficult fields")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        app_label = 'research_intelligence'

    def __init__(self, *args, **kwargs):
        if 'exit_metrics' in kwargs:
            val = kwargs['exit_metrics']
            if isinstance(val, (list, tuple)):
                kwargs['exit_metrics'] = ", ".join(str(m).strip() for m in val if m and str(m).strip())
            elif val is None:
                kwargs['exit_metrics'] = ""

        # Handle primary_frontend_metric and plural alias primary_frontend_metrics
        if 'primary_frontend_metrics' in kwargs:
            alias_val = kwargs.pop('primary_frontend_metrics')
            if 'primary_frontend_metric' not in kwargs:
                kwargs['primary_frontend_metric'] = alias_val

        prim_val = kwargs.get('primary_frontend_metric')
        if prim_val is not None:
            if isinstance(prim_val, (list, tuple)):
                kwargs['primary_frontend_metric'] = str(prim_val[0]).strip() if prim_val else ""
            else:
                kwargs['primary_frontend_metric'] = str(prim_val).strip()

        # Handle secondary_frontend_metrics
        sec_val = kwargs.get('secondary_frontend_metrics')
        if sec_val is not None:
            if isinstance(sec_val, (list, tuple)):
                kwargs['secondary_frontend_metrics'] = ", ".join(str(m).strip() for m in sec_val if m and str(m).strip())
            else:
                kwargs['secondary_frontend_metrics'] = str(sec_val).strip()

        super().__init__(*args, **kwargs)

    def get_exit_metrics_list(self) -> list[str]:
        """Returns ordered, unique list of sanitized exit metric keys without spaces."""
        if not self.exit_metrics:
            return []
        from ..tasks.step_6_signal_score.scorer import _sanitize_identifier
        if isinstance(self.exit_metrics, (list, tuple)):
            raw_items = [str(part).strip() for part in self.exit_metrics if str(part).strip()]
        else:
            raw_items = [part.strip() for part in str(self.exit_metrics).split(',') if part.strip()]
        seen = set()
        res = []
        for item in raw_items:
            clean_item = _sanitize_identifier(item)
            if clean_item and clean_item not in seen:
                seen.add(clean_item)
                res.append(clean_item)
        return res

    def has_explicit_frontend_metrics(self) -> bool:
        """
        Returns True if either primary_frontend_metric or secondary_frontend_metrics
        is explicitly configured on this extraction definition.
        """
        has_prim = bool(self.primary_frontend_metric and self.primary_frontend_metric.strip())
        has_sec = False
        if self.secondary_frontend_metrics:
            if isinstance(self.secondary_frontend_metrics, (list, tuple)):
                has_sec = any(str(x).strip() for x in self.secondary_frontend_metrics)
            else:
                has_sec = any(x.strip() for x in str(self.secondary_frontend_metrics).split(','))
        return has_prim or has_sec

    def get_primary_exit_metric(self) -> str:
        """Returns the first exit metric from the list, used for primary exit metric lookups and _postprocessed suffix."""
        metrics = self.get_exit_metrics_list()
        return metrics[0] if metrics else ""

    def get_primary_frontend_metric(self) -> str | None:
        """
        Returns explicit primary frontend metric key if configured.
        If explicit frontend metrics are configured but primary is blank, returns None.
        If no explicit frontend metrics are configured, falls back to primary exit metric.
        """
        if self.primary_frontend_metric and self.primary_frontend_metric.strip():
            from ..tasks.step_6_signal_score.scorer import _sanitize_identifier
            clean_prim = _sanitize_identifier(self.primary_frontend_metric.strip())
            return clean_prim if clean_prim else None
        if self.has_explicit_frontend_metrics():
            return None
        prim = self.get_primary_exit_metric()
        return prim if prim else None

    def get_secondary_frontend_metrics_list(self) -> list[str]:
        """
        Returns ordered list of explicit secondary frontend metric keys if configured.
        If explicit frontend metrics are configured but secondary is blank, returns [].
        If no explicit frontend metrics are configured, falls back to exit metrics after primary.
        """
        if self.secondary_frontend_metrics:
            from ..tasks.step_6_signal_score.scorer import _sanitize_identifier
            if isinstance(self.secondary_frontend_metrics, (list, tuple)):
                raw_items = [str(x).strip() for x in self.secondary_frontend_metrics if str(x).strip()]
            else:
                raw_items = [x.strip() for x in str(self.secondary_frontend_metrics).split(',') if x.strip()]
            seen = set()
            res = []
            for item in raw_items:
                clean_item = _sanitize_identifier(item)
                if clean_item and clean_item not in seen:
                    seen.add(clean_item)
                    res.append(clean_item)
            return res
        if self.has_explicit_frontend_metrics():
            return []
        # Fallback for definitions without explicit secondary frontend metrics:
        exit_list = self.get_exit_metrics_list()
        prim = self.get_primary_frontend_metric()
        return [m for m in exit_list if m != prim]

    def get_available_postprocessing_variables(self) -> list[dict]:
        """
        Deduces all accessible sandbox variables for this ExtractionDefinition's postprocessing_code:
          1. Schema Properties defined in response_schema['properties']
          2. Exit Metrics configured in exit_metrics
          3. Paper Metadata Context (title, abstract, arxiv_id, doi)
          4. Extracted Fields Dictionaries (fields, data, extractions, fields_data, json_data, raw_data)
        """
        from ..tasks.step_6_signal_score.scorer import _sanitize_identifier

        variables = []
        seen = set()

        def _add(name: str, category: str, source: str, var_type: str = "numeric (float)", description: str = "", default_val=0.0):
            clean = _sanitize_identifier(name)
            if not clean or clean in seen:
                return
            seen.add(clean)
            variables.append({
                "name": clean,
                "variable_name": clean,
                "original_name": name,
                "category": category,
                "source": source,
                "type": var_type,
                "description": description,
                "default": default_val
            })

        # 1. Schema Properties (from response_schema)
        if self.response_schema and isinstance(self.response_schema, dict):
            props = self.response_schema.get("properties", {})
            if isinstance(props, dict):
                for prop_k, prop_spec in props.items():
                    if not isinstance(prop_spec, dict):
                        p_type = "any"
                        p_desc = ""
                    else:
                        p_type = prop_spec.get("type", "any")
                        p_desc = prop_spec.get("description", "")

                    if p_type in ("number", "float"):
                        def_val = 8.5
                        friendly_type = "numeric (float)"
                    elif p_type in ("integer", "int"):
                        def_val = 3
                        friendly_type = "integer"
                    elif p_type in ("boolean", "bool"):
                        def_val = True
                        friendly_type = "boolean"
                    elif p_type in ("array", "list"):
                        def_val = ["sample_1", "sample_2"]
                        friendly_type = "array (list)"
                    elif p_type in ("object", "dict"):
                        def_val = {"key": "sample_value"}
                        friendly_type = "object (dict)"
                    elif p_type in ("string", "str"):
                        def_val = f"sample_{prop_k}"
                        friendly_type = "string"
                    else:
                        def_val = 5.0
                        friendly_type = str(p_type)

                    desc = f"Extracted parameter '{prop_k}'"
                    if p_desc:
                        desc += f": {p_desc}"

                    _add(
                        prop_k,
                        "Schema Property",
                        f"📋 Schema Property of '{self.name or 'Extraction'}'",
                        friendly_type,
                        desc,
                        def_val
                    )

        # 2. Exit Metrics configured for this extraction definition
        for exit_m in self.get_exit_metrics_list():
            _add(
                exit_m,
                "Exit Metric",
                f"⚡ Exit Metric of '{self.name or 'Extraction'}'",
                "numeric (float)",
                f"Unpacked exit metric '{exit_m}'",
                7.5
            )

        # 3. Paper Metadata Context
        _add(
            "title",
            "Paper Metadata Context",
            "📄 Paper Metadata Context",
            "string",
            "Title of the paper being evaluated",
            "Deep Learning for Scientific Discovery"
        )
        _add(
            "abstract",
            "Paper Metadata Context",
            "📄 Paper Metadata Context",
            "string",
            "Abstract text of the paper",
            "We present a novel neural architecture..."
        )
        _add(
            "arxiv_id",
            "Paper Metadata Context",
            "📄 Paper Metadata Context",
            "string",
            "arXiv identifier of the paper (e.g. 2401.01234)",
            "2401.01234"
        )
        _add(
            "doi",
            "Paper Metadata Context",
            "📄 Paper Metadata Context",
            "string",
            "Digital Object Identifier (DOI) of the paper",
            "10.1016/j.jbi.2024.104200"
        )

        # 4. Extracted Fields Dictionaries
        mock_dict = {}
        for v in variables:
            if v["category"] in ("Schema Property", "Exit Metric"):
                mock_dict[v["name"]] = v["default"]
        if not mock_dict:
            mock_dict = {"score": 8.5, "confidence": 0.92}

        _add(
            "fields",
            "Extracted Fields Dictionary",
            "📦 Global Extraction Scope",
            "dict",
            "Direct dictionary containing all raw extracted fields: fields['property']",
            mock_dict
        )
        _add(
            "data",
            "Extracted Fields Dictionary",
            "📦 Global Extraction Scope",
            "dict",
            "Alias dictionary of all raw extracted fields: data['property']",
            mock_dict
        )
        _add(
            "extractions",
            "Extracted Fields Dictionary",
            "📦 Global Extraction Scope",
            "dict",
            "Alias dictionary for extracted parameters: extractions['property']",
            mock_dict
        )
        _add(
            "fields_data",
            "Extracted Fields Dictionary",
            "📦 Global Extraction Scope",
            "dict",
            "Raw extraction fields payload dictionary",
            mock_dict
        )
        _add(
            "json_data",
            "Extracted Fields Dictionary",
            "📦 Global Extraction Scope",
            "dict",
            "Alias for parsed extraction JSON data dictionary",
            mock_dict
        )
        _add(
            "raw_data",
            "Extracted Fields Dictionary",
            "📦 Global Extraction Scope",
            "dict",
            "Raw extracted parameters dictionary",
            mock_dict
        )

        return variables

    def clean(self):
        super().clean()
        if self.exit_metrics and isinstance(self.exit_metrics, (list, tuple)):
            self.exit_metrics = ", ".join(str(m).strip() for m in self.exit_metrics if m and str(m).strip())
        if self.exit_metrics and str(self.exit_metrics).strip() and self.workspace_id:
            my_metrics = self.get_exit_metrics_list()
            duplicates = ExtractionDefinition.objects.filter(workspace_id=self.workspace_id).exclude(pk=self.pk)
            conflicts = []
            for d in duplicates:
                other_metrics = set(d.get_exit_metrics_list())
                shared = set(my_metrics) & other_metrics
                if shared:
                    conflicts.append(f"'{d.name}' (shared: {', '.join(sorted(shared))})")
            if conflicts:
                conflict_details = "; ".join(conflicts)
                raise ValidationError({
                    'exit_metrics': (
                        f"Consistency Error: One or more exit metrics are already used in this workspace by: {conflict_details}. "
                        f"Each exit metric must be unique within a workspace to avoid Signal Score collisions."
                    )
                })

    def __str__(self):
        return f"{self.workspace.name} - {self.name}"


def get_default_postprocessing_variables() -> list[dict]:
    """
    Returns default candidate variables available for Extraction postprocessing snippets
    when no specific response schema is configured yet.
    """
    return [
        {
            "name": "score",
            "variable_name": "score",
            "original_name": "score",
            "category": "Schema Property",
            "source": "Default Schema Field",
            "type": "numeric (float)",
            "description": "Standard numerical score property (0.0 - 10.0)",
            "default": 8.5
        },
        {
            "name": "confidence",
            "variable_name": "confidence",
            "original_name": "confidence",
            "category": "Schema Property",
            "source": "Default Schema Field",
            "type": "numeric (float)",
            "description": "Extraction confidence indicator (0.0 - 1.0)",
            "default": 0.92
        },
        {
            "name": "category",
            "variable_name": "category",
            "original_name": "category",
            "category": "Schema Property",
            "source": "Default Schema Field",
            "type": "string",
            "description": "Extracted classification label or string tag",
            "default": "high_impact"
        },
        {
            "name": "title",
            "variable_name": "title",
            "original_name": "title",
            "category": "Paper Metadata Context",
            "source": "📄 Paper Metadata Context",
            "type": "string",
            "description": "Title of the research paper being evaluated",
            "default": "Deep Learning for Scientific Discovery"
        },
        {
            "name": "abstract",
            "variable_name": "abstract",
            "original_name": "abstract",
            "category": "Paper Metadata Context",
            "source": "📄 Paper Metadata Context",
            "type": "string",
            "description": "Full abstract text of the research paper",
            "default": "We present a novel benchmark and evaluation protocol..."
        },
        {
            "name": "arxiv_id",
            "variable_name": "arxiv_id",
            "original_name": "arxiv_id",
            "category": "Paper Metadata Context",
            "source": "📄 Paper Metadata Context",
            "type": "string",
            "description": "arXiv identifier of the paper (e.g. 2401.01234)",
            "default": "2401.01234"
        },
        {
            "name": "doi",
            "variable_name": "doi",
            "original_name": "doi",
            "category": "Paper Metadata Context",
            "source": "📄 Paper Metadata Context",
            "type": "string",
            "description": "Digital Object Identifier of the paper",
            "default": "10.1016/j.jbi.2024.104200"
        },
        {
            "name": "fields",
            "variable_name": "fields",
            "original_name": "fields",
            "category": "Extracted Fields Dictionary",
            "source": "📦 Global Extraction Dictionary",
            "type": "dict",
            "description": "Direct dictionary of all raw extracted fields: fields['key']",
            "default": {"score": 8.5, "confidence": 0.92}
        },
        {
            "name": "data",
            "variable_name": "data",
            "original_name": "data",
            "category": "Extracted Fields Dictionary",
            "source": "📦 Global Extraction Dictionary",
            "type": "dict",
            "description": "Alias for the raw extraction dictionary: data['key']",
            "default": {"score": 8.5, "confidence": 0.92}
        },
        {
            "name": "extractions",
            "variable_name": "extractions",
            "original_name": "extractions",
            "category": "Extracted Fields Dictionary",
            "source": "📦 Global Extraction Dictionary",
            "type": "dict",
            "description": "Alias for raw extraction dictionary",
            "default": {"score": 8.5, "confidence": 0.92}
        },
        {
            "name": "fields_data",
            "variable_name": "fields_data",
            "original_name": "fields_data",
            "category": "Extracted Fields Dictionary",
            "source": "📦 Global Extraction Dictionary",
            "type": "dict",
            "description": "Full fields_data dictionary payload",
            "default": {"score": 8.5, "confidence": 0.92}
        },
        {
            "name": "json_data",
            "variable_name": "json_data",
            "original_name": "json_data",
            "category": "Extracted Fields Dictionary",
            "source": "📦 Global Extraction Dictionary",
            "type": "dict",
            "description": "Alias for parsed extraction JSON dictionary",
            "default": {"score": 8.5, "confidence": 0.92}
        },
        {
            "name": "raw_data",
            "variable_name": "raw_data",
            "original_name": "raw_data",
            "category": "Extracted Fields Dictionary",
            "source": "📦 Global Extraction Dictionary",
            "type": "dict",
            "description": "Alias for raw JSON data payload",
            "default": {"score": 8.5, "confidence": 0.92}
        }
    ]


class Extraction(models.Model):
    """
    Stores schema-validated claims, research parameters, technical attributes, or patent details.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey('Workspace', on_delete=models.CASCADE, related_name="extractions")
    paper = models.ForeignKey('Paper', on_delete=models.CASCADE, related_name="extractions")
    extraction_definition = models.ForeignKey(
        ExtractionDefinition,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="extractions"
    )
    category = models.CharField(max_length=50, help_text="e.g. ml_method, performance_metric, patent_claim")
    fields_data = models.JSONField(help_text="Extracted data containing value, evidence array, rationale, and confidence per field")
    is_hitl_validated = models.BooleanField(default=False)
    
    version_info = models.JSONField(default=dict, help_text="Stores prompt_version, schema_version, llm_model, provider")
    validation_status = models.CharField(
        max_length=50, 
        choices=[('pending', 'Pending'), ('pass', 'Pass'), ('warn', 'Warn'), ('fail', 'Fail')],
        default='pending'
    )
    review_required = models.BooleanField(default=False)
    confidence_score = models.FloatField(blank=True, null=True, help_text="Aggregate confidence score")
    confidence_method = models.CharField(max_length=50, blank=True, null=True, help_text="e.g. self_consistency, single_pass")
    
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def exit_metric(self) -> str:
        """
        Dynamically unpacks the exit metric value from fields_data using extraction_definition.exit_metrics keys
        with smart fallbacks for key variants and scalar values.
        """
        if self.validation_status == 'fail':
            return "-"

        if self.fields_data and isinstance(self.fields_data, dict):
            data = self.fields_data
            if "fields" in data and isinstance(data["fields"], dict):
                data = data["fields"]

            # 0. If postprocessing_code is configured on definition, the postprocessed metric is primary
            if self.extraction_definition and self.extraction_definition.postprocessing_code and self.extraction_definition.postprocessing_code.strip():
                cand_name = self.extraction_definition.name.lower().replace(" ", "_")
                primary_exit = self.extraction_definition.get_primary_exit_metric()
                post_cands = [f"{cand_name}_postprocessed", f"{cand_name}_computed"]
                if primary_exit:
                    post_cands.insert(0, f"{primary_exit}_postprocessed")
                    post_cands.insert(1, f"{primary_exit}_computed")
                def _unwrap_cand(val):
                    if val is None:
                        return None
                    if isinstance(val, dict):
                        if "value" in val and len(val) <= 2:
                            return str(val["value"])
                        if len(val) == 1:
                            inner_v = next(iter(val.values()))
                            if isinstance(inner_v, dict) and "value" in inner_v:
                                return str(inner_v["value"])
                            if inner_v is not None:
                                return str(inner_v)
                        return None
                    return str(val)

                for pk in post_cands:
                    for k, v in data.items():
                        if k.lower().replace(" ", "_") == pk:
                            unwrapped = _unwrap_cand(v)
                            if unwrapped is not None:
                                return unwrapped
                # Fallback: any key ending with _postprocessed or _computed
                for k, v in data.items():
                    k_norm = k.lower().replace(" ", "_")
                    if k_norm.endswith("_postprocessed") or k_norm.endswith("_computed"):
                        unwrapped = _unwrap_cand(v)
                        if unwrapped is not None:
                            return unwrapped

            # 0.5 Explicit primary_frontend_metric prioritized if set
            if self.extraction_definition and self.extraction_definition.primary_frontend_metric and self.extraction_definition.primary_frontend_metric.strip():
                prim_k = self.extraction_definition.primary_frontend_metric.strip()
                val = data.get(prim_k)
                if isinstance(val, dict) and "value" in val:
                    return str(val["value"])
                if val is not None:
                    return str(val)
                for k, v in data.items():
                    if k.lower().replace(" ", "_") == prim_k.lower().replace(" ", "_"):
                        if isinstance(v, dict) and "value" in v:
                            return str(v["value"])
                        elif v is not None:
                            return str(v)

            # 1. Match on configured extraction_definition.exit_metrics (supports comma-separated list)
            if self.extraction_definition and self.extraction_definition.exit_metrics:
                exit_keys = self.extraction_definition.get_exit_metrics_list()
                for exit_key in exit_keys:
                    val = data.get(exit_key)
                    if isinstance(val, dict) and "value" in val:
                        return str(val["value"])
                    if val is not None:
                        return str(val)
                    # Case-insensitive / snake_case lookup for the configured exit_key
                    for k, v in data.items():
                        if k.lower().replace(" ", "_") == exit_key.lower().replace(" ", "_"):
                            if isinstance(v, dict) and "value" in v:
                                return str(v["value"])
                            elif v is not None:
                                return str(v)
                return "-"

            # 2. Case-insensitive / snake_case candidate keys when exit_metrics not set
            candidates = []
            if self.extraction_definition:
                cand_name = self.extraction_definition.name.lower().replace(" ", "_")
                candidates.extend([
                    f"{cand_name}_postprocessed",
                    f"{cand_name}_computed",
                    cand_name,
                    cand_name.replace("_extraction", ""),
                    cand_name.replace("_score", "")
                ])
            if self.category:
                cat_name = self.category.lower().replace(" ", "_")
                candidates.extend([
                    f"{cat_name}_postprocessed",
                    f"{cat_name}_computed",
                    cat_name,
                    cat_name.replace("_extraction", "")
                ])

            for ck in candidates:
                for k, v in data.items():
                    if k.lower().replace(" ", "_") == ck:
                        if isinstance(v, dict) and "value" in v:
                            return str(v["value"])
                        elif v is not None:
                            return str(v)

            # 3. First non-empty scalar value in fields_data (excluding long text / urls)
            for k, v in data.items():
                if isinstance(v, dict) and "value" in v:
                    return str(v["value"])
                elif isinstance(v, (int, float, bool)):
                    return str(v)
                elif isinstance(v, str) and len(v) < 80 and not v.startswith("http"):
                    return v

        return "-"

    @property
    def exit_metrics(self) -> str:
        return self.exit_metric

    def get_exit_metric(self) -> str:
        return self.exit_metric

    def get_exit_metrics(self) -> str:
        return self.exit_metrics

    class Meta:
        app_label = 'research_intelligence'
        ordering = ['-created_at', '-id']
        indexes = [
            models.Index(fields=['paper', 'extraction_definition']),
            models.Index(fields=['workspace', 'validation_status']),
            models.Index(fields=['paper', 'validation_status']),
            models.Index(fields=['workspace', '-created_at']),
            models.Index(fields=['paper', '-created_at']),
        ]

    def __str__(self):
        return f"{self.paper.title[:30]}... ({self.category}): {self.exit_metric}"


class HITLCorrection(models.Model):
    """
    Audits manual corrections and validation overrides made by domain experts.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    extraction = models.ForeignKey(Extraction, on_delete=models.CASCADE, related_name="corrections")
    action = models.CharField(max_length=50, help_text="verify, modify, or reject")
    human_operator = models.CharField(max_length=255, help_text="Email or identifier of the scientist")
    original_value = models.JSONField(help_text="Extracted data before correction")
    corrected_value = models.JSONField(blank=True, null=True, help_text="Updated data after correction")
    reason = models.TextField(blank=True, null=True, help_text="Reasoning for override")
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = 'research_intelligence'
        ordering = ['-timestamp', '-id']
