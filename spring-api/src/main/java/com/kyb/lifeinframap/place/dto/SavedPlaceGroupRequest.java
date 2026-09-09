package com.kyb.lifeinframap.place.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record SavedPlaceGroupRequest(
        @NotBlank @Size(max = 100) String name,
        @Size(max = 10000) String memo) {
}
