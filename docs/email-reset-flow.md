# Email Reset / Change Flow Plan

## Overview

A secure, user-friendly process for handling email change requests, including:

- Requesting an email change (with validation and rate limiting)
- Sending a confirmation link to the new email
- Verifying the link and updating the email
- Security and edge case handling

---

## 1. Initiate Email Change (API Endpoint)

- **Input:** Authenticated user, new email address
- **Steps:**
  - Validate new email format
  - Check for uniqueness (case-insensitive)
  - Remove any previous pending email changes for the user
  - Generate a secure, random token and expiry timestamp
  - Store the pending change in the database (PendingEmailChange model) with user, new email, token, and expiry
  - Construct a confirmation link with the token as a query parameter
  - Send the link to the new email address via Celery background task
  - Respond with a generic message (do not reveal if email is already in use)

## 2. Token Generation & Storage

- Use a securely generated random token (e.g., `secrets.token_urlsafe`)
- Store the token, user, new email, and expiry in the PendingEmailChange model
- Set token expiry (e.g., 24 hours)
- Remove any previous pending changes for the user before creating a new one

## 3. Confirmation Link

- Format: `https://yourdomain.com/account/confirm-email-change/?token=...`
- Token is stored in the database, not stateless
- Link is sent only to the new email address

## 4. Confirm Email Change (API Endpoint)

- **Input:** Token (from query param)
- **Steps:**
  - Look up the pending change in the database by token
  - Check expiry
  - Fetch user by ID, verify user still exists
  - Check that the email is still unique
  - Update user's email and mark as verified
  - Delete the pending change entry
  - (Optional) Invalidate sessions/JWTs if needed

## 5. Security & Edge Cases

- Only allow one pending email change per user at a time
- Delete expired or used tokens
- Rate-limit requests (e.g., 3/hour)
- Respond with generic messages to avoid information leaks

## 6. Edge Cases

- Token expired
- User deleted or inactive
- Email already taken after token issued
- User requests multiple changes (latest token wins)

## 7. Tech Stack Notes

- Celery for async email sending
- Django's ORM for database interactions
- Can be used with any frontend (web, mobile, SPA)

---

**Note:**
This flow uses a stateful (DB-backed) approach for maximum control, auditability, and security. If a stateless (token-based) flow is desired, see previous versions of this document for guidance.
