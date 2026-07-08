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
    class Meta:
        model = Medicine
        # We only want the donor to fill in these fields
        fields = ['name', 'batch_number', 'medicine_image', 'expiry_date', 'original_price']
        widgets = {
            'expiry_date': forms.DateInput(attrs={'type': 'date'}),
        }
