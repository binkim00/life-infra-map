package com.kyb.lifeinframap;

import com.kyb.lifeinframap.security.DjangoPasswordEncoder;

/**
 * Spring 이 만든 해시를 Django 가 그대로 검증하는지 확인할 때 쓰는 보조 도구입니다.
 *
 *   java -cp build/classes/java/main:build/classes/java/test com.kyb.lifeinframap.PrintHash '비밀번호'
 */
public class PrintHash {

    public static void main(String[] args) {
        if (args.length != 1) {
            System.err.println("사용법: PrintHash <비밀번호>");
            System.exit(1);
        }
        System.out.println(new DjangoPasswordEncoder().encode(args[0]));
    }
}
