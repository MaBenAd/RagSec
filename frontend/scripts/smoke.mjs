const frontendUrl = process.env.FRONTEND_URL || "http://127.0.0.1:3000";
const backendUrl = process.env.BACKEND_URL || "http://127.0.0.1:8000";
const stamp = Date.now();
const email = `smoke.${stamp}@usms.ac.ma`;
const password = "SmokePass123!";

const checks = [];

async function check(name, run) {
  try {
    const detail = await run();
    checks.push({ name, ok: true, detail });
  } catch (error) {
    checks.push({ name, ok: false, detail: error?.message || String(error) });
  }
}

function expectStatus(response, expected) {
  if (!expected.includes(response.status)) {
    throw new Error(`HTTP ${response.status}, expected ${expected.join("/")}`);
  }
}

await check("backend health", async () => {
  const response = await fetch(`${backendUrl}/healthz`);
  expectStatus(response, [200]);
  return await response.text();
});

await check("login page", async () => {
  const response = await fetch(`${frontendUrl}/login`, { redirect: "manual" });
  expectStatus(response, [200]);
  return "reachable";
});

for (const path of ["/chat", "/admin", "/profile"]) {
  await check(`protected redirect ${path}`, async () => {
    const response = await fetch(`${frontendUrl}${path}`, { redirect: "manual" });
    expectStatus(response, [307, 308]);
    return response.headers.get("location") || "redirect";
  });
}

let token = "";
let conversationId = null;

await check("student register", async () => {
  const response = await fetch(`${backendUrl}/api/v1/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      email,
      password,
      class_label: null,
      language: "fr",
      accepted_privacy: true,
    }),
  });
  expectStatus(response, [201]);
  const data = await response.json();
  token = data.access_token;
  return data.user.email;
});

await check("student chat", async () => {
  const response = await fetch(`${backendUrl}/api/v1/chat`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ question: "Bonjour", class_label: null }),
  });
  expectStatus(response, [200]);
  const data = await response.json();
  conversationId = data.conversation_id;
  if (!data.answer || !conversationId) throw new Error("missing chat answer or conversation id");
  return `conversation ${conversationId}`;
});

await check("conversation messages", async () => {
  const response = await fetch(`${backendUrl}/api/v1/conversations/${conversationId}/messages`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  expectStatus(response, [200]);
  const data = await response.json();
  if (!Array.isArray(data.messages) || data.messages.length < 2) throw new Error("missing persisted messages");
  return `${data.messages.length} messages`;
});

await check("cleanup smoke account", async () => {
  const response = await fetch(`${backendUrl}/api/v1/auth/me`, {
    method: "DELETE",
    headers: { Authorization: `Bearer ${token}` },
  });
  expectStatus(response, [200]);
  return "deleted";
});

for (const item of checks) {
  console.log(`${item.ok ? "PASS" : "FAIL"} | ${item.name} | ${item.detail}`);
}

if (checks.some((item) => !item.ok)) {
  process.exit(1);
}
