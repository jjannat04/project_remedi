from django import forms
from .models import Medicine

class DonationForm(forms.ModelForm):
    class Meta:
        model = Medicine
        # We only want the donor to fill in these fields
        fields = ['name', 'batch_number', 'expiry_date', 'original_price']
        widgets = {
            'expiry_date': forms.DateInput(attrs={'type': 'date'}),
        }