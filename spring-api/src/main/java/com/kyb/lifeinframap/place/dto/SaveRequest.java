package com.kyb.lifeinframap.place.dto;

import java.math.BigDecimal;
import java.util.Map;

public record SaveRequest(
        String placeKey,
        String source,
        String name,
        String category,
        String address,
        Long placeId,
        String externalId,
        BigDecimal lat,
        BigDecimal lng,
        String detailUrl,
        String kakaoPlaceUrl,
        String phone,
        String memo,
        Map<String, Object> raw) {
}
