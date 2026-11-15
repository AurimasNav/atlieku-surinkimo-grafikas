const { addReleaseSigning } = require('./with-release-signing');

// The relevant part of Expo SDK 57's android/app/build.gradle template.
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

describe('addReleaseSigning', () => {
  it('signs release builds with the upload key when the workflow provides one', () => {
    const gradle = addReleaseSigning(TEMPLATE);
    expect(gradle).toContain("storeFile file(System.getenv('ANDROID_UPLOAD_STORE_FILE'))");
    expect(gradle).toContain(
      "signingConfig System.getenv('ANDROID_UPLOAD_STORE_FILE') ? signingConfigs.release : signingConfigs.debug",
    );
    // Debug builds keep the debug key.
    expect(gradle).toMatch(/debug \{\s+signingConfig signingConfigs\.debug/);
  });

  it('is idempotent', () => {
    const once = addReleaseSigning(TEMPLATE);
    expect(addReleaseSigning(once)).toBe(once);
  });

  it('fails when the template changes', () => {
    expect(() => addReleaseSigning('android { }')).toThrow(/expected template/);
  });
});
