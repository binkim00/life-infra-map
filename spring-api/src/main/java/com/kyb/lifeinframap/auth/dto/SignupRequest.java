package com.kyb.lifeinframap.auth.dto;

import com.fasterxml.jackson.annotation.JsonAlias;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Size;

public record SignupRequest(
        @NotBlank @Size(max = 150) String username,
        @NotBlank @Size(max = 50) String nickname,
        @Email @Size(max = 254) String email,
        @NotBlank @Size(min = 8) String password,
        @JsonAlias("password_confirm") @NotBlank @Size(min = 8) String passwordConfirm) {
}
