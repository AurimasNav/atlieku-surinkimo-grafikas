const { addNativeDebugSymbols } = require('./with-native-debug-symbols');
const { addReleaseSigning } = require('./with-release-signing');

// The relevant part of Expo's android/app/build.gradle template.
const TEMPLATE = `
    signingConfigs {
        debug {
            storeFile file('debug.keystore')
        }
    }
    buildTypes {
        debug {
            signingConfig signingConfigs.debug
        }
        release {
            signingConfig signingConfigs.debug
            minifyEnabled enableMinifyInReleaseBuilds
        }
    }
`;

describe('addNativeDebugSymbols', () => {
  it('adds the symbol table to release builds only', () => {
    const gradle = addNativeDebugSymbols(TEMPLATE);
    expect(gradle).toMatch(/release \{\s+ndk \{\s+debugSymbolLevel 'SYMBOL_TABLE'\s+\}/);
    expect(gradle).toMatch(/debug \{\s+signingConfig signingConfigs\.debug\s+\}/);
  });

  it('is idempotent', () => {
    const once = addNativeDebugSymbols(TEMPLATE);
    expect(addNativeDebugSymbols(once)).toBe(once);
  });

  it('works together with release signing, in either order', () => {
    const a = addReleaseSigning(addNativeDebugSymbols(TEMPLATE));
    const b = addNativeDebugSymbols(addReleaseSigning(TEMPLATE));
    for (const gradle of [a, b]) {
      expect(gradle).toContain("debugSymbolLevel 'SYMBOL_TABLE'");
      expect(gradle).toContain(
        "signingConfig System.getenv('ANDROID_UPLOAD_STORE_FILE') ? signingConfigs.release : signingConfigs.debug",
      );
    }
  });

  it('fails when the template changes', () => {
    expect(() => addNativeDebugSymbols('android { }')).toThrow(/expected template/);
  });
});
