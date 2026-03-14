---
name: git commit 단축 명령
description: 사용자가 "git commit"이라고만 말하면 변경 내용 확인 → 커밋 메시지 작성 → commit + push까지 자동 수행
type: feedback
---

사용자가 "git commit"이라고만 입력하면 아래 절차를 자동으로 수행한다.

1. `git status` + `git diff`로 변경 내용 확인
2. 변경 내용을 분석하여 한국어 커밋 메시지 작성
3. 관련 파일 staging → commit → `git push origin main`까지 수행

**Why:** 매번 커밋할 때 상세 지시를 반복하기 번거로움. "git commit" 한마디로 전체 흐름을 자동화하고 싶음.

**How to apply:** "git commit" 메시지를 받으면 확인 없이 바로 위 절차를 실행한다. 커밋 메시지는 기존 레포 스타일(한국어, 제목 + 상세 설명)을 따른다.
