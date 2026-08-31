package com.kyb.lifeinframap.place.dto;

import com.fasterxml.jackson.annotation.JsonAlias;
import jakarta.validation.constraints.DecimalMax;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import java.math.BigDecimal;
import java.util.Map;

public record SaveRequest(
        @JsonAlias("place_key") @NotBlank @Size(max = 255) String placeKey,
        @NotBlank @Pattern(regexp = "local_db|db|kakao|kakao_local|web|web_evidence_candidate|other") String source,
        @NotBlank @Size(max = 200) String name,
        @Size(max = 100) String category,
        @Size(max = 255) String address,
        @JsonAlias("place_id") Long placeId,
        @JsonAlias("external_id") @Size(max = 100) String externalId,
        @DecimalMin("-90") @DecimalMax("90") BigDecimal lat,
        @DecimalMin("-180") @DecimalMax("180") BigDecimal lng,
        @JsonAlias("detail_url") @Size(max = 500) String detailUrl,
        @JsonAlias("kakao_place_url") @Size(max = 500) String kakaoPlaceUrl,
        @Size(max = 50) String phone,
        @Size(max = 10000) String memo,
        Map<String, Object> raw) {
}
