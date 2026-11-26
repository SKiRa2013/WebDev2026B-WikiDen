from django.conf import settings
from django.core.validators import RegexValidator
from django.db import models, transaction
from django.utils import timezone
from django.utils.text import slugify

hex_color_validator = RegexValidator(
    regex=r"^#[0-9A-Fa-f]{6}$",
    message="Usa un color hexadecimal válido, por ejemplo #0d6efd.",
)


class Wiki(models.Model):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="wikis",
    )
    title = models.CharField(max_length=150)
    slug = models.SlugField(max_length=160, unique=True, blank=True)
    description = models.TextField(blank=True)

    # Personalización de apariencia
    primary_color = models.CharField(
        max_length=7, default="#0d6efd", validators=[hex_color_validator]
    )
    secondary_color = models.CharField(
        max_length=7, default="#6c757d", validators=[hex_color_validator]
    )
    background_color = models.CharField(
        max_length=7, default="#ffffff", validators=[hex_color_validator]
    )
    text_color = models.CharField(
        max_length=7, default="#212529", validators=[hex_color_validator]
    )
    logo = models.ImageField(upload_to="wikis/logos/", blank=True, null=True)
    banner = models.ImageField(upload_to="wikis/banners/", blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.title) or "wiki"
            slug = base_slug
            counter = 1
            while Wiki.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            self.slug = slug
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title


class Article(models.Model):
    wiki = models.ForeignKey(
        Wiki,
        on_delete=models.CASCADE,
        related_name="articles",
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="authored_articles",
    )
    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=210, blank=True)
    content = models.TextField(help_text="Contenido en formato Markdown.")
    is_home = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-is_home", "title"]
        constraints = [
            models.UniqueConstraint(
                fields=["wiki", "slug"],
                name="unique_article_slug_per_wiki",
            )
        ]

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.title) or "articulo"
            slug = base_slug
            counter = 1
            while (
                Article.objects.filter(wiki=self.wiki, slug=slug)
                .exclude(pk=self.pk)
                .exists()
            ):
                slug = f"{base_slug}-{counter}"
                counter += 1
            self.slug = slug
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.wiki.title} / {self.title}"


class ArticleImage(models.Model):
    wiki = models.ForeignKey(
        Wiki,
        on_delete=models.CASCADE,
        related_name="images",
    )
    article = models.ForeignKey(
        Article,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="images",
    )
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="uploaded_wiki_images",
    )
    image = models.ImageField(upload_to="wikis/article_images/%Y/%m/")
    caption = models.CharField(max_length=200, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-uploaded_at"]

    @property
    def markdown_snippet(self):
        alt = self.caption or "imagen"
        return f"![{alt}]({self.image.url})"

    def __str__(self):
        return self.caption or self.image.name


class ChangeProposal(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pendiente"
        APPROVED = "approved", "Aprobada"
        REJECTED = "rejected", "Rechazada"

    article = models.ForeignKey(
        Article,
        on_delete=models.CASCADE,
        related_name="proposals",
    )
    proposed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="change_proposals",
    )
    guest_name = models.CharField(
        max_length=100,
        blank=True,
        help_text="Nombre opcional cuando sugiere un usuario no registrado.",
    )
    proposed_title = models.CharField(max_length=200)
    proposed_content = models.TextField()
    summary = models.CharField(
        max_length=300,
        help_text="Resumen breve de los cambios propuestos.",
    )
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_proposals",
    )
    review_note = models.TextField(blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    @property
    def contributor_label(self):
        if self.proposed_by:
            return self.proposed_by.username
        return self.guest_name or "Anónimo"

    @transaction.atomic
    def approve(self, reviewer, note=""):
        if self.status != self.Status.PENDING:
            raise ValueError("Solo se pueden aprobar propuestas pendientes.")
        self.article.title = self.proposed_title
        self.article.content = self.proposed_content
        self.article.save(update_fields=["title", "content", "updated_at"])

        self.status = self.Status.APPROVED
        self.reviewed_by = reviewer
        self.review_note = note
        self.reviewed_at = timezone.now()
        self.save(
            update_fields=["status", "reviewed_by", "review_note", "reviewed_at"]
        )

    def reject(self, reviewer, note=""):
        if self.status != self.Status.PENDING:
            raise ValueError("Solo se pueden rechazar propuestas pendientes.")
        self.status = self.Status.REJECTED
        self.reviewed_by = reviewer
        self.review_note = note
        self.reviewed_at = timezone.now()
        self.save(
            update_fields=["status", "reviewed_by", "review_note", "reviewed_at"]
        )

    def __str__(self):
        return f"PR #{self.pk} en {self.article.title} ({self.get_status_display()})"
    