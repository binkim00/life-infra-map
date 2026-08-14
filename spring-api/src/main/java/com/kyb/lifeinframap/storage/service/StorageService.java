package com.kyb.lifeinframap.storage.service;

import java.io.IOException;
import java.net.URI;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.util.Locale;
import java.util.Set;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.web.multipart.MultipartFile;
import software.amazon.awssdk.auth.credentials.AwsBasicCredentials;
import software.amazon.awssdk.auth.credentials.StaticCredentialsProvider;
import software.amazon.awssdk.core.sync.RequestBody;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.S3Configuration;
import software.amazon.awssdk.services.s3.model.PutObjectRequest;

/**
 * 업로드 파일을 S3 호환 저장소에 올립니다.
 *
 * Django 와 같은 버킷, 같은 키 규칙을 씁니다. 그래야 어느 쪽이 올렸든 서로 읽을 수 있습니다.
 *
 *   프로필 사진   profile_images/<파일명>
 *   게시글 이미지 board_images/<파일명>
 *   제보 사진     place_reports/<연>/<월>/<파일명>
 *
 * 같은 이름이 이미 있으면 Django 처럼 덮어쓰지 않고 뒤에 짧은 구분자를 붙입니다.
 */
@Service
public class StorageService {

    public static final String PROFILE_IMAGE_PREFIX = "profile_images";
    public static final String BOARD_IMAGE_PREFIX = "board_images";
    public static final String PLACE_REPORT_PREFIX = "place_reports";

    private static final Set<String> ALLOWED_EXTENSIONS =
            Set.of("jpg", "jpeg", "png", "gif", "webp");
    private static final long MAX_BYTES = 10L * 1024 * 1024;

    private final S3Client client;
    private final String bucket;

    public StorageService(
            @Value("${app.storage.endpoint}") String endpoint,
            @Value("${app.storage.bucket}") String bucket,
            @Value("${app.storage.access-key}") String accessKey,
            @Value("${app.storage.secret-key}") String secretKey,
            @Value("${app.storage.region}") String region) {
        this.bucket = bucket;
        this.client = S3Client.builder()
                .endpointOverride(URI.create(endpoint))
                .region(Region.of(region))
                .credentialsProvider(StaticCredentialsProvider.create(
                        AwsBasicCredentials.create(accessKey, secretKey)))
                // MinIO 는 가상 호스트 방식 주소를 기본 지원하지 않습니다.
                .serviceConfiguration(S3Configuration.builder().pathStyleAccessEnabled(true).build())
                .build();
    }

    /** 업로드하고 저장소 키를 돌려줍니다. 파일이 비어 있으면 null 입니다. */
    public String upload(MultipartFile file, String prefix) {
        if (file == null || file.isEmpty()) {
            return null;
        }
        validate(file);

        String key = buildKey(file.getOriginalFilename(), prefix);
        try {
            client.putObject(
                    PutObjectRequest.builder()
                            .bucket(bucket)
                            .key(key)
                            .contentType(file.getContentType())
                            .build(),
                    RequestBody.fromInputStream(file.getInputStream(), file.getSize()));
        } catch (IOException exception) {
            throw new IllegalStateException("파일을 저장하지 못했습니다.", exception);
        }
        return key;
    }

    private void validate(MultipartFile file) {
        if (file.getSize() > MAX_BYTES) {
            throw new IllegalArgumentException("파일 크기는 10MB 를 넘을 수 없습니다.");
        }
        String extension = extensionOf(file.getOriginalFilename());
        if (!ALLOWED_EXTENSIONS.contains(extension)) {
            throw new IllegalArgumentException("jpg, jpeg, png, gif, webp 만 올릴 수 있습니다.");
        }
    }

    private String buildKey(String originalName, String prefix) {
        String extension = extensionOf(originalName);
        String base = baseNameOf(originalName);
        // 같은 이름이 겹쳐도 서로 덮어쓰지 않도록 짧은 구분자를 붙입니다.
        String unique = java.util.UUID.randomUUID().toString().replace("-", "").substring(0, 7);
        String fileName = base + "_" + unique + "." + extension;

        if (PLACE_REPORT_PREFIX.equals(prefix)) {
            LocalDate today = LocalDate.now();
            return String.format("%s/%s/%s/%s", prefix,
                    today.format(DateTimeFormatter.ofPattern("yyyy")),
                    today.format(DateTimeFormatter.ofPattern("MM")),
                    fileName);
        }
        return prefix + "/" + fileName;
    }

    private String extensionOf(String name) {
        if (name == null) {
            return "";
        }
        int dot = name.lastIndexOf('.');
        return dot < 0 ? "" : name.substring(dot + 1).toLowerCase(Locale.ROOT);
    }

    private String baseNameOf(String name) {
        if (name == null || name.isBlank()) {
            return "upload";
        }
        String withoutPath = name.replaceAll(".*[/\\\\]", "");
        int dot = withoutPath.lastIndexOf('.');
        String base = dot < 0 ? withoutPath : withoutPath.substring(0, dot);
        // 키에 쓰기 곤란한 문자만 걸러내고 한글은 그대로 둡니다. Django 도 그렇게 저장합니다.
        base = base.replaceAll("[\\s?#\\[\\]{}<>%\"'`|^]+", "_");
        return base.isBlank() ? "upload" : base;
    }
}
