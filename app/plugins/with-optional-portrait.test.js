const { addOptionalPortrait } = require('./with-optional-portrait');

const portrait = { $: { 'android:name': 'android.hardware.screen.portrait', 'android:required': 'false' } };

describe('addOptionalPortrait', () => {
  it('declares the portrait screen as not required', () => {
    expect(addOptionalPortrait({})['uses-feature']).toEqual([portrait]);
  });

  it('keeps other features and replaces an earlier declaration', () => {
    const camera = { $: { 'android:name': 'android.hardware.camera' } };
    const required = { $: { 'android:name': 'android.hardware.screen.portrait', 'android:required': 'true' } };
    const manifest = addOptionalPortrait({ 'uses-feature': [camera, required] });
    expect(manifest['uses-feature']).toEqual([camera, portrait]);
    expect(addOptionalPortrait(manifest)['uses-feature']).toEqual([camera, portrait]);
  });
});
