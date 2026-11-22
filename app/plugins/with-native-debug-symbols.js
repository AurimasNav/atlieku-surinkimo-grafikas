// Puts the native libraries' symbol tables into release bundles, so Google Play can show readable
// native stack traces for crashes and ANRs (and stops warning that the bundle "contains native
// code, and you've not uploaded debug symbols"). Gradle extracts them into the bundle's metadata;
// the libraries in the app stay stripped, so the download size doesn't change.
//
// expo-build-properties (SDK 58) has no option for this, only `doNotStrip`.
// SYMBOL_TABLE (function names) rather than FULL keeps the bundle small; it is what Play needs to
// symbolicate stack traces.
const { withAppBuildGradle } = require('expo/config-plugins');

const NDK_CONFIG = `
            ndk {
                debugSymbolLevel 'SYMBOL_TABLE'
            }`;

function addNativeDebugSymbols(gradle) {
  if (gradle.includes('debugSymbolLevel')) return gradle;

  const updated = gradle.replace(/(buildTypes\s*\{[\s\S]*?\brelease\s*\{)/, (match) => match + NDK_CONFIG);
  if (updated === gradle) {
    throw new Error('with-native-debug-symbols: android/app/build.gradle no longer matches the expected template');
  }
  return updated;
}

module.exports = function withNativeDebugSymbols(config) {
  return withAppBuildGradle(config, (mod) => {
    mod.modResults.contents = addNativeDebugSymbols(mod.modResults.contents);
    return mod;
  });
};

module.exports.addNativeDebugSymbols = addNativeDebugSymbols;
