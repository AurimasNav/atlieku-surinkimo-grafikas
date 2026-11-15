// https://docs.expo.dev/guides/using-eslint/
const { defineConfig } = require('eslint/config');
const expoConfig = require("eslint-config-expo/flat");

module.exports = defineConfig([
  expoConfig,
  {
    ignores: ["dist/*"],
  },
  {
    // TypeScript already checks that namespace members exist. The import plugin's copy of the
    // check can't follow some compiled packages (expo-notifications 58's enums) and reports
    // false errors; typescript-eslint recommends turning it off for TypeScript files.
    files: ["**/*.ts", "**/*.tsx"],
    rules: {
      "import/namespace": "off",
    },
  },
]);
