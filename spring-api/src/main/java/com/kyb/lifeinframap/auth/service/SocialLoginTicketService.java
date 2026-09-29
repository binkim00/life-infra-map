package com.kyb.lifeinframap.auth.service;

import com.kyb.lifeinframap.account.domain.User;
import com.kyb.lifeinframap.account.repository.UserRepository;
import com.kyb.lifeinframap.auth.domain.SocialLoginTicket;
import com.kyb.lifeinframap.auth.repository.SocialLoginTicketRepository;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.SecureRandom;
import java.time.OffsetDateTime;
import java.util.Base64;
import java.util.HexFormat;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class SocialLoginTicketService {
    private final SocialLoginTicketRepository tickets;
    private final UserRepository users;
    private final SecureRandom random = new SecureRandom();

    public SocialLoginTicketService(SocialLoginTicketRepository tickets, UserRepository users) {
        this.tickets = tickets;
        this.users = users;
    }

    @Transactional
    public String issue(User user) {
        byte[] bytes = new byte[32];
        random.nextBytes(bytes);
        String ticket = Base64.getUrlEncoder().withoutPadding().encodeToString(bytes);
        tickets.save(new SocialLoginTicket(user.getId(), hash(ticket)));
        return ticket;
    }

    @Transactional
    public User consume(String ticket) {
        if (ticket == null || ticket.length() < 40 || ticket.length() > 100) return null;
        SocialLoginTicket row = tickets.lockByTicketHash(hash(ticket)).orElse(null);
        if (row == null || !row.isActive(OffsetDateTime.now())) return null;
        User user = users.findById(row.getUserId()).orElse(null);
        if (user == null || !user.isActive()) return null;
        row.consume(OffsetDateTime.now());
        return user;
    }

    private static String hash(String value) {
        try {
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256")
                    .digest(value.getBytes(StandardCharsets.UTF_8)));
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException("SHA-256 unavailable", exception);
        }
    }
}
