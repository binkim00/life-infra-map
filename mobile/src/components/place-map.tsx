import MapView, { Marker } from "react-native-maps";
import { StyleSheet } from "react-native";
import type { Place } from "@/types/place";

export function PlaceMap({
  place,
  places = [],
  onSelectPlace,
}: {
  place?: Place | null;
  places?: Place[];
  onSelectPlace?: (place: Place) => void;
}) {
  const lat = place?.lat ?? 37.5665;
  const lng = place?.lng ?? 126.978;
  const markers = places.length ? places : place ? [place] : [];
  return (
    <MapView
      key={`${lat}-${lng}`}
      style={styles.map}
      initialRegion={{
        latitude: lat,
        longitude: lng,
        latitudeDelta: 0.02,
        longitudeDelta: 0.02,
      }}
    >
      {markers.map((item) => (
        <Marker
          key={String(item.id)}
          coordinate={{
            latitude: Number(item.lat),
            longitude: Number(item.lng),
          }}
          title={item.name}
          pinColor={
            String(item.id) === String(place?.id) ? "#0F766E" : "#64748B"
          }
          onPress={() => onSelectPlace?.(item)}
        />
      ))}
    </MapView>
  );
}
const styles = StyleSheet.create({ map: { width: "100%", height: 300 } });
