# Welcome to your Expo app 👋

This is an [Expo](https://expo.dev) project created with [`create-expo-app`](https://www.npmjs.com/package/create-expo-app).

## Get started

1. Install dependencies

   ```bash
   npm install
   ```

2. Start the app

   ```bash
   npx expo start
   ```

In the output, you'll find options to open the app in a

- [development build](https://docs.expo.dev/develop/development-builds/introduction/)
- [Android emulator](https://docs.expo.dev/workflow/android-studio-emulator/)
- [iOS simulator](https://docs.expo.dev/workflow/ios-simulator/)
- [Expo Go](https://expo.dev/go), a limited sandbox for trying out app development with Expo

You can start developing by editing the files inside the **app** directory. This project uses [file-based routing](https://docs.expo.dev/router/introduction).

## Get a fresh project

When you're ready, run:

```bash
npm run reset-project
```

This command will move the starter code to the **app-example** directory and create a blank **app** directory where you can start developing.

### Other setup steps

- To set up ESLint for linting, run `npx expo lint`, or follow our guide on ["Using ESLint and Prettier"](https://docs.expo.dev/guides/using-eslint/)
- If you'd like to set up unit testing, follow our guide on ["Unit Testing with Jest"](https://docs.expo.dev/develop/unit-testing/)
- Learn more about the TypeScript setup in this template in our guide on ["Using TypeScript"](https://docs.expo.dev/guides/typescript/)

## Learn more

To learn more about developing your project with Expo, look at the following resources:

- [Expo documentation](https://docs.expo.dev/): Learn fundamentals, or go into advanced topics with our [guides](https://docs.expo.dev/guides).
- [Learn Expo tutorial](https://docs.expo.dev/tutorial/introduction/): Follow a step-by-step tutorial where you'll create a project that runs on Android, iOS, and the web.

## Join the community

Join our community of developers creating universal apps.

- [Expo on GitHub](https://github.com/expo/expo): View our open source platform and contribute.
- [Discord community](https://chat.expo.dev): Chat with Expo users and ask questions.

## 백엔드 연결

휴대폰 또는 개발 PC가 EC2와 같은 Tailscale 네트워크에 연결돼 있어야 합니다.

```bash
npm run start
npm run android
npm run ios
npm run web
```

기본 설정으로 검색·추천은
Django `http://100.71.169.91:8000/api`, 로그인·게시판·저장 장소는 Spring
`http://100.71.169.91:8081/api`를 사용합니다.

다른 백엔드를 사용할 때만 `EXPO_PUBLIC_DJANGO_API_BASE_URL`과
`EXPO_PUBLIC_SPRING_API_BASE_URL` 환경변수로 주소를 덮어씁니다. API 주소가
`http://`일 때 Android와 iOS 개발 빌드의 cleartext 접속 설정도 자동으로
활성화됩니다. 공개 배포 전에 HTTPS 주소로 바꾸면 이 예외는 적용되지 않습니다.

연결 전 `npm run check:server`로 Django와 Spring의 health 응답을 확인할 수 있습니다.

## 모바일 빌드

네이티브 앱의 로그인 토큰은 `expo-secure-store`를 통해 Android Keystore와 iOS
Keychain에 보관합니다. 기존 개발 빌드의 AsyncStorage 토큰은 최초 실행 시 자동으로
이관됩니다. 웹 빌드는 브라우저 저장소를 계속 사용합니다.

`eas.json`에는 개발, 내부 테스트 APK, 스토어 배포 프로필이 준비돼 있습니다. 공개
빌드 전 EAS의 `preview`와 `production` 환경에 아래 값을 HTTPS 주소로 등록해야 합니다.

- `EXPO_PUBLIC_DJANGO_API_BASE_URL`
- `EXPO_PUBLIC_SPRING_API_BASE_URL`
- `EXPO_PUBLIC_KAKAO_MAP_EMBED_URL`

현재 Tailscale HTTP 주소는 로컬 개발용이며 스토어 배포 주소로 사용하지 않습니다.
