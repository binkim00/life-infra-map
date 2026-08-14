package com.kyb.lifeinframap.account.service;

import com.kyb.lifeinframap.account.domain.*;
import com.kyb.lifeinframap.account.repository.*;
import com.kyb.lifeinframap.account.service.*;

import com.kyb.lifeinframap.tier.service.ContributionService;
import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

/**
 * 사용자 응답을 한 곳에서 만듭니다.
 *
 * Django `accounts/serializers.py` 의 `UserSerializer` 와 같은 필드여야 합니다.
 * 회원가입/로그인/내정보/닉네임변경이 모두 이 형태를 돌려주므로,
 * 한 곳에서만 만들어야 화면마다 다른 값이 나가는 일이 없습니다.
 */
@Component
public class UserPayloadFactory {

    private final UserProfileRepository profileRepository;
    private final ContributionService contributionService;
    private final String mediaBaseUrl;

    public UserPayloadFactory(
            UserProfileRepository profileRepository,
            ContributionService contributionService,
            @Value("${app.media.base-url:}") String mediaBaseUrl) {
        this.profileRepository = profileRepository;
        this.contributionService = contributionService;
        this.mediaBaseUrl = mediaBaseUrl == null ? "" : mediaBaseUrl.replaceAll("/+$", "");
    }

    public Map<String, Object> of(User user) {
        UserProfile profile = profileRepository.findByUserId(user.getId()).orElse(null);
        return of(user, profile == null ? null : profile.getNickname(),
                profile == null ? null : profile.getProfileImage());
    }

    /** 방금 만든 프로필처럼 아직 조회되지 않는 값이 있을 때 직접 넘겨 씁니다. */
    public Map<String, Object> of(User user, String nickname, String profileImageKey) {
        ContributionService.TierInfo tier = contributionService.getTierInfo(user.getId(), user.isStaff());

        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("id", user.getId());
        payload.put("username", user.getUsername());
        payload.put("nickname", nickname != null ? nickname : user.getUsername());
        payload.put("profile_image_url", fileUrl(profileImageKey));
        payload.put("email", user.getEmail());
        payload.put("is_staff", user.isStaff());
        payload.put("date_joined", user.getDateJoined());
        payload.put("score", tier.score());
        payload.put("contribution", tier.contribution());
        payload.put("tier", tier.tier());
        payload.put("tier_label", tier.tierLabel());
        payload.put("tier_color", tier.tierColor());
        payload.put("nickname_color", tier.nicknameColor());
        return payload;
    }

    /** 저장소 키를 브라우저가 열 수 있는 주소로 바꿉니다. 비어 있으면 빈 문자열입니다. */
    public String fileUrl(String key) {
        if (key == null || key.isBlank()) {
            return "";
        }
        if (key.startsWith("http://") || key.startsWith("https://")) {
            return key;
        }
        return mediaBaseUrl.isEmpty() ? key : mediaBaseUrl + "/" + key.replaceAll("^/+", "");
    }
}
