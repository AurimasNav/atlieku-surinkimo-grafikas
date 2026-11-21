import type { WidgetTaskHandler } from 'react-native-android-widget';

import { renderNextPickup } from './render';

/**
 * Runs without the app's UI when the launcher adds, resizes or periodically updates the widget
 * (and every few hours for "Tomorrow" to become "Today"). The stores load the saved state
 * synchronously, so the widget is drawn from what the app saved last.
 */
export const widgetTaskHandler: WidgetTaskHandler = async ({ widgetAction, renderWidget }) => {
  if (widgetAction === 'WIDGET_ADDED' || widgetAction === 'WIDGET_UPDATE' || widgetAction === 'WIDGET_RESIZED') {
    renderWidget(renderNextPickup());
  }
};
