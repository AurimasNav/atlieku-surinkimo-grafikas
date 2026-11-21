// The app's entry. Android also starts the JavaScript without any screen: for the background
// schedule refresh and for the reminder buttons pressed while the app is closed. Expo Router
// only loads the screens (and the root layout) when it renders, so the background tasks must be
// defined here, before anything else, or Android finds no task to run.
import './src/lib/background';
import 'expo-router/entry';
