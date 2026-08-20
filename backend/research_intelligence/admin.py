import json
from django import forms
from django.db import models
from django.contrib import admin
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.urls import reverse
from research_intelligence.models import (
    Workspace,
    WorkspaceMember,
    APIKey,
    Subscriber,
    Scraper,
    ExtractionDefinition,
    PipelineRun,
    ComponentRun,
    DocumentRegistry,
    Paper,
    Extraction,
    PaperMetric,
    NarrativeReport,
    HITLCorrection,
    UserActivityLog,
    ResearchAgentProcess,
)


class PrettyJSONWidget(forms.Textarea):
    """
    State-of-the-art interactive JSON viewer & editor widget for Django Admin.
    Provides a dark-mode monospace code editor with auto-formatting, live syntax validation, and visual tree preview.
    """
    def render(self, name, value, attrs=None, renderer=None):
        raw_json_str = ""
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
                raw_json_str = json.dumps(parsed, indent=2, ensure_ascii=False)
            except Exception:
                raw_json_str = value
        elif value is not None:
            try:
                raw_json_str = json.dumps(value, indent=2, ensure_ascii=False)
            except Exception:
                raw_json_str = str(value)

        attrs = attrs or {}
        attrs['style'] = "width: 100%; min-height: 320px; font-family: 'Fira Code', 'SFMono-Regular', Consolas, Menlo, monospace; font-size: 13px; line-height: 1.5; background-color: #0d1117; color: #e6edf3; padding: 12px; border-radius: 6px; border: 1px solid #30363d; tab-size: 2;"
        textarea_html = super().render(name, raw_json_str, attrs, renderer)
        widget_id = attrs.get('id', f'json_widget_{name}')

        js_helpers = """
        <script>
        if (typeof window.syntaxHighlightJson !== 'function') {
            window.syntaxHighlightJson = function(json) {
                if (typeof json !== 'string') {
                    json = JSON.stringify(json, undefined, 2);
                }
                json = json.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
                return json.replace(/("(\\u[a-zA-Z0-9]{4}|\\[^u]|[^\\"])*"(\\s*:)?|\\b(true|false|null)\\b|-?\\d+(?:\\.\\d*)?(?:[eE][+\\-]?\\d+)?)/g, function (match) {
                    var style = 'color: #d19a66;';
                    if (/^"/.test(match)) {
                        if (/:$/.test(match)) {
                            style = 'color: #7ee787; font-weight: 600;';
                        } else {
                            style = 'color: #a5d6ff;';
                        }
                    } else if (/true|false/.test(match)) {
                        style = 'color: #ff7b72; font-weight: 600;';
                    } else if (/null/.test(match)) {
                        style = 'color: #79c0ff; font-style: italic;';
                    }
                    return '<span style="' + style + '">' + match + '</span>';
                });
            };
            window.toggleJsonView = function(widgetId) {
                var rawDiv = document.getElementById(widgetId + '_raw');
                var prettyDiv = document.getElementById(widgetId + '_pretty');
                if (rawDiv.style.display === 'none') {
                    rawDiv.style.display = 'block';
                    prettyDiv.style.display = 'none';
                } else {
                    rawDiv.style.display = 'none';
                    prettyDiv.style.display = 'block';
                }
            };
            window.formatJsonEditor = function(widgetId) {
                var rawEl = document.getElementById(widgetId);
                if (rawEl) {
                    try {
                        var parsed = JSON.parse(rawEl.value);
                        rawEl.value = JSON.stringify(parsed, null, 2);
                        var statusEl = document.getElementById(widgetId + '_status');
                        if (statusEl) {
                            statusEl.innerHTML = '<span style="color: #3fb950; font-weight: bold;">✓ Formatted JSON</span>';
                        }
                    } catch(e) {
                        alert('Invalid JSON Syntax: ' + e.message);
                    }
                }
            };
            window.copyJsonContent = function(widgetId) {
                var rawEl = document.getElementById(widgetId);
                if (rawEl) {
                    navigator.clipboard.writeText(rawEl.value).then(function() {
                        alert('JSON copied to clipboard!');
                    });
                }
            };
        }
        </script>
        """

        html = f"""
        {js_helpers}
        <div class="pretty-json-container" style="margin: 8px 0; width: 100%; max-width: 950px;">
            <div style="margin-bottom: 8px; display: flex; gap: 8px; align-items: center; flex-wrap: wrap;">
                <button type="button" class="button" onclick="toggleJsonView('{widget_id}')" style="padding: 5px 12px; font-size: 11px; cursor: pointer; background: #0d6efd; color: white; border: none; border-radius: 4px;">⇄ Switch View (Editor / Readonly)</button>
                <button type="button" class="button" onclick="formatJsonEditor('{widget_id}')" style="padding: 5px 12px; font-size: 11px; cursor: pointer; background: #198754; color: white; border: none; border-radius: 4px;">✨ Format & Indent JSON</button>
                <button type="button" class="button" onclick="copyJsonContent('{widget_id}')" style="padding: 5px 12px; font-size: 11px; cursor: pointer; background: #495057; color: white; border: none; border-radius: 4px;">📋 Copy JSON</button>
                <span id="{widget_id}_status" style="font-size: 12px; font-family: monospace;"></span>
            </div>
            <div id="{widget_id}_raw" style="display: block;">
                {textarea_html}
            </div>
            <pre id="{widget_id}_pretty" style="display: none; background: #0d1117; color: #c9d1d9; padding: 14px; border-radius: 8px; border: 1px solid #30363d; font-family: 'SFMono-Regular', Consolas, Menlo, monospace; font-size: 12px; line-height: 1.5; max-height: 550px; overflow: auto; margin: 0; white-space: pre-wrap; word-break: break-word;"></pre>
        </div>
        <script>
        (function() {{
            var rawEl = document.getElementById('{widget_id}');
            var prettyEl = document.getElementById('{widget_id}_pretty');
            var statusEl = document.getElementById('{widget_id}_status');
            if (rawEl) {{
                function validateAndSync() {{
                    try {{
                        var obj = JSON.parse(rawEl.value);
                        if (prettyEl) prettyEl.innerHTML = window.syntaxHighlightJson(obj);
                        if (statusEl) statusEl.innerHTML = '<span style="color: #3fb950; font-weight: bold;">🟢 Valid JSON</span>';
                    }} catch(e) {{
                        if (prettyEl) prettyEl.textContent = rawEl.value;
                        if (statusEl) statusEl.innerHTML = '<span style="color: #f85149; font-weight: bold;">🔴 Invalid JSON</span>';
                    }}
                }}
                rawEl.addEventListener('input', validateAndSync);
                validateAndSync();
            }}
        }})();
        </script>
        """
        return mark_safe(html)


# Helper function to render CSS badges in Django Admin
def render_badge(text, bg_color="#6c757d", text_color="#ffffff"):
    return format_html(
        '<span style="background-color: {}; color: {}; padding: 4px 8px; border-radius: 4px; font-weight: bold; font-size: 11px; white-space: nowrap; display: inline-block;">{}</span>',
        bg_color,
        text_color,
        text
    )


# --- Inlines for Workspace ---

class WorkspaceMemberInline(admin.TabularInline):
    model = WorkspaceMember
    extra = 1
    fields = ('user', 'role', 'created_at')
    readonly_fields = ('created_at',)


class ScraperInline(admin.TabularInline):
    model = Scraper
    extra = 1
    fields = ('provider', 'search_query', 'is_active', 'created_at')
    readonly_fields = ('created_at',)


class SubscriberInline(admin.TabularInline):
    model = Subscriber
    extra = 1
    fields = ('name', 'email', 'is_active', 'created_at')
    readonly_fields = ('created_at',)


# Helper function to render formatted component metrics summary
def render_component_metrics_summary(obj):
    if not obj.metrics:
        return "-"
    m = obj.metrics
    if obj.step_type == 'screening':
        total = m.get('total_screened', 0)
        passed = m.get('passed', 0)
        rejected = m.get('rejected', 0)
        rej_color = '#6c757d' if rejected == 0 else '#dc3545'
        return format_html(
            '<div style="line-height: 1.35; white-space: nowrap;">'
            '<strong>{} screened:</strong><br>'
            '<span style="color: #198754; font-weight: 600;">{} passed</span>,<br>'
            '<span style="color: {}; font-weight: 600;">{} rejected</span>'
            '</div>',
            total,
            passed,
            rej_color,
            rejected,
        )
    elif obj.step_type == 'search':
        fetched = m.get('total_fetched', m.get('total_created', 0))
        skipped = m.get('total_duplicates_skipped', 0)
        if skipped:
            return format_html(
                '<div style="line-height: 1.35; white-space: nowrap;">'
                '<strong>{} papers</strong> fetched<br>'
                '<span style="color: #6c757d; font-size: 11px;">({} dupes skipped)</span>'
                '</div>',
                fetched,
                skipped,
            )
        return format_html(
            '<div style="line-height: 1.35; white-space: nowrap;">'
            '<strong>{} papers</strong> fetched'
            '</div>',
            fetched,
        )
    elif obj.step_type == 'download':
        dl = m.get('downloaded', 0)
        failed = m.get('failed', 0)
        cached = m.get('cached_hits', 0)
        extras = []
        if cached:
            extras.append(f"{cached} cached")
        if failed:
            extras.append(f"{failed} failed")
        if extras:
            return format_html(
                '<div style="line-height: 1.35; white-space: nowrap;">'
                '<strong>{} PDFs</strong> downloaded<br>'
                '<span style="color: #6c757d; font-size: 11px;">({})</span>'
                '</div>',
                dl,
                ", ".join(extras),
            )
        return format_html(
            '<div style="line-height: 1.35; white-space: nowrap;">'
            '<strong>{} PDFs</strong> downloaded'
            '</div>',
            dl,
        )
    elif obj.step_type == 'ocr':
        ocr = m.get('ocr_converted', 0)
        failed = m.get('failed', 0)
        if failed:
            return format_html(
                '<div style="line-height: 1.35; white-space: nowrap;">'
                '<strong>{}</strong> converted<br>'
                '<span style="color: #dc3545; font-size: 11px;">({} failed)</span>'
                '</div>',
                ocr,
                failed,
            )
    elif obj.step_type == 'signal_score':
        scored = m.get('scored_count', 0)
        total = m.get('total_papers', 0)
        avg_score = m.get('avg_signal_score', 0.0)
        max_score = m.get('max_signal_score', 0.0)
        return format_html(
            '<div style="line-height: 1.35; white-space: nowrap;">'
            '<strong>{}/{}</strong> scored<br>'
            '<span style="color: #0d6efd; font-weight: 600;">Avg: {:.2f}</span> (Max: {:.2f})'
            '</div>',
            scored,
            total,
            avg_score,
            max_score,
        )
        return format_html(
            '<div style="line-height: 1.35; white-space: nowrap;">'
            '<strong>{}</strong> converted'
            '</div>',
            ocr,
        )
    elif obj.step_type == 'extraction':
        created = m.get('extractions_created', 0)
        papers = m.get('total_papers', 0)
        defs = m.get('total_definitions', 0)
        return format_html(
            '<div style="line-height: 1.35; white-space: nowrap;">'
            '<strong>{} extractions</strong><br>'
            '<span style="color: #6c757d; font-size: 11px;">({} papers, {} defs)</span>'
            '</div>',
            created,
            papers,
            defs,
        )
    elif obj.step_type == 'reporting':
        reports = m.get('reports_generated', 1)
        return format_html(
            '<div style="line-height: 1.35; white-space: nowrap;">'
            '<strong>{} report(s)</strong> generated'
            '</div>',
            reports,
        )
    return "-"


# Helper function to render formatted component USD cost & tokens
def render_component_cost(obj):
    if not obj.metrics and not obj.output_data and obj.step_type not in ['screening', 'extraction', 'metrics', 'deep_research']:
        return format_html('<span style="color: #6c757d;">$0.0000</span>')

    cost = 0.0
    tokens = 0
    tokens_in = 0
    tokens_out = 0
    model_name = None

    metrics = obj.metrics if isinstance(obj.metrics, dict) else {}
    output_data = obj.output_data if isinstance(obj.output_data, dict) else {}

    # 1. Direct USD cost
    if 'usd_cost' in metrics and metrics['usd_cost'] is not None:
        cost = float(metrics.get('usd_cost') or 0.0)
    elif 'usd_cost' in output_data and output_data['usd_cost'] is not None:
        cost = float(output_data.get('usd_cost') or 0.0)

    # 2. Extract input/output tokens from all known schema variants
    tokens_in = int(
        metrics.get('tokens_in') or metrics.get('input_tokens') or metrics.get('prompt_tokens') or
        output_data.get('tokens_in') or output_data.get('input_tokens') or output_data.get('prompt_tokens') or 0
    )
    tokens_out = int(
        metrics.get('tokens_out') or metrics.get('output_tokens') or metrics.get('candidates_tokens') or
        output_data.get('tokens_out') or output_data.get('output_tokens') or output_data.get('candidates_tokens') or 0
    )
    tokens = int(
        metrics.get('total_tokens') or metrics.get('total_tokens_consumed') or
        output_data.get('total_tokens') or output_data.get('total_tokens_consumed') or (tokens_in + tokens_out) or 0
    )

    # 3. Model name
    model_name = metrics.get('model_used') or output_data.get('model_used')
    if not model_name and obj.pipeline_run and obj.pipeline_run.workspace:
        model_name = obj.pipeline_run.workspace.screening_llm_model
    model_name = model_name or "google/gemini-3.7-flash"

    # 4. If only total_tokens is known, split 80% prompt / 20% completion
    if tokens > 0 and tokens_in == 0 and tokens_out == 0:
        tokens_in = int(tokens * 0.8)
        tokens_out = max(1, tokens - tokens_in)

    # 5. Historical LLM fallback if token fields were completely omitted in legacy runs
    if obj.step_type in ['screening', 'extraction'] and tokens == 0 and cost == 0.0:
        if obj.step_type == 'screening':
            screened = int(metrics.get('total_screened') or 0)
            if screened > 0:
                if 'full_text' in str(obj.component_name).lower():
                    tokens_in = screened * 5000
                    tokens_out = screened * 300
                else:
                    tokens_in = screened * 800
                    tokens_out = screened * 200
                tokens = tokens_in + tokens_out
        elif obj.step_type == 'extraction':
            extracted = int(metrics.get('extractions_created') or metrics.get('total_extractions_attempted') or 0)
            if extracted > 0:
                tokens_in = extracted * 2500
                tokens_out = extracted * 400
                tokens = tokens_in + tokens_out

    # 6. Calculate cost dynamically if missing / 0.0 and tokens exist
    if cost == 0.0 and (tokens > 0 or tokens_in > 0 or tokens_out > 0):
        try:
            from research_intelligence.llm_providers.pricing import calculate_llm_cost
            cost = float(calculate_llm_cost(model_name, tokens_in, tokens_out))
        except Exception:
            pass

    if tokens == 0 and (tokens_in > 0 or tokens_out > 0):
        tokens = tokens_in + tokens_out

    if cost > 0:
        cost_str = f"{cost:.4f}"
        if tokens > 0:
            tokens_str = f"{tokens:,} tok"
            return format_html(
                '<div style="line-height: 1.35; white-space: nowrap;">'
                '<strong style="color: #0d6efd;">${}</strong><br>'
                '<span style="color: #6c757d; font-size: 11px;">{}</span>'
                '</div>',
                cost_str,
                tokens_str,
            )
        return format_html('<strong style="color: #0d6efd;">${}</strong>', cost_str)
    return format_html('<span style="color: #6c757d;">$0.0000</span>')



# --- Inlines for PipelineRun ---

class ComponentRunInline(admin.TabularInline):
    model = ComponentRun
    extra = 0
    fields = ('step_type_badge', 'component_name', 'status_badge', 'execution_time', 'cost_display', 'metrics_summary', 'celery_task_id', 'raw_storage_path', 'started_at', 'completed_at')
    readonly_fields = ('step_type_badge', 'status_badge', 'execution_time', 'cost_display', 'metrics_summary', 'started_at', 'completed_at')

    def execution_time(self, obj):
        sec = obj.duration_seconds
        if sec is None:
            return "-"
        formatted = obj.execution_time_display
        if obj.status == 'running':
            return format_html('<span style="color: #0d6efd; font-weight: 600;">{}</span>', formatted)
        elif obj.status == 'completed':
            return format_html('<span>⏱️ <strong>{}</strong></span>', formatted)
        elif obj.status in ['failed', 'aborted']:
            return format_html('<span style="color: #dc3545;">⏱️ {}</span>', formatted)
        return formatted
    execution_time.short_description = "Execution Time"

    def cost_display(self, obj):
        return render_component_cost(obj)
    cost_display.short_description = "USD Cost"

    def metrics_summary(self, obj):
        return render_component_metrics_summary(obj)
    metrics_summary.short_description = "Metrics Summary"

    def step_type_badge(self, obj):
        colors = {
            'search': '#0d6efd',
            'download': '#0dcaf0',
            'ocr': '#6f42c1',
            'screening': '#ffc107',
            'extraction': '#198754',
            'metrics': '#fd7e14',
            'deep_research': '#d63384',
            'reporting': '#20c997',
        }
        bg = colors.get(obj.step_type, '#6c757d')
        text_color = '#000000' if bg == '#ffc107' else '#ffffff'
        return render_badge(obj.get_step_type_display(), bg, text_color)
    step_type_badge.short_description = "Step Type"

    def status_badge(self, obj):
        colors = {
            'pending': '#6c757d',
            'running': '#0d6efd',
            'completed': '#198754',
            'failed': '#dc3545',
            'aborted': '#495057',
        }
        return render_badge(obj.status.upper(), colors.get(obj.status, '#6c757d'))
    status_badge.short_description = "Status"


# --- Model Admins ---

@admin.register(Workspace)
class WorkspaceAdmin(admin.ModelAdmin):
    list_display = (
        'name',
        'ocr_provider',
        'screening_llm_model',
        'monthly_token_limit',
        'tokens_in_consumed_this_month',
        'tokens_out_consumed_this_month',
        'tokens_consumed_this_month',
        'monthly_usd_limit',
        'usd_spent_this_month',
        'created_at'
    )
    search_fields = ('name', 'abstract_acceptance_criteria', 'abstract_rejection_criteria', 'full_text_acceptance_criteria', 'full_text_rejection_criteria')
    list_filter = ('ocr_provider', 'llm_provider', 'created_at')
    inlines = [WorkspaceMemberInline, ScraperInline, SubscriberInline]
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'digest_schedule')
        }),
        ('Pipeline Guidelines & Criteria', {
            'fields': (
                'abstract_acceptance_criteria', 'abstract_rejection_criteria',
                'full_text_acceptance_criteria', 'full_text_rejection_criteria'
            )
        }),
        ('Engine & Provider Configuration', {
            'fields': ('ocr_provider', 'screening_llm_model', 'llm_provider')
        }),
        ('Step 6: Signal Score Configuration', {
            'fields': ('signal_score_code',),
            'description': 'Custom Python snippet evaluated in Step 6 on paper extracted parameters (e.g. <code>k = fit_score + 2*novelty_score; return 5 if k > 10 else 99</code>). Executed securely in an isolated sandbox.'
        }),
        ('Monthly Quotas & Budgets', {
            'fields': (
                'monthly_token_limit',
                ('tokens_in_consumed_this_month', 'tokens_out_consumed_this_month'),
                'tokens_consumed_this_month',
                'monthly_usd_limit',
                'usd_spent_this_month'
            )
        }),
    )


@admin.register(WorkspaceMember)
class WorkspaceMemberAdmin(admin.ModelAdmin):
    list_display = ('user', 'workspace', 'role_badge', 'created_at')
    list_filter = ('role', 'workspace', 'created_at')
    search_fields = ('user__username', 'user__email', 'workspace__name')

    def role_badge(self, obj):
        colors = {
            'admin': '#dc3545',
            'manager': '#0d6efd',
            'researcher': '#198754',
        }
        return render_badge(obj.role.upper(), colors.get(obj.role, '#6c757d'))
    role_badge.short_description = "Role"


class APIKeyAdminForm(forms.ModelForm):
    new_secret = forms.CharField(
        required=False,
        label="New Secret Key",
        help_text="Provide a custom secret/password. If left blank on creation, a random one will be generated. On edit, leave blank to keep current.",
        widget=forms.TextInput(attrs={'style': 'width: 25em;'}),
    )

    class Meta:
        model = APIKey
        fields = '__all__'


@admin.register(APIKey)
class APIKeyAdmin(admin.ModelAdmin):
    form = APIKeyAdminForm
    list_display = ('name', 'key_id', 'user', 'workspace', 'status_badge', 'last_used_at', 'created_at')
    list_filter = ('is_active', 'created_at', 'workspace')
    search_fields = ('name', 'key_id', 'user__username', 'user__email')
    fields = ('name', 'key_id', 'hashed_secret', 'is_active', 'scopes', 'user', 'workspace', 'new_secret', 'generate_secret_button', 'created_at', 'last_used_at')
    readonly_fields = ('key_id', 'hashed_secret', 'created_at', 'last_used_at', 'generate_secret_button')
    actions = ['revoke_keys']

    def status_badge(self, obj):
        if obj.is_active:
            return render_badge("ACTIVE", "#198754")
        return render_badge("REVOKED", "#dc3545")
    status_badge.short_description = "Status"

    def generate_secret_button(self, obj):
        if not obj.pk:
            return "Save the API Key first to generate a secret."
        url = reverse('admin:generate-apikey-secret', args=[obj.pk])
        return format_html(
            '<a class="button" href="{}">⚡ Generate & Show New Secret</a>',
            url
        )
    generate_secret_button.short_description = "Generate Secret"

    def save_model(self, request, obj, form, change):
        import secrets
        from django.contrib import messages
        
        new_secret = form.cleaned_data.get('new_secret')
        
        # Auto-generate key_id if not present
        if not obj.key_id:
            obj.key_id = secrets.token_hex(8)
            
        raw_secret = None
        if not change and not new_secret:
            # On creation, if no secret is provided, generate a random one
            raw_secret = secrets.token_urlsafe(32)
            obj.set_secret(raw_secret)
        elif new_secret:
            # If a custom secret is entered, use it
            obj.set_secret(new_secret)
            raw_secret = new_secret
            
        super().save_model(request, obj, form, change)
        
        if raw_secret:
            messages.success(
                request,
                format_html(
                    "API Key secret successfully configured! The secret key is:<br><br>"
                    "<code style='font-size: 16px; font-weight: bold; background: #eee; padding: 4px 8px; border-radius: 4px; color: #111;'>{}</code><br><br>"
                    "Please copy this secret key now. It is hashed in the database and cannot be retrieved later.",
                    raw_secret
                )
            )

    def get_urls(self):
        from django.urls import path
        urls = super().get_urls()
        custom_urls = [
            path(
                '<path:object_id>/generate-secret/',
                self.admin_site.admin_view(self.generate_secret),
                name='generate-apikey-secret'
            ),
        ]
        return custom_urls + urls

    def generate_secret(self, request, object_id):
        import secrets
        from django.http import HttpResponseRedirect, Http404
        from django.contrib import messages
        
        obj = self.get_object(request, object_id)
        if obj is None:
            raise Http404("APIKey not found")
        
        raw_secret = secrets.token_urlsafe(32)
        obj.set_secret(raw_secret)
        obj.save(update_fields=['hashed_secret'])
        
        messages.success(
            request,
            format_html(
                "Successfully generated a new secret for API Key <strong>{}</strong>:<br><br>"
                "<code style='font-size: 16px; font-weight: bold; background: #eee; padding: 4px 8px; border-radius: 4px; color: #111;'>{}</code><br><br>"
                "Please copy this secret now. It is hashed in the database and cannot be retrieved again.",
                obj.name,
                raw_secret
            )
        )
        return HttpResponseRedirect(reverse('admin:research_intelligence_apikey_change', args=[object_id]))

    def revoke_keys(self, request, queryset):
        rows = queryset.update(is_active=False)
        self.message_user(request, f"Successfully revoked {rows} API key(s).")
    revoke_keys.short_description = "Revoke selected API Keys"


@admin.register(Scraper)
class ScraperAdmin(admin.ModelAdmin):
    list_display = ('workspace', 'provider_badge', 'search_query', 'status_badge', 'created_at')
    list_filter = ('provider', 'is_active', 'workspace')
    search_fields = ('workspace__name', 'search_query')

    def provider_badge(self, obj):
        colors = {
            'arxiv': '#fd7e14',
            'openalex': '#0d6efd',
            'lens': '#6f42c1',
        }
        return render_badge(obj.get_provider_display(), colors.get(obj.provider, '#6c757d'))
    provider_badge.short_description = "Provider"

    def status_badge(self, obj):
        return render_badge("ACTIVE", "#198754") if obj.is_active else render_badge("DISABLED", "#6c757d")
    status_badge.short_description = "Status"


@admin.register(PipelineRun)
class PipelineRunAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'workspace',
        'run_date',
        'status_badge',
        'current_stage_badge',
        'reprocess_existing',
        'execution_time',
        'formatted_usd_cost',
        'total_papers_fetched',
        'total_papers_passed_screening',
        'tokens_in',
        'tokens_out',
        'tokens_consumed',
        'started_at',
        'completed_at'
    )
    ordering = ('-started_at', '-id')
    list_filter = ('status', 'current_stage', 'reprocess_existing', 'run_date', 'workspace')
    search_fields = ('id', 'workspace__name')
    readonly_fields = ('started_at', 'completed_at', 'execution_time')
    inlines = [ComponentRunInline]

    actions = ['run_full_pipeline']

    def execution_time(self, obj):
        sec = obj.duration_seconds
        if sec is None:
            return "-"
        formatted = obj.execution_time_display
        if obj.status == 'running':
            return format_html('<span style="color: #0d6efd; font-weight: 600;">{}</span>', formatted)
        elif obj.status == 'completed':
            return format_html('<span>⏱️ <strong>{}</strong></span>', formatted)
        elif obj.status in ['failed', 'aborted']:
            return format_html('<span style="color: #dc3545;">⏱️ {}</span>', formatted)
        return formatted
    execution_time.short_description = "Execution Time"
    execution_time.admin_order_field = 'completed_at'

    def formatted_usd_cost(self, obj):
        cost = float(obj.usd_cost or 0.0)
        if cost == 0.0 and (obj.tokens_in or obj.tokens_out or obj.tokens_consumed):
            try:
                from research_intelligence.llm_providers.pricing import calculate_llm_cost
                model_name = obj.workspace.screening_llm_model if obj.workspace else "google/gemini-3.7-flash"
                cost = float(calculate_llm_cost(model_name, obj.tokens_in or 0, obj.tokens_out or 0))
            except Exception:
                pass
        if cost > 0:
            return format_html('<strong style="color: #0d6efd;">${}</strong>', f"{cost:.4f}")
        return format_html('<span style="color: #6c757d;">$0.0000</span>')
    formatted_usd_cost.short_description = "USD Cost"
    formatted_usd_cost.admin_order_field = 'usd_cost'

    def status_badge(self, obj):
        colors = {
            'pending': '#6c757d',
            'running': '#0d6efd',
            'completed': '#198754',
            'failed': '#dc3545',
            'aborted': '#495057',
        }
        return render_badge(obj.status.upper(), colors.get(obj.status, '#6c757d'))
    status_badge.short_description = "Status"

    def current_stage_badge(self, obj):
        colors = {
            'search': '#0d6efd',
            'download': '#0dcaf0',
            'ocr': '#6f42c1',
            'screening': '#ffc107',
            'extraction': '#198754',
            'metrics': '#fd7e14',
            'deep_research': '#d63384',
            'reporting': '#20c997',
            'completed': '#198754',
        }
        bg = colors.get(obj.current_stage, '#6c757d')
        text_color = '#000000' if bg == '#ffc107' else '#ffffff'
        return render_badge(obj.get_current_stage_display(), bg, text_color)
    current_stage_badge.short_description = "Current Stage"

    @admin.action(description="🚀 Launch/Advance End-to-End Autonomous Pipeline")
    def run_full_pipeline(self, request, queryset):
        from research_intelligence.tasks.orchestrator.agent_engine import tick_agent_process
        for pr in queryset:
            agent = pr.agent_processes.filter(status__in=['running', 'pending', 'paused']).first()
            if not agent:
                agent = ResearchAgentProcess.objects.create(
                    workspace=pr.workspace,
                    pipeline_run=pr,
                    name=f"Autonomous Pipeline - {pr.workspace.name}",
                    status='running',
                    current_step=pr.current_stage if pr.current_stage != 'completed' else 'initialized'
                )
            tick_agent_process(str(agent.id))
        self.message_user(request, f"Triggered autonomous pipeline orchestrator for {queryset.count()} pipeline run(s).")


@admin.register(ResearchAgentProcess)
class ResearchAgentProcessAdmin(admin.ModelAdmin):
    formfield_overrides = {
        models.JSONField: {'widget': PrettyJSONWidget},
    }
    list_display = (
        'name',
        'workspace',
        'status_badge',
        'current_step_badge',
        'execution_time',
        'usd_cost',
        'pipeline_run_link',
        'started_at',
        'completed_at'
    )
    ordering = ('-started_at', '-id')
    list_filter = ('status', 'current_step', 'workspace')
    search_fields = ('name', 'id', 'workspace__name')
    readonly_fields = ('started_at', 'completed_at', 'execution_time', 'step_history_preview')

    fieldsets = (
        ('Agent Identification', {
            'fields': ('workspace', 'name', 'status', 'current_step', 'pipeline_run')
        }),
        ('Configuration & Override', {
            'fields': ('configuration_override',)
        }),
        ('Audit Log & History', {
            'fields': ('step_history_preview', 'step_history', 'error_message')
        }),
        ('Lifecycle', {
            'fields': ('started_at', 'completed_at')
        }),
    )

    actions = ['tick_selected_agents', 'pause_selected_agents', 'resume_selected_agents', 'abort_selected_agents']

    def usd_cost(self, obj):
        if obj.pipeline_run:
            cost = float(obj.pipeline_run.usd_cost or 0.0)
            if cost == 0.0 and (obj.pipeline_run.tokens_in or obj.pipeline_run.tokens_out or obj.pipeline_run.tokens_consumed):
                try:
                    from research_intelligence.llm_providers.pricing import calculate_llm_cost
                    model_name = obj.pipeline_run.workspace.screening_llm_model if obj.pipeline_run.workspace else "google/gemini-3.7-flash"
                    cost = float(calculate_llm_cost(model_name, obj.pipeline_run.tokens_in or 0, obj.pipeline_run.tokens_out or 0))
                except Exception:
                    pass
            if cost > 0:
                return format_html('<strong style="color: #0d6efd;">${}</strong>', f"{cost:.4f}")
        return format_html('<span style="color: #6c757d;">$0.0000</span>')
    usd_cost.short_description = "USD Cost"
    usd_cost.admin_order_field = 'pipeline_run__usd_cost'

    def status_badge(self, obj):
        colors = {
            'pending': '#6c757d',
            'running': '#0d6efd',
            'paused': '#ffc107',
            'completed': '#198754',
            'failed': '#dc3545',
            'aborted': '#495057',
        }
        bg = colors.get(obj.status, '#6c757d')
        text_color = '#000000' if bg == '#ffc107' else '#ffffff'
        return render_badge(obj.status.upper(), bg, text_color)
    status_badge.short_description = "Status"

    def current_step_badge(self, obj):
        colors = {
            'initialized': '#6c757d',
            'search': '#0d6efd',
            'download': '#0dcaf0',
            'ocr': '#6f42c1',
            'screening': '#ffc107',
            'extraction': '#198754',
            'completed': '#198754',
            'failed': '#dc3545',
            'aborted': '#495057',
        }
        bg = colors.get(obj.current_step, '#6c757d')
        text_color = '#000000' if bg == '#ffc107' else '#ffffff'
        return render_badge(obj.get_current_step_display(), bg, text_color)
    current_step_badge.short_description = "Active Step"

    def execution_time(self, obj):
        sec = obj.duration_seconds
        if sec is None:
            return "-"
        formatted = obj.execution_time_display
        if obj.status == 'running':
            return format_html('<span style="color: #0d6efd; font-weight: 600;">{}</span>', formatted)
        elif obj.status == 'completed':
            return format_html('<span>⏱️ <strong>{}</strong></span>', formatted)
        elif obj.status in ['failed', 'aborted']:
            return format_html('<span style="color: #dc3545;">⏱️ {}</span>', formatted)
        return formatted
    execution_time.short_description = "Execution Time"
    execution_time.admin_order_field = 'completed_at'

    def pipeline_run_link(self, obj):
        if not obj.pipeline_run:
            return "-"
        url = reverse("admin:research_intelligence_pipelinerun_change", args=[obj.pipeline_run.id])
        return format_html('<a href="{}"><code>{}</code></a>', url, str(obj.pipeline_run.id)[:8] + '...')
    pipeline_run_link.short_description = "Pipeline Run"

    def step_history_preview(self, obj):
        if not obj.step_history:
            return "-"
        items = []
        for entry in obj.step_history:
            step = entry.get('step', 'unknown')
            event = entry.get('event') or entry.get('action') or 'event'
            ts = entry.get('timestamp', '')
            details = []
            if 'papers_fetched' in entry:
                details.append(f"{entry['papers_fetched']} papers")
            if 'passed' in entry and 'total_screened' in entry:
                details.append(f"{entry['passed']}/{entry['total_screened']} passed")
            elif 'passed' in entry:
                details.append(f"{entry['passed']} passed")
            if 'error' in entry:
                details.append(f"<span style='color: #dc3545;'>{entry['error']}</span>")
            if 'message' in entry:
                details.append(f"<em>{entry['message']}</em>")

            detail_str = f" &bull; {', '.join(details)}" if details else ""
            badge_color = "#198754" if event == "completed" else ("#dc3545" if event in ["failed", "halted_zero_papers"] else "#0d6efd")
            items.append(
                f"<li><strong>{step}</strong>: <span style='color: {badge_color}; font-weight: 500;'>{event}</span>"
                f"{detail_str} <span style='color: #888; font-size: 11px;'>({ts})</span></li>"
            )
        return format_html('<ul style="margin: 0; padding-left: 18px; line-height: 1.6;">{}</ul>', mark_safe("".join(items)))
    step_history_preview.short_description = "Recent History"

    @admin.action(description="▶️ Advance/Tick Selected Agent(s)")
    def tick_selected_agents(self, request, queryset):
        from research_intelligence.tasks.orchestrator.agent_engine import tick_agent_process
        for agent in queryset:
            tick_agent_process(str(agent.id))
        self.message_user(request, f"Ticked state machine for {queryset.count()} agent process(es).")

    @admin.action(description="⏸️ Pause Selected Agent(s)")
    def pause_selected_agents(self, request, queryset):
        for agent in queryset.filter(status='running'):
            agent.status = 'paused'
            agent.save(update_fields=['status'])
        self.message_user(request, f"Paused {queryset.count()} agent process(es).")

    @admin.action(description="▶️ Resume Selected Agent(s)")
    def resume_selected_agents(self, request, queryset):
        from research_intelligence.tasks.orchestrator.agent_engine import tick_agent_process
        for agent in queryset.filter(status='paused'):
            agent.status = 'running'
            agent.save(update_fields=['status'])
            tick_agent_process(str(agent.id))
        self.message_user(request, f"Resumed {queryset.count()} agent process(es).")

    @admin.action(description="⏹️ Abort Selected Agent(s)")
    def abort_selected_agents(self, request, queryset):
        for agent in queryset.exclude(status__in=['completed', 'failed', 'aborted']):
            agent.status = 'aborted'
            agent.save(update_fields=['status'])
        self.message_user(request, f"Aborted {queryset.count()} agent process(es).")


class RecentPipelineRunFilter(admin.SimpleListFilter):
    title = "Pipeline Run (Recent 15)"
    parameter_name = "pipeline_run_id"

    def lookups(self, request, model_admin):
        runs = (
            PipelineRun.objects.select_related('workspace')
            .order_by('-started_at', '-id')[:15]
        )
        options = []
        for r in runs:
            ws_name = r.workspace.name if r.workspace else "No Workspace"
            short_id = str(r.id)[:8]
            date_str = r.started_at.strftime('%Y-%m-%d %H:%M') if r.started_at else (r.run_date.strftime('%Y-%m-%d') if r.run_date else "No Date")
            status_emoji = "🟢" if r.status == 'completed' else ("🔵" if r.status == 'running' else ("🔴" if r.status == 'failed' else "⚪"))
            label = f"{status_emoji} [{short_id}] {ws_name} ({date_str})"
            options.append((str(r.id), label))
        return options

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(pipeline_run_id=self.value())
        return queryset


class ComponentRunWorkspaceFilter(admin.SimpleListFilter):
    title = "Workspace"
    parameter_name = "workspace_id"

    def lookups(self, request, model_admin):
        workspaces = Workspace.objects.order_by('name')[:30]
        return [(str(w.id), w.name) for w in workspaces]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(pipeline_run__workspace_id=self.value())
        return queryset


@admin.register(ComponentRun)
class ComponentRunAdmin(admin.ModelAdmin):
    formfield_overrides = {
        models.JSONField: {'widget': PrettyJSONWidget},
    }
    list_display = (
        'id',
        'pipeline_run_link',
        'step_type_badge',
        'component_name',
        'status_badge',
        'execution_time',
        'cost_display',
        'metrics_summary',
        'celery_task_id',
        'started_at',
        'completed_at'
    )
    ordering = ('-started_at', '-id')
    list_filter = (RecentPipelineRunFilter, ComponentRunWorkspaceFilter, 'step_type', 'status', 'started_at')
    search_fields = ('id', 'component_name', 'celery_task_id', 'pipeline_run__id', 'pipeline_run__workspace__name')
    readonly_fields = ('started_at', 'completed_at', 'execution_time')

    def pipeline_run_link(self, obj):
        if not obj.pipeline_run:
            return "-"
        url = reverse("admin:research_intelligence_pipelinerun_change", args=[obj.pipeline_run.id])
        ws_name = obj.pipeline_run.workspace.name if obj.pipeline_run.workspace else ""
        short_id = str(obj.pipeline_run.id)[:8]
        return format_html(
            '<a href="{}" title="Pipeline Run: {}">'
            '<strong>{}</strong><br>'
            '<span style="color: #6c757d; font-size: 11px;">{}</span>'
            '</a>',
            url,
            str(obj.pipeline_run.id),
            short_id,
            ws_name[:25] + ("..." if len(ws_name) > 25 else "")
        )
    pipeline_run_link.short_description = "Pipeline Run"
    pipeline_run_link.admin_order_field = "pipeline_run"

    def execution_time(self, obj):
        sec = obj.duration_seconds
        if sec is None:
            return "-"
        formatted = obj.execution_time_display
        if obj.status == 'running':
            return format_html('<span style="color: #0d6efd; font-weight: 600;">{}</span>', formatted)
        elif obj.status == 'completed':
            return format_html('<span>⏱️ <strong>{}</strong></span>', formatted)
        elif obj.status in ['failed', 'aborted']:
            return format_html('<span style="color: #dc3545;">⏱️ {}</span>', formatted)
        return formatted
    execution_time.short_description = "Execution Time"
    execution_time.admin_order_field = 'completed_at'

    def cost_display(self, obj):
        return render_component_cost(obj)
    cost_display.short_description = "USD Cost"

    def metrics_summary(self, obj):
        return render_component_metrics_summary(obj)
    metrics_summary.short_description = "Metrics Summary"

    def step_type_badge(self, obj):
        colors = {
            'search': '#0d6efd',
            'download': '#0dcaf0',
            'ocr': '#6f42c1',
            'screening': '#ffc107',
            'extraction': '#198754',
            'metrics': '#fd7e14',
            'deep_research': '#d63384',
            'reporting': '#20c997',
        }
        bg = colors.get(obj.step_type, '#6c757d')
        text_color = '#000000' if bg == '#ffc107' else '#ffffff'
        return render_badge(obj.get_step_type_display(), bg, text_color)
    step_type_badge.short_description = "Step Type"

    def status_badge(self, obj):
        colors = {
            'pending': '#6c757d',
            'running': '#0d6efd',
            'completed': '#198754',
            'failed': '#dc3545',
            'aborted': '#495057',
        }
        return render_badge(obj.status.upper(), colors.get(obj.status, '#6c757d'))
    status_badge.short_description = "Status"


@admin.register(Paper)
class PaperAdmin(admin.ModelAdmin):
    formfield_overrides = {
        models.JSONField: {'widget': PrettyJSONWidget},
    }
    list_display = (
        'title',
        'workspace',
        'pipeline_run',
        'signal_score_badge',
        'source_database',
        'screening_status_badge',
        'is_evaluation_benchmark',
        'created_at'
    )
    ordering = ('-created_at', '-id')
    list_filter = ('source_database', 'screening_status', 'is_evaluation_benchmark', 'workspace')
    search_fields = ('title', 'authors', 'doi', 'arxiv_id', 'hash_id')

    def signal_score_badge(self, obj):
        if obj.signal_score is None:
            return mark_safe('<span style="color: #6c757d; font-size: 0.85em;">-</span>')
        return format_html(
            '<span style="background-color: #0d6efd; color: #ffffff; padding: 3px 8px; border-radius: 4px; font-weight: 700; font-size: 0.9em;">'
            '⚡ {:.2f}'
            '</span>',
            obj.signal_score
        )
    signal_score_badge.short_description = "Signal Score"
    signal_score_badge.admin_order_field = 'signal_score'

    def screening_status_badge(self, obj):
        colors = {
            'pending': '#6c757d',
            'abstract_passed': '#0dcaf0',
            'full_text_passed': '#198754',
            'borderline': '#ffc107',
            'rejected': '#dc3545',
        }
        bg = colors.get(obj.screening_status, '#6c757d')
        text_color = '#000000' if bg in ['#ffc107', '#0dcaf0'] else '#ffffff'
        return render_badge(obj.get_screening_status_display(), bg, text_color)
    screening_status_badge.short_description = "Screening Status"


@admin.register(ExtractionDefinition)
class ExtractionDefinitionAdmin(admin.ModelAdmin):
    formfield_overrides = {
        models.JSONField: {'widget': PrettyJSONWidget},
    }
    list_display = ('name', 'exit_metric', 'workspace', 'version', 'llm_model', 'requires_consensus', 'is_active', 'created_at')
    ordering = ('-created_at', '-id')
    list_filter = ('is_active', 'requires_consensus', 'workspace')
    search_fields = ('name', 'exit_metric', 'system_prompt', 'user_prompt_template')
    fields = (
        'workspace',
        'name',
        'exit_metric',
        'system_prompt',
        'user_prompt_template',
        'response_schema',
        'llm_model',
        'version',
        'requires_consensus',
        'is_active'
    )


@admin.register(Extraction)
class ExtractionAdmin(admin.ModelAdmin):
    formfield_overrides = {
        models.JSONField: {'widget': PrettyJSONWidget},
    }
    list_display = (
        'paper',
        'extraction_definition',
        'exit_metric_badge',
        'category',
        'workspace',
        'validation_status',
        'confidence_score',
        'review_required',
        'created_at'
    )
    ordering = ('-created_at', '-id')
    list_filter = ('validation_status', 'review_required', 'category', 'workspace')
    search_fields = ('paper__title', 'category', 'extraction_definition__name')
    readonly_fields = ('exit_metric_preview', 'extraction_system_prompt', 'extraction_user_prompt_template', 'created_at')

    fieldsets = (
        ('Extraction Target & Definition', {
            'fields': (
                'workspace',
                'paper',
                'extraction_definition',
                'category',
                'extraction_system_prompt',
                'extraction_user_prompt_template'
            )
        }),
        ('Extracted Data & Evidence', {
            'fields': (
                'exit_metric_preview',
                'fields_data',
                'validation_status',
                'confidence_score',
                'confidence_method',
                'review_required',
                'is_hitl_validated'
            )
        }),
        ('Execution Metadata', {
            'fields': ('version_info', 'created_at')
        }),
    )

    actions = ['rerun_selected_extractions']

    def exit_metric_badge(self, obj):
        metric_str = obj.get_exit_metric()
        if not metric_str or metric_str == "-":
            return mark_safe('<span style="color: #6c757d; font-size: 0.85em;">-</span>')

        lower_str = metric_str.lower()
        if any(k in lower_str for k in ("fit_score", "schwarz", "trl", "score")):
            bg = "#0d6efd"  # Primary Blue
            color = "#ffffff"
        elif any(k in lower_str for k in ("pass", "accepted", "high", "true")):
            bg = "#198754"  # Emerald Green
            color = "#ffffff"
        elif any(k in lower_str for k in ("fail", "rejected", "low", "false")):
            bg = "#dc3545"  # Crimson Red
            color = "#ffffff"
        elif any(k in lower_str for k in ("warn", "medium", "borderline")):
            bg = "#ffc107"  # Amber
            color = "#000000"
        else:
            bg = "#6f42c1"  # Purple
            color = "#ffffff"

        return format_html(
            '<span style="background-color: {}; color: {}; padding: 4px 9px; border-radius: 5px; '
            'font-size: 0.82em; font-weight: 600; display: inline-block; white-space: nowrap; '
            'box-shadow: 0 1px 3px rgba(0,0,0,0.12);" title="{}">{}</span>',
            bg, color, metric_str, metric_str
        )
    exit_metric_badge.short_description = "Exit Metric / Output"

    def exit_metric_preview(self, obj):
        metric_str = obj.get_exit_metric()
        return format_html('<strong style="font-size: 1.1em; color: #0d6efd;">{}</strong>', metric_str)
    exit_metric_preview.short_description = "Primary Exit Metric"

    @admin.action(description="🔄 Re-run selected extraction(s)")
    def rerun_selected_extractions(self, request, queryset):
        from research_intelligence.tasks.step_5_extraction.extract import _run_single_extraction_worker
        succeeded = 0
        failed = 0
        for extraction in queryset:
            if extraction.paper and extraction.extraction_definition:
                res = _run_single_extraction_worker(
                    paper=extraction.paper,
                    definition=extraction.extraction_definition,
                    workspace=extraction.workspace
                )
                if res.get("success"):
                    succeeded += 1
                else:
                    failed += 1
        self.message_user(request, f"Successfully re-ran {succeeded} extraction(s). (Failed: {failed})")

    def extraction_system_prompt(self, obj):
        if obj.extraction_definition:
            return obj.extraction_definition.system_prompt
        return "-"
    extraction_system_prompt.short_description = "System Prompt (from Definition)"

    def extraction_user_prompt_template(self, obj):
        if obj.extraction_definition:
            return obj.extraction_definition.user_prompt_template
        return "-"
    extraction_user_prompt_template.short_description = "User Prompt Template (from Definition)"


@admin.register(PaperMetric)
class PaperMetricAdmin(admin.ModelAdmin):
    formfield_overrides = {
        models.JSONField: {'widget': PrettyJSONWidget},
    }
    list_display = ('paper', 'workspace', 'signal_score', 'trl_score', 'importance_score', 'citation_count', 'created_at')
    ordering = ('-created_at', '-id')
    list_filter = ('workspace', 'trl_score')
    search_fields = ('paper__title',)


@admin.register(NarrativeReport)
class NarrativeReportAdmin(admin.ModelAdmin):
    list_display = ('title', 'workspace', 'pipeline_run', 'refinement_depth', 'created_at')
    ordering = ('-created_at', '-id')
    list_filter = ('workspace', 'created_at')
    search_fields = ('title', 'content_markdown')


@admin.register(HITLCorrection)
class HITLCorrectionAdmin(admin.ModelAdmin):
    list_display = ('action', 'human_operator', 'extraction', 'timestamp')
    ordering = ('-timestamp', '-id')
    list_filter = ('action', 'timestamp')
    search_fields = ('human_operator', 'reason')


@admin.register(Subscriber)
class SubscriberAdmin(admin.ModelAdmin):
    list_display = ('email', 'name', 'workspace', 'is_active', 'created_at')
    ordering = ('-created_at', '-id')
    list_filter = ('is_active', 'workspace')
    search_fields = ('email', 'name')


@admin.register(UserActivityLog)
class UserActivityLogAdmin(admin.ModelAdmin):
    """
    State-of-the-art Django Admin interface for operational User & API Activity Audit Logs.
    Imforces read-only immutability, visual status badges, and pretty JSON formatting for payloads.
    """
    list_display = (
        'formatted_timestamp',
        'user_display',
        'workspace_display',
        'interface_badge',
        'action_name',
        'status_badge',
        'execution_duration_fmt',
        'ip_address'
    )
    ordering = ('-timestamp', '-id')
    list_filter = ('interface', 'status', 'timestamp')
    search_fields = (
        'user_username',
        'user_email',
        'workspace_name',
        'action_name',
        'error_message',
        'ip_address',
        'api_key_id'
    )
    readonly_fields = [f.name for f in UserActivityLog._meta.fields]
    formfield_overrides = {
        models.JSONField: {'widget': PrettyJSONWidget},
    }

    def has_add_permission(self, request):
        return False  # Immutable audit trail

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser

    def formatted_timestamp(self, obj):
        return obj.timestamp.strftime("%Y-%m-%d %H:%M:%S")
    formatted_timestamp.short_description = "Timestamp"
    formatted_timestamp.admin_order_field = "timestamp"

    def user_display(self, obj):
        return obj.user_username or (obj.user.username if obj.user else "Anonymous")
    user_display.short_description = "User"

    def workspace_display(self, obj):
        return obj.workspace_name or (obj.workspace.name if obj.workspace else "-")
    workspace_display.short_description = "Workspace"

    def interface_badge(self, obj):
        color = "#0052cc" if obj.interface == "mcp" else "#6f42c1"
        return format_html(
            f'<span style="background-color: {color}; color: white; padding: 3px 8px; border-radius: 4px; font-weight: bold; font-size: 11px;">{obj.interface.upper()}</span>'
        )
    interface_badge.short_description = "Interface"

    def status_badge(self, obj):
        if obj.status == "success":
            color = "#28a745"
        elif obj.status == "unauthorized":
            color = "#fd7e14"
        else:
            color = "#dc3545"
        return format_html(
            f'<span style="background-color: {color}; color: white; padding: 3px 8px; border-radius: 4px; font-weight: bold; font-size: 11px;">{obj.status.upper()}</span>'
        )
    status_badge.short_description = "Status"

    def execution_duration_fmt(self, obj):
        return f"{obj.execution_time_ms:.1f} ms"
    execution_duration_fmt.short_description = "Duration"
    execution_duration_fmt.admin_order_field = "execution_time_ms"


@admin.register(DocumentRegistry)
class DocumentRegistryAdmin(admin.ModelAdmin):
    list_display = (
        'title_snippet',
        'doi',
        'arxiv_id',
        'primary_source',
        'file_size_formatted',
        'ocr_status_badge',
        'access_count_badge',
        'last_accessed_at',
    )
    search_fields = ('title', 'doi', 'arxiv_id', 'sha256_hash', 'canonical_pdf_path')
    list_filter = ('primary_source', 'ocr_provider', 'first_ingested_at', 'last_accessed_at')
    readonly_fields = ('id', 'sha256_hash', 'first_ingested_at', 'last_accessed_at', 'access_count')

    def title_snippet(self, obj):
        return obj.title[:60] + "..." if len(obj.title) > 60 else obj.title
    title_snippet.short_description = "Title"

    def file_size_formatted(self, obj):
        kb = obj.pdf_file_size_bytes / 1024
        if kb > 1024:
            return f"{kb / 1024:.2f} MB"
        return f"{kb:.1f} KB"
    file_size_formatted.short_description = "PDF Size"

    def ocr_status_badge(self, obj):
        if obj.canonical_ocr_md_path:
            return render_badge(obj.ocr_provider or "OCR OK", "#198754")
        return format_html('<span style="color: #6c757d; font-size: 11px; white-space: nowrap;">No OCR</span>')
    ocr_status_badge.short_description = "OCR Layout"

    def access_count_badge(self, obj):
        color = "#17a2b8" if obj.access_count > 1 else "#6c757d"
        return render_badge(f"⚡ {obj.access_count} hits", color)
    access_count_badge.short_description = "Reused"


# Customize Admin Portal Branding Header & Titles
admin.site.site_header = "Schwarz Research Intelligence Admin"
admin.site.site_title = "Schwarz Research Intelligence Admin"
admin.site.index_title = mark_safe(
    'Schwarz Research Intelligence Management Portal &nbsp;&nbsp;'
    '<a href="/admin/storage-browser/" style="display: inline-block; background-color: #0d6efd; color: white !important; padding: 4px 10px; border-radius: 4px; font-weight: bold; text-decoration: none; font-size: 13px; line-height: 1.2; white-space: nowrap; vertical-align: middle;">📂 S3 Storage Browser</a>'
)

from research_intelligence.admin_views.storage_browser import storage_browser_view

_original_admin_get_urls = admin.site.get_urls

def get_admin_urls():
    from django.urls import path
    custom_urls = [
        path('storage-browser/', admin.site.admin_view(storage_browser_view), name='storage-browser'),
    ]
    return custom_urls + _original_admin_get_urls()

admin.site.get_urls = get_admin_urls


