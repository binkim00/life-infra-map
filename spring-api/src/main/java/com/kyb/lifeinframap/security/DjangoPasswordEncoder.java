package com.kyb.lifeinframap.security;

import java.security.NoSuchAlgorithmException;
import java.security.spec.InvalidKeySpecException;
import java.security.spec.KeySpec;
import java.util.Base64;
import javax.crypto.SecretKeyFactory;
import javax.crypto.spec.PBEKeySpec;
import org.springframework.security.crypto.password.PasswordEncoder;

/**
 * Django 가 저장한 비밀번호 해시를 그대로 검증합니다.
 *
 * 기존 사용자가 Spring 쪽 로그인에서도 같은 비밀번호를 쓸 수 있어야 하므로
 * Django 의 `pbkdf2_sha256` 형식을 직접 다룹니다.
 *
 *   pbkdf2_sha256$<반복횟수>$<salt>$<base64 해시>
 *
 * 새 비밀번호를 만들 때도 같은 형식으로 저장해 Django 쪽에서도 로그인되게 합니다.
 */
public class DjangoPasswordEncoder implements PasswordEncoder {

    private static final String ALGORITHM = "pbkdf2_sha256";
    private static final String SECRET_KEY_ALGORITHM = "PBKDF2WithHmacSHA256";
    private static final int KEY_LENGTH_BITS = 256;
    private static final int DEFAULT_ITERATIONS = 1_200_000;

    private final int iterations;
    private final java.security.SecureRandom random = new java.security.SecureRandom();

    public DjangoPasswordEncoder() {
        this(DEFAULT_ITERATIONS);
    }

    public DjangoPasswordEncoder(int iterations) {
        this.iterations = iterations;
    }

    @Override
    public String encode(CharSequence rawPassword) {
        byte[] saltBytes = new byte[16];
        random.nextBytes(saltBytes);
        // Django 는 salt 를 문자열로 저장하므로 영숫자로 만듭니다.
        String salt = Base64.getEncoder().withoutPadding().encodeToString(saltBytes)
                .replace("+", "")
                .replace("/", "");
        String hash = pbkdf2(rawPassword.toString(), salt, iterations);
        return ALGORITHM + "$" + iterations + "$" + salt + "$" + hash;
    }

    @Override
    public boolean matches(CharSequence rawPassword, String encodedPassword) {
        if (rawPassword == null || encodedPassword == null) {
            return false;
        }
        String[] parts = encodedPassword.split("\\$");
        if (parts.length != 4 || !ALGORITHM.equals(parts[0])) {
            // 다른 해시 방식(bcrypt, argon2 등)은 아직 다루지 않습니다.
            return false;
        }
        int storedIterations;
        try {
            storedIterations = Integer.parseInt(parts[1]);
        } catch (NumberFormatException exception) {
            return false;
        }
        String expected = parts[3];
        String actual = pbkdf2(rawPassword.toString(), parts[2], storedIterations);
        return constantTimeEquals(expected, actual);
    }

    @Override
    public boolean upgradeEncoding(String encodedPassword) {
        // 반복 횟수가 지금 기준보다 낮으면 다음 로그인 때 다시 해싱하도록 알립니다.
        String[] parts = encodedPassword == null ? new String[0] : encodedPassword.split("\\$");
        if (parts.length != 4 || !ALGORITHM.equals(parts[0])) {
            return false;
        }
        try {
            return Integer.parseInt(parts[1]) < iterations;
        } catch (NumberFormatException exception) {
            return false;
        }
    }

    private String pbkdf2(String password, String salt, int iterationCount) {
        try {
            KeySpec spec = new PBEKeySpec(
                    password.toCharArray(),
                    salt.getBytes(java.nio.charset.StandardCharsets.UTF_8),
                    iterationCount,
                    KEY_LENGTH_BITS);
            SecretKeyFactory factory = SecretKeyFactory.getInstance(SECRET_KEY_ALGORITHM);
            return Base64.getEncoder().encodeToString(factory.generateSecret(spec).getEncoded());
        } catch (NoSuchAlgorithmException | InvalidKeySpecException exception) {
            throw new IllegalStateException("PBKDF2 계산에 실패했습니다.", exception);
        }
    }

    private boolean constantTimeEquals(String left, String right) {
        byte[] a = left.getBytes(java.nio.charset.StandardCharsets.UTF_8);
        byte[] b = right.getBytes(java.nio.charset.StandardCharsets.UTF_8);
        return java.security.MessageDigest.isEqual(a, b);
    }
}
