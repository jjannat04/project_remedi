# ReMedi - Circular Healthcare Platform 

**1st Runner-Up @ Hult Prize CUET 2025–26**

ReMedi is a Django-based web application designed to bridge the gap between pharmaceutical waste and healthcare affordability in Bangladesh. We facilitate the donation of unexpired surplus medicine, verify it through a professional audit, and resell it at a 70% discount.

##  Key Features
- **Triple-Check Audit:** A pharmacist-led verification protocol ensuring physical integrity, authenticity, and expiry validation.
- **Automated Pricing:** Business logic that automatically applies a 70% discount to all verified listings.
- **Impact Dashboard:** Real-time tracking of community savings.

##  Tech Stack
- **Backend:** Django (Python)
- **Database:** SQLite (Development) / PostgreSQL (Production ready)
- **Frontend:** Django Templates & CSS

##  Installation
1. Clone the repo: `git clone <your-repo-link>`
2. Create venv: `python -m venv .venv`
3. Activate venv: `.venv\Scripts\activate`
4. Install Django: `pip install django`
5. Migrate: `python manage.py migrate`
6. Run: `python manage.py runserver`