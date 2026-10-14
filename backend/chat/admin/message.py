from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from chat.models import PaperChatMessage


class PaperChatMessageInline(admin.TabularInline):
    model = PaperChatMessage
    extra = 0
    readonly_fields = ('id', 'sender', 'status', 'llm_model', 'tokens_in', 'tokens_out', 'total_tokens', 'usd_cost', 'created_at', 'question_snippet', 'message_snippet')
    fields = ('sender', 'status', 'llm_model', 'tokens_in', 'tokens_out', 'total_tokens', 'usd_cost', 'question_snippet', 'message_snippet', 'created_at')
    can_delete = True

    def question_snippet(self, obj):
        return obj.question[:50] + "..." if len(obj.question) > 50 else obj.question
    question_snippet.short_description = "Question"

    def message_snippet(self, obj):
        return obj.message[:50] + "..." if len(obj.message) > 50 else obj.message
    message_snippet.short_description = "Answer"


# PaperChatMessage is hidden from Django admin
class PaperChatMessageAdmin(admin.ModelAdmin):
    list_display = ('id_snippet', 'session_link', 'sender', 'status_badge', 'llm_model', 'tokens_total', 'usd_cost_display', 'created_at')
    list_filter = ('status', 'sender', 'llm_model', 'created_at')
    search_fields = ('question', 'message', 'session__title', 'session__paper__title')
    readonly_fields = ('id', 'session', 'celery_task_id', 'tokens_in', 'tokens_out', 'total_tokens', 'usd_cost', 'llm_model', 'created_at', 'completed_at')

    def id_snippet(self, obj):
        return str(obj.id)[:8] + "..."
    id_snippet.short_description = "Message ID"

    def session_link(self, obj):
        try:
            url = reverse("admin:chat_paperchatsession_change", args=[obj.session.id])
            return format_html('<a href="{}">{}</a>', url, obj.session.title[:40])
        except Exception:
            return str(obj.session.title[:40])
    session_link.short_description = "Session"

    def status_badge(self, obj):
        colors = {
            'completed': '#198754',
            'processing': '#0d6efd',
            'pending': '#ffc107',
            'failed': '#dc3545',
            'aborted': '#6c757d',
        }
        color = colors.get(obj.status, '#6c757d')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; border-radius: 4px; font-weight: 600; font-size: 11px;">{}</span>',
            color,
            obj.status.upper()
        )
    status_badge.short_description = "Status"

    def tokens_total(self, obj):
        return f"In: {obj.tokens_in} / Out: {obj.tokens_out} (Tot: {obj.total_tokens})"
    tokens_total.short_description = "Tokens"

    def usd_cost_display(self, obj):
        return f"${float(obj.usd_cost):.5f}"
    usd_cost_display.short_description = "Est. Cost"
