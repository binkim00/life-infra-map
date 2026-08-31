package com.kyb.lifeinframap.web;

import jakarta.validation.ConstraintViolationException;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.validation.BindException;
import org.springframework.validation.FieldError;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.MissingServletRequestParameterException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.method.annotation.HandlerMethodValidationException;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;
import org.springframework.web.multipart.MaxUploadSizeExceededException;

/** Django REST Framework와 비슷한 예측 가능한 오류 응답을 만듭니다. */
@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<?> invalidBody(MethodArgumentNotValidException exception) {
        return ResponseEntity.badRequest().body(fieldErrors(exception.getBindingResult().getFieldErrors()));
    }

    @ExceptionHandler(BindException.class)
    public ResponseEntity<?> invalidBinding(BindException exception) {
        return ResponseEntity.badRequest().body(fieldErrors(exception.getBindingResult().getFieldErrors()));
    }

    @ExceptionHandler({ConstraintViolationException.class, HandlerMethodValidationException.class})
    public ResponseEntity<?> invalidParameter(Exception exception) {
        return ResponseEntity.badRequest().body(Map.of("detail", "요청 값을 확인해주세요."));
    }

    @ExceptionHandler({HttpMessageNotReadableException.class, MethodArgumentTypeMismatchException.class})
    public ResponseEntity<?> malformedRequest(Exception exception) {
        return ResponseEntity.badRequest().body(Map.of("detail", "요청 형식이 올바르지 않습니다."));
    }

    @ExceptionHandler(MissingServletRequestParameterException.class)
    public ResponseEntity<?> missingParameter(MissingServletRequestParameterException exception) {
        return ResponseEntity.badRequest().body(Map.of(
                snakeCase(exception.getParameterName()), List.of("필수 항목입니다.")));
    }

    @ExceptionHandler(MaxUploadSizeExceededException.class)
    public ResponseEntity<?> uploadTooLarge(MaxUploadSizeExceededException exception) {
        return ResponseEntity.status(HttpStatus.PAYLOAD_TOO_LARGE)
                .body(Map.of("detail", "업로드 파일이 허용 크기를 초과했습니다."));
    }

    @ExceptionHandler(DataIntegrityViolationException.class)
    public ResponseEntity<?> dataConflict(DataIntegrityViolationException exception) {
        return ResponseEntity.status(HttpStatus.CONFLICT)
                .body(Map.of("detail", "이미 존재하거나 저장할 수 없는 값입니다."));
    }

    private Map<String, List<String>> fieldErrors(List<FieldError> errors) {
        Map<String, List<String>> body = new LinkedHashMap<>();
        for (FieldError error : errors) {
            body.computeIfAbsent(snakeCase(error.getField()), key -> new ArrayList<>())
                    .add(error.getDefaultMessage() == null ? "올바른 값을 입력해주세요." : error.getDefaultMessage());
        }
        return body;
    }

    private static String snakeCase(String value) {
        return value.replaceAll("([a-z0-9])([A-Z])", "$1_$2").toLowerCase();
    }
}
