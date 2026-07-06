from django.db import models
from django.contrib.auth.models import AbstractUser
from decimal import Decimal
import uuid
from django.core.exceptions import ValidationError

def validate_image_size(image):
    if image.size > 5 * 1024 * 1024:  # 5 MB
        raise ValidationError("Image must be under 5 MB.")
# --- NEW CUSTOM USER MODEL ---
class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = "ADMIN", "Admin"
        PHARMACIST = "PHARMACIST", "Pharmacist"
        DONOR = "DONOR", "Donor"
        PATIENT = "PATIENT", "Patient"

    role = models.CharField(max_length=20, choices=Role.choices, default=Role.PATIENT)
    license_number = models.CharField(max_length=50, blank=True, null=True) # Only for Pharmacists
    phone = models.CharField(max_length=15, blank=True)
    is_demo_account = models.BooleanField(default=False)

# --- UPDATED MEDICINE MODEL ---
class Medicine(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending Review'),
        ('verified', 'Verified & Available'),
        ('rejected', 'Rejected'),
        ('sold', 'Sold'),
    ]

    # Change User to 'myapp.User' to point to your custom model
    donor = models.ForeignKey('myapp.User', on_delete=models.CASCADE, related_name='donations')
    name = models.CharField(max_length=255)
    scientific_name = models.CharField(max_length=255, blank=True)
    category = models.CharField(max_length=100, blank=True)
    batch_number = models.CharField(max_length=100)
    medicine_image = models.ImageField(upload_to='medicines/%Y/%m/', blank=True)
    expiry_date = models.DateField()
    original_price = models.DecimalField(max_digits=10, decimal_places=2)
    resale_price = models.DecimalField(max_digits=10, decimal_places=2, editable=False)
    rejection_reason = models.TextField(blank=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    rejected_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    is_physical_intact = models.BooleanField(default=False)
    is_authentic = models.BooleanField(default=False)
    is_expiry_valid = models.BooleanField(default=False)
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    qr_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    qr_code_id = models.CharField(max_length=20, unique=True, null=True, blank=True, db_index=True)
    qr_generated_at = models.DateTimeField(null=True, blank=True)
    patient = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='purchases')
    ordered_at = models.DateTimeField(null=True, blank=True)

    def save(self, *args, **kwargs):
        self.resale_price = self.original_price * Decimal("0.30")
        if self.status == 'pending' and self.is_physical_intact and self.is_authentic and self.is_expiry_valid:
            self.status = 'verified'
        super().save(*args, **kwargs)

class ReMediCorner(models.Model):
    name = models.CharField(max_length=255)
    address = models.TextField()
    city = models.CharField(max_length=100, default="Feni") # Useful for filtering
    latitude = models.FloatField()
    longitude = models.FloatField()

    def __str__(self):
        return f"{self.name} ({self.city})"        
