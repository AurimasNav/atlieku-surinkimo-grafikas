import {
  Manrope_500Medium,
  Manrope_600SemiBold,
  Manrope_700Bold,
  Manrope_800ExtraBold,
  useFonts,
} from '@expo-google-fonts/manrope';
import { DarkTheme, DefaultTheme, Stack, ThemeProvider } from 'expo-router';
import * as SplashScreen from 'expo-splash-screen';
import { StatusBar } from 'expo-status-bar';
import { useEffect } from 'react';
import { AppState } from 'react-native';

import i18n, { resolveLanguage } from '@/i18n';
// Importing this module also defines the background task, which must happen at startup.
import { registerBackgroundRefresh } from '@/lib/background';
import { configureNotifications, syncReminders } from '@/lib/notifications';
import { useSchedule } from '@/store/schedule';
import { useSettings } from '@/store/settings';
import { useTheme } from '@/theme';

SplashScreen.preventAutoHideAsync();

export default function RootLayout() {
  const theme = useTheme();
  const language = useSettings((s) => s.language);
  const [fontsLoaded, fontError] = useFonts({
    Manrope_500Medium,
    Manrope_600SemiBold,
    Manrope_700Bold,
    Manrope_800ExtraBold,
  });

  useEffect(() => {
    if (fontsLoaded || fontError) SplashScreen.hideAsync();
  }, [fontsLoaded, fontError]);

  useEffect(() => {
    i18n.changeLanguage(resolveLanguage(language));
  }, [language]);

  useEffect(() => {
    const refreshAndSync = () => useSchedule.getState().refresh().finally(() => syncReminders());

    configureNotifications().then(refreshAndSync);
    registerBackgroundRefresh().catch(() => {});

    const appState = AppState.addEventListener('change', (state) => {
      if (state === 'active') refreshAndSync();
    });
    // Re-plan reminders whenever the inputs to the plan change.
    const unsubscribeSettings = useSettings.subscribe((state, prev) => {
      if (state.place !== prev.place || state.reminder !== prev.reminder || state.language !== prev.language) {
        syncReminders();
      }
    });
    const unsubscribeSchedule = useSchedule.subscribe((state, prev) => {
      if (state.data !== prev.data) syncReminders();
    });

    return () => {
      appState.remove();
      unsubscribeSettings();
      unsubscribeSchedule();
    };
  }, []);

  if (!fontsLoaded && !fontError) return null;

  const navigationTheme = theme.dark ? DarkTheme : DefaultTheme;
  return (
    <ThemeProvider
      value={{
        ...navigationTheme,
        colors: { ...navigationTheme.colors, background: theme.background, primary: theme.primary },
      }}>
      <StatusBar style={theme.dark ? 'light' : 'dark'} />
      <Stack
        screenOptions={{
          headerShown: false,
          contentStyle: { backgroundColor: theme.background },
          animation: 'slide_from_right',
        }}>
        <Stack.Screen name="onboarding" options={{ animation: 'fade' }} />
        <Stack.Screen name="setup/done" options={{ animation: 'fade_from_bottom' }} />
      </Stack>
    </ThemeProvider>
  );
}
