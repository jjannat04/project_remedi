from django.shortcuts import render, get_object_or_404, redirect
from .models import Medicine, ReMediCorner
from django.db.models import Sum
import json
from pathlib import Path
import mimetypes
from django.contrib.auth import login
from django.contrib.auth.forms import UserCreationForm
from .models import User
from .forms import DonationForm
from django.utils import timezone
from django.contrib.auth.decorators import login_required
from django.conf import settings
from django.http import FileResponse, Http404, HttpResponseForbidden

from .services.analytics import calculate_demo_analytics, calculate_medicine_analytics, demo_medicine_queryset
from .services.ai import analyze_medicine_image
from .services.demo_data import ensure_demo_user
from .services.image_processing import compress_uploaded_image


def hackathon_media_serve(request, path):
    """Hackathon/demo-only media serving fallback.

    This is temporary and should be replaced with proper static/media storage
    before production use beyond the demo environment.
    """
    media_root = Path(settings.MEDIA_ROOT).resolve()
    requested_path = (media_root / path).resolve()

    try:
        requested_path.relative_to(media_root)
    except ValueError:
        raise Http404()

    if not requested_path.is_file():
        raise Http404()

    content_type, _encoding = mimetypes.guess_type(requested_path)
    return FileResponse(open(requested_path, "rb"), content_type=content_type or "application/octet-stream")


def judge_entry(request):
    if not settings.DEMO_MODE:
        raise Http404()
    return render(request, 'myapp/judge.html')


def judge_demo_login(request, kind):
    if not settings.DEMO_MODE:
        raise Http404()
    if request.method != 'POST' or kind not in {'donor', 'pharmacist'}:
        raise Http404()

    user, _created = ensure_demo_user(kind)
    login(request, user)

    if user.role == User.Role.PHARMACIST:
        return redirect('pharmacist_queue')
    return redirect('profile')


def judge_ocr(request):
    if not settings.DEMO_MODE:
        raise Http404()

    result = None
    result_json = None
    if request.method == 'POST':
        image_file = request.FILES.get('medicine_image')
        if image_file:
            result = analyze_medicine_image(image_file)
            result_json = json.dumps(result, indent=2)

    return render(request, 'myapp/judge_ocr.html', {
        'result': result,
        'result_json': result_json,
    })


# A simple custom form to include the 'role' field
class SignUpForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = User
        fields = UserCreationForm.Meta.fields + ('role', 'phone', 'license_number')
def signup(request):
    if request.method == 'POST':
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            
            # If the user is a pharmacist, deactivate them pending approval
            if user.role == User.Role.PHARMACIST:
                user.is_active = False 
                user.save()
                # Redirect to a "Wait for approval" page instead of logging them in
                return render(request, 'myapp/pending_approval.html')
            
            # Regular users (Donors/Patients) can log in immediately
            user.save()
            login(request, user)
            return redirect('marketplace')
    else:
        form = SignUpForm()
    return render(request, 'myapp/signup.html', {'form': form})


def marketplace(request):
    # Simplified Filter: Show everything that is verified and not yet sold
    medicines = Medicine.objects.filter(status='verified').filter(patient=None)
    reserved_medicines = Medicine.objects.filter(status='verified', patient__isnull=False, completed_at__isnull=True)

    # Calculate Total Savings
    # We use .aggregate for better performance (Competitive Programmer style!)
    sold_meds = Medicine.objects.filter(status='sold')
    savings_data = sold_meds.aggregate(
        total_orig=Sum('original_price'), 
        total_resale=Sum('resale_price')
    )
    
    # Handle case where no meds are sold yet to avoid None errors
    total_saved = (savings_data['total_orig'] or 0) - (savings_data['total_resale'] or 0)

    context = {
        'medicines': medicines,
        'reserved_medicines': reserved_medicines,
        'total_saved': total_saved,
    }
    if settings.DEMO_MODE:
        context['demo_analytics'] = calculate_demo_analytics()
    return render(request, 'myapp/marketplace.html', context)


@login_required
def verification_queue(request):
    return pharmacist_queue(request)


@login_required
def pharmacist_queue(request):
    """The Dashboard/List view"""
    if request.user.role != User.Role.PHARMACIST or not request.user.is_active:
        return HttpResponseForbidden("Your pharmacist account is either not verified or you don't have permission.")
        
    pending_medicines = Medicine.objects.filter(status='pending') # or whatever your default status is
    pending_count = pending_medicines.count()
    verified_count = Medicine.objects.filter(status__in=['verified', 'sold']).count()
    rejected_count = Medicine.objects.filter(status='rejected').count()
    
    context = {
        'pending_medicines': pending_medicines,
        'pending_count': pending_count
    }
    context['verified_count'] = verified_count
    context['rejected_count'] = rejected_count
    if settings.DEMO_MODE:
        context['demo_analytics'] = calculate_demo_analytics()
    return render(request, 'myapp/verify_form.html', context)

@login_required
def verify_medicine(request, med_id):
    # 1. Security Check
    if request.user.role != User.Role.PHARMACIST or not request.user.is_active:
        return HttpResponseForbidden("Your pharmacist account is either not verified or you don't have permission.")

    # 2. Get the medicine
    medicine = get_object_or_404(Medicine, id=med_id)

    # 3. Handle the logic
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'verify':
            medicine.status = 'verified'
            medicine.is_physical_intact = True
            medicine.is_authentic = True
            medicine.is_expiry_valid = True
            medicine.verified_at = timezone.now()
            medicine.rejection_reason = ''
            medicine.rejected_at = None
        elif action == 'reject':
            medicine.status = 'rejected'
            medicine.rejected_at = timezone.now()
            medicine.rejection_reason = request.POST.get('rejection_reason') or 'Rejected during pharmacist review.'
        
        medicine.save()
    
    # 4. Redirect back to the queue (the page you were just on)
    return redirect('pharmacist_queue')
def corner_map(request):
    corners = ReMediCorner.objects.all()
    return render(request, 'myapp/map.html', {'corners': corners})



@login_required
def donate_medicine(request):
    if request.method == 'POST':
        form = DonationForm(request.POST, request.FILES)
        if form.is_valid():
            medicine = form.save(commit=False)
            medicine.donor = request.user  # Link the medicine to the logged-in user
            medicine.status = 'pending'    # Ensure it starts as pending
            if medicine.medicine_image:
                medicine.medicine_image = compress_uploaded_image(medicine.medicine_image)
            medicine.save()
            return redirect('marketplace')
    else:
        form = DonationForm()
    return render(request, 'myapp/donate.html', {'form': form})

@login_required
def profile_view(request):
    # Meds the user donated
    my_donations = Medicine.objects.filter(donor=request.user).order_by('-id')
    
    # Meds the user ordered/purchased
    # We filter by patient=request.user
    my_orders = Medicine.objects.filter(patient=request.user).order_by('-ordered_at')
    donation_groups = {
        'pending': my_donations.filter(status='pending'),
        'rejected': my_donations.filter(status='rejected'),
        'verified': my_donations.filter(status='verified', patient__isnull=True),
        'reserved': my_donations.filter(status='verified', patient__isnull=False, completed_at__isnull=True),
        'sold': my_donations.filter(status='sold'),
    }
    profile_analytics = calculate_medicine_analytics(my_donations)
    
    context = {
        'donations': my_donations,
        'orders': my_orders,
        'donation_groups': donation_groups,
        'profile_analytics': profile_analytics,
    }
    if settings.DEMO_MODE:
        context['demo_analytics'] = calculate_demo_analytics()
        context['demo_medicines_count'] = demo_medicine_queryset().count()
    return render(request, 'myapp/profile.html', context)

@login_required
def order_medicine(request, med_id):
    medicine = get_object_or_404(Medicine, id=med_id)
    
    if medicine.status == 'verified' and medicine.patient is None:
        medicine.patient = request.user
        medicine.status = 'sold'  # Force the status change here
        medicine.ordered_at = timezone.now()
        medicine.completed_at = medicine.ordered_at
        medicine.save()
        return redirect('profile')
    
    return redirect('marketplace')
