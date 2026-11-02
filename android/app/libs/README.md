No proprietary SDK files are distributed here.

The default build requires no RayNeo SDK. For the optional adapter, obtain a licensed
`MercuryAndroidSDK*.aar` from the official RayNeo Android ARDK download page, place
exactly one AAR here, and build with `./gradlew -PwithRayneo=true assembleDebug`.
See `../../../docs/RAYNEO_SETUP.md` for source evidence, installation and validation.
