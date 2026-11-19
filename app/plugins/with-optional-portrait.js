// The app is locked to portrait ("orientation" in app.json). Android reads that as a hardware
// requirement, android.hardware.screen.portrait, and Google Play then hides the app from devices
// that don't report the feature (some tablets, desktops, XR headsets). The app works on them, so
// the feature is declared as not required.
const { withAndroidManifest } = require('expo/config-plugins');

const FEATURE = 'android.hardware.screen.portrait';

function addOptionalPortrait(manifest) {
  const features = (manifest['uses-feature'] ?? []).filter((item) => item.$?.['android:name'] !== FEATURE);
  manifest['uses-feature'] = [...features, { $: { 'android:name': FEATURE, 'android:required': 'false' } }];
  return manifest;
}

module.exports = (config) =>
  withAndroidManifest(config, (cfg) => {
    addOptionalPortrait(cfg.modResults.manifest);
    return cfg;
  });
module.exports.addOptionalPortrait = addOptionalPortrait;
