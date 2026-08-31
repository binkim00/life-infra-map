package com.kyb.lifeinframap.storage;

import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.kyb.lifeinframap.storage.service.StorageService;
import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockMultipartFile;

class StorageServiceValidationTest {

    @Test
    void rejectsNonImageContentWithAllowedExtension() {
        StorageService storage = new StorageService(
                "http://127.0.0.1:9000", "test", "test", "test-secret", "us-east-1");
        MockMultipartFile disguised = new MockMultipartFile(
                "image", "not-an-image.png", "image/png", "plain text".getBytes(StandardCharsets.UTF_8));

        assertThatThrownBy(() -> storage.upload(disguised, StorageService.BOARD_IMAGE_PREFIX))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("확장자");
    }
}
