const { withAppBuildGradle, withGradleProperties, withDangerousMod } = require("expo/config-plugins");
const fs = require("node:fs");
const path = require("node:path");

// Applied by prebuild, including EAS builds that do not upload android/.
function withAndroidReleaseOptimization(config) {
  config = withGradleProperties(config, (mod) => {
    for (const key of [
      "android.enableMinifyInReleaseBuilds",
      "android.enableShrinkResourcesInReleaseBuilds",
      "edgeToEdgeEnabled",
    ]) {
      mod.modResults = mod.modResults.filter(
        (item) => item.type !== "property" || item.key !== key,
      );
      mod.modResults.push({ type: "property", key, value: "true" });
    }
    return mod;
  });
  config = withDangerousMod(config, ["android", async (mod) => {
    const root = mod.modRequest.projectRoot;
    const rnVersion = require(require.resolve("react-native/package.json", { paths: [root] })).version;
    if (rnVersion !== "0.86.2") {
      throw new Error("Revalidate the native Window API guard before changing React Native " + rnVersion);
    }
    const buildSrc = path.join(mod.modRequest.platformProjectRoot, "buildSrc");
    const source = path.join(buildSrc, "src/main/java/lifemap/build");
    fs.mkdirSync(source, { recursive: true });
    fs.copyFileSync(path.join(__dirname, "android-api-guards/ReactNativeWindowApiGuard.java"),
      path.join(source, "ReactNativeWindowApiGuard.java"));
    fs.writeFileSync(path.join(buildSrc, "build.gradle"), `plugins { id 'java' }
repositories { google(); mavenCentral() }
dependencies {
    implementation 'com.android.tools.build:gradle-api:8.12.0'
    implementation 'org.ow2.asm:asm:9.8'
}
`);
    return mod;
  }]);
  return withAppBuildGradle(config, (mod) => {
    if (mod.modResults.language !== "groovy") {
      throw new Error("Android release optimization requires the Expo Groovy template");
    }
    mod.modResults.contents = mod.modResults.contents.replace(
      /getDefaultProguardFile\(["']proguard-android\.txt["']\)/g,
      'getDefaultProguardFile("proguard-android-optimize.txt")',
    );
    if (!mod.modResults.contents.includes("proguard-android-optimize.txt")) {
      throw new Error("Android release optimization could not find the ProGuard configuration");
    }
    // Material 1.14 includes the upstream Android 35+ edge-to-edge API guards.
    // Use a constraint instead of overriding unrelated transitive dependencies.
    if (!mod.modResults.contents.includes('com.google.android.material:material:1.14.0')) {
      mod.modResults.contents += `
dependencies {
    constraints {
        implementation("com.google.android.material:material:1.14.0") {
            because("Use the upstream Android 35+ edge-to-edge compatibility fix")
        }
    }
}
`;
    }
    if (!mod.modResults.contents.includes("lifemap.build.ReactNativeWindowApiGuard")) {
      mod.modResults.contents += `
// Android 35+ migration for the pinned RN binary; retains Android 24-34 behavior.
androidComponents {
    onVariants(selector().all()) { variant ->
        variant.instrumentation.transformClassesWith(
            lifemap.build.ReactNativeWindowApiGuard,
            com.android.build.api.instrumentation.InstrumentationScope.ALL) {}
        variant.instrumentation.setAsmFramesComputationMode(
            com.android.build.api.instrumentation.FramesComputationMode.COMPUTE_FRAMES_FOR_INSTRUMENTED_METHODS)
    }
}
`;
    }
    if (process.platform === "win32" && !mod.modResults.contents.includes('rootProject.file("../../.cxx-build")')) {
      mod.modResults.contents += `
// Shorten the native staging root so CMake can hash external source paths.
android {
    externalNativeBuild {
        cmake { buildStagingDirectory = rootProject.file("../../.cxx-build").canonicalFile }
    }
}
`;
    }
    return mod;
  });
}

module.exports = withAndroidReleaseOptimization;
