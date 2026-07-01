from django import forms
from .models import Medicine
from .services.image_processing import compress_uploaded_image

class DonationForm(forms.ModelForm):
    class Meta:
        model = Medicine
        # We only want the donor to fill in these fields
        fields = ['name', 'batch_number', 'medicine_image', 'expiry_date', 'original_price']
        widgets = {
            'expiry_date': forms.DateInput(attrs={'type': 'date'}),
        }

    def clean_medicine_image(self):
        image = self.cleaned_data.get('medicine_image')
        return compress_uploaded_image(image)
