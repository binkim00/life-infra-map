package com.kyb.lifeinframap.auth.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record PasswordChangeRequest(
        @NotBlank String currentPassword,
        @NotBlank @Size(min = 8) String newPassword,
        @NotBlank @Size(min = 8) String newPasswordConfirm) {
}
