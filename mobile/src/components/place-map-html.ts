type MapPlace = {
  id: string;
  name: string;
  lat: number;
  lng: number;
  label: string;
};

const escapeScriptJson = (value: unknown) =>
  JSON.stringify(value).replace(/</g, "\\u003c");

export function buildPlaceMapHtml(places: MapPlace[], selectedId: string | null) {
  const initialState = escapeScriptJson({ places, selectedId });

  return `<!doctype html>
<html lang="ko">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no" />
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <style>
      html, body, #map { width: 100%; height: 100%; margin: 0; }
      body { overflow: hidden; background: #e9ecea; font-family: sans-serif; }
      #status { position: absolute; inset: 0; z-index: 1000; display: flex; align-items: center;
        justify-content: center; padding: 24px; color: #475569; background: #f8faf9;
        font-size: 13px; font-weight: 700; text-align: center; }
      #status.hidden { display: none; }
      .place-marker { display: flex; align-items: center; justify-content: center; width: 34px;
        height: 34px; border: 2px solid #475569; border-radius: 50% 50% 50% 0;
        color: #1e293b; background: #fff; box-shadow: 0 2px 5px rgb(15 23 42 / 24%);
        font: 800 12px/1 Arial, sans-serif; transform: rotate(-45deg); }
      .place-marker span { transform: rotate(45deg); }
      .place-marker.selected { border-color: #0f766e; color: #fff; background: #0f766e; }
    </style>
  </head>
  <body>
    <div id="map"></div>
    <div id="status">지도를 불러오는 중입니다.</div>
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <script>
      const input = ${initialState};
      const statusElement = document.getElementById("status");
      const send = (message) => window.ReactNativeWebView?.postMessage(JSON.stringify(message));
      if (!window.L?.map) {
        statusElement.textContent = "지도를 불러오지 못했습니다.";
      } else {
        const map = L.map("map", { zoomControl: true }).setView([37.5665, 126.978], 13);
        const markerIcon = (label, selected) => L.divIcon({
          className: "",
          html: '<div class="place-marker' + (selected ? ' selected' : '') + '"><span>' + label + '</span></div>',
          iconSize: [36, 42],
          iconAnchor: [18, 38],
        });
        const bounds = [];
        input.places.forEach((place) => {
          const position = [Number(place.lat), Number(place.lng)];
          const selected = String(place.id) === String(input.selectedId);
          L.marker(position, {
            icon: markerIcon(place.label, selected),
            title: place.name,
            zIndexOffset: selected ? 1000 : 0,
          }).on("click", () => send({ type: "life-infra-map:select-place", id: place.id })).addTo(map);
          bounds.push(position);
        });
        if (bounds.length > 1) map.fitBounds(bounds, { padding: [48, 48], maxZoom: 16 });
        else if (bounds.length === 1) map.setView(bounds[0], 15);
        L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
          maxZoom: 19,
          attribution: "&copy; OpenStreetMap contributors",
        }).on("load", () => statusElement.classList.add("hidden"))
          .on("tileerror", () => { statusElement.textContent = "지도 배경을 불러오지 못했습니다."; })
          .addTo(map);
      }
    </script>
  </body>
</html>`;
}
