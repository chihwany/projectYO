# Figma 와이어프레임 정보

## Figma 파일

- **파일명**: projectYO
- **URL**: https://www.figma.com/design/LnFgPrgTDokH3FfjGJ4hqB/projectYO
- **fileKey**: `LnFgPrgTDokH3FfjGJ4hqB`
- **Page**: Page 1 (nodeId: `0:1`)

---

## 프레임 목록

| 프레임 | Node ID | 화면 설명 |
|---|---|---|
| 01_daangn_tab | `1:357` | 탭1: 당근 검색 - 구/군 레벨 지역 선택 + 하위 동 전체 통합 검색 |
| 02_market_tab | `1:180` | 탭2: 매물 검색 - 번개장터 + 중고나라 통합 검색 (플랫폼 구분 없음) |
| 03_alerts_tab | `1:238` | 탭3: 알림 이력 - 읽음/미읽음 구분, 날짜별 그룹핑, 미읽음 뱃지 |
| 04_settings_tab | `1:304` | 탭4: 설정 - 프로필, 알림 키워드, 알림 설정(수신/방해금지/진동/사운드), 기타 |
| 05_login_screen | `1:417` | 로그인 - 소셜 로그인(네이버/카카오/구글) + 자체 이메일 로그인 |
| 06_keyword_list | `1:448` | 키워드 관리 목록 - 활성/비활성 토글, 스와이프 삭제, FAB 추가 버튼 |
| 07_keyword_form | `1:485` | 키워드 추가/수정 - 키워드 입력 + 가격 범위 (번개장터+중고나라 통합 등록) |
| 08_register_screen | `1:511` | 회원가입 - 닉네임, 이메일, 비밀번호 |

---

## SVG 원본 파일

`docs/wireframes/` 디렉토리에 각 화면별 SVG 파일이 저장되어 있습니다.

| 파일명 | 대응 프레임 |
|---|---|
| `01_daangn_tab.svg` | 01_daangn_tab |
| `02_market_tab.svg` | 02_market_tab |
| `03_alerts_tab.svg` | 03_alerts_tab |
| `04_settings_tab.svg` | 04_settings_tab |
| `05_login_screen.svg` | 05_login_screen |
| `06_keyword_list.svg` | 06_keyword_list |
| `07_keyword_form.svg` | 07_keyword_form |
| `08_register_screen.svg` | 08_register_screen |

---

## MCP 접근 방법

Figma MCP 도구를 통해 디자인 정보를 읽을 수 있습니다.

```
# 전체 메타데이터 조회
get_metadata(fileKey="LnFgPrgTDokH3FfjGJ4hqB", nodeId="0:1")

# 특정 프레임 디자인 컨텍스트 조회
get_design_context(fileKey="LnFgPrgTDokH3FfjGJ4hqB", nodeId="1:357")  # 당근 검색
get_design_context(fileKey="LnFgPrgTDokH3FfjGJ4hqB", nodeId="1:180")  # 매물 검색
```

---

## 설계 참고사항

- **탭2 매물 검색**: 번개장터/중고나라 플랫폼 선택 없이 항상 통합 검색
- **탭1 당근 검색**: 지역 자동완성은 구/군 레벨까지만 표시, 선택 후 하위 모든 동을 병렬 검색
- **키워드 등록**: 플랫폼 선택 없이 번개장터 + 중고나라 모두에 적용
- **당근은 키워드 알림 대상이 아님**: 지역 기반 검색 특성상 스케줄러 폴링 제외
