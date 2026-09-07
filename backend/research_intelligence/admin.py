import json
from decimal import Decimal
from django import forms
from django.db import models
from django.db.models import Q
from django.contrib import admin
from django.utils.html import format_html, escape
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
    LLMUsageRecord,
    ResearchAgentProcess,
    WorkflowSchedule,
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


class PrettyPythonCodeWidget(forms.Textarea):
    """
    Interactive Python code viewer and editor widget for Django Admin with dark theme styling,
    syntax highlighting, copy support, and live code preview.
    """
    def render(self, name, value, attrs=None, renderer=None):
        raw_code = value if value is not None else ""
        attrs = attrs or {}
        attrs['style'] = "width: 100%; min-height: 240px; font-family: 'Fira Code', 'SFMono-Regular', Consolas, Menlo, monospace; font-size: 13px; line-height: 1.5; background-color: #0d1117; color: #e6edf3; padding: 12px; border-radius: 6px; border: 1px solid #30363d; tab-size: 4;"
        textarea_html = super().render(name, raw_code, attrs, renderer)
        widget_id = attrs.get('id', f'python_widget_{name}')

        js_helpers = """
        <script>
        if (typeof window.syntaxHighlightPython !== 'function') {
            window.syntaxHighlightPython = function(code) {
                if (typeof code !== 'string') code = String(code);
                var escaped = code.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
                var lines = escaped.split('\\n');
                var highlightedLines = lines.map(function(line) {
                    var commentIdx = line.indexOf('#');
                    var codePart = commentIdx !== -1 ? line.substring(0, commentIdx) : line;
                    var commentPart = commentIdx !== -1 ? line.substring(commentIdx) : '';

                    // Highlight strings
                    codePart = codePart.replace(/(["'])(?:(?=(\\\\?))\\2.)*?\\1/g, '<span style="color: #a5d6ff;">$&</span>');

                    // Highlight keywords
                    var keywords = ['def', 'return', 'if', 'elif', 'else', 'for', 'while', 'in', 'and', 'or', 'not', 'is', 'None', 'True', 'False', 'class', 'try', 'except', 'with', 'as', 'pass', 'break', 'continue', 'lambda'];
                    var kwRegex = new RegExp('\\\\b(' + keywords.join('|') + ')\\\\b', 'g');
                    codePart = codePart.replace(kwRegex, '<span style="color: #ff7b72; font-weight: 600;">$1</span>');

                    // Highlight builtins and math
                    var builtins = ['min', 'max', 'abs', 'round', 'sum', 'pow', 'len', 'int', 'float', 'str', 'math', 'sqrt', 'log', 'exp'];
                    var biRegex = new RegExp('\\\\b(' + builtins.join('|') + ')\\\\b', 'g');
                    codePart = codePart.replace(biRegex, '<span style="color: #d2a8ff; font-weight: 500;">$1</span>');

                    // Highlight paper metrics & extraction variables
                    var vars = ['fit_score', 'novelty_score', 'trl_level', 'rigour_score', 'commercial_viability', 'score', 'base', 'multiplier'];
                    var varRegex = new RegExp('\\\\b(' + vars.join('|') + ')\\\\b', 'g');
                    codePart = codePart.replace(varRegex, '<span style="color: #7ee787;">$1</span>');

                    // Highlight numbers
                    codePart = codePart.replace(/\\b(\\d+(?:\\.\\d+)?)\\b/g, '<span style="color: #79c0ff; font-weight: 500;">$1</span>');

                    // Comment part in green/grey italic
                    if (commentPart) {
                        commentPart = '<span style="color: #8b949e; font-style: italic;">' + commentPart + '</span>';
                    }

                    return codePart + commentPart;
                });
                return highlightedLines.join('\\n');
            };
            window.togglePythonView = function(widgetId) {
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
            window.copyPythonCode = function(widgetId) {
                var rawEl = document.getElementById(widgetId);
                if (rawEl) {
                    navigator.clipboard.writeText(rawEl.value).then(function() {
                        alert('Python code copied to clipboard!');
                    });
                }
            };
        }
        </script>
        """

        html = f"""
        {js_helpers}
        <div class="pretty-python-container" style="margin: 8px 0; width: 100%; max-width: 950px;">
            <div style="margin-bottom: 8px; display: flex; gap: 8px; align-items: center; flex-wrap: wrap;">
                <button type="button" class="button" onclick="togglePythonView('{widget_id}')" style="padding: 5px 12px; font-size: 11px; cursor: pointer; background: #0d6efd; color: white; border: none; border-radius: 4px;">⇄ Switch View (Editor / Highlighted Code)</button>
                <button type="button" class="button" onclick="copyPythonCode('{widget_id}')" style="padding: 5px 12px; font-size: 11px; cursor: pointer; background: #495057; color: white; border: none; border-radius: 4px;">📋 Copy Python Code</button>
                <span style="font-size: 11px; color: #8b949e; font-family: monospace;">🐍 Python AST Sandboxed</span>
            </div>
            <div id="{widget_id}_raw" style="display: block;">
                {textarea_html}
            </div>
            <pre id="{widget_id}_pretty" style="display: none; background: #0d1117; color: #c9d1d9; padding: 14px; border-radius: 8px; border: 1px solid #30363d; font-family: 'Fira Code', 'SFMono-Regular', Consolas, Menlo, monospace; font-size: 13px; line-height: 1.5; max-height: 500px; overflow: auto; margin: 0; white-space: pre-wrap; word-break: break-word;"></pre>
        </div>
        <script>
        (function() {{
            var rawEl = document.getElementById('{widget_id}');
            var prettyEl = document.getElementById('{widget_id}_pretty');
            if (rawEl && prettyEl) {{
                function syncHighlight() {{
                    prettyEl.innerHTML = window.syntaxHighlightPython(rawEl.value);
                }}
                rawEl.addEventListener('input', syncHighlight);
                syncHighlight();
            }}
        }})();
        </script>
        """
        return mark_safe(html)


class SignalScoreCodeWidget(PrettyPythonCodeWidget):
    """
    Advanced interactive Python code editor widget for Signal Score calculations in WorkspaceAdmin.
    Features:
      - Automatic deduction and visual presentation of all available workspace variables
        (Extraction Definitions, Exit Metrics, Postprocessed values, Schema properties, Screening metrics).
      - Interactive click-to-insert chips at editor cursor position with visual pulse feedback.
      - Real-time client-side variable linter checking referenced variables against available signals.
      - Interactive 'Test & Validate Formula' button performing safe AST dry-run execution with mock variables.
      - Dynamic synchronization with ExtractionDefinitionInline formsets on the same admin change page.
      - Detailed expandable schema and variable reference table.
    """
    def __init__(self, attrs=None, available_variables=None, workspace=None):
        super().__init__(attrs=attrs)
        self.available_variables = available_variables or []
        self.workspace = workspace

    def render(self, name, value, attrs=None, renderer=None):
        from research_intelligence.models.workspace import get_default_signal_variables

        raw_code = value if value is not None else ""
        attrs = attrs or {}
        widget_id = attrs.get('id', f'signal_widget_{name}')

        # Deduce variables if not provided
        if not self.available_variables and self.workspace:
            self.available_variables = self.workspace.get_available_signal_variables()
        elif not self.available_variables:
            self.available_variables = get_default_signal_variables()

        # Resolve test endpoint URL
        if self.workspace and getattr(self.workspace, 'pk', None):
            try:
                test_url = reverse('admin:research_intelligence_workspace_test_signal_score', args=[str(self.workspace.pk)])
            except Exception:
                test_url = f"/admin/research_intelligence/workspace/{self.workspace.pk}/test-signal-score/"
        else:
            try:
                test_url = reverse('admin:research_intelligence_workspace_test_signal_score_generic')
            except Exception:
                test_url = "/admin/research_intelligence/workspace/test-signal-score/"

        category_meta = {
            "Screening Exit Metric": {
                "icon": "🎯",
                "bg": "rgba(9, 105, 218, 0.15)",
                "border": "#388bfd",
                "color": "#58a6ff",
                "order": 1,
            },
            "Extraction Definition": {
                "icon": "🔬",
                "bg": "rgba(35, 134, 54, 0.15)",
                "border": "#2ea043",
                "color": "#3fb950",
                "order": 2,
            },
            "Exit Metric": {
                "icon": "⚡",
                "bg": "rgba(137, 87, 229, 0.15)",
                "border": "#8957e5",
                "color": "#d2a8ff",
                "order": 3,
            },
            "Postprocessed Metric": {
                "icon": "🪄",
                "bg": "rgba(187, 128, 9, 0.15)",
                "border": "#bb8009",
                "color": "#e3b341",
                "order": 4,
            },
            "Schema Property": {
                "icon": "📋",
                "bg": "rgba(57, 197, 207, 0.15)",
                "border": "#39c5cf",
                "color": "#56d4dd",
                "order": 5,
            },
            "Runtime Metric": {
                "icon": "📈",
                "bg": "rgba(219, 39, 119, 0.15)",
                "border": "#db2777",
                "color": "#f472b6",
                "order": 6,
            },
        }

        math_builtins = [
            ("round(score, 2)", "Round score to 2 decimal places"),
            ("min(a, b)", "Minimum of two values"),
            ("max(a, b)", "Maximum of two values"),
            ("abs(x)", "Absolute value of x"),
            ("sum(iterable)", "Sum of elements"),
            ("math.sqrt(x)", "Square root of x"),
            ("math.log(x)", "Natural logarithm of x"),
            ("math.exp(x)", "Exponential of x"),
            ("math.pow(x, y)", "x to power y"),
        ]

        grouped_vars = {}
        for v in self.available_variables:
            cat = v.get("category", "Other Metric")
            grouped_vars.setdefault(cat, []).append(v)

        sorted_categories = sorted(
            grouped_vars.keys(),
            key=lambda c: category_meta.get(c, {}).get("order", 99)
        )

        chips_html_parts = []
        table_rows_parts = []

        for cat in sorted_categories:
            cat_info = category_meta.get(cat, {"icon": "📌", "bg": "rgba(110, 118, 129, 0.15)", "border": "#6e7681", "color": "#c9d1d9"})
            cat_icon = cat_info["icon"]
            cat_bg = cat_info["bg"]
            cat_border = cat_info["border"]
            cat_color = cat_info["color"]
            v_list = grouped_vars[cat]
            chips_for_cat = []
            for v in v_list:
                v_name = v["name"]
                v_type = v.get("type", "float")
                v_desc = v.get("description", "")
                v_default = v.get("default", "0.0")
                v_source = v.get("source", "")
                tooltip = f"{v_source} • Default: {v_default}"
                if v_desc:
                    tooltip += f" — {v_desc}"

                chip = (
                    f'<span class="sri-var-chip" data-var="{escape(v_name)}" '
                    f'onclick="window.insertSignalVar(\'{widget_id}\', \'{escape(v_name)}\', this)" '
                    f'title="{escape(tooltip)}" '
                    f'style="cursor: pointer; display: inline-flex; align-items: center; gap: 5px; '
                    f'padding: 4px 10px; border-radius: 6px; font-family: \'SFMono-Regular\', Consolas, Menlo, monospace; '
                    f'font-size: 12px; font-weight: 600; margin: 3px; background: {cat_bg}; '
                    f'border: 1px solid {cat_border}; color: {cat_color}; '
                    f'user-select: none; transition: transform 0.1s, filter 0.15s;" '
                    f'onmouseover="this.style.filter=\'brightness(1.3)\'; this.style.transform=\'scale(1.03)\'" '
                    f'onmouseout="this.style.filter=\'brightness(1)\'; this.style.transform=\'scale(1)\'">'
                    f'<code>{escape(v_name)}</code>'
                    f'<small style="font-size: 10px; font-weight: normal; opacity: 0.85;">({escape(v_type)})</small>'
                    f'</span>'
                )
                chips_for_cat.append(chip)

                row = (
                    f'<tr style="border-bottom: 1px solid #21262d;">'
                    f'<td style="padding: 7px 10px; font-family: monospace; font-weight: bold; color: {cat_color};">{escape(v_name)}</td>'
                    f'<td style="padding: 7px 10px;"><span style="background: {cat_bg}; border: 1px solid {cat_border}; color: {cat_color}; padding: 2px 7px; border-radius: 4px; font-size: 11px; font-weight: 600;">{cat_icon} {escape(cat)}</span></td>'
                    f'<td style="padding: 7px 10px; color: #8b949e;">{escape(v_source)}</td>'
                    f'<td style="padding: 7px 10px; color: #79c0ff; font-family: monospace;">{escape(v_type)} ({escape(str(v_default))})</td>'
                    f'<td style="padding: 7px 10px; color: #c9d1d9;">{escape(v_desc)}</td>'
                    f'<td style="padding: 7px 10px; text-align: center;">'
                    f'<button type="button" class="button" onclick="window.insertSignalVar(\'{widget_id}\', \'{escape(v_name)}\', null)" style="padding: 3px 9px; font-size: 11px; cursor: pointer; background: #238636; color: white; border: none; border-radius: 4px;">Insert</button>'
                    f'</td>'
                    f'</tr>'
                )
                table_rows_parts.append(row)

            chips_html_parts.append(
                f'<div class="sri-var-category-block" style="margin-bottom: 8px;">'
                f'<div style="font-size: 11px; font-weight: 600; color: #8b949e; margin-bottom: 4px; display: flex; align-items: center; gap: 5px;">'
                f'<span>{cat_icon}</span> <span>{escape(cat)} ({len(v_list)}):</span>'
                f'</div>'
                f'<div style="display: flex; flex-wrap: wrap; align-items: center;">{"".join(chips_for_cat)}</div>'
                f'</div>'
            )

        # Math builtins chips
        math_chips = []
        for fn_name, fn_desc in math_builtins:
            math_chips.append(
                f'<span class="sri-var-chip" data-var="{escape(fn_name)}" '
                f'onclick="window.insertSignalVar(\'{widget_id}\', \'{escape(fn_name)}\', this)" '
                f'title="{escape(fn_desc)} • Click to insert" '
                f'style="cursor: pointer; display: inline-flex; align-items: center; padding: 3px 9px; '
                f'border-radius: 6px; font-family: monospace; font-size: 11px; margin: 3px; '
                f'background: #21262d; border: 1px solid #30363d; color: #c9d1d9; '
                f'transition: all 0.15s ease-in-out;" onmouseover="this.style.filter=\'brightness(1.25)\'" onmouseout="this.style.filter=\'brightness(1)\'">'
                f'<code>{escape(fn_name)}</code>'
                f'</span>'
            )
        chips_html_parts.append(
            f'<div class="sri-var-category-block" style="margin-bottom: 4px;">'
            f'<div style="font-size: 11px; font-weight: 600; color: #8b949e; margin-bottom: 4px; display: flex; align-items: center; gap: 5px;">'
            f'<span>🐍</span> <span>Safe Math & Builtins:</span>'
            f'</div>'
            f'<div style="display: flex; flex-wrap: wrap; align-items: center;">{"".join(math_chips)}</div>'
            f'</div>'
        )

        vars_json = json.dumps(self.available_variables, ensure_ascii=False)
        attrs['style'] = "width: 100%; min-height: 250px; font-family: 'Fira Code', 'SFMono-Regular', Consolas, Menlo, monospace; font-size: 13px; line-height: 1.5; background-color: #0d1117; color: #e6edf3; padding: 12px; border-radius: 6px; border: 1px solid #30363d; tab-size: 4;"
        textarea_html = forms.Textarea.render(self, name, raw_code, attrs, renderer)

        html = f"""
        <div class="pretty-python-container" style="margin: 8px 0; width: 100%; max-width: 950px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;">
            <!-- 1. Variables Explorer Panel -->
            <div id="{widget_id}_vars_panel" style="background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 14px; margin-bottom: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.15);">
                <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 10px; margin-bottom: 10px;">
                    <div style="display: flex; align-items: center; gap: 8px;">
                        <span style="font-size: 16px;">🧩</span>
                        <strong style="color: #f0f6fc; font-size: 13px; letter-spacing: 0.2px;">Available Variables & Signals for this Workspace</strong>
                        <span id="{widget_id}_count_badge" style="background: #238636; color: #ffffff; font-size: 11px; padding: 2px 9px; border-radius: 12px; font-weight: 600;">{len(self.available_variables)} Signals Configured</span>
                    </div>
                    <div style="display: flex; align-items: center; gap: 8px;">
                        <input type="text" id="{widget_id}_filter_input" placeholder="🔍 Filter signals..." oninput="window.filterSignalVars('{widget_id}', this.value)" style="background: #0d1117; border: 1px solid #30363d; color: #e6edf3; border-radius: 6px; padding: 5px 10px; font-size: 11px; width: 160px; outline: none;">
                        <button type="button" class="button" onclick="window.toggleSignalVarsTable('{widget_id}')" style="background: #21262d; border: 1px solid #30363d; color: #c9d1d9; border-radius: 6px; padding: 5px 12px; font-size: 11px; cursor: pointer; transition: background 0.2s;">📋 View Schema Table</button>
                    </div>
                </div>
                <div style="font-size: 11px; color: #8b949e; line-height: 1.5; margin-bottom: 12px; border-bottom: 1px solid #21262d; padding-bottom: 8px;">
                    💡 <strong>Quick Click-to-Insert:</strong> Click any variable chip below to insert it at your cursor position in the code editor. Defaults are automatically injected as <code>0.0</code> if an extraction fails or is pending.
                </div>
                <div id="{widget_id}_chips_box">
                    {"".join(chips_html_parts)}
                </div>

                <!-- Expandable Detailed Schema Table -->
                <div id="{widget_id}_table_drawer" style="display: none; margin-top: 12px; border-top: 1px solid #30363d; padding-top: 10px; max-height: 380px; overflow-y: auto;">
                    <table style="width: 100%; border-collapse: collapse; font-size: 11px; color: #c9d1d9;">
                        <thead>
                            <tr style="border-bottom: 2px solid #30363d; color: #8b949e; text-align: left;">
                                <th style="padding: 6px 8px;">Variable Name</th>
                                <th style="padding: 6px 8px;">Category</th>
                                <th style="padding: 6px 8px;">Origin / Source</th>
                                <th style="padding: 6px 8px;">Type & Default</th>
                                <th style="padding: 6px 8px;">Description</th>
                                <th style="padding: 6px 8px; text-align: center;">Action</th>
                            </tr>
                        </thead>
                        <tbody>
                            {"".join(table_rows_parts)}
                        </tbody>
                    </table>
                </div>
            </div>

            <!-- 2. Real-time Code Linter & Safety Validator Banner -->
            <div id="{widget_id}_linter_box" style="margin-bottom: 10px; padding: 9px 14px; border-radius: 6px; font-size: 12px; border: 1px solid #30363d; background: #0d1117; display: flex; align-items: center; justify-content: space-between; transition: all 0.2s;">
                <div id="{widget_id}_linter_msg" style="display: flex; align-items: center; gap: 8px; color: #8b949e;">
                    <span>🔍</span>
                    <span>Ready to evaluate custom signal score formula...</span>
                </div>
                <div id="{widget_id}_linter_status_badge" style="font-size: 11px; font-family: monospace; color: #8b949e;">
                    AST Sandbox Guard
                </div>
            </div>

            <!-- 3. Toolbar -->
            <div style="margin-bottom: 8px; display: flex; gap: 8px; align-items: center; flex-wrap: wrap;">
                <button type="button" class="button" onclick="togglePythonView('{widget_id}')" style="padding: 5px 12px; font-size: 11px; cursor: pointer; background: #0d6efd; color: white; border: none; border-radius: 4px;">⇄ Switch View (Editor / Highlighted Code)</button>
                <button type="button" class="button" onclick="copyPythonCode('{widget_id}')" style="padding: 5px 12px; font-size: 11px; cursor: pointer; background: #495057; color: white; border: none; border-radius: 4px;">📋 Copy Python Code</button>
                <button type="button" class="button" id="{widget_id}_test_btn" onclick="window.testSignalFormula('{widget_id}', '{test_url}')" style="padding: 5px 14px; font-size: 11px; cursor: pointer; background: #238636; color: white; font-weight: 600; border: none; border-radius: 4px; box-shadow: 0 2px 6px rgba(35,134,54,0.3);">🧪 Test & Validate Formula (Dry Run)</button>
                <span style="font-size: 11px; color: #8b949e; font-family: monospace;">🐍 Python AST Sandboxed</span>
            </div>

            <!-- 4. Dry Run Sandbox Results Banner -->
            <div id="{widget_id}_test_result" style="display: none; margin-bottom: 10px; border-radius: 6px; overflow: hidden; transition: all 0.2s;"></div>

            <!-- 5. Editor and Highlighted View -->
            <div id="{widget_id}_raw" style="display: block;">
                {textarea_html}
            </div>
            <pre id="{widget_id}_pretty" style="display: none; background: #0d1117; color: #c9d1d9; padding: 14px; border-radius: 8px; border: 1px solid #30363d; font-family: 'Fira Code', 'SFMono-Regular', Consolas, Menlo, monospace; font-size: 13px; line-height: 1.5; max-height: 500px; overflow: auto; margin: 0; white-space: pre-wrap; word-break: break-word;"></pre>
        </div>

        <script>
        (function() {{
            var varsData = {vars_json};
            var availableVarsMap = {{}};
            for (var i = 0; i < varsData.length; i++) {{
                availableVarsMap[varsData[i].name] = varsData[i];
            }}

            if (typeof window.insertSignalVar !== 'function') {{
                window.insertSignalVar = function(widgetId, snippet, chipEl) {{
                    var rawEl = document.getElementById(widgetId);
                    if (!rawEl) return;
                    var start = rawEl.selectionStart || 0;
                    var end = rawEl.selectionEnd || 0;
                    var val = rawEl.value;
                    rawEl.value = val.substring(0, start) + snippet + val.substring(end);
                    rawEl.selectionStart = rawEl.selectionEnd = start + snippet.length;
                    rawEl.focus();
                    rawEl.dispatchEvent(new Event('input'));

                    if (chipEl) {{
                        var origBg = chipEl.style.background;
                        var origBorder = chipEl.style.borderColor;
                        chipEl.style.background = '#238636';
                        chipEl.style.borderColor = '#3fb950';
                        chipEl.style.color = '#ffffff';
                        chipEl.style.transform = 'scale(1.1)';
                        setTimeout(function() {{
                            chipEl.style.background = origBg;
                            chipEl.style.borderColor = origBorder;
                            chipEl.style.color = '';
                            chipEl.style.transform = 'scale(1)';
                        }}, 300);
                    }}
                }};

                window.filterSignalVars = function(widgetId, query) {{
                    query = (query || '').toLowerCase().trim();
                    var panel = document.getElementById(widgetId + '_vars_panel');
                    if (!panel) return;
                    var chips = panel.querySelectorAll('.sri-var-chip');
                    for (var i = 0; i < chips.length; i++) {{
                        var c = chips[i];
                        var v = (c.getAttribute('data-var') || '').toLowerCase();
                        var text = (c.innerText || '').toLowerCase();
                        if (!query || v.indexOf(query) !== -1 || text.indexOf(query) !== -1) {{
                            c.style.display = 'inline-flex';
                        }} else {{
                            c.style.display = 'none';
                        }}
                    }}
                }};

                window.toggleSignalVarsTable = function(widgetId) {{
                    var drawer = document.getElementById(widgetId + '_table_drawer');
                    if (drawer) {{
                        drawer.style.display = drawer.style.display === 'none' ? 'block' : 'none';
                    }}
                }};

                window.testSignalFormula = function(widgetId, testUrl) {{
                    var rawEl = document.getElementById(widgetId);
                    var resultBox = document.getElementById(widgetId + '_test_result');
                    var btn = document.getElementById(widgetId + '_test_btn');
                    if (!rawEl || !resultBox) return;

                    var code = (rawEl.value || '').trim();
                    if (!code) {{
                        alert('Please enter a Python snippet to test.');
                        return;
                    }}

                    if (btn) {{
                        btn.disabled = true;
                        btn.innerHTML = '⏳ Executing in Sandbox...';
                    }}

                    resultBox.style.display = 'block';
                    resultBox.innerHTML = '<div style="background: #161b22; border: 1px solid #30363d; padding: 12px; border-radius: 6px; color: #8b949e; font-family: monospace; font-size: 12px;">⏳ Running formula securely in AST Python Sandbox with mock parameters...</div>';

                    var csrfToken = '';
                    var csrfEl = document.querySelector('input[name="csrfmiddlewaretoken"]');
                    if (csrfEl) csrfToken = csrfEl.value;

                    fetch(testUrl, {{
                        method: 'POST',
                        headers: {{
                            'Content-Type': 'application/json',
                            'X-CSRFToken': csrfToken
                        }},
                        body: JSON.stringify({{
                            code: code,
                            mock_variables: {{}}
                        }})
                    }})
                    .then(function(response) {{ return response.json(); }})
                    .then(function(data) {{
                        if (btn) {{
                            btn.disabled = false;
                            btn.innerHTML = '🧪 Test & Validate Formula (Dry Run)';
                        }}

                        if (data.success) {{
                            var varList = [];
                            var varsEval = data.variables_evaluated || {{}};
                            for (var k in varsEval) {{
                                varList.push('<code style="color: #79c0ff;">' + k + '</code>=' + varsEval[k]);
                            }}
                            var varsStr = varList.slice(0, 8).join(', ') + (varList.length > 8 ? ' ...' : '');

                            resultBox.innerHTML = 
                                '<div style="background: #042612; border: 1px solid #238636; border-radius: 6px; padding: 12px 14px; box-shadow: 0 4px 14px rgba(35,134,54,0.2);">' +
                                    '<div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 6px;">' +
                                        '<div style="display: flex; align-items: center; gap: 8px;">' +
                                            '<span style="font-size: 16px;">🎉</span>' +
                                            '<strong style="color: #3fb950; font-size: 13px;">SANDBOX DRY RUN PASSED: Score = ' + data.score + ' (' + data.score_type + ')</strong>' +
                                        '</div>' +
                                        '<span style="background: #238636; color: white; padding: 2px 8px; border-radius: 12px; font-size: 11px; font-weight: 600;">' + data.execution_time_ms + 'ms</span>' +
                                    '</div>' +
                                    '<div style="font-size: 11px; color: #c9d1d9; line-height: 1.4;">' +
                                        'Formula executed cleanly without syntax or security exceptions. Output score parsed as valid numeric signal.' +
                                    '</div>' +
                                    '<div style="font-size: 11px; color: #8b949e; margin-top: 6px; font-family: monospace;">' +
                                        'Tested against parameters: ' + varsStr +
                                    '</div>' +
                                '</div>';
                        }} else {{
                            var errTitle = data.error_type || 'SandboxExecutionError';
                            var lineStr = data.line_number ? ' (Line ' + data.line_number + ')' : '';
                            resultBox.innerHTML = 
                                '<div style="background: #2b1114; border: 1px solid #da3633; border-radius: 6px; padding: 12px 14px; box-shadow: 0 4px 14px rgba(218,54,51,0.2);">' +
                                    '<div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 6px;">' +
                                        '<div style="display: flex; align-items: center; gap: 8px;">' +
                                            '<span style="font-size: 16px;">❌</span>' +
                                            '<strong style="color: #f85149; font-size: 13px;">' + errTitle + lineStr + '</strong>' +
                                        '</div>' +
                                        '<span style="background: #da3633; color: white; padding: 2px 8px; border-radius: 12px; font-size: 11px; font-weight: 600;">' + data.execution_time_ms + 'ms</span>' +
                                    '</div>' +
                                    '<div style="font-size: 12px; color: #ff7b72; font-family: monospace; line-height: 1.4; margin-bottom: 6px; white-space: pre-wrap; word-break: break-word;">' +
                                        data.error +
                                    '</div>' +
                                    '<div style="font-size: 11px; color: #8b949e;">' +
                                        '💡 <em>Tip: Verify that all referenced variables match the chips above and that your formula returns a valid numeric score (e.g. <code>return round(score, 2)</code>).</em>' +
                                    '</div>' +
                                '</div>';
                        }}
                    }})
                    .catch(function(err) {{
                        if (btn) {{
                            btn.disabled = false;
                            btn.innerHTML = '🧪 Test & Validate Formula (Dry Run)';
                        }}
                        resultBox.innerHTML = '<div style="background: #2b1114; border: 1px solid #da3633; padding: 10px; border-radius: 6px; color: #f85149; font-size: 12px;">Network error while testing formula: ' + err + '</div>';
                    }});
                }};
            }}

            // Real-time Variable Linter
            function runLiveLinter() {{
                var rawEl = document.getElementById('{widget_id}');
                var linterBox = document.getElementById('{widget_id}_linter_box');
                var linterMsg = document.getElementById('{widget_id}_linter_msg');
                var linterBadge = document.getElementById('{widget_id}_linter_status_badge');
                if (!rawEl || !linterBox || !linterMsg) return;

                var code = (rawEl.value || '').trim();
                if (!code) {{
                    linterBox.style.borderColor = '#30363d';
                    linterBox.style.background = '#0d1117';
                    linterMsg.innerHTML = '<span style="color: #8b949e;">💡 Write Python code returning a numeric signal score. Use variables above (e.g. <code>return 0.6 * fit_score + 0.4 * novelty_score</code>).</span>';
                    if (linterBadge) linterBadge.innerHTML = '<span style="color: #8b949e;">AST Sandboxed</span>';
                    return;
                }}

                var pyKeywords = ['def', 'return', 'if', 'elif', 'else', 'for', 'while', 'in', 'and', 'or', 'not', 'is', 'None', 'True', 'False', 'class', 'try', 'except', 'with', 'as', 'pass', 'break', 'continue', 'lambda', 'score', 'base', 'multiplier', 'k'];
                var pyBuiltins = ['min', 'max', 'abs', 'round', 'sum', 'pow', 'len', 'int', 'float', 'str', 'bool', 'math', 'sqrt', 'log', 'exp', 'ceil', 'floor'];

                // Detect locally assigned variables
                var assigned = {{}};
                var assignRegex = /\\b([a-zA-Z_][a-zA-Z0-9_]*)\\s*(?:=|[+]=|[-]=|[*]=)/g;
                var assignMatch;
                while ((assignMatch = assignRegex.exec(code)) !== null) {{
                    assigned[assignMatch[1]] = true;
                }}

                // Find all identifiers
                var idRegex = /\\b([a-zA-Z_][a-zA-Z0-9_]*)\\b/g;
                var match;
                var usedVars = {{}};
                var unrecognizedVars = [];

                while ((match = idRegex.exec(code)) !== null) {{
                    var id = match[1];
                    if (pyKeywords.indexOf(id) !== -1 || pyBuiltins.indexOf(id) !== -1 || assigned[id]) {{
                        continue;
                    }}
                    if (availableVarsMap[id]) {{
                        usedVars[id] = true;
                    }} else {{
                        if (unrecognizedVars.indexOf(id) === -1) {{
                            unrecognizedVars.push(id);
                        }}
                    }}
                }}

                var usedKeys = Object.keys(usedVars);

                if (unrecognizedVars.length > 0) {{
                    linterBox.style.borderColor = '#d29922';
                    linterBox.style.background = 'rgba(187, 128, 9, 0.12)';
                    var unrecStr = unrecognizedVars.map(function(u) {{ return '<code>' + u + '</code>'; }}).join(', ');
                    linterMsg.innerHTML = '<span style="font-size: 15px;">⚠️</span> <span style="color: #e3b341;"><strong>Unrecognized variable:</strong> ' + unrecStr + ' is not found in extraction definitions or screening exit metrics! Verify spelling or define it below.</span>';
                    if (linterBadge) linterBadge.innerHTML = '<span style="color: #d29922; font-weight: bold;">Unmatched Signals</span>';
                }} else if (usedKeys.length > 0) {{
                    linterBox.style.borderColor = '#238636';
                    linterBox.style.background = 'rgba(35, 134, 54, 0.12)';
                    var validStr = usedKeys.map(function(k) {{ return '<code>' + k + '</code>'; }}).join(', ');
                    linterMsg.innerHTML = '<span style="font-size: 15px;">✅</span> <span style="color: #3fb950;"><strong>Valid signals referenced:</strong> ' + validStr + ' (All mapped to workspace extractions).</span>';
                    if (linterBadge) linterBadge.innerHTML = '<span style="color: #3fb950; font-weight: bold;">All Verified</span>';
                }} else {{
                    linterBox.style.borderColor = '#388bfd';
                    linterBox.style.background = 'rgba(9, 105, 218, 0.1)';
                    linterMsg.innerHTML = '<span style="font-size: 15px;">ℹ️</span> <span style="color: #58a6ff;">Code syntax ready. Click any variable above to incorporate it into your scoring formula.</span>';
                    if (linterBadge) linterBadge.innerHTML = '<span style="color: #58a6ff;">Ready</span>';
                }}
            }}

            var rawEl = document.getElementById('{widget_id}');
            var prettyEl = document.getElementById('{widget_id}_pretty');
            if (rawEl) {{
                rawEl.addEventListener('input', function() {{
                    if (prettyEl && window.syntaxHighlightPython) {{
                        prettyEl.innerHTML = window.syntaxHighlightPython(rawEl.value);
                    }}
                    runLiveLinter();
                }});
                setTimeout(runLiveLinter, 100);
            }}

            // Dynamic Inline Formset Observer
            function observeInlineExtractions() {{
                var inlineInputs = document.querySelectorAll('input[id^="id_extraction_definitions-"][id$="-name"], input[id^="id_extraction_definitions-"][id$="-exit_metrics"]');
                inlineInputs.forEach(function(inp) {{
                    inp.addEventListener('input', function() {{
                        var rawName = inp.value.trim();
                        if (rawName && rawName.length >= 2) {{
                            var clean = rawName.toLowerCase().replace(/[^a-zA-Z0-9_]/g, '_').replace(/_+/g, '_').replace(/^_+|_+$/g, '');
                            if (clean) {{
                                availableVarsMap[clean] = {{ name: clean, category: 'Inline Extraction', source: 'Inline Formset' }};
                                runLiveLinter();
                            }}
                        }}
                    }});
                }});
            }}
            setTimeout(observeInlineExtractions, 500);
        }})();
        </script>
        """
        return mark_safe(html)


class PostprocessingCodeWidget(PrettyPythonCodeWidget):
    """
    Advanced interactive Python code editor widget for Extraction postprocessing calculations in ExtractionDefinitionAdmin.
    Features:
      - Automatic deduction and visual presentation of all available extraction variables
        (Schema Properties, Exit Metrics, Paper Metadata Context, Extracted Fields Dictionaries, Safe Math Builtins).
      - Interactive click-to-insert chips at editor cursor position with visual pulse feedback.
      - Real-time client-side variable linter checking referenced variables against schema properties and scope.
      - Interactive 'Test Postprocessing Code (Dry Run)' button executing safe AST sandbox with mock fields.
      - Dynamic synchronization with the response_schema and exit_metrics fields on the same change form.
      - Detailed expandable schema and variable reference table.
    """
    def __init__(self, attrs=None, available_variables=None, extraction_definition=None):
        super().__init__(attrs=attrs)
        self.available_variables = available_variables or []
        self.extraction_definition = extraction_definition

    def render(self, name, value, attrs=None, renderer=None):
        from research_intelligence.models.extraction import get_default_postprocessing_variables

        raw_code = value if value is not None else ""
        attrs = attrs or {}
        widget_id = attrs.get('id', f'postprocess_widget_{name}')

        # Deduce variables if not provided
        if not self.available_variables and self.extraction_definition:
            self.available_variables = self.extraction_definition.get_available_postprocessing_variables()
        elif not self.available_variables:
            self.available_variables = get_default_postprocessing_variables()

        # Resolve test endpoint URL
        if self.extraction_definition and getattr(self.extraction_definition, 'pk', None):
            try:
                test_url = reverse('admin:research_intelligence_extractiondefinition_test_postprocessing', args=[str(self.extraction_definition.pk)])
            except Exception:
                test_url = f"/admin/research_intelligence/extractiondefinition/{self.extraction_definition.pk}/test-postprocessing/"
        else:
            try:
                test_url = reverse('admin:research_intelligence_extractiondefinition_test_postprocessing_generic')
            except Exception:
                test_url = "/admin/research_intelligence/extractiondefinition/test-postprocessing/"

        category_meta = {
            "Schema Property": {
                "icon": "📋",
                "bg": "rgba(57, 197, 207, 0.15)",
                "border": "#39c5cf",
                "color": "#56d4dd",
                "order": 1,
            },
            "Exit Metric": {
                "icon": "⚡",
                "bg": "rgba(137, 87, 229, 0.15)",
                "border": "#8957e5",
                "color": "#d2a8ff",
                "order": 2,
            },
            "Paper Metadata Context": {
                "icon": "📄",
                "bg": "rgba(9, 105, 218, 0.15)",
                "border": "#388bfd",
                "color": "#58a6ff",
                "order": 3,
            },
            "Extracted Fields Dictionary": {
                "icon": "📦",
                "bg": "rgba(187, 128, 9, 0.15)",
                "border": "#bb8009",
                "color": "#e3b341",
                "order": 4,
            },
        }

        math_builtins = [
            ("round(val, 2)", "Round value to 2 decimal places"),
            ("min(a, b)", "Minimum of two values"),
            ("max(a, b)", "Maximum of two values"),
            ("abs(x)", "Absolute value of x"),
            ("sum(iterable)", "Sum of elements"),
            ("len(obj)", "Length of list, dict, or string"),
            ("int(x)", "Cast to integer"),
            ("float(x)", "Cast to float"),
            ("str(x)", "Cast to string"),
            ("bool(x)", "Cast to boolean"),
            ("math.sqrt(x)", "Square root of x"),
            ("math.log(x)", "Natural logarithm of x"),
            ("math.exp(x)", "Exponential of x"),
            ("math.pow(x, y)", "x to power y"),
        ]

        grouped_vars = {}
        for v in self.available_variables:
            cat = v.get("category", "Schema Property")
            grouped_vars.setdefault(cat, []).append(v)

        sorted_categories = sorted(
            grouped_vars.keys(),
            key=lambda c: category_meta.get(c, {}).get("order", 99)
        )

        chips_html_parts = []
        table_rows_parts = []

        for cat in sorted_categories:
            cat_info = category_meta.get(cat, {"icon": "📌", "bg": "rgba(110, 118, 129, 0.15)", "border": "#6e7681", "color": "#c9d1d9"})
            cat_icon = cat_info["icon"]
            cat_bg = cat_info["bg"]
            cat_border = cat_info["border"]
            cat_color = cat_info["color"]
            v_list = grouped_vars[cat]
            chips_for_cat = []
            for v in v_list:
                v_name = v["name"]
                v_type = v.get("type", "float")
                v_desc = v.get("description", "")
                v_default = v.get("default", "0.0")
                v_source = v.get("source", "")
                tooltip = f"{v_source} • Default: {v_default}"
                if v_desc:
                    tooltip += f" — {v_desc}"

                chip = (
                    f'<span class="sri-postprocess-chip" data-var="{escape(v_name)}" '
                    f'onclick="window.insertPostprocessVar(\'{widget_id}\', \'{escape(v_name)}\', this)" '
                    f'title="{escape(tooltip)}" '
                    f'style="cursor: pointer; display: inline-flex; align-items: center; gap: 5px; '
                    f'padding: 4px 10px; border-radius: 6px; font-family: \'SFMono-Regular\', Consolas, Menlo, monospace; '
                    f'font-size: 12px; font-weight: 600; margin: 3px; background: {cat_bg}; '
                    f'border: 1px solid {cat_border}; color: {cat_color}; '
                    f'user-select: none; transition: transform 0.1s, filter 0.15s;" '
                    f'onmouseover="this.style.filter=\'brightness(1.3)\'; this.style.transform=\'scale(1.03)\'" '
                    f'onmouseout="this.style.filter=\'brightness(1)\'; this.style.transform=\'scale(1)\'">'
                    f'<code>{escape(v_name)}</code>'
                    f'<small style="font-size: 10px; font-weight: normal; opacity: 0.85;">({escape(v_type)})</small>'
                    f'</span>'
                )
                chips_for_cat.append(chip)

                row = (
                    f'<tr style="border-bottom: 1px solid #21262d;">'
                    f'<td style="padding: 7px 10px; font-family: monospace; font-weight: bold; color: {cat_color};">{escape(v_name)}</td>'
                    f'<td style="padding: 7px 10px;"><span style="background: {cat_bg}; border: 1px solid {cat_border}; color: {cat_color}; padding: 2px 7px; border-radius: 4px; font-size: 11px; font-weight: 600;">{cat_icon} {escape(cat)}</span></td>'
                    f'<td style="padding: 7px 10px; color: #8b949e;">{escape(v_source)}</td>'
                    f'<td style="padding: 7px 10px; color: #79c0ff; font-family: monospace;">{escape(v_type)} ({escape(str(v_default))})</td>'
                    f'<td style="padding: 7px 10px; color: #c9d1d9;">{escape(v_desc)}</td>'
                    f'<td style="padding: 7px 10px; text-align: center;">'
                    f'<button type="button" class="button" onclick="window.insertPostprocessVar(\'{widget_id}\', \'{escape(v_name)}\', null)" style="padding: 3px 9px; font-size: 11px; cursor: pointer; background: #238636; color: white; border: none; border-radius: 4px;">Insert</button>'
                    f'</td>'
                    f'</tr>'
                )
                table_rows_parts.append(row)

            chips_html_parts.append(
                f'<div class="sri-var-category-block" style="margin-bottom: 8px;">'
                f'<div style="font-size: 11px; font-weight: 600; color: #8b949e; margin-bottom: 4px; display: flex; align-items: center; gap: 5px;">'
                f'<span>{cat_icon}</span> <span>{escape(cat)} ({len(v_list)}):</span>'
                f'</div>'
                f'<div style="display: flex; flex-wrap: wrap; align-items: center;">{"".join(chips_for_cat)}</div>'
                f'</div>'
            )

        # Math builtins chips
        math_chips = []
        for fn_name, fn_desc in math_builtins:
            math_chips.append(
                f'<span class="sri-postprocess-chip" data-var="{escape(fn_name)}" '
                f'onclick="window.insertPostprocessVar(\'{widget_id}\', \'{escape(fn_name)}\', this)" '
                f'title="{escape(fn_desc)} • Click to insert" '
                f'style="cursor: pointer; display: inline-flex; align-items: center; padding: 3px 9px; '
                f'border-radius: 6px; font-family: monospace; font-size: 11px; margin: 3px; '
                f'background: #21262d; border: 1px solid #30363d; color: #c9d1d9; '
                f'transition: all 0.15s ease-in-out;" onmouseover="this.style.filter=\'brightness(1.25)\'" onmouseout="this.style.filter=\'brightness(1)\'">'
                f'<code>{escape(fn_name)}</code>'
                f'</span>'
            )
        chips_html_parts.append(
            f'<div class="sri-var-category-block" style="margin-bottom: 4px;">'
            f'<div style="font-size: 11px; font-weight: 600; color: #8b949e; margin-bottom: 4px; display: flex; align-items: center; gap: 5px;">'
            f'<span>🐍</span> <span>Safe Math & Builtins:</span>'
            f'</div>'
            f'<div style="display: flex; flex-wrap: wrap; align-items: center;">{"".join(math_chips)}</div>'
            f'</div>'
        )

        vars_json = json.dumps(self.available_variables, ensure_ascii=False)
        attrs['style'] = "width: 100%; min-height: 250px; font-family: 'Fira Code', 'SFMono-Regular', Consolas, Menlo, monospace; font-size: 13px; line-height: 1.5; background-color: #0d1117; color: #e6edf3; padding: 12px; border-radius: 6px; border: 1px solid #30363d; tab-size: 4;"
        textarea_html = forms.Textarea.render(self, name, raw_code, attrs, renderer)

        html = f"""
        <div class="pretty-python-container" style="margin: 8px 0; width: 100%; max-width: 950px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;">
            <!-- 1. Variables Explorer Panel -->
            <div id="{widget_id}_vars_panel" style="background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 14px; margin-bottom: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.15);">
                <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 10px; margin-bottom: 10px;">
                    <div style="display: flex; align-items: center; gap: 8px;">
                        <span style="font-size: 16px;">🧩</span>
                        <strong style="color: #f0f6fc; font-size: 13px; letter-spacing: 0.2px;">Available Variables & Context for Postprocessing</strong>
                        <span id="{widget_id}_count_badge" style="background: #238636; color: #ffffff; font-size: 11px; padding: 2px 9px; border-radius: 12px; font-weight: 600;">{len(self.available_variables)} Variables Configured</span>
                    </div>
                    <div style="display: flex; align-items: center; gap: 8px;">
                        <input type="text" id="{widget_id}_filter_input" placeholder="🔍 Filter variables..." oninput="window.filterPostprocessVars('{widget_id}', this.value)" style="background: #0d1117; border: 1px solid #30363d; color: #e6edf3; border-radius: 6px; padding: 5px 10px; font-size: 11px; width: 160px; outline: none;">
                        <button type="button" class="button" onclick="window.togglePostprocessVarsTable('{widget_id}')" style="background: #21262d; border: 1px solid #30363d; color: #c9d1d9; border-radius: 6px; padding: 5px 12px; font-size: 11px; cursor: pointer; transition: background 0.2s;">📋 View Schema Table</button>
                    </div>
                </div>
                <div style="font-size: 11px; color: #8b949e; line-height: 1.5; margin-bottom: 12px; border-bottom: 1px solid #21262d; padding-bottom: 8px;">
                    💡 <strong>Quick Click-to-Insert:</strong> Click any variable chip below to insert it at your cursor position in the code editor. Schema properties are extracted directly into local variables. You can return a single scalar or a dictionary of metrics.
                </div>
                <div id="{widget_id}_chips_box">
                    {"".join(chips_html_parts)}
                </div>

                <!-- Expandable Detailed Schema Table -->
                <div id="{widget_id}_table_drawer" style="display: none; margin-top: 12px; border-top: 1px solid #30363d; padding-top: 10px; max-height: 380px; overflow-y: auto;">
                    <table style="width: 100%; border-collapse: collapse; font-size: 11px; color: #c9d1d9;">
                        <thead>
                            <tr style="border-bottom: 2px solid #30363d; color: #8b949e; text-align: left;">
                                <th style="padding: 6px 8px;">Variable Name</th>
                                <th style="padding: 6px 8px;">Category</th>
                                <th style="padding: 6px 8px;">Origin / Source</th>
                                <th style="padding: 6px 8px;">Type & Default</th>
                                <th style="padding: 6px 8px;">Description</th>
                                <th style="padding: 6px 8px; text-align: center;">Action</th>
                            </tr>
                        </thead>
                        <tbody>
                            {"".join(table_rows_parts)}
                        </tbody>
                    </table>
                </div>
            </div>

            <!-- 2. Real-time Code Linter & Safety Validator Banner -->
            <div id="{widget_id}_linter_box" style="margin-bottom: 10px; padding: 9px 14px; border-radius: 6px; font-size: 12px; border: 1px solid #30363d; background: #0d1117; display: flex; align-items: center; justify-content: space-between; transition: all 0.2s;">
                <div id="{widget_id}_linter_msg" style="display: flex; align-items: center; gap: 8px; color: #8b949e;">
                    <span>🔍</span>
                    <span>Ready to evaluate custom postprocessing formula...</span>
                </div>
                <div id="{widget_id}_linter_status_badge" style="font-size: 11px; font-family: monospace; color: #8b949e;">
                    AST Sandbox Guard
                </div>
            </div>

            <!-- 3. Toolbar -->
            <div style="margin-bottom: 8px; display: flex; gap: 8px; align-items: center; flex-wrap: wrap;">
                <button type="button" class="button" onclick="togglePythonView('{widget_id}')" style="padding: 5px 12px; font-size: 11px; cursor: pointer; background: #0d6efd; color: white; border: none; border-radius: 4px;">⇄ Switch View (Editor / Highlighted Code)</button>
                <button type="button" class="button" onclick="copyPythonCode('{widget_id}')" style="padding: 5px 12px; font-size: 11px; cursor: pointer; background: #495057; color: white; border: none; border-radius: 4px;">📋 Copy Python Code</button>
                <button type="button" class="button" id="{widget_id}_test_btn" onclick="window.testPostprocessingCode('{widget_id}', '{test_url}')" style="padding: 5px 14px; font-size: 11px; cursor: pointer; background: #238636; color: white; font-weight: 600; border: none; border-radius: 4px; box-shadow: 0 2px 6px rgba(35,134,54,0.3);">🧪 Test Postprocessing Code (Dry Run)</button>
                <span style="font-size: 11px; color: #8b949e; font-family: monospace;">🐍 Python AST Sandboxed</span>
            </div>

            <!-- 4. Dry Run Sandbox Results Banner -->
            <div id="{widget_id}_test_result" style="display: none; margin-bottom: 10px; border-radius: 6px; overflow: hidden; transition: all 0.2s;"></div>

            <!-- 5. Editor and Highlighted View -->
            <div id="{widget_id}_raw" style="display: block;">
                {textarea_html}
            </div>
            <pre id="{widget_id}_pretty" style="display: none; background: #0d1117; color: #c9d1d9; padding: 14px; border-radius: 8px; border: 1px solid #30363d; font-family: 'Fira Code', 'SFMono-Regular', Consolas, Menlo, monospace; font-size: 13px; line-height: 1.5; max-height: 500px; overflow: auto; margin: 0; white-space: pre-wrap; word-break: break-word;"></pre>
        </div>

        <script>
        (function() {{
            var varsData = {vars_json};
            var availableVarsMap = {{}};
            for (var i = 0; i < varsData.length; i++) {{
                availableVarsMap[varsData[i].name] = varsData[i];
            }}

            if (typeof window.insertPostprocessVar !== 'function') {{
                window.insertPostprocessVar = function(widgetId, snippet, chipEl) {{
                    var rawEl = document.getElementById(widgetId);
                    if (!rawEl) return;
                    var start = rawEl.selectionStart || 0;
                    var end = rawEl.selectionEnd || 0;
                    var val = rawEl.value;
                    rawEl.value = val.substring(0, start) + snippet + val.substring(end);
                    rawEl.selectionStart = rawEl.selectionEnd = start + snippet.length;
                    rawEl.focus();
                    rawEl.dispatchEvent(new Event('input'));

                    if (chipEl) {{
                        var origBg = chipEl.style.background;
                        var origBorder = chipEl.style.borderColor;
                        chipEl.style.background = '#238636';
                        chipEl.style.borderColor = '#3fb950';
                        chipEl.style.color = '#ffffff';
                        chipEl.style.transform = 'scale(1.1)';
                        setTimeout(function() {{
                            chipEl.style.background = origBg;
                            chipEl.style.borderColor = origBorder;
                            chipEl.style.color = '';
                            chipEl.style.transform = 'scale(1)';
                        }}, 300);
                    }}
                }};

                window.filterPostprocessVars = function(widgetId, query) {{
                    query = (query || '').toLowerCase().trim();
                    var panel = document.getElementById(widgetId + '_vars_panel');
                    if (!panel) return;
                    var chips = panel.querySelectorAll('.sri-postprocess-chip');
                    for (var i = 0; i < chips.length; i++) {{
                        var c = chips[i];
                        var v = (c.getAttribute('data-var') || '').toLowerCase();
                        var text = (c.innerText || '').toLowerCase();
                        if (!query || v.indexOf(query) !== -1 || text.indexOf(query) !== -1) {{
                            c.style.display = 'inline-flex';
                        }} else {{
                            c.style.display = 'none';
                        }}
                    }}
                }};

                window.togglePostprocessVarsTable = function(widgetId) {{
                    var drawer = document.getElementById(widgetId + '_table_drawer');
                    if (drawer) {{
                        drawer.style.display = drawer.style.display === 'none' ? 'block' : 'none';
                    }}
                }};

                window.testPostprocessingCode = function(widgetId, testUrl) {{
                    var rawEl = document.getElementById(widgetId);
                    var resultBox = document.getElementById(widgetId + '_test_result');
                    var btn = document.getElementById(widgetId + '_test_btn');
                    if (!rawEl || !resultBox) return;

                    var code = (rawEl.value || '').trim();
                    if (!code) {{
                        alert('Please enter a Python snippet to test postprocessing.');
                        return;
                    }}

                    if (btn) {{
                        btn.disabled = true;
                        btn.innerHTML = '⏳ Executing in Sandbox...';
                    }}

                    resultBox.style.display = 'block';
                    resultBox.innerHTML = '<div style="background: #161b22; border: 1px solid #30363d; padding: 12px; border-radius: 6px; color: #8b949e; font-family: monospace; font-size: 12px;">⏳ Running postprocessing snippet securely in AST Sandbox with mock extracted fields...</div>';

                    var csrfToken = '';
                    var csrfEl = document.querySelector('input[name="csrfmiddlewaretoken"]');
                    if (csrfEl) csrfToken = csrfEl.value;

                    // Dynamically read schema from form if present
                    var schemaVal = null;
                    var schemaEl = document.getElementById('id_response_schema');
                    if (schemaEl && schemaEl.value) {{
                        try {{
                            schemaVal = JSON.parse(schemaEl.value);
                        }} catch (e) {{}}
                    }}

                    var exitMetricsVal = null;
                    var exitMetricsEl = document.getElementById('id_exit_metrics');
                    if (exitMetricsEl && exitMetricsEl.value) {{
                        exitMetricsVal = exitMetricsEl.value;
                    }}

                    fetch(testUrl, {{
                        method: 'POST',
                        headers: {{
                            'Content-Type': 'application/json',
                            'X-CSRFToken': csrfToken
                        }},
                        body: JSON.stringify({{
                            code: code,
                            schema: schemaVal,
                            exit_metrics: exitMetricsVal
                        }})
                    }})
                    .then(function(response) {{ return response.json(); }})
                    .then(function(data) {{
                        if (btn) {{
                            btn.disabled = false;
                            btn.innerHTML = '🧪 Test Postprocessing Code (Dry Run)';
                        }}

                        if (data.success) {{
                            var varList = [];
                            var varsEval = data.fields_evaluated || {{}};
                            for (var k in varsEval) {{
                                var valDisplay = typeof varsEval[k] === 'object' ? JSON.stringify(varsEval[k]) : varsEval[k];
                                varList.push('<code style="color: #79c0ff;">' + k + '</code>=' + valDisplay);
                            }}
                            var varsStr = varList.slice(0, 8).join(', ') + (varList.length > 8 ? ' ...' : '');

                            var resDisplay = typeof data.result === 'object' ? JSON.stringify(data.result, null, 2) : String(data.result);

                            resultBox.innerHTML = 
                                '<div style="background: #042612; border: 1px solid #238636; border-radius: 6px; padding: 12px 14px; box-shadow: 0 4px 14px rgba(35,134,54,0.2);">' +
                                    '<div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 6px;">' +
                                        '<div style="display: flex; align-items: center; gap: 8px;">' +
                                            '<span style="font-size: 16px;">🎉</span>' +
                                            '<strong style="color: #3fb950; font-size: 13px;">SANDBOX DRY RUN PASSED: Output Type = ' + data.result_type + '</strong>' +
                                        '</div>' +
                                        '<span style="background: #238636; color: white; padding: 2px 8px; border-radius: 12px; font-size: 11px; font-weight: 600;">' + data.execution_time_ms + 'ms</span>' +
                                    '</div>' +
                                    '<div style="background: #0d1117; border: 1px solid #30363d; border-radius: 4px; padding: 8px 12px; margin: 6px 0; font-family: monospace; font-size: 12px; color: #58a6ff; white-space: pre-wrap;">' +
                                        resDisplay +
                                    '</div>' +
                                    '<div style="font-size: 11px; color: #8b949e; margin-top: 6px; font-family: monospace;">' +
                                        'Fields evaluated: ' + varsStr +
                                    '</div>' +
                                '</div>';
                        }} else {{
                            var errTitle = data.error_type || 'SandboxExecutionError';
                            var lineStr = data.line_number ? ' (Line ' + data.line_number + ')' : '';
                            resultBox.innerHTML = 
                                '<div style="background: #2b1114; border: 1px solid #da3633; border-radius: 6px; padding: 12px 14px; box-shadow: 0 4px 14px rgba(218,54,51,0.2);">' +
                                    '<div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 6px;">' +
                                        '<div style="display: flex; align-items: center; gap: 8px;">' +
                                            '<span style="font-size: 16px;">❌</span>' +
                                            '<strong style="color: #f85149; font-size: 13px;">' + errTitle + lineStr + '</strong>' +
                                        '</div>' +
                                        '<span style="background: #da3633; color: white; padding: 2px 8px; border-radius: 12px; font-size: 11px; font-weight: 600;">' + (data.execution_time_ms || 0) + 'ms</span>' +
                                    '</div>' +
                                    '<div style="font-size: 12px; color: #ff7b72; font-family: monospace; line-height: 1.4; margin-bottom: 6px; white-space: pre-wrap; word-break: break-word;">' +
                                        data.error +
                                    '</div>' +
                                    '<div style="font-size: 11px; color: #8b949e;">' +
                                        '💡 <em>Tip: Return a numeric value or dictionary (e.g. <code>return round(score, 2)</code> or <code>return {{"computed": 10}}</code>).</em>' +
                                    '</div>' +
                                '</div>';
                        }}
                    }})
                    .catch(function(err) {{
                        if (btn) {{
                            btn.disabled = false;
                            btn.innerHTML = '🧪 Test Postprocessing Code (Dry Run)';
                        }}
                        resultBox.innerHTML = '<div style="background: #2b1114; border: 1px solid #da3633; padding: 10px; border-radius: 6px; color: #f85149; font-size: 12px;">Network error while testing postprocessing snippet: ' + err + '</div>';
                    }});
                }};
            }}

            // Real-time Postprocessing Variable Linter
            function runLiveLinter() {{
                var rawEl = document.getElementById('{widget_id}');
                var linterBox = document.getElementById('{widget_id}_linter_box');
                var linterMsg = document.getElementById('{widget_id}_linter_msg');
                var linterBadge = document.getElementById('{widget_id}_linter_status_badge');
                if (!rawEl || !linterBox || !linterMsg) return;

                var code = (rawEl.value || '').trim();
                if (!code) {{
                    linterBox.style.borderColor = '#30363d';
                    linterBox.style.background = '#0d1117';
                    linterMsg.innerHTML = '<span style="color: #8b949e;">💡 Write Python code postprocessing extracted fields (e.g. <code>return round(score * 1.5, 2)</code>).</span>';
                    if (linterBadge) linterBadge.innerHTML = '<span style="color: #8b949e;">AST Sandboxed</span>';
                    return;
                }}

                var pyKeywords = ['def', 'return', 'if', 'elif', 'else', 'for', 'while', 'in', 'and', 'or', 'not', 'is', 'None', 'True', 'False', 'class', 'try', 'except', 'with', 'as', 'pass', 'break', 'continue', 'lambda', 'result', 'output', 'computed', 'postprocessed', 'score', 'val', 'value', 'postprocess', 'calculate', 'compute', 'process'];
                var pyBuiltins = ['min', 'max', 'abs', 'round', 'sum', 'pow', 'len', 'int', 'float', 'str', 'bool', 'math', 'sqrt', 'log', 'exp', 'ceil', 'floor'];
                var contextVars = ['title', 'abstract', 'arxiv_id', 'doi', 'fields', 'data', 'extractions', 'fields_data', 'json_data', 'raw_data'];

                // Detect locally assigned variables
                var assigned = {{}};
                var assignRegex = /\\b([a-zA-Z_][a-zA-Z0-9_]*)\\s*(?:=|[+]=|[-]=|[*]=)/g;
                var assignMatch;
                while ((assignMatch = assignRegex.exec(code)) !== null) {{
                    assigned[assignMatch[1]] = true;
                }}

                // Find all identifiers
                var idRegex = /\\b([a-zA-Z_][a-zA-Z0-9_]*)\\b/g;
                var match;
                var usedVars = {{}};
                var unrecognizedVars = [];

                while ((match = idRegex.exec(code)) !== null) {{
                    var id = match[1];
                    if (pyKeywords.indexOf(id) !== -1 || pyBuiltins.indexOf(id) !== -1 || contextVars.indexOf(id) !== -1 || assigned[id]) {{
                        continue;
                    }}
                    if (availableVarsMap[id]) {{
                        usedVars[id] = true;
                    }} else {{
                        if (unrecognizedVars.indexOf(id) === -1) {{
                            unrecognizedVars.push(id);
                        }}
                    }}
                }}

                var usedKeys = Object.keys(usedVars);

                if (unrecognizedVars.length > 0) {{
                    linterBox.style.borderColor = '#d29922';
                    linterBox.style.background = 'rgba(187, 128, 9, 0.12)';
                    var unrecStr = unrecognizedVars.map(function(u) {{ return '<code>' + u + '</code>'; }}).join(', ');
                    linterMsg.innerHTML = '<span style="font-size: 15px;">⚠️</span> <span style="color: #e3b341;"><strong>Unrecognized variable:</strong> ' + unrecStr + ' is not found in extraction schema or context! Verify spelling or define it in schema.</span>';
                    if (linterBadge) linterBadge.innerHTML = '<span style="color: #d29922; font-weight: bold;">Unmatched Signals</span>';
                }} else if (usedKeys.length > 0) {{
                    linterBox.style.borderColor = '#238636';
                    linterBox.style.background = 'rgba(35, 134, 54, 0.12)';
                    var validStr = usedKeys.map(function(k) {{ return '<code>' + k + '</code>'; }}).join(', ');
                    linterMsg.innerHTML = '<span style="font-size: 15px;">✅</span> <span style="color: #3fb950;"><strong>Valid variables referenced:</strong> ' + validStr + ' (All mapped to schema properties).</span>';
                    if (linterBadge) linterBadge.innerHTML = '<span style="color: #3fb950; font-weight: bold;">All Verified</span>';
                }} else {{
                    linterBox.style.borderColor = '#388bfd';
                    linterBox.style.background = 'rgba(9, 105, 218, 0.1)';
                    linterMsg.innerHTML = '<span style="font-size: 15px;">ℹ️</span> <span style="color: #58a6ff;">Code syntax ready. Click any variable above to incorporate it into your postprocessing formula.</span>';
                    if (linterBadge) linterBadge.innerHTML = '<span style="color: #58a6ff;">Ready</span>';
                }}
            }}

            var rawEl = document.getElementById('{widget_id}');
            var prettyEl = document.getElementById('{widget_id}_pretty');
            if (rawEl) {{
                rawEl.addEventListener('input', function() {{
                    if (prettyEl && window.syntaxHighlightPython) {{
                        prettyEl.innerHTML = window.syntaxHighlightPython(rawEl.value);
                    }}
                    runLiveLinter();
                }});
                setTimeout(runLiveLinter, 100);
            }}

            // Dynamic Response Schema & Exit Metrics Observer
            function observeResponseSchema() {{
                var schemaEl = document.getElementById('id_response_schema');
                var exitMetricsEl = document.getElementById('id_exit_metrics');

                function syncFromSchema() {{
                    if (!schemaEl) return;
                    try {{
                        var parsed = JSON.parse(schemaEl.value);
                        if (parsed && parsed.properties && typeof parsed.properties === 'object') {{
                            var newCount = 0;
                            for (var propKey in parsed.properties) {{
                                var clean = propKey.toLowerCase().replace(/[^a-zA-Z0-9_]/g, '_').replace(/_+/g, '_').replace(/^_+|_+$/g, '');
                                if (clean && !availableVarsMap[clean]) {{
                                    var pDef = parsed.properties[propKey] || {{}};
                                    availableVarsMap[clean] = {{
                                        name: clean,
                                        category: 'Schema Property',
                                        type: pDef.type || 'any',
                                        source: 'Live Form Schema'
                                    }};
                                    newCount++;
                                }}
                            }}
                            if (newCount > 0) {{
                                runLiveLinter();
                            }}
                        }}
                    }} catch (e) {{}}
                }}

                if (schemaEl) {{
                    schemaEl.addEventListener('input', syncFromSchema);
                    schemaEl.addEventListener('change', syncFromSchema);
                }}

                if (exitMetricsEl) {{
                    exitMetricsEl.addEventListener('input', function() {{
                        var val = exitMetricsEl.value || '';
                        var parts = val.split(',');
                        for (var i = 0; i < parts.length; i++) {{
                            var clean = parts[i].trim().toLowerCase().replace(/[^a-zA-Z0-9_]/g, '_').replace(/_+/g, '_').replace(/^_+|_+$/g, '');
                            if (clean && !availableVarsMap[clean]) {{
                                availableVarsMap[clean] = {{ name: clean, category: 'Exit Metric', source: 'Live Exit Metrics' }};
                            }}
                        }}
                        runLiveLinter();
                    }});
                }}
            }}
            setTimeout(observeResponseSchema, 500);
        }})();
        </script>
        """
        return mark_safe(html)




# Helper function to render CSS badges in Django Admin
def render_badge(text, bg_color="#6c757d", text_color="#ffffff", title=None):
    title_attr = format_html(' title="{}"', title) if title else ""
    return format_html(
        '<span style="background-color: {}; color: {}; padding: 4px 8px; border-radius: 4px; font-weight: bold; font-size: 11px; white-space: nowrap; display: inline-block;"{}>{}</span>',
        bg_color,
        text_color,
        title_attr,
        text
    )


def format_human_readable_bytes(num_bytes: int) -> str:
    """
    Formats raw byte count into human-readable notation (B, KB, MB, GB, TB, PB).
    """
    if not num_bytes or num_bytes <= 0:
        return "0 B"
    nb = float(num_bytes)
    for unit in ['B', 'KB', 'MB', 'GB', 'TB', 'PB']:
        if abs(nb) < 1024.0:
            if unit == 'B':
                return f"{int(nb)} B"
            elif unit == 'KB':
                return f"{nb:.1f} KB"
            else:
                return f"{nb:.2f} {unit}"
        nb /= 1024.0
    return f"{nb:.2f} EB"



# --- Inlines for Workspace ---

class WorkspaceMemberInline(admin.TabularInline):
    model = WorkspaceMember
    extra = 1
    fields = ('user', 'role', 'created_at')
    readonly_fields = ('created_at',)


class ScraperInline(admin.TabularInline):
    model = Scraper
    extra = 1
    fields = ('provider', 'search_query', 'n_last_days', 'is_active', 'created_at')
    readonly_fields = ('created_at',)


class SubscriberInline(admin.TabularInline):
    model = Subscriber
    extra = 1
    fields = ('name', 'email', 'subscription_type', 'is_active', 'created_at')
    readonly_fields = ('created_at',)


class ExtractionDefinitionInline(admin.TabularInline):
    model = ExtractionDefinition
    extra = 0
    fields = ('name', 'exit_metrics', 'has_postprocessing', 'llm_model', 'is_active', 'created_at')
    readonly_fields = ('has_postprocessing', 'created_at')
    show_change_link = True

    @admin.display(boolean=True, description="Postprocess Code")
    def has_postprocessing(self, obj):
        return bool(obj.postprocessing_code and obj.postprocessing_code.strip())


class WorkflowScheduleInline(admin.TabularInline):
    model = WorkflowSchedule
    extra = 0
    fields = ('name', 'frequency', 'time_of_day', 'is_active', 'next_run_at', 'last_run_at')
    readonly_fields = ('next_run_at', 'last_run_at')
    show_change_link = True


# Helper function to render formatted component metrics summary
def render_component_metrics_summary(obj):
    if not obj.metrics:
        return "-"
    m = obj.metrics
    if obj.step_type == 'screening':
        total = m.get('total_screened', 0)
        passed = m.get('passed', 0)
        rejected = m.get('rejected', 0)
        withdrawn = m.get('withdrawn', 0)
        rej_color = '#6c757d' if rejected == 0 else '#dc3545'
        extras = []
        if withdrawn > 0:
            extras.append(f'<span style="color: #6c757d; font-size: 11px;">({withdrawn} withdrawn)</span>')
        extra_html = f"<br>{''.join(extras)}" if extras else ""
        return format_html(
            '<div style="line-height: 1.35; white-space: nowrap;">'
            '<strong>{} screened:</strong><br>'
            '<span style="color: #198754; font-weight: 600;">{} passed</span>,<br>'
            '<span style="color: {}; font-weight: 600;">{} rejected</span>{}'
            '</div>',
            total,
            passed,
            rej_color,
            rejected,
            format_html(extra_html) if extra_html else mark_safe(""),
        )
    elif obj.step_type == 'search':
        created = m.get('ingested_new', m.get('total_created', 0))
        fetched = m.get('total_fetched', m.get('total_found', created))
        dupes = m.get('duplicates_count', m.get('total_duplicates', m.get('total_duplicates_skipped', 0)))
        if dupes:
            return format_html(
                '<div style="line-height: 1.35; white-space: nowrap;">'
                '<strong>{} created (new)</strong> / {} fetched<br>'
                '<span style="color: #6c757d; font-size: 11px;">({} duplicates)</span>'
                '</div>',
                created,
                fetched,
                dupes,
            )
        return format_html(
            '<div style="line-height: 1.35; white-space: nowrap;">'
            '<strong>{} papers</strong> created'
            '</div>',
            created,
        )
    elif obj.step_type == 'download':
        dl = m.get('downloaded', 0)
        failed = m.get('failed', 0)
        cached = m.get('cached', m.get('from_cache', m.get('cached_hits', 0)))
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
        try:
            avg_score_str = f"{float(m.get('avg_signal_score', 0.0)):.2f}"
            max_score_str = f"{float(m.get('max_signal_score', 0.0)):.2f}"
        except Exception:
            avg_score_str = str(m.get('avg_signal_score', 0.0))
            max_score_str = str(m.get('max_signal_score', 0.0))
        return format_html(
            '<div style="line-height: 1.35; white-space: nowrap;">'
            '<strong>{}/{}</strong> scored<br>'
            '<span style="color: #0d6efd; font-weight: 600;">Avg: {}</span> (Max: {})'
            '</div>',
            scored,
            total,
            avg_score_str,
            max_score_str,
        )
    elif obj.step_type == 'extraction':
        created = m.get('extractions_created', m.get('completed_extractions', 0))
        total_items = m.get('total_work_items', 0)
        papers = m.get('total_papers', 0)
        defs = m.get('total_definitions', 0)
        pct = m.get('percent_complete')
        latest = m.get('latest_processed')
        if obj.status == 'running' and total_items > 0:
            return format_html(
                '<div style="line-height: 1.35; white-space: nowrap;">'
                '<strong>{}/{} extractions</strong> (<span style="color: #0d6efd; font-weight: 600;">{}%</span>)<br>'
                '<span style="color: #6c757d; font-size: 11px;">{}</span>'
                '</div>',
                created,
                total_items,
                pct or 0,
                latest or f"{papers} papers, {defs} defs"
            )
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
    model_name = model_name or "google/gemini-3.8-flash"

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
    fields = ('step_type_badge', 'status_badge', 'execution_time', 'cost_display', 'metrics_summary', 'celery_task_id', 'raw_storage_path', 'started_at', 'completed_at')
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
    formfield_overrides = {
        models.JSONField: {'widget': PrettyJSONWidget},
    }
    list_display = (
        'name',
        'ocr_provider',
        'screening_llm_model',
        'reasoning_effort',
        'skip_abstract_screening',
        'tokens_consumed_display',
        'usd_spent_display',
        'created_at'
    )
    search_fields = (
        'name',
        'abstract_acceptance_criteria',
        'abstract_rejection_criteria',
        'full_text_acceptance_criteria',
        'full_text_rejection_criteria'
    )
    list_filter = ('ocr_provider', 'llm_provider', 'reasoning_effort', 'skip_abstract_screening', 'reprocess_existing', 'created_at')
    inlines = [WorkspaceMemberInline, ScraperInline, ExtractionDefinitionInline, SubscriberInline, WorkflowScheduleInline]

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.annotate(
            all_time_tokens=models.Sum('runs__tokens_consumed'),
            all_time_usd=models.Sum('runs__usd_cost')
        )

    @admin.display(description="Tokens Consumed (Total / Month)", ordering="tokens_consumed_this_month")
    def tokens_consumed_display(self, obj):
        all_time = getattr(obj, 'all_time_tokens', None)
        if all_time is None:
            all_time = obj.runs.aggregate(t=models.Sum('tokens_consumed'))['t'] or 0
        all_time_int = max(int(all_time or 0), int(obj.tokens_consumed_this_month or 0))
        month_int = int(obj.tokens_consumed_this_month or 0)
        return f"{all_time_int:,} ({month_int:,} this month)"

    @admin.display(description="USD Spent (Total / Month)", ordering="usd_spent_this_month")
    def usd_spent_display(self, obj):
        all_time = getattr(obj, 'all_time_usd', None)
        if all_time is None:
            all_time = obj.runs.aggregate(u=models.Sum('usd_cost'))['u'] or Decimal("0.0000")
        all_time_dec = Decimal(str(all_time or 0))
        month_dec = Decimal(str(obj.usd_spent_this_month or 0))
        all_time_dec = max(all_time_dec, month_dec)
        return f"${all_time_dec:,.2f} (${month_dec:,.2f} this month)"

    def formfield_for_dbfield(self, db_field, **kwargs):
        if db_field.name == 'signal_score_code':
            kwargs['widget'] = SignalScoreCodeWidget
        return super().formfield_for_dbfield(db_field, **kwargs)

    def get_form(self, request, obj=None, **kwargs):
        FormClass = super().get_form(request, obj, **kwargs)
        if 'signal_score_code' in FormClass.base_fields:
            if obj:
                available_vars = obj.get_available_signal_variables()
            else:
                from research_intelligence.models.workspace import get_default_signal_variables
                available_vars = get_default_signal_variables()

            class WorkspaceAdminForm(FormClass):
                def __init__(self, *args, **kwargs_inner):
                    super().__init__(*args, **kwargs_inner)
                    if 'signal_score_code' in self.fields:
                        self.fields['signal_score_code'].widget = SignalScoreCodeWidget(
                            available_variables=available_vars,
                            workspace=obj
                        )
            return WorkspaceAdminForm
        return FormClass

    fieldsets = (

        ('Basic Information', {
            'fields': ('name', 'skip_abstract_screening', 'reprocess_existing')
        }),
        ('Engine & Provider Configuration', {
            'fields': ('ocr_provider', 'screening_llm_model', 'llm_provider', 'reasoning_effort')
        }),
        ('🎯 Abstract Screening Engine & Dynamic Prompting', {
            'fields': (
                'abstract_acceptance_criteria',
                'abstract_rejection_criteria',
                'abstract_screening_system_prompt',
                'abstract_screening_user_prompt_template',
                'abstract_screening_response_schema',
                'abstract_screening_exit_metric',
            ),
            'description': 'Configure criteria, system prompt, user prompt template (placeholders: <code>{title}</code>, <code>{abstract}</code>, <code>{acceptance_criteria}</code>, <code>{rejection_criteria}</code>), custom JSON schema, and exit metric for Abstract Screening. If left blank, standard defaults are used.'
        }),
        ('📄 Full-Text Screening Engine & Dynamic Prompting', {
            'fields': (
                'full_text_acceptance_criteria',
                'full_text_rejection_criteria',
                'full_text_screening_system_prompt',
                'full_text_screening_user_prompt_template',
                'full_text_screening_response_schema',
                'full_text_screening_exit_metric',
            ),
            'description': 'Configure criteria, system prompt, user prompt template (placeholders: <code>{title}</code>, <code>{abstract}</code>, <code>{full_text}</code>, <code>{acceptance_criteria}</code>, <code>{rejection_criteria}</code>), custom JSON schema, and exit metric for Full-Text Screening. If left blank, standard defaults are used.'
        }),
        ('⚙️ Signal Score Configuration', {
            'fields': ('signal_score_code',),
            'description': 'Custom Python snippet evaluated on paper extracted parameters (e.g. <code>k = fit_score + 2*novelty_score; return 5 if k > 10 else 99</code>). All available variables deduced from Extraction Definitions and Screening Stages are displayed below with click-to-insert, live linter, and real-time dry-run sandbox testing.'
        }),
        ('📊 Executive Briefing & Narrative Report Prompting', {
            'fields': (
                'narrative_report_top_n_papers',
                'narrative_report_system_prompt',
                'narrative_report_prompt',
            ),
            'description': 'Configure executive briefing generation for Step 7. When <code>narrative_report_prompt</code> is provided, an LLM synthesizes an executive briefing based on the top N accepted papers ranked by signal score. Placeholders available in prompt: <code>{papers}</code> (formatted catalog), <code>{papers_json}</code> (structured JSON list), <code>{score_vectors_summary}</code>, <code>{workspace_name}</code>, <code>{run_date}</code>, <code>{run_id}</code>, <code>{total_papers}</code>, <code>{accepted_papers_count}</code>, <code>{rejected_papers_count}</code>, <code>{avg_signal_score}</code>, <code>{top_n_papers_count}</code>. If prompt is blank, a standard deterministic summary is generated.'
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

    change_list_template = 'admin/research_intelligence/workspace/change_list.html'
    actions = ['launch_agent_standard', 'launch_agent_reprocess', 'export_configuration', 'import_configuration_action']

    @admin.action(description="📦 Export Workspace Configuration (JSON)")
    def export_configuration(self, request, queryset):
        import json
        from django.http import HttpResponse
        from django.utils.timezone import now
        from django.utils.text import slugify
        from research_intelligence.services.workspace_service import serialize_workspace_configuration

        workspaces_data = [serialize_workspace_configuration(ws) for ws in queryset]
        export_payload = {
            "version": "1.0",
            "exported_at": now().isoformat(),
            "workspaces_count": len(workspaces_data),
            "workspaces": workspaces_data,
        }

        if len(workspaces_data) == 1:
            filename = f"workspace_{slugify(workspaces_data[0]['name'])}_{now().strftime('%Y%m%d_%H%M%S')}.json"
        else:
            filename = f"workspaces_export_{len(workspaces_data)}_items_{now().strftime('%Y%m%d_%H%M%S')}.json"

        response = HttpResponse(
            json.dumps(export_payload, indent=2, ensure_ascii=False),
            content_type="application/json; charset=utf-8"
        )
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response

    @admin.action(description="📥 Import Configuration (JSON File / Paste)")
    def import_configuration_action(self, request, queryset):
        from django.http import HttpResponseRedirect
        from django.urls import reverse
        return HttpResponseRedirect(reverse('admin:workspace-import-configuration'))

    def get_urls(self):
        from django.urls import path
        urls = super().get_urls()
        custom_urls = [
            path(
                '<path:object_id>/test-signal-score/',
                self.admin_site.admin_view(self.test_signal_score_view),
                name='research_intelligence_workspace_test_signal_score'
            ),
            path(
                'test-signal-score/',
                self.admin_site.admin_view(self.test_signal_score_view),
                name='research_intelligence_workspace_test_signal_score_generic'
            ),
            path(
                'import-configuration/',
                self.admin_site.admin_view(self.import_configuration_view),
                name='workspace-import-configuration'
            ),
            path(
                'import-configuration/',
                self.admin_site.admin_view(self.import_configuration_view),
                name='research_intelligence_workspace_import_configuration'
            ),
        ]
        return custom_urls + urls

    def test_signal_score_view(self, request, object_id=None):
        """
        AJAX endpoint allowing admins to execute a dry-run test of the signal score Python formula
        within the AST-restricted sandbox using deduced or mocked variables.
        """
        import json
        import time
        from django.http import JsonResponse
        from research_intelligence.utils.sandbox import execute_sandboxed_snippet, SandboxSecurityError, SandboxExecutionError
        from research_intelligence.models.workspace import get_default_signal_variables

        if request.method != 'POST':
            return JsonResponse({'success': False, 'error': 'POST request required for testing signal score formulas.'}, status=405)

        try:
            payload = json.loads(request.body.decode('utf-8'))
        except Exception:
            payload = request.POST

        code = payload.get('code', '').strip()
        if not code:
            return JsonResponse({
                'success': False,
                'error_type': 'EmptyCodeError',
                'error': 'No Python code snippet was provided for evaluation.',
                'execution_time_ms': 0
            })

        workspace = None
        if object_id:
            try:
                workspace = self.get_object(request, object_id)
            except Exception:
                workspace = None

        if workspace:
            available_vars = workspace.get_available_signal_variables()
        else:
            available_vars = get_default_signal_variables()

        # Build mocked test evaluation context
        test_context_vars = {}
        for var_meta in available_vars:
            v_name = var_meta.get('name')
            if not v_name or not v_name.isidentifier() or v_name.startswith('_'):
                continue
            example_val = var_meta.get('default') if var_meta.get('default') is not None else var_meta.get('example_value')
            if example_val is not None:
                test_context_vars[v_name] = example_val
            else:
                v_type = (var_meta.get('type') or 'float').lower()
                if 'int' in v_type:
                    test_context_vars[v_name] = 3
                elif 'bool' in v_type:
                    test_context_vars[v_name] = True
                elif 'list' in v_type or 'array' in v_type:
                    test_context_vars[v_name] = ["sample_1", "sample_2"]
                elif 'dict' in v_type or 'object' in v_type:
                    test_context_vars[v_name] = {"score": 0.85, "label": "high"}
                else:
                    test_context_vars[v_name] = 0.85

        # Guaranteed default signals if not already present
        if 'fit_score' not in test_context_vars:
            test_context_vars['fit_score'] = 0.85
        if 'novelty_score' not in test_context_vars:
            test_context_vars['novelty_score'] = 0.75

        # Allow user overrides from payload if provided
        custom_mock = payload.get('mock_variables')
        if isinstance(custom_mock, dict):
            test_context_vars.update(custom_mock)

        t0 = time.perf_counter()
        try:
            result = execute_sandboxed_snippet(
                code_snippet=code,
                context_vars=test_context_vars,
                timeout_seconds=2.0
            )
            exec_time_ms = round((time.perf_counter() - t0) * 1000, 2)

            if result is None:
                return JsonResponse({
                    'success': False,
                    'error_type': 'NullResultWarning',
                    'error': 'The snippet executed without exceptions but returned None (or did not include a return statement). Make sure to return a number, e.g.: return round(score, 2)',
                    'execution_time_ms': exec_time_ms,
                    'variables_evaluated': {k: v for k, v in test_context_vars.items() if not k.startswith('_') and not callable(v) and k != 'math'}
                })

            try:
                numeric_score = float(result)
            except (ValueError, TypeError):
                return JsonResponse({
                    'success': False,
                    'error_type': 'NonNumericScoreError',
                    'error': f"The snippet returned a non-numeric value of type '{type(result).__name__}': {repr(result)}. Signal score must be a number (float or int).",
                    'execution_time_ms': exec_time_ms,
                    'variables_evaluated': {k: v for k, v in test_context_vars.items() if not k.startswith('_') and not callable(v) and k != 'math'}
                })

            return JsonResponse({
                'success': True,
                'score': round(numeric_score, 4),
                'score_type': type(result).__name__,
                'execution_time_ms': exec_time_ms,
                'variables_evaluated': {k: v for k, v in test_context_vars.items() if not k.startswith('_') and not callable(v) and k != 'math'}
            })

        except (SandboxSecurityError, SandboxExecutionError, Exception) as e:
            exec_time_ms = round((time.perf_counter() - t0) * 1000, 2)
            error_type = type(e).__name__
            error_msg = str(e)
            line_number = getattr(e, 'lineno', None)

            if not line_number:
                import traceback
                tb = traceback.extract_tb(e.__traceback__)
                for frame in reversed(tb):
                    if frame.filename in ('<string>', '<sandbox>'):
                        line_number = frame.lineno
                        break

            return JsonResponse({
                'success': False,
                'error_type': error_type,
                'error': error_msg or repr(e),
                'line_number': line_number,
                'execution_time_ms': exec_time_ms,
                'variables_evaluated': {k: v for k, v in test_context_vars.items() if not k.startswith('_') and not callable(v) and k != 'math'}
            })

    def import_configuration_view(self, request):
        import json
        from django.shortcuts import render, redirect
        from django.contrib import messages
        from research_intelligence.services.workspace_service import import_workspace_configuration_bundle

        if request.method == 'POST':
            raw_json = request.POST.get('raw_json', '').strip()
            uploaded_file = request.FILES.get('json_file')
            overwrite_val = request.POST.get('overwrite_existing', 'yes').strip().lower()
            update_existing = overwrite_val in ['yes', '1', 'true', 'on']

            payload_str = None
            if uploaded_file:
                try:
                    payload_str = uploaded_file.read().decode('utf-8')
                except Exception as e:
                    messages.error(request, f"Failed to read uploaded file: {str(e)}")
            elif raw_json:
                payload_str = raw_json

            if not payload_str:
                messages.error(request, "Please provide a JSON file or paste JSON content.")
                return redirect('admin:workspace-import-configuration')

            try:
                parsed_data = json.loads(payload_str)
            except Exception as e:
                messages.error(request, f"Invalid JSON syntax: {str(e)}")
                return redirect('admin:workspace-import-configuration')

            try:
                stats = import_workspace_configuration_bundle(
                    data=parsed_data,
                    user=request.user,
                    update_existing=update_existing
                )
                mode_desc = "Overwrite / Fine-tune enabled" if update_existing else "Overwrite disabled (skipped existing items)"
                messages.success(
                    request,
                    f"✅ Workspace configuration imported successfully ({mode_desc})! "
                    f"Workspaces: {stats['created_workspaces']} created, {stats['updated_workspaces']} updated, {stats.get('skipped_workspaces', 0)} skipped | "
                    f"Extraction Definitions: {stats['created_extractions']} created, {stats['updated_extractions']} updated, {stats.get('skipped_extractions', 0)} skipped | "
                    f"Scrapers: {stats['created_scrapers']} created, {stats['updated_scrapers']} updated, {stats.get('skipped_scrapers', 0)} skipped | "
                    f"Subscribers: {stats['created_subscribers']} created, {stats['updated_subscribers']} updated, {stats.get('skipped_subscribers', 0)} skipped."
                )
                return redirect('admin:research_intelligence_workspace_changelist')
            except Exception as e:
                messages.error(request, f"Import error: {str(e)}")
                return redirect('admin:workspace-import-configuration')

        context = {
            **self.admin_site.each_context(request),
            'title': 'Import Workspace Configuration',
            'opts': self.model._meta,
        }
        return render(request, 'admin/research_intelligence/workspace/import_configuration.html', context)

    @admin.action(description="🚀 Launch Autonomous Agent (Standard - Skip Duplicates)")
    def launch_agent_standard(self, request, queryset):
        from research_intelligence.tasks.orchestrator.agent_engine import tick_agent_process
        for ws in queryset:
            agent = ResearchAgentProcess.objects.create(
                workspace=ws,
                name=f"Admin Run - {ws.name}",
                status='running',
                current_step='initialized',
                configuration_override={"reprocess_existing": False}
            )
            tick_agent_process(str(agent.id))
        self.message_user(request, f"Launched standard autonomous agent for {queryset.count()} workspace(s).")

    @admin.action(description="🔄 Launch Autonomous Agent (Reprocess All Workspace Papers)")
    def launch_agent_reprocess(self, request, queryset):
        from research_intelligence.tasks.orchestrator.agent_engine import tick_agent_process
        for ws in queryset:
            agent = ResearchAgentProcess.objects.create(
                workspace=ws,
                name=f"Reprocess Run - {ws.name}",
                status='running',
                current_step='initialized',
                configuration_override={"reprocess_existing": True}
            )
            tick_agent_process(str(agent.id))
        self.message_user(request, f"Launched reprocessing agent for {queryset.count()} workspace(s).")


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
    list_display = ('workspace', 'provider_badge', 'search_query', 'n_last_days', 'status_badge', 'created_at')
    list_filter = ('provider', 'is_active', 'workspace')
    search_fields = ('workspace__name', 'search_query')
    fields = ('workspace', 'provider', 'search_query', 'limit', 'sort_by', 'sort_order', 'n_last_days', 'is_active')

    def provider_badge(self, obj):
        colors = {
            'arxiv': '#fd7e14',
            'openalex': '#0d6efd',
            'lens': '#6f42c1',
            'pubmed': '#20c997',
        }
        return render_badge(obj.get_provider_display(), colors.get(obj.provider, '#6c757d'))
    provider_badge.short_description = "Provider"

    def status_badge(self, obj):
        return render_badge("ACTIVE", "#198754") if obj.is_active else render_badge("DISABLED", "#6c757d")
    status_badge.short_description = "Status"


@admin.register(WorkflowSchedule)
class WorkflowScheduleAdmin(admin.ModelAdmin):
    formfield_overrides = {
        models.JSONField: {'widget': PrettyJSONWidget},
    }
    list_display = (
        'schedule_identity_display',
        'frequency_badge',
        'schedule_pattern_display',
        'is_active_toggle',
        'next_run_display',
        'last_run_display',
        'total_runs_display',
        'trigger_actions_column',
    )
    list_filter = ('is_active', 'frequency', 'timezone_name', 'workspace')
    search_fields = ('name', 'workspace__name', 'cron_expression')
    actions = ['trigger_now_action', 'activate_schedules_action', 'pause_schedules_action']

    fieldsets = (
        ('Schedule Target & Basic Info', {
            'fields': ('name', 'workspace', 'is_active', 'created_by')
        }),
        ('Recurrence & Timing Pattern', {
            'description': 'Configure the automated execution schedule. Supports One-Off (Run Once), Daily, Weekdays (Mon-Fri), Weekly, Monthly, Interval Hours, or Custom Cron expressions.',
            'fields': ('frequency', 'one_off_datetime', 'time_of_day', 'days_of_week', 'day_of_month', 'interval_hours', 'cron_expression', 'timezone_name')
        }),
        ('Execution Parameters & Overrides', {
            'fields': ('reprocess_existing', 'prevent_overlap', 'configuration_override'),
            'classes': ('collapse',)
        }),
        ('Telemetry & Run History', {
            'fields': ('next_run_at', 'last_run_at', 'last_pipeline_run', 'last_status', 'total_runs_count', 'consecutive_failures_count', 'max_consecutive_failures', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    readonly_fields = ('next_run_at', 'last_run_at', 'last_pipeline_run', 'last_status', 'total_runs_count', 'consecutive_failures_count', 'created_at', 'updated_at')

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        from django.utils import timezone
        import datetime

        now = timezone.now()
        next_24h = now + datetime.timedelta(hours=24)

        all_schedules = WorkflowSchedule.objects.all()
        total_count = all_schedules.count()
        active_count = all_schedules.filter(is_active=True).count()
        paused_count = total_count - active_count
        upcoming_24h_count = all_schedules.filter(is_active=True, next_run_at__range=(now, next_24h)).count()
        total_dispatched_runs = all_schedules.aggregate(models.Sum('total_runs_count'))['total_runs_count__sum'] or 0
        latest_run = all_schedules.filter(last_run_at__isnull=False).order_by('-last_run_at').first()

        extra_context['schedule_stats'] = {
            'total_count': total_count,
            'active_count': active_count,
            'paused_count': paused_count,
            'upcoming_24h_count': upcoming_24h_count,
            'total_dispatched_runs': total_dispatched_runs,
            'last_dispatched_at': latest_run.last_run_at if latest_run else None,
        }
        return super().changelist_view(request, extra_context=extra_context)

    def schedule_identity_display(self, obj):
        change_url = reverse('admin:research_intelligence_workflowschedule_change', args=[obj.id])
        ws_url = reverse('admin:research_intelligence_workspace_change', args=[obj.workspace.id])
        
        reprocess_tag = (
            '<span style="background-color: #6f42c1; color: white; padding: 2px 7px; border-radius: 4px; font-size: 10px; font-weight: 600; display: inline-block; white-space: nowrap;">🔄 Full Reprocess</span>'
            if obj.reprocess_existing else
            '<span style="background-color: #0d6efd; color: white; padding: 2px 7px; border-radius: 4px; font-size: 10px; font-weight: 600; display: inline-block; white-space: nowrap;">⚡ Incremental</span>'
        )

        return format_html(
            '<div style="display: flex; flex-direction: column; gap: 4px; align-items: flex-start;">'
            '<div style="font-weight: 700; font-size: 13px; color: #212529;">'
            '<a href="{}" style="text-decoration: none; color: inherit;">{}</a>'
            '</div>'
            '<div style="font-size: 11px; color: #6c757d; white-space: nowrap;">'
            'Target: <a href="{}" style="color: #0d6efd; text-decoration: none; font-weight: 500;">📁 {}</a>'
            '</div>'
            '<div>{}</div>'
            '</div>',
            change_url,
            obj.name,
            ws_url,
            obj.workspace.name,
            mark_safe(reprocess_tag)
        )
    schedule_identity_display.short_description = "Schedule & Target Workflow"
    schedule_identity_display.admin_order_field = "name"

    def frequency_badge(self, obj):
        colors = {
            'one_off': '#e83e8c',
            'daily': '#0d6efd',
            'weekdays': '#6f42c1',
            'weekly': '#198754',
            'monthly': '#fd7e14',
            'interval_hours': '#0dcaf0',
            'custom_cron': '#212529',
        }
        return render_badge(obj.get_frequency_display(), colors.get(obj.frequency, '#6c757d'))
    frequency_badge.short_description = "Frequency"
    frequency_badge.admin_order_field = "frequency"

    def schedule_pattern_display(self, obj):
        if obj.frequency == 'one_off':
            date_chip = f'<span style="font-size: 11px; background-color: #fce8f3; color: #d63384; padding: 2px 6px; border-radius: 4px; font-weight: 600; white-space: nowrap;">⏱️ Run Once</span>'
            return format_html(
                '<div style="font-size: 12px; font-weight: 600; color: #212529; margin-bottom: 3px;">🗓️ {}</div>'
                '<div>{}</div>',
                obj.schedule_description,
                mark_safe(date_chip)
            )

        return format_html(
            '<div style="font-size: 12px; font-weight: 600; color: #212529; margin-bottom: 3px;">🗓️ {}</div>'
            '<span style="font-family: monospace; font-size: 11px; background-color: #f1f3f5; color: #495057; padding: 2px 6px; border-radius: 4px; border: 1px solid #dee2e6; white-space: nowrap;">cron: {}</span>',
            obj.schedule_description,
            obj.cron_expression or '-'
        )
    schedule_pattern_display.short_description = "Schedule Recurrence"

    def is_active_toggle(self, obj):
        toggle_url = reverse('admin:research_intelligence_workflowschedule_toggle', args=[obj.id])
        if obj.is_active:
            badge = render_badge("ACTIVE", "#198754")
            action_text = "⏸️ Pause"
            action_hover = "Click to pause schedule"
        else:
            badge = render_badge("PAUSED", "#6c757d")
            action_text = "▶️ Resume"
            action_hover = "Click to activate schedule"

        return format_html(
            '<div style="display: flex; flex-direction: column; gap: 6px; align-items: flex-start;">'
            '<div>{}</div>'
            '<a href="{}" style="font-size: 10px; color: #495057; text-decoration: none; border: 1px solid #ced4da; padding: 2px 7px; border-radius: 4px; background: #ffffff; font-weight: 500; white-space: nowrap; box-shadow: 0 1px 2px rgba(0,0,0,0.05);" title="{}">{}</a>'
            '</div>',
            badge,
            toggle_url,
            action_hover,
            action_text
        )
    is_active_toggle.short_description = "Status"
    is_active_toggle.admin_order_field = "is_active"

    def next_run_display(self, obj):
        if not obj.is_active or not obj.next_run_at:
            return format_html('<span style="color: #6c757d; font-size: 11px; font-style: italic;">Paused</span>')
        from django.utils import timezone
        now = timezone.now()
        diff = obj.next_run_at - now
        if diff.total_seconds() < 0:
            diff_badge = '<span style="background-color: #dc3545; color: white; padding: 2px 6px; border-radius: 4px; font-size: 10px; font-weight: 700; white-space: nowrap;">🚨 Due now</span>'
        else:
            hours = int(diff.total_seconds() // 3600)
            minutes = int((diff.total_seconds() % 3600) // 60)
            diff_str = f"in {hours}h {minutes}m" if hours > 0 else f"in {minutes}m"
            diff_badge = f'<span style="background-color: #e7f5ff; color: #0c85d0; padding: 2px 6px; border-radius: 4px; font-size: 10px; font-weight: 600; white-space: nowrap;">⏳ {diff_str}</span>'

        return format_html(
            '<div style="white-space: nowrap; font-size: 12px; font-weight: 600; color: #212529; margin-bottom: 3px;">{}</div>'
            '<div>{}</div>',
            obj.next_run_at.strftime("%Y-%m-%d %H:%M UTC"),
            mark_safe(diff_badge)
        )
    next_run_display.short_description = "Next Run"
    next_run_display.admin_order_field = "next_run_at"

    def last_run_display(self, obj):
        if not obj.last_run_at:
            return format_html('<span style="color: #adb5bd;">Never</span>')

        # Observable status: reflect live state from pipeline_run/agent_process
        status = obj.current_execution_status or obj.last_status or 'pending'
        if obj.last_status != status:
            WorkflowSchedule.objects.filter(id=obj.id).update(last_status=status)
            obj.last_status = status

        is_halted, halt_step = getattr(obj, 'is_last_execution_halted_early', (False, ""))
        stop_reason = getattr(obj, 'last_execution_stop_reason', "") or ""

        note_html = ""
        if is_halted:
            status_color = "#fd7e14"
            badge_label = f"⚠️ HALTED ({halt_step.upper()})" if halt_step else "⚠️ HALTED"
            if "duplicate" in stop_reason.lower():
                short_note = "0 new papers (duplicates)"
            elif "0 papers" in stop_reason.lower() or "0 new papers" in stop_reason.lower():
                short_note = "0 papers passed criteria"
            elif stop_reason:
                short_note = stop_reason[:28] + ("..." if len(stop_reason) > 28 else "")
            else:
                short_note = f"Halted at {halt_step}"
            note_html = format_html(
                '<div style="font-size: 10px; color: #856404; background-color: #fff3cd; border: 1px solid #ffeeba; border-radius: 3px; padding: 2px 6px; white-space: nowrap; max-width: 170px; overflow: hidden; text-overflow: ellipsis;" title="{}">ℹ️ {}</div>',
                stop_reason,
                short_note
            )
        elif status == 'completed':
            status_color = "#198754"
            badge_label = "COMPLETED"
        elif status == 'failed':
            status_color = "#dc3545"
            badge_label = "FAILED"
            if stop_reason:
                short_note = stop_reason[:26] + ("..." if len(stop_reason) > 26 else "")
                note_html = format_html(
                    '<div style="font-size: 10px; color: #842029; background-color: #f8d7da; border: 1px solid #f5c2c7; border-radius: 3px; padding: 2px 6px; white-space: nowrap; max-width: 170px; overflow: hidden; text-overflow: ellipsis;" title="{}">❌ {}</div>',
                    stop_reason,
                    short_note
                )
        elif status == 'running':
            status_color = "#17a2b8"
            badge_label = "RUNNING"
        elif status == 'aborted':
            status_color = "#495057"
            badge_label = "ABORTED"
        else:
            status_color = "#6c757d"
            badge_label = status.upper()

        status_badge = render_badge(badge_label, status_color, title=stop_reason if stop_reason else None)
        
        run_link_html = ""
        if obj.last_pipeline_run:
            run_url = reverse('admin:research_intelligence_pipelinerun_change', args=[obj.last_pipeline_run.id])
            run_link_html = format_html(
                '<a href="{}" style="font-size: 11px; font-weight: 500; text-decoration: none; color: #0d6efd; background-color: #f0f6ff; border: 1px solid #b6d4fe; border-radius: 4px; padding: 2px 8px; display: inline-flex; align-items: center; gap: 3px; white-space: nowrap; box-shadow: 0 1px 2px rgba(0,0,0,0.04);" title="Inspect detailed pipeline run execution">'
                '🔍 View Run'
                '</a>',
                run_url
            )

        return format_html(
            '<div style="display: flex; flex-direction: column; gap: 4px; align-items: flex-start;">'
            '<div style="font-size: 11px; font-weight: 600; color: #495057; white-space: nowrap;">{}</div>'
            '<div>{}</div>'
            '{}'
            '<div>{}</div>'
            '</div>',
            obj.last_run_at.strftime("%Y-%m-%d %H:%M"),
            status_badge,
            note_html,
            mark_safe(run_link_html)
        )
    last_run_display.short_description = "Last Execution"
    last_run_display.admin_order_field = "last_run_at"

    def total_runs_display(self, obj):
        sr = obj.success_rate_percent
        if sr is not None:
            sr_color = "#198754" if sr >= 90 else ("#fd7e14" if sr >= 70 else "#dc3545")
            rate_badge = f'<div style="font-size: 10px; color: {sr_color}; font-weight: 600; margin-top: 2px;">{sr}% success</div>'
        else:
            rate_badge = ''

        runs_url = reverse('admin:research_intelligence_pipelinerun_changelist') + f"?schedule__id__exact={obj.id}"

        return format_html(
            '<div style="display: flex; flex-direction: column; align-items: flex-start;">'
            '<a href="{}" style="background-color: #f8f9fa; color: #495057; border: 1px solid #dee2e6; padding: 2px 7px; border-radius: 12px; font-weight: 600; font-size: 11px; white-space: nowrap; text-decoration: none;" title="View all pipeline runs triggered by this schedule">'
            '🚀 {} runs'
            '</a>'
            '{}'
            '</div>',
            runs_url,
            obj.total_runs_count,
            mark_safe(rate_badge)
        )
    total_runs_display.short_description = "Runs & SLA"
    total_runs_display.admin_order_field = "total_runs_count"

    def trigger_actions_column(self, obj):
        url = reverse('admin:research_intelligence_workflowschedule_trigger', args=[obj.id])
        return format_html(
            '<a href="{}" class="button" style="background-color: #198754; color: white !important; font-weight: bold; padding: 4px 10px; border-radius: 4px; text-decoration: none; font-size: 11px; white-space: nowrap; display: inline-flex; align-items: center; gap: 4px; box-shadow: 0 1px 2px rgba(0,0,0,0.1);">'
            '🚀 Run Now'
            '</a>',
            url
        )
    trigger_actions_column.short_description = "Actions"

    def get_urls(self):
        from django.urls import path
        urls = super().get_urls()
        custom_urls = [
            path('<uuid:schedule_id>/trigger/', self.admin_site.admin_view(self.trigger_schedule_view), name='research_intelligence_workflowschedule_trigger'),
            path('<uuid:schedule_id>/toggle/', self.admin_site.admin_view(self.toggle_schedule_view), name='research_intelligence_workflowschedule_toggle'),
        ]
        return custom_urls + urls

    def trigger_schedule_view(self, request, schedule_id):
        from django.shortcuts import get_object_or_404, redirect
        from django.contrib import messages
        schedule = get_object_or_404(WorkflowSchedule, id=schedule_id)
        agent = schedule.trigger_run(triggered_by_user=request.user, force=True)
        messages.success(request, f"Successfully triggered scheduled workflow '{schedule.name}' (Agent Process: {agent.id}).")
        return redirect('admin:research_intelligence_workflowschedule_changelist')

    def toggle_schedule_view(self, request, schedule_id):
        from django.shortcuts import get_object_or_404, redirect
        from django.contrib import messages
        schedule = get_object_or_404(WorkflowSchedule, id=schedule_id)
        schedule.is_active = not schedule.is_active
        if schedule.is_active:
            schedule.next_run_at = schedule.compute_next_run()
            messages.success(request, f"Resumed schedule '{schedule.name}'. Next run at {schedule.next_run_at.strftime('%Y-%m-%d %H:%M UTC')}.")
        else:
            schedule.next_run_at = None
            messages.info(request, f"Paused schedule '{schedule.name}'.")
        schedule.save(update_fields=['is_active', 'next_run_at'])
        return redirect('admin:research_intelligence_workflowschedule_changelist')

    @admin.action(description="🚀 Trigger Selected Schedules Now")
    def trigger_now_action(self, request, queryset):
        count = 0
        for sched in queryset:
            sched.trigger_run(triggered_by_user=request.user, force=True)
            count += 1
        self.message_user(request, f"Successfully triggered {count} scheduled workflow run(s).")

    @admin.action(description="▶️ Activate / Resume Selected Schedules")
    def activate_schedules_action(self, request, queryset):
        for s in queryset:
            s.is_active = True
            s.next_run_at = s.compute_next_run()
            s.save(update_fields=['is_active', 'next_run_at'])
        self.message_user(request, f"Activated {queryset.count()} schedule(s).")

    @admin.action(description="⏸️ Pause Selected Schedules")
    def pause_schedules_action(self, request, queryset):
        queryset.update(is_active=False, next_run_at=None)
        self.message_user(request, f"Paused {queryset.count()} schedule(s).")


@admin.register(PipelineRun)
class PipelineRunAdmin(admin.ModelAdmin):
    formfield_overrides = {
        models.JSONField: {'widget': PrettyJSONWidget},
    }
    list_display = (
        'id',
        'workspace',
        'name_display',
        'status_badge',
        'stopped_stage_badge',
        'status_message_display',
        'papers_funnel_display',
        'reprocess_existing_badge',
        'execution_time',
        'formatted_usd_cost',
        'schedule_display',
        'started_at',
        'completed_at',
        'triggered_by_display'
    )
    list_display_links = ('id', 'name_display')
    ordering = ('-started_at', '-id')
    list_select_related = ('workspace', 'triggered_by', 'schedule')
    list_filter = ('status', 'current_stage', 'stopped_at_stage', 'reprocess_existing', 'schedule', 'run_date', 'workspace', 'triggered_by')
    search_fields = ('id', 'name', 'workspace__name', 'status_message', 'schedule__name', 'triggered_by__username', 'triggered_by__email')
    readonly_fields = ('started_at', 'completed_at', 'execution_time', 'stage_results_preview', 'step_history_preview')
    inlines = [ComponentRunInline]

    fieldsets = (
        ('Execution Info', {
            'fields': ('workspace', 'name', 'schedule', 'status', 'current_stage', 'stopped_at_stage', 'status_message', 'triggered_by')
        }),
        ('Stage Execution Results & Breakdown', {
            'fields': ('stage_results_preview', 'stage_results'),
            'description': 'Per-stage execution status, summary explanations, and metrics.'
        }),
        ('Reprocessing & Ingestion Options', {
            'fields': ('reprocess_existing', 'configuration_override'),
            'description': 'When enabled, existing and duplicate papers in the workspace will be re-screened and re-extracted through all downstream stages instead of halted during Search & Ingestion.'
        }),
        ('Audit Log & History', {
            'fields': ('step_history_preview', 'step_history')
        }),
        ('Timestamps & Throughput Metrics', {
            'fields': (
                'started_at', 'completed_at', 'execution_time',
                'total_papers_fetched', 'total_papers_passed_screening',
                'tokens_in', 'tokens_out', 'tokens_consumed', 'usd_cost'
            )
        }),
    )

    actions = [
        'run_full_pipeline',
        'rerun_with_reprocessing',
        'tick_selected_runs',
        'pause_selected_runs',
        'resume_selected_runs',
        'abort_selected_runs',
        'send_digest_email_action',
        'reap_zombie_runs_action'
    ]

    def name_display(self, obj):
        name = (obj.name or "").strip()
        if name:
            return format_html('<strong>{}</strong>', name)
        return format_html('<span style="color: #6c757d;">Run {}</span>', str(obj.id)[:8])
    name_display.short_description = "Run Name"
    name_display.admin_order_field = "name"

    def papers_funnel_display(self, obj):
        fetched = obj.total_papers_fetched
        passed = obj.total_papers_passed_screening
        if fetched is None or fetched == 0:
            if hasattr(obj, 'get_papers'):
                try:
                    fetched = obj.get_papers().count()
                except Exception:
                    fetched = 0
            else:
                fetched = 0
        if passed is None:
            passed = 0

        if fetched == 0 and passed == 0:
            return format_html('<span style="color: #6c757d;">0 in ➔ 0 out</span>')
        return format_html(
            '<span style="white-space: nowrap; font-family: monospace; font-size: 12px;">'
            '<strong style="color: #0d6efd;">{} in</strong> '
            '<span style="color: #6c757d;">➔</span> '
            '<strong style="color: #198754;">{} out</strong>'
            '</span>',
            fetched,
            passed
        )
    papers_funnel_display.short_description = "Papers (In ➔ Out)"
    papers_funnel_display.admin_order_field = 'total_papers_fetched'

    papers_in_out = papers_funnel_display

    def total_papers_fetched(self, obj):
        return obj.total_papers_fetched
    total_papers_fetched.short_description = "Papers In (Fetched)"

    def total_papers_passed_screening(self, obj):
        return obj.total_papers_passed_screening
    total_papers_passed_screening.short_description = "Papers Out (Passed)"

    def stopped_stage_badge(self, obj):
        stage = obj.stopped_at_stage or obj.current_stage
        stage_choices = dict(PipelineRun.STAGE_CHOICES)
        stage_name = stage_choices.get(stage, (stage or "").replace('_', ' ').title())

        if obj.status == 'running':
            cur_name = stage_choices.get(obj.current_stage, (obj.current_stage or "Search").replace('_', ' ').title())
            return render_badge(f"⏳ IN PROGRESS ({cur_name.upper()})", "#0d6efd", "#ffffff")
        elif obj.status == 'failed':
            return render_badge(f"❌ FAILED AT {stage_name.upper()}", "#dc3545", "#ffffff")
        elif obj.status == 'completed':
            if stage and stage not in ('completed', 'reporting'):
                return render_badge(f"⚠️ HALTED AT {stage_name.upper()}", "#fd7e14", "#ffffff")
            return render_badge("✅ COMPLETED", "#198754", "#ffffff")
        elif obj.status == 'paused':
            return render_badge("⏸️ PAUSED", "#ffc107", "#000000")
        elif obj.status == 'aborted':
            return render_badge("🛑 ABORTED", "#495057", "#ffffff")
        return render_badge((obj.status or "PENDING").upper(), "#6c757d", "#ffffff")
    stopped_stage_badge.short_description = "Halt / Final Stage"

    def schedule_display(self, obj):
        if not obj.schedule:
            return format_html('<span style="color: #adb5bd; font-size: 11px;">Manual</span>')
        sched_url = reverse('admin:research_intelligence_workflowschedule_change', args=[obj.schedule.id])
        return format_html(
            '<a href="{}" style="font-size: 11px; color: #0d6efd; text-decoration: none; font-weight: 500;" title="View trigger schedule">⏰ {}</a>',
            sched_url,
            obj.schedule.name
        )
    schedule_display.short_description = "Schedule"
    schedule_display.admin_order_field = "schedule__name"

    def save_model(self, request, obj, form, change):
        if not obj.triggered_by and request.user.is_authenticated:
            obj.triggered_by = request.user
        super().save_model(request, obj, form, change)

    def triggered_by_display(self, obj):
        user = obj.triggered_by
        if not user:
            agent = obj.agent_processes.filter(triggered_by__isnull=False).first()
            if agent:
                user = agent.triggered_by

        if not user:
            return format_html('<span style="color: #6c757d; font-style: italic;">⚙️ System / Automated</span>')

        username = user.username or "User"
        email_part = f" ({user.email})" if user.email else ""
        return format_html(
            '<span style="font-weight: 500; color: #212529;">👤 {}<span style="color: #6c757d; font-size: 0.85em;">{}</span></span>',
            username,
            email_part
        )
    triggered_by_display.short_description = "Triggered By"
    triggered_by_display.admin_order_field = 'triggered_by__username'

    def status_message_display(self, obj):
        msg = (obj.status_message or "").strip()
        if not msg and obj.error_message:
            msg = obj.error_message.strip()
        if not msg and obj.step_history:
            for entry in reversed(obj.step_history):
                if entry.get('message'):
                    msg = entry['message'].strip()
                    break

        if not msg:
            if obj.status == 'running':
                return format_html('<span style="color: #0d6efd;">⏳ Active stage in progress...</span>')
            elif obj.status == 'completed':
                return format_html('<span style="color: #198754;">✅ Systematic review completed</span>')
            return "-"

        display_text = msg if len(msg) <= 65 else (msg[:62] + "...")
        is_halted = (
            (obj.stopped_at_stage and obj.stopped_at_stage not in ('completed', 'reporting'))
            or "halted" in msg.lower()
            or "0 new papers" in msg.lower()
            or "0 papers fetched" in msg.lower()
            or "0 papers passed" in msg.lower()
        )
        if obj.status == 'failed':
            return format_html('<span title="{}" style="color: #dc3545; font-weight: 500;">❌ {}</span>', msg, display_text)
        elif is_halted:
            return format_html('<span title="{}" style="color: #d63384; font-weight: 500;">⚠️ {}</span>', msg, display_text)
        elif obj.status == 'completed':
            return format_html('<span title="{}" style="color: #198754; font-weight: 500;">✅ {}</span>', msg, display_text)
        return format_html('<span title="{}">{}</span>', msg, display_text)
    status_message_display.short_description = "Status Message / Reason"

    @admin.display(boolean=True, description="Reprocess Existing", ordering="reprocess_existing")
    def reprocess_existing_badge(self, obj):
        return obj.reprocess_existing

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
                model_name = obj.workspace.screening_llm_model if obj.workspace else "google/gemini-3.8-flash"
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
            'abstract_screening': '#0dcaf0',
            'download': '#0dcaf0',
            'ocr': '#6f42c1',
            'full_text_screening': '#ffc107',
            'screening': '#ffc107',
            'extraction': '#198754',
            'signal_score': '#fd7e14',
            'metrics': '#fd7e14',
            'deep_research': '#d63384',
            'reporting': '#20c997',
            'completed': '#198754',
        }
        bg = colors.get(obj.current_stage, '#6c757d')
        text_color = '#000000' if bg in ('#ffc107', '#0dcaf0') else '#ffffff'
        return render_badge(obj.get_current_stage_display(), bg, text_color)
    current_stage_badge.short_description = "Current Stage"

    def stage_results_preview(self, obj):
        if not obj.stage_results:
            return format_html('<span style="color: #6c757d;">No stage results recorded yet.</span>')
        rows = []
        status_colors = {
            'completed': '#198754',
            'running': '#0d6efd',
            'failed': '#dc3545',
            'skipped': '#6c757d',
            'pending': '#adb5bd',
        }
        for stage, data in obj.stage_results.items():
            if not isinstance(data, dict):
                continue
            st = data.get('status', 'pending')
            color = status_colors.get(st, '#6c757d')
            summary = data.get('summary') or data.get('error') or '-'
            badge = render_badge(st.upper(), color, '#ffffff')
            updated_at = data.get('updated_at', '')
            ts_str = f"<span style='color: #888; font-size: 11px;'> ({updated_at[:19]})</span>" if updated_at else ""
            rows.append(
                f"<tr>"
                f"<td style='padding: 6px 10px; font-weight: bold; border-bottom: 1px solid #e9ecef;'>{stage.title()}</td>"
                f"<td style='padding: 6px 10px; border-bottom: 1px solid #e9ecef;'>{badge}</td>"
                f"<td style='padding: 6px 10px; border-bottom: 1px solid #e9ecef;'>{summary}{ts_str}</td>"
                f"</tr>"
            )
        
        return format_html(
            '<table style="border-collapse: collapse; width: 100%; max-width: 850px; background: #ffffff; border: 1px solid #dee2e6; border-radius: 4px; box-shadow: 0 1px 3px rgba(0,0,0,0.05);">'
            '<thead><tr style="background: #f8f9fa; text-align: left; border-bottom: 2px solid #dee2e6;">'
            '<th style="padding: 8px 10px;">Pipeline Stage</th><th style="padding: 8px 10px;">Status</th><th style="padding: 8px 10px;">Execution Summary / Reason</th>'
            '</tr></thead>'
            '<tbody>{}</tbody></table>',
            mark_safe(''.join(rows))
        )
    stage_results_preview.short_description = "Pipeline Stages Breakdown"

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

    @admin.action(description="🧟 Reap / Terminate Stale Zombie Runs")
    def reap_zombie_runs_action(self, request, queryset):
        from research_intelligence.tasks.auxiliary.zombie_watchdog import reap_zombie_tasks
        stats = reap_zombie_tasks(max_component_age_minutes=5, force=False)
        self.message_user(
            request,
            f"🧟 Reaped {stats['reaped_pipelines']} stale pipeline run(s), {stats['reaped_agents']} agent process(es), and {stats['reaped_components']} component task(s)."
        )

    @admin.action(description="🚀 Launch/Advance Autonomous Pipeline (Current Settings)")
    def run_full_pipeline(self, request, queryset):
        from research_intelligence.tasks.orchestrator.agent_engine import tick_agent_process
        for pr in queryset:
            if request.user.is_authenticated and not pr.triggered_by:
                pr.triggered_by = request.user
                pr.save(update_fields=['triggered_by'])
            agent = pr.agent_processes.filter(status__in=['running', 'pending', 'paused']).first()
            if not agent:
                agent = ResearchAgentProcess.objects.create(
                    workspace=pr.workspace,
                    pipeline_run=pr,
                    triggered_by=request.user if request.user.is_authenticated else pr.triggered_by,
                    name=f"Autonomous Pipeline - {pr.workspace.name}",
                    status='running',
                    current_step=pr.current_stage if pr.current_stage != 'completed' else 'initialized',
                    configuration_override={"reprocess_existing": pr.reprocess_existing}
                )
            elif request.user.is_authenticated and not agent.triggered_by:
                agent.triggered_by = request.user
                agent.save(update_fields=['triggered_by'])
            tick_agent_process(str(agent.id))
        self.message_user(request, f"Triggered autonomous pipeline orchestrator for {queryset.count()} pipeline run(s).")

    @admin.action(description="🔄 Launch Pipeline with Forced Reprocessing of Existing Papers (ON)")
    def rerun_with_reprocessing(self, request, queryset):
        from research_intelligence.tasks.orchestrator.agent_engine import tick_agent_process
        for pr in queryset:
            pr.reprocess_existing = True
            pr.save(update_fields=['reprocess_existing'])
            agent = ResearchAgentProcess.objects.create(
                workspace=pr.workspace,
                pipeline_run=pr,
                triggered_by=request.user if request.user.is_authenticated else pr.triggered_by,
                name=f"Reprocessing Run - {pr.workspace.name}",
                status='running',
                current_step='initialized',
                configuration_override={"reprocess_existing": True}
            )
            tick_agent_process(str(agent.id))
        self.message_user(request, f"Launched forced reprocessing run for {queryset.count()} pipeline run(s).")

    @admin.action(description="▶️ Advance/Tick Selected Run(s)")
    def tick_selected_runs(self, request, queryset):
        from research_intelligence.tasks.orchestrator.agent_engine import run_pipeline_tick
        for pr in queryset:
            run_pipeline_tick(str(pr.id))
        self.message_user(request, f"Ticked execution engine for {queryset.count()} pipeline run(s).")

    @admin.action(description="⏸️ Pause Selected Run(s)")
    def pause_selected_runs(self, request, queryset):
        for pr in queryset.filter(status='running'):
            pr.status = 'paused'
            pr.save(update_fields=['status'])
        self.message_user(request, f"Paused {queryset.count()} pipeline run(s).")

    @admin.action(description="▶️ Resume Selected Run(s)")
    def resume_selected_runs(self, request, queryset):
        from research_intelligence.tasks.orchestrator.agent_engine import run_pipeline_tick
        for pr in queryset.filter(status='paused'):
            pr.status = 'running'
            pr.save(update_fields=['status'])
            run_pipeline_tick(str(pr.id))
        self.message_user(request, f"Resumed {queryset.count()} pipeline run(s).")

    @admin.action(description="⏹️ Abort Selected Run(s)")
    def abort_selected_runs(self, request, queryset):
        for pr in queryset.exclude(status__in=['completed', 'failed', 'aborted']):
            pr.status = 'aborted'
            pr.save(update_fields=['status'])
        self.message_user(request, f"Aborted {queryset.count()} pipeline run(s).")


class ResearchAgentProcessAdmin(PipelineRunAdmin):
    """
    Backward-compatibility proxy ModelAdmin for ResearchAgentProcess.
    Inherits all rich UI/UX, funnel metrics, stage results preview,
    and actions from PipelineRunAdmin without exposing a separate menu item.
    """

    def has_module_permission(self, request):
        return False

    def reprocess_mode_badge(self, obj):
        is_reprocess = False
        if isinstance(getattr(obj, 'configuration_override', None), dict) and obj.configuration_override.get('reprocess_existing'):
            is_reprocess = True
        elif getattr(obj, 'reprocess_existing', False):
            is_reprocess = True
        elif hasattr(obj, 'pipeline_run') and obj.pipeline_run and obj.pipeline_run.reprocess_existing:
            is_reprocess = True
        if is_reprocess:
            return render_badge("🔄 REPROCESS ON", "#0dcaf0", "#000000")
        return format_html('<span style="color: #6c757d;">Standard</span>')
    reprocess_mode_badge.short_description = "Reprocess"

    def pipeline_run_link(self, obj):
        pr = getattr(obj, 'pipeline_run', None)
        if not pr and getattr(obj, 'workspace', None):
            pr = PipelineRun.objects.filter(workspace=obj.workspace).exclude(pk=obj.pk).order_by('-started_at').first()
            if pr:
                obj.pipeline_run = pr
                obj.save(update_fields=['pipeline_run'])
        if not pr:
            return "-"
        url = reverse("admin:research_intelligence_pipelinerun_change", args=[pr.id])
        return format_html('<a href="{}"><code>{}</code></a>', url, str(pr.id)[:8] + '...')
    pipeline_run_link.short_description = "Pipeline Run"

    def current_step_badge(self, obj):
        step = getattr(obj, 'current_step', None) or getattr(obj, 'current_stage', 'search')
        colors = {
            'initialized': '#6c757d',
            'search': '#0d6efd',
            'download': '#0dcaf0',
            'ocr': '#6f42c1',
            'screening': '#ffc107',
            'extraction': '#198754',
            'signal_score': '#fd7e14',
            'reporting': '#20c997',
            'completed': '#198754',
            'failed': '#dc3545',
            'aborted': '#495057',
        }
        bg = colors.get(step, '#6c757d')
        text_color = '#000000' if bg in ('#ffc107', '#0dcaf0') else '#ffffff'
        display_name = dict(ResearchAgentProcess.STEP_CHOICES).get(step, step.title())
        return render_badge(display_name, bg, text_color)
    current_step_badge.short_description = "Active Step"

    def stop_reason_display(self, obj):
        return self.status_message_display(obj)
    stop_reason_display.short_description = "Stop Reason / Status Message"

    def save_model(self, request, obj, form, change):
        is_new = obj._state.adding
        if not obj.triggered_by and request.user.is_authenticated:
            obj.triggered_by = request.user
        super().save_model(request, obj, form, change)
        if (is_new or obj.current_step == 'initialized') and obj.status == 'running':
            from research_intelligence.tasks.orchestrator.agent_engine import tick_agent_process
            try:
                tick_agent_process(str(obj.id))
            except Exception as e:
                logger.warning(f"Failed to auto-tick newly created agent '{obj.id}': {e}")

    def changelist_view(self, request, extra_context=None):
        stuck_agents = list(ResearchAgentProcess.objects.filter(status='running', current_step='initialized')[:5])
        if stuck_agents:
            from research_intelligence.tasks.orchestrator.agent_engine import tick_agent_process
            for agent in stuck_agents:
                try:
                    tick_agent_process(str(agent.id))
                except Exception:
                    pass
        return super().changelist_view(request, extra_context=extra_context)

    def usd_cost(self, obj):
        pr = obj.pipeline_run
        if not pr and obj.workspace:
            pr = PipelineRun.objects.filter(workspace=obj.workspace).exclude(pk=obj.pk).order_by('-started_at').first()
        if pr:
            cost = float(PipelineRun.objects.filter(pk=pr.pk).values_list('usd_cost', flat=True).first() or pr.usd_cost or 0.0)
            if cost == 0.0:
                comp_cost = sum(
                    float((cr.metrics or {}).get("usd_cost") or 0.0)
                    for cr in pr.component_runs.all()
                )
                if comp_cost > 0.0:
                    cost = comp_cost
            if cost == 0.0 and (pr.tokens_in or pr.tokens_out or pr.tokens_consumed):
                try:
                    from research_intelligence.llm_providers.pricing import calculate_llm_cost
                    model_name = pr.workspace.screening_llm_model if pr.workspace else "google/gemini-3.8-flash"
                    cost = float(calculate_llm_cost(model_name, pr.tokens_in or 0, pr.tokens_out or 0))
                except Exception:
                    pass
            if cost > 0:
                return format_html('<strong style="color: #0d6efd;">${}</strong>', f"{cost:.4f}")
        return format_html('<span style="color: #6c757d;">$0.0000</span>')
    usd_cost.short_description = "USD Cost"
    usd_cost.admin_order_field = 'usd_cost'

    def usd_cost_display(self, obj):
        return self.usd_cost(obj)
    usd_cost_display.short_description = "USD Cost"
    usd_cost_display.admin_order_field = 'usd_cost'

    @admin.action(description="▶️ Advance/Tick Selected Agent(s)")
    def tick_selected_agents(self, request, queryset):
        from research_intelligence.tasks.orchestrator.agent_engine import tick_agent_process
        for agent in queryset:
            tick_agent_process(str(agent.id))
        self.message_user(request, f"Ticked state machine for {queryset.count()} agent process(es).")

    @admin.action(description="⏸️ Pause Selected Agent(s)")
    def pause_selected_agents(self, request, queryset):
        return self.pause_selected_runs(request, queryset)

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
        return self.abort_selected_runs(request, queryset)

    @admin.action(description="🧟 Reap / Terminate Stale Zombie Processes")
    def reap_zombie_agents_action(self, request, queryset):
        return self.reap_zombie_runs_action(request, queryset)


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
        'status_badge',
        'execution_time',
        'cost_display',
        'metrics_summary',
        'celery_task_id',
        'started_at',
        'completed_at',
        'triggered_by_display'
    )
    ordering = ('-started_at', '-id')
    list_select_related = ('pipeline_run', 'pipeline_run__workspace', 'pipeline_run__triggered_by')
    list_filter = (RecentPipelineRunFilter, ComponentRunWorkspaceFilter, 'pipeline_run__triggered_by', 'step_type', 'status', 'started_at')
    search_fields = ('id', 'component_name', 'celery_task_id', 'pipeline_run__id', 'pipeline_run__workspace__name', 'pipeline_run__triggered_by__username', 'pipeline_run__triggered_by__email')
    readonly_fields = ('started_at', 'completed_at', 'execution_time')

    def triggered_by_display(self, obj):
        user = None
        if obj.pipeline_run:
            user = obj.pipeline_run.triggered_by
            if not user:
                agent = obj.pipeline_run.agent_processes.filter(triggered_by__isnull=False).first()
                if agent:
                    user = agent.triggered_by

        if not user:
            return format_html('<span style="color: #6c757d; font-style: italic;">⚙️ System / Automated</span>')

        username = user.username or "User"
        email_part = f" ({user.email})" if user.email else ""
        return format_html(
            '<span style="font-weight: 500; color: #212529;">👤 {}<span style="color: #6c757d; font-size: 0.85em;">{}</span></span>',
            username,
            email_part
        )
    triggered_by_display.short_description = "Triggered By"
    triggered_by_display.admin_order_field = 'pipeline_run__triggered_by__username'

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
            'abstract_screening': '#0dcaf0',
            'download': '#0dcaf0',
            'ocr': '#6f42c1',
            'screening': '#ffc107',
            'full_text_screening': '#ffc107',
            'extraction': '#198754',
            'signal_score': '#fd7e14',
            'metrics': '#fd7e14',
            'deep_research': '#d63384',
            'reporting': '#20c997',
        }
        label = obj.get_step_type_display()
        if obj.step_type == 'screening' and obj.component_name:
            if obj.component_name == 'abstract_screening':
                label = 'Abstract Screening'
            elif obj.component_name == 'full_text_screening':
                label = 'Full-Text Screening'
        bg = colors.get(obj.component_name, colors.get(obj.step_type, '#6c757d'))
        text_color = '#000000' if bg in ('#ffc107', '#0dcaf0') else '#ffffff'
        return render_badge(label, bg, text_color)
    step_type_badge.short_description = "Step Type"

    def status_badge(self, obj):
        colors = {
            'pending': '#6c757d',
            'running': '#0d6efd',
            'completed': '#198754',
            'skipped': '#6c757d',
            'failed': '#dc3545',
            'aborted': '#495057',
        }
        return render_badge(obj.status.upper(), colors.get(obj.status, '#6c757d'))
    status_badge.short_description = "Status"

    actions = ['rerun_from_this_component_step', 'reexecute_single_component_run', 'abort_selected_component_runs', 'reap_zombie_components_action']

    @admin.action(description="🧟 Reap / Terminate Stale Zombie Tasks")
    def reap_zombie_components_action(self, request, queryset):
        from research_intelligence.tasks.auxiliary.zombie_watchdog import reap_zombie_tasks
        stats = reap_zombie_tasks(max_component_age_minutes=5, force=False)
        self.message_user(
            request,
            f"🧟 Reaped {stats['reaped_components']} stale component task(s), {stats['reaped_pipelines']} pipeline run(s), and {stats['reaped_agents']} agent process(es)."
        )

    @admin.action(description="🔄 Rerun Pipeline from Selected Step Forward")
    def rerun_from_this_component_step(self, request, queryset):
        from research_intelligence.tasks.orchestrator.dag import build_default_slr_dag
        from research_intelligence.tasks.orchestrator.agent_engine import tick_agent_process
        from research_intelligence.models import ResearchAgentProcess

        count = 0
        for comp in queryset:
            pr = comp.pipeline_run
            dag = build_default_slr_dag(pr.workspace)
            target_node = None
            if comp.component_name in dag.nodes:
                target_node = comp.component_name
            else:
                for n_name, node in dag.nodes.items():
                    if node.step_type == comp.step_type:
                        target_node = n_name
                        break

            if target_node:
                # 1. Reset DAG downstream from target node
                dag.rerun_from_node(pr, target_node)

                # 2. Find or create an active ResearchAgentProcess
                agent = pr.agent_processes.filter(status__in=['running', 'pending', 'paused', 'failed', 'completed']).first()
                if not agent:
                    agent = ResearchAgentProcess.objects.create(
                        workspace=pr.workspace,
                        pipeline_run=pr,
                        triggered_by=request.user if request.user.is_authenticated else pr.triggered_by,
                        name=f"Rerun from {comp.get_step_type_display()} - {pr.workspace.name}",
                        status='running',
                        current_step=comp.step_type,
                        configuration_override={"reprocess_existing": getattr(pr, 'reprocess_existing', False)}
                    )
                else:
                    agent.status = 'running'
                    agent.current_step = comp.step_type
                    agent.stopped_at_step = None
                    agent.stop_reason = ""
                    agent.completed_at = None
                    agent.save(update_fields=['status', 'current_step', 'stopped_at_step', 'stop_reason', 'completed_at'])

                # 3. Synchronously evaluate and dispatch the ready node(s) so a new ComponentRun is immediately created
                dag.evaluate_and_dispatch(pr, agent_process=agent)

                # 4. Trigger asynchronous orchestrator ticker for Celery tasks
                tick_agent_process(str(agent.id))
                count += 1

        self.message_user(request, f"Successfully triggered DAG rerun from selected step for {count} component run(s).")

    @admin.action(description="⚡ Re-execute only this single Component Task (Celery)")
    def reexecute_single_component_run(self, request, queryset):
        from research_intelligence.tasks.orchestrator.dag import build_default_slr_dag
        from django.utils import timezone

        count = 0
        for comp in queryset:
            dag = build_default_slr_dag(comp.pipeline_run.workspace)
            for n_name, node in dag.nodes.items():
                if node.step_type == comp.step_type:
                    comp.status = 'running'
                    comp.error_message = ''
                    comp.completed_at = None
                    comp.started_at = timezone.now()
                    comp.save(update_fields=['status', 'error_message', 'completed_at', 'started_at'])
                    node.execute(comp.pipeline_run, comp)
                    count += 1
                    break

        self.message_user(request, f"Re-dispatched {count} single component task(s) on Celery.")

    @admin.action(description="🛑 Stop / Abort Selected Component Task(s) (Celery Revoke)")
    def abort_selected_component_runs(self, request, queryset):
        from django.utils import timezone
        import logging
        logger = logging.getLogger(__name__)

        count = 0
        for comp in queryset:
            # 1. Revoke Celery task if running/active
            if comp.celery_task_id:
                try:
                    from django_project.celery import app as celery_app
                    celery_app.control.revoke(comp.celery_task_id, terminate=True, signal='SIGKILL')
                    logger.info(f"🛑 [CELERY REVOKE] Revoked task '{comp.celery_task_id}' for ComponentRun '{comp.id}' with SIGKILL.")
                except Exception as e:
                    logger.warning(f"Failed to revoke Celery task '{comp.celery_task_id}': {e}")

            # 2. Mark ComponentRun as aborted
            comp.status = 'aborted'
            comp.error_message = "🛑 Aborted manually by administrator in Django Admin."
            comp.completed_at = timezone.now()
            comp.save(update_fields=['status', 'error_message', 'completed_at'])

            # 3. Synchronize Agent Process and PipelineRun state
            pr = comp.pipeline_run
            if pr:
                pr.status = 'aborted'
                pr.stopped_at_stage = comp.step_type
                pr.status_message = f"Pipeline aborted at step '{comp.step_type}' by administrator."
                pr.completed_at = timezone.now()
                p_hist = list(pr.step_history or [])
                p_hist.append({
                    "step": comp.step_type,
                    "event": "aborted",
                    "message": f"ComponentRun '{comp.id}' aborted by administrator",
                    "timestamp": timezone.now().isoformat()
                })
                pr.step_history = p_hist
                pr.save(update_fields=['status', 'stopped_at_stage', 'status_message', 'completed_at', 'step_history'])

                for agent in pr.agent_processes.filter(status__in=['running', 'pending', 'paused']):
                    agent.status = 'aborted'
                    agent.stopped_at_step = comp.step_type
                    agent.stop_reason = f"Component task '{comp.step_type}' was aborted by admin."
                    agent.completed_at = timezone.now()
                    agent.step_history = p_hist
                    agent.save(update_fields=['status', 'stopped_at_step', 'stop_reason', 'completed_at', 'step_history'])

            count += 1

        self.message_user(request, f"Successfully stopped and aborted {count} component task(s).")


class PaperMetricInline(admin.TabularInline):
    model = PaperMetric
    extra = 0
    fields = ('pipeline_run_link', 'screening_status_badge', 'signal_score_badge', 'metrics_preview', 'created_at')
    readonly_fields = ('pipeline_run_link', 'screening_status_badge', 'signal_score_badge', 'metrics_preview', 'created_at')
    can_delete = False
    show_change_link = True

    def pipeline_run_link(self, obj):
        pr = obj.pipeline_run
        if not pr:
            return "-"
        url = reverse("admin:research_intelligence_pipelinerun_change", args=[pr.id])
        return format_html('<a href="{}" title="Pipeline Run: {}"><code>{}</code></a>', url, str(pr.id), str(pr.id)[:8] + '...')
    pipeline_run_link.short_description = "Pipeline Run"

    def screening_status_badge(self, obj):
        colors = {
            'pending': '#6c757d',
            'abstract_passed': '#0dcaf0',
            'full_text_passed': '#198754',
            'accepted': '#198754',
            'borderline': '#ffc107',
            'rejected': '#dc3545',
            'withdrawn': '#6c757d',
        }
        labels = {
            'pending': 'Pending',
            'abstract_passed': 'Abstract Passed',
            'full_text_passed': 'Full Text Passed',
            'accepted': 'Accepted',
            'borderline': 'Borderline',
            'rejected': 'Rejected',
            'withdrawn': 'Withdrawn'
        }
        status = obj.screening_status or 'pending'
        bg = colors.get(status, '#6c757d')
        text_color = '#000000' if bg in ['#ffc107', '#0dcaf0'] else '#ffffff'
        return render_badge(labels.get(status, status), bg, text_color)
    screening_status_badge.short_description = "Screening Status"

    def signal_score_badge(self, obj):
        if obj.signal_score is None:
            return mark_safe('<span style="color: #6c757d;">-</span>')
        try:
            score_str = f"{float(obj.signal_score):.2f}"
        except Exception:
            score_str = str(obj.signal_score)
        return format_html(
            '<span style="background-color: #0d6efd; color: #ffffff; padding: 2px 7px; border-radius: 4px; font-weight: bold; font-size: 11px; white-space: nowrap; display: inline-block;">⚡&nbsp;{}</span>',
            score_str
        )
    signal_score_badge.short_description = "Signal Score"

    def metrics_preview(self, obj):
        if not obj.metrics_data:
            return mark_safe('<span style="color: #6c757d;">-</span>')
        items = []
        for k, v in list(obj.metrics_data.items())[:3]:
            items.append(f"<strong>{escape(str(k))}</strong>: {escape(str(v))}")
        preview_str = " | ".join(items)
        if len(obj.metrics_data) > 3:
            preview_str += " ..."
        return mark_safe(f'<span style="font-size: 11px; color: #495057;">{preview_str}</span>')
    metrics_preview.short_description = "Extracted Metrics"


@admin.register(Paper)
class PaperAdmin(admin.ModelAdmin):
    formfield_overrides = {
        models.JSONField: {'widget': PrettyJSONWidget},
    }
    inlines = [PaperMetricInline]
    list_display = (
        'title',
        'workspace',
        'runs_count_badge',
        'source_database_badge',
        'source_link_badge',
        'created_at'
    )
    ordering = ('-created_at', '-id')
    list_select_related = ('workspace',)
    list_filter = ('source_database', 'workspace')
    search_fields = ('title', 'authors', 'doi', 'arxiv_id', 'source_url', 'hash_id')
    readonly_fields = ('id', 'hash_id', 'created_at')

    fieldsets = (
        ('Paper Metadata', {
            'fields': ('workspace', 'title', 'authors', 'abstract')
        }),
        ('Identifiers & Source Repository', {
            'fields': ('source_database', 'source_url', 'doi', 'arxiv_id', 'hash_id')
        }),
        ('Canonical Document Registry & Local Storage', {
            'fields': ('document_registry', 'original_pdf_path', 'converted_md_path', 'created_at')
        }),
        ('Source Metadata (meta)', {
            'fields': ('meta',),
            'description': 'Raw JSON metadata payload ingested from external repository.'
        }),
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.annotate(
            _runs_count=models.Count('metrics__pipeline_run', distinct=True)
        )

    def runs_count_badge(self, obj):
        count = getattr(obj, '_runs_count', None)
        if count is None:
            count = obj.metrics.filter(pipeline_run__isnull=False).values('pipeline_run').distinct().count()

        if count == 0:
            return format_html('<span style="color: #adb5bd; font-size: 11px;">0 runs</span>')

        label = "1 run" if count == 1 else f"{count} runs"
        url = reverse("admin:research_intelligence_papermetric_changelist")
        return format_html(
            '<a href="{}?paper__id__exact={}" style="text-decoration: none;" title="Show metrics from all {} runs">'
            '<span style="background-color: #0d6efd; color: #ffffff; padding: 2px 8px; border-radius: 12px; font-weight: 700; font-size: 11px; white-space: nowrap;">⚡ {}</span>'
            '</a>',
            url,
            obj.id,
            count,
            label
        )
    runs_count_badge.short_description = "Pipeline Runs"
    runs_count_badge.admin_order_field = "_runs_count"

    def pipeline_run_link(self, obj):
        pr = getattr(obj, 'latest_pipeline_run', None) or obj.pipeline_run
        if not pr:
            return "-"
        url = reverse("admin:research_intelligence_pipelinerun_change", args=[pr.id])
        return format_html('<a href="{}" title="Pipeline Run: {}"><code>{}</code></a>', url, str(pr.id), str(pr.id)[:8] + '...')
    pipeline_run_link.short_description = "Latest Pipeline Run"

    def source_database_badge(self, obj):
        colors = {
            'arxiv': '#b31b1b',
            'openalex': '#5c3d99',
            'lens': '#0d6efd',
            'pubmed': '#198754'
        }
        src = (obj.source_database or 'unknown').lower()
        bg = colors.get(src, '#6c757d')
        return format_html(
            '<span style="background-color: {}; color: #ffffff; padding: 2px 7px; border-radius: 4px; font-weight: 600; font-size: 11px; text-transform: uppercase;">{}</span>',
            bg, src
        )
    source_database_badge.short_description = "Source"
    source_database_badge.admin_order_field = "source_database"

    def source_link_badge(self, obj):
        url = obj.source_url or (obj.resolve_source_url() if hasattr(obj, 'resolve_source_url') else None)
        if not url:
            return format_html('<span style="color: #adb5bd;">-</span>')
        return format_html(
            '<a href="{}" target="_blank" rel="noopener noreferrer" title="{}" style="text-decoration: none;">'
            '<span style="background-color: #198754; color: #ffffff; padding: 2px 8px; border-radius: 12px; font-weight: 600; font-size: 11px; white-space: nowrap;">🌐 Source ↗</span>'
            '</a>',
            url,
            url
        )
    source_link_badge.short_description = "Source Link"


@admin.register(ExtractionDefinition)
class ExtractionDefinitionAdmin(admin.ModelAdmin):
    formfield_overrides = {
        models.JSONField: {'widget': PrettyJSONWidget},
    }
    list_display = ('name', 'exit_metrics_status', 'workspace', 'version', 'llm_model', 'has_postprocessing_code', 'requires_consensus', 'is_active', 'created_at')
    ordering = ('-created_at', '-id')
    list_filter = ('is_active', 'requires_consensus', 'workspace')
    search_fields = ('name', 'exit_metrics', 'system_prompt', 'user_prompt_template', 'postprocessing_code')
    readonly_fields = ('postprocessed_variable_preview',)
    fields = (
        'workspace',
        'name',
        'exit_metrics',
        'system_prompt',
        'user_prompt_template',
        'response_schema',
        'postprocessing_code',
        'postprocessed_variable_preview',
        'llm_model',
        'version',
        'requires_consensus',
        'is_active'
    )

    def changelist_view(self, request, extra_context=None):
        self._ws_exit_metrics_cache = {}
        return super().changelist_view(request, extra_context=extra_context)

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('workspace')

    @admin.display(description="Exit Metrics", ordering="exit_metrics")
    def exit_metrics_status(self, obj):
        if not obj.exit_metrics or not obj.exit_metrics.strip():
            return mark_safe("<span style='color: #94a3b8; font-style: italic;'>-</span>")

        my_metrics = obj.get_exit_metrics_list()
        if not my_metrics:
            return mark_safe("<span style='color: #94a3b8; font-style: italic;'>-</span>")

        if not hasattr(self, '_ws_exit_metrics_cache'):
            self._ws_exit_metrics_cache = {}

        if obj.workspace_id not in self._ws_exit_metrics_cache:
            defs = ExtractionDefinition.objects.filter(workspace_id=obj.workspace_id)
            mapping = {}
            for d in defs:
                for m in d.get_exit_metrics_list():
                    mapping.setdefault(m, []).append(d)
            self._ws_exit_metrics_cache[obj.workspace_id] = mapping

        rendered_badges = []
        for m in my_metrics:
            duplicates = [
                d for d in self._ws_exit_metrics_cache[obj.workspace_id].get(m, [])
                if str(d.id) != str(obj.id)
            ]
            if duplicates:
                conflict_names = ", ".join([d.name for d in duplicates])
                rendered_badges.append(
                    f"<span style='background: #fee2e2; border: 1px solid #ef4444; color: #b91c1c; padding: 2px 7px; border-radius: 4px; font-size: 11px; font-weight: bold; display: inline-block; margin: 1px 2px;' "
                    f"title='COLLISION: \"{m}\" is duplicated in this workspace with {conflict_names}'>"
                    f"🚨 {m} (Duplicate: {conflict_names})</span>"
                )
            else:
                rendered_badges.append(
                    f"<span style='background: #f1f5f9; color: #0369a1; border: 1px solid #cbd5e1; padding: 2px 7px; border-radius: 4px; font-family: monospace; font-size: 11px; font-weight: 600; display: inline-block; margin: 1px 2px;'>"
                    f"{m}</span>"
                )

        return mark_safe("".join(rendered_badges))

    def formfield_for_dbfield(self, db_field, **kwargs):
        if db_field.name == 'postprocessing_code':
            kwargs['widget'] = PostprocessingCodeWidget
        return super().formfield_for_dbfield(db_field, **kwargs)

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        if 'exit_metrics' in form.base_fields:
            default_help = (
                "Comma-separated list of field keys to unpack from extracted data for Signal Score (e.g. 'rigour_score, param1, param2'). "
                "Spaces are automatically stripped. The first key is used for postprocessing naming. "
                "Each metric must be unique across extraction definitions in this workspace."
            )
            if obj and obj.exit_metrics and obj.workspace_id:
                my_metrics = obj.get_exit_metrics_list()
                duplicates = ExtractionDefinition.objects.filter(workspace_id=obj.workspace_id).exclude(pk=obj.pk)
                conflicts = []
                for d in duplicates:
                    shared = set(my_metrics) & set(d.get_exit_metrics_list())
                    if shared:
                        conflicts.append(f"'{d.name}' (shared: {', '.join(sorted(shared))})")
                if conflicts:
                    conflict_str = "; ".join(conflicts)
                    form.base_fields['exit_metrics'].help_text = mark_safe(
                        f"<div style='color: #dc2626; background: #fee2e2; border: 1px solid #ef4444; padding: 6px 10px; border-radius: 4px; font-weight: bold; margin-top: 4px;'>"
                        f"🚨 CONSISTENCY ERROR: One or more exit metrics from this list are already defined in this workspace by {conflict_str}! "
                        f"Please change duplicate values to prevent Signal Score variable collisions."
                        f"</div><div style='margin-top: 4px;'>{default_help}</div>"
                    )
                else:
                    form.base_fields['exit_metrics'].help_text = default_help
            else:
                form.base_fields['exit_metrics'].help_text = default_help

        if 'postprocessing_code' in form.base_fields:
            if obj and obj.name:
                from research_intelligence.tasks.step_6_signal_score.scorer import _sanitize_identifier
                def_slug = _sanitize_identifier(obj.name)
                primary_exit = obj.get_primary_exit_metric()
                primary_var = f"{def_slug}_postprocessed"
                bold_vars = f"<b><code>{primary_var}</code></b>"
                if primary_exit and primary_exit != def_slug:
                    bold_vars += f" and <b><code>{primary_exit}_postprocessed</code></b> (from 1st exit metric)"
                form.base_fields['postprocessing_code'].help_text = mark_safe(
                    f"Optional Python snippet executed on extracted <code>fields_data</code>. "
                    f"The computed value will be directly accessible in <b>Signal Score</b> (Calculate score) as variable: {bold_vars}."
                )
            else:
                form.base_fields['postprocessing_code'].help_text = mark_safe(
                    "Optional Python snippet executed on extracted <code>fields_data</code>. "
                    "The computed value will be directly accessible in <b>Signal Score</b> (Calculate score) as: <b><code>{definition_name}_postprocessed</code></b>."
                )

            if obj:
                available_vars = obj.get_available_postprocessing_variables()
            else:
                from research_intelligence.models.extraction import get_default_postprocessing_variables
                available_vars = get_default_postprocessing_variables()

            form.base_fields['postprocessing_code'].widget = PostprocessingCodeWidget(
                available_variables=available_vars,
                extraction_definition=obj
            )

        return form

    def get_urls(self):
        from django.urls import path
        urls = super().get_urls()
        custom_urls = [
            path(
                '<path:object_id>/test-postprocessing/',
                self.admin_site.admin_view(self.test_postprocessing_view),
                name='research_intelligence_extractiondefinition_test_postprocessing'
            ),
            path(
                'test-postprocessing/',
                self.admin_site.admin_view(self.test_postprocessing_view),
                name='research_intelligence_extractiondefinition_test_postprocessing_generic'
            ),
        ]
        return custom_urls + urls

    def test_postprocessing_view(self, request, object_id=None):
        """
        AJAX endpoint allowing admins to execute a dry-run test of the extraction postprocessing
        Python snippet within the sandboxed scope using deduced or mocked extracted fields.
        """
        import json
        import time
        from django.http import JsonResponse
        from research_intelligence.utils.sandbox import execute_sandboxed_postprocessing, SandboxSecurityError, SandboxExecutionError
        from research_intelligence.models.extraction import get_default_postprocessing_variables

        if request.method != 'POST':
            return JsonResponse({'success': False, 'error': 'POST request required for testing postprocessing code.'}, status=405)

        try:
            payload = json.loads(request.body.decode('utf-8'))
        except Exception:
            payload = request.POST

        code = payload.get('code', '').strip()
        if not code:
            return JsonResponse({
                'success': False,
                'error_type': 'EmptyCodeError',
                'error': 'No Python code snippet was provided for evaluation.',
                'execution_time_ms': 0
            })

        definition = None
        if object_id:
            try:
                definition = self.get_object(request, object_id)
            except Exception:
                definition = None

        # Build mock extracted fields dictionary
        mock_fields = {}
        client_schema = payload.get('schema')
        schema_to_use = None
        if isinstance(client_schema, dict) and 'properties' in client_schema:
            schema_to_use = client_schema
        elif definition and definition.response_schema and isinstance(definition.response_schema, dict):
            schema_to_use = definition.response_schema

        if schema_to_use and isinstance(schema_to_use.get('properties'), dict):
            for prop_k, prop_spec in schema_to_use['properties'].items():
                if not isinstance(prop_k, str) or not prop_k.isidentifier():
                    continue
                p_type = prop_spec.get('type', 'number') if isinstance(prop_spec, dict) else 'number'
                if p_type in ('number', 'float'):
                    mock_fields[prop_k] = 8.5
                elif p_type in ('integer', 'int'):
                    mock_fields[prop_k] = 3
                elif p_type in ('boolean', 'bool'):
                    mock_fields[prop_k] = True
                elif p_type in ('array', 'list'):
                    mock_fields[prop_k] = ["sample_1", "sample_2"]
                elif p_type in ('object', 'dict'):
                    mock_fields[prop_k] = {"key": "sample_value"}
                elif p_type in ('string', 'str'):
                    mock_fields[prop_k] = f"sample_{prop_k}"
                else:
                    mock_fields[prop_k] = 5.0

        # Include exit metrics
        client_exit = payload.get('exit_metrics')
        exit_keys = []
        if client_exit:
            exit_keys = [k.strip() for k in str(client_exit).split(',') if k.strip()]
        elif definition:
            exit_keys = definition.get_exit_metrics_list()

        for em in exit_keys:
            if em and em.isidentifier() and em not in mock_fields:
                mock_fields[em] = 7.5

        if not mock_fields:
            if definition:
                for v in definition.get_available_postprocessing_variables():
                    if v.get('category') in ('Schema Property', 'Exit Metric'):
                        mock_fields[v['name']] = v.get('default', 5.0)
            if not mock_fields:
                mock_fields = {"score": 8.5, "confidence": 0.92, "label": "high_impact"}

        # Custom mock overrides
        custom_mock = payload.get('mock_variables')
        if isinstance(custom_mock, dict):
            mock_fields.update(custom_mock)

        mock_context = {
            "title": "Deep Learning for Scientific Discovery",
            "abstract": "We present a novel benchmark and evaluation protocol...",
            "arxiv_id": "2401.01234",
            "doi": "10.1016/j.jbi.2024.104200"
        }

        t0 = time.perf_counter()
        try:
            result = execute_sandboxed_postprocessing(
                code_snippet=code,
                fields_data=mock_fields,
                context_vars=mock_context,
                timeout_seconds=2.0
            )
            exec_time_ms = round((time.perf_counter() - t0) * 1000, 2)

            if result is None:
                return JsonResponse({
                    'success': False,
                    'error_type': 'NullResultWarning',
                    'error': 'The snippet executed without exceptions but returned None (or did not include a return statement or assignment). Make sure to return a value or dictionary, e.g.: return round(score, 2) or return {"metric": 10}',
                    'execution_time_ms': exec_time_ms,
                    'fields_evaluated': mock_fields
                })

            return JsonResponse({
                'success': True,
                'result': result,
                'result_type': type(result).__name__,
                'execution_time_ms': exec_time_ms,
                'fields_evaluated': mock_fields
            })

        except (SandboxSecurityError, SandboxExecutionError, Exception) as e:
            exec_time_ms = round((time.perf_counter() - t0) * 1000, 2)
            return JsonResponse({
                'success': False,
                'error_type': type(e).__name__,
                'error': str(e),
                'execution_time_ms': exec_time_ms,
                'fields_evaluated': mock_fields
            })

    @admin.display(description="Signal Score Variable Name(s)")
    def postprocessed_variable_preview(self, obj):
        if not obj or not obj.name:
            return mark_safe("<span style='color: #64748b;'>Save this extraction definition to generate variable name preview.</span>")
        from research_intelligence.tasks.step_6_signal_score.scorer import _sanitize_identifier
        def_slug = _sanitize_identifier(obj.name)
        primary_var = f"{def_slug}_postprocessed"
        vars_badges = [
            f"<code style='font-size: 14px; font-weight: bold; background: #0f172a; color: #38bdf8; padding: 3px 8px; border-radius: 4px;'>{primary_var}</code>"
        ]
        primary_exit = obj.get_primary_exit_metric()
        if primary_exit and primary_exit != def_slug:
            vars_badges.append(
                f"<code style='font-size: 14px; font-weight: bold; background: #0f172a; color: #38bdf8; padding: 3px 8px; border-radius: 4px;'>{primary_exit}_postprocessed</code> <small style='color: #64748b;'>(from 1st exit metric)</small>"
            )
        badges_html = " &nbsp;and&nbsp; ".join(vars_badges)

        extra_metrics = obj.get_exit_metrics_list()
        extra_html = ""
        if extra_metrics:
            raw_vars_html = ", ".join([f"<code><b>{m}</b></code>" for m in extra_metrics])
            extra_html = (
                f"<div style='margin-top: 8px; font-size: 12px; color: var(--body-fg, #334155); border-top: 1px dashed var(--hairline-color, #cbd5e1); padding-top: 6px;'>"
                f"📥 Raw exit metric variable(s) passed to Signal Score: {raw_vars_html}"
                f"</div>"
            )

        return mark_safe(
            f"<div style='background: var(--darkened-bg, #f0f9ff); border: 1px solid var(--hairline-color, #bae6fd); "
            f"border-left: 4px solid #0284c7; padding: 12px 16px; border-radius: 6px; font-size: 13px; color: var(--body-fg, #0f172a); max-width: 850px;'>"
            f"💡 In <b>Signal Score</b> (Calculate score), this computed postprocessing value is accessible as: "
            f"{badges_html}"
            f"{extra_html}"
            f"</div>"
        )

    @admin.display(boolean=True, description="Postprocess Code")
    def has_postprocessing_code(self, obj):
        return bool(obj.postprocessing_code and obj.postprocessing_code.strip())


@admin.register(Extraction)
class ExtractionAdmin(admin.ModelAdmin):
    formfield_overrides = {
        models.JSONField: {'widget': PrettyJSONWidget},
    }
    list_display = (
        'paper',
        'extraction_definition',
        'exit_metrics_badge',
        'validation_confidence_badge',
        'workspace',
        'pipeline_run_link',
        'component_run_link',
        'created_at'
    )
    list_select_related = (
        'paper',
        'extraction_definition',
        'workspace'
    )
    ordering = ('-created_at', '-id')
    list_filter = ('validation_status', 'workspace')
    search_fields = ('paper__title', 'category', 'extraction_definition__name')
    readonly_fields = ('exit_metrics_preview', 'extraction_system_prompt', 'extraction_user_prompt_template', 'created_at')

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
                'exit_metrics_preview',
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

    def validation_confidence_badge(self, obj):
        status = (obj.validation_status or "pending").lower()
        score = obj.confidence_score
        
        if score is not None:
            score_formatted = f"{score:.2f}".rstrip('0').rstrip('.') if '.' in f"{score:.2f}" else f"{score}"
            score_str = f" ({score_formatted})"
        else:
            score_str = ""

        if status == 'pass':
            bg = "#198754"
            text_color = "#ffffff"
            label = f"PASS{score_str}"
        elif status == 'warn':
            bg = "#ffc107"
            text_color = "#000000"
            label = f"WARN{score_str}"
        elif status in ('fail', 'failed'):
            bg = "#dc3545"
            text_color = "#ffffff"
            label = f"FAIL{score_str}"
        elif status == 'pending':
            bg = "#6c757d"
            text_color = "#ffffff"
            label = f"PENDING{score_str}"
        else:
            bg = "#dc3545"
            text_color = "#ffffff"
            label = f"{status.upper()}{score_str}"

        return format_html(
            '<span style="background-color: {}; color: {}; padding: 4px 10px; border-radius: 12px; '
            'font-size: 11px; font-weight: 600; display: inline-block; white-space: nowrap; '
            'box-shadow: 0 1px 2px rgba(0,0,0,0.1); text-transform: uppercase;">{}</span>',
            bg, text_color, label
        )
    validation_confidence_badge.short_description = "Validation & Confidence"
    validation_confidence_badge.admin_order_field = "confidence_score"

    def pipeline_run_link(self, obj):
        pr = None
        if obj.paper:
            pr = getattr(obj.paper, 'latest_pipeline_run', None) or obj.paper.pipeline_run
        if not pr and obj.workspace:
            pr = PipelineRun.objects.filter(workspace=obj.workspace).order_by('-started_at').first()
        if not pr:
            return "-"
        url = reverse("admin:research_intelligence_pipelinerun_change", args=[pr.id])
        return format_html('<a href="{}" title="Pipeline Run: {}"><code>{}</code></a>', url, str(pr.id), str(pr.id)[:8] + '...')
    pipeline_run_link.short_description = "Pipeline Run"

    def component_run_link(self, obj):
        cr = None
        pr = None
        if obj.paper:
            pr = getattr(obj.paper, 'latest_pipeline_run', None) or obj.paper.pipeline_run
        if pr:
            cr = pr.component_runs.filter(
                Q(step_type='extraction') | Q(component_name__icontains='extract')
            ).order_by('-started_at').first()
            if not cr:
                cr = pr.component_runs.order_by('-started_at').first()
        if not cr and obj.workspace:
            cr = ComponentRun.objects.filter(
                pipeline_run__workspace=obj.workspace,
                step_type='extraction'
            ).order_by('-started_at').first()
        if not cr:
            return "-"
        url = reverse("admin:research_intelligence_componentrun_change", args=[cr.id])
        return format_html('<a href="{}" title="Component Run: {}"><code>{}</code></a>', url, str(cr.id), str(cr.id)[:8] + '...')
    component_run_link.short_description = "Component Run"

    def exit_metrics_badge(self, obj):
        metric_str = obj.exit_metric
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
    exit_metrics_badge.short_description = "Exit Metrics / Output"

    def exit_metrics_preview(self, obj):
        metric_str = obj.exit_metric
        return format_html('<strong style="font-size: 1.1em; color: #0d6efd;">{}</strong>', metric_str)
    exit_metrics_preview.short_description = "Exit Metrics"

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
    list_display = (
        'metric_detail_link',
        'paper_display',
        'workspace_link',
        'pipeline_run_link',
        'screening_status_badge',
        'metrics_preview',
        'signal_score_badge',
        'created_at'
    )
    list_display_links = ('metric_detail_link',)
    ordering = ('-created_at', '-id')
    list_select_related = ('paper', 'pipeline_run', 'workspace')
    list_filter = ('screening_status', 'is_evaluation_benchmark', 'workspace', 'pipeline_run')
    search_fields = (
        'paper__title', 'paper__authors', 'paper__doi', 'paper__arxiv_id',
        'pipeline_run__id', 'abstract_screening_reasoning', 'full_text_screening_reasoning'
    )
    readonly_fields = (
        'id', 'created_at', 'paper_detail_link', 'pipeline_run_detail_link',
        'abstract_screening_reasoning_display', 'full_text_screening_reasoning_display'
    )

    fieldsets = (
        ('Review & Ingestion Context', {
            'fields': (
                'workspace',
                'pipeline_run',
                'pipeline_run_detail_link',
                'paper',
                'paper_detail_link',
                'created_at'
            )
        }),
        ('Screening Decision & Verification', {
            'fields': (
                'screening_status',
                'abstract_screening_reasoning_display',
                'full_text_screening_reasoning_display',
                'is_evaluation_benchmark',
                'evaluation_label'
            )
        }),
        ('Composite Signal Score Evaluation', {
            'fields': (
                'signal_score',
                'signal_score_details'
            ),
            'description': 'Composite score evaluated by sandboxed Python AST formula.'
        }),
        ('Dynamic Extracted Variables Matrix', {
            'fields': ('metrics_data',),
            'description': 'Dictionary of all normalized parameters and scores extracted across pipeline stages.'
        }),
    )

    def abstract_screening_reasoning_display(self, obj):
        if not obj.abstract_screening_reasoning:
            return mark_safe('<span style="color: #adb5bd; font-style: italic;">No rationale for abstract stage</span>')
        return format_html(
            '<div style="background: #f0fbfc; border-left: 4px solid #0dcaf0; padding: 8px 12px; border-radius: 4px; font-size: 13px; line-height: 1.5; color: #212529;">'
            '<strong style="color: #055160;">📄 Abstract Screening Reasoning:</strong><br/><div style="margin-top: 4px;">{}</div>'
            '</div>',
            obj.abstract_screening_reasoning
        )
    abstract_screening_reasoning_display.short_description = "Abstract Screening Reasoning"

    def full_text_screening_reasoning_display(self, obj):
        if not obj.full_text_screening_reasoning:
            return mark_safe('<span style="color: #adb5bd; font-style: italic;">No rationale for full-text stage (e.g. rejected at abstract stage)</span>')
        return format_html(
            '<div style="background: #f0fdf4; border-left: 4px solid #198754; padding: 8px 12px; border-radius: 4px; font-size: 13px; line-height: 1.5; color: #212529;">'
            '<strong style="color: #0f5132;">📑 Full-Text Screening Reasoning:</strong><br/><div style="margin-top: 4px;">{}</div>'
            '</div>',
            obj.full_text_screening_reasoning
        )
    full_text_screening_reasoning_display.short_description = "Full-Text Screening Reasoning"

    def metric_detail_link(self, obj):
        url = reverse("admin:research_intelligence_papermetric_change", args=[obj.id])
        return format_html(
            '<a href="{}" style="font-weight: 700; color: #0d6efd; display: inline-flex; align-items: center; gap: 4px; text-decoration: none;" title="Open Metric Details (ID: {})">'
            '<span style="background: #e7f1ff; color: #0d6efd; border: 1px solid #b6d4fe; padding: 2px 7px; border-radius: 4px; font-size: 11px; white-space: nowrap;">📊 Detal ({})</span>'
            '</a>',
            url,
            str(obj.id),
            str(obj.id)[:8]
        )
    metric_detail_link.short_description = "Metric Detail"
    metric_detail_link.admin_order_field = "id"

    def workspace_link(self, obj):
        ws = obj.workspace or (obj.paper.workspace if obj.paper else None)
        if not ws:
            return mark_safe('<span style="color: #adb5bd; font-size: 11px;">-</span>')
        url = reverse("admin:research_intelligence_workspace_change", args=[ws.id])
        return format_html(
            '<a href="{}" style="font-weight: 600; color: #212529; text-decoration: none;" title="Workspace: {}">'
            '🏢 {}'
            '</a>',
            url,
            ws.name,
            ws.name[:25] + ("..." if len(ws.name) > 25 else "")
        )
    workspace_link.short_description = "Workspace"
    workspace_link.admin_order_field = "workspace__name"

    def paper_display(self, obj):
        if not obj.paper:
            return "-"
        url = reverse("admin:research_intelligence_paper_change", args=[obj.paper.id])
        src_tag = f" <span style='font-size: 10px; color: #6c757d; text-transform: uppercase;'>[{obj.paper.source_database}]</span>" if getattr(obj.paper, 'source_database', None) else ""
        return format_html(
            '<a href="{}" style="font-weight: 600; color: #0d6efd;" title="View Paper Details">{}</a>{}',
            url,
            obj.paper.title[:65] + ("..." if len(obj.paper.title) > 65 else ""),
            mark_safe(src_tag)
        )
    paper_display.short_description = "Paper"
    paper_display.admin_order_field = "paper__title"

    def benchmark_badge(self, obj):
        if not obj.is_evaluation_benchmark:
            return format_html('<span style="color: #adb5bd; font-size: 11px;">-</span>')
        label = f" ({obj.evaluation_label.upper()})" if obj.evaluation_label else ""
        return format_html(
            '<span style="background-color: #6f42c1; color: white; padding: 2px 7px; border-radius: 10px; font-size: 11px; font-weight: 600;">🎯 Benchmark{}</span>',
            label
        )
    benchmark_badge.short_description = "Benchmark"
    benchmark_badge.admin_order_field = "is_evaluation_benchmark"

    def paper_detail_link(self, obj):
        if not obj.paper:
            return "-"
        url = reverse("admin:research_intelligence_paper_change", args=[obj.paper.id])
        return format_html('<a href="{}" class="button" target="_blank" style="margin-top: 4px;">📖 Open Paper Detail Form</a>', url)
    paper_detail_link.short_description = "Open Paper in Admin"

    def pipeline_run_detail_link(self, obj):
        pr = obj.pipeline_run or (obj.paper.pipeline_run if obj.paper else None)
        if not pr:
            return "-"
        url = reverse("admin:research_intelligence_pipelinerun_change", args=[pr.id])
        return format_html('<a href="{}" class="button" target="_blank" style="margin-top: 4px;">⚡ Open PipelineRun Change Form</a>', url)
    pipeline_run_detail_link.short_description = "Open Pipeline Run in Admin"

    def pipeline_run_link(self, obj):
        pr = obj.pipeline_run
        if not pr and obj.paper:
            pr = obj.paper.pipeline_run
        if not pr:
            return "-"
        url = reverse("admin:research_intelligence_pipelinerun_change", args=[pr.id])
        return format_html('<a href="{}" title="Pipeline Run: {}"><code>{}</code></a>', url, str(pr.id), str(pr.id)[:8] + '...')
    pipeline_run_link.short_description = "Pipeline Run"
    pipeline_run_link.admin_order_field = "pipeline_run"

    def screening_status_badge(self, obj):
        colors = {
            'pending': '#6c757d',
            'abstract_passed': '#0dcaf0',
            'full_text_passed': '#198754',
            'accepted': '#198754',
            'borderline': '#ffc107',
            'rejected': '#dc3545',
            'withdrawn': '#6c757d',
        }
        labels = {
            'pending': 'Pending',
            'abstract_passed': 'Abstract Passed',
            'full_text_passed': 'Full Text Passed',
            'accepted': 'Accepted',
            'borderline': 'Borderline (Human Review)',
            'rejected': 'Rejected',
            'withdrawn': 'Withdrawn by Authors'
        }
        status = obj.screening_status or 'pending'
        bg = colors.get(status, '#6c757d')
        text_color = '#000000' if bg in ['#ffc107', '#0dcaf0'] else '#ffffff'
        return render_badge(labels.get(status, status), bg, text_color)
    screening_status_badge.short_description = "Screening Status"
    screening_status_badge.admin_order_field = "screening_status"

    def signal_score_badge(self, obj):
        if obj.signal_score is None:
            return mark_safe('<span style="color: #6c757d;">-</span>')
        try:
            score = float(obj.signal_score)
            score_str = f"{score:.2f}"
        except Exception:
            score_str = str(obj.signal_score)
            score = 0.0

        if score >= 75.0:
            bg = "#198754"  # emerald green
        elif score >= 50.0:
            bg = "#0d6efd"  # primary blue
        elif score >= 25.0:
            bg = "#fd7e14"  # orange
        else:
            bg = "#6c757d"  # gray

        return format_html(
            '<span style="background-color: {}; color: #ffffff; padding: 3px 8px; border-radius: 4px; font-weight: bold; font-size: 12px; white-space: nowrap; display: inline-block;">⚡&nbsp;{}</span>',
            bg, score_str
        )
    signal_score_badge.short_description = "Signal Score"
    signal_score_badge.admin_order_field = "signal_score"

    def _format_metric_badge(self, val):
        if val is None:
            return '<span style="color: #adb5bd; font-size: 11px;">-</span>'

        if isinstance(val, bool):
            if val:
                return '<span style="background-color: #d1e7dd; color: #0f5132; border: 1px solid #badbcc; padding: 1px 6px; border-radius: 4px; font-weight: 700; font-size: 10px;">✅ PASS</span>'
            return '<span style="background-color: #f8d7da; color: #842029; border: 1px solid #f5c2c7; padding: 1px 6px; border-radius: 4px; font-weight: 700; font-size: 10px;">❌ FAIL</span>'

        if isinstance(val, (int, float)):
            if isinstance(val, float) and val.is_integer():
                val_str = str(int(val))
            elif isinstance(val, float):
                val_str = f"{val:.2f}"
            else:
                val_str = str(val)
            return format_html(
                '<span style="background-color: #cff4fc; color: #055160; border: 1px solid #b6effb; padding: 1px 6px; border-radius: 4px; font-weight: 700; font-size: 11px; font-family: monospace;">{}</span>',
                val_str
            )

        if isinstance(val, dict):
            for sub_key in ('passed', 'success', 'status', 'decision_category', 'score', 'value'):
                if sub_key in val:
                    return self._format_metric_badge(val[sub_key])
            return '<span style="background-color: #e2e3e5; color: #41464b; border: 1px solid #d3d6d8; padding: 1px 5px; border-radius: 3px; font-size: 10px;">[Obiekt]</span>'

        if isinstance(val, list):
            return format_html(
                '<span style="background-color: #e2e3e5; color: #41464b; border: 1px solid #d3d6d8; padding: 1px 5px; border-radius: 3px; font-size: 10px;">{} poz.</span>',
                len(val)
            )

        val_lower = str(val).strip().lower()
        if val_lower in ('true', 'passed', 'pass', 'accepted', 'yes'):
            return '<span style="background-color: #d1e7dd; color: #0f5132; border: 1px solid #badbcc; padding: 1px 6px; border-radius: 4px; font-weight: 700; font-size: 10px;">✅ PASS</span>'
        elif val_lower in ('false', 'failed', 'fail', 'rejected', 'no'):
            return '<span style="background-color: #f8d7da; color: #842029; border: 1px solid #f5c2c7; padding: 1px 6px; border-radius: 4px; font-weight: 700; font-size: 10px;">❌ FAIL</span>'
        elif val_lower in ('borderline', 'hitl', 'review'):
            return '<span style="background-color: #fff3cd; color: #664d03; border: 1px solid #ffecb5; padding: 1px 6px; border-radius: 4px; font-weight: 700; font-size: 10px;">⚠️ BORDERLINE</span>'

        try:
            num = float(val_lower)
            formatted_num = str(int(num)) if num.is_integer() else f"{num:.2f}"
            return format_html(
                '<span style="background-color: #cff4fc; color: #055160; border: 1px solid #b6effb; padding: 1px 6px; border-radius: 4px; font-weight: 700; font-size: 11px; font-family: monospace;">{}</span>',
                formatted_num
            )
        except (ValueError, TypeError):
            pass

        short_val = str(val)[:20] + ("..." if len(str(val)) > 20 else "")
        return format_html(
            '<span style="background-color: #f8f9fa; color: #495057; border: 1px solid #dee2e6; padding: 1px 6px; border-radius: 4px; font-weight: 600; font-size: 11px;">{}</span>',
            short_val
        )

    def metrics_preview(self, obj):
        if not obj.metrics_data:
            return mark_safe('<span style="color: #adb5bd; font-size: 11px;">-</span>')

        excluded_keys = {
            'reasoning', 'evidence_quotes', 'evidence_quote', 'dynamic_data',
            'system_prompt', 'user_prompt', 'raw_output', 'error',
            'justification', 'decision_category'
        }

        filtered_items = []
        for k, v in obj.metrics_data.items():
            k_lower = str(k).lower()
            if k_lower in excluded_keys:
                continue
            # Hide test-prefixed alias duplicates (e.g. test_e2e_sched_..._fit_score)
            if 'test_' in k_lower:
                continue
            filtered_items.append((k, v))

        # Fallback: if all metrics had 'test_' and filtered_items is empty, show them without excluding
        if not filtered_items and obj.metrics_data:
            for k, v in obj.metrics_data.items():
                if str(k).lower() not in excluded_keys:
                    filtered_items.append((k, v))

        if not filtered_items:
            return mark_safe('<span style="color: #6c757d; font-size: 11px;">(Detale w formularzu)</span>')

        rendered_lines = []
        for k, v in filtered_items[:6]:
            badge_html = self._format_metric_badge(v)
            clean_key = escape(str(k))
            rendered_lines.append(
                f'<div style="margin: 2px 0; display: flex; align-items: center; gap: 5px; font-size: 11px; white-space: nowrap;">'
                f'<strong style="color: #495057;">{clean_key}:</strong> {badge_html}'
                f'</div>'
            )

        if len(filtered_items) > 6:
            more_count = len(filtered_items) - 6
            rendered_lines.append(f'<div style="color: #6c757d; font-size: 10px; margin-top: 1px;">+ {more_count} more in detail...</div>')

        return mark_safe("".join(rendered_lines))
    metrics_preview.short_description = "Extracted Metrics"


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
    list_display = ('email', 'name', 'workspace', 'subscribed_reports_display', 'is_active', 'created_at')
    list_filter = ('subscription_type', 'is_active', 'workspace', 'created_at')
    search_fields = ('email', 'name', 'workspace__name')
    readonly_fields = ('created_at',)
    ordering = ('-created_at', '-id')

    @admin.display(description="Subscribed Feeds & Reports", ordering="subscription_type")
    def subscribed_reports_display(self, obj):
        """
        Renders a clean, multi-line stacked badge layout showing exactly what notifications
        and report types this user receives.
        """
        if obj.subscription_type == 'all':
            return format_html(
                '<div style="display: flex; flex-direction: column; gap: 4px; line-height: 1.25; min-width: 260px;">'
                '  <div style="font-weight: 700; color: #6f42c1; font-size: 11px; margin-bottom: 2px;">🌐 ALL NOTIFICATIONS (Full Broadcast):</div>'
                '  <div><span style="background: #198754; color: white; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 600;">📊 Result Report</span> <span style="font-size: 11px; color: #6c757d;">— Findings & Scorecard</span></div>'
                '  <div><span style="background: #dc3545; color: white; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 600;">🚨 Pipeline Errors</span> <span style="font-size: 11px; color: #6c757d;">— Stage Crash Alerts</span></div>'
                '  <div><span style="background: #0d6efd; color: white; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 600;">⚡ Pipeline Status</span> <span style="font-size: 11px; color: #6c757d;">— DAG Execution Digest</span></div>'
                '</div>'
            )
        elif obj.subscription_type == 'result_report':
            return format_html(
                '<div style="display: flex; flex-direction: column; gap: 3px; line-height: 1.25;">'
                '  <div><span style="background: #198754; color: white; padding: 3px 8px; border-radius: 4px; font-size: 11px; font-weight: 600;">📊 Result Report</span></div>'
                '  <div style="font-size: 11px; color: #6c757d;">Scorecards, Parameter Matrix & Findings</div>'
                '</div>'
            )
        elif obj.subscription_type == 'pipeline_errors':
            return format_html(
                '<div style="display: flex; flex-direction: column; gap: 3px; line-height: 1.25;">'
                '  <div><span style="background: #dc3545; color: white; padding: 3px 8px; border-radius: 4px; font-size: 11px; font-weight: 600;">🚨 Pipeline Errors</span></div>'
                '  <div style="font-size: 11px; color: #6c757d;">Immediate Incident & Stage Failure Alerts</div>'
                '</div>'
            )
        elif obj.subscription_type == 'pipeline_status':
            return format_html(
                '<div style="display: flex; flex-direction: column; gap: 3px; line-height: 1.25;">'
                '  <div><span style="background: #0d6efd; color: white; padding: 3px 8px; border-radius: 4px; font-size: 11px; font-weight: 600;">⚡ Pipeline Status</span></div>'
                '  <div style="font-size: 11px; color: #6c757d;">DAG Progression, Throughput & Resource Digest</div>'
                '</div>'
            )
        else:
            return render_badge(f"📋 {obj.get_subscription_type_display()}", '#6c757d')

    # Alias for backwards compatibility
    subscription_type_badge = subscribed_reports_display




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


@admin.register(LLMUsageRecord)
class LLMUsageRecordAdmin(admin.ModelAdmin):
    """
    State-of-the-art Persistent Financial & Token Ledger for Django Admin.
    Guarantees permanent audit traceability across all LLM inference calls even after Workspace or Pipeline deletion.
    """
    formfield_overrides = {
        models.JSONField: {'widget': PrettyJSONWidget},
    }
    list_display = (
        'formatted_timestamp',
        'operation_type_badge',
        'llm_model_badge',
        'workspace_display',
        'tokens_in_fmt',
        'tokens_out_fmt',
        'total_tokens_fmt',
        'usd_cost_fmt',
        'user_display',
        'pipeline_run_link',
    )
    ordering = ('-timestamp', '-id')
    list_filter = ('operation_type', 'llm_model', 'llm_provider', 'timestamp')
    search_fields = (
        'workspace_name_snapshot',
        'workspace_id_snapshot',
        'user_username_snapshot',
        'pipeline_run_id',
        'component_run_id',
        'llm_model'
    )
    readonly_fields = [f.name for f in LLMUsageRecord._meta.fields]
    date_hierarchy = 'timestamp'

    def has_add_permission(self, request):
        return False  # Immutable audit ledger

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser

    def formatted_timestamp(self, obj):
        return obj.timestamp.strftime("%Y-%m-%d %H:%M:%S")
    formatted_timestamp.short_description = "Timestamp"
    formatted_timestamp.admin_order_field = "timestamp"

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        from django.db.models import Sum, Count

        # 1. Super-fast database aggregation across the current filtered queryset
        cl = self.get_changelist_instance(request)
        try:
            filtered_qs = cl.get_queryset(request)
        except Exception:
            filtered_qs = self.get_queryset(request)

        filtered_stats = filtered_qs.aggregate(
            prompt_tokens=Sum('tokens_in'),
            output_tokens=Sum('tokens_out'),
            total_tokens=Sum('total_tokens'),
            total_cost=Sum('usd_cost'),
            total_count=Count('id')
        )

        # 2. All-time global totals across the entire platform
        all_time_stats = LLMUsageRecord.objects.aggregate(
            prompt_tokens=Sum('tokens_in'),
            output_tokens=Sum('tokens_out'),
            total_tokens=Sum('total_tokens'),
            total_cost=Sum('usd_cost'),
            total_count=Count('id')
        )

        f_count = filtered_stats['total_count'] or 0
        a_count = all_time_stats['total_count'] or 0

        extra_context['ledger_stats'] = {
            'filtered': {
                'prompt_tokens': filtered_stats['prompt_tokens'] or 0,
                'output_tokens': filtered_stats['output_tokens'] or 0,
                'total_tokens': filtered_stats['total_tokens'] or 0,
                'total_cost': float(filtered_stats['total_cost'] or 0.0),
                'total_count': f_count,
            },
            'all_time': {
                'prompt_tokens': all_time_stats['prompt_tokens'] or 0,
                'output_tokens': all_time_stats['output_tokens'] or 0,
                'total_tokens': all_time_stats['total_tokens'] or 0,
                'total_cost': float(all_time_stats['total_cost'] or 0.0),
                'total_count': a_count,
            },
            'is_filtered': (f_count != a_count)
        }

        return super().changelist_view(request, extra_context=extra_context)

    def operation_type_badge(self, obj):
        color_map = {
            'abstract_screening': '#0d6efd',
            'full_text_screening': '#6f42c1',
            'extraction': '#198754',
            'signal_score': '#fd7e14',
            'reporting': '#20c997',
            'chat': '#d63384',
            'mcp': '#0dcaf0',
            'other': '#6c757d',
        }
        color = color_map.get(obj.operation_type, '#6c757d')
        label = obj.get_operation_type_display() if hasattr(obj, 'get_operation_type_display') else obj.operation_type
        return format_html(
            f'<span style="background-color: {color}; color: white; padding: 3px 8px; border-radius: 4px; font-weight: bold; font-size: 11px; white-space: nowrap; display: inline-block;">{label}</span>'
        )
    operation_type_badge.short_description = "Operation"
    operation_type_badge.admin_order_field = "operation_type"

    def llm_model_badge(self, obj):
        model_short = obj.llm_model.replace("google/", "").replace("openai/", "").replace("anthropic/", "")
        return format_html(
            f'<span style="font-family: monospace; font-size: 12px; background: #f8fafc; color: #0f172a; padding: 3px 8px; border-radius: 4px; border: 1px solid #cbd5e1; white-space: nowrap; display: inline-block; font-weight: 500;">{model_short}</span>'
        )
    llm_model_badge.short_description = "Model"
    llm_model_badge.admin_order_field = "llm_model"

    def workspace_display(self, obj):
        if obj.workspace:
            url = reverse("admin:research_intelligence_workspace_change", args=[obj.workspace.id])
            return format_html(f'<a href="{url}" style="font-weight: 500; white-space: nowrap;">🏢 {escape(obj.workspace.name)}</a>')
        if obj.workspace_name_snapshot:
            return format_html(f'<span style="color: #6c757d; font-style: italic; white-space: nowrap;">🗑️ {escape(obj.workspace_name_snapshot)} <span style="font-size: 10px;">(deleted)</span></span>')
        return format_html('<span style="color: #adb5bd;">-</span>')
    workspace_display.short_description = "Workspace"
    workspace_display.admin_order_field = "workspace_name_snapshot"

    def tokens_in_fmt(self, obj):
        return f"{obj.tokens_in:,}"
    tokens_in_fmt.short_description = "Prompt In"
    tokens_in_fmt.admin_order_field = "tokens_in"

    def tokens_out_fmt(self, obj):
        return f"{obj.tokens_out:,}"
    tokens_out_fmt.short_description = "Output"
    tokens_out_fmt.admin_order_field = "tokens_out"

    def total_tokens_fmt(self, obj):
        return format_html(f'<strong style="white-space: nowrap;">{obj.total_tokens:,}</strong>')
    total_tokens_fmt.short_description = "Total Tokens"
    total_tokens_fmt.admin_order_field = "total_tokens"

    def usd_cost_fmt(self, obj):
        return format_html(f'<span style="color: #198754; font-weight: 600; white-space: nowrap;">${obj.usd_cost:.5f}</span>')
    usd_cost_fmt.short_description = "Cost (USD)"
    usd_cost_fmt.admin_order_field = "usd_cost"

    def user_display(self, obj):
        return obj.user_username_snapshot or (obj.user.username if obj.user else "System")
    user_display.short_description = "User"

    def pipeline_run_link(self, obj):
        if not obj.pipeline_run_id:
            return "-"
        try:
            url = reverse("admin:research_intelligence_pipelinerun_change", args=[obj.pipeline_run_id])
            return format_html(f'<a href="{url}" style="font-family: monospace; font-size: 11px; white-space: nowrap;">{obj.pipeline_run_id[:8]}...</a>')
        except Exception:
            return format_html(f'<span style="font-family: monospace; font-size: 11px; color: #6c757d; white-space: nowrap;">{obj.pipeline_run_id[:8]}...</span>')
    pipeline_run_link.short_description = "Pipeline"


@admin.register(DocumentRegistry)
class DocumentRegistryAdmin(admin.ModelAdmin):
    formfield_overrides = {
        models.JSONField: {'widget': PrettyJSONWidget},
    }
    list_display = (
        'title_snippet',
        'doi_display',
        'arxiv_id_display',
        'primary_source_badge',
        'source_link_badge',
        'file_size_formatted',
        'ocr_status_badge',
        'access_count_badge',
        'last_accessed_at_display',
    )
    search_fields = ('title', 'doi', 'arxiv_id', 'source_url', 'sha256_hash', 'canonical_pdf_path')
    list_filter = ('primary_source', 'ocr_provider', 'first_ingested_at', 'last_accessed_at')
    readonly_fields = ('id', 'sha256_hash', 'first_ingested_at', 'last_accessed_at', 'access_count')

    fieldsets = (
        ('Document Identity & Core Hashes', {
            'fields': (
                'id',
                'title',
                'doi',
                'arxiv_id',
                'source_url',
                'sha256_hash',
                'primary_source',
            )
        }),
        ('Canonical Storage & Layout Cache', {
            'fields': (
                'canonical_pdf_path',
                'pdf_file_size_bytes',
                'ocr_provider',
                'canonical_ocr_md_path',
            )
        }),
        ('Usage & Lifetime Metrics', {
            'fields': (
                'access_count',
                'first_ingested_at',
                'last_accessed_at',
            )
        }),
        ('Source Metadata (meta)', {
            'fields': ('meta',),
            'description': 'Raw JSON metadata payload ingested from external repository (arXiv Atom XML or OpenAlex).'
        }),
    )

    def changelist_view(self, request, extra_context=None):
        from django.db.models import Sum, Count, Q
        extra_context = extra_context or {}

        cl = self.get_changelist_instance(request)
        queryset = cl.get_queryset(request)

        # 1. Aggregation for filtered view (single fast SQL query)
        filtered_stats = queryset.aggregate(
            total_docs=Count('id'),
            total_size_bytes=Sum('pdf_file_size_bytes'),
            total_access_count=Sum('access_count'),
            reused_docs=Count('id', filter=Q(access_count__gt=1)),
            ocr_docs=Count('id', filter=~Q(canonical_ocr_md_path__exact='') & Q(canonical_ocr_md_path__isnull=False)),
        )

        # 2. All-time global totals (single fast SQL query)
        all_time_stats = DocumentRegistry.objects.aggregate(
            total_docs=Count('id'),
            total_size_bytes=Sum('pdf_file_size_bytes'),
            total_access_count=Sum('access_count'),
            reused_docs=Count('id', filter=Q(access_count__gt=1)),
            ocr_docs=Count('id', filter=~Q(canonical_ocr_md_path__exact='') & Q(canonical_ocr_md_path__isnull=False)),
        )

        f_total = filtered_stats['total_docs'] or 0
        a_total = all_time_stats['total_docs'] or 0
        f_reused = filtered_stats['reused_docs'] or 0
        a_reused = all_time_stats['reused_docs'] or 0
        f_ocr = filtered_stats['ocr_docs'] or 0
        a_ocr = all_time_stats['ocr_docs'] or 0
        f_hits = filtered_stats['total_access_count'] or 0
        a_hits = all_time_stats['total_access_count'] or 0

        f_size = filtered_stats['total_size_bytes'] or 0
        a_size = all_time_stats['total_size_bytes'] or 0

        extra_context['doc_registry_stats'] = {
            'filtered': {
                'total_docs': f_total,
                'total_size_bytes': f_size,
                'total_size_formatted': format_human_readable_bytes(f_size),
                'total_access_count': f_hits,
                'reused_docs': f_reused,
                'reused_pct': round((f_reused / f_total * 100.0), 1) if f_total > 0 else 0.0,
                'saved_downloads': max(0, f_hits - f_total),
                'ocr_docs': f_ocr,
                'ocr_pct': round((f_ocr / f_total * 100.0), 1) if f_total > 0 else 0.0,
            },
            'all_time': {
                'total_docs': a_total,
                'total_size_bytes': a_size,
                'total_size_formatted': format_human_readable_bytes(a_size),
                'total_access_count': a_hits,
                'reused_docs': a_reused,
                'reused_pct': round((a_reused / a_total * 100.0), 1) if a_total > 0 else 0.0,
                'saved_downloads': max(0, a_hits - a_total),
                'ocr_docs': a_ocr,
                'ocr_pct': round((a_ocr / a_total * 100.0), 1) if a_total > 0 else 0.0,
            },
            'is_filtered': (f_total != a_total)
        }

        return super().changelist_view(request, extra_context=extra_context)

    def title_snippet(self, obj):
        return obj.title[:60] + "..." if len(obj.title) > 60 else obj.title
    title_snippet.short_description = "Title"

    def doi_display(self, obj):
        if not obj.doi:
            return format_html('<span style="color: #adb5bd;">-</span>')
        return format_html('<span style="font-family: monospace; font-size: 11px; white-space: nowrap;">{}</span>', obj.doi)
    doi_display.short_description = "DOI"
    doi_display.admin_order_field = "doi"

    def arxiv_id_display(self, obj):
        if not obj.arxiv_id:
            return format_html('<span style="color: #adb5bd;">-</span>')
        return format_html('<span style="font-family: monospace; font-size: 11px; white-space: nowrap; color: #b31b1b; font-weight: 500;">arXiv:{}</span>', obj.arxiv_id)
    arxiv_id_display.short_description = "arXiv ID"
    arxiv_id_display.admin_order_field = "arxiv_id"

    def primary_source_badge(self, obj):
        color_map = {
            'arxiv': '#b31b1b',
            'openalex': '#0d6efd',
            'lens': '#6f42c1',
            'pubmed': '#198754',
        }
        color = color_map.get((obj.primary_source or '').lower(), '#6c757d')
        return render_badge((obj.primary_source or 'source').upper(), color)
    primary_source_badge.short_description = "Source"
    primary_source_badge.admin_order_field = "primary_source"

    def source_link_badge(self, obj):
        url = obj.source_url
        if not url:
            from research_intelligence.utils.source_url import resolve_paper_source_url
            url = resolve_paper_source_url(obj)
        if not url:
            return format_html('<span style="color: #adb5bd;">-</span>')
        return format_html(
            '<a href="{}" target="_blank" rel="noopener noreferrer" title="{}" style="text-decoration: none;">'
            '<span style="background-color: #198754; color: #ffffff; padding: 2px 8px; border-radius: 12px; font-weight: 600; font-size: 11px; white-space: nowrap;">🌐 Source ↗</span>'
            '</a>',
            url,
            url
        )
    source_link_badge.short_description = "Source Link"

    def file_size_formatted(self, obj):
        formatted = format_human_readable_bytes(obj.pdf_file_size_bytes)
        return format_html('<span style="white-space: nowrap; font-family: monospace;">{}</span>', formatted)
    file_size_formatted.short_description = "PDF Size"
    file_size_formatted.admin_order_field = "pdf_file_size_bytes"

    def ocr_status_badge(self, obj):
        if obj.canonical_ocr_md_path:
            return render_badge(obj.ocr_provider or "OCR OK", "#198754")
        return format_html('<span style="color: #6c757d; font-size: 11px; white-space: nowrap;">No OCR</span>')
    ocr_status_badge.short_description = "OCR Layout"

    def access_count_badge(self, obj):
        color = "#17a2b8" if obj.access_count > 1 else ("#6c757d" if obj.access_count == 1 else "#dc3545")
        return render_badge(f"⚡ {obj.access_count} hits", color)
    access_count_badge.short_description = "Reused"
    access_count_badge.admin_order_field = "access_count"

    def last_accessed_at_display(self, obj):
        if not obj.last_accessed_at:
            return "-"
        return format_html('<span style="white-space: nowrap; font-size: 11px;">{}</span>', obj.last_accessed_at.strftime("%Y-%m-%d %H:%M"))
    last_accessed_at_display.short_description = "Last Accessed"
    last_accessed_at_display.admin_order_field = "last_accessed_at"


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


