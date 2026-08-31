package com.kyb.lifeinframap.auth.dto;

import com.fasterxml.jackson.annotation.JsonAlias;
import jakarta.validation.constraints.Size;

public record ProfileImageRequest(
        @JsonAlias("profile_image") @Size(max = 100) String profileImage) {
}
