from django.shortcuts import render, get_object_or_404, redirect
from .models import Medicine, ReMediCorner
from django.db.models import Sum
from pathlib import Path
import mimetypes
import re
from datetime import date
from django.contrib.auth import login
from .models import User
from .forms import DonationForm, SignUpForm
from django.utils import timezone
from django.contrib.auth.decorators import login_required
from django.conf import settings
from django.http import FileResponse, Http404, HttpResponse, HttpResponseForbidden, JsonResponse

from .services.analytics import calculate_demo_analytics, calculate_medicine_analytics, demo_medicine_queryset
from .services.demo_data import ensure_demo_user
from .services.dashboard import get_dashboard_charts, get_dashboard_statistics
from .services.explanation import build_explanation
from .services.image_processing import compress_uploaded_image
from .services.marketplace import get_marketplace_medicines
from .services.pipeline import evaluate_donation
from .services.qr import ensure_medicine_qr, render_qr_data_uri
from .services.reports import REPORT_TYPES, generate_report
from .services.reservations import reserve_medicine, verify_pickup_otp


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

    evaluation = None
    explanation = None
    if request.method == 'POST':
        image_file = request.FILES.get('medicine_image')
        if image_file:
            evaluation = evaluate_donation(image_file)
            explanation = build_explanation(evaluation)

    return render(request, 'myapp/judge_ocr.html', {
        'evaluation': evaluation,
        'explanation': explanation,
    })

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
    search_query = request.GET.get('q', '')
    medicines = get_marketplace_medicines(search_query)
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
        'search_query': search_query,
        'total_saved': total_saved,
    }
    if settings.DEMO_MODE:
        context['demo_analytics'] = calculate_demo_analytics()
    return render(request, 'myapp/marketplace.html', context)


def marketplace_detail(request, med_id):
    medicine = get_object_or_404(get_marketplace_medicines(), id=med_id)
    return render(request, 'myapp/marketplace_detail.html', {
        'medicine': medicine,
    })


def impact_dashboard(request):
    return render(request, 'myapp/dashboard.html', {
        'statistics': get_dashboard_statistics(),
        'chart_data': get_dashboard_charts(),
    })


def impact_reports(request):
    report_type = request.GET.get("type", "overall")
    if report_type not in REPORT_TYPES:
        report_type = "overall"
    report = generate_report(report_type)

    if request.GET.get("download") == "txt":
        content = report["content"] if report["has_data"] else "No report data available yet."
        response = HttpResponse(content, content_type="text/plain; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="{report["filename"]}"'
        return response

    return render(request, 'myapp/reports.html', {
        'report': report,
        'report_types': REPORT_TYPES,
        'selected_report_type': report_type,
    })


@login_required
def reserve_marketplace_medicine(request, med_id):
    if request.method != 'POST':
        return redirect('marketplace_detail', med_id=med_id)

    result = reserve_medicine(med_id, request.user)
    return render(request, 'myapp/reservation_confirmation.html', result)


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
def pharmacist_pickup(request):
    if request.user.role != User.Role.PHARMACIST or not request.user.is_active:
        return HttpResponseForbidden("Your pharmacist account is either not verified or you don't have permission.")

    result = None
    if request.method == 'POST':
        result = verify_pickup_otp(
            request.POST.get('identifier'),
            request.POST.get('otp'),
        )

    return render(request, 'myapp/pharmacist_pickup.html', {
        'result': result,
    })


@login_required
def pharmacist_review(request, med_id):
    """Pharmacist human-in-the-loop review workflow."""
    if request.user.role != User.Role.PHARMACIST or not request.user.is_active:
        return HttpResponseForbidden("Your pharmacist account is either not verified or you don't have permission.")

    medicine = get_object_or_404(Medicine, id=med_id)
    evaluation = None
    explanation = None
    success_message = None
    rejection_error = None
    reviewed_at = medicine.verified_at or medicine.rejected_at
    is_reviewed = medicine.status in {'verified', 'rejected', 'sold'}
    qr_image_data_uri = None

    if medicine.medicine_image:
        evaluation = evaluate_donation(medicine.medicine_image)
        explanation = build_explanation(evaluation)

    if request.method == 'POST' and not is_reviewed:
        action = request.POST.get('action')
        if action == 'approve':
            medicine.status = 'verified'
            medicine.is_physical_intact = True
            medicine.is_authentic = True
            medicine.is_expiry_valid = True
            medicine.verified_at = timezone.now()
            medicine.rejected_at = None
            medicine.rejection_reason = ''
            medicine.save()
            ensure_medicine_qr(medicine)
            reviewed_at = medicine.verified_at
            is_reviewed = True
            success_message = "Medicine verified successfully."
        elif action == 'reject':
            rejection_reason = (request.POST.get('rejection_reason') or '').strip()
            if rejection_reason:
                medicine.status = 'rejected'
                medicine.rejected_at = timezone.now()
                medicine.rejection_reason = rejection_reason
                medicine.save()
                reviewed_at = medicine.rejected_at
                is_reviewed = True
                success_message = "Medicine rejected successfully."
            else:
                rejection_error = "Reason for rejection is required."

    if medicine.qr_code_id:
        qr_image_data_uri = render_qr_data_uri(medicine.qr_code_id)

    return render(request, 'myapp/pharmacist_review.html', {
        'medicine': medicine,
        'evaluation': evaluation,
        'explanation': explanation,
        'success_message': success_message,
        'rejection_error': rejection_error,
        'is_reviewed': is_reviewed,
        'reviewed_at': reviewed_at,
        'qr_image_data_uri': qr_image_data_uri,
    })


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
            medicine.save()
            ensure_medicine_qr(medicine)
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


def _donor_display_name(user):
    return user.get_full_name().strip() or user.username


def _parse_expiry_date(expiry_text):
    text = (expiry_text or "").strip()
    if not text:
        return ""

    match = re.search(r"\b(20\d{2})[-/.](0?[1-9]|1[0-2])[-/.](0?[1-9]|[12]\d|3[01])\b", text)
    if match:
        year, month, day = match.groups()
        try:
            return date(int(year), int(month), int(day)).isoformat()
        except ValueError:
            return ""

    match = re.search(r"\b(0?[1-9]|1[0-2])[-/.](20\d{2})\b", text)
    if match:
        month, year = match.groups()
        return date(int(year), int(month), 1).isoformat()

    match = re.search(r"\b(0?[1-9]|[12]\d|3[01])[-/.](0?[1-9]|1[0-2])[-/.](20\d{2})\b", text)
    if match:
        day, month, year = match.groups()
        try:
            return date(int(year), int(month), int(day)).isoformat()
        except ValueError:
            return ""

    return ""


@login_required
def analyze_donation_image(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Image analysis requires POST.'}, status=405)

    image_file = request.FILES.get('medicine_image')
    if not image_file:
        return JsonResponse({'error': 'Please upload a medicine package image.'}, status=400)

    evaluation = evaluate_donation(image_file)
    explanation = build_explanation(evaluation)
    ocr = evaluation.get('ocr') or {}
    safety = evaluation.get('safety') or {}
    risk = evaluation.get('risk') or {}
    decision = evaluation.get('decision') or {}

    return JsonResponse({
        'ocr': {
            'medicine_name': ocr.get('medicine_name', ''),
            'scientific_name': ocr.get('scientific_name', ''),
            'dosage': ocr.get('dosage', ''),
            'manufacturer': ocr.get('manufacturer', ''),
            'batch_number': ocr.get('batch_number', ''),
            'expiry_text': ocr.get('expiry_text', ''),
            'expiry_date': _parse_expiry_date(ocr.get('expiry_text')),
            'confidence': ocr.get('confidence', 0),
            'source': ocr.get('source', ''),
        },
        'safety': {
            'expiry_visible': bool((ocr.get('expiry_text') or '').strip()) and not safety.get('unclear_expiry'),
            'batch_visible': bool((ocr.get('batch_number') or '').strip()),
            'package_intact': not safety.get('damaged_packaging') and not safety.get('tampered_seal'),
            'flags': safety,
        },
        'risk': risk,
        'decision': decision,
        'explanation': explanation,
    })


@login_required
def donate_medicine(request):
    if request.method == 'POST':
        form = DonationForm(request.POST, request.FILES, user=request.user)
        if form.is_valid():
            medicine = form.save(commit=False)
            medicine.donor = request.user  # Link the medicine to the logged-in user
            medicine.status = 'pending'    # Ensure it starts as pending
            if medicine.medicine_image:
                medicine.medicine_image = compress_uploaded_image(medicine.medicine_image)
            medicine.save()
            return redirect('marketplace')
    else:
        form = DonationForm(user=request.user)
    return render(request, 'myapp/donate.html', {
        'form': form,
        'donor_display_name': _donor_display_name(request.user),
    })

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
    return reserve_marketplace_medicine(request, med_id)
