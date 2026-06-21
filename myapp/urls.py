from django.urls import path
from django.contrib.auth import views as auth_views 
from . import views

urlpatterns = [
    path('', views.marketplace, name='marketplace'),
    path('signup/', views.signup, name='signup'),
    
    # --- LOGIN & LOGOUT PATHS ---
    path('login/', auth_views.LoginView.as_view(template_name='myapp/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='marketplace'), name='logout'),
    
    path('verify-queue/', views.verification_queue, name='verification_queue'),
    path('pharmacist/queue/', views.pharmacist_queue, name='pharmacist_queue'),
    path('verify/<int:med_id>/', views.verify_medicine, name='verify_medicine'),
    path('map/', views.corner_map, name='corner_map'),
    path('donate/', views.donate_medicine, name='donate_medicine'),
    path('profile/', views.profile_view, name='profile'),
    path('order/<int:med_id>/', views.order_medicine, name='order_medicine'),
]