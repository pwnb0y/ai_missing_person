# core/urls.py

from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),  # Homepage
    path('file_case_frontend/', views.file_case_frontend, name='file_case_frontend'),
    path('find_person_frontend/', views.find_person_frontend, name='find_person_frontend'),
    path('about_us/', views.about_us, name='about_us'), # about us

    # Health check
    path('health/', views.health_check, name='health_check'),

    # File a missing person case
    path('file_case/', views.file_case, name='file_case'),

    # Match a face
    path('match/', views.match_face, name='match_face'),

    # Get a person's details by ID
    path('person/<int:person_id>/', views.get_person_details, name='get_person_details'),

    # List all cases
    path('cases/', views.list_all_cases, name='list_all_cases'),

    # Force update from Google Drive and re-encode
    path('manual_update/', views.manual_update, name='manual_update'),

    # Serve image from temp folder
    path('media/temp/<str:filename>/', views.get_temp_image, name='get_temp_image'),
]
