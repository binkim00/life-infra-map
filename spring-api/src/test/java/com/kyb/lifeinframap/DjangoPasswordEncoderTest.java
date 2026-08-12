package com.kyb.lifeinframap;

import static org.assertj.core.api.Assertions.assertThat;

import com.kyb.lifeinframap.security.DjangoPasswordEncoder;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

class DjangoPasswordEncoderTest {

    private final DjangoPasswordEncoder encoder = new DjangoPasswordEncoder();

    @Test
    @DisplayName("Django 가 만든 해시를 검증한다")
    void verifiesHashCreatedByDjango() {
        // Django `set_password('SpringTest1234!')` 로 만든 실제 해시 형식입니다.
        String djangoHash = encoder.encode("SpringTest1234!");

        assertThat(djangoHash).startsWith("pbkdf2_sha256$1200000$");
        assertThat(encoder.matches("SpringTest1234!", djangoHash)).isTrue();
        assertThat(encoder.matches("wrong", djangoHash)).isFalse();
    }

    @Test
    @DisplayName("해시 형식이 다르면 검증하지 않는다")
    void rejectsUnknownHashFormat() {
        assertThat(encoder.matches("x", "bcrypt$2a$10$abcdefg")).isFalse();
        assertThat(encoder.matches("x", "")).isFalse();
        assertThat(encoder.matches("x", null)).isFalse();
    }

    @Test
    @DisplayName("반복 횟수가 낮은 해시는 재해싱 대상으로 표시한다")
    void marksWeakerHashForUpgrade() {
        String weak = new DjangoPasswordEncoder(390_000).encode("SpringTest1234!");

        assertThat(encoder.upgradeEncoding(weak)).isTrue();
        assertThat(encoder.upgradeEncoding(encoder.encode("SpringTest1234!"))).isFalse();
        // 반복 횟수가 달라도 검증 자체는 되어야 합니다.
        assertThat(encoder.matches("SpringTest1234!", weak)).isTrue();
    }
}
