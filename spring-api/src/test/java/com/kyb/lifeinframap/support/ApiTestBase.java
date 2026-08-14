package com.kyb.lifeinframap.support;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.kyb.lifeinframap.account.domain.User;
import com.kyb.lifeinframap.account.domain.UserProfile;
import com.kyb.lifeinframap.account.repository.UserProfileRepository;
import com.kyb.lifeinframap.account.repository.UserRepository;
import com.kyb.lifeinframap.security.JwtService;
import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.transaction.TestTransaction;
import org.springframework.test.util.ReflectionTestUtils;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.transaction.annotation.Transactional;

/**
 * 컨트롤러 테스트 공통 설정입니다.
 *
 * 스키마 소유자가 Django 이므로 Hibernate 가 테이블을 만들 수 없습니다(`ddl-auto: validate`).
 * 그래서 개발용 Postgres 에 그대로 붙고, `@Transactional` 로 테스트마다 롤백합니다.
 * 실행 전에 `docker compose up -d db` 가 되어 있어야 합니다.
 *
 * 롤백되지 않는 것이 하나 있습니다. 시퀀스는 트랜잭션을 따르지 않으므로
 * 테스트를 돌리면 id 값이 앞으로 나갑니다. 데이터가 남지는 않으니 문제되지 않습니다.
 */
@SpringBootTest
@AutoConfigureMockMvc
@Transactional
public abstract class ApiTestBase {

    /** 같은 실행 안에서 username 이 겹치지 않게 합니다. username 에 unique 제약이 있습니다. */
    private static final AtomicInteger SEQUENCE = new AtomicInteger();

    @Autowired
    protected MockMvc mockMvc;

    @Autowired
    protected ObjectMapper objectMapper;

    @Autowired
    protected UserRepository userRepository;

    @Autowired
    protected UserProfileRepository profileRepository;

    @Autowired
    protected JwtService jwtService;

    /** 일반 사용자를 만듭니다. 비밀번호 검증이 필요한 테스트는 `createUser(username, password, staff)` 를 쓰세요. */
    protected User createUser() {
        return createUser(false);
    }

    protected User createUser(boolean staff) {
        int index = SEQUENCE.incrementAndGet();
        return createUser("testuser" + index + "_" + System.nanoTime(), staff);
    }

    protected User createUser(String username, boolean staff) {
        // 비밀번호는 이미 해싱된 값을 넣습니다. 로그인 테스트가 아니면 값 자체는 쓰이지 않습니다.
        User user = User.create(username, username + "@test.dev", "!unusable");
        if (staff) {
            // User 에 staff 설정 메서드가 없습니다. 운영 코드에 테스트 전용 setter 를 만들지 않기 위해
            // 여기서만 필드를 직접 채웁니다. is_staff 는 Django 가 소유한 컬럼입니다.
            ReflectionTestUtils.setField(user, "staff", true);
        }
        userRepository.save(user);
        profileRepository.save(new UserProfile(user, nickname(username)));
        return user;
    }

    /**
     * `accounts_userprofile.nickname` 에는 unique 제약이 있고 길이는 50 입니다.
     * username 앞부분만 쓰면 테스트끼리 겹치므로 뒤쪽(고유한 부분)을 남깁니다.
     */
    private String nickname(String username) {
        String candidate = "닉" + username;
        return candidate.length() <= 50 ? candidate : candidate.substring(candidate.length() - 50);
    }

    /** `Authorization` 헤더에 넣을 값입니다. 실제 JwtService 로 발급하므로 필터 경로를 그대로 지납니다. */
    protected String bearer(User user) {
        return "Bearer " + jwtService.issueAccessToken(user.getId(), user.getUsername());
    }

    /**
     * 조회 API 가 방금 만든 데이터를 보게 하려면 트랜잭션을 한 번 끊어야 합니다.
     * MockMvc 요청은 같은 트랜잭션을 쓰므로 대부분은 필요 없지만,
     * 커밋된 상태를 전제로 하는 테스트에서 씁니다. 호출한 테스트는 롤백되지 않으니 정리를 직접 하세요.
     */
    protected void flushAndCommit() {
        TestTransaction.flagForCommit();
        TestTransaction.end();
        TestTransaction.start();
    }
}
