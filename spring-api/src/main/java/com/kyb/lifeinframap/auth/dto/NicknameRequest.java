package com.kyb.lifeinframap.auth.dto;

import jakarta.validation.constraints.NotBlank;

public record NicknameRequest(@NotBlank String nickname) {
}
