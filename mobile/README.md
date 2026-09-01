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

## EC2 백엔드 연결

휴대폰 또는 개발 PC가 EC2와 같은 Tailscale 네트워크에 연결돼 있어야 합니다.

```bash
npm run start:server
npm run android:server
npm run ios:server
npm run web:server
```

위 명령은 `.env.server`의 주소를 Expo 프로세스에 주입합니다. 검색·추천은
Django `http://100.71.169.91:8000/api`, 로그인·게시판·저장 장소는 Spring
`http://100.71.169.91:8081/api`를 사용합니다. 기본 `npm run start`는 기존처럼
에뮬레이터 또는 로컬 PC의 백엔드를 사용합니다.

현재 서버가 Tailscale 내부 HTTP이므로 `*:server` 명령으로 실행할 때만 Android와
iOS 개발 빌드에서 cleartext 접속을 허용합니다. 기본 실행과 외부 공개 빌드에는 이
예외가 적용되지 않습니다. Expo 웹은 기본 `localhost:8081` origin을 사용하므로
서버 CORS도 해당 origin을 허용해야 합니다.

연결 전 `npm run check:server`로 Django와 Spring의 health 응답을 확인할 수 있습니다.
