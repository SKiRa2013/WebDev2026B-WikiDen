from django.contrib.auth import authenticate, get_user_model
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from .models import Article, ArticleImage, ChangeProposal, Wiki
from .services import build_diff, render_markdown

User = get_user_model()


# --- Autenticación ---

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("id", "username", "email", "is_staff")
        read_only_fields = fields


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = User
        fields = ("username", "email", "password")

    def create(self, validated_data):
        return User.objects.create_user(
            username=validated_data["username"],
            email=validated_data.get("email", ""),
            password=validated_data["password"],
        )


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        user = authenticate(
            username=attrs["username"],
            password=attrs["password"],
        )
        if not user:
            raise serializers.ValidationError("Credenciales inválidas.")
        if not user.is_active:
            raise serializers.ValidationError("Esta cuenta está desactivada.")
        attrs["user"] = user
        return attrs


class AuthTokenResponseSerializer(serializers.Serializer):
    token = serializers.CharField()
    user = UserSerializer()


# --- Wikis ---

class WikiSerializer(serializers.ModelSerializer):
    owner_username = serializers.CharField(source="owner.username", read_only=True)
    articles_count = serializers.SerializerMethodField()
    pending_proposals_count = serializers.SerializerMethodField()

    class Meta:
        model = Wiki
        fields = (
            "id",
            "owner",
            "owner_username",
            "title",
            "slug",
            "description",
            "primary_color",
            "secondary_color",
            "background_color",
            "text_color",
            "logo",
            "banner",
            "articles_count",
            "pending_proposals_count",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "owner", "slug", "created_at", "updated_at")

    @extend_schema_field(serializers.IntegerField)
    def get_articles_count(self, obj):
        return obj.articles.count()

    @extend_schema_field(serializers.IntegerField)
    def get_pending_proposals_count(self, obj):
        return ChangeProposal.objects.filter(
            article__wiki=obj,
            status=ChangeProposal.Status.PENDING,
        ).count()


# --- Artículos ---

class ArticleSerializer(serializers.ModelSerializer):
    wiki_slug = serializers.CharField(source="wiki.slug", read_only=True)
    wiki_title = serializers.CharField(source="wiki.title", read_only=True)
    author_username = serializers.CharField(
        source="author.username", read_only=True, default=None
    )
    rendered_html = serializers.SerializerMethodField()

    class Meta:
        model = Article
        fields = (
            "id",
            "wiki",
            "wiki_slug",
            "wiki_title",
            "author",
            "author_username",
            "title",
            "slug",
            "content",
            "rendered_html",
            "is_home",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "author", "slug", "created_at", "updated_at")

    @extend_schema_field(serializers.CharField)
    def get_rendered_html(self, obj):
        return render_markdown(obj.content)


# --- Imágenes ---

class ArticleImageSerializer(serializers.ModelSerializer):
    uploaded_by_username = serializers.CharField(
        source="uploaded_by.username", read_only=True, default=None
    )
    markdown_snippet = serializers.CharField(read_only=True)

    class Meta:
        model = ArticleImage
        fields = (
            "id",
            "wiki",
            "article",
            "uploaded_by",
            "uploaded_by_username",
            "image",
            "caption",
            "markdown_snippet",
            "uploaded_at",
        )
        read_only_fields = ("id", "uploaded_by", "markdown_snippet", "uploaded_at")

    def validate(self, attrs):
        wiki = attrs.get("wiki")
        article = attrs.get("article")
        if article and wiki and article.wiki_id != wiki.id:
            raise serializers.ValidationError(
                {"article": "El artículo seleccionado no pertenece a esta wiki."}
            )
        return attrs


# --- Pull Requests (Sugerencias de cambio) ---

class DiffLineSerializer(serializers.Serializer):
    type = serializers.ChoiceField(choices=["meta", "add", "remove", "context"])
    text = serializers.CharField()


class ChangeProposalSerializer(serializers.ModelSerializer):
    article_title = serializers.CharField(source="article.title", read_only=True)
    wiki_slug = serializers.CharField(source="article.wiki.slug", read_only=True)
    contributor_label = serializers.CharField(read_only=True)
    reviewed_by_username = serializers.CharField(
        source="reviewed_by.username", read_only=True, default=None
    )
    title_changed = serializers.SerializerMethodField()
    diff = serializers.SerializerMethodField()
    proposed_html = serializers.SerializerMethodField()

    class Meta:
        model = ChangeProposal
        fields = (
            "id",
            "article",
            "article_title",
            "wiki_slug",
            "proposed_by",
            "guest_name",
            "contributor_label",
            "proposed_title",
            "proposed_content",
            "proposed_html",
            "summary",
            "status",
            "title_changed",
            "diff",
            "reviewed_by",
            "reviewed_by_username",
            "review_note",
            "reviewed_at",
            "created_at",
        )
        read_only_fields = (
            "id",
            "proposed_by",
            "status",
            "reviewed_by",
            "review_note",
            "reviewed_at",
            "created_at",
        )

    @extend_schema_field(serializers.BooleanField)
    def get_title_changed(self, obj):
        return obj.article.title != obj.proposed_title

    @extend_schema_field(DiffLineSerializer(many=True))
    def get_diff(self, obj):
        return build_diff(obj.article.content, obj.proposed_content)

    @extend_schema_field(serializers.CharField)
    def get_proposed_html(self, obj):
        return render_markdown(obj.proposed_content)


class ReviewProposalSerializer(serializers.Serializer):
    review_note = serializers.CharField(required=False, allow_blank=True, default="")


# --- Buscador ---

class SearchResponseSerializer(serializers.Serializer):
    query = serializers.CharField()
    wikis = WikiSerializer(many=True)
    articles = ArticleSerializer(many=True)