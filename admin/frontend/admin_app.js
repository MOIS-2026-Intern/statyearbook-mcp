// 이 파일은 관리자 화면 전환, 연보 업로드, 작업 polling과 결과 다운로드를 처리한다.
// 공통 API와 publication 삭제 화면을 조립하는 frontend 진입점이다.
import { adminApiBasePath, api, restoreAdminToken, saveAdminToken } from "./api.js";
import {
  configurePublicationTargets,
  initializePublicationScreen,
  loadPublications,
} from "./publications.js";

const ingestionStages = [
  ["validate", "파일 확인", "형식·대상 환경 검증"],
  ["parse", "구조 파싱", "JSON·검수 Markdown 생성"],
  ["load_dml", "적재 SQL 생성", "누적 적재 DML 보존"],
  ["load_db", "DB 적재", "선택 연도 트랜잭션 실행"],
  ["embedding_dml", "임베딩 SQL 생성", "제목 벡터를 DML 산출물로 보존"],
  ["embedding_db", "임베딩 DB 적재", "생성된 임베딩 DML 실행"],
  ["table_embedding_dml", "표 검색 임베딩 생성", "컬럼·분류 검색 벡터를 DML 산출물로 보존"],
  ["table_embedding_db", "표 검색 임베딩 적재", "생성된 표 검색 임베딩 DML 실행"],
  ["verify", "결과 검증", "건수·모델 profile 확인"],
];
const artifactLabels = { parsed_json:"파싱 JSON", review_markdown:"검수 Markdown", load_dml:"적재 SQL", embedding_dml:"제목 임베딩 SQL", table_embedding_dml:"표 검색 임베딩 SQL" };
let currentJobId = null;
let pollTimer = null;
// 고정된 관리자 화면 요소를 ID로 조회한다.
const $ = (id) => document.getElementById(id);

// 서버·사용자 입력을 HTML 텍스트와 따옴표 속성에 안전하게 삽입하도록 이스케이프한다.
function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (character) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    "\"": "&quot;",
    "'": "&#39;",
  })[character]);
}

// 적재와 발간물 관리 화면의 표시 상태와 탐색 강조를 함께 전환한다.
function showAdminView(view) {
  const showLoad = view === "load";
  $("loadView").hidden = !showLoad;
  $("publicationView").hidden = showLoad;
  $("showLoadView").classList.toggle("nav-item--active", showLoad);
  $("showPublicationView").classList.toggle("nav-item--active", !showLoad);
  $("pageTitle").textContent = showLoad ? "새 통계연보 적재" : "DB 통계연보 삭제";
  document.querySelector(".admin-shell").classList.toggle("admin-shell--management", !showLoad);
  if (!showLoad) loadPublications();
}

// 현재 작업 단계까지의 완료·진행 상태를 전체 파이프라인 목록에 표시한다.
function renderStages(job) {
  // 작업 단계 ID가 고정된 화면 단계 목록의 어느 위치인지 찾는다.
  const currentIndex = ingestionStages.findIndex(([id]) => id === job?.stage);
  // 각 단계는 작업 상태에 따라 완료 또는 활성 스타일을 얻는다.
  $("stageList").innerHTML = ingestionStages.map(([id, title, detail], index) => {
    const done = job?.status === "completed" || index < currentIndex;
    const active = job?.status === "running" && index === currentIndex;
    return `<li class="stage ${done ? "stage--done" : ""} ${active ? "stage--active" : ""}"><span class="stage-dot">${done ? "✓" : index + 1}</span><div><strong>${title}</strong><span>${detail}</span></div></li>`;
  }).join("");
}

// 저장된 작업 상태 코드를 화면에 표시할 한국어 라벨로 변환한다.
function statusLabel(status) { return ({ queued:"대기", running:"진행 중", completed:"완료", failed:"실패" })[status] || "대기"; }

// 단일 작업의 진행률, 이벤트, 결과와 다운로드 가능한 산출물을 모두 갱신한다.
function renderJob(job) {
  currentJobId = job.job_id;
  $("progressValue").textContent = `${job.progress}%`;
  $("progressBar").style.width = `${job.progress}%`;
  $("progressMessage").textContent = job.message;
  $("statusBadge").textContent = statusLabel(job.status);
  $("statusBadge").className = `status-badge status-badge--${job.status}`;
  renderStages(job);
  // 최신 이벤트가 위에 오도록 복사본을 뒤집어 시간·단계와 함께 렌더링한다.
  $("eventLog").innerHTML = job.events?.length ? job.events.slice().reverse().map((event) => `<div class="event event--${escapeHtml(event.level)}"><strong>${escapeHtml(event.message)}</strong><span>${escapeHtml(event.stage)} · ${escapeHtml(new Date(event.created_at).toLocaleString())}</span></div>`).join("") : `<p class="muted">아직 기록된 이벤트가 없습니다.</p>`;
  const result = job.result || {};
  $("resultGrid").innerHTML = Object.keys(result).length ? [
    [result.statistics_count ?? 0, "통계 단위"], [result.table_count ?? 0, "원자료 표"],
    [result.verified_embedding_count ?? 0, "제목 임베딩"], [result.verified_table_embedding_count ?? 0, "표 검색 임베딩"],
    [result.publication_year ?? "-", "발간연도"],
  // 결과 값을 동일한 수치·라벨 카드 형식으로 변환한다.
  ].map(([value,label]) => `<div class="result-item"><strong>${escapeHtml(value)}</strong><span>${escapeHtml(label)}</span></div>`).join("") : `<p class="muted">완료 후 적재 건수가 표시됩니다.</p>`;
  const artifacts = job.artifacts || {};
  // 등록된 산출물 키마다 사람이 읽을 수 있는 다운로드 버튼을 만든다.
  $("artifactList").innerHTML = Object.keys(artifacts).length ? Object.keys(artifacts).map((name) => `<button class="artifact-button" data-artifact="${escapeHtml(name)}"><span>${escapeHtml(artifactLabels[name] || name)}</span><b>↓</b></button>`).join("") : `<p class="muted">생성된 파일이 없습니다.</p>`;
  // 생성된 각 산출물 버튼에 현재 작업의 다운로드 동작을 연결한다.
  document.querySelectorAll("[data-artifact]").forEach((button) => {
    // 클릭한 버튼의 산출물 키만 다운로드 요청에 전달한다.
    button.addEventListener("click", () => downloadArtifact(job.job_id, button.dataset.artifact));
  });
  $("errorDetails").hidden = !job.error;
  $("errorText").textContent = job.error || "";
  if (["completed", "failed"].includes(job.status)) { clearInterval(pollTimer); pollTimer = null; $("submitButton").disabled = false; loadJobs(); }
}

// 단일 작업의 최신 상태를 조회해 현재 상세 화면에 반영한다.
async function loadJob(jobId) { const job = await (await api(`${adminApiBasePath}/jobs/${jobId}`)).json(); renderJob(job); }

// 최근 작업 목록을 조회하고 각 항목을 상세 화면 진입 버튼으로 구성한다.
async function loadJobs() {
  try {
    const jobs = await (await api(`${adminApiBasePath}/jobs`)).json();
    // 각 작업 요약을 현재 선택 표시가 포함된 탐색 버튼으로 렌더링한다.
    $("jobList").innerHTML = jobs.length ? jobs.map((job) => `<button class="job-item ${job.job_id === currentJobId ? "job-item--active" : ""}" data-job="${escapeHtml(job.job_id)}"><strong>${escapeHtml(job.options?.year || "-")} ${escapeHtml(job.options?.original_filename || "통계연보")}</strong><span>${escapeHtml(statusLabel(job.status))} · ${escapeHtml(job.progress)}%</span></button>`).join("") : `<p class="muted">아직 실행한 작업이 없습니다.</p>`;
    // 작업 목록의 각 버튼에 상세 조회 진입 동작을 연결한다.
    document.querySelectorAll("[data-job]").forEach((button) => {
      // 클릭 시 적재 화면으로 이동해 해당 작업의 최신 상태를 불러온다.
      button.addEventListener("click", () => {
        showAdminView("load");
        loadJob(button.dataset.job);
      });
    });
  } catch (error) { $("jobList").innerHTML = `<p class="muted">${escapeHtml(error.message)}</p>`; }
}

// 인증된 API에서 산출물을 받아 임시 object URL로 브라우저 다운로드를 시작한다.
async function downloadArtifact(jobId, name) {
  const response = await api(`${adminApiBasePath}/jobs/${jobId}/artifacts/${name}`);
  const blob = await response.blob(); const url = URL.createObjectURL(blob);
  const link = document.createElement("a"); link.href = url; link.download = response.headers.get("content-disposition")?.match(/filename="?([^";]+)/)?.[1] || name; link.click(); URL.revokeObjectURL(url);
}

// 서버가 허용한 업로드 제한, DB, 적재 모드와 모델 선택지를 화면에 반영한다.
function renderOptions(payload) {
  $("maxUpload").textContent = payload.max_upload_mb;
  // 비활성 DB 대상은 보이지만 선택되지 않도록 option으로 변환한다.
  $("targetSelect").innerHTML = payload.targets.map((item) => `<option value="${escapeHtml(item.id)}" ${item.enabled ? "" : "disabled"}>${escapeHtml(item.label)}${item.enabled ? "" : " (비활성)"}</option>`).join("");
  // 적재 정책은 서버가 제공한 순서 그대로 선택 option으로 만든다.
  $("loadModeSelect").innerHTML = payload.load_modes.map((item) => `<option value="${escapeHtml(item.id)}">${escapeHtml(item.label)}</option>`).join("");
  // 첫 활성 모델을 기본으로 보여주는 라디오 선택지를 렌더링한다.
  $("embeddingOptions").innerHTML = payload.embedding_models.map((item, index) => `<label class="choice"><input type="radio" name="embedding_model" value="${escapeHtml(item.id)}" ${index === 0 ? "checked" : ""} ${item.enabled ? "" : "disabled"}/><strong>${escapeHtml(item.label)}</strong><small>${escapeHtml(item.description)}</small></label>`).join("");
  configurePublicationTargets(payload.targets);
}

// 서버 옵션과 기존 작업을 불러와 관리자 화면의 초기 상태를 구성한다.
async function initialize() {
  try { renderOptions(await (await api(`${adminApiBasePath}/options`)).json()); await loadJobs(); renderStages(null); }
  catch (error) { $("formError").hidden = false; $("formError").textContent = `관리자 API 연결 실패: ${error.message}`; }
}

// 기본 형식의 제목만 연도 입력에 맞춰 자동 갱신한다.
$("yearInput").addEventListener("input", () => { if (/^\d{4} 행정안전통계연보$/.test($("titleInput").value)) $("titleInput").value = `${$("yearInput").value} 행정안전통계연보`; });
// 교체 적재가 선택된 동안만 데이터 삭제 경고를 노출한다.
$("loadModeSelect").addEventListener("change", () => { $("replaceWarning").hidden = $("loadModeSelect").value !== "replace"; });
// 파일 선택 결과를 dropzone 라벨에 즉시 표시한다.
$("fileInput").addEventListener("change", () => { $("fileLabel").textContent = $("fileInput").files[0]?.name || "파일을 끌어놓거나 클릭해 선택"; });
// 파일을 끌고 있는 동안 기본 브라우저 동작을 막고 dropzone을 강조한다.
$("dropzone").addEventListener("dragover", (event) => { event.preventDefault(); $("dropzone").classList.add("dropzone--active"); });
// 포인터가 떠나면 dropzone 강조 상태를 제거한다.
$("dropzone").addEventListener("dragleave", () => $("dropzone").classList.remove("dropzone--active"));
// 드롭된 파일 목록을 업로드 입력에 전달하고 선택 파일명을 표시한다.
$("dropzone").addEventListener("drop", (event) => { event.preventDefault(); $("dropzone").classList.remove("dropzone--active"); if (event.dataTransfer.files.length) { $("fileInput").files = event.dataTransfer.files; $("fileLabel").textContent = event.dataTransfer.files[0].name; } });
// 적재 탐색 버튼은 업로드·작업 화면으로 전환한다.
$("showLoadView").addEventListener("click", () => showAdminView("load"));
// 발간물 탐색 버튼은 DB 발간물 관리 화면으로 전환한다.
$("showPublicationView").addEventListener("click", () => showAdminView("publications"));
$("refreshJobs").addEventListener("click", loadJobs);
// 새 토큰을 저장한 뒤 해당 자격 증명으로 화면 데이터를 다시 불러온다.
$("tokenInput").addEventListener("change", () => { saveAdminToken($("tokenInput").value); initialize(); });
// 제출값을 multipart 요청으로 만들고 생성된 작업의 polling을 시작한다.
$("ingestionForm").addEventListener("submit", async (event) => {
  event.preventDefault(); $("formError").hidden = true; $("submitButton").disabled = true;
  const form = new FormData(); const file = $("fileInput").files[0];
  if (!file) { $("formError").hidden = false; $("formError").textContent = "HWPX 파일을 선택하세요."; $("submitButton").disabled = false; return; }
  form.append("file", file); form.append("year", $("yearInput").value); form.append("title", $("titleInput").value); form.append("pub_no", $("pubNoInput").value); form.append("target", $("targetSelect").value); form.append("load_mode", $("loadModeSelect").value); form.append("embedding_model", document.querySelector("input[name=embedding_model]:checked").value);
  // 작업이 완료 또는 실패할 때까지 상세 상태를 1초 간격으로 갱신한다.
  try { const job = await (await api(`${adminApiBasePath}/jobs`, { method:"POST", body:form })).json(); renderJob(job); await loadJobs(); pollTimer = setInterval(() => loadJob(job.job_id).catch(console.error), 1000); }
  catch (error) { $("formError").hidden = false; $("formError").textContent = error.message; $("submitButton").disabled = false; }
});

restoreAdminToken();
initializePublicationScreen();
initialize();
