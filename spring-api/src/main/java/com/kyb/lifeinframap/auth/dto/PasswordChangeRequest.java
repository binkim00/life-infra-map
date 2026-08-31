package com.kyb.lifeinframap.auth.dto;

import com.fasterxml.jackson.annotation.JsonAlias;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record PasswordChangeRequest(
        @JsonAlias("current_password") @NotBlank String currentPassword,
        @JsonAlias("new_password") @NotBlank @Size(min = 8) String newPassword,
        @JsonAlias("new_password_confirm") @NotBlank @Size(min = 8) String newPasswordConfirm) {
}
