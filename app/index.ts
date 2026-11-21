// The app's entry. Android also starts the JavaScript without any screen: for the background
// schedule refresh, for the reminder buttons pressed while the app is closed, and to draw the
// home screen widget. Expo Router only loads the screens (and the root layout) when it renders,
// so the background tasks and the widget's task handler must be set up here, before anything
// else, or Android finds nothing to run.
import './src/lib/background';
import 'expo-router/entry';

import { Platform } from 'react-native';
import { registerWidgetTaskHandler } from 'react-native-android-widget';

import { widgetTaskHandler } from './src/widget/task-handler';

if (Platform.OS === 'android') registerWidgetTaskHandler(widgetTaskHandler);
