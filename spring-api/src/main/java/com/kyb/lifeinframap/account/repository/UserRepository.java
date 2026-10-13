package com.kyb.lifeinframap.account.repository;

import com.kyb.lifeinframap.account.domain.*;
import com.kyb.lifeinframap.account.repository.*;
import com.kyb.lifeinframap.account.service.*;

import java.util.Optional;
import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;

public interface UserRepository extends JpaRepository<User, Integer> {

    Optional<User> findByUsername(String username);

    List<User> findByEmailIgnoreCase(String email);
}
