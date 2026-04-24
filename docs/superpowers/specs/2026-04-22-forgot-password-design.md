# Forgot Password Design

## Goal

Add a standalone "Forgot Password" flow so unauthenticated users can reset their password by email verification code.

## Scope

- Add a standalone forgot-password page in the auth flow.
- Add public backend endpoints for password-reset code delivery and password reset.
- Unify password policy across registration, forgot-password reset, and authenticated password change.
- Preserve the current auth-shell visual style and `authView` switching pattern.

## Non-Goals

- No auth system rewrite.
- No new routing library.
- No automatic login after password reset.
- No forced migration for existing users with weaker passwords.

## UX Flow

1. User opens login page.
2. User clicks `忘记密码？`.
3. App switches to a dedicated forgot-password page.
4. User enters email and requests a verification code.
5. Backend responds with a generic success message to avoid email enumeration.
6. In dev mode, the UI may also show `dev_code` if the backend includes it.
7. User enters verification code, new password, and confirmation password.
8. On success, the page shows a success message and redirects back to login after a short delay.

## Frontend Design

### Navigation

- Extend `authView` in `frontend/src/App.tsx` from:
  - `landing | login | register`
- To:
  - `landing | login | register | forgot_password`

### New Page

- Add `frontend/src/pages/ForgotPasswordPage.tsx`.
- Reuse the existing auth-shell layout and auth form styling.
- Required fields:
  - Email
  - Verification code
  - New password
  - Confirm password
- Primary actions:
  - `获取验证码`
  - `重置密码`
- Secondary action:
  - `返回登录`

### Login Entry

- Add a `忘记密码？` entry near the password field or auth footer on the login page.

### Shared Password Validation

- Add a lightweight frontend password validation utility reused by:
  - `RegisterPage`
  - `ForgotPasswordPage`
  - `SettingsPage`

Password rule:

- At least 8 characters
- At least one uppercase letter
- At least one lowercase letter
- At least one number

Unified validation message:

- `密码必须至少 8 位，并包含大写字母、小写字母和数字`

## Backend Design

### Public Endpoints

- Add `POST /api/auth/password/send-reset-code`
- Add `POST /api/auth/password/reset`

### Request Behavior

#### `POST /api/auth/password/send-reset-code`

Input:

- `email`

Behavior:

- Validate email format.
- Apply rate limiting by IP and email.
- If the account exists and has an email, send a password-reset verification code.
- If the account does not exist, do not reveal that fact.
- Return a generic success payload either way.
- In dev mode, include `dev_code` only when a real code was generated.

Response message:

- `如果该邮箱已注册，我们已发送验证码，请查收邮箱`

#### `POST /api/auth/password/reset`

Input:

- `email`
- `code`
- `new_password`

Behavior:

- Validate email format.
- Enforce the shared password policy.
- Look up the user by email.
- Consume a password-reset code scoped specifically to reset-password usage.
- Update password hash.
- Return success without logging the user in.

### Password Policy

- Introduce a shared backend validator for password strength.
- Reuse it in:
  - registration
  - authenticated password reset
  - unauthenticated forgot-password reset

### Verification Code Scope

- Separate registration codes from password-reset codes.
- Registration codes remain under the existing email-verification flow.
- Forgot-password codes use a dedicated code kind such as `password_reset`.
- This avoids cross-use of codes between registration and password reset.

## Security Notes

- Avoid user enumeration by returning a generic success message from the public send-code endpoint.
- Keep public reset endpoints rate-limited.
- Do not auto-login after password reset.
- Do not relax the existing JWT-protected security-center flow.

## Testing Plan

### Backend

- Public send-reset-code returns generic success for existing and non-existing emails.
- Public password reset succeeds with valid reset code.
- Weak passwords are rejected by register and both reset flows.
- Reset codes are isolated from registration codes.

### Frontend

- Login page exposes a forgot-password navigation action.
- Forgot-password page sends a code and handles success/dev-code display.
- Forgot-password page validates password strength and confirmation.
- Forgot-password page resets password and navigates back to login.
- Register and settings pages use the same stronger password rule.

## Risks

- Existing frontend tests already contain stale fetch mocks for some auth/file flows; password-flow tests should use real `Response` objects or response shapes compatible with `safeFetchJSON`.
- Existing users with weak passwords may still log in until they next change their password; this is intentional and avoids surprise lockouts.
