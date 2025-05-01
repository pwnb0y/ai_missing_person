from django.http import JsonResponse, FileResponse
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from deepface import DeepFace
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload
import os, pickle, numpy as np
from django.shortcuts import render
from .models import MissingPerson

# --- Paths & Config ---
UPLOAD_DIR = os.path.join(settings.MEDIA_ROOT, 'uploads')
TEMP_DIR = os.path.join(settings.MEDIA_ROOT, 'temp')
ENCODINGS_FILE = os.path.join(settings.BASE_DIR, 'encodings.pkl')
CREDENTIALS_FILE = os.path.join(settings.BASE_DIR, 'credentials.json')
DRIVE_FOLDER_ID = '17zt840iXARAn9sQmDWmqpy4pdSTQLRdS'

# Ensure directories exist
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(TEMP_DIR, exist_ok=True)

# Google Drive setup
SCOPES = ['https://www.googleapis.com/auth/drive']
creds = service_account.Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=SCOPES)
drive_service = build('drive', 'v3', credentials=creds)

# In-memory cache for face embeddings
known_encodings = {}

# === Utility Functions ===
def _list_drive():
    resp = drive_service.files().list(
        q=f"'{DRIVE_FOLDER_ID}' in parents", fields='files(id,name)'
    ).execute()
    return {f['id']: f['name'] for f in resp.get('files', [])}

def _download_new():
    current = _list_drive()
    local = set(os.listdir(TEMP_DIR))
    new_files = {fid: name for fid, name in current.items() if name not in local}
    for fid, name in new_files.items():
        path = os.path.join(TEMP_DIR, name)
        req = drive_service.files().get_media(fileId=fid)
        with open(path, 'wb') as f:
            downloader = MediaIoBaseDownload(f, req)
            done = False
            while not done:
                _, done = downloader.next_chunk()
    if new_files:
        _encode_all()

def _load_encodings():
    global known_encodings
    if os.path.exists(ENCODINGS_FILE):
        with open(ENCODINGS_FILE, 'rb') as f:
            known_encodings = pickle.load(f)

def _save_encodings():
    with open(ENCODINGS_FILE, 'wb') as f:
        pickle.dump(known_encodings, f)
    # Backup encodings file to Drive
    meta = {'name': os.path.basename(ENCODINGS_FILE), 'parents': [DRIVE_FOLDER_ID]}
    media = MediaFileUpload(ENCODINGS_FILE, mimetype='application/octet-stream')
    query = f"'{DRIVE_FOLDER_ID}' in parents and name='{os.path.basename(ENCODINGS_FILE)}'"
    existing = drive_service.files().list(q=query, fields='files(id)').execute().get('files')
    if existing:
        drive_service.files().update(fileId=existing[0]['id'], media_body=media).execute()
    else:
        drive_service.files().create(body=meta, media_body=media).execute()

def _encode_all():
    global known_encodings
    for filename in os.listdir(TEMP_DIR):
        if filename in known_encodings:
            continue
        path = os.path.join(TEMP_DIR, filename)
        try:
            embeddings = DeepFace.represent(
                img_path=path, model_name='Facenet', enforce_detection=False
            )
            if embeddings:
                known_encodings[filename] = np.array(embeddings[0]['embedding'])
        except Exception:
            pass
    _save_encodings()

# === VIEW: File a Case ===
@csrf_exempt
def file_case(request):
    if request.method != 'POST' or 'image' not in request.FILES:
        return JsonResponse({'error': 'Use POST and include "image" file.'}, status=400)

    data = request.POST
    img = request.FILES['image']
    filename = img.name
    upload_path = os.path.join(UPLOAD_DIR, filename)

    # Save upload locally
    with open(upload_path, 'wb+') as f:
        for chunk in img.chunks():
            f.write(chunk)

    # Upload to Drive
    file_meta = {'name': filename, 'parents': [DRIVE_FOLDER_ID]}
    media = MediaFileUpload(upload_path, mimetype='image/jpeg')
    upload_result = drive_service.files().create(
        body=file_meta, media_body=media, fields='id'
    ).execute()

    # Download back to temp
    file_id = upload_result['id']
    temp_path = os.path.join(TEMP_DIR, filename)
    request_drive = drive_service.files().get_media(fileId=file_id)
    with open(temp_path, 'wb') as f:
        downloader = MediaIoBaseDownload(f, request_drive)
        done = False
        while not done:
            _, done = downloader.next_chunk()

    # Create DB record
    person = MissingPerson.objects.create(
        name=data.get('name'),
        age=int(data.get('age')),
        height=data.get('height'),
        color=data.get('color'),
        gender=data.get('gender'),
        address=data.get('address'),
        contact=data.get('contact'),
        last_seen_location=data.get('last_seen_location'),
        bounty=float(data.get('bounty', 0)),
        image_path=temp_path,
        reporter_name=data.get('reporter_name'),
        reporter_address=data.get('reporter_address'),
        reporter_contact=data.get('reporter_contact'),
        message=data.get('message'),
    )

    return JsonResponse({'status': 'Case filed', 'id': person.id}, status=201)

# === VIEW: Match Face ===
@csrf_exempt
def match_face(request):
    if request.method != 'POST' or 'file' not in request.FILES:
        return JsonResponse({'error': 'Use POST and include "file" to match.'}, status=400)

    # Load and sync encodings
    _load_encodings()
    _download_new()

    upload = request.FILES['file']
    fname = upload.name
    upload_path = os.path.join(UPLOAD_DIR, fname)

    with open(upload_path, 'wb+') as f:
        for chunk in upload.chunks():
            f.write(chunk)

    try:
        results = DeepFace.find(
            img_path=upload_path,
            db_path=TEMP_DIR,
            model_name='Facenet',
            enforce_detection=False
        )
        os.remove(upload_path)

        if isinstance(results, list) and len(results) > 0 and not results[0].empty:
            matched_file = os.path.basename(results[0]['identity'].values[0])
            matched_path = os.path.join(TEMP_DIR, matched_file)
            person = MissingPerson.objects.filter(image_path=matched_path).first()
            if person:
                web_friendly_path = person.image_path.replace("\\", "/")
                return JsonResponse({
                    'match': True,
                    'person': {
                        'id': person.id,
                        'name': person.name,
                        'age': person.age,
                        'height': person.height,
                        'color': person.color,
                        'gender': person.gender,
                        'address': person.address,
                        'contact': person.contact,
                        'last_seen_location': person.last_seen_location,
                        'bounty': person.bounty,
                        'image_path': web_friendly_path,
                        'reporter_name': person.reporter_name,
                        'reporter_address': person.reporter_address,
                        'reporter_contact': person.reporter_contact,
                        'message': person.message,
                    }
                })
        return JsonResponse({'match': False, 'message': 'No match found.'})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

# === VIEW: Get Person Details ===
def get_person_details(request, person_id):
    try:
        person = MissingPerson.objects.get(id=person_id)
        data = {
            'id': person.id,
            'name': person.name,
            'age': person.age,
            'height': person.height,
            'color': person.color,
            'contact': person.contact,
            'address': person.address,
            'last_seen_location': person.last_seen_location,
            'bounty': person.bounty,
            'reporter_name': person.reporter_name,
            'reporter_address': person.reporter_address,
            'reporter_contact': person.reporter_contact,
            'message': person.message,
            'image': f'/media/temp/{os.path.basename(person.image_path)}' if person.image_path else None,
        }
        return JsonResponse(data)
    except MissingPerson.DoesNotExist:
        return JsonResponse({'error': 'Person not found'}, status=404)

# === VIEW: List All Cases ===
def list_all_cases(request):
    persons = MissingPerson.objects.all()
    cases = []
    for person in persons:
        image_path = person.image_path
        image_url = f'/media/temp/{os.path.basename(image_path)}' if image_path else None

        cases.append({
            'id': person.id,
            'name': person.name,
            'age': person.age,
            'height': person.height,
            'color': person.color,
            'contact': person.contact,
            'address': person.address,
            'last_seen_location': person.last_seen_location,
            'bounty': person.bounty,
            'reporter_name': person.reporter_name,
            'reporter_address': person.reporter_address,
            'reporter_contact': person.reporter_contact,
            'message': person.message,
            'image': image_url,
        })

    return JsonResponse({'cases': cases})

# === VIEW: Manual Update & Helpers ===
@csrf_exempt
def manual_update(request):
    _download_new()
    return JsonResponse({'message': 'Download and encode complete.'})

def get_temp_image(request, filename):
    path = os.path.join(TEMP_DIR, filename)
    if os.path.exists(path):
        return FileResponse(open(path, 'rb'))
    return JsonResponse({'error': 'File not found'}, status=404)

def health_check(request):
    return JsonResponse({'status': 'OK'})

def home(request):
    return render(request, 'core/index.html')
def file_case_frontend(request):
    return render(request, 'core/file-case.html')
def find_person_frontend(request):
    return render(request, 'core/find-person.html')
def about_us(request):
    return render(request, 'core/about-us.html')

