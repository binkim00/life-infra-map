package com.kyb.lifeinframap;

import static org.assertj.core.api.Assertions.assertThat;
import static org.hamcrest.Matchers.endsWith;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.kyb.lifeinframap.account.domain.User;
import com.kyb.lifeinframap.board.domain.Post;
import com.kyb.lifeinframap.board.repository.PostRepository;
import com.kyb.lifeinframap.storage.service.StorageService;
import com.kyb.lifeinframap.support.ApiTestBase;
import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.web.multipart.MultipartFile;

class MultipartUploadApiTest extends ApiTestBase {

    @MockitoBean
    private StorageService storageService;

    @Autowired
    private PostRepository postRepository;

    @Test
    @DisplayName("회원가입 프로필 이미지를 저장하고 저장소 키를 프로필에 기록한다")
    void signsUpWithProfileImage() throws Exception {
        String username = "multipart" + System.nanoTime();
        String imageKey = "profile_images/signup-avatar.png";
        MockMultipartFile image = image("profile_image", "signup-avatar.png");
        when(storageService.upload(any(MultipartFile.class), eq(StorageService.PROFILE_IMAGE_PREFIX)))
                .thenReturn(imageKey);

        mockMvc.perform(multipart("/api/accounts/signup")
                        .file(image)
                        .param("username", username)
                        .param("nickname", "multipart-" + System.nanoTime())
                        .param("email", username + "@test.dev")
                        .param("password", "testpass1234")
                        .param("password_confirm", "testpass1234"))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.user.username").value(username))
                .andExpect(jsonPath("$.user.profile_image_url", endsWith("/" + imageKey)));

        verify(storageService).upload(any(MultipartFile.class), eq(StorageService.PROFILE_IMAGE_PREFIX));
        User created = userRepository.findByUsername(username).orElseThrow();
        assertThat(profileRepository.findByUserId(created.getId()).orElseThrow().getProfileImage())
                .isEqualTo(imageKey);
    }

    @Test
    @DisplayName("multipart 요청으로 현재 사용자의 프로필 이미지를 변경한다")
    void changesProfileImageWithMultipartRequest() throws Exception {
        User user = createUser();
        String imageKey = "profile_images/changed-avatar.webp";
        MockMultipartFile image = image("profile_image", "changed-avatar.webp");
        when(storageService.upload(any(MultipartFile.class), eq(StorageService.PROFILE_IMAGE_PREFIX)))
                .thenReturn(imageKey);

        mockMvc.perform(multipart("/api/accounts/me/profile-image")
                        .file(image)
                        .with(request -> {
                            request.setMethod("PATCH");
                            return request;
                        })
                        .header("Authorization", bearer(user)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.user.profile_image_url", endsWith("/" + imageKey)));

        verify(storageService).upload(any(MultipartFile.class), eq(StorageService.PROFILE_IMAGE_PREFIX));
        assertThat(profileRepository.findByUserId(user.getId()).orElseThrow().getProfileImage())
                .isEqualTo(imageKey);
    }

    @Test
    @DisplayName("게시글 이미지를 저장하고 게시글 응답과 DB에 저장소 키를 기록한다")
    void createsPostWithImage() throws Exception {
        User author = createUser();
        String title = "multipart-post-" + System.nanoTime();
        String imageKey = "board_images/post-image.jpg";
        MockMultipartFile image = image("image", "post-image.jpg");
        when(storageService.upload(any(MultipartFile.class), eq(StorageService.BOARD_IMAGE_PREFIX)))
                .thenReturn(imageKey);

        mockMvc.perform(multipart("/api/boards/posts")
                        .file(image)
                        .param("title", title)
                        .param("content", "이미지가 포함된 게시글 본문")
                        .param("board_type", "free")
                        .header("Authorization", bearer(author)))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.title").value(title))
                .andExpect(jsonPath("$.image").value(imageKey))
                .andExpect(jsonPath("$.image_url", endsWith("/" + imageKey)));

        verify(storageService).upload(any(MultipartFile.class), eq(StorageService.BOARD_IMAGE_PREFIX));
        Post created = postRepository.findAll().stream()
                .filter(post -> title.equals(post.getTitle()))
                .findFirst()
                .orElseThrow();
        assertThat(created.getImage()).isEqualTo(imageKey);
    }

    private MockMultipartFile image(String fieldName, String originalFilename) {
        return new MockMultipartFile(
                fieldName,
                originalFilename,
                "image/png",
                "fake-image-content".getBytes(StandardCharsets.UTF_8));
    }
}
