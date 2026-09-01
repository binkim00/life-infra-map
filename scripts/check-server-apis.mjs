const serverHost = process.env.LIFE_INFRA_SERVER_HOST || "100.71.169.91";

const services = [
  {
    name: "Django API",
    url: `http://${serverHost}:8000/api/recommendations/health/`,
  },
  {
    name: "Spring API",
    url: `http://${serverHost}:8081/api/health`,
  },
];

let failed = false;

for (const service of services) {
  try {
    const response = await fetch(service.url, {
      signal: AbortSignal.timeout(10_000),
    });
    console.log(`${service.name}: ${response.status} ${service.url}`);
    if (!response.ok) failed = true;
  } catch (error) {
    failed = true;
    console.error(`${service.name}: 연결 실패 (${error.message})`);
  }
}

if (failed) {
  console.error("Tailscale 연결과 EC2 서비스 상태를 확인하세요.");
  process.exitCode = 1;
}
