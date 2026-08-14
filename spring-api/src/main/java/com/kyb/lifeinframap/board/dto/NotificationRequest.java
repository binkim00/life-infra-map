package com.kyb.lifeinframap.board.dto;

import jakarta.validation.constraints.NotBlank;

public record NotificationRequest(@NotBlank String title, @NotBlank String message) {
}
