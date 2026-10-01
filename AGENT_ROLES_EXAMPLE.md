# 🤖 GEMINI.md vs rules/ 분리 가이드 (`AGENT_ROLES_EXAMPLE.md`)

에이전트 지침을 효과적으로 적용하기 위해 **개요 및 역할 정의는 `GEMINI.md`**에, **강력한 강제 규칙은 `rules/`**에 나누어 작성합니다.

---

## 1. `rules/subagents.md` 에 넣을 내용 (강제 행동 규칙)

> 💡 **용도**: AI가 반드시 지켜야 하는 **강력한 제약, 트리거, 검증 게이트**를 담당합니다. (우선순위 최고)

```markdown
# Strict Subagent & Watchdog Rules (엄격한 서브에이전트 및 감시 규칙)

1. **Mandatory Role Delegation** (필수 역할 위임):
   - For broad research or large file reading, MUST spawn `research` subagent. (광범위한 조사나 대형 파일 열람 시 반드시 research 에이전트를 호출할 것)
   - Assign implementation to `coder` with explicit file boundaries. (코드 구현은 명확한 파일 경계와 함께 coder에게 위임할 것)
   - NEVER declare completion without running `tester` verification. (tester의 검증 테스트 통과 없이 절대로 완료를 선언하지 말 것)

2. **Trigger-based Quality Gates** (트리거 기반 품질 게이트):
   - When 2+ files or 80+ lines are modified, MUST trigger `tester` immediately. (파일 2개 이상 또는 80줄 이상 수정 시 즉시 tester를 호출해 테스트할 것)
   - Every 5 tool executions, perform a health check before making further edits. (툴 실행이 5회 누적될 때마다 다음 수정 전 중간 점검을 수행할 것)
   - Any test failure MUST be routed to `debugger` immediately. (테스트 실패 시 즉시 debugger를 호출하여 버그부터 수정할 것)

3. **Communication Rule** (사용자 대화 원칙):
   - Keep chat responses short and conversational (2-3 sentences max). (대화창 답변은 2~3줄 이내로 짧고 대화하듯 작성할 것)
   - Put detailed analysis and checklists into separate markdown documents. (상세 분석과 체크리스트는 항상 별도 마크다운 문서로 분리할 것)
   - Always respond to the user in Korean. (사용자에게는 항상 한국어로 응답할 것)
```

---

## 2. `GEMINI.md` 에 넣을 내용 (팀 구성 및 역할 개요)

> 💡 **용도**: 프로젝트의 **전체 팀 구조, 에이전트 이름(ID), 기본 분업 체계**를 안내하는 총괄 가이드입니다.

```markdown
# Project Team Architecture & Agents (프로젝트 팀 구조 및 에이전트 안내)

This workspace uses role-based multi-agent collaboration: (이 작업공간은 역할 기반 다중 에이전트 협업 체계를 따릅니다)

[Available Subagents (사용 가능한 서브에이전트 팀)]
- `research`: Documentation, web research, and API spec analysis. (자료 조사, 공식 문서 및 API 스펙 분석 담당)
- `coder`: Clean code implementation and refactoring. (깔끔한 코드 구현 및 리팩토링 담당)
- `tester`: Automated test execution, build checks, and regression tests. (자동 테스트 실행, 빌드 체크 및 회귀 검증 담당)
- `debugger`: Root-cause analysis and bug fixes on failures. (에러 발생 시 근본 원인 분석 및 버그 수정 담당)

[Policy Reference (규칙 참조)]
- Strict delegation and watchdog triggers are enforced in `rules/subagents.md`. (엄격한 분업 지침 및 감시자 트리거는 rules/subagents.md에서 강제됩니다)
```
