// 이 파일은 관리자 API prefix, 인증 토큰과 공통 HTTP 오류 처리를 제공한다.
export const adminApiBasePath = "/api/admin";

function token() {
  return document.getElementById("tokenInput").value
    || localStorage.getItem("statyearbookAdminToken")
    || "";
}

export function restoreAdminToken() {
  document.getElementById("tokenInput").value = localStorage.getItem("statyearbookAdminToken") || "";
}

export function saveAdminToken(value) {
  localStorage.setItem("statyearbookAdminToken", value);
}

export async function api(path, init = {}) {
  const headers = new Headers(init.headers || {});
  if (token()) headers.set("X-Admin-Token", token());
  const response = await fetch(path, { ...init, headers });
  if (!response.ok) {
    let message = `${response.status} ${response.statusText}`;
    try {
      const payload = await response.json();
      message = payload.detail || message;
    } catch {}
    throw new Error(message);
  }
  return response;
}
