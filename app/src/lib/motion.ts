import { useReducedMotion } from 'react-native-reanimated';

/**
 * Wraps the entering and layout animations of a screen: `entering={motion(FadeIn)}`. When the
 * phone's animations are off (Android: Accessibility → "Remove animations", or the developer
 * animation scales at 0), there is no animation at all and views show right away. That is what
 * the setting asks for, and it is required with Reanimated 4.7.1 (Expo SDK 58): with animations
 * off, a view with an entering animation stays invisible, which emptied the welcome screen
 * (https://github.com/software-mansion/react-native-reanimated/issues/11174, to be fixed in
 * Reanimated 4.7.2 and 4.8.0). Keep it after that fix: skipping the animations is still right.
 */
export function useMotion() {
  const reduced = useReducedMotion();
  return <T>(animation: T): T | undefined => (reduced ? undefined : animation);
}
