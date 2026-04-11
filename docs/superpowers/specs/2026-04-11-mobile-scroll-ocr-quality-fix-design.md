# Mobile Scroll And OCR Quality Fix Design

## Scope

Fix two production issues reported on mobile:

- After importing a contract, the user cannot comfortably move around or zoom the contract confirmation view, and it is easy to miss the contract tab.
- The settings page cannot scroll vertically on mobile.
- OCR sometimes returns repeated blank-template or low-information placeholder text, which should be rejected instead of passed forward as a usable contract.

## Design

### Mobile Layout

- Keep desktop behavior unchanged.
- On screens up to 768px, make the app shell and settings page use dynamic viewport height and explicit scroll containers.
- Allow the document content area to scroll both vertically and horizontally with touch momentum.
- Keep the bottom mobile nav floating above browser chrome and preserve the existing bottom padding.

### Contract Confirmation Flow

- When OCR finishes on mobile, automatically switch to the contract panel so the user can inspect the recognized text first.
- When the user confirms and starts analysis, switch back to the chat panel so the review stream is visible.
- Show zoom controls in the OCR confirmation state too, and apply the selected zoom to the editable OCR text area.

### OCR Quality Gate

- Strengthen prompts to forbid blank template completion and repeated visible-field guessing.
- Detect obvious bad OCR results:
  - many repeated lines,
  - repeated underscore blank fields,
  - low unique-character density,
  - common template placeholders repeated several times.
- Do not reject a real contract template only because it contains blank underline fields. Blank fields are common in rental contracts, so placeholder-heavy text is only suspicious when it has weak contract signals or very low unique-character density.
- Do not reject real contract text solely because OCR repeats some blank template rows. Repeated rows are suspicious only when the extracted text lacks strong contract context.
- Retry once with a stricter prompt. If the retry is still suspicious, return a clear OCR quality error instead of continuing with bad text.

### Mobile Browser Chrome

- Account center uses its own mobile scroll container because the app body is intentionally locked.
- Add generous bottom scroll padding for real mobile browsers where the bottom address bar or keyboard overlaps form controls.

## Validation

- Frontend build must pass.
- Relevant frontend tests for `DocPanel` and `SideNav` should pass.
- Backend OCR unit tests should cover repeated placeholder rejection and retry behavior.
- Docker frontend/backend deployment should be attempted after checks.
