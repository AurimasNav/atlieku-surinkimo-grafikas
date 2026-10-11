import * as Location from 'expo-location';

import { ADDRESSES_URL } from './config';
import { type AddressTable, findNearest, type NearestAddress } from './nearest';

/** Further than this from any served address: probably not at home, or not served here. */
const MAX_DISTANCE_M = 400;
/** Worse than this, the street may be wrong: keep the settlement but ask for the street. */
const MAX_STREET_ACCURACY_M = 75;

export type GeolocateResult =
  | { ok: true; address: NearestAddress; streetConfident: boolean }
  | { ok: false; reason: 'denied' | 'servicesOff' | 'unavailable' | 'offline' | 'far' };

let cached: AddressTable | null = null;

async function loadAddresses(): Promise<AddressTable> {
  if (!cached) {
    const response = await fetch(ADDRESSES_URL);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    cached = (await response.json()) as AddressTable;
  }
  return cached;
}

/**
 * Reads the current position once and finds the nearest served address on the phone.
 * The position itself is never sent or stored; only the address table is downloaded,
 * and it is the same file for everyone.
 */
export async function locateHome(): Promise<GeolocateResult> {
  const permission = await Location.requestForegroundPermissionsAsync();
  if (!permission.granted) return { ok: false, reason: 'denied' };
  if (!(await Location.hasServicesEnabledAsync())) return { ok: false, reason: 'servicesOff' };

  let position: Location.LocationObject;
  let table: AddressTable;
  try {
    // Start the download while the GPS gets a fix.
    const download = loadAddresses();
    position = await Location.getCurrentPositionAsync({
      accuracy: Location.Accuracy.High,
      // Don't push Google's "Location Accuracy" consent screen; plain GPS is enough here.
      mayShowUserSettingsDialog: false,
    });
    table = await download;
  } catch (error) {
    return { ok: false, reason: error instanceof TypeError || String(error).includes('HTTP') ? 'offline' : 'unavailable' };
  }

  const address = findNearest(table, position.coords.latitude, position.coords.longitude);
  if (!address || address.distance > MAX_DISTANCE_M) return { ok: false, reason: 'far' };

  const approximate = permission.android?.accuracy === 'coarse' || permission.ios?.accuracy === 'reduced';
  const accuracy = position.coords.accuracy ?? Infinity;
  return { ok: true, address, streetConfident: !approximate && accuracy <= MAX_STREET_ACCURACY_M };
}
