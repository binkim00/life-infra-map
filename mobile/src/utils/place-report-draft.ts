import AsyncStorage from "@react-native-async-storage/async-storage";
import { Directory, File, Paths } from "expo-file-system";
import { Platform } from "react-native";

export type ReportDraftImage = {
  uri: string;
  fileName?: string | null;
  mimeType?: string;
  width?: number;
  height?: number;
};

export type PlaceReportDraft = {
  version: 2;
  ownerKey: string;
  requestId: string;
  type: string;
  name: string;
  address: string;
  lat: string;
  lng: string;
  description: string;
  tags: string[];
  images: ReportDraftImage[];
  updatedAt: string;
};

const DRAFT_PREFIX = "place-report-draft:v2";
const DRAFT_IMAGE_DIRECTORY = "place-report-drafts";

export const reportDraftKey = (placeId?: string) =>
  `${DRAFT_PREFIX}:${placeId || "new-place"}`;

export const createReportRequestId = () =>
  "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (character) => {
    const random = Math.floor(Math.random() * 16);
    const value = character === "x" ? random : (random & 0x3) | 0x8;
    return value.toString(16);
  });

export async function loadPlaceReportDraft(key: string) {
  const raw = await AsyncStorage.getItem(key);
  if (!raw) return null;
  try {
    const value = JSON.parse(raw) as Partial<PlaceReportDraft>;
    if (value.version !== 2 || !value.requestId || !value.ownerKey) return null;
    return value as PlaceReportDraft;
  } catch {
    return null;
  }
}

export async function savePlaceReportDraft(key: string, draft: PlaceReportDraft) {
  await AsyncStorage.setItem(key, JSON.stringify(draft));
}

const isManagedDraftImage = (uri: string) =>
  uri.includes(`/${DRAFT_IMAGE_DIRECTORY}/`);

export async function removeDraftImages(images: ReportDraftImage[]) {
  if (Platform.OS === "web") return;
  await Promise.all(
    images.filter((image) => isManagedDraftImage(image.uri)).map(async (image) => {
      try {
        const file = new File(image.uri);
        if (file.exists) file.delete();
      } catch {
        // A missing draft photo must not block clearing a completed receipt.
      }
    }),
  );
}

export async function clearPlaceReportDraft(key: string, images: ReportDraftImage[]) {
  await AsyncStorage.removeItem(key);
  await removeDraftImages(images);
}

export async function persistDraftImages(
  images: ReportDraftImage[],
  requestId: string,
) {
  if (Platform.OS === "web") return images;
  const directory = new Directory(Paths.document, DRAFT_IMAGE_DIRECTORY);
  directory.create({ idempotent: true, intermediates: true });
  // A new picker selection must not reuse the previous selection's paths.
  // The caller removes the old managed files only after every new copy succeeds.
  const selectionId = createReportRequestId().slice(0, 8);
  return Promise.all(
    images.map(async (image, index) => {
      const extension = (
        image.fileName?.match(/\.[a-zA-Z0-9]{1,8}$/)?.[0] ||
        image.uri.match(/\.[a-zA-Z0-9]{1,8}(?=\?|$)/)?.[0] ||
        ".jpg"
      ).toLowerCase();
      const destination = new File(
        directory,
        `${requestId}-${selectionId}-${index}${extension}`,
      );
      await new File(image.uri).copy(destination, { overwrite: true });
      return {
        ...image,
        uri: destination.uri,
        fileName: image.fileName || `report-${index + 1}${extension}`,
      };
    }),
  );
}
