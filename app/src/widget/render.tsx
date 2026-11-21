'use no memo';

import i18n, { resolveLanguage } from '@/i18n';
import { useReminderActions } from '@/store/reminder-actions';
import { useSchedule } from '@/store/schedule';
import { useSettings } from '@/store/settings';

import { widgetModel } from './model';
import { NextPickupWidget } from './next-pickup-widget';

/** The widget for the saved state, in both themes (the launcher picks one). */
export function renderNextPickup(now = new Date()) {
  const { place, placeId, placeName, language } = useSettings.getState();
  const lang = resolveLanguage(language);
  const model = widgetModel({
    data: useSchedule.getState().data,
    place,
    placeId,
    placeName,
    done: useReminderActions.getState().done,
    now,
    t: i18n.getFixedT(lang),
    lang,
  });
  return {
    light: <NextPickupWidget model={model} scheme="light" />,
    dark: <NextPickupWidget model={model} scheme="dark" />,
  };
}
