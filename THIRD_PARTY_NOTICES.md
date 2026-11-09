# Third-party dependencies and research references

This repository's original implementation is MIT licensed. Dependencies retain their own licenses; do not infer redistribution rights for proprietary SDKs from this project's license.

| Dependency | License / usage |
| --- | --- |
| Kotlin / kotlinx.coroutines, AndroidX | Apache-2.0; Android runtime/UI |
| Android Gradle Plugin / Gradle wrapper | Apache-2.0; build tooling; wrapper from Gradle v8.9.0 |
| ZXing core 3.5.3 | Apache-2.0; on-device QR decoding |
| OkHttp / MockWebServer 4.12.0, Gson 2.11.0 | Apache-2.0; HTTP/JSON and tests |
| JUnit 4.13.2 | EPL-1.0; JVM tests |
| FastAPI, SQLAlchemy, Pydantic | MIT; backend framework/data validation |
| Uvicorn | BSD-3-Clause; ASGI server |
| argon2-cffi | MIT; password hashing (native implementation retains its own notices) |
| qrcode | BSD; printable QR generation |
| Pillow | HPND; PNG output |
| psycopg | LGPL-3.0; optional PostgreSQL driver |
| Pytest, HTTPX | MIT / BSD-3-Clause; backend tests |
| Caddy | Apache-2.0; optional TLS reverse proxy |

Pinned direct runtime/test versions live in Gradle and backend requirements files. Transitive dependencies retain their package metadata/notices. Gradle downloads and packages applicable Java library metadata. Python package distributions provide license files in their dist-info directories.

No code/assets from TapInsight (GPL-3.0), xg-glass-sdk (Apache-2.0), or the experimental native spatial SDK (Apache-2.0) are bundled. They were inspected as research references. RayNeo OpenClaw is MIT except the separately licensed Mercury binaries; it was used to verify API usage. The small optional adapter here is independently written against those APIs. See [SDK research](docs/RESEARCH.md) for pinned source commits.

**No Mercury, RayNeo IPC or RayNeo OpenXR proprietary AARs are distributed.** Users must acquire a valid license and follow RayNeo's terms before building/redistributing any APK containing them. The default APK contains no RayNeo proprietary SDK.

Optional model detection uses OpenCV (Apache-2.0), NumPy (BSD-3-Clause), and the
Apache-2.0 NanoDet Plus adapter/weights from OpenCV Zoo revision
`48b10fa505aeb51fbd127fc60a5c660040e823b7`. The adapter is vendored unmodified with
its LICENSE under `backend/app/vendor/nanodet/`; weights are checksum-verified,
downloaded separately and ignored by Git. See [model provenance](docs/MODEL_DETECTION.md).
The downloaded coffee photo used in local evidence is CC0 by Rachel Michetti,
courtesy of Pikolo Espresso Bar, via scikit-image v0.19.3. It is not bundled in source.
