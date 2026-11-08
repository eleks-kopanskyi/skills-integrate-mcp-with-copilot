# Mergington High School Activities API

A super simple FastAPI application that allows students to view and sign up for extracurricular activities.

## Features

- View all available extracurricular activities
- Sign in with a provisioned student, parent, staff, or admin account
- Sign up for activities as a student and manage participants as staff/admin
- View activities and participants without signing in; parent accounts are read-only

## Getting Started

1. Install the dependencies:

   ```
   pip install -r requirements.txt
   ```

2. Run the application:

   ```
   cd src
   uvicorn app:app --reload
   ```

3. Open your browser and go to:
   - API documentation: http://localhost:8000/docs
   - Alternative documentation: http://localhost:8000/redoc

## API Endpoints

| Method | Endpoint                                                          | Description                                                         |
| ------ | ----------------------------------------------------------------- | ------------------------------------------------------------------- |
| POST   | `/auth/login`                                                      | Sign in and receive an HTTP-only session cookie                     |
| POST   | `/auth/logout`                                                     | End the current session                                             |
| GET    | `/auth/me`                                                         | Get the current user's identity and role                            |
| GET    | `/activities`                                                      | Get activities and current participants                             |
| POST   | `/activities/{activity_name}/signup`                               | Sign up the authenticated student                                   |
| DELETE | `/activities/{activity_name}/unregister`                           | Unregister yourself, or (staff/admin) a participant by email        |

## User accounts

Accounts are provisioned by an administrator; there is no public registration or
client-controlled role selection. Usernames, email addresses, roles, and
PBKDF2-hashed passwords are stored in `users.json`. The file is created when
the first account is provisioned. From the `src` directory, create accounts
interactively:

```sh
python manage_users.py alice alice@mergington.edu student
python manage_users.py parent1 parent@mergington.edu parent
python manage_users.py teacher1 teacher@mergington.edu staff
```

The password is entered without being echoed and must be at least 12 characters.
Do not commit real account data. The local `users.json` file is git-ignored; set
the `USERS_FILE` environment variable to use a different location.

Student signup and self-unregistration are tied to the signed-in account's
email. Only staff/admin accounts can unregister other participants. Parent
accounts can view activity information but cannot modify signups. Sessions
expire after 12 hours and are held in memory, so restarting the server signs
everyone out.

Activity and participant data remains in memory and resets when the server
restarts.

## Tests

From the repository root, run:

```sh
python -m unittest discover -s tests -v
```
