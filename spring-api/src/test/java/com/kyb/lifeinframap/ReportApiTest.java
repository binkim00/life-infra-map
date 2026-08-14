package com.kyb.lifeinframap;

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
 * 신고 API의 Spring 이관 결과를 확인합니다.
 *
 * 신고는 규칙이 여러 개 겹칩니다(본인 글 제외, 중복 제외, 처리 권한).
 * Django 쪽 테스트가 `@skip` 으로 넘어가 있어 여기가 유일한 안전망입니다.
 */
class ReportApiTest extends ApiTestBase {

    private long createPost(User author) throws Exception {
        MvcResult result = mockMvc.perform(post("/api/boards/posts")
                        .header("Authorization", bearer(author))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"title":"신고 대상 글","content":"본문"}
                                """))
                .andExpect(status().isCreated())
                .andReturn();
        return objectMapper.readTree(result.getResponse().getContentAsString()).get("id").asLong();
    }

    private long createComment(User author, long postId) throws Exception {
        MvcResult result = mockMvc.perform(post("/api/boards/posts/{id}/comments", postId)
                        .header("Authorization", bearer(author))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"content":"신고 대상 댓글"}
                                """))
                .andExpect(status().isCreated())
                .andReturn();
        return objectMapper.readTree(result.getResponse().getContentAsString()).get("id").asLong();
    }

    private long reportPost(User reporter, long postId) throws Exception {
        MvcResult result = mockMvc.perform(post("/api/boards/posts/{id}/report", postId)
                        .header("Authorization", bearer(reporter))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"reason":"부적절한 내용입니다"}
                                """))
                .andExpect(status().isCreated())
                .andReturn();
        return objectMapper.readTree(result.getResponse().getContentAsString()).get("id").asLong();
    }

    // ---------- 게시글 신고 ----------

    @Test
    @DisplayName("남의 글은 신고할 수 있다")
    void reportsOthersPost() throws Exception {
        User author = createUser();
        User reporter = createUser();
        long postId = createPost(author);

        mockMvc.perform(post("/api/boards/posts/{id}/report", postId)
                        .header("Authorization", bearer(reporter))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"reason":"부적절한 내용입니다"}
                                """))
                .andExpect(status().isCreated());
    }

    @Test
    @DisplayName("본인 글은 신고할 수 없다")
    void rejectsSelfReport() throws Exception {
        User author = createUser();
        long postId = createPost(author);

        mockMvc.perform(post("/api/boards/posts/{id}/report", postId)
                        .header("Authorization", bearer(author))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"reason":"자기 신고"}
                                """))
                .andExpect(status().isBadRequest());
    }

    @Test
    @DisplayName("같은 글을 두 번 신고할 수 없다")
    void rejectsDuplicateReport() throws Exception {
        User author = createUser();
        User reporter = createUser();
        long postId = createPost(author);
        reportPost(reporter, postId);

        mockMvc.perform(post("/api/boards/posts/{id}/report", postId)
                        .header("Authorization", bearer(reporter))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"reason":"또 신고"}
                                """))
                .andExpect(status().isBadRequest());
    }

    @Test
    @DisplayName("없는 글은 신고할 수 없다")
    void rejectsReportOnMissingPost() throws Exception {
        User reporter = createUser();

        mockMvc.perform(post("/api/boards/posts/{id}/report", 99_999_999L)
                        .header("Authorization", bearer(reporter))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"reason":"없는 글"}
                                """))
                .andExpect(status().isNotFound());
    }

    @Test
    @DisplayName("비로그인은 신고할 수 없다")
    void rejectsAnonymousReport() throws Exception {
        User author = createUser();
        long postId = createPost(author);

        mockMvc.perform(post("/api/boards/posts/{id}/report", postId)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"reason":"익명 신고"}
                                """))
                .andExpect(status().isUnauthorized());
    }

    // ---------- 댓글 신고 ----------

    @Test
    @DisplayName("본인 댓글은 신고할 수 없다")
    void rejectsSelfCommentReport() throws Exception {
        User author = createUser();
        long postId = createPost(author);
        long commentId = createComment(author, postId);

        mockMvc.perform(post("/api/boards/comments/{id}/report", commentId)
                        .header("Authorization", bearer(author))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"reason":"자기 댓글 신고"}
                                """))
                .andExpect(status().isBadRequest());
    }

    @Test
    @DisplayName("같은 댓글을 두 번 신고할 수 없다")
    void rejectsDuplicateCommentReport() throws Exception {
        User author = createUser();
        User reporter = createUser();
        long postId = createPost(author);
        long commentId = createComment(author, postId);

        mockMvc.perform(post("/api/boards/comments/{id}/report", commentId)
                        .header("Authorization", bearer(reporter))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"reason":"부적절"}
                                """))
                .andExpect(status().isCreated());

        mockMvc.perform(post("/api/boards/comments/{id}/report", commentId)
                        .header("Authorization", bearer(reporter))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"reason":"또 신고"}
                                """))
                .andExpect(status().isBadRequest());
    }

    // ---------- 신고 처리 권한 ----------

    @Test
    @DisplayName("일반 사용자는 신고를 처리할 수 없다")
    void rejectsProcessByNonStaff() throws Exception {
        User author = createUser();
        User reporter = createUser();
        long postId = createPost(author);
        long reportId = reportPost(reporter, postId);

        mockMvc.perform(post("/api/boards/reports/{id}/process", reportId)
                        .header("Authorization", bearer(reporter))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"status":"resolved","adminMemo":"셀프 처리"}
                                """))
                .andExpect(status().isForbidden());
    }

    @Test
    @DisplayName("관리자는 신고를 처리할 수 있다")
    void allowsProcessByStaff() throws Exception {
        User author = createUser();
        User reporter = createUser();
        User staff = createUser(true);
        long postId = createPost(author);
        long reportId = reportPost(reporter, postId);

        mockMvc.perform(post("/api/boards/reports/{id}/process", reportId)
                        .header("Authorization", bearer(staff))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"status":"resolved","adminMemo":"처리했습니다"}
                                """))
                .andExpect(status().isOk());
    }

    @Test
    @DisplayName("신고 목록은 관리자만 볼 수 있다")
    void reportListRequiresStaff() throws Exception {
        User user = createUser(false);

        mockMvc.perform(org.springframework.test.web.servlet.request.MockMvcRequestBuilders
                        .get("/api/boards/reports")
                        .header("Authorization", bearer(user)))
                .andExpect(status().isForbidden());
    }

    /**
     * Django `boards/tests.py` 의 `test_report_post_notifies_staff_users` 를 대체합니다.
     *
     * 신고가 접수되면 관리자가 알아야 하므로 staff 에게 알림이 갑니다.
     * 이 연결이 끊기면 신고가 쌓여도 아무도 모르는 상태가 되고, 화면상으로는 정상으로 보입니다.
     */
    @Test
    @DisplayName("신고가 접수되면 관리자에게 알림이 간다")
    void reportNotifiesStaff() throws Exception {
        User staff = createUser(true);
        User author = createUser();
        User reporter = createUser();
        long postId = createPost(author);

        reportPost(reporter, postId);

        mockMvc.perform(org.springframework.test.web.servlet.request.MockMvcRequestBuilders
                        .get("/api/notifications")
                        .header("Authorization", bearer(staff)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[0].notification_type").value("report_received"));
    }

    @Test
    @DisplayName("신고에는 신고자가 기록된다")
    void reportRecordsReporter() throws Exception {
        User author = createUser();
        User reporter = createUser();
        long postId = createPost(author);

        mockMvc.perform(post("/api/boards/posts/{id}/report", postId)
                        .header("Authorization", bearer(reporter))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"reason":"기록 확인"}
                                """))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.reason").value("기록 확인"));
    }
}
