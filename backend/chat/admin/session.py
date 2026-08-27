from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from chat.models import PaperChatSession
from .message import PaperChatMessageInline


@admin.register(PaperChatSession)
class PaperChatSessionAdmin(admin.ModelAdmin):
    list_display = ('title', 'paper_link', 'workspace', 'user', 'messages_count', 'session_tokens_display', 'session_cost_display', 'updated_at', 'created_at')
    list_filter = ('workspace', 'created_at')
    search_fields = ('title', 'paper__title', 'paper__doi', 'user__username', 'user__email')
    readonly_fields = ('id', 'total_tokens_in', 'total_tokens_out', 'total_tokens', 'total_usd_cost', 'created_at', 'updated_at')
    inlines = [PaperChatMessageInline]

    def paper_link(self, obj):
        if not obj.paper:
            return format_html('<span style="color: #6c757d; font-style: italic;">Workspace-Level</span>')
        try:
            url = reverse("admin:research_intelligence_paper_change", args=[obj.paper.id])
            return format_html('<a href="{}">{}</a>', url, obj.paper.title[:50] + ("..." if len(obj.paper.title) > 50 else ""))
        except Exception:
            return getattr(obj.paper, 'title', str(obj.paper_id))
    paper_link.short_description = "Paper"

    def messages_count(self, obj):
        return obj.messages.count()
    messages_count.short_description = "Messages"

    def session_tokens_display(self, obj):
        return format_html('<span style="font-weight: 600;">{}</span> tokens', obj.total_tokens)
    session_tokens_display.short_description = "Total Tokens"

    def session_cost_display(self, obj):
        return format_html('<span style="color: #198754; font-weight: 600;">${}</span>', f"{float(obj.total_usd_cost):.5f}")
    session_cost_display.short_description = "Total Cost"
