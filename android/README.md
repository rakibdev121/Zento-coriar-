# ZENTO Android apps (website, admin, rider)

Each app is a thin Android shell around your deployed ZENTO site: the website app opens `/`, the admin app `/admin`, the rider app `/rider`. They share one code base (`app/src/main/java/.../MainActivity.java`) and differ by *flavor* (name, icon, start page). **You do not need Java or Android Studio: GitHub builds the APKs for you.**

The shell handles back button, sign-in memory, photo/ID upload (rider application), PDF download to the Downloads folder, phone/WhatsApp links, and an offline screen with *Try again*.

## Build the APKs (no computer setup needed)

1. Deploy the server first (see the main README) and note its address, for example `https://zento.onrender.com`. It must be `https://`.
2. GitHub repo -> **Settings -> Secrets and variables -> Actions -> Variables -> New repository variable**
   Name `ZENTO_BASE_URL`, value your address (no `/` at the end).
3. GitHub repo -> **Actions -> Build Android apps -> Run workflow**.
4. After about 5-8 minutes open the finished run and download the **zento-apks** artifact: `zento-website.apk`, `zento-admin.apk`, `zento-rider.apk`. Send each APK to a phone and install it (allow "install unknown apps").

If you change the server address, run the workflow again (the address is built into the APK).

## Signed release key (needed for Google Play or for updating an installed app)

Without a key the APKs are signed with Android's debug key. They install fine, but a key made later will not be able to update them. To use your own key, once:

```bash
keytool -genkeypair -v -keystore zento.jks -alias zento -keyalg RSA -keysize 2048 -validity 10000
base64 -w0 zento.jks      # copy the output
```

Add repository **secrets** (Settings -> Secrets and variables -> Actions -> Secrets): `ANDROID_KEYSTORE_BASE64` (the base64 text), `ANDROID_KEYSTORE_PASSWORD`, `ANDROID_KEY_ALIAS` (`zento`), `ANDROID_KEY_PASSWORD`. **Keep zento.jks safe and never commit it.** If you lose it you cannot update the app on Google Play.

## Icons

`app/src/<flavor>/res/mipmap-*` hold the launcher icons (website = Z + box, admin = shield, rider = scooter). The 512 px store icons are `*-store-icon-512.png`. The matching web icons are in `frontend/icons`, `frontend/admin/icons` and `frontend/rider/icons`.

## Build on your own computer (optional)

Install JDK 17, Android SDK 34 and Gradle 8.7, then:

```bash
ZENTO_BASE_URL=https://your-site gradle -p android assembleRiderRelease
```
