/** addresses.json from the pipeline: every served address with coordinates. */
export type AddressTable = {
  generatedAt: string;
  source: string;
  /** [location id, street key or "", street label] */
  places: [string, string, string][];
  /** [lat * 1e5, lon * 1e5, place index, house number], sorted by latitude */
  points: [number, number, number, string][];
};

export type NearestAddress = {
  locationId: string;
  /** Street key, or undefined for addresses without a street (small villages). */
  street?: string;
  streetLabel: string;
  number: string;
  /** Straight-line distance from the given position, in metres. */
  distance: number;
};

const METRES_PER_DEGREE = 111_320;

/** Worse than this, the street may be wrong: keep the settlement but ask for the street. */
export const MAX_STREET_ACCURACY_M = 75;
/**
 * Further than this from the nearest address, it may be on another street: a house far from the
 * road, a new house not in the data yet, or a field. Keep the settlement but ask for the street.
 */
export const MAX_STREET_DISTANCE_M = 100;

/**
 * Whether the street of the nearest address can be suggested: 'approximate' if the position
 * isn't precise enough, 'far' if the nearest address is too far away to be the user's.
 */
export function streetConfidence(position: {
  approximate: boolean;
  accuracy: number;
  distance: number;
}): 'ok' | 'approximate' | 'far' {
  if (position.approximate || position.accuracy > MAX_STREET_ACCURACY_M) return 'approximate';
  if (position.distance > MAX_STREET_DISTANCE_M) return 'far';
  return 'ok';
}

/**
 * Finds the closest address to a position. Runs on the phone: the position is never sent
 * anywhere. A linear scan over ~50k points takes a few milliseconds.
 */
export function findNearest(table: AddressTable, lat: number, lon: number): NearestAddress | null {
  const nearest = nearestPoint(table.points, lat, lon);
  if (!nearest) return null;
  const [, , placeIndex, number] = table.points[nearest.index];
  const [locationId, street, streetLabel] = table.places[placeIndex];
  return { locationId, street: street || undefined, streetLabel, number, distance: nearest.distance };
}

/** The closest of `points` ([lat * 1e5, lon * 1e5, ...]) and its distance in metres. */
export function nearestPoint(
  points: readonly (readonly [number, number, ...unknown[]])[],
  lat: number,
  lon: number,
): { index: number; distance: number } | null {
  const cosLat = Math.cos((lat * Math.PI) / 180);
  let best = -1;
  let bestSq = Infinity;
  for (let i = 0; i < points.length; i++) {
    const [pLat, pLon] = points[i];
    const dy = pLat / 1e5 - lat;
    const dx = (pLon / 1e5 - lon) * cosLat;
    const sq = dx * dx + dy * dy;
    if (sq < bestSq) {
      bestSq = sq;
      best = i;
    }
  }
  return best < 0 ? null : { index: best, distance: Math.sqrt(bestSq) * METRES_PER_DEGREE };
}
