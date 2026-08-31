package com.kyb.lifeinframap.board.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record ReportRequest(@NotBlank @Size(max = 5000) String reason) {
}
