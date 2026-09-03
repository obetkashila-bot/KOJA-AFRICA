plugins { id("com.android.application"); id("com.google.gms.google-services") }

android { namespace = "com.kojaafrica.app"; compileSdk = 36
    defaultConfig { applicationId = "com.kojaafrica.app"; minSdk = 23; targetSdk = 35; versionCode = 1; versionName = "1.0" }
}

dependencies {
    implementation(platform("com.google.firebase:firebase-bom:34.18.0"))
    implementation("com.google.firebase:firebase-messaging")
    implementation("androidx.core:core:1.17.0")
    implementation("androidx.appcompat:appcompat:1.7.1")
}


