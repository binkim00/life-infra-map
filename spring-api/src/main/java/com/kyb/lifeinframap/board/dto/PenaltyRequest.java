package com.kyb.lifeinframap.board.dto;

import jakarta.validation.constraints.NotBlank;

public record PenaltyRequest(@NotBlank String penaltyType, @NotBlank String reason, Integer days) {
}
