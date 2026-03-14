# Figma MCP 서버 설정 가이드

## 개요

Figma MCP 서버를 Claude Code에 연결하면 다음이 가능하다:
- Figma 디자인을 읽어 코드로 변환 (Design → Code)
- Claude Code에서 만든 UI를 Figma에 푸시 (Code → Design)
- 디자인 수정 후 다시 코드에 반영하는 양방향 워크플로우

---

## 권장 구성: 공식 Remote MCP + Framelink 동시 사용 (무료 무제한)

Figma Starter(무료) 플랜에서 **공식 MCP 서버의 읽기는 월 6회로 제한**되지만,
**Framelink(오픈소스)을 읽기 전용으로 병행**하면 사실상 무료 무제한으로 사용할 수 있다.

| 작업 | 사용 서버 | 제한 | 비용 |
|---|---|---|---|
| **읽기** (Figma → 코드) | Framelink | Figma REST API rate limit만 (1~2명 사용 시 제한 없음) | 무료 |
| **쓰기** (코드 → Figma) | 공식 Remote MCP | **rate limit 면제** | 무료 |

> 1~2명이 일반적인 개발 속도로 사용하는 수준에서는 API rate limit에 걸릴 일이 거의 없다.

### 한 줄 요약

- **디자인 읽기** → Framelink (무제한)
- **Figma에 푸시** → 공식 Remote MCP (쓰기 면제)
- **결과:** 무료 플랜으로 양방향 동기화를 제한 없이 사용 가능

---

## Figma 무료 플랜 (Starter) 제한 사항

| 항목 | Starter (무료) | Professional ($12/월) |
|---|---|---|
| 공식 MCP 읽기 도구 호출 | **월 6회** | 분당 제한 (사실상 무제한) |
| 공식 MCP 쓰기 도구 호출 | **제한 없음** (면제) | 제한 없음 |
| 디자인 파일 | 팀 3개, 개인 무제한 | 무제한 |
| Dev Mode | 기본 inspect만 | 전체 기능 |

> **공식 MCP 월 6회 제한은 읽기 도구에만 적용된다.**
> Figma에 디자인을 **푸시(쓰기)**하는 도구(`create_figma_file`, `create_component_in_figma`)는 면제.
> 읽기는 Framelink으로 대체하면 이 제한을 우회할 수 있다.

---

## 설정 1: Framelink MCP 서버 (읽기 전용, 무제한)

Figma REST API + Personal Access Token을 사용하며, 읽기 전용이다.
공식 MCP 서버의 월 6회 읽기 제한 없이 무제한으로 디자인 데이터를 가져올 수 있다.

### 1단계: Figma Personal Access Token 생성

1. [Figma](https://www.figma.com) 접속 → 좌상단 프로필 클릭
2. **Settings** → **Security** 섹션
3. **Personal access tokens** → **Generate new token**
4. 이름 입력 (예: `claude-mcp`) → 권한: **File content — Read only**
5. 생성된 토큰 복사 (한 번만 표시됨)

### 2단계: MCP 서버 추가

```bash
claude mcp add figma-framelink --command npx -- -y figma-developer-mcp --figma-api-key=YOUR_TOKEN_HERE --stdio
```

또는 `.claude/settings.local.json`에 직접 추가:

```json
{
  "mcpServers": {
    "figma-framelink": {
      "command": "npx",
      "args": [
        "-y",
        "figma-developer-mcp",
        "--figma-api-key=YOUR_TOKEN_HERE",
        "--stdio"
      ]
    }
  }
}
```

> **보안 주의:** API 토큰은 `.claude/settings.local.json`에 넣고 `.gitignore`에 추가하여 git에 커밋되지 않도록 한다.

### 3단계: 연결 확인

```bash
/mcp
# figma-framelink → connected 확인
```

### Framelink 특징

- Figma API 데이터를 **약 90% 압축**하여 전달 (토큰 절약)
- 읽기 전용 (Figma에 푸시는 불가 → 쓰기는 공식 MCP 사용)
- **공식 서버의 월 6회 제한 없음** (Figma REST API rate limit만 적용)
- Node.js (npx) 필요

---

## 설정 2: Figma 공식 Remote MCP 서버 (쓰기 전용으로 활용)

OAuth 기반 인증으로, Personal Access Token 없이 브라우저 로그인으로 연결한다.
Framelink과 병행 시 **쓰기(푸시) 전용**으로 사용하며, 쓰기는 rate limit이 면제된다.

### 1단계: MCP 서버 추가

```bash
# 현재 프로젝트에만 적용
claude mcp add --transport http figma-remote-mcp https://mcp.figma.com/mcp

# 모든 프로젝트에서 사용하려면 (글로벌)
claude mcp add --scope user --transport http figma-remote-mcp https://mcp.figma.com/mcp
```

### 2단계: 인증

1. Claude Code에서 `/mcp` 입력
2. `figma-remote-mcp` 서버가 `disconnected`로 표시되면 Enter
3. 브라우저가 열리면 Figma 계정으로 로그인
4. **Allow access** 클릭하여 Claude Code 접근 허용

### 3단계: 연결 확인

```bash
/mcp
# figma-remote-mcp → connected 확인
```

### 제공 도구 (Tools)

| 도구 | 설명 | Rate Limit | 용도 |
|---|---|---|---|
| `get_figma_data` | 디자인 데이터 읽기 | 월 6회 (Starter) | **Framelink으로 대체** |
| `download_figma_images` | 이미지/아이콘 다운로드 | 월 6회 (Starter) | **Framelink으로 대체** |
| `create_figma_file` | 새 Figma 파일 생성 | **면제** | 이 서버로 사용 |
| `create_component_in_figma` | 컴포넌트 생성/수정 | **면제** | 이 서버로 사용 |

> 읽기 도구는 Framelink으로 대체하므로, 이 서버는 **쓰기 도구만 사용**하면 월 6회 제한에 걸리지 않는다.

---

## 빠른 설정 (두 서버 동시 추가)

```bash
# 1. Framelink (읽기 전용) — Personal Access Token 필요
claude mcp add figma-framelink --command npx -- -y figma-developer-mcp --figma-api-key=YOUR_TOKEN --stdio

# 2. 공식 Remote MCP (쓰기 전용) — OAuth 브라우저 인증
claude mcp add --transport http figma-remote-mcp https://mcp.figma.com/mcp
```

연결 후 `/mcp`에서 두 서버 모두 `connected` 상태인지 확인한다.

---

## 두 MCP 서버 역할 비교

| 항목 | Framelink (읽기) | 공식 Remote MCP (쓰기) |
|---|---|---|
| 인증 방식 | Personal Access Token | OAuth (브라우저 로그인) |
| 디자인 읽기 | **O (무제한)** | O (월 6회 — 사용하지 않음) |
| Figma에 쓰기 | X | **O (면제)** |
| 데이터 압축 | 약 90% 압축 | 원본 |
| 추가 의존성 | Node.js (npx) | 없음 |

---

## 사용 예시

### 1. Figma 디자인 → Python 코드 변환

```
# Claude Code에서:
이 Figma 파일의 로그인 화면을 Flask + Jinja2 템플릿으로 만들어줘
[Figma 파일 URL 붙여넣기]
```

### 2. 특정 프레임만 코드로 변환

```
# Figma에서 프레임 선택 → 우클릭 → Copy link
이 프레임을 HTML/CSS로 변환해줘
https://www.figma.com/file/xxxxx?node-id=123:456
```

### 3. 코드에서 Figma로 푸시 (공식 MCP만 가능)

```
# Claude Code에서:
현재 login.html 템플릿을 Figma 파일로 푸시해줘
```

### 4. 디자인 수정 후 코드 반영

```
# Figma에서 디자인 수정 후:
Figma에서 변경된 로그인 화면을 다시 읽어서 코드에 반영해줘
https://www.figma.com/file/xxxxx
```

---

## 트러블슈팅

### MCP 서버 연결 실패

```bash
# MCP 서버 상태 확인
/mcp

# 서버 재시작
claude mcp remove figma-remote-mcp
claude mcp add --transport http figma-remote-mcp https://mcp.figma.com/mcp
```

### Framelink npx 실행 오류

```bash
# Node.js 설치 확인
node --version   # v18+ 필요
npx --version

# 캐시 정리 후 재시도
npx clear-npx-cache
```

### 공식 MCP 읽기 월 6회 제한 초과 시

- 읽기는 Framelink을 사용하면 제한 없음
- 공식 MCP의 읽기 도구를 실수로 사용하지 않도록 주의
- Professional 플랜($12/월) 업그레이드 시 공식 MCP도 사실상 무제한

---

## 참고 링크

- [Figma MCP 서버 공식 가이드](https://help.figma.com/hc/en-us/articles/32132100833559-Guide-to-the-Figma-MCP-server)
- [Figma Remote MCP 설정](https://developers.figma.com/docs/figma-mcp-server/remote-server-installation/)
- [Figma 플랜별 MCP 권한](https://developers.figma.com/docs/figma-mcp-server/plans-access-and-permissions/)
- [Framelink GitHub](https://github.com/GLips/Figma-Context-MCP)
- [Claude Code + Figma 블로그](https://www.builder.io/blog/claude-code-figma-mcp-server)
- [Figma MCP 서버 가이드 GitHub](https://github.com/figma/mcp-server-guide)
