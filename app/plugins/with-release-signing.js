// Signs Android release builds with the upload key when the release workflow provides one
// (.github/workflows/release.yml). Without it, as in local builds, release builds keep Expo's
// default debug signing, which Google Play rejects.
//
// The key comes from environment variables, so it never ends up in the generated project:
//   ANDROID_UPLOAD_STORE_FILE, ANDROID_UPLOAD_STORE_PASSWORD, ANDROID_UPLOAD_KEY_ALIAS,
//   ANDROID_UPLOAD_KEY_PASSWORD
const { withAppBuildGradle } = require('expo/config-plugins');

const RELEASE_CONFIG = `
        release {
            if (System.getenv('ANDROID_UPLOAD_STORE_FILE')) {
                storeFile file(System.getenv('ANDROID_UPLOAD_STORE_FILE'))
                storePassword System.getenv('ANDROID_UPLOAD_STORE_PASSWORD')
                keyAlias System.getenv('ANDROID_UPLOAD_KEY_ALIAS')
                keyPassword System.getenv('ANDROID_UPLOAD_KEY_PASSWORD')
            }
        }`;

function addReleaseSigning(gradle) {
  if (gradle.includes('ANDROID_UPLOAD_STORE_FILE')) return gradle;

  const withConfig = gradle.replace(/signingConfigs\s*\{/, (match) => match + RELEASE_CONFIG);
  // The release build type of Expo's template signs with the debug key.
  const withBuildType = withConfig.replace(
    /(buildTypes\s*\{[\s\S]*?release\s*\{[\s\S]*?)signingConfig signingConfigs\.debug/,
    "$1signingConfig System.getenv('ANDROID_UPLOAD_STORE_FILE') ? signingConfigs.release : signingConfigs.debug",
  );
  if (withConfig === gradle || withBuildType === withConfig) {
    // Fail the build rather than upload a debug-signed bundle after a template change.
    throw new Error('with-release-signing: android/app/build.gradle no longer matches the expected template');
  }
  return withBuildType;
}

module.exports = function withReleaseSigning(config) {
  return withAppBuildGradle(config, (mod) => {
    mod.modResults.contents = addReleaseSigning(mod.modResults.contents);
    return mod;
  });
};

module.exports.addReleaseSigning = addReleaseSigning;
