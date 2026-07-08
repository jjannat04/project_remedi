from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.utils.text import capfirst

from .models import Medicine
from .models import User


class SignUpForm(UserCreationForm):
    full_name = forms.CharField(
        label="Full Name",
        max_length=150,
        required=True,
        widget=forms.TextInput(attrs={
            "autocomplete": "name",
            "placeholder": "Enter your legal full name",
        }),
    )
    nid = forms.CharField(
        label="National ID (NID)",
        max_length=30,
        required=True,
        widget=forms.TextInput(attrs={
            "autocomplete": "off",
            "placeholder": "Enter your National ID number",
        }),
    )
    phone = forms.CharField(
        label="Phone Number",
        max_length=15,
        required=True,
        widget=forms.TextInput(attrs={
            "autocomplete": "tel",
            "placeholder": "Enter your phone number",
        }),
    )
    role = forms.ChoiceField(
        label="Account Type",
        choices=(
            (User.Role.DONOR, "User"),
            (User.Role.PHARMACIST, "Healthcare Verifier"),
        ),
        initial=User.Role.DONOR,
        required=True,
        widget=forms.RadioSelect,
    )
    license_number = forms.CharField(
        label="Pharmacy License Number",
        max_length=50,
        required=False,
        widget=forms.TextInput(attrs={
            "autocomplete": "off",
            "placeholder": "Enter pharmacy license number",
        }),
    )

    class Meta(UserCreationForm.Meta):
        model = User
        fields = (
            "full_name",
            "username",
            "nid",
            "phone",
            "role",
            "license_number",
            "password1",
            "password2",
        )
        widgets = {
            "username": forms.TextInput(attrs={
                "autocomplete": "username",
                "placeholder": "Choose a username",
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name in ("username", "password1", "password2"):
            self.fields[field_name].label = capfirst(self.fields[field_name].label)
        self.fields["password1"].widget.attrs.update({
            "autocomplete": "new-password",
            "placeholder": "Create a password",
        })
        self.fields["password2"].widget.attrs.update({
            "autocomplete": "new-password",
            "placeholder": "Confirm your password",
        })

    def clean_license_number(self):
        license_number = (self.cleaned_data.get("license_number") or "").strip()
        role = self.cleaned_data.get("role")
        if role == User.Role.PHARMACIST and not license_number:
            raise forms.ValidationError("Pharmacy license number is required for Healthcare Verifiers.")
        if role == User.Role.DONOR:
            return ""
        return license_number

    def save(self, commit=True):
        user = super().save(commit=False)
        full_name = self.cleaned_data["full_name"].strip()
        first_name, separator, last_name = full_name.partition(" ")
        user.first_name = first_name
        user.last_name = last_name.strip() if separator else ""
        user.nid = self.cleaned_data["nid"].strip()
        user.phone = self.cleaned_data["phone"].strip()
        user.role = self.cleaned_data["role"]
        user.license_number = self.cleaned_data["license_number"] or ""
        if commit:
            user.save()
        return user

class DonationForm(forms.ModelForm):
    opened = forms.TypedChoiceField(
        label="Package Already Opened?",
        choices=((False, 'No'), (True, 'Yes')),
        coerce=lambda value: str(value).lower() == 'true',
        widget=forms.RadioSelect,
        required=True,
    )
    confirm_accuracy = forms.BooleanField(
        label="I confirm the above information is accurate.",
        required=True,
    )

    class Meta:
        model = Medicine
        fields = [
            'donor_phone',
            'donation_address',
            'district',
            'area',
            'pickup_notes',
            'medicine_image',
            'name',
            'scientific_name',
            'dosage',
            'manufacturer',
            'batch_number',
            'expiry_date',
            'category',
            'quantity',
            'package_type',
            'opened',
            'storage_condition',
            'original_price',
        ]
        labels = {
            'donor_phone': 'Phone Number',
            'donation_address': 'Donation Address',
            'area': 'Area / Upazila',
            'pickup_notes': 'Additional Pickup Notes',
            'medicine_image': 'Medicine Package Photo',
            'name': 'Medicine Name',
            'scientific_name': 'Scientific / Generic Name',
            'expiry_date': 'Expiry Date',
            'original_price': 'Original Price',
            'opened': 'Package Already Opened?',
        }
        widgets = {
            'expiry_date': forms.DateInput(attrs={'type': 'date'}),
            'pickup_notes': forms.Textarea(attrs={'rows': 3}),
            'donation_address': forms.Textarea(attrs={'rows': 3}),
            'medicine_image': forms.FileInput(attrs={'accept': 'image/*', 'class': 'sr-only'}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user and not self.is_bound:
            self.fields['donor_phone'].initial = getattr(user, 'phone', '')
        required_fields = [
            'donor_phone',
            'donation_address',
            'district',
            'area',
            'name',
            'batch_number',
            'expiry_date',
            'quantity',
            'package_type',
            'storage_condition',
            'original_price',
        ]
        for field_name in required_fields:
            self.fields[field_name].required = True

    def clean_quantity(self):
        quantity = self.cleaned_data.get('quantity')
        if quantity is None or quantity < 1:
            raise forms.ValidationError('Quantity must be at least 1.')
        return quantity
