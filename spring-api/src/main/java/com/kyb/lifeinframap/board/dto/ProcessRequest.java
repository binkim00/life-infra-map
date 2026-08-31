package com.kyb.lifeinframap.board.dto;

import com.fasterxml.jackson.annotation.JsonAlias;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

public record ProcessRequest(
        @JsonAlias("action") @Pattern(regexp = "passed|penalized|resolved") String status,
        @JsonAlias("admin_memo") @Size(max = 5000) String adminMemo,
        @JsonAlias("penalty_type")
        @Pattern(regexp = "warning|suspend|suspend_3_days|suspend_7_days|suspend_30_days|suspend_1_year|permanent_ban")
        String penaltyType,
        @JsonAlias("penalty_reason") @Size(max = 5000) String penaltyReason) {
}
