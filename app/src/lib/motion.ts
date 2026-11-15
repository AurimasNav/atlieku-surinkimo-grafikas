import { useReducedMotion } from 'react-native-reanimated';

/**
 * Wraps the entering and layout animations of a screen: `entering={motion(FadeIn)}`. When the
 * phone's animations are off (Android: Accessibility → "Remove animations", or the developer
 * animation scales at 0), there is no animation at all and views show right away. That is what
 * the setting asks for, and it is required with Reanimated 4.7 (Expo SDK 58): with animations
 * off, a view with an entering animation stays invisible, which emptied the welcome screen.
 */
export function useMotion() {
  const reduced = useReducedMotion();
  return <T>(animation: T): T | undefined => (reduced ? undefined : animation);
}
