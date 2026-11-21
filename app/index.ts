// The app's entry: Expo Router, plus the Android home screen widget's task handler, which must
// be registered at startup so the launcher can draw the widget without opening the app.
import 'expo-router/entry';

import { Platform } from 'react-native';
import { registerWidgetTaskHandler } from 'react-native-android-widget';

import { widgetTaskHandler } from './src/widget/task-handler';

if (Platform.OS === 'android') registerWidgetTaskHandler(widgetTaskHandler);
