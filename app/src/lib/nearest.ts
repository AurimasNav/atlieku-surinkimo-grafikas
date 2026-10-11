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

/**
 * Finds the closest address to a position. Runs on the phone: the position is never sent
 * anywhere. A linear scan over ~50k points takes a few milliseconds.
 */
export function findNearest(table: AddressTable, lat: number, lon: number): NearestAddress | null {
  const cosLat = Math.cos((lat * Math.PI) / 180);
  let best = -1;
  let bestSq = Infinity;
  for (let i = 0; i < table.points.length; i++) {
    const [pLat, pLon] = table.points[i];
    const dy = pLat / 1e5 - lat;
    const dx = (pLon / 1e5 - lon) * cosLat;
    const sq = dx * dx + dy * dy;
    if (sq < bestSq) {
      bestSq = sq;
      best = i;
    }
  }
  if (best < 0) return null;
  const [, , placeIndex, number] = table.points[best];
  const [locationId, street, streetLabel] = table.places[placeIndex];
  return {
    locationId,
    street: street || undefined,
    streetLabel,
    number,
    distance: Math.sqrt(bestSq) * METRES_PER_DEGREE,
  };
}
