import * as Location from "expo-location";

/** Bound GPS acquisition so a missing fix cannot leave search waiting forever. */
export async function searchLocation({ cachedOnly = false } = {}) {
  const permission = await Location.requestForegroundPermissionsAsync();
  if (!permission.granted) return null;
  const cached = await Location.getLastKnownPositionAsync({
    maxAge: 300_000,
    requiredAccuracy: 1000,
  });
  if (cached) return cached.coords;
  if (cachedOnly) return null;
  let timer: ReturnType<typeof setTimeout> | undefined;
  try {
    const position = await Promise.race([
      Location.getCurrentPositionAsync({
        accuracy: Location.Accuracy.Balanced,
      }),
      new Promise<never>((_, reject) => {
        timer = setTimeout(
          () =>
            reject(
              new Error(
                "위치를 확인하지 못했습니다. 지역명과 함께 검색해 주세요.",
              ),
            ),
          4000,
        );
      }),
    ]);
    return position.coords;
  } finally {
    if (timer) clearTimeout(timer);
  }
}
