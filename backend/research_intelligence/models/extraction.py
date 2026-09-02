import uuid
import logging
from django.db import models

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
    exit_metric = models.CharField(max_length=100, blank=True, null=True, help_text="Field key to unpack from extracted data as the exit metric (e.g. 'fit_score', 'trl_score')")
    llm_model = models.CharField(max_length=100, default="google/gemini-3.8-flash", help_text="LLM model used for this specific extraction")
    version = models.IntegerField(default=1, help_text="Tracks prompt/schema evolution")
    requires_consensus = models.BooleanField(default=False, help_text="Requires multi-sample self-consistency for difficult fields")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def exit_metrics(self):
        return self.exit_metric

    @exit_metrics.setter
    def exit_metrics(self, value):
        self.exit_metric = value

    @property
    def exit_metric_key(self):
        return self.exit_metric

    @exit_metric_key.setter
    def exit_metric_key(self, value):
        self.exit_metric = value

    class Meta:
        app_label = 'research_intelligence'

    def __str__(self):
        return f"{self.workspace.name} - {self.name}"


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
        Dynamically unpacks the exit metric value from fields_data using extraction_definition.exit_metric key
        with smart fallbacks for key variants and scalar values.
        """
        if self.fields_data and isinstance(self.fields_data, dict):
            data = self.fields_data
            if "fields" in data and isinstance(data["fields"], dict):
                data = data["fields"]

            # 1. Exact match on configured extraction_definition.exit_metric
            if self.extraction_definition and self.extraction_definition.exit_metric:
                exit_key = self.extraction_definition.exit_metric
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

            # 2. Case-insensitive / snake_case candidate keys when exit_metric not set
            candidates = []
            if self.extraction_definition:
                cand_name = self.extraction_definition.name.lower().replace(" ", "_")
                candidates.extend([cand_name, cand_name.replace("_extraction", ""), cand_name.replace("_score", "")])
            if self.category:
                cat_name = self.category.lower().replace(" ", "_")
                candidates.extend([cat_name, cat_name.replace("_extraction", "")])

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

    def get_exit_metric(self) -> str:
        return self.exit_metric

    class Meta:
        app_label = 'research_intelligence'
        ordering = ['-created_at', '-id']
        indexes = [
            models.Index(fields=['paper', 'extraction_definition']),
            models.Index(fields=['workspace', 'validation_status']),
            models.Index(fields=['paper', 'validation_status']),
            models.Index(fields=['workspace', '-created_at']),
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
