package com.kyb.lifeinframap.board.dto;

import com.fasterxml.jackson.annotation.JsonAlias;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.PositiveOrZero;
import jakarta.validation.constraints.Size;

public record PenaltyRequest(
        @JsonAlias("penalty_type")
        @NotBlank
        @Pattern(regexp = "warning|suspend|suspend_3_days|suspend_7_days|suspend_30_days|suspend_1_year|permanent_ban")
        String penaltyType,
        @NotBlank @Size(max = 5000) String reason,
        @PositiveOrZero Integer days) {
}
