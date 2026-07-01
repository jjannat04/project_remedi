from django.conf import settings


def demo_mode(request):
    return {
        "DEMO_MODE": settings.DEMO_MODE,
        "AI_FALLBACK_ENABLED": settings.AI_FALLBACK_ENABLED,
    }
