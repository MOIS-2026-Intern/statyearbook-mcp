// 이 파일은 관리자 API prefix, 인증 토큰과 공통 HTTP 오류 처리를 제공한다.
export const adminApiBasePath = "/api/admin";

// 입력값을 우선해 현재 요청에 사용할 관리자 토큰을 결정한다.
function token() {
  return document.getElementById("tokenInput").value
    || sessionStorage.getItem("statyearbookAdminToken")
    || "";
}

// 현재 탭 세션에 저장된 토큰을 관리자 입력란에 복원한다.
export function restoreAdminToken() {
  document.getElementById("tokenInput").value = sessionStorage.getItem("statyearbookAdminToken") || "";
}

// 사용자가 바꾼 관리자 토큰을 현재 탭 세션 동안만 저장한다.
export function saveAdminToken(value) {
  sessionStorage.setItem("statyearbookAdminToken", value);
}

// 인증 헤더를 공통 적용하고 비정상 HTTP 응답을 사용자용 오류로 변환한다.
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
