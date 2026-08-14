package com.kyb.lifeinframap.board.dto;

import jakarta.validation.constraints.NotBlank;

public record PostRequest(
        @NotBlank String title,
        @NotBlank String content,
        String boardType,
        String image) {
}
