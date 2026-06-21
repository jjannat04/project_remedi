from django.contrib import admin
from .models import User, Medicine, ReMediCorner
@admin.register(Medicine)
class MedicineAdmin(admin.ModelAdmin):
    list_display = ('name', 'status', 'original_price', 'resale_price', 'expiry_date')
    list_filter = ('status',)
    search_fields = ('name', 'batch_number')


@admin.register(ReMediCorner)
class ReMediCornerAdmin(admin.ModelAdmin):
    # This displays the columns in the main admin list
    list_display = ('name', 'city', 'latitude', 'longitude')
    
    # Allows you to filter by city (Feni, Dhaka, etc.) on the right sidebar
    list_filter = ('city',)
    
    # Adds a search bar to look up corners by name or address
    search_fields = ('name', 'address')
    
    # Grouping fields for a cleaner edit page
    fieldsets = (
        ('Location Info', {
            'fields': ('name', 'address', 'city')
        }),
        ('Coordinates', {
            'fields': ('latitude', 'longitude'),
            'description': 'You can find these on Google Maps by right-clicking a location.'
        }),
    )

@admin.register(User)
class CustomUserAdmin(admin.ModelAdmin):
    list_display = ('username', 'role', 'is_active', 'license_number')
    list_filter = ('role', 'is_active')
    # Allow quick activation from the list view
    list_editable = ('is_active',)