package com.kyb.lifeinframap.auth.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record SignupRequest(
        @NotBlank @Size(max = 150) String username,
        @NotBlank @Size(max = 50) String nickname,
        String email,
        @NotBlank @Size(min = 8) String password,
        @NotBlank @Size(min = 8) String passwordConfirm) {
}
