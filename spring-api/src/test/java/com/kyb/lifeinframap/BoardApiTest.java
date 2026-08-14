package com.kyb.lifeinframap;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.patch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.kyb.lifeinframap.account.domain.User;
import com.kyb.lifeinframap.board.repository.PostRepository;
import com.kyb.lifeinframap.support.ApiTestBase;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MvcResult;

/**
 * 게시판 API의 Spring 이관 결과를 확인합니다.
 *
 * 권한 검사에 무게를 둡니다. 남의 글을 고칠 수 있는 종류의 결함은 조용히 들어가고,
 * 지금 Django 쪽 테스트가 1개뿐이라 이관 전후를 대조할 근거가 없습니다.
 */
class BoardApiTest extends ApiTestBase {

    @Autowired
    private PostRepository postRepository;

    private long createPost(User author) throws Exception {
        MvcResult result = mockMvc.perform(post("/api/boards/posts")
                        .header("Authorization", bearer(author))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"title":"제목","content":"본문","boardType":"free"}
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
                                {"content":"댓글 내용"}
                                """))
                .andExpect(status().isCreated())
                .andReturn();
        return objectMapper.readTree(result.getResponse().getContentAsString()).get("id").asLong();
    }

    // ---------- 글쓰기 ----------

    @Test
    @DisplayName("로그인하면 글을 쓸 수 있고 작성자가 기록된다")
    void createsPost() throws Exception {
        User author = createUser();

        mockMvc.perform(post("/api/boards/posts")
                        .header("Authorization", bearer(author))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"title":"첫 글","content":"본문입니다","boardType":"free"}
                                """))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.title").value("첫 글"))
                .andExpect(jsonPath("$.board_type").value("free"));
    }

    // ---------- 비로그인 조회 ----------
    //
    // Django 는 게시글 목록/상세가 `AllowAny` 였습니다. Spring 이관 직후 전부 인증을 요구해서
    // 로그인하지 않으면 게시판을 볼 수 없는 회귀가 있었습니다(커밋 53cfef2 에서 수정).
    // 가입 직후 상태로만 확인하면 드러나지 않는 종류라 테스트로 고정합니다.

    @Test
    @DisplayName("비로그인도 게시글 목록을 볼 수 있다")
    void allowsAnonymousList() throws Exception {
        User author = createUser();
        createPost(author);

        mockMvc.perform(get("/api/boards/posts"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$").isArray());
    }

    @Test
    @DisplayName("비로그인도 게시글 상세를 볼 수 있다")
    void allowsAnonymousDetail() throws Exception {
        User author = createUser();
        long postId = createPost(author);

        mockMvc.perform(get("/api/boards/posts/{id}", postId))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.title").value("제목"))
                .andExpect(jsonPath("$.comments").isArray());
    }

    @Test
    @DisplayName("비로그인 조회에서는 좋아요 표시가 켜지지 않는다")
    void anonymousDetailHasNoPersonalization() throws Exception {
        User author = createUser();
        long postId = createPost(author);
        mockMvc.perform(post("/api/boards/posts/{id}/like", postId)
                        .header("Authorization", bearer(author)))
                .andExpect(status().isOk());

        // 좋아요를 누른 사람이 아닌 익명 요청에는 개인화가 붙지 않아야 합니다.
        mockMvc.perform(get("/api/boards/posts/{id}", postId))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.is_liked").value(false));
    }

    @Test
    @DisplayName("토큰 없이 글을 쓸 수 없다")
    void rejectsAnonymousPost() throws Exception {
        mockMvc.perform(post("/api/boards/posts")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"title":"익명","content":"본문"}
                                """))
                .andExpect(status().isUnauthorized());
    }

    @Test
    @DisplayName("일반 사용자는 공지를 쓸 수 없다")
    void rejectsNoticeFromNonStaff() throws Exception {
        User user = createUser(false);

        mockMvc.perform(post("/api/boards/posts")
                        .header("Authorization", bearer(user))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"title":"공지","content":"본문","boardType":"notice"}
                                """))
                .andExpect(status().isForbidden());
    }

    @Test
    @DisplayName("관리자는 공지를 쓸 수 있고 공지는 고정된다")
    void allowsNoticeFromStaff() throws Exception {
        User staff = createUser(true);

        mockMvc.perform(post("/api/boards/posts")
                        .header("Authorization", bearer(staff))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"title":"공지","content":"본문","boardType":"notice"}
                                """))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.board_type").value("notice"))
                .andExpect(jsonPath("$.is_pinned").value(true));
    }

    // ---------- 수정·삭제 권한 ----------

    @Test
    @DisplayName("남의 글은 수정할 수 없다")
    void rejectsUpdateByOtherUser() throws Exception {
        User author = createUser();
        User stranger = createUser();
        long postId = createPost(author);

        mockMvc.perform(patch("/api/boards/posts/{id}", postId)
                        .header("Authorization", bearer(stranger))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"title":"가로채기","content":"바꿔치기"}
                                """))
                .andExpect(status().isForbidden());

        assertThat(postRepository.findById(postId).orElseThrow().getTitle()).isEqualTo("제목");
    }

    @Test
    @DisplayName("본인 글은 수정할 수 있다")
    void allowsUpdateByAuthor() throws Exception {
        User author = createUser();
        long postId = createPost(author);

        mockMvc.perform(patch("/api/boards/posts/{id}", postId)
                        .header("Authorization", bearer(author))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"title":"고친 제목","content":"고친 본문"}
                                """))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.title").value("고친 제목"));
    }

    @Test
    @DisplayName("남의 글은 삭제할 수 없다")
    void rejectsDeleteByOtherUser() throws Exception {
        User author = createUser();
        User stranger = createUser();
        long postId = createPost(author);

        mockMvc.perform(delete("/api/boards/posts/{id}", postId)
                        .header("Authorization", bearer(stranger)))
                .andExpect(status().isForbidden());

        assertThat(postRepository.findById(postId)).isPresent();
    }

    @Test
    @DisplayName("관리자는 남의 글도 삭제할 수 있다")
    void allowsDeleteByStaff() throws Exception {
        User author = createUser();
        User staff = createUser(true);
        long postId = createPost(author);

        mockMvc.perform(delete("/api/boards/posts/{id}", postId)
                        .header("Authorization", bearer(staff)))
                .andExpect(status().isNoContent());

        assertThat(postRepository.findById(postId)).isEmpty();
    }

    @Test
    @DisplayName("없는 글은 404 다")
    void returnsNotFoundForMissingPost() throws Exception {
        User user = createUser();

        mockMvc.perform(get("/api/boards/posts/{id}", 99_999_999L)
                        .header("Authorization", bearer(user)))
                .andExpect(status().isNotFound());
    }

    // ---------- 상세 조회 ----------

    @Test
    @DisplayName("상세 조회는 댓글을 함께 내려주고 조회수를 올린다")
    void detailIncludesCommentsAndIncreasesViewCount() throws Exception {
        User author = createUser();
        long postId = createPost(author);
        createComment(author, postId);

        mockMvc.perform(get("/api/boards/posts/{id}", postId)
                        .header("Authorization", bearer(author)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.comments").isArray())
                .andExpect(jsonPath("$.comments[0].content").value("댓글 내용"))
                .andExpect(jsonPath("$.view_count").value(1));
    }

    // ---------- 댓글 ----------

    @Test
    @DisplayName("남의 댓글은 수정할 수 없다")
    void rejectsCommentUpdateByOtherUser() throws Exception {
        User author = createUser();
        User stranger = createUser();
        long postId = createPost(author);
        long commentId = createComment(author, postId);

        mockMvc.perform(patch("/api/boards/comments/{id}", commentId)
                        .header("Authorization", bearer(stranger))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"content":"가로채기"}
                                """))
                .andExpect(status().isForbidden());
    }

    @Test
    @DisplayName("답글의 부모가 없으면 400 이다")
    void rejectsReplyToMissingParent() throws Exception {
        User author = createUser();
        long postId = createPost(author);

        mockMvc.perform(post("/api/boards/posts/{id}/comments", postId)
                        .header("Authorization", bearer(author))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"content":"답글","parent":99999999}
                                """))
                .andExpect(status().isBadRequest());
    }

    // ---------- 좋아요 토글 ----------

    @Test
    @DisplayName("같은 글에 좋아요를 두 번 누르면 취소된다")
    void togglesPostLike() throws Exception {
        User author = createUser();
        long postId = createPost(author);

        mockMvc.perform(post("/api/boards/posts/{id}/like", postId)
                        .header("Authorization", bearer(author)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.is_liked").value(true));

        mockMvc.perform(post("/api/boards/posts/{id}/like", postId)
                        .header("Authorization", bearer(author)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.is_liked").value(false));
    }

    @Test
    @DisplayName("댓글 좋아요를 누르면 싫어요가 해제된다")
    void commentLikeClearsDislike() throws Exception {
        User author = createUser();
        long postId = createPost(author);
        long commentId = createComment(author, postId);

        mockMvc.perform(post("/api/boards/comments/{id}/dislike", commentId)
                        .header("Authorization", bearer(author)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.is_disliked").value(true));

        mockMvc.perform(post("/api/boards/comments/{id}/like", commentId)
                        .header("Authorization", bearer(author)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.is_liked").value(true))
                .andExpect(jsonPath("$.is_disliked").value(false));
    }
}
