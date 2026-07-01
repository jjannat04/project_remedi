from django.conf import settings

from myapp.services.demo_data import is_seeded_demo_data_ready


def demo_mode(request):
    demo_seeded = False
    if settings.DEMO_MODE:
        try:
            demo_seeded = is_seeded_demo_data_ready()
        except Exception:
            demo_seeded = False

    return {
        "DEMO_MODE": settings.DEMO_MODE,
        "DEMO_SEEDED": demo_seeded,
        "AI_FALLBACK_ENABLED": settings.AI_FALLBACK_ENABLED,
    }
