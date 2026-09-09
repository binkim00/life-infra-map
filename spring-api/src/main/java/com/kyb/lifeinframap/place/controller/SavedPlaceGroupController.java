package com.kyb.lifeinframap.place.controller;

import com.kyb.lifeinframap.account.domain.User;
import com.kyb.lifeinframap.account.repository.UserRepository;
import com.kyb.lifeinframap.place.domain.UserSavedPlaceGroup;
import com.kyb.lifeinframap.place.dto.SavedPlaceGroupRequest;
import com.kyb.lifeinframap.place.repository.UserSavedPlaceGroupRepository;
import com.kyb.lifeinframap.place.repository.UserSavedPlaceRepository;
import jakarta.validation.Valid;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/recommendations/saved-place-groups")
public class SavedPlaceGroupController {
    private final UserSavedPlaceGroupRepository groupRepository;
    private final UserSavedPlaceRepository savedPlaceRepository;
    private final UserRepository userRepository;

    public SavedPlaceGroupController(UserSavedPlaceGroupRepository groupRepository,
                                     UserSavedPlaceRepository savedPlaceRepository,
                                     UserRepository userRepository) {
        this.groupRepository = groupRepository;
        this.savedPlaceRepository = savedPlaceRepository;
        this.userRepository = userRepository;
    }

    @GetMapping
    @Transactional(readOnly = true)
    public ResponseEntity<?> list(Authentication authentication) {
        User user = currentUser(authentication);
        if (user == null) return unauthorized();
        List<Map<String, Object>> results = new ArrayList<>();
        groupRepository.findByUserIdOrderByUpdatedAtDescIdDesc(user.getId())
                .forEach(group -> results.add(serialize(group)));
        return ResponseEntity.ok(Map.of("results", results));
    }

    @PostMapping
    @Transactional
    public ResponseEntity<?> create(@Valid @RequestBody SavedPlaceGroupRequest request,
                                    Authentication authentication) {
        User user = currentUser(authentication);
        if (user == null) return unauthorized();
        String name = request.name().trim();
        if (groupRepository.findByUserIdAndNameIgnoreCase(user.getId(), name).isPresent()) {
            return duplicateName();
        }
        UserSavedPlaceGroup group = UserSavedPlaceGroup.create(user, name, cleanMemo(request.memo()));
        groupRepository.save(group);
        return ResponseEntity.status(HttpStatus.CREATED).body(serialize(group));
    }

    @PatchMapping("/{groupId}")
    @Transactional
    public ResponseEntity<?> update(@PathVariable Long groupId,
                                    @Valid @RequestBody SavedPlaceGroupRequest request,
                                    Authentication authentication) {
        User user = currentUser(authentication);
        if (user == null) return unauthorized();
        UserSavedPlaceGroup group = groupRepository.findByIdAndUserId(groupId, user.getId()).orElse(null);
        if (group == null) return notFound();
        String name = request.name().trim();
        UserSavedPlaceGroup sameName = groupRepository
                .findByUserIdAndNameIgnoreCase(user.getId(), name).orElse(null);
        if (sameName != null && !sameName.getId().equals(groupId)) return duplicateName();
        group.update(name, cleanMemo(request.memo()));
        return ResponseEntity.ok(serialize(group));
    }

    @DeleteMapping("/{groupId}")
    @Transactional
    public ResponseEntity<?> delete(@PathVariable Long groupId, Authentication authentication) {
        User user = currentUser(authentication);
        if (user == null) return unauthorized();
        UserSavedPlaceGroup group = groupRepository.findByIdAndUserId(groupId, user.getId()).orElse(null);
        if (group == null) return notFound();
        savedPlaceRepository.clearGroup(groupId, user.getId());
        groupRepository.delete(group);
        return ResponseEntity.noContent().build();
    }

    private Map<String, Object> serialize(UserSavedPlaceGroup group) {
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("id", group.getId());
        body.put("name", group.getName());
        body.put("memo", group.getMemo());
        body.put("created_at", group.getCreatedAt());
        body.put("updated_at", group.getUpdatedAt());
        return body;
    }

    private String cleanMemo(String memo) {
        return memo == null ? "" : memo.trim();
    }

    private User currentUser(Authentication authentication) {
        if (authentication == null || authentication.getName() == null) return null;
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
        return ResponseEntity.status(HttpStatus.NOT_FOUND).body(Map.of("detail", "저장 그룹을 찾을 수 없습니다."));
    }

    private ResponseEntity<Map<String, List<String>>> duplicateName() {
        return ResponseEntity.badRequest().body(Map.of("name", List.of("같은 이름의 저장 그룹이 이미 있습니다.")));
    }
}
