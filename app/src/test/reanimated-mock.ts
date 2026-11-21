/**
 * A stand-in for react-native-reanimated in screen tests: the package's own mock doesn't load
 * under Jest here ("setCSSEventHandler is not available in JSReanimated"). Covers what the app
 * uses; animations are skipped, as with "reduce motion" on.
 */
import { FlatList, ScrollView, Text, View } from 'react-native';

/** Layout animation builders: `FadeIn.delay(90).duration(400)` and the like. */
const builder: unknown = new Proxy(() => builder, { get: () => () => builder });

const Animated = { View, Text, ScrollView, FlatList, createAnimatedComponent: <T,>(component: T) => component };

export default Animated;
export const FadeIn = builder;
export const FadeInDown = builder;
export const LinearTransition = builder;
export const Easing = builder;
export const useReducedMotion = () => true;
export const useSharedValue = <T,>(value: T) => ({ value, get: () => value, set: () => {} });
export const useAnimatedStyle = () => ({});
export const withSpring = <T,>(value: T) => value;
export const withTiming = <T,>(value: T) => value;
export const withRepeat = <T,>(value: T) => value;
export const cancelAnimation = () => {};
