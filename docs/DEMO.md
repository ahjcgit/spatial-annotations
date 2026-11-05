# Two-user, two-object demonstration

## Preparation

Use two visually identical mugs (or two identical boxes), a printer, a LAN backend, and two users. One glasses device can be passed between users with explicit sign-out/sign-in. Two devices may be used concurrently. A desktop browser is the typing companion.

```bash
cd spatial-annotations
cp .env.example .env  # only if .env does not exist yet
# Check port availability; do not use reserved port 5173.
ss -lnt '( sport = :8000 )'
docker compose up -d --build
docker compose ps
```

Open `http://SERVER_LAN_IP:8000` from the companion. `/health` should return `{"status":"ok"}`. Use HTTPS for credentials outside a controlled LAN. The companion and glasses must point to the **same server**.

## Reproducible software demonstration

This path exercises real HTTP endpoints and persistent Docker storage without needing glasses:

```bash
python3.11 -m venv .venv
.venv/bin/pip install -r backend/requirements-dev.txt
.venv/bin/python scripts/e2e.py --url http://SERVER_LAN_IP:8000
```

The script creates two uniquely named accounts with random passwords, two objects, and a group. It asserts public sharing, private isolation, group access before/after membership, author-only edits/deletes, and object disambiguation. It then restores Bob's membership for the physical demo. It leaves data in the server and saves credentials/IDs in ignored `demo-data.json` (mode 0600), not in console output. Rerunning creates new data; it does not wipe prior users. Use a fresh E2E dataset for each Android smoke test; that test adds a note and checks exact counts. Keep credentials local.

Generate matching QR labels for the two marker IDs in that file:

```bash
.venv/bin/python scripts/generate_markers.py --count 1 --marker-id MUG_A_MARKER_UUID --output markers
.venv/bin/python scripts/generate_markers.py --count 1 --marker-id MUG_B_MARKER_UUID --output markers
```

Open `markers/print.html` and print. Repeated runs append to its manifest. Alternatively look up each marker in the companion and use **Print marker**, or open `/markers/UUID.png`. Each label encodes `spatial:v1:UUID`. Print approximately 65 mm wide, preserve the white quiet zone and attach flat. Do not attach the same UUID to both mugs.

The steps below can instead be done manually with fresh accounts and markers, which demonstrates the UI as well as the API.

## Manual physical demo

1. **Accounts.** Open the companion in two separate browser profiles/private windows. Register Alice and Bob (unique names, passwords at least ten characters). Expected: each window shows its own username. Reloading drops its in-memory browser session, so sign in again if needed.
2. **Object A.** Alice clicks **New marker**, opens **Register / update object**, enters “Mug A”, optional location “Lab table — left”, and saves. Object metadata is public. Print the label and attach it to mug A. Expected: the displayed marker UUID is stable; lookup returns the same object.
3. **Object B.** Create and print a second marker with name “Mug B”, optionally the same location. Attach to the identical second mug. Expected: different marker/object UUIDs despite identical appearance and proximity.
4. **Public note.** Select A. Alice creates “Mug A: clean before use” with Public visibility. Bob looks up A's marker and refreshes. Expected: both users and an anonymous window can read it, with Alice's author and server timestamp.
5. **Private note.** Alice creates “Alice's private observation” with Private visibility on A. Expected: Alice sees it; Bob/anonymous do not. Bob cannot read it even with its annotation UUID through `GET /annotations/{id}` (404). The object response contains neither its text nor a total hidden count.
6. **Group note.** Alice creates “Lab partners” under Your groups, then creates “Team inspection pending” on A with Group visibility and that group. Expected: Bob cannot see it yet. Alice adds Bob's registered username. Bob refreshes: now sees public and group notes, but not Alice's private note.
7. **Glasses retrieval.** Install/start the APK using RAYNEO_SETUP.md. Enter the same LAN/HTTPS URL, sign in as Alice, open **Scan / view annotations**, and select **Start camera / scan next object**. Allow CAMERA. Look at A's QR. Expected on supported hardware: “Mug A”, three authorized notes, readable text, navigation and author/time details. Acquisition stops after detection. Use Refresh after creating a companion note. Physical hardware validation is still pending for this repository.
8. **Second user on glasses.** Return to Settings, sign out, sign in as Bob and scan A again. Expected: public and group notes; no private note. Alice's prior note state is cleared. The default APK uses ordinary Android views; use the opt-in licensed Mercury build for the binocular viewer and test fusion/temple controls separately.
9. **Disambiguation.** Scan B. Expected: “Mug B” and zero annotations (until you create one on B). Scan A again: its notes return. Swap the mugs' positions without swapping labels: notes follow the labels, not coordinates or appearance.
10. **Persistence.** Run `docker compose restart backend`, wait for healthy status, and refresh/scan A. Expected: objects, accounts, notes and group memberships survive. Do not remove the named volume. Restart the Android app: account session can be recovered from encrypted storage until expiry; QR re-identification retrieves the same server notes. This proves identifier/database persistence, not SLAM relocalization.
11. **Revocation.** Alice removes Bob from the group using the member's user ID displayed under the group. Bob refreshes. Expected: only public notes remain. A direct group-note request returns 404. Re-add Bob if the demonstration should end in a shared state.
12. **Author-only changes.** Bob creates his own public note on A. Alice can read it but cannot edit/delete it. The author's companion offers Edit/Delete; direct API attempts from the other user return 403. Alice editing her own public note to Private removes it from Bob's next retrieval.

## Explicit simulation without a camera

On the standard Android app, open **Manual marker · SIMULATION** and paste the UUID/payload from a registered object. The screen remains labeled SIMULATION. It uses the same authentication, HTTP client and server permissions as optical scanning, but **does not validate the camera or physical-object detection**. JVM tests separately verify QR recognition using generated pixel images. The desktop companion performs the same identity lookup by typed marker.

## Expected failures

| Test | Expected behavior |
| --- | --- |
| Scan an unregistered valid marker | Unknown object; signed-in user can register via app/companion |
| Scan unrelated QR / random text | Ignored by optical recognizer; manual parser reports invalid UUID |
| Register an existing marker again | HTTP 409; look up existing object instead |
| Deny camera permission | Meaningful status and settings/manual simulation route; no crash |
| Close another app using the camera / retry | Camera acquisition can resume; log camera errors for firmware analysis |
| Stop backend / lose Wi-Fi | Timeout/error with no stale private-note result presented as fresh data |
| Token expires or is revoked | 401 clears session; sign in again |
| Enter HTTP public host in Android | Rejected; release build requires HTTPS for all hosts |
| Choose group visibility with no member group | Validation/403; no unauthorized note is created |
| Bob requests Alice's private annotation ID | 404, no content in response |
| User edits object metadata they did not create | 403 |
| Same marker copied onto another object | Same identity by design; no anti-counterfeit guarantee |
| Move head while reading | Head/screen-locked panel, not physically anchored text |

Record the actual model, OS, AAR version, test date, result and camera ID for every physical test. A successful emulator/manual lookup does not satisfy the physical-glasses acceptance criterion. World-space alignment is a separate future experiment, not part of this demonstration's claimed results.
