from django import forms
from .models import Medicine

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
