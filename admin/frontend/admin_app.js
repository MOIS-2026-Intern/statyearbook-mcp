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
  ["schema_ddl", "Schema 적용", "db/schema.sql 실행 및 로컬·운영 공통 DDL 보존"],
  ["load_dml", "적재 SQL 생성", "누적 적재 DML 보존"],
  ["load_db", "DB 적재", "선택 연도 트랜잭션 실행"],
  ["embedding_dml", "임베딩 SQL 생성", "제목 벡터를 DML 산출물로 보존"],
  ["embedding_db", "임베딩 DB 적재", "생성된 임베딩 DML 실행"],
  ["table_embedding_dml", "표 검색 임베딩 생성", "컬럼·분류 검색 벡터를 DML 산출물로 보존"],
  ["table_embedding_db", "표 검색 임베딩 적재", "생성된 표 검색 임베딩 DML 실행"],
  ["verify", "결과 검증", "건수·모델 profile 확인"],
];
const artifactLabels = { parsed_json:"파싱 JSON", review_markdown:"검수 Markdown", schema_ddl:"Schema SQL", load_dml:"적재 SQL", embedding_dml:"제목 임베딩 SQL", table_embedding_dml:"표 검색 임베딩 SQL" };
let currentJobId = null;
let pollTimer = null;
const $ = (id) => document.getElementById(id);

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

function renderStages(job) {
  const currentIndex = ingestionStages.findIndex(([id]) => id === job?.stage);
  $("stageList").innerHTML = ingestionStages.map(([id, title, detail], index) => {
    const done = job?.status === "completed" || index < currentIndex;
    const active = job?.status === "running" && index === currentIndex;
    return `<li class="stage ${done ? "stage--done" : ""} ${active ? "stage--active" : ""}"><span class="stage-dot">${done ? "✓" : index + 1}</span><div><strong>${title}</strong><span>${detail}</span></div></li>`;
  }).join("");
}

function statusLabel(status) { return ({ queued:"대기", running:"진행 중", completed:"완료", failed:"실패" })[status] || "대기"; }
function renderJob(job) {
  currentJobId = job.job_id;
  $("progressValue").textContent = `${job.progress}%`;
  $("progressBar").style.width = `${job.progress}%`;
  $("progressMessage").textContent = job.message;
  $("statusBadge").textContent = statusLabel(job.status);
  $("statusBadge").className = `status-badge status-badge--${job.status}`;
  renderStages(job);
  $("eventLog").innerHTML = job.events?.length ? job.events.slice().reverse().map((event) => `<div class="event event--${event.level}"><strong>${event.message}</strong><span>${event.stage} · ${new Date(event.created_at).toLocaleString()}</span></div>`).join("") : `<p class="muted">아직 기록된 이벤트가 없습니다.</p>`;
  const result = job.result || {};
  $("resultGrid").innerHTML = Object.keys(result).length ? [
    [result.statistics_count ?? 0, "통계 단위"], [result.table_count ?? 0, "원자료 표"],
    [result.verified_embedding_count ?? 0, "제목 임베딩"], [result.verified_table_embedding_count ?? 0, "표 검색 임베딩"],
    [result.publication_year ?? "-", "발간연도"],
  ].map(([value,label]) => `<div class="result-item"><strong>${value}</strong><span>${label}</span></div>`).join("") : `<p class="muted">완료 후 적재 건수가 표시됩니다.</p>`;
  const artifacts = job.artifacts || {};
  $("artifactList").innerHTML = Object.keys(artifacts).length ? Object.keys(artifacts).map((name) => `<button class="artifact-button" data-artifact="${name}"><span>${artifactLabels[name] || name}</span><b>↓</b></button>`).join("") : `<p class="muted">생성된 파일이 없습니다.</p>`;
  document.querySelectorAll("[data-artifact]").forEach((button) => button.addEventListener("click", () => downloadArtifact(job.job_id, button.dataset.artifact)));
  $("errorDetails").hidden = !job.error;
  $("errorText").textContent = job.error || "";
  if (["completed", "failed"].includes(job.status)) { clearInterval(pollTimer); pollTimer = null; $("submitButton").disabled = false; loadJobs(); }
}

async function loadJob(jobId) { const job = await (await api(`${adminApiBasePath}/jobs/${jobId}`)).json(); renderJob(job); }
async function loadJobs() {
  try {
    const jobs = await (await api(`${adminApiBasePath}/jobs`)).json();
    $("jobList").innerHTML = jobs.length ? jobs.map((job) => `<button class="job-item ${job.job_id === currentJobId ? "job-item--active" : ""}" data-job="${job.job_id}"><strong>${job.options?.year || "-"} ${job.options?.original_filename || "통계연보"}</strong><span>${statusLabel(job.status)} · ${job.progress}%</span></button>`).join("") : `<p class="muted">아직 실행한 작업이 없습니다.</p>`;
    document.querySelectorAll("[data-job]").forEach((button) => button.addEventListener("click", () => {
      showAdminView("load");
      loadJob(button.dataset.job);
    }));
  } catch (error) { $("jobList").innerHTML = `<p class="muted">${error.message}</p>`; }
}

async function downloadArtifact(jobId, name) {
  const response = await api(`${adminApiBasePath}/jobs/${jobId}/artifacts/${name}`);
  const blob = await response.blob(); const url = URL.createObjectURL(blob);
  const link = document.createElement("a"); link.href = url; link.download = response.headers.get("content-disposition")?.match(/filename="?([^";]+)/)?.[1] || name; link.click(); URL.revokeObjectURL(url);
}

function renderOptions(payload) {
  $("maxUpload").textContent = payload.max_upload_mb;
  $("targetSelect").innerHTML = payload.targets.map((item) => `<option value="${item.id}" ${item.enabled ? "" : "disabled"}>${item.label}${item.enabled ? "" : " (비활성)"}</option>`).join("");
  $("loadModeSelect").innerHTML = payload.load_modes.map((item) => `<option value="${item.id}">${item.label}</option>`).join("");
  $("embeddingOptions").innerHTML = payload.embedding_models.map((item, index) => `<label class="choice"><input type="radio" name="embedding_model" value="${item.id}" ${index === 0 ? "checked" : ""} ${item.enabled ? "" : "disabled"}/><strong>${item.label}</strong><small>${item.description}</small></label>`).join("");
  configurePublicationTargets(payload.targets);
}

async function initialize() {
  try { renderOptions(await (await api(`${adminApiBasePath}/options`)).json()); await loadJobs(); renderStages(null); }
  catch (error) { $("formError").hidden = false; $("formError").textContent = `관리자 API 연결 실패: ${error.message}`; }
}

$("yearInput").addEventListener("input", () => { if (/^\d{4} 행정안전통계연보$/.test($("titleInput").value)) $("titleInput").value = `${$("yearInput").value} 행정안전통계연보`; });
$("loadModeSelect").addEventListener("change", () => { $("replaceWarning").hidden = $("loadModeSelect").value !== "replace"; });
$("fileInput").addEventListener("change", () => { $("fileLabel").textContent = $("fileInput").files[0]?.name || "파일을 끌어놓거나 클릭해 선택"; });
$("dropzone").addEventListener("dragover", (event) => { event.preventDefault(); $("dropzone").classList.add("dropzone--active"); });
$("dropzone").addEventListener("dragleave", () => $("dropzone").classList.remove("dropzone--active"));
$("dropzone").addEventListener("drop", (event) => { event.preventDefault(); $("dropzone").classList.remove("dropzone--active"); if (event.dataTransfer.files.length) { $("fileInput").files = event.dataTransfer.files; $("fileLabel").textContent = event.dataTransfer.files[0].name; } });
$("showLoadView").addEventListener("click", () => showAdminView("load"));
$("showPublicationView").addEventListener("click", () => showAdminView("publications"));
$("refreshJobs").addEventListener("click", loadJobs);
$("tokenInput").addEventListener("change", () => { saveAdminToken($("tokenInput").value); initialize(); });
$("ingestionForm").addEventListener("submit", async (event) => {
  event.preventDefault(); $("formError").hidden = true; $("submitButton").disabled = true;
  const form = new FormData(); const file = $("fileInput").files[0];
  if (!file) { $("formError").hidden = false; $("formError").textContent = "HWPX 파일을 선택하세요."; $("submitButton").disabled = false; return; }
  form.append("file", file); form.append("year", $("yearInput").value); form.append("title", $("titleInput").value); form.append("pub_no", $("pubNoInput").value); form.append("target", $("targetSelect").value); form.append("load_mode", $("loadModeSelect").value); form.append("embedding_model", document.querySelector("input[name=embedding_model]:checked").value);
  try { const job = await (await api(`${adminApiBasePath}/jobs`, { method:"POST", body:form })).json(); renderJob(job); await loadJobs(); pollTimer = setInterval(() => loadJob(job.job_id).catch(console.error), 1000); }
  catch (error) { $("formError").hidden = false; $("formError").textContent = error.message; $("submitButton").disabled = false; }
});

restoreAdminToken();
initializePublicationScreen();
initialize();
