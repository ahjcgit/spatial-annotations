plugins { id("com.android.application"); id("org.jetbrains.kotlin.android") }
val withRayneo = providers.gradleProperty("withRayneo").orNull == "true"
android {
    namespace = "org.spatial.annotations"
    compileSdk = 35
    defaultConfig {
        applicationId = "org.spatial.annotations"
        minSdk = 26
        targetSdk = 35
        versionCode = 1
        versionName = "0.1.0"
    }
    buildFeatures { buildConfig = true; viewBinding = true }
    buildTypes {
        debug {
            manifestPlaceholders["cleartext"] = "true"
            if (providers.gradleProperty("presentationDemo").orNull == "true") applicationIdSuffix = ".branchdemo"
        }
        release { manifestPlaceholders["cleartext"] = "false"; isMinifyEnabled = false }
    }
    sourceSets.getByName("main") {
        java.srcDir(if (withRayneo) "src/rayneo/java" else "src/standard/java")
        if (withRayneo) { res.srcDir("src/rayneo/res"); manifest.srcFile("src/rayneo/AndroidManifest.xml") }
    }
    compileOptions { sourceCompatibility = JavaVersion.VERSION_17; targetCompatibility = JavaVersion.VERSION_17 }
    kotlinOptions { jvmTarget = "17" }
    testOptions { unitTests.isReturnDefaultValues = true }
    packaging { resources.excludes += "/META-INF/{AL2.0,LGPL2.1}" }
}
dependencies {
    implementation("androidx.appcompat:appcompat:1.7.0")
    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.8.7")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.9.0")
    implementation("com.squareup.okhttp3:okhttp:4.12.0")
    implementation("com.google.code.gson:gson:2.11.0")
    implementation("com.google.zxing:core:3.5.3")
    testImplementation("junit:junit:4.13.2")
    testImplementation("com.squareup.okhttp3:mockwebserver:4.12.0")
    testImplementation("org.jetbrains.kotlinx:kotlinx-coroutines-test:1.9.0")
    if (withRayneo) {
        val aars = fileTree("libs") { include("MercuryAndroidSDK*.aar") }
        require(aars.files.size == 1) { "Install exactly one licensed MercuryAndroidSDK*.aar in app/libs; see docs/RAYNEO_SETUP.md" }
        implementation(aars)
        implementation("androidx.constraintlayout:constraintlayout:2.1.4")
    }
}

// Optional deterministic PNG replay uses the exact production ZXing recognizer.
tasks.withType<Test>().configureEach {
    providers.gradleProperty("replayDir").orNull?.let {
        systemProperty("replayDir", file(it).absolutePath)
        inputs.files(fileTree(it) { exclude("replay-results.jsonl") })
        outputs.upToDateWhen { false }
    }
    providers.gradleProperty("demoData").orNull?.let {
        systemProperty("demoData", file(it).absolutePath)
        outputs.upToDateWhen { false }
    }
}
