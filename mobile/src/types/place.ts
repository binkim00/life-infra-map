export type PlaceTag = {
  id?: number;
  name: string;
  is_verified?: boolean;
};

export type SmokingMetadata = {
  facility_type?: string;
  facility_type_label?: string;
  smoking_permission?: string;
  verification_level?: string;
  verification_level_label?: string;
  last_verified_at?: string | null;
  evidence_confidence?: number | null;
  source_summary?: string;
  location_description?: string;
  location_directions?: string;
};

export type Place = {
  id: number | string;
  name: string;
  category: string;
  category_label?: string;
  address?: string;
  detail_location?: string;
  lat: number;
  lng: number;
  distance?: number;
  source_label?: string;
  result_source?: string;
  external_id?: string;
  place_url?: string;
  kakao_place_url?: string;
  phone?: string;
  source_name?: string;
  tags?: PlaceTag[];
  smoking?: SmokingMetadata | null;
};

export type MapSearchResponse = {
  search_mode?: "place_search";
  recommendation_applied?: false;
  query: string;
  count: number;
  needs_location?: boolean;
  message?: string;
  results: Place[];
  candidate_counts?: {
    db?: number;
    kakao?: number;
    db_total?: number;
  };
  kakao_error?: string;
  location_context?: {
    anchor_location?: string;
    anchor_resolved?: boolean;
    center_source?: string;
    center_label?: string;
    lat?: number | null;
    lng?: number | null;
  };
};
