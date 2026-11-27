from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    ArticleImageViewSet,
    ArticleViewSet,
    ChangeProposalViewSet,
    GlobalSearchView,
    LoginView,
    LogoutView,
    MeView,
    RegisterView,
    WikiViewSet,
)

router = DefaultRouter()
router.register("wikis", WikiViewSet, basename="wiki")
router.register("articles", ArticleViewSet, basename="article")
router.register("images", ArticleImageViewSet, basename="article-image")
router.register("proposals", ChangeProposalViewSet, basename="proposal")

urlpatterns = [
    path("auth/register/", RegisterView.as_view(), name="api-register"),
    path("auth/login/", LoginView.as_view(), name="api-login"),
    path("auth/logout/", LogoutView.as_view(), name="api-logout"),
    path("auth/me/", MeView.as_view(), name="api-me"),
    path("search/", GlobalSearchView.as_view(), name="api-search"),
    path("", include(router.urls)),
]
