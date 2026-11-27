from django.contrib.auth import login, logout
from django.db.models import Q
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, permissions, status, viewsets
from rest_framework.authtoken.models import Token
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Article, ArticleImage, ChangeProposal, Wiki
from .permissions import IsWikiOwnerOrAdmin, IsWikiOwnerOrReadOnly
from .serializers import (
    ArticleImageSerializer,
    ArticleSerializer,
    AuthTokenResponseSerializer,
    ChangeProposalSerializer,
    LoginSerializer,
    RegisterSerializer,
    ReviewProposalSerializer,
    SearchResponseSerializer,
    UserSerializer,
    WikiSerializer,
)


# --- Autenticación ---

class RegisterView(APIView):
    authentication_classes = []
    permission_classes = [permissions.AllowAny]

    @extend_schema(
        tags=["Auth"],
        request=RegisterSerializer,
        responses={201: AuthTokenResponseSerializer},
    )
    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        token, _ = Token.objects.get_or_create(user=user)
        return Response(
            {"token": token.key, "user": UserSerializer(user).data},
            status=status.HTTP_201_CREATED,
        )


class LoginView(APIView):
    authentication_classes = []
    permission_classes = [permissions.AllowAny]

    @extend_schema(
        tags=["Auth"],
        request=LoginSerializer,
        responses={200: AuthTokenResponseSerializer},
    )
    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]
        login(request, user)
        token, _ = Token.objects.get_or_create(user=user)
        return Response(
            {"token": token.key, "user": UserSerializer(user).data},
            status=status.HTTP_200_OK,
        )


class LogoutView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(tags=["Auth"], request=None, responses={204: None})
    def post(self, request):
        Token.objects.filter(user=request.user).delete()
        logout(request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(tags=["Auth"], responses={200: UserSerializer})
    def get(self, request):
        return Response(UserSerializer(request.user).data)


# --- Wikis ---

@extend_schema(tags=["Wikis"])
class WikiViewSet(viewsets.ModelViewSet):
    queryset = Wiki.objects.select_related("owner").all()
    serializer_class = WikiSerializer
    lookup_field = "slug"
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    permission_classes = [
        permissions.IsAuthenticatedOrReadOnly,
        IsWikiOwnerOrReadOnly,
    ]

    def get_queryset(self):
        qs = super().get_queryset()
        owner = self.request.query_params.get("owner")
        if owner == "me" and self.request.user.is_authenticated:
            qs = qs.filter(owner=self.request.user)
        elif owner:
            qs = qs.filter(owner__username=owner)
        return qs

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)

    @extend_schema(responses={200: ArticleSerializer(many=True)})
    @action(detail=True, methods=["get"], permission_classes=[permissions.AllowAny])
    def articles(self, request, slug=None):
        """Lista todos los artículos pertenecientes a esta wiki."""
        wiki = self.get_object()
        serializer = ArticleSerializer(
            wiki.articles.select_related("wiki", "author").all(),
            many=True,
            context={"request": request},
        )
        return Response(serializer.data)

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="status",
                type=str,
                required=False,
                enum=["pending", "approved", "rejected"],
            )
        ],
        responses={200: ChangeProposalSerializer(many=True)},
    )
    @action(detail=True, methods=["get"], permission_classes=[permissions.AllowAny])
    def proposals(self, request, slug=None):
        """Lista las sugerencias de cambio (PRs) de todos los artículos de esta wiki."""
        wiki = self.get_object()
        qs = ChangeProposal.objects.filter(article__wiki=wiki).select_related(
            "article", "article__wiki", "proposed_by", "reviewed_by"
        )
        proposal_status = request.query_params.get("status")
        if proposal_status:
            qs = qs.filter(status=proposal_status)
        serializer = ChangeProposalSerializer(
            qs, many=True, context={"request": request}
        )
        return Response(serializer.data)


# --- Artículos ---

@extend_schema(tags=["Artículos"])
class ArticleViewSet(viewsets.ModelViewSet):
    queryset = Article.objects.select_related("wiki", "author").all()
    serializer_class = ArticleSerializer
    permission_classes = [
        permissions.IsAuthenticatedOrReadOnly,
        IsWikiOwnerOrReadOnly,
    ]

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="wiki",
                type=str,
                required=False,
                description="Filtra artículos por slug de la wiki.",
            )
        ]
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    def get_queryset(self):
        qs = super().get_queryset()
        wiki_slug = self.request.query_params.get("wiki")
        if wiki_slug:
            qs = qs.filter(wiki__slug=wiki_slug)
        return qs

    def perform_create(self, serializer):
        wiki = serializer.validated_data["wiki"]
        if not (self.request.user.is_staff or wiki.owner == self.request.user):
            raise PermissionDenied(
                "Solo el dueño de la wiki puede crear artículos directamente."
            )
        serializer.save(author=self.request.user)


# --- Imágenes ---

@extend_schema(tags=["Imágenes"])
class ArticleImageViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    queryset = ArticleImage.objects.select_related(
        "wiki", "article", "uploaded_by"
    ).all()
    serializer_class = ArticleImageSerializer
    parser_classes = [MultiPartParser, FormParser]
    permission_classes = [
        permissions.IsAuthenticatedOrReadOnly,
        IsWikiOwnerOrReadOnly,
    ]

    def get_queryset(self):
        qs = super().get_queryset()
        wiki_slug = self.request.query_params.get("wiki")
        article_id = self.request.query_params.get("article")
        if wiki_slug:
            qs = qs.filter(wiki__slug=wiki_slug)
        if article_id:
            qs = qs.filter(article_id=article_id)
        return qs

    def perform_create(self, serializer):
        wiki = serializer.validated_data["wiki"]
        if not (self.request.user.is_staff or wiki.owner == self.request.user):
            raise PermissionDenied(
                "Solo el dueño de la wiki puede subir imágenes."
            )
        serializer.save(uploaded_by=self.request.user)


# --- Pull Requests (Sugerencias de cambio) ---

@extend_schema(tags=["Pull Requests"])
class ChangeProposalViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    queryset = ChangeProposal.objects.select_related(
        "article", "article__wiki", "proposed_by", "reviewed_by"
    ).all()
    serializer_class = ChangeProposalSerializer

    def get_permissions(self):
        if self.action in ("list", "retrieve", "create"):
            return [permissions.AllowAny()]
        return [permissions.IsAuthenticated(), IsWikiOwnerOrAdmin()]

    def get_queryset(self):
        qs = super().get_queryset()
        wiki_slug = self.request.query_params.get("wiki")
        article_id = self.request.query_params.get("article")
        proposal_status = self.request.query_params.get("status")
        if wiki_slug:
            qs = qs.filter(article__wiki__slug=wiki_slug)
        if article_id:
            qs = qs.filter(article_id=article_id)
        if proposal_status:
            qs = qs.filter(status=proposal_status)
        return qs

    def perform_create(self, serializer):
        article = serializer.validated_data["article"]
        user = self.request.user
        if user.is_authenticated:
            if article.wiki.owner == user:
                raise ValidationError(
                    "Eres el dueño de esta wiki; edita el artículo directamente."
                )
            serializer.save(proposed_by=user)
        else:
            serializer.save(proposed_by=None)

    @extend_schema(
        request=ReviewProposalSerializer,
        responses={200: ChangeProposalSerializer},
    )
    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        """Aprueba el PR y aplica título y contenido al artículo de forma atómica."""
        proposal = self.get_object()
        review_serializer = ReviewProposalSerializer(data=request.data)
        review_serializer.is_valid(raise_exception=True)
        try:
            proposal.approve(
                reviewer=request.user,
                note=review_serializer.validated_data["review_note"],
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            ChangeProposalSerializer(proposal, context={"request": request}).data
        )

    @extend_schema(
        request=ReviewProposalSerializer,
        responses={200: ChangeProposalSerializer},
    )
    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        """Rechaza el PR sin modificar el artículo original."""
        proposal = self.get_object()
        review_serializer = ReviewProposalSerializer(data=request.data)
        review_serializer.is_valid(raise_exception=True)
        try:
            proposal.reject(
                reviewer=request.user,
                note=review_serializer.validated_data["review_note"],
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            ChangeProposalSerializer(proposal, context={"request": request}).data
        )


# --- Buscador global ---

class GlobalSearchView(APIView):
    permission_classes = [permissions.AllowAny]

    @extend_schema(
        tags=["Buscador"],
        parameters=[
            OpenApiParameter(
                name="q",
                type=str,
                required=True,
                description="Texto a buscar en títulos, descripciones y contenido Markdown.",
            ),
            OpenApiParameter(
                name="wiki",
                type=str,
                required=False,
                description="Opcional: limitar la búsqueda de artículos a una wiki (slug).",
            ),
        ],
        responses={200: SearchResponseSerializer},
    )
    def get(self, request):
        q = request.query_params.get("q", "").strip()
        wiki_slug = request.query_params.get("wiki", "").strip()

        if not q:
            return Response({"query": "", "wikis": [], "articles": []})

        wikis_qs = Wiki.objects.select_related("owner").filter(
            Q(title__icontains=q) | Q(description__icontains=q)
        )
        articles_qs = Article.objects.select_related("wiki", "author").filter(
            Q(title__icontains=q) | Q(content__icontains=q)
        )
        if wiki_slug:
            articles_qs = articles_qs.filter(wiki__slug=wiki_slug)

        return Response(
            {
                "query": q,
                "wikis": WikiSerializer(
                    wikis_qs, many=True, context={"request": request}
                ).data,
                "articles": ArticleSerializer(
                    articles_qs, many=True, context={"request": request}
                ).data,
            }
        )
        