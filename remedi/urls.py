from django.contrib import admin
from django.conf import settings
from django.conf.urls.static import static
from django.urls import path, include
from myapp import views as myapp_views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('myapp.urls')), # This makes myapp the home page
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
else:
    # Hackathon/demo-only media fallback for DEBUG=False.
    # Replace with proper persistent/static media serving before real production use.
    urlpatterns += [
        path('media/<path:path>', myapp_views.hackathon_media_serve, name='hackathon_media_serve'),
    ]
