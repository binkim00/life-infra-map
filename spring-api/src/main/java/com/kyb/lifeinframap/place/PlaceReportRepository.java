package com.kyb.lifeinframap.place;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;

public interface PlaceReportRepository extends JpaRepository<PlaceReport, Long> {

    Page<PlaceReport> findByUserIdOrderByCreatedAtDesc(Integer userId, Pageable pageable);

    Page<PlaceReport> findByStatus(String status, Pageable pageable);
}
