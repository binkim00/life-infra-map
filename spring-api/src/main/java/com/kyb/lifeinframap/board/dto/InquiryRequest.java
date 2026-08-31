package com.kyb.lifeinframap.board.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record InquiryRequest(
        @NotBlank @Size(max = 200) String title,
        @NotBlank @Size(max = 20000) String content) {
}
