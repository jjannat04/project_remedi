import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'remedi.settings') # Use your project name
django.setup()

from myapp.models import ReMediCorner

data = [
    # --- DHAKA REGION ---
    ["Lazz Pharma Ltd (Kalabagan)", "64/3, Lake Circus, Mirpur Road, Dhaka", "Dhaka", 23.7511, 90.3844],
    ["Tamanna Pharmacy (Panthopath)", "Sabamoon Tower, Green Road, Dhaka", "Dhaka", 23.7505, 90.3861],
    ["Shahbag Medicine Corner", "BSMMU Gate No-03, Shahbagh, Dhaka", "Dhaka", 23.7388, 90.3959],
    ["Al-Madina Pharmacy", "30/5 Jahid Tower, Gulshan-2, Dhaka", "Dhaka", 23.7925, 90.4162],
    ["Popular Medicine Corner", "House 12, Road 02, Dhanmondi, Dhaka", "Dhaka", 23.7364, 90.3828],
    ["Labaid Pharmacy", "House-06, Road-04, Dhanmondi, Dhaka", "Dhaka", 23.7423, 90.3815],
    ["Wellbeing Pharmacy", "Sector 3, Uttara, Dhaka", "Dhaka", 23.8631, 90.3995],
    ["Prescription Aid", "Road-02, Dhanmondi R/A, Dhaka", "Dhaka", 23.7371, 90.3830],
    ["Al-Noor Pharmacy", "Zahed Plaza, Gulshan-2, Dhaka", "Dhaka", 23.7931, 90.4158],
    ["T Hossain Pharma", "Mirpur-10 Circle, Dhaka", "Dhaka", 23.8069, 90.3687],

    # --- FENI REGION (Your Home Base) ---
    ["Feni Sadar Model Pharmacy", "Hospital Road, Feni", "Feni", 23.0125, 91.3995],
    ["Central Feni Pharmacy", "Trunk Road, Feni", "Feni", 23.0159, 91.3976],
    ["Lazz Pharma Feni", "S.S.K. Road, Feni", "Feni", 23.0132, 91.4010],
    ["Janani Medical Hall", "Grand Trunk Road, Feni", "Feni", 23.0118, 91.3982],
    ["Square Pharma Outlet", "Mizan Road, Feni", "Feni", 23.0145, 91.4035],

    # --- CHITTAGONG REGION (CUET Context) ---
    ["Lazz Pharma Chittagong", "Mehedibag, Chittagong", "Chittagong", 22.3562, 91.8219],
    ["CIMCH Pharmacy", "Chittagong International Medical College, CTG", "Chittagong", 22.3705, 91.8315],
    ["Economic Pharmacy", "Hazari Lane, Chittagong", "Chittagong", 22.3397, 91.8335],
    ["Banik Pharmacy", "Anderkilla, Chittagong", "Chittagong", 22.3385, 91.8372],
    ["Orbit Trading Intl", "Veterinary University Road, CTG", "Chittagong", 22.3642, 91.8105],
    ["Popular Pharmacy CTG", "O.R. Nizam Road, Chittagong", "Chittagong", 22.3592, 91.8225],
    ["Medicine Zone", "Chawkbazar, Chittagong", "Chittagong", 22.3575, 91.8402],
    ["Fair Medicine House", "Jamal Khan, Chittagong", "Chittagong", 22.3482, 91.8285],

    # --- SYLHET & OTHER REGIONS ---
    ["Labaid Pharmacy Sylhet", "Sylhet Sadar, Sylhet", "Sylhet", 24.8917, 91.8683],
    ["Lazz Pharma Sylhet", "Nayasarak, Sylhet", "Sylhet", 24.8945, 91.8752],
    ["Anarkali Pharmacy", "Zindabazar, Sylhet", "Sylhet", 24.8993, 91.8705],
    ["Bengal Pharmacy Rajshahi", "Laxmipur More, Rajshahi", "Rajshahi", 24.3705, 88.5831],
    ["Baba Pharmacy", "G.P.O, Rajpara, Rajshahi", "Rajshahi", 24.3682, 88.5810],
    ["Beacon Pharma Outlet", "Barisal City, Barisal", "Barisal", 22.7010, 90.3535],
    ["Khulna Chilling Pharma", "Khulna Sadar, Khulna", "Khulna", 22.8156, 89.5685]
]

for item in data:
    ReMediCorner.objects.get_or_create(
        name=item[0],
        address=item[1],
        city=item[2],
        latitude=item[3],
        longitude=item[4]
    )
print("Corners imported successfully!")