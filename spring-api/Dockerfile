FROM eclipse-temurin:21-jdk-jammy AS build

WORKDIR /workspace

# The production EC2 is intentionally small. Keep Gradle from exhausting the
# host while the already-running database, workers, Django, and MinIO stay up.
ENV GRADLE_OPTS="-Dorg.gradle.jvmargs=-Xmx512m -Dorg.gradle.workers.max=1"

COPY gradlew gradlew.bat build.gradle settings.gradle ./
COPY gradle ./gradle
RUN chmod +x gradlew && ./gradlew dependencies --no-daemon --max-workers=1

COPY src ./src
RUN ./gradlew bootJar --no-daemon --max-workers=1

FROM eclipse-temurin:21-jre-jammy

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --system --uid 10001 --create-home app

WORKDIR /app
COPY --from=build /workspace/build/libs/*.jar /app/app.jar

USER app
EXPOSE 8081
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
