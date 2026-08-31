package com.kyb.lifeinframap;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.patch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.kyb.lifeinframap.account.domain.User;
import com.kyb.lifeinframap.board.domain.Post;
import com.kyb.lifeinframap.board.domain.Report;
import com.kyb.lifeinframap.board.repository.PostRepository;
import com.kyb.lifeinframap.board.repository.ReportRepository;
import com.kyb.lifeinframap.board.repository.UserPenaltyRepository;
import com.kyb.lifeinframap.support.ApiTestBase;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.MediaType;

class ApiContractCompatibilityTest extends ApiTestBase {

    @Autowired
    private PostRepository postRepository;

    @Autowired
    private ReportRepository reportRepository;

    @Autowired
    private UserPenaltyRepository penaltyRepository;

    @Test
    void acceptsDjangoStyleSavedPlaceFields() throws Exception {
        User user = createUser();

        mockMvc.perform(post("/api/recommendations/saved-places")
                        .header("Authorization", bearer(user))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"place_key":"place:123","source":"local_db","name":"테스트 장소",
                                 "place_id":123,"external_id":"ext-1","detail_url":"https://example.test/place"}
                                """))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.place").value(123))
                .andExpect(jsonPath("$.external_id").value("ext-1"))
                .andExpect(jsonPath("$.source_label").value("저장 장소"));
    }

    @Test
    void acceptsPatchAndSnakeCaseWhenProcessingReport() throws Exception {
        User author = createUser();
        User reporter = createUser();
        User staff = createUser(true);
        Post post = postRepository.save(Post.create(author, "free", "신고 대상", "본문", null));
        Report report = reportRepository.save(Report.create(reporter, post, null, "신고 사유입니다"));

        mockMvc.perform(patch("/api/boards/reports/{id}/process", report.getId())
                        .header("Authorization", bearer(staff))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"action":"penalized","admin_memo":"처리 완료",
                                 "penalty_type":"warning","penalty_reason":"운영 정책 위반"}
                                """))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("penalized"))
                .andExpect(jsonPath("$.target_type").value("post"))
                .andExpect(jsonPath("$.reported_user_id").value(author.getId()));

        org.assertj.core.api.Assertions.assertThat(
                penaltyRepository.findByUserIdOrderByCreatedAtDesc(author.getId())).hasSize(1);
    }

    @Test
    void rejectsBlankPostBody() throws Exception {
        User author = createUser();

        mockMvc.perform(post("/api/boards/posts")
                        .header("Authorization", bearer(author))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"title\":\"\",\"content\":\"\"}"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.title").isArray())
                .andExpect(jsonPath("$.content").isArray());
    }
}
