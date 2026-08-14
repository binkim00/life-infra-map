package com.kyb.lifeinframap;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.patch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.kyb.lifeinframap.account.domain.User;
import com.kyb.lifeinframap.support.ApiTestBase;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MvcResult;

/**
 * 사용자별 데이터(알림·문의·저장 장소)의 격리를 확인합니다.
 *
 * 이 API 들은 모두 "내 것만 보이고 내 것만 고칠 수 있다"가 핵심 규칙입니다.
 * 남의 데이터가 새는 결함은 화면상 정상으로 보여서 눈으로는 발견되지 않습니다.
 */
class UserDataApiTest extends ApiTestBase {

    // ---------- 알림 ----------

    private long sendNotification(User staff, User recipient) throws Exception {
        MvcResult result = mockMvc.perform(post("/api/admin/users/{id}/notifications", recipient.getId())
                        .header("Authorization", bearer(staff))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"title":"공지","message":"내용입니다"}
                                """))
                .andExpect(status().isCreated())
                .andReturn();
        return objectMapper.readTree(result.getResponse().getContentAsString()).get("id").asLong();
    }

    @Test
    @DisplayName("알림 목록은 로그인이 필요하다")
    void notificationListRequiresAuth() throws Exception {
        mockMvc.perform(get("/api/notifications"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    @DisplayName("알림 목록은 배열이다")
    void notificationListIsArray() throws Exception {
        User user = createUser();

        mockMvc.perform(get("/api/notifications").header("Authorization", bearer(user)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$").isArray());
    }

    @Test
    @DisplayName("내 알림만 보인다")
    void notificationListIsScopedToMe() throws Exception {
        User staff = createUser(true);
        User mine = createUser();
        User other = createUser();
        sendNotification(staff, other);

        // 남에게 보낸 알림이 내 목록에 들어오면 안 됩니다.
        mockMvc.perform(get("/api/notifications").header("Authorization", bearer(mine)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.length()").value(0));
    }

    @Test
    @DisplayName("받은 사람에게는 알림이 보인다")
    void recipientSeesNotification() throws Exception {
        User staff = createUser(true);
        User recipient = createUser();
        sendNotification(staff, recipient);

        mockMvc.perform(get("/api/notifications").header("Authorization", bearer(recipient)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.length()").value(1))
                .andExpect(jsonPath("$[0].is_read").value(false));
    }

    @Test
    @DisplayName("남의 알림은 읽음 처리할 수 없다")
    void cannotReadOthersNotification() throws Exception {
        User staff = createUser(true);
        User recipient = createUser();
        User stranger = createUser();
        long notificationId = sendNotification(staff, recipient);

        // 남의 알림인지 없는 알림인지 구분해 알려주지 않으므로 404 입니다.
        mockMvc.perform(patch("/api/notifications/{id}/read", notificationId)
                        .header("Authorization", bearer(stranger)))
                .andExpect(status().isNotFound());
    }

    @Test
    @DisplayName("내 알림은 읽음 처리된다")
    void marksMyNotificationRead() throws Exception {
        User staff = createUser(true);
        User recipient = createUser();
        long notificationId = sendNotification(staff, recipient);

        mockMvc.perform(patch("/api/notifications/{id}/read", notificationId)
                        .header("Authorization", bearer(recipient)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.is_read").value(true));
    }

    @Test
    @DisplayName("전체 읽음 처리는 내 알림만 바꾼다")
    void readAllOnlyAffectsMe() throws Exception {
        User staff = createUser(true);
        User mine = createUser();
        User other = createUser();
        sendNotification(staff, mine);
        long othersNotification = sendNotification(staff, other);

        mockMvc.perform(patch("/api/notifications/read-all")
                        .header("Authorization", bearer(mine)))
                .andExpect(status().isOk());

        // 남의 알림은 그대로 읽지 않은 상태여야 합니다.
        mockMvc.perform(patch("/api/notifications/{id}/read", othersNotification)
                        .header("Authorization", bearer(other)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.is_read").value(true));
    }

    // ---------- 문의 상세 접근 범위 ----------

    private long createInquiry(User author) throws Exception {
        MvcResult result = mockMvc.perform(post("/api/inquiries")
                        .header("Authorization", bearer(author))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"title":"내 문의","content":"내용"}
                                """))
                .andExpect(status().isCreated())
                .andReturn();
        return objectMapper.readTree(result.getResponse().getContentAsString()).get("id").asLong();
    }

    @Test
    @DisplayName("작성자는 자기 문의를 볼 수 있다")
    void authorSeesOwnInquiry() throws Exception {
        User author = createUser();
        long inquiryId = createInquiry(author);

        mockMvc.perform(get("/api/inquiries/{id}", inquiryId)
                        .header("Authorization", bearer(author)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.title").value("내 문의"));
    }

    @Test
    @DisplayName("남의 문의는 볼 수 없다")
    void strangerCannotSeeInquiry() throws Exception {
        User author = createUser();
        User stranger = createUser();
        long inquiryId = createInquiry(author);

        // Django `inquiry_detail` 과 같은 403 과 메시지입니다.
        // 알림은 404 인데 문의는 403 인 것이 Django 의 의도된 차이입니다.
        mockMvc.perform(get("/api/inquiries/{id}", inquiryId)
                        .header("Authorization", bearer(stranger)))
                .andExpect(status().isForbidden())
                .andExpect(jsonPath("$.detail").value("본인이 작성한 문의만 확인할 수 있습니다."));
    }

    @Test
    @DisplayName("관리자는 남의 문의도 볼 수 있다")
    void staffSeesAnyInquiry() throws Exception {
        User author = createUser();
        User staff = createUser(true);
        long inquiryId = createInquiry(author);

        mockMvc.perform(get("/api/inquiries/{id}", inquiryId)
                        .header("Authorization", bearer(staff)))
                .andExpect(status().isOk());
    }

    @Test
    @DisplayName("내 문의 목록에는 남의 문의가 섞이지 않는다")
    void myInquiryListIsScoped() throws Exception {
        User mine = createUser();
        User other = createUser();
        createInquiry(other);

        mockMvc.perform(get("/api/inquiries/my").header("Authorization", bearer(mine)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.length()").value(0));
    }

    // ---------- 저장 장소 ----------

    private long savePlace(User user, String name) throws Exception {
        MvcResult result = mockMvc.perform(post("/api/recommendations/saved-places")
                        .header("Authorization", bearer(user))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"placeKey":"kakao:%d","source":"kakao_local","name":"%s",
                                 "category":"cafe","address":"부산 부산진구","lat":35.1578,"lng":129.0594}
                                """.formatted(System.nanoTime(), name)))
                .andExpect(status().isCreated())
                .andReturn();
        return objectMapper.readTree(result.getResponse().getContentAsString()).get("id").asLong();
    }

    @Test
    @DisplayName("저장 장소 목록은 로그인이 필요하다")
    void savedPlaceListRequiresAuth() throws Exception {
        mockMvc.perform(get("/api/recommendations/saved-places"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    @DisplayName("장소를 저장하면 내 목록에 들어온다")
    void savesPlace() throws Exception {
        User user = createUser();
        savePlace(user, "테스트 카페");

        mockMvc.perform(get("/api/recommendations/saved-places")
                        .header("Authorization", bearer(user)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.count").value(1))
                .andExpect(jsonPath("$.results[0].name").value("테스트 카페"));
    }

    @Test
    @DisplayName("남이 저장한 장소는 내 목록에 없다")
    void savedPlaceListIsScoped() throws Exception {
        User mine = createUser();
        User other = createUser();
        savePlace(other, "남의 카페");

        mockMvc.perform(get("/api/recommendations/saved-places")
                        .header("Authorization", bearer(mine)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.count").value(0));
    }

    @Test
    @DisplayName("남이 저장한 장소는 메모를 고칠 수 없다")
    void cannotEditOthersSavedPlace() throws Exception {
        User owner = createUser();
        User stranger = createUser();
        long savedId = savePlace(owner, "남의 카페");

        mockMvc.perform(patch("/api/recommendations/saved-places/{id}", savedId)
                        .header("Authorization", bearer(stranger))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"memo":"가로채기"}
                                """))
                .andExpect(status().isNotFound());
    }

    @Test
    @DisplayName("남이 저장한 장소는 삭제할 수 없다")
    void cannotDeleteOthersSavedPlace() throws Exception {
        User owner = createUser();
        User stranger = createUser();
        long savedId = savePlace(owner, "남의 카페");

        mockMvc.perform(delete("/api/recommendations/saved-places/{id}", savedId)
                        .header("Authorization", bearer(stranger)))
                .andExpect(status().isNotFound());

        // 소유자에게는 그대로 남아 있어야 합니다.
        mockMvc.perform(get("/api/recommendations/saved-places")
                        .header("Authorization", bearer(owner)))
                .andExpect(jsonPath("$.count").value(1));
    }

    @Test
    @DisplayName("본인은 메모를 고치고 삭제할 수 있다")
    void ownerCanEditAndDelete() throws Exception {
        User owner = createUser();
        long savedId = savePlace(owner, "내 카페");

        mockMvc.perform(patch("/api/recommendations/saved-places/{id}", savedId)
                        .header("Authorization", bearer(owner))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"memo":"조용해서 좋음"}
                                """))
                .andExpect(status().isOk());

        mockMvc.perform(delete("/api/recommendations/saved-places/{id}", savedId)
                        .header("Authorization", bearer(owner)))
                .andExpect(status().isNoContent());

        mockMvc.perform(get("/api/recommendations/saved-places")
                        .header("Authorization", bearer(owner)))
                .andExpect(jsonPath("$.count").value(0));
    }

    @Test
    @DisplayName("limit 을 주면 페이지 정보 없이 배열만 온다")
    void savedPlaceLimitReturnsResultsOnly() throws Exception {
        User user = createUser();
        savePlace(user, "카페 하나");

        // Django `saved_places` 와 같은 규칙입니다. limit 만 주면 count/page 를 붙이지 않습니다.
        mockMvc.perform(get("/api/recommendations/saved-places")
                        .param("limit", "5")
                        .header("Authorization", bearer(user)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.results").isArray())
                .andExpect(jsonPath("$.count").doesNotExist());
    }
}
