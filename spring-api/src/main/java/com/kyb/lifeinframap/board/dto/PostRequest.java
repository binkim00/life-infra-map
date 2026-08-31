package com.kyb.lifeinframap.board.dto;

import com.fasterxml.jackson.annotation.JsonAlias;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

public record PostRequest(
        @NotBlank @Size(max = 200) String title,
        @NotBlank @Size(max = 20000) String content,
        @JsonAlias("board_type") @Pattern(regexp = "free|notice") String boardType,
        @Size(max = 100) String image) {
}
