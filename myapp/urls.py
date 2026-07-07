from django.urls import path
from django.contrib.auth import views as auth_views 
from . import views

urlpatterns = [
    path('', views.marketplace, name='marketplace'),
    path('marketplace/', views.marketplace, name='marketplace_page'),
    path('marketplace/<int:med_id>/', views.marketplace_detail, name='marketplace_detail'),
    path('dashboard/', views.impact_dashboard, name='impact_dashboard'),
    path('reports/', views.impact_reports, name='impact_reports'),
    path('judge/', views.judge_entry, name='judge_entry'),
    path('judge/ocr/', views.judge_ocr, name='judge_ocr'),
    path('judge/<str:kind>/login/', views.judge_demo_login, name='judge_demo_login'),
    path('signup/', views.signup, name='signup'),
    
    # --- LOGIN & LOGOUT PATHS ---
    path('login/', auth_views.LoginView.as_view(template_name='myapp/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='marketplace'), name='logout'),
    
    path('verify-queue/', views.verification_queue, name='verification_queue'),
    path('pharmacist/queue/', views.pharmacist_queue, name='pharmacist_queue'),
    path('pharmacist/pickup/', views.pharmacist_pickup, name='pharmacist_pickup'),
    path('pharmacist/review/<int:med_id>/', views.pharmacist_review, name='pharmacist_review'),
    path('verify/<int:med_id>/', views.verify_medicine, name='verify_medicine'),
    path('map/', views.corner_map, name='corner_map'),
    path('donate/', views.donate_medicine, name='donate_medicine'),
    path('profile/', views.profile_view, name='profile'),
    path('order/<int:med_id>/', views.order_medicine, name='order_medicine'),
    path('reserve/<int:med_id>/', views.reserve_marketplace_medicine, name='reserve_medicine'),
]
