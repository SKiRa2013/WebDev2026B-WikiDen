from django.contrib import admin, messages
from .models import Article, ArticleImage, ChangeProposal, Wiki


class ArticleInline(admin.TabularInline):
    model = Article
    fields = ("title", "slug", "is_home", "author")
    extra = 0


@admin.register(Wiki)
class WikiAdmin(admin.ModelAdmin):
    list_display = ("title", "slug", "owner", "primary_color", "created_at")
    list_filter = ("created_at",)
    search_fields = ("title", "slug", "description", "owner__username")
    prepopulated_fields = {"slug": ("title",)}
    inlines = [ArticleInline]
    fieldsets = (
        ("Información general", {
            "fields": ("owner", "title", "slug", "description"),
        }),
        ("Apariencia", {
            "fields": (
                "primary_color",
                "secondary_color",
                "background_color",
                "text_color",
                "logo",
                "banner",
            ),
        }),
    )


@admin.register(Article)
class ArticleAdmin(admin.ModelAdmin):
    list_display = ("title", "wiki", "author", "is_home", "updated_at")
    list_filter = ("wiki", "is_home", "updated_at")
    search_fields = ("title", "content", "wiki__title")
    prepopulated_fields = {"slug": ("title",)}


@admin.register(ArticleImage)
class ArticleImageAdmin(admin.ModelAdmin):
    list_display = ("caption", "wiki", "article", "uploaded_by", "uploaded_at")
    list_filter = ("wiki", "uploaded_at")
    search_fields = ("caption", "wiki__title")
    readonly_fields = ("markdown_snippet", "uploaded_at")


@admin.register(ChangeProposal)
class ChangeProposalAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "article",
        "contributor_label",
        "summary",
        "status",
        "reviewed_by",
        "created_at",
    )
    list_filter = ("status", "article__wiki", "created_at")
    search_fields = (
        "summary",
        "proposed_title",
        "proposed_content",
        "guest_name",
        "proposed_by__username",
    )
    readonly_fields = ("reviewed_by", "reviewed_at", "created_at")
    actions = ["approve_selected", "reject_selected"]

    @admin.action(description="Aprobar propuestas pendientes seleccionadas")
    def approve_selected(self, request, queryset):
        approved = 0
        for proposal in queryset.filter(status=ChangeProposal.Status.PENDING):
            proposal.approve(reviewer=request.user, note="Aprobada desde Admin.")
            approved += 1
        self.message_user(
            request,
            f"{approved} propuesta(s) aprobada(s) y aplicada(s).",
            level=messages.SUCCESS,
        )

    @admin.action(description="Rechazar propuestas pendientes seleccionadas")
    def reject_selected(self, request, queryset):
        rejected = 0
        for proposal in queryset.filter(status=ChangeProposal.Status.PENDING):
            proposal.reject(reviewer=request.user, note="Rechazada desde Admin.")
            rejected += 1
        self.message_user(
            request,
            f"{rejected} propuesta(s) rechazada(s).",
            level=messages.WARNING,
        )