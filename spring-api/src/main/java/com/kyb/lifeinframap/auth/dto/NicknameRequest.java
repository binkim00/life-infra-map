package com.kyb.lifeinframap.auth.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record NicknameRequest(@NotBlank @Size(max = 50) String nickname) {
}
