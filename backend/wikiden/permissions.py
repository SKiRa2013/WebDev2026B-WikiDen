from rest_framework import permissions


def get_wiki_owner(obj):
    if hasattr(obj, "owner"):
        return obj.owner
    if hasattr(obj, "wiki"):
        return obj.wiki.owner
    if hasattr(obj, "article"):
        return obj.article.wiki.owner
    return None


class IsWikiOwnerOrReadOnly(permissions.BasePermission):
    """Lectura pública; escritura solo para el dueño de la wiki o un administrador."""

    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        if not request.user or not request.user.is_authenticated:
            return False
        return request.user.is_staff or get_wiki_owner(obj) == request.user


class IsWikiOwnerOrAdmin(permissions.BasePermission):
    """Acción exclusiva del dueño de la wiki o un administrador."""

    def has_object_permission(self, request, view, obj):
        if not request.user or not request.user.is_authenticated:
            return False
        return request.user.is_staff or get_wiki_owner(obj) == request.user