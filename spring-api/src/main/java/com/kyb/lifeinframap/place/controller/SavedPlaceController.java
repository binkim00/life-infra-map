package com.kyb.lifeinframap.place.controller;

import com.kyb.lifeinframap.place.domain.*;
import com.kyb.lifeinframap.place.repository.*;
import com.kyb.lifeinframap.place.dto.*;

import com.kyb.lifeinframap.account.domain.User;
import com.kyb.lifeinframap.account.repository.UserRepository;
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.bind.annotation.*;

/**
 * 저장 장소 API 입니다.
 *
 * 검색은 Django 가 담당하지만, 사용자가 담아 둔 목록은 사용자 기능이라 Spring 이 가집니다.
 * 저장 시점의 장소 정보를 복사해 두므로 조회할 때 Django 를 부르지 않습니다.
 */
@RestController
@RequestMapping("/api/recommendations/saved-places")
public class SavedPlaceController {

    private final UserSavedPlaceRepository savedPlaceRepository;
    private final UserRepository userRepository;

    public SavedPlaceController(UserSavedPlaceRepository savedPlaceRepository, UserRepository userRepository) {
        this.savedPlaceRepository = savedPlaceRepository;
        this.userRepository = userRepository;
    }



    @GetMapping
    @Transactional(readOnly = true)
    public ResponseEntity<?> list(
            @RequestParam(name = "q", required = false) String keyword,
            @RequestParam(required = false) String source,
            @RequestParam(required = false) Integer limit,
            @RequestParam(defaultValue = "1") int page,
            @RequestParam(name = "page_size", defaultValue = "10") int pageSize,
            Authentication authentication) {
        User user = currentUser(authentication);
        if (user == null) {
            return unauthorized();
        }

        List<UserSavedPlace> all = savedPlaceRepository.findByUserId(user.getId()).stream()
                .filter(saved -> matches(saved, keyword, source))
                .sorted((a, b) -> b.getUpdatedAt().compareTo(a.getUpdatedAt()))
                .toList();

        // limit 만 주면 페이지 정보 없이 배열만 돌려줍니다. Django 와 같은 규칙입니다.
        if (limit != null) {
            int capped = Math.min(Math.max(limit, 1), 100);
            List<Map<String, Object>> results = new ArrayList<>();
            all.stream().limit(capped).forEach(saved -> results.add(serialize(saved)));
            return ResponseEntity.ok(Map.of("results", results));
        }

        int safePage = Math.max(page, 1);
        int safeSize = Math.min(Math.max(pageSize, 1), 100);
        int from = Math.min((safePage - 1) * safeSize, all.size());
        int to = Math.min(from + safeSize, all.size());

        List<Map<String, Object>> results = new ArrayList<>();
        for (UserSavedPlace saved : all.subList(from, to)) {
            results.add(serialize(saved));
        }
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("count", all.size());
        body.put("page", safePage);
        body.put("page_size", safeSize);
        body.put("total_pages", Math.max((int) Math.ceil(all.size() / (double) safeSize), 1));
        body.put("results", results);
        return ResponseEntity.ok(body);
    }

    @PostMapping
    @Transactional
    public ResponseEntity<?> save(@RequestBody SaveRequest request, Authentication authentication) {
        User user = currentUser(authentication);
        if (user == null) {
            return unauthorized();
        }
        String placeKey = request.placeKey();
        if (placeKey == null || placeKey.isBlank()) {
            return ResponseEntity.badRequest().body(Map.of("place_key", List.of("장소 식별자가 필요합니다.")));
        }

        // 같은 장소를 다시 저장하면 내용을 갱신합니다.
        UserSavedPlace saved = savedPlaceRepository.findByUserIdAndPlaceKey(user.getId(), placeKey)
                .orElseGet(() -> UserSavedPlace.create(user, placeKey,
                        request.source() == null ? "" : request.source(),
                        request.name() == null ? "" : request.name()));

        saved.fill(request.placeId(), request.externalId(), request.category(), request.address(),
                request.lat(), request.lng(), request.detailUrl(), request.kakaoPlaceUrl(),
                request.phone(), request.memo(), request.raw());
        savedPlaceRepository.save(saved);

        return ResponseEntity.status(HttpStatus.CREATED).body(serialize(saved));
    }

    @PatchMapping("/{savedPlaceId}")
    @Transactional
    public ResponseEntity<?> updateMemo(@PathVariable Long savedPlaceId, @RequestBody MemoRequest request,
                                        Authentication authentication) {
        User user = currentUser(authentication);
        if (user == null) {
            return unauthorized();
        }
        UserSavedPlace saved = savedPlaceRepository.findByIdAndUserId(savedPlaceId, user.getId()).orElse(null);
        if (saved == null) {
            return notFound();
        }
        saved.changeMemo(request.memo());
        return ResponseEntity.ok(serialize(saved));
    }

    @DeleteMapping("/{savedPlaceId}")
    @Transactional
    public ResponseEntity<?> delete(@PathVariable Long savedPlaceId, Authentication authentication) {
        User user = currentUser(authentication);
        if (user == null) {
            return unauthorized();
        }
        UserSavedPlace saved = savedPlaceRepository.findByIdAndUserId(savedPlaceId, user.getId()).orElse(null);
        if (saved == null) {
            return notFound();
        }
        savedPlaceRepository.delete(saved);
        return ResponseEntity.noContent().build();
    }

    private boolean matches(UserSavedPlace saved, String keyword, String source) {
        if (source != null && !source.isBlank() && !source.equals(saved.getSource())) {
            return false;
        }
        if (keyword == null || keyword.isBlank()) {
            return true;
        }
        String needle = keyword.toLowerCase();
        return contains(saved.getName(), needle) || contains(saved.getCategory(), needle)
                || contains(saved.getAddress(), needle) || contains(saved.getMemo(), needle);
    }

    private boolean contains(String value, String needle) {
        return value != null && value.toLowerCase().contains(needle);
    }

    private Map<String, Object> serialize(UserSavedPlace saved) {
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("id", saved.getId());
        body.put("place", saved.getPlaceId());
        body.put("place_key", saved.getPlaceKey());
        body.put("source", saved.getSource());
        body.put("source_label", sourceLabel(saved.getSource()));
        body.put("external_id", saved.getExternalId());
        body.put("name", saved.getName());
        body.put("category", saved.getCategory());
        body.put("address", saved.getAddress());
        body.put("lat", saved.getLat());
        body.put("lng", saved.getLng());
        body.put("detail_url", saved.getDetailUrl());
        body.put("kakao_place_url", saved.getKakaoPlaceUrl());
        body.put("phone", saved.getPhone());
        body.put("memo", saved.getMemo());
        body.put("raw", saved.getRaw());
        body.put("created_at", saved.getCreatedAt());
        body.put("updated_at", saved.getUpdatedAt());
        return body;
    }

    /** Django `get_source_display` 와 같은 표기입니다. */
    private String sourceLabel(String source) {
        return switch (source == null ? "" : source) {
            case "db" -> "저장 장소";
            case "kakao" -> "카카오 장소";
            case "web" -> "웹 참고";
            default -> source == null ? "" : source;
        };
    }

    private User currentUser(Authentication authentication) {
        if (authentication == null || authentication.getName() == null) {
            return null;
        }
        try {
            return userRepository.findById(Integer.valueOf(authentication.getName())).orElse(null);
        } catch (NumberFormatException exception) {
            return null;
        }
    }

    private ResponseEntity<Map<String, Object>> unauthorized() {
        return ResponseEntity.status(HttpStatus.UNAUTHORIZED).body(Map.of("detail", "로그인이 필요합니다."));
    }

    private ResponseEntity<Map<String, Object>> notFound() {
        return ResponseEntity.status(HttpStatus.NOT_FOUND).body(Map.of("detail", "저장한 장소를 찾을 수 없습니다."));
    }
}
