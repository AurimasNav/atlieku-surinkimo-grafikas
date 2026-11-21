import { Platform } from 'react-native';
import { requestWidgetUpdate } from 'react-native-android-widget';

import { WIDGET_NAME } from './next-pickup-widget';
import { renderNextPickup } from './render';

/** Redraws the home screen widgets, if any, after the schedule, the place or a reminder changed. */
export async function updateWidgets(): Promise<void> {
  if (Platform.OS !== 'android') return;
  await requestWidgetUpdate({ widgetName: WIDGET_NAME, renderWidget: () => renderNextPickup() }).catch(() => {});
}
