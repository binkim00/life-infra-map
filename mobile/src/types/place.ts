export type PlaceTag = {
  id?: number;
  name: string;
  is_verified?: boolean;
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
};
