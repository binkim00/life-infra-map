package com.kyb.lifeinframap.board.dto;

import jakarta.validation.constraints.NotBlank;

public record CommentRequest(@NotBlank String content, Long parent) {
}
