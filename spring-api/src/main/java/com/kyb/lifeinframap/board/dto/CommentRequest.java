package com.kyb.lifeinframap.board.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record CommentRequest(@NotBlank @Size(max = 10000) String content, Long parent) {
}
