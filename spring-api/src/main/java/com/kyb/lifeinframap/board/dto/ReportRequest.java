package com.kyb.lifeinframap.board.dto;

import jakarta.validation.constraints.NotBlank;

public record ReportRequest(@NotBlank String reason) {
}
