import * as Location from 'expo-location';

import { ADDRESSES_URL, KAUNO_POINTS_URL } from './config';
import type { KaunoAddress } from './kauno';
import { type AddressTable, findNearest, type NearestAddress, nearestPoint } from './nearest';

/** Further than this from any served address: probably not at home, or not served here. */
const MAX_DISTANCE_M = 400;
/** Worse than this, the street may be wrong: keep the settlement but ask for the street. */
const MAX_STREET_ACCURACY_M = 75;

/** kauno-r/points.json: the addresses of Kauno r. with coordinates. */
type KaunoPoints = {
  /** [eldership file, eldership, town, street] */
  places: [string, string, string, string][];
  /** [lat * 1e5, lon * 1e5, place index, house number] */
  points: [number, number, number, string][];
};

export type GeolocateResult =
  | { ok: true; address: NearestAddress; streetConfident: boolean }
  /** The nearest address is in Kauno r. (UAB „Kauno švara“). */
  | { ok: true; address?: undefined; kauno: KaunoAddress; streetConfident: boolean }
  | { ok: false; reason: 'denied' | 'servicesOff' | 'unavailable' | 'offline' | 'far' };

let cached: AddressTable | null = null;

let cachedKauno: KaunoPoints | null = null;

/** Kauno r. is optional: without it, addresses there just aren't found by location. */
async function loadKaunoPoints(): Promise<KaunoPoints | null> {
  try {
    if (!cachedKauno) {
      const response = await fetch(KAUNO_POINTS_URL);
      if (response.ok) cachedKauno = (await response.json()) as KaunoPoints;
    }
  } catch {
    // offline: handled through the main table
  }
  return cachedKauno;
}

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
  let kaunoPoints: KaunoPoints | null;
  try {
    // Start the downloads while the GPS gets a fix.
    const download = loadAddresses();
    const kaunoDownload = loadKaunoPoints();
    position = await Location.getCurrentPositionAsync({
      accuracy: Location.Accuracy.High,
      // Don't push Google's "Location Accuracy" consent screen; plain GPS is enough here.
      mayShowUserSettingsDialog: false,
    });
    table = await download;
    kaunoPoints = await kaunoDownload;
  } catch (error) {
    return { ok: false, reason: error instanceof TypeError || String(error).includes('HTTP') ? 'offline' : 'unavailable' };
  }

  const { latitude, longitude } = position.coords;
  const address = findNearest(table, latitude, longitude);
  const kauno = kaunoPoints && nearestPoint(kaunoPoints.points, latitude, longitude);
  const distance = Math.min(address?.distance ?? Infinity, kauno?.distance ?? Infinity);
  if (distance > MAX_DISTANCE_M) return { ok: false, reason: 'far' };

  const approximate = permission.android?.accuracy === 'coarse' || permission.ios?.accuracy === 'reduced';
  const accuracy = position.coords.accuracy ?? Infinity;
  const streetConfident = !approximate && accuracy <= MAX_STREET_ACCURACY_M;
  if (kaunoPoints && kauno && kauno.distance === distance) {
    const [, , placeIndex, house] = kaunoPoints.points[kauno.index];
    const [eldership, eldershipName, town, street] = kaunoPoints.places[placeIndex];
    return { ok: true, kauno: { eldership, eldershipName, town, street, house }, streetConfident };
  }
  return { ok: true, address: address!, streetConfident };
}
