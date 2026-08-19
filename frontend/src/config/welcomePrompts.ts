import type { PublicationScope } from "../types/chat";

export interface WelcomePrompt {
  // 화면에는 명사형 요약을 보여주고, 눌렀을 때는 문장형 질의를 그대로 보낸다.
  label: string;
  query: string;
}

export interface WelcomeContent {
  // 제목에서 색으로 강조할 발간물 이름과 뒤에 붙는 조사를 나눠 둔다.
  titleName: string;
  titleParticle: string;
  prompts: WelcomePrompt[];
}

// 조회 범위마다 첫 화면의 제목과 예시 질의를 다르게 보여준다.
export const WELCOME_CONTENT: Record<PublicationScope, WelcomeContent> = {
  all: {
    titleName: "통계 발간물",
    titleParticle: "을",
    prompts: [
      {
        label: "중앙행정기관 공공데이터 활용 건수 추이 시각화",
        query: "중앙행정기관의 공공데이터 활용 건수 추이를 시각화 해줘",
      },
      { label: "승강기 안전사고 통계 정리", query: "승강기 안전사고 통계에 대해서 정리해줘" },
      { label: "행정안전부 공무원 수 정리", query: "행정안전부 공무원 수에 대해 정리해줘" },
      { label: "검색 가능한 전체 발간물 목록", query: "현재 검색 가능한 전체 발간물 리스트 알려줘" },
      { label: "주민등록 인구 추이", query: "주민등록 인구 추이 알려줘" },
      { label: "최근 물놀이 안전사고 통계", query: "최근 물놀이 안전사고 관련 통계 정리해줘" },
    ],
  },
  yearbook: {
    titleName: "행정안전통계연보",
    titleParticle: "를",
    prompts: [
      { label: "26년판 통계 자료 제공 부서 수", query: "26년 판에 통계 자료를 제공한 부서는 총 몇곳이야?" },
      { label: "국정자원 담당 통계 목록", query: "국정자원에서 담당한 통계는 어떤게 있니?" },
      { label: "모바일 신분증 활용처 증감 추이 시각화", query: "모바일 신분증 활용처 증감 추이 시각화해줘" },
      { label: "주민대피시설 수용률 최저 지역", query: "주민대피시설 수용률이 가장 낮은 지역은 어디야?" },
      { label: "정보공개 청구 전부·부분·비공개 비율", query: "정보공개 청구 전부·부분·비공개 비율을 알려줘" },
      { label: "서울 재난 유형별 재산 피해", query: "서울의 재난으로 인한 재산 피해를 각 재난 별로 알려줘" },
    ],
  },
  major_statistics: {
    titleName: "주요통계집",
    titleParticle: "을",
    prompts: [
      { label: "지자체별 마을기업 현황", query: "각 지자체별 마을 기업 현황 알려줘" },
      { label: "시도별 민방위 사이렌 보유 개수", query: "시도별로 민방위 사이렌 보유 개수 알려줘" },
      { label: "서울시 안전신문고 신고 건수 추이", query: "서울시의 안전신문고 신고 건수 추이 알려줘" },
    ],
  },
};
