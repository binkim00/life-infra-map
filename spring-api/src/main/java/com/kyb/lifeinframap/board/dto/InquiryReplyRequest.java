package com.kyb.lifeinframap.board.dto;

import com.fasterxml.jackson.annotation.JsonAlias;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

public record InquiryReplyRequest(
        @Pattern(regexp = "pending|answered|closed") String status,
        @JsonAlias("admin_reply") @Size(max = 20000) String adminReply) {
}
