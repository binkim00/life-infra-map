package com.kyb.lifeinframap.board.dto;

import jakarta.validation.constraints.NotBlank;

public record InquiryRequest(@NotBlank String title, @NotBlank String content) {
}
