// 이 파일은 publication 목록 선택, 전체 삭제 확인과 삭제 결과 표시를 담당한다.
import { adminApiBasePath, api } from "./api.js";

// 고정된 관리자 화면 요소를 ID로 간결하게 조회한다.
const $ = (id) => document.getElementById(id);
let publications = [];

// 서버 문자열을 표 템플릿에 안전하게 삽입하도록 HTML 특수문자를 이스케이프한다.
function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

// 체크된 발간물 요소의 data 속성을 숫자 ID 목록으로 변환한다.
function selectedPublicationIds() {
  return [...document.querySelectorAll("[data-publication-id]:checked")]
    // 각 체크박스는 API 요청에 필요한 정수 발간물 ID 하나를 나타낸다.
    .map((checkbox) => Number(checkbox.dataset.publicationId));
}

// 현재 선택 수에 맞춰 전체 선택 상태와 삭제 버튼 활성화를 동기화한다.
function updateSelectionState() {
  const selectedIds = selectedPublicationIds();
  const checkboxes = [...document.querySelectorAll("[data-publication-id]")];
  $("selectedPublicationCount").textContent = selectedIds.length;
  $("deletePublications").disabled = selectedIds.length === 0;
  $("selectAllPublications").checked = checkboxes.length > 0 && selectedIds.length === checkboxes.length;
  $("selectAllPublications").indeterminate = selectedIds.length > 0 && selectedIds.length < checkboxes.length;
}

// 발간물 작업의 성공·실패 메시지를 접근 가능한 고정 영역에 표시한다.
function showMessage(message, type = "success") {
  const element = $("publicationMessage");
  element.hidden = false;
  element.className = `action-message action-message--${type}`;
  element.textContent = message;
}

// 발간물 목록을 선택 가능한 표 행으로 렌더링하고 선택 상태를 초기화한다.
function renderPublications(rows) {
  publications = rows;
  $("publicationList").innerHTML = rows.length
    // 각 발간물은 삭제 선택용 체크박스를 가진 한 표 행으로 렌더링된다.
    ? rows.map((publication) => `
      <tr>
        <td class="checkbox-cell"><input type="checkbox" data-publication-id="${escapeHtml(publication.pub_id)}" aria-label="${escapeHtml(publication.title)} 선택" /></td>
        <td>${escapeHtml(publication.pub_id)}</td>
        <td>${escapeHtml(publication.year)}</td>
        <td>${escapeHtml(publication.pub_no || "-")}</td>
        <td class="publication-title">${escapeHtml(publication.title)}</td>
      </tr>`).join("")
    : '<tr><td colspan="5" class="empty-table">등록된 publication이 없습니다.</td></tr>';
  $("selectAllPublications").checked = false;
  updateSelectionState();
}

// 프로필이 허용한 DB 대상만 선택 가능하도록 목록을 구성한다.
export function configurePublicationTargets(targets) {
  $("publicationTargetSelect").innerHTML = targets
    // 비활성 대상은 표시하되 사용자가 선택할 수 없게 한다.
    .map((target) => `<option value="${escapeHtml(target.id)}" ${target.enabled ? "" : "disabled"}>${escapeHtml(target.label)}${target.enabled ? "" : " (비활성)"}</option>`)
    .join("");
}

// 선택 DB의 발간물을 조회해 표를 갱신하고 오류는 화면 안에 표시한다.
export async function loadPublications() {
  $("publicationMessage").hidden = true;
  $("publicationList").innerHTML = '<tr><td colspan="5" class="empty-table">목록을 불러오는 중입니다.</td></tr>';
  try {
    const target = encodeURIComponent($("publicationTargetSelect").value);
    const response = await api(`${adminApiBasePath}/publications?target=${target}`);
    renderPublications(await response.json());
  } catch (error) {
    renderPublications([]);
    showMessage(`발간물 목록 조회 실패: ${error.message}`, "error");
  }
}

// 명시적 확인 후 선택 발간물과 모든 종속 데이터를 삭제하고 결과 건수를 표시한다.
async function deleteSelectedPublications() {
  const pubIds = selectedPublicationIds();
  if (!pubIds.length) return;
  // 확인창에는 현재 선택 ID와 일치하는 발간물만 포함한다.
  const selected = publications.filter((publication) => pubIds.includes(publication.pub_id));
  // 각 선택 항목을 사람이 재확인할 수 있는 연도·제목 한 줄로 만든다.
  const description = selected.map((publication) => `${publication.year} ${publication.title}`).join("\n");
  if (!window.confirm(`다음 발간물과 연결된 모든 데이터를 삭제합니다.\n\n${description}\n\n이 작업은 되돌릴 수 없습니다.`)) return;

  const button = $("deletePublications");
  button.disabled = true;
  button.textContent = "삭제 중...";
  try {
    const response = await api(`${adminApiBasePath}/publications`, {
      method: "DELETE",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        pub_ids: pubIds,
        target: $("publicationTargetSelect").value,
      }),
    });
    const result = await response.json();
    const counts = result.deleted_counts;
    await loadPublications();
    showMessage(
      `${counts.publications}개 발간물 삭제 완료 · 통계 ${counts.statistics} · 표 ${counts.stat_tables} · 주석 ${counts.footnotes} · 연락처 ${counts.contacts}`,
    );
  } catch (error) {
    showMessage(`삭제 실패: ${error.message}`, "error");
  } finally {
    button.textContent = "선택한 데이터 삭제";
    updateSelectionState();
  }
}

// 발간물 관리 화면의 조회·선택·삭제 이벤트를 한 번 연결한다.
export function initializePublicationScreen() {
  $("refreshPublications").addEventListener("click", loadPublications);
  $("publicationTargetSelect").addEventListener("change", loadPublications);
  // 전체 선택 변경을 현재 목록의 모든 체크박스에 전파한다.
  $("selectAllPublications").addEventListener("change", (event) => {
    // 개별 체크박스가 전체 선택 값과 동일하도록 갱신한다.
    document.querySelectorAll("[data-publication-id]").forEach((checkbox) => {
      checkbox.checked = event.target.checked;
    });
    updateSelectionState();
  });
  $("publicationList").addEventListener("change", updateSelectionState);
  $("deletePublications").addEventListener("click", deleteSelectedPublications);
}
