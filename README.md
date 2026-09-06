# Tajneed Registration App

Python Flask + SQLite web app for self-registration.

## Run

1. `python -m venv venv`
2. Windows: `venv\Scripts\activate`
3. `pip install -r requirements.txt`
4. `python app.py`
5. Open `http://127.0.0.1:5000`

## Registration fields

- Full Name
- Phone Number
- Gender
- Date of Birth
- State
- School Attended (dropdown)
- Level of Study (dropdown)
- Course of Study
- Email Address

## School options

- Obafemi Awolowo University
- University of Ilesa
- Osun State University
- Federal Polytechnic Ede
- Fountain University

## Level options

- 100 level
- 200 level
- 300 level
- 400 level
- 500 level

## Admin

Admin login: `http://127.0.0.1:5000/admin/login`

Starter password: `change-me`

The updated app includes a small database migration so an older local `tajneed.db` can gain the new columns without deleting existing registrations.

Before public deployment, change the secret key and admin password, add proper authentication/security controls, use HTTPS, and use a production database/server.
