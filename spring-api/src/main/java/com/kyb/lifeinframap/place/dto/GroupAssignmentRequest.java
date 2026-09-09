package com.kyb.lifeinframap.place.dto;

import com.fasterxml.jackson.annotation.JsonAlias;

public record GroupAssignmentRequest(@JsonAlias("group_id") Long groupId) {
}
