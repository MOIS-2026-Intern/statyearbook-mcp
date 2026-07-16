// 이 파일은 publication 목록 선택, 전체 삭제 확인과 삭제 결과 표시를 담당한다.
import { adminApiBasePath, api } from "./api.js";

const $ = (id) => document.getElementById(id);
let publications = [];

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function selectedPublicationIds() {
  return [...document.querySelectorAll("[data-publication-id]:checked")]
    .map((checkbox) => Number(checkbox.dataset.publicationId));
}

function updateSelectionState() {
  const selectedIds = selectedPublicationIds();
  const checkboxes = [...document.querySelectorAll("[data-publication-id]")];
  $("selectedPublicationCount").textContent = selectedIds.length;
  $("deletePublications").disabled = selectedIds.length === 0;
  $("selectAllPublications").checked = checkboxes.length > 0 && selectedIds.length === checkboxes.length;
  $("selectAllPublications").indeterminate = selectedIds.length > 0 && selectedIds.length < checkboxes.length;
}

function showMessage(message, type = "success") {
  const element = $("publicationMessage");
  element.hidden = false;
  element.className = `action-message action-message--${type}`;
  element.textContent = message;
}

function renderPublications(rows) {
  publications = rows;
  $("publicationList").innerHTML = rows.length
    ? rows.map((publication) => `
      <tr>
        <td class="checkbox-cell"><input type="checkbox" data-publication-id="${publication.pub_id}" aria-label="${escapeHtml(publication.title)} 선택" /></td>
        <td>${publication.pub_id}</td>
        <td>${publication.year}</td>
        <td>${escapeHtml(publication.pub_no || "-")}</td>
        <td class="publication-title">${escapeHtml(publication.title)}</td>
      </tr>`).join("")
    : '<tr><td colspan="5" class="empty-table">등록된 publication이 없습니다.</td></tr>';
  $("selectAllPublications").checked = false;
  updateSelectionState();
}

export function configurePublicationTargets(targets) {
  $("publicationTargetSelect").innerHTML = targets
    .map((target) => `<option value="${target.id}" ${target.enabled ? "" : "disabled"}>${escapeHtml(target.label)}${target.enabled ? "" : " (비활성)"}</option>`)
    .join("");
}

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

async function deleteSelectedPublications() {
  const pubIds = selectedPublicationIds();
  if (!pubIds.length) return;
  const selected = publications.filter((publication) => pubIds.includes(publication.pub_id));
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
      `${counts.publications}개 발간물 삭제 완료 · 통계 ${counts.statistics} · 표 ${counts.stat_tables} · 주석 ${counts.footnotes} · 연락처 ${counts.contacts} · 이미지 ${counts.statistic_images}`,
    );
  } catch (error) {
    showMessage(`삭제 실패: ${error.message}`, "error");
  } finally {
    button.textContent = "선택한 데이터 삭제";
    updateSelectionState();
  }
}

export function initializePublicationScreen() {
  $("refreshPublications").addEventListener("click", loadPublications);
  $("publicationTargetSelect").addEventListener("change", loadPublications);
  $("selectAllPublications").addEventListener("change", (event) => {
    document.querySelectorAll("[data-publication-id]").forEach((checkbox) => {
      checkbox.checked = event.target.checked;
    });
    updateSelectionState();
  });
  $("publicationList").addEventListener("change", updateSelectionState);
  $("deletePublications").addEventListener("click", deleteSelectedPublications);
}
