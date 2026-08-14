package com.kyb.lifeinframap.tier.controller;

import com.kyb.lifeinframap.tier.domain.*;
import com.kyb.lifeinframap.tier.service.*;

import com.kyb.lifeinframap.account.domain.User;
import com.kyb.lifeinframap.account.repository.UserRepository;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/**
 * 등급 조회 엔드포인트입니다.
 *
 * 이관 중에는 Django 계산 결과와 대조할 수 있어야 하므로 단건 조회를 열어 둡니다.
 * 게시글 목록처럼 작성자가 여러 명인 화면은 목록 조회로 한 번에 가져갑니다.
 */
@RestController
@RequestMapping("/api/tiers")
public class TierController {

    private final ContributionService contributionService;
    private final UserRepository userRepository;

    public TierController(ContributionService contributionService, UserRepository userRepository) {
        this.contributionService = contributionService;
        this.userRepository = userRepository;
    }

    @GetMapping("/{userId}")
    public ResponseEntity<?> tierOf(@PathVariable Integer userId) {
        return userRepository.findById(userId)
                .<ResponseEntity<?>>map(user -> ResponseEntity.ok(
                        contributionService.getTierInfo(user.getId(), user.isStaff())))
                .orElseGet(() -> ResponseEntity.status(HttpStatus.NOT_FOUND)
                        .body(Map.of("detail", "사용자를 찾을 수 없습니다.")));
    }

    @GetMapping
    public Map<Integer, ContributionService.TierInfo> tiersOf(@RequestParam List<Integer> userIds) {
        Set<Integer> staffIds = userRepository.findAllById(userIds).stream()
                .filter(User::isStaff)
                .map(User::getId)
                .collect(Collectors.toSet());
        return contributionService.getTierInfo(userIds, staffIds);
    }
}
