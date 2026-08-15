package com.kyb.lifeinframap;

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
 * 관리자 API 의 권한 경계입니다.
 *
 * 여기서 새는 결함은 조용히 들어가고 피해가 큽니다. 일반 사용자가 관리자 화면 데이터를 읽거나
 * 남에게 제재를 걸 수 있으면 안 됩니다. 각 엔드포인트마다 비로그인·일반사용자·관리자 세 경우를 봅니다.
 */
class AdminApiTest extends ApiTestBase {

    // ---------- 사용자 관리 ----------

    @Test
    @DisplayName("비로그인은 사용자 목록을 볼 수 없다")
    void userListRejectsAnonymous() throws Exception {
        mockMvc.perform(get("/api/admin/users"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    @DisplayName("일반 사용자는 사용자 목록을 볼 수 없다")
    void userListRejectsNonStaff() throws Exception {
        User user = createUser(false);

        mockMvc.perform(get("/api/admin/users").header("Authorization", bearer(user)))
                .andExpect(status().isForbidden());
    }

    @Test
    @DisplayName("관리자는 사용자 목록을 볼 수 있다")
    void userListAllowsStaff() throws Exception {
        User staff = createUser(true);

        mockMvc.perform(get("/api/admin/users").header("Authorization", bearer(staff)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$").isArray());
    }

    @Test
    @DisplayName("일반 사용자는 남의 상세 정보를 볼 수 없다")
    void userDetailRejectsNonStaff() throws Exception {
        User user = createUser(false);
        User target = createUser(false);

        mockMvc.perform(get("/api/admin/users/{id}", target.getId())
                        .header("Authorization", bearer(user)))
                .andExpect(status().isForbidden());
    }

    @Test
    @DisplayName("관리자 사용자 상세는 React 화면이 기대하는 중첩 응답을 반환한다")
    void userDetailReturnsReactShape() throws Exception {
        User staff = createUser(true);
        User target = createUser(false);

        mockMvc.perform(get("/api/admin/users/{id}", target.getId())
                        .header("Authorization", bearer(staff)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.user.id").value(target.getId()))
                .andExpect(jsonPath("$.user.posts_count").isNumber())
                .andExpect(jsonPath("$.user.comments_count").isNumber())
                .andExpect(jsonPath("$.user.received_reports_count").isNumber())
                .andExpect(jsonPath("$.posts").isArray())
                .andExpect(jsonPath("$.comments").isArray())
                .andExpect(jsonPath("$.penalties").isArray());
    }

    // ---------- 제재 ----------

    @Test
    @DisplayName("일반 사용자는 남에게 제재를 걸 수 없다")
    void penaltyRejectsNonStaff() throws Exception {
        User attacker = createUser(false);
        User victim = createUser(false);

        mockMvc.perform(post("/api/admin/users/{id}/penalties", victim.getId())
                        .header("Authorization", bearer(attacker))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"penaltyType":"suspend","reason":"장난","days":7}
                                """))
                .andExpect(status().isForbidden());
    }

    @Test
    @DisplayName("관리자는 제재를 걸 수 있다")
    void penaltyAllowsStaff() throws Exception {
        User staff = createUser(true);
        User target = createUser(false);

        mockMvc.perform(post("/api/admin/users/{id}/penalties", target.getId())
                        .header("Authorization", bearer(staff))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"penaltyType":"suspend","reason":"규정 위반","days":7}
                                """))
                .andExpect(status().isCreated());
    }

    @Test
    @DisplayName("제재를 받은 사용자는 글을 쓸 수 없다")
    void penalizedUserCannotWrite() throws Exception {
        User staff = createUser(true);
        User target = createUser(false);

        mockMvc.perform(post("/api/admin/users/{id}/penalties", target.getId())
                        .header("Authorization", bearer(staff))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"penaltyType":"suspend","reason":"규정 위반","days":7}
                                """))
                .andExpect(status().isCreated());

        mockMvc.perform(post("/api/boards/posts")
                        .header("Authorization", bearer(target))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"title":"제재 중 글쓰기","content":"본문"}
                                """))
                .andExpect(status().isForbidden());
    }

    // ---------- 관리자 알림 발송 ----------

    @Test
    @DisplayName("일반 사용자는 관리자 알림을 보낼 수 없다")
    void adminNotificationRejectsNonStaff() throws Exception {
        User user = createUser(false);
        User target = createUser(false);

        mockMvc.perform(post("/api/admin/users/{id}/notifications", target.getId())
                        .header("Authorization", bearer(user))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"title":"사칭","message":"관리자입니다"}
                                """))
                .andExpect(status().isForbidden());
    }

    // ---------- 문의 관리 ----------

    @Test
    @DisplayName("일반 사용자는 전체 문의 목록을 볼 수 없다")
    void adminInquiryListRejectsNonStaff() throws Exception {
        User user = createUser(false);

        mockMvc.perform(get("/api/admin/inquiries").header("Authorization", bearer(user)))
                .andExpect(status().isForbidden());
    }

    @Test
    @DisplayName("관리자는 전체 문의 목록을 볼 수 있다")
    void adminInquiryListAllowsStaff() throws Exception {
        User staff = createUser(true);

        mockMvc.perform(get("/api/admin/inquiries").header("Authorization", bearer(staff)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$").isArray());
    }

    // ---------- 목록 응답 형태 ----------
    //
    // Django 는 이 목록들을 배열로 주고 프론트도 배열을 전제로 씁니다.
    //   AdminInquiryView          response.data.map(...)
    //   ReportListView            reportList.map(...)
    //   MyInquiryView             목록 렌더링 + 길이 확인
    // Spring 이관 과정에서 페이지네이션 객체로 감싸 세 화면이 깨진 적이 있습니다.
    // 형태를 바꾸면 프론트가 함께 바뀌어야 하므로 계약으로 고정합니다.

    @Test
    @DisplayName("관리자 문의 목록은 페이지네이션으로 감싸지 않는다")
    void adminInquiryListIsNotWrapped() throws Exception {
        User staff = createUser(true);

        mockMvc.perform(get("/api/admin/inquiries").header("Authorization", bearer(staff)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$").isArray())
                .andExpect(jsonPath("$.results").doesNotExist())
                .andExpect(jsonPath("$.count").doesNotExist());
    }

    @Test
    @DisplayName("내 문의 목록도 배열이다")
    void myInquiryListIsArray() throws Exception {
        User author = createUser(false);
        createInquiry(author);

        mockMvc.perform(get("/api/inquiries/my").header("Authorization", bearer(author)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$").isArray())
                .andExpect(jsonPath("$[0].title").value("문의 제목"))
                .andExpect(jsonPath("$.results").doesNotExist());
    }

    @Test
    @DisplayName("신고 목록도 배열이다")
    void reportListIsArray() throws Exception {
        User staff = createUser(true);

        mockMvc.perform(get("/api/boards/reports").header("Authorization", bearer(staff)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$").isArray())
                .andExpect(jsonPath("$.results").doesNotExist());
    }

    @Test
    @DisplayName("일반 사용자는 문의에 답변할 수 없다")
    void adminInquiryReplyRejectsNonStaff() throws Exception {
        User author = createUser(false);
        long inquiryId = createInquiry(author);
        User stranger = createUser(false);

        mockMvc.perform(patch("/api/admin/inquiries/{id}", inquiryId)
                        .header("Authorization", bearer(stranger))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"status":"answered","adminReply":"가짜 답변"}
                                """))
                .andExpect(status().isForbidden());
    }

    @Test
    @DisplayName("관리자는 문의에 답변할 수 있다")
    void adminInquiryReplyAllowsStaff() throws Exception {
        User author = createUser(false);
        long inquiryId = createInquiry(author);
        User staff = createUser(true);

        mockMvc.perform(patch("/api/admin/inquiries/{id}", inquiryId)
                        .header("Authorization", bearer(staff))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"status":"answered","adminReply":"확인했습니다"}
                                """))
                .andExpect(status().isOk());
    }

    // ---------- 등급 조회 ----------
    //
    // 이관 중에는 Django 계산 결과와 대조하기 위해 `/api/tiers/**` 를 permitAll 로 열어 두었습니다.
    // 이관이 끝나 닫았습니다. 다시 열리면 남의 기여도가 인증 없이 노출됩니다.

    @Test
    @DisplayName("등급 조회는 로그인이 필요하다")
    void tierRequiresAuthentication() throws Exception {
        User target = createUser(false);

        mockMvc.perform(get("/api/tiers/{id}", target.getId()))
                .andExpect(status().isUnauthorized());
    }

    @Test
    @DisplayName("로그인하면 등급을 조회할 수 있다")
    void tierAllowsAuthenticated() throws Exception {
        User user = createUser(false);

        mockMvc.perform(get("/api/tiers/{id}", user.getId())
                        .header("Authorization", bearer(user)))
                .andExpect(status().isOk());
    }

    private long createInquiry(User author) throws Exception {
        MvcResult result = mockMvc.perform(post("/api/inquiries")
                        .header("Authorization", bearer(author))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"title":"문의 제목","content":"문의 내용"}
                                """))
                .andExpect(status().isCreated())
                .andReturn();
        return objectMapper.readTree(result.getResponse().getContentAsString()).get("id").asLong();
    }
}
