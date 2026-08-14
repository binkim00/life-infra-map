package com.kyb.lifeinframap.storage;

import static org.assertj.core.api.Assertions.assertThat;

import java.net.URI;
import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockMultipartFile;
import software.amazon.awssdk.auth.credentials.AwsBasicCredentials;
import software.amazon.awssdk.auth.credentials.StaticCredentialsProvider;
import software.amazon.awssdk.core.ResponseBytes;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.S3Configuration;
import software.amazon.awssdk.services.s3.model.DeleteObjectRequest;
import software.amazon.awssdk.services.s3.model.GetObjectRequest;
import software.amazon.awssdk.services.s3.model.GetObjectResponse;

@Tag("integration")
class StorageServiceMinioIntegrationTest {

    @Test
    void uploadsAndReadsImageFromMinio() {
        String endpoint = environment("S3_ENDPOINT_URL", "http://127.0.0.1:9000");
        String bucket = environment("S3_BUCKET", "life-infra-map-media");
        String accessKey = environment("S3_ACCESS_KEY", "life_infra_map");
        String secretKey = environment("S3_SECRET_KEY", "life_infra_map_secret");
        String region = environment("S3_REGION", "us-east-1");
        byte[] expected = "minio-integration-test".getBytes(StandardCharsets.UTF_8);

        StorageService storageService = new StorageService(
                endpoint, bucket, accessKey, secretKey, region);
        MockMultipartFile image = new MockMultipartFile(
                "image", "integration-test.png", "image/png", expected);

        try (S3Client client = client(endpoint, accessKey, secretKey, region)) {
            String key = storageService.upload(image, StorageService.BOARD_IMAGE_PREFIX);
            try {
                ResponseBytes<GetObjectResponse> stored = client.getObjectAsBytes(
                        GetObjectRequest.builder().bucket(bucket).key(key).build());

                assertThat(key).startsWith(StorageService.BOARD_IMAGE_PREFIX + "/");
                assertThat(stored.asByteArray()).isEqualTo(expected);
                assertThat(stored.response().contentType()).isEqualTo("image/png");
            } finally {
                client.deleteObject(DeleteObjectRequest.builder().bucket(bucket).key(key).build());
            }
        }
    }

    private S3Client client(String endpoint, String accessKey, String secretKey, String region) {
        return S3Client.builder()
                .endpointOverride(URI.create(endpoint))
                .region(Region.of(region))
                .credentialsProvider(StaticCredentialsProvider.create(
                        AwsBasicCredentials.create(accessKey, secretKey)))
                .serviceConfiguration(S3Configuration.builder().pathStyleAccessEnabled(true).build())
                .build();
    }

    private String environment(String name, String defaultValue) {
        String value = System.getenv(name);
        return value == null || value.isBlank() ? defaultValue : value;
    }
}
